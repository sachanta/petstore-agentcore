output "ecr_repository_url" {
  description = "ECR repository URL (without tag)"
  value       = aws_ecr_repository.agent.repository_url
}

output "ecr_image_uri" {
  description = "Full URI of the latest agent image"
  value       = "${aws_ecr_repository.agent.repository_url}:latest"
}

output "agent_code_hash" {
  description = "Hash of agent source files — changes when any agent code changes"
  value       = null_resource.trigger_image_build.triggers["agent_code_hash"]
}
