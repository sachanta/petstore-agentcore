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
  description = "ARN of the pre-existing solution access role (used by AgentCore runtime)"
  type        = string
}

variable "kb_execution_role_arn" {
  description = "ARN of the Bedrock KB execution role (AmazonBedrockExecution* with aoss:APIAccessAll)"
  type        = string
}

variable "aoss_collection_arn" {
  description = "ARN of the AOSS collection (from aoss module output)"
  type        = string
}

variable "knowledge_bucket_arn" {
  description = "ARN of the S3 bucket that holds the product knowledge files"
  type        = string
}

variable "knowledge_bucket_name" {
  description = "Name of the S3 bucket that holds the product knowledge files"
  type        = string
}
