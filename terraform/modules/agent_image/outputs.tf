output "ecr_repository_url" {
  description = "ECR repository URL (without tag)"
  value       = aws_ecr_repository.agent.repository_url
}

output "ecr_image_uri" {
  description = "Full URI of the latest agent image"
  value       = "${aws_ecr_repository.agent.repository_url}:latest"
}
