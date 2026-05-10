# ─────────────────────────────────────────────────────────────
# ECR Repository
# force_delete = true: ECR refuses to delete a non-empty repo,
# so we must enable this for terraform destroy to work cleanly.
# ─────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "agent" {
  name         = "petstore-agent-repo"
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Project = var.project_name
    Phase   = "6-agent-image"
  }
}

resource "aws_ecr_lifecycle_policy" "agent" {
  repository = aws_ecr_repository.agent.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the last 5 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = { type = "expire" }
      }
    ]
  })
}

# ─────────────────────────────────────────────────────────────
# CodeBuild Project — ARM64 Docker image builder
#
# ARM_CONTAINER + aarch64 build image: required because AgentCore
# Runtime runs on Graviton (ARM64). An AMD64 image would fail at
# runtime with "exec format error".
#
# privilegedMode = true: Docker-in-Docker requires elevated
# container privileges to start the Docker daemon.
#
# Source: S3 bucket from Phase 1 (codebuild_staging).
# The null_resource below zips and uploads the repo source before
# starting the build.
# ─────────────────────────────────────────────────────────────

resource "aws_codebuild_project" "agent_builder" {
  name          = "petstore-agent-builder"
  description   = "Builds the ARM64 pet store agent Docker image and pushes to ECR"
  service_role  = var.codebuild_role_arn
  build_timeout = 30

  source {
    type      = "S3"
    location  = "${var.codebuild_bucket_name}/petstore-source.zip"
    buildspec = yamlencode({
      version = "0.2"
      phases = {
        pre_build = {
          commands = [
            "echo Logging in to Amazon ECR...",
            "aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${var.aws_account_id}.dkr.ecr.${var.aws_region}.amazonaws.com",
            # ECR Public (public.ecr.aws) supports anonymous pulls — no auth needed.
            # The CodeBuild role lacks ecr-public:GetAuthorizationToken, so we skip it.
          ]
        }
        build = {
          commands = [
            "echo Building ARM64 Docker image...",
            "docker build --platform linux/arm64 -t petstore-agent:latest .",
          ]
        }
        post_build = {
          commands = [
            "echo Tagging and pushing image to ECR...",
            "docker tag petstore-agent:latest ${aws_ecr_repository.agent.repository_url}:latest",
            "docker push ${aws_ecr_repository.agent.repository_url}:latest",
            "echo Build complete.",
          ]
        }
      }
    })
  }

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    type            = "ARM_CONTAINER"
    compute_type    = "BUILD_GENERAL1_SMALL"
    image           = "aws/codebuild/amazonlinux2-aarch64-standard:3.0"
    privileged_mode = true
  }

  tags = {
    Project = var.project_name
    Phase   = "6-agent-image"
  }
}

# ─────────────────────────────────────────────────────────────
# Build Trigger
#
# triggers hash: any change to agent source or Dockerfile causes
# the null_resource to replace → re-upload source → rebuild image.
#
# Steps:
#   1. Zip repo root (excluding .git and terraform state) → upload to S3
#   2. Start CodeBuild build
#   3. Poll until SUCCEEDED or FAILED
# ─────────────────────────────────────────────────────────────

resource "null_resource" "trigger_image_build" {
  triggers = {
    ecr_repo_url     = aws_ecr_repository.agent.repository_url
    codebuild_project = aws_codebuild_project.agent_builder.name
    agent_code_hash  = sha256(join("", [
      filesha256("${path.root}/../pet_store_agent/agentcore_entrypoint.py"),
      filesha256("${path.root}/../pet_store_agent/pet_store_agent.py"),
      filesha256("${path.root}/../pet_store_agent/retrieve_product_info.py"),
      filesha256("${path.root}/../pet_store_agent/retrieve_pet_care.py"),
      filesha256("${path.root}/../pet_store_agent/inventory_management.py"),
      filesha256("${path.root}/../pet_store_agent/user_management.py"),
      filesha256("${path.root}/../pet_store_agent/requirements.txt"),
      filesha256("${path.root}/../pet_store_agent/tracing.py"),
      filesha256("${path.root}/../Dockerfile"),
    ]))
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      echo "Zipping repo source for CodeBuild..."
      python3 ${path.module}/../../scripts/zip_source.py \
        --source-dir ${path.root}/.. \
        --output /tmp/petstore-source.zip
      echo "Uploading source to S3..."
      aws s3 cp /tmp/petstore-source.zip s3://${var.codebuild_bucket_name}/petstore-source.zip
      echo "Starting CodeBuild build..."
      BUILD_ID=$(aws codebuild start-build \
        --project-name ${aws_codebuild_project.agent_builder.name} \
        --region ${var.aws_region} \
        --query 'build.id' --output text)
      echo "Build started: $BUILD_ID"
      echo "Polling for completion (this takes ~8 minutes)..."
      python3 ${path.module}/../../scripts/poll_codebuild.py \
        --build-id "$BUILD_ID" \
        --region ${var.aws_region}
    EOT
  }

  depends_on = [
    aws_ecr_repository.agent,
    aws_codebuild_project.agent_builder,
  ]
}
