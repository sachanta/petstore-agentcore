variable "project_name" {
  description = "Short project name used as prefix on all resources"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "ecr_image_uri" {
  description = "Full ECR image URI (repository:tag) for the agent container"
  type        = string
}

variable "solution_access_role_arn" {
  description = "ARN of the IAM role used by the AgentCore Runtime"
  type        = string
}

variable "product_info_kb_id" {
  description = "Bedrock Knowledge Base ID for ProductInformation (KNOWLEDGE_BASE_1_ID)"
  type        = string
}

variable "pet_care_kb_id" {
  description = "Bedrock Knowledge Base ID for PetCaringKnowledge (KNOWLEDGE_BASE_2_ID)"
  type        = string
}

variable "inventory_function_name" {
  description = "Lambda function name for inventory management (SYSTEM_FUNCTION_1_NAME)"
  type        = string
}

variable "user_management_function_name" {
  description = "Lambda function name for user management (SYSTEM_FUNCTION_2_NAME)"
  type        = string
}
