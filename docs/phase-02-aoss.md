# Phase 2: OpenSearch Serverless (AOSS)

## Goal
Deploy the vector search backend that stores embeddings for both knowledge bases. OpenSearch Serverless (AOSS) is where the actual indexed content lives — the knowledge bases in Phase 3 are just a Bedrock-managed interface on top of it. After this phase, `terraform destroy` should cleanly remove the collection and all its policies.

---

## What We're Building

```
terraform/
└── modules/
    └── aoss/
        ├── main.tf
        ├── variables.tf
        ├── outputs.tf
        └── scripts/
            └── create_vector_indices.py   ← custom script, no native TF resource
```

### Resources

| Resource | Name | Purpose |
|---|---|---|
| `aws_opensearchserverless_security_policy` (encryption) | `petstore-enc-policy` | Mandates AWS-owned KMS encryption on the collection — required before collection can be created |
| `aws_opensearchserverless_security_policy` (network) | `petstore-net-policy` | Controls network access — set to public so Bedrock can reach it from managed service infrastructure |
| `aws_opensearchserverless_access_policy` (data) | `petstore-data-policy` | Controls which IAM principals can read/write documents and manage indices — grants access to `PetStoreSolutionAccessRole` |
| `aws_opensearchserverless_collection` | `clashofagents` | The VECTORSEARCH collection — the actual database that holds the embedded vectors |
| `null_resource` + `local-exec` | `create_vector_indices` | Runs `create_vector_indices.py` after the collection is ACTIVE to create the two index mappings |

### Vector Indices (created by script, not Terraform)

| Index Name | Used By |
|---|---|
| `product_info_index` | ProductInformation Knowledge Base (Phase 3) |
| `pet_care_index` | PetCaringKnowledge Knowledge Base (Phase 3) |

Each index has this mapping:
```json
{
  "settings": { "index.knn": true },
  "mappings": {
    "properties": {
      "vector": { "type": "knn_vector", "dimension": 1024, "method": { "name": "hnsw", "engine": "faiss" } },
      "text":   { "type": "text" },
      "metadata": { "type": "text" }
    }
  }
}
```

---

## Why AOSS Needs Three Separate Policies

This confuses everyone the first time. OpenSearch Serverless separates concerns into three independent policy types — all three are required:

```
Encryption Policy  →  "How is data encrypted at rest?"
Network Policy     →  "Who can reach the endpoint over the network?"
Access Policy      →  "Which IAM identities can perform which operations?"
```

A collection will not become ACTIVE unless an encryption policy is attached. Network and access policies can be attached after creation but are needed before any data operations.

---

## The AOSS Bootstrap Timing Problem

AOSS collections take 2-5 minutes to go from `CREATING` to `ACTIVE`. The vector indices cannot be created until the collection endpoint is available. This is why the CFN template had `time.sleep(120)` hardcoded in the Lambda.

In Terraform we handle this properly:
1. The `aws_opensearchserverless_collection` resource returns when the API call succeeds (collection is `CREATING`, not yet `ACTIVE`)
2. The `null_resource` for index creation uses a `depends_on` the collection resource
3. The `create_vector_indices.py` script polls the collection status via `batch_get_collection` until it sees `ACTIVE`, then creates the indices

This is cleaner than sleeping blindly for 2 minutes.

---

## `create_vector_indices.py` — What It Does

```
1. Accept collection_name and endpoint as arguments
2. Poll batch_get_collection until status == ACTIVE (max 10 min timeout)
3. Build AWS SigV4 auth (requests_aws4auth)
4. PUT /product_info_index with knn_vector mapping
5. PUT /pet_care_index with knn_vector mapping
6. Verify both indices exist
7. Exit 0 on success, non-zero on failure (Terraform will catch this)
```

On `terraform destroy`, a companion `destroy_vector_indices.py` (or delete provisioner) sends:
```
DELETE /product_info_index
DELETE /pet_care_index
```

---

## Outputs (passed to Phase 3)

```
aoss_collection_arn
aoss_collection_endpoint
aoss_collection_id
```

---

## Step-by-Step Implementation

1. Write `modules/aoss/main.tf` — three policies, collection, null_resource
2. Write `create_vector_indices.py` under `terraform/scripts/`
3. Add `pip install requests requests_aws4auth` to the script's setup comment
4. Wire `module "aoss"` from root `main.tf`, passing `solution_access_role_arn` from Phase 1 outputs
5. `terraform plan` — you should see 5 resources to create
6. `terraform apply` — collection creation alone takes 2-5 mins, be patient
7. Verify collection in AWS console: status should be `Active`, two indices visible
8. `terraform destroy` — verify collection deleted, policies deleted
9. `terraform apply` again to restore for Phase 3
10. `git push`

