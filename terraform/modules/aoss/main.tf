# ─────────────────────────────────────────────────────────────
# AOSS Security Policy — Encryption
# Required before the collection can be created.
# Uses AWS-owned KMS key (no cost, sufficient for this project).
# ─────────────────────────────────────────────────────────────

resource "aws_opensearchserverless_security_policy" "encryption" {
  name        = "${var.collection_name}-enc-policy"
  type        = "encryption"
  description = "AWS-owned KMS encryption for ${var.collection_name} collection"

  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource     = ["collection/${var.collection_name}"]
      }
    ]
    AWSOwnedKey = true
  })
}

# ─────────────────────────────────────────────────────────────
# AOSS Security Policy — Network
# PUBLIC allows Bedrock managed service to reach the collection
# endpoint without needing a VPC endpoint.
# ─────────────────────────────────────────────────────────────

resource "aws_opensearchserverless_security_policy" "network" {
  name        = "${var.collection_name}-net-policy"
  type        = "network"
  description = "Public network access for ${var.collection_name} collection and dashboard"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${var.collection_name}"]
        },
        {
          ResourceType = "dashboard"
          Resource     = ["collection/${var.collection_name}"]
        }
      ]
      AllowFromPublic = true
    }
  ])
}

# ─────────────────────────────────────────────────────────────
# AOSS Access Policy — Data
# Grants the SolutionAccessRole full index and collection access.
# This is separate from network/encryption — controls which IAM
# principals can read/write documents and manage indices.
# ─────────────────────────────────────────────────────────────

resource "aws_opensearchserverless_access_policy" "data" {
  name        = "${var.collection_name}-data-policy"
  type        = "data"
  description = "Data access for SolutionAccessRole and EC2 role on ${var.collection_name}"

  policy = jsonencode([
    {
      Description = "Full access for SolutionAccessRole and EC2 provisioner role"
      # Both the service role (Bedrock/Lambda) AND the EC2 instance role need access:
      # - solution_access_role_arn: used by Bedrock at runtime
      # - EC2 role: used by the Terraform local-exec script that creates indices
      Principal   = [
        var.solution_access_role_arn,
        "arn:aws:iam::${var.aws_account_id}:role/HCL-User-Role-Aiml-EC2"
      ]
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${var.collection_name}"]
          Permission   = ["aoss:*"]
        },
        {
          ResourceType = "index"
          Resource     = ["index/${var.collection_name}/*"]
          Permission = [
            "aoss:CreateIndex",
            "aoss:UpdateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument"
          ]
        }
      ]
    }
  ])
}

# ─────────────────────────────────────────────────────────────
# AOSS Collection
# VECTORSEARCH type: optimised for knn_vector indices.
# StandbyReplicas DISABLED: single-AZ, lower cost for dev/challenge.
# ─────────────────────────────────────────────────────────────

resource "aws_opensearchserverless_collection" "main" {
  name             = var.collection_name
  type             = "VECTORSEARCH"
  standby_replicas = "DISABLED"
  description      = "Vector search collection for pet store knowledge bases"

  # Encryption policy must exist before collection creation
  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
    aws_opensearchserverless_access_policy.data,
  ]

  tags = {
    Project = var.project_name
    Phase   = "2-aoss"
  }
}

# ─────────────────────────────────────────────────────────────
# Propagation wait
# AOSS data access policies take ~30-60 s to become effective
# after creation/update.  Without this sleep the local-exec script
# hits 403 even though the policy was just applied.
# ─────────────────────────────────────────────────────────────

resource "time_sleep" "aoss_policy_propagation" {
  create_duration = "60s"

  depends_on = [
    aws_opensearchserverless_access_policy.data,
    aws_opensearchserverless_collection.main,
  ]
}

# ─────────────────────────────────────────────────────────────
# Vector Indices
# No native Terraform resource for AOSS indices exists.
# A Python script creates them via the OpenSearch REST API once
# the collection is ACTIVE. Destroy provisioner cleans them up.
#
# triggers: any change to the script re-runs index creation.
# ─────────────────────────────────────────────────────────────

resource "null_resource" "vector_indices" {
  # Store everything destroy needs in triggers — resource attrs unavailable during destroy
  triggers = {
    collection_id   = aws_opensearchserverless_collection.main.id
    collection_name = var.collection_name
    region          = var.aws_region
    endpoint        = aws_opensearchserverless_collection.main.collection_endpoint
    script_hash     = filesha256("${path.module}/../../scripts/create_vector_indices.py")
  }

  provisioner "local-exec" {
    command = <<-EOT
      python3 ${path.module}/../../scripts/create_vector_indices.py \
        --collection-name ${self.triggers.collection_name} \
        --region ${self.triggers.region} \
        --endpoint ${self.triggers.endpoint}
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      python3 ${path.module}/../../scripts/create_vector_indices.py \
        --collection-name ${self.triggers.collection_name} \
        --region ${self.triggers.region} \
        --endpoint ${self.triggers.endpoint} \
        --destroy
    EOT

    on_failure = continue  # Don't block destroy if indices already gone
  }

  depends_on = [
    aws_opensearchserverless_collection.main,
    aws_opensearchserverless_access_policy.data,
    time_sleep.aoss_policy_propagation,
  ]
}
