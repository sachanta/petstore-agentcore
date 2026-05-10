# ─────────────────────────────────────────────────────────────
# CloudWatch Log Group
# Captures agent runtime logs. AgentCore writes here automatically.
# Also picked up by the GenAI Observability dashboard in CloudWatch
# (Application Signals → GenAI Observability).
# ─────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "agent_runtime" {
  name              = "/aws/bedrock-agentcore/petstore-agent"
  retention_in_days = 7

  tags = {
    Project = var.project_name
    Phase   = "7-agent-runtime"
  }
}

# ─────────────────────────────────────────────────────────────
# AgentCore Runtime
#
# No native Terraform resource exists for bedrock-agentcore-control
# (new service, not yet in the AWS provider). We call the API via
# deploy_runtime.py (local-exec create provisioner) and
# delete_runtime.py (local-exec destroy provisioner).
#
# triggers hash: any change to the image URI or env vars causes
# the null_resource to replace → runtime is updated.
#
# The script writes runtime ID + ARN to tmp/runtime_outputs.json.
# The local_file data source below reads that file so Terraform
# can expose outputs.
# ─────────────────────────────────────────────────────────────

locals {
  output_file   = "${path.module}/tmp/runtime_outputs.json"
  runtime_name  = "LangGraphAgentCoreRuntime"
}

resource "null_resource" "agent_runtime" {
  triggers = {
    runtime_name        = local.runtime_name
    image_uri           = var.ecr_image_uri
    role_arn            = var.solution_access_role_arn
    product_info_kb_id  = var.product_info_kb_id
    pet_care_kb_id      = var.pet_care_kb_id
    inventory_fn        = var.inventory_function_name
    user_mgmt_fn        = var.user_management_function_name
    guardrail_id        = var.guardrail_id
    guardrail_version   = var.guardrail_version
    region              = var.aws_region
    arize_space_id      = var.arize_space_id
    arize_project       = var.arize_project_name
    arize_api_key_hash  = sha256(var.arize_api_key)
    agent_code_hash     = var.agent_code_hash
  }

  provisioner "local-exec" {
    command = <<-EOT
      python3 ${path.module}/../../scripts/deploy_runtime.py \
        --runtime-name  ${local.runtime_name} \
        --image-uri     ${var.ecr_image_uri} \
        --role-arn      ${var.solution_access_role_arn} \
        --region        ${var.aws_region} \
        --output-file   ${local.output_file} \
        --env \
          AWS_DEFAULT_REGION=${var.aws_region} \
          KNOWLEDGE_BASE_1_ID=${var.product_info_kb_id} \
          KNOWLEDGE_BASE_2_ID=${var.pet_care_kb_id} \
          SYSTEM_FUNCTION_1_NAME=${var.inventory_function_name} \
          SYSTEM_FUNCTION_2_NAME=${var.user_management_function_name} \
          GUARDRAIL_ID=${var.guardrail_id} \
          GUARDRAIL_VERSION=${var.guardrail_version} \
          ARIZE_SPACE_ID=${var.arize_space_id} \
          ARIZE_API_KEY=${var.arize_api_key} \
          ARIZE_PROJECT_NAME=${var.arize_project_name}
    EOT
  }

  provisioner "local-exec" {
    when       = destroy
    on_failure = continue
    command    = <<-EOT
      python3 ${path.module}/../../scripts/delete_runtime.py \
        --runtime-name ${self.triggers.runtime_name} \
        --region       ${self.triggers.region}
    EOT
  }

  depends_on = [aws_cloudwatch_log_group.agent_runtime]
}

# ─────────────────────────────────────────────────────────────
# Read runtime outputs written by deploy_runtime.py
#
# The file is created during apply; on the first plan it won't
# exist, so we default to empty-string sentinels to avoid errors.
# ─────────────────────────────────────────────────────────────

locals {
  runtime_outputs = fileexists(local.output_file) ? jsondecode(file(local.output_file)) : {
    agent_runtime_id  = ""
    agent_runtime_arn = ""
  }
}
