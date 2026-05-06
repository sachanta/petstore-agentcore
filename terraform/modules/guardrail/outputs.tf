output "guardrail_id" {
  description = "ID of the Bedrock guardrail"
  value       = aws_bedrock_guardrail.petstore.guardrail_id
}

output "guardrail_arn" {
  description = "ARN of the Bedrock guardrail"
  value       = aws_bedrock_guardrail.petstore.guardrail_arn
}

output "guardrail_version" {
  description = "Published version number of the guardrail (e.g. '1')"
  value       = aws_bedrock_guardrail_version.v1.version
}
