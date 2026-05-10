variable "aws_region" {
  description = "AWS region to deploy resources into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used as a prefix/tag on all resources"
  type        = string
  default     = "petstore"
}

variable "arize_space_id" {
  description = "Arize AX Space ID. Pass via TF_VAR_arize_space_id env var — do not hardcode."
  type        = string
  default     = ""
  sensitive   = true
}

variable "arize_api_key" {
  description = "Arize AX API key. Pass via TF_VAR_arize_api_key env var — do not hardcode."
  type        = string
  default     = ""
  sensitive   = true
}

variable "arize_project_name" {
  description = "Arize project name for grouping traces in the UI"
  type        = string
  default     = "virtual-pet-store-agent"
}
