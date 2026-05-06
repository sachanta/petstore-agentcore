variable "project_name" {
  description = "Short project name used as prefix on all resources"
  type        = string
}

variable "solution_access_role_arn" {
  description = "ARN of the IAM role used as Lambda execution role"
  type        = string
}
