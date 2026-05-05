output "solution_access_role_arn" {
  description = "ARN of the IAM role used by Lambda, Bedrock, and AgentCore"
  value       = module.foundation.solution_access_role_arn
}

output "codebuild_role_arn" {
  description = "ARN of the IAM role used by CodeBuild"
  value       = module.foundation.codebuild_role_arn
}

output "knowledge_bucket_name" {
  description = "S3 bucket name holding the pet-store-products knowledge files"
  value       = module.foundation.knowledge_bucket_name
}

output "knowledge_bucket_arn" {
  description = "ARN of the knowledge S3 bucket (needed by Bedrock data source config)"
  value       = module.foundation.knowledge_bucket_arn
}

output "codebuild_bucket_name" {
  description = "S3 bucket name used as CodeBuild source staging area"
  value       = module.foundation.codebuild_bucket_name
}
