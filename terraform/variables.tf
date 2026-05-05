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
