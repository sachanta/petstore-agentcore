output "product_info_kb_id" {
  description = "ID of the ProductInformation knowledge base (KNOWLEDGE_BASE_1_ID for the agent)"
  value       = aws_bedrockagent_knowledge_base.product_info.id
}

output "pet_care_kb_id" {
  description = "ID of the PetCaringKnowledge knowledge base (KNOWLEDGE_BASE_2_ID for the agent)"
  value       = aws_bedrockagent_knowledge_base.pet_care.id
}

output "s3_data_source_id" {
  description = "ID of the S3 data source attached to ProductInformation KB"
  value       = aws_bedrockagent_data_source.s3.data_source_id
}
