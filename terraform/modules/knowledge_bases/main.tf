# ─────────────────────────────────────────────────────────────
# ProductInformation Knowledge Base
# Backed by AOSS product_info_index.
# Used by the agent tool retrieve_product_info (KNOWLEDGE_BASE_1_ID).
# ─────────────────────────────────────────────────────────────

resource "aws_bedrockagent_knowledge_base" "product_info" {
  name        = "ProductInformation"
  description = "Product information knowledge base containing: a product catalog providing product descriptions, customer advantages, and detailed product specifications."
  role_arn    = var.kb_execution_role_arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = var.aoss_collection_arn
      vector_index_name = "product_info_index"
      field_mapping {
        vector_field   = "vector"
        text_field     = "text"
        metadata_field = "metadata"
      }
    }
  }

  tags = {
    Project = var.project_name
    Phase   = "3-knowledge-bases"
  }
}

# ─────────────────────────────────────────────────────────────
# S3 Data Source — product catalog files
# Reads *.txt files from pet-store-products/ prefix in the
# knowledge bucket.  Native Terraform resource exists for S3.
# ─────────────────────────────────────────────────────────────

resource "aws_bedrockagent_data_source" "s3" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.product_info.id
  name              = "S3DataSource"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn         = var.knowledge_bucket_arn
      inclusion_prefixes = ["pet-store-products/"]
    }
  }
}

# ─────────────────────────────────────────────────────────────
# Trigger S3 ingestion — sync product files into product_info_index
# Bedrock has the data source config but won't read docs until
# an ingestion job is started explicitly.
# ─────────────────────────────────────────────────────────────

resource "null_resource" "s3_ingestion" {
  triggers = {
    data_source_id    = aws_bedrockagent_data_source.s3.data_source_id
    knowledge_base_id = aws_bedrockagent_knowledge_base.product_info.id
    region            = var.aws_region
    script_hash       = filesha256("${path.module}/../../scripts/start_ingestion.py")
  }

  provisioner "local-exec" {
    command = <<-EOT
      python3 ${path.module}/../../scripts/start_ingestion.py \
        --knowledge-base-id ${self.triggers.knowledge_base_id} \
        --data-source-id ${self.triggers.data_source_id} \
        --region ${self.triggers.region}
    EOT
  }

  depends_on = [aws_bedrockagent_data_source.s3]
}

# ─────────────────────────────────────────────────────────────
# PetCaringKnowledge Knowledge Base
# Backed by AOSS pet_care_index.
# Used by the agent tool retrieve_pet_care (KNOWLEDGE_BASE_2_ID).
# ─────────────────────────────────────────────────────────────

resource "aws_bedrockagent_knowledge_base" "pet_care" {
  name        = "PetCaringKnowledge"
  description = "Pet care advice knowledge base containing reference sources which should be the only authoritative references on pet caring information."
  role_arn    = var.kb_execution_role_arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = var.aoss_collection_arn
      vector_index_name = "pet_care_index"
      field_mapping {
        vector_field   = "vector"
        text_field     = "text"
        metadata_field = "metadata"
      }
    }
  }

  tags = {
    Project = var.project_name
    Phase   = "3-knowledge-bases"
  }
}

# ─────────────────────────────────────────────────────────────
# Web Crawler Data Source + ingestion
# No native Terraform resource for WEB type data sources.
# Created via local-exec calling Bedrock API.
#
# Destroy provisioner deletes the data source before the KB is
# destroyed — Bedrock rejects KB deletion while data sources exist.
# ─────────────────────────────────────────────────────────────

resource "null_resource" "webcrawler_datasource" {
  triggers = {
    knowledge_base_id = aws_bedrockagent_knowledge_base.pet_care.id
    region            = var.aws_region
    create_hash       = filesha256("${path.module}/../../scripts/manage_webcrawler_datasource.py")
  }

  provisioner "local-exec" {
    command = <<-EOT
      python3 ${path.module}/../../scripts/manage_webcrawler_datasource.py \
        --knowledge-base-id ${self.triggers.knowledge_base_id} \
        --region ${self.triggers.region}
    EOT
  }

  provisioner "local-exec" {
    when = destroy
    command = <<-EOT
      python3 ${path.module}/../../scripts/manage_webcrawler_datasource.py \
        --knowledge-base-id ${self.triggers.knowledge_base_id} \
        --region ${self.triggers.region} \
        --destroy
    EOT
    on_failure = continue
  }

  depends_on = [aws_bedrockagent_knowledge_base.pet_care]
}
