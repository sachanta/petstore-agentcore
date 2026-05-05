variable "project_name" {
  description = "Short project name used as prefix on all resources"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID (injected from data source — not hardcoded)"
  type        = string
}

variable "product_files" {
  description = "Set of .txt filenames in the pet-store-products directory"
  type        = set(string)
}

variable "product_files_path" {
  description = "Absolute path to the pet-store-products directory"
  type        = string
}
