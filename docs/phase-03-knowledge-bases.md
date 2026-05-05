# Phase 3: Bedrock Knowledge Bases

## Goal
Create two Bedrock Knowledge Bases backed by the AOSS collection from Phase 2, connect their data sources, and trigger ingestion so the vector indices are populated with real content. After this phase the agent has something to actually retrieve. `terraform destroy` must cleanly remove both knowledge bases, both data sources, and stop any in-progress ingestion jobs.

---

## What We're Building

```
terraform/
└── modules/
    └── knowledge_bases/
        ├── main.tf
        ├── variables.tf
        ├── outputs.tf
        └── scripts/
            ├── start_ingestion.py       ← triggers S3 KB sync
            └── delete_web_datasource.py ← teardown helper (orphan fix)
```

### Resources

| Resource | Name | Purpose |
|---|---|---|
| `aws_bedrockagent_knowledge_base` | `ProductInformation` | KB backed by AOSS `product_info_index` — queries product catalog |
| `aws_bedrockagent_data_source` | `S3DataSource` | Reads `.txt` files from `pet-store-products/` prefix in the knowledge S3 bucket |
| `null_resource` | `trigger_s3_ingestion` | Runs `start_ingestion.py` after the S3 data source is created |
| `aws_bedrockagent_knowledge_base` | `PetCaringKnowledge` | KB backed by AOSS `pet_care_index` — queries pet care advice |
| `null_resource` | `create_webcrawler_datasource` | Calls Bedrock API to create web crawler data source and start ingestion (no native TF resource) |
| `null_resource` | `destroy_webcrawler_datasource` | Destroy-time provisioner that deletes the web crawler data source before the KB is destroyed |

---

## Why Two Separate Knowledge Bases?

The agent uses them for different purposes, enforced by how the tools are named in the agent code:

- `retrieve_product_info` → queries `ProductInformation` KB → answers "do we sell this?", "what's the price?", "what are the specs?"
- `retrieve_pet_care` → queries `PetCaringKnowledge` KB → answers pet care questions (only for subscribed users)

Keeping them separate allows the guardrail to apply different topic restrictions without mixing product data and care advice in the same index.

---

## Knowledge Base Configuration

Both KBs share the same embedding model and storage type, but point to different AOSS indices:

```
Embedding Model:  amazon.titan-embed-text-v2:0   (produces 1024-dim vectors)
Storage Type:     OPENSEARCH_SERVERLESS
Vector Field:     "vector"
Text Field:       "text"
Metadata Field:   "metadata"
```

| KB | AOSS Index | Data Source Type |
|---|---|---|
| ProductInformation | `product_info_index` | S3 — `pet-store-products/` prefix |
| PetCaringKnowledge | `pet_care_index` | Web Crawler — 4 Wikipedia URLs |

---

## The S3 Ingestion Sync

After the `S3DataSource` resource is created, Bedrock has the configuration but has not read any documents. The sync must be triggered explicitly.

`start_ingestion.py` does:
```
1. Accept knowledge_base_id and data_source_id as arguments
2. Call bedrock-agent start-ingestion-job
3. Poll get-ingestion-job until status is COMPLETE or FAILED
4. Print final statistics: documents indexed, failed, deleted
5. Exit non-zero on FAILED so Terraform surfaces the error
```

The ingestion process for 6 small `.txt` files typically completes in 2-4 minutes.

---

## The Web Crawler Data Source — The Orphan Problem

Terraform has no native `aws_bedrockagent_data_source` type for web crawler sources (only S3). The web crawler data source is created via a `null_resource` + `local-exec` calling the Bedrock API.

**Seed URLs:**
```
https://en.wikipedia.org/wiki/Cat_food
https://en.wikipedia.org/wiki/Cat_play_and_toys
https://en.wikipedia.org/wiki/Dog_food
https://en.wikipedia.org/wiki/Dog_grooming
```

**The destroy problem:** `null_resource` has no destroy logic by default. If we don't handle this, `terraform destroy` will try to delete the `PetCaringKnowledge` KB but fail because the data source still exists (Bedrock prevents deleting a KB with active data sources).

