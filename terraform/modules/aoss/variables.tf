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

variable "solution_access_role_arn" {
  description = "ARN of the IAM role granted data access on the AOSS collection"
  type        = string
}

variable "kb_execution_role_arn" {
  description = "ARN of the Bedrock KB execution role (needs data access for Bedrock to validate KB storage)"
  type        = string
}

variable "collection_name" {
  description = "Name of the AOSS collection (must be lowercase alphanumeric + hyphens, max 32 chars)"
  type        = string
  default     = "clashofagents"
}
