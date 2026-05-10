# Terraform — Ops Troubleshooting

Common operational issues encountered when running `terraform apply` in this project.

---

## 1. `TF_VAR_*` variables not picked up — missing `export`

### Symptom

Credentials stored in `terraform/.env` appear correct when you `echo` them, but Terraform passes empty values to the runtime. The deployed resource ends up with blank env vars despite the `.env` file looking right.

Example: `ARIZE_SPACE_ID` shows as empty string inside the container even though `terraform/.env` contains the correct value. CloudWatch logs say:

```
ARIZE_SPACE_ID or ARIZE_API_KEY not set — tracing disabled.
```

And the runtime API confirms the variable landed empty:

```python
resp = c.get_agent_runtime(agentRuntimeId=rt_id)
resp["environmentVariables"]["ARIZE_SPACE_ID"]  # → ''
```

### Root cause

`source terraform/.env` sets variables in the **current shell** but does not export them to child processes. Terraform runs as a subprocess — it only sees variables that have been exported via `export`.

Without `export`:
```bash
source .env
echo $TF_VAR_arize_space_id   # works — current shell sees it
terraform apply                # Terraform subprocess does NOT see it
```

`TF_VAR_*` variables must be in the environment (not just the shell) for Terraform to read them.

Additionally, `TF_VAR_arize_space_id` is a base64 string ending in `==`. When passed unquoted through a shell heredoc in the Terraform `local-exec` provisioner, the `=` signs can cause parsing issues. The `deploy_runtime.py` script uses `kv.partition("=")` which correctly handles `KEY=VALUE==` by splitting only on the first `=` — but this only works if the variable reached Terraform in the first place.

### Fix

Add `export` to every line in `terraform/.env`:

```bash
export TF_VAR_arize_space_id=U3BhY2U6MTE0MzY6SmRmRA==
export TF_VAR_arize_api_key=ak-...
export TF_VAR_arize_project_name=virtual-pet-store-agent
```

Then `source .env && terraform apply` will work correctly.

### How to verify before applying

```bash
source terraform/.env
python3 -c "import os; print(os.environ.get('TF_VAR_arize_space_id', 'NOT_SET'))"
```

If it prints `NOT_SET`, the variable is not exported. If it prints the value, Terraform will see it.

### Recovering a live runtime with wrong env vars

If `terraform apply` has already run with empty values, you can patch the runtime directly without a full redeploy:

```python
import boto3

c = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
rt_id = "<your-runtime-id>"

resp = c.get_agent_runtime(agentRuntimeId=rt_id)
env = resp["environmentVariables"]
env["ARIZE_SPACE_ID"] = "<correct-value>"   # patch the empty value

c.update_agent_runtime(
    agentRuntimeId=rt_id,
    agentRuntimeArtifact=resp["agentRuntimeArtifact"],
    roleArn=resp["roleArn"],
    networkConfiguration=resp["networkConfiguration"],
    environmentVariables=env,
)
```

This triggers an in-place update (status: UPDATING → READY) without rebuilding the container image. Takes ~30 seconds.

---

## 2. Runtime ARN changes on each redeploy

### Symptom

After `terraform apply`, invoking the agent with the old ARN returns:

```
ResourceNotFoundException: No endpoint or agent found with qualifier 'DEFAULT'
```

### Root cause

Each `terraform apply` that triggers the `null_resource.agent_runtime` (due to a trigger change) destroys and recreates the runtime, which assigns a new random suffix to the runtime ID.

The runtime ARN is written to `terraform/modules/agent_runtime/tmp/runtime_outputs.json` during apply. The Terraform output (`agent_runtime_arn`) reads from this file — but the UI and test scripts cache the old ARN.

### Fix

After any `terraform apply` that touches the runtime, update `ui/.env`:

```bash
RUNTIME_ARN=$(cd terraform && terraform output -raw agent_runtime_arn)
sed -i "s|RUNTIME_ARN=.*|RUNTIME_ARN=$RUNTIME_ARN|" ui/.env
```

Or read it directly from the output file:

```bash
cat terraform/modules/agent_runtime/tmp/runtime_outputs.json
```

For the test suite:

```bash
export RUNTIME_ARN=$(cd terraform && terraform output -raw agent_runtime_arn)
python3 tests/test_agent.py
```

---

## 3. Runtime not redeploying after image rebuild

### Symptom

Code changes are pushed, CodeBuild rebuilds the image, but the running runtime still executes old code. The ECR image tag is `:latest` — it never changes, so Terraform sees no trigger change and skips the runtime update.

### Root cause

The `null_resource.agent_runtime` triggers on `image_uri`, which is always `<account>.dkr.ecr.<region>.amazonaws.com/petstore-agent-repo:latest`. When the image is rebuilt, the URI doesn't change — only the digest behind the tag does. Terraform doesn't track image digests.

### Fix

An `agent_code_hash` trigger was added to both the image build and runtime resources. It's computed from the SHA256 of all agent source files:

```hcl
agent_code_hash = sha256(join("", [
  filesha256("${path.root}/../pet_store_agent/agentcore_entrypoint.py"),
  filesha256("${path.root}/../pet_store_agent/pet_store_agent.py"),
  filesha256("${path.root}/../pet_store_agent/tracing.py"),
  # ...
]))
```

This hash changes whenever any source file changes, causing Terraform to replace the `null_resource` and trigger a runtime update.

If you add a new source file to the agent, add its `filesha256()` to the list in `terraform/modules/agent_image/main.tf`.

### Immediate fix (before the hash was wired in)

```bash
terraform taint module.agent_runtime.null_resource.agent_runtime
terraform apply
```

This forces the runtime resource to be replaced on the next apply regardless of triggers.
