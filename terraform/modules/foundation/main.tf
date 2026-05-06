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
# Bedrock KB Execution Role
# HCL-User-Role-PD-BedrockAgentCoreRole lacks aoss:APIAccessAll
# (required for Bedrock to validate AOSS storage at KB creation
# time), so we create a dedicated KB role.
#
# The permissions boundary (HCL-Permissions-Boundary) allows
# iam:CreateRole / iam:PutRolePolicy on AmazonBedrockExecution*
# resources that carry the AmazonBedrockManaged=true tag.
# ─────────────────────────────────────────────────────────────

resource "aws_iam_role" "kb_execution" {
  name        = "AmazonBedrockExecutionRoleForKnowledgeBase_petstore"
  description = "Execution role for petstore Bedrock Knowledge Bases"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AmazonBedrockKnowledgeBaseTrustPolicy"
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = var.aws_account_id
          }
          ArnLike = {
            "aws:SourceArn" = "arn:aws:bedrock:${var.aws_region}:${var.aws_account_id}:knowledge-base/*"
          }
        }
      }
    ]
  })

  tags = {
    AmazonBedrockManaged = "true"
    Project              = var.project_name
    Phase                = "1-foundation"
  }
}

resource "aws_iam_role_policy" "kb_aoss" {
  name = "AOSS-APIAccess"
  role = aws_iam_role.kb_execution.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "aoss:APIAccessAll"
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "kb_s3" {
  name = "S3-KnowledgeBucket"
  role = aws_iam_role.kb_execution.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.knowledge_data.arn,
          "${aws_s3_bucket.knowledge_data.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "kb_bedrock" {
  name = "Bedrock-EmbeddingModel"
  role = aws_iam_role.kb_execution.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0"
      }
    ]
  })
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