**The fix:** Add a `destroy` provisioner to the `null_resource` that calls `delete_web_datasource.py` before the KB is destroyed. This script:
```
1. Lists data sources for the KB
2. Finds the WebCrawlerDataSource by name
3. Calls bedrock-agent delete-data-source
4. Waits for deletion to confirm
```

This is the specific gap that the original CFN template had — the `WebCrawlerCreateLambda` had no Delete handler. Terraform lets us fix it properly.

---

## Ingestion — What Bedrock Does Under the Hood

Understanding this is important for debugging:

```
For S3 data source:
  1. Bedrock reads each .txt file from S3
  2. Splits content into chunks (default: ~300 tokens with 20% overlap)
  3. Sends each chunk to Titan Embed Text v2 → 1024-dim vector
  4. Writes (vector, text, metadata) into AOSS product_info_index

For web crawler:
  1. Bedrock fetches each seed URL
  2. Follows links matching the inclusion filter (.*)
  3. Extracts text from HTML
  4. Same chunking + embedding + write pipeline
```

The metadata field stored with each chunk includes the source S3 key or URL — this is what appears as `Document ID` in the agent's retrieval results.

---

## Outputs (passed to Phase 7)

```
product_info_kb_id
pet_care_kb_id
```

---

## Step-by-Step Implementation

1. Write `modules/knowledge_bases/main.tf`
2. Write `start_ingestion.py` and `delete_web_datasource.py` under `terraform/scripts/`
3. Wire `module "knowledge_bases"` from root, passing AOSS outputs from Phase 2
4. `terraform plan` — 6 resources to create (2 KBs, 1 S3 data source, 3 null_resources)
5. `terraform apply` — expect 8-12 minutes total (ingestion jobs run during apply)
6. Verify in AWS Bedrock console: both KBs show `Ready`, data sources show `Available`
7. Test retrieval in console: "Doggy Delights price" should return results from the S3 KB
8. `terraform destroy` — web crawler data source must be deleted before KB, verify Terraform handles this
9. `terraform apply` again to restore
10. `git push`

---

## Verify & Test

After `terraform apply`:
```bash
# Check KB status
aws bedrock-agent get-knowledge-base \
  --knowledge-base-id <ProductInfo1stKnowledgeBaseId> \
  --query 'knowledgeBase.status'

# Check ingestion job result
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id <ProductInfo1stKnowledgeBaseId> \
  --data-source-id <S3DataSourceId> \
  --query 'ingestionJobSummaries[0].{status:status,indexed:statistics.numberOfDocumentsIndexed}'
```

After `terraform destroy`:
```bash
# Both should return ResourceNotFoundException
aws bedrock-agent get-knowledge-base --knowledge-base-id <id>
```

---

## For Srikar's Understanding

### Homework

**1. What is RAG and why does chunking matter?**
RAG stands for Retrieval-Augmented Generation. The product catalog files are split into chunks before embedding. Why can't the entire file be embedded as one vector? What happens to retrieval quality if chunks are too large? Too small?

**2. Embedding models — what does Titan Embed Text v2 actually produce?**
When Bedrock embeds the text "Doggy Delights is a premium grain-free dry dog food", it produces a list of 1024 floating-point numbers. What do these numbers represent? Why does similarity search on vectors work for finding semantically related content?

**3. The relevance score threshold in the agent code**
Look at `retrieve_product_info.py` line 19: `score: float = 0.25`. Results below this score are filtered out. What does a score of 0.25 mean in cosine similarity terms? What would happen if you set it to 0.9? What about 0.01?

**4. Why is the web crawler data source not a native Terraform resource?**
AWS adds new resource types to the Terraform AWS provider over time. The S3 data source exists but the web crawler type does not yet. How would you check what version of the AWS provider added a resource? What is the risk of using `null_resource` for something the provider might support natively in the future?

**5. Ingestion job failure modes**
The `start_ingestion.py` script checks for `FAILED` status. What could cause an ingestion job to fail? Think about: IAM permissions, S3 bucket policy, AOSS access policy, document format. How would you diagnose a failed ingestion job?
