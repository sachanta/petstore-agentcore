# ─────────────────────────────────────────────────────────────
# IAM Roles — reference pre-existing roles (account policy
# boundary prevents creating new roles in this environment)
#
# HCL-User-Role-PD-BedrockAgentCoreRole  → Lambda, Bedrock, AgentCore
# HCL-User-Role-Aiml-BedrockAgentCore-CodeBuild → CodeBuild
# ─────────────────────────────────────────────────────────────

data "aws_iam_role" "solution_access" {
  name = "HCL-User-Role-PD-BedrockAgentCoreRole"
}

data "aws_iam_role" "codebuild" {
  name = "HCL-User-Role-Aiml-BedrockAgentCore-CodeBuild"
}

# ─────────────────────────────────────────────────────────────
# S3 Bucket — knowledge data (product catalog files)
# ─────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "knowledge_data" {
  bucket        = "${var.project_name}-knowledge-data-${var.aws_account_id}"
  force_destroy = true # allows terraform destroy to empty + delete in one step

  tags = {
    Project = var.project_name
    Phase   = "1-foundation"
    Purpose = "bedrock-knowledge-base-source"
  }
}

resource "aws_s3_bucket_versioning" "knowledge_data" {
  bucket = aws_s3_bucket.knowledge_data.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Upload each .txt file into pet-store-products/ prefix
resource "aws_s3_object" "product_files" {
  for_each = var.product_files

  bucket       = aws_s3_bucket.knowledge_data.id
  key          = "pet-store-products/${each.value}"
  source       = "${var.product_files_path}/${each.value}"
  content_type = "text/plain"
  etag         = filemd5("${var.product_files_path}/${each.value}")

  tags = {
    Project = var.project_name
  }
}

# ─────────────────────────────────────────────────────────────
# S3 Bucket — CodeBuild source staging (Phase 6)
# ─────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "codebuild_staging" {
  bucket        = "${var.project_name}-codebuild-${var.aws_account_id}"
  force_destroy = true

  tags = {
    Project = var.project_name
    Phase   = "1-foundation"
    Purpose = "codebuild-source-staging"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "codebuild_staging" {
  bucket = aws_s3_bucket.codebuild_staging.id

  rule {
    id     = "expire-build-artifacts"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = 7
    }
  }
}
