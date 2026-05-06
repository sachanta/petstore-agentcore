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

output "aoss_collection_arn" {
  description = "ARN of the AOSS vector search collection"
  value       = module.aoss.collection_arn
}

output "aoss_collection_endpoint" {
  description = "HTTPS endpoint of the AOSS collection"
  value       = module.aoss.collection_endpoint
}

output "kb_execution_role_arn" {
  description = "ARN of the Bedrock KB execution role"
  value       = module.foundation.kb_execution_role_arn
}

output "product_info_kb_id" {
  description = "ID of the ProductInformation knowledge base (KNOWLEDGE_BASE_1_ID)"
  value       = module.knowledge_bases.product_info_kb_id
}

output "pet_care_kb_id" {
  description = "ID of the PetCaringKnowledge knowledge base (KNOWLEDGE_BASE_2_ID)"
  value       = module.knowledge_bases.pet_care_kb_id
}

output "s3_data_source_id" {
  description = "ID of the S3 data source for ProductInformation KB"
  value       = module.knowledge_bases.s3_data_source_id
}

output "agent_runtime_id" {
  description = "ID of the AgentCore Runtime"
  value       = module.agent_runtime.agent_runtime_id
}

output "agent_runtime_arn" {
  description = "ARN of the AgentCore Runtime"
  value       = module.agent_runtime.agent_runtime_arn
}

output "ecr_image_uri" {
  description = "Full URI of the latest agent image in ECR"
  value       = module.agent_image.ecr_image_uri
}

output "inventory_function_name" {
  description = "Name of the inventory Lambda function (SYSTEM_FUNCTION_1_NAME)"
  value       = module.lambda_backends.inventory_function_name
}

output "user_management_function_name" {
  description = "Name of the user management Lambda function (SYSTEM_FUNCTION_2_NAME)"
  value       = module.lambda_backends.user_management_function_name
}

output "guardrail_id" {
  description = "ID of the Bedrock guardrail"
  value       = module.guardrail.guardrail_id
}

output "guardrail_version" {
  description = "Published version number of the guardrail"
  value       = module.guardrail.guardrail_version
}

output "guardrail_arn" {
  description = "ARN of the Bedrock guardrail"
  value       = module.guardrail.guardrail_arn
}
