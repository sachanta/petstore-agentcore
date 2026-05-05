output "solution_access_role_arn" {
  description = "ARN of the pre-existing IAM role for Lambda, Bedrock, and AgentCore"
  value       = data.aws_iam_role.solution_access.arn
}

output "solution_access_role_name" {
  description = "Name of the pre-existing IAM role"
  value       = data.aws_iam_role.solution_access.name
}

output "codebuild_role_arn" {
  description = "ARN of the pre-existing IAM role for CodeBuild"
  value       = data.aws_iam_role.codebuild.arn
}

output "knowledge_bucket_name" {
  description = "S3 bucket name for knowledge base source files"
  value       = aws_s3_bucket.knowledge_data.bucket
}

output "knowledge_bucket_arn" {
  description = "S3 bucket ARN (used in Bedrock data source config)"
  value       = aws_s3_bucket.knowledge_data.arn
}

output "codebuild_bucket_name" {
  description = "S3 bucket name for CodeBuild source staging"
  value       = aws_s3_bucket.codebuild_staging.bucket
}
