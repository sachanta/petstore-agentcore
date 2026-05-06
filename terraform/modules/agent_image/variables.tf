variable "project_name" {
  description = "Short project name used as prefix on all resources"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID"
  type        = string
}

variable "codebuild_role_arn" {
  description = "ARN of the IAM role used by CodeBuild"
  type        = string
}

variable "codebuild_bucket_name" {
  description = "S3 bucket used as CodeBuild source staging area"
  type        = string
}
