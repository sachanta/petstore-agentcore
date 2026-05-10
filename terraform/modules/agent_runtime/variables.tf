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

variable "guardrail_id" {
  description = "Bedrock Guardrail ID (GUARDRAIL_ID env var for the agent)"
  type        = string
}

variable "guardrail_version" {
  description = "Bedrock Guardrail published version (GUARDRAIL_VERSION env var)"
  type        = string
}

variable "arize_space_id" {
  description = "Arize AX Space ID (ARIZE_SPACE_ID env var)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "arize_api_key" {
  description = "Arize AX API key (ARIZE_API_KEY env var)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "arize_project_name" {
  description = "Arize project name for grouping traces (ARIZE_PROJECT_NAME env var)"
  type        = string
  default     = "virtual-pet-store-agent"
}

variable "agent_code_hash" {
  description = "Hash of agent source files — triggers runtime redeploy when image changes"
  type        = string
  default     = ""
}
