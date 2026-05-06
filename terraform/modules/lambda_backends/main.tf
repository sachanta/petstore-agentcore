# ─────────────────────────────────────────────────────────────
# Lambda deployment packaging
#
# archive_file zips the handler.py at plan time.  Terraform tracks
# the zip's SHA256 hash — any change to handler.py triggers a
# Lambda update on the next apply.
#
# tmp/ is .gitignored; Terraform recreates it on each plan.
# ─────────────────────────────────────────────────────────────

data "archive_file" "inventory_zip" {
  type        = "zip"
  source_file = "${path.module}/../../../lambdas/inventory/handler.py"
  output_path = "${path.module}/tmp/inventory.zip"
}

data "archive_file" "user_management_zip" {
  type        = "zip"
  source_file = "${path.module}/../../../lambdas/user_management/handler.py"
  output_path = "${path.module}/tmp/user_management.zip"
}

# ─────────────────────────────────────────────────────────────
# Inventory Lambda
#
# Uses solution_access_role_arn (HCL-User-Role-PD-BedrockAgentCoreRole)
# as the execution role.  Creating a dedicated Lambda role would
# require a name outside the AmazonBedrockExecution* pattern, which
# the HCL permissions boundary does not permit.
# ─────────────────────────────────────────────────────────────

resource "aws_lambda_function" "inventory" {
  function_name = "PetStoreInventoryManagementFunction"
  description   = "Inventory management backend for the Pet Store agent"

  role    = var.solution_access_role_arn
  runtime = "python3.12"
  handler = "handler.lambda_handler"
  timeout = 30

  filename         = data.archive_file.inventory_zip.output_path
  source_code_hash = data.archive_file.inventory_zip.output_base64sha256

  tags = {
    Project = var.project_name
    Phase   = "5-lambda-backends"
  }
}

# ─────────────────────────────────────────────────────────────
# User Management Lambda
# ─────────────────────────────────────────────────────────────

resource "aws_lambda_function" "user_management" {
  function_name = "PetStoreUserManagementFunction"
  description   = "User management backend for the Pet Store agent"

  role    = var.solution_access_role_arn
  runtime = "python3.12"
  handler = "handler.lambda_handler"
  timeout = 30

  filename         = data.archive_file.user_management_zip.output_path
  source_code_hash = data.archive_file.user_management_zip.output_base64sha256

  tags = {
    Project = var.project_name
    Phase   = "5-lambda-backends"
  }
}