---

## Verify & Test

After `terraform apply`:
```bash
# Check collection status
aws opensearchserverless batch-get-collection --names clashofagents \
  --query 'collectionDetails[0].status'

# Check indices exist (need the collection endpoint from outputs)
# This is an HTTP GET to the OpenSearch endpoint — best done via console
# OpenSearch Dashboard → Dev Tools → GET /_cat/indices
```

After `terraform destroy`:
```bash
# Should return empty
aws opensearchserverless list-collections \
  --query 'collectionSummaries[?name==`clashofagents`]'
```

---

## Execution Log

### Apply (final successful run)
```
# terraform apply -auto-approve

module.aoss.aws_opensearchserverless_security_policy.encryption: Creating...
module.aoss.aws_opensearchserverless_security_policy.network: Creating...
module.aoss.aws_opensearchserverless_access_policy.data: Creating...
module.aoss.aws_opensearchserverless_collection.main: Creating...
module.aoss.time_sleep.aoss_policy_propagation: Creating...  [60s]
module.aoss.null_resource.vector_indices: Creating...
  product_info_index → Response 200: {"acknowledged":true,...}
  pet_care_index     → Response 200: {"acknowledged":true,...}

Apply complete! Resources: 16 added, 0 changed, 0 destroyed.

Outputs:
  aoss_collection_arn      = "arn:aws:aoss:us-east-1:040504913362:collection/5nvu2ztxn21jrclpdvdi"
  aoss_collection_endpoint = "https://5nvu2ztxn21jrclpdvdi.us-east-1.aoss.amazonaws.com"
  knowledge_bucket_name    = "petstore-knowledge-data-040504913362"
  solution_access_role_arn = "arn:aws:iam::040504913362:role/HCL-User-Role-PD-BedrockAgentCoreRole"
```

### Destroy
```
# terraform destroy -auto-approve

module.aoss.null_resource.vector_indices: Destroying...   (on_failure=continue — 403 OK, collection will be deleted anyway)
module.aoss.aws_opensearchserverless_collection.main: Destroying...  [~30s]
module.aoss.aws_opensearchserverless_security_policy.*: Destroying...
module.aoss.aws_opensearchserverless_access_policy.data: Destroying...

Destroy complete! Resources: 16 destroyed.
```

### Errors Encountered and Fixed

**Error 1: ModuleNotFoundError (boto3)**
The first apply failed because `boto3` / `requests` were not installed.
```bash
pip3 install boto3 requests requests-aws4auth
```

**Error 2: 403 on index creation**
Root cause: AOSS data access policy was applied, but the `null_resource` ran immediately before the policy propagated (~60 s delay).
Fix: Added `time_sleep.aoss_policy_propagation` (60 s) between policy creation and `null_resource`.
Also added the EC2 instance role (`HCL-User-Role-Aiml-EC2`) to the data access policy Principal list, because the local-exec script authenticates as that role.

**Error 3: 403 on index deletion (destroy)**
The destroy provisioner runs without a propagation wait and gets 403 — this is expected.
`on_failure = continue` allows destroy to proceed. Terraform then deletes the collection, which removes the indices implicitly.

---

## For Srikar's Understanding

### Homework

**1. What is a vector and why does dimension matter?**
The index mapping specifies `"dimension": 1024`. This matches the output size of Amazon Titan Embed Text v2. If you used a different embedding model with a different output size (e.g. 1536 dimensions), what would happen when Bedrock tried to write embeddings into this index?

**2. What is HNSW and why is it used for vector search?**
The index uses `"name": "hnsw"` as the algorithm. HNSW stands for Hierarchical Navigable Small World. Look it up and answer: why is approximate nearest-neighbor search (ANN) used instead of exact search for RAG use cases? What is the trade-off?

**3. Why three separate AOSS policy types instead of one?**
AWS designed encryption, network, and data access as three separate control planes. Think about who in an enterprise might own each one — security team, network team, application team. Why would separating these be useful in a real organisation?

**4. What is SigV4 and why does the script need it?**
The `create_vector_indices.py` script uses `requests_aws4auth` to sign HTTP requests. OpenSearch Serverless doesn't accept unsigned REST calls. What is AWS Signature Version 4? What does it prove to AWS about the caller?

**5. `null_resource` in Terraform — what is it and when should you use it?**
We used a `null_resource` with `local-exec` to run a Python script. Terraform's job is to manage resources, but `null_resource` doesn't manage any real resource. When is this the right tool, and what are the risks of overusing it? What happens to a `null_resource` on `terraform destroy`?
