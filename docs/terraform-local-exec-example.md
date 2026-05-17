# Terraform `local-exec` — Explained with a Real Example

## What is `local-exec`?

Terraform's `local-exec` provisioner runs a shell command on **your machine** (or CI runner) --- not on the cloud resource. It's the escape hatch for when Terraform doesn't have a native resource type for a service.

In this project, it's used because **there's no `aws_bedrock_agentcore_runtime` Terraform resource** --- the service is too new for the AWS provider. So we shell out to a Python script instead.

---

## The Pattern

Here's the actual code from `terraform/modules/agent_runtime/main.tf`:

```hcl
resource "null_resource" "agent_runtime" {
  # ① TRIGGERS — Terraform tracks these values. If ANY change,
  #    the resource is destroyed and recreated (runs both provisioners).
  triggers = {
    image_uri       = var.ecr_image_uri
    guardrail_id    = var.guardrail_id
    agent_code_hash = var.agent_code_hash    # ← SHA256 of source files
    arize_space_id  = var.arize_space_id
    # ... more env vars
  }

  # ② CREATE provisioner — runs when the resource is created
  provisioner "local-exec" {
    command = <<-EOT
      python3 ${path.module}/../../scripts/deploy_runtime.py \
        --runtime-name  LangGraphAgentCoreRuntime \
        --image-uri     ${var.ecr_image_uri} \
        --role-arn      ${var.solution_access_role_arn} \
        --region        ${var.aws_region} \
        --output-file   ${local.output_file} \
        --env \
          GUARDRAIL_ID=${var.guardrail_id} \
          ARIZE_API_KEY=${var.arize_api_key}
    EOT
  }

  # ③ DESTROY provisioner — runs when the resource is destroyed
  provisioner "local-exec" {
    when       = destroy
    on_failure = continue
    command = <<-EOT
      python3 ${path.module}/../../scripts/delete_runtime.py \
        --runtime-name ${self.triggers.runtime_name} \
        --region       ${self.triggers.region}
    EOT
  }
}
```

---

## How the Pieces Fit Together

### `null_resource`

A resource that doesn't create anything in the cloud. It exists purely as a container for provisioners and triggers. It's the "I need to run a script" resource.

### `triggers`

A map of strings Terraform stores in state. When any value changes on the next `apply`, Terraform **replaces** the resource (destroy + create), which re-runs both provisioners. This is how `agent_code_hash` forces a redeploy when you edit `tracing.py` or `pet_store_agent.py`.

### Create provisioner

Calls `deploy_runtime.py`, which uses boto3 to call `create_agent_runtime()` or `update_agent_runtime()`, polls until READY, then writes the runtime ID and ARN to a JSON file. Terraform reads that file back to expose outputs.

### Destroy provisioner

Calls `delete_runtime.py` to clean up. `on_failure = continue` means if deletion fails (runtime already gone), Terraform won't block the rest of the destroy.

Note: it uses `self.triggers.*` instead of `var.*` because during destroy, variables may not be available --- only the values stored in triggers at creation time are guaranteed.

---

## The Lifecycle in Practice

```
terraform apply  (first time)
  → triggers stored in state
  → CREATE provisioner runs deploy_runtime.py
  → Runtime created, ARN written to JSON

You edit tracing.py
  → agent_code_hash changes
  → terraform apply detects trigger change
  → DESTROY provisioner runs delete_runtime.py (old runtime)
  → CREATE provisioner runs deploy_runtime.py (new runtime)
  → New ARN written to JSON

terraform destroy
  → DESTROY provisioner runs delete_runtime.py
  → null_resource removed from state
```

---

## The Gotcha We Hit

The `terraform/.env` file had `TF_VAR_arize_space_id=...` without `export`. The shell variable existed but wasn't exported to child processes. Since `terraform` is a subprocess, it never saw the variable and passed an empty string to `deploy_runtime.py`. The runtime was created with a blank `ARIZE_SPACE_ID`.

**Fix:** Add `export` to every line in `.env`:

```bash
export TF_VAR_arize_space_id=U3BhY2U6MTE0MzY6SmRmRA==
export TF_VAR_arize_api_key=<your-key>
```

See [terraform-troubleshooting.md](terraform-troubleshooting.md) for the full write-up and how to patch a live runtime without redeploying.
