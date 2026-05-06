output "agent_runtime_id" {
  description = "ID of the AgentCore Runtime"
  value       = local.runtime_outputs["agent_runtime_id"]
}

output "agent_runtime_arn" {
  description = "ARN of the AgentCore Runtime"
  value       = local.runtime_outputs["agent_runtime_arn"]
}
