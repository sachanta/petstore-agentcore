output "inventory_function_name" {
  description = "Name of the inventory Lambda function (SYSTEM_FUNCTION_1_NAME)"
  value       = aws_lambda_function.inventory.function_name
}

output "inventory_function_arn" {
  description = "ARN of the inventory Lambda function"
  value       = aws_lambda_function.inventory.arn
}

output "user_management_function_name" {
  description = "Name of the user management Lambda function (SYSTEM_FUNCTION_2_NAME)"
  value       = aws_lambda_function.user_management.function_name
}

output "user_management_function_arn" {
  description = "ARN of the user management Lambda function"
  value       = aws_lambda_function.user_management.arn
}
