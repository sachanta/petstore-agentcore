output "collection_arn" {
  description = "ARN of the AOSS collection"
  value       = aws_opensearchserverless_collection.main.arn
}

output "collection_endpoint" {
  description = "HTTPS endpoint of the AOSS collection (used to create indices)"
  value       = aws_opensearchserverless_collection.main.collection_endpoint
}

output "collection_id" {
  description = "ID of the AOSS collection"
  value       = aws_opensearchserverless_collection.main.id
}

output "collection_name" {
  description = "Name of the AOSS collection"
  value       = aws_opensearchserverless_collection.main.name
}
