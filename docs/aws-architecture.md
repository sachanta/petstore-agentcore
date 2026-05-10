# AWS Architecture — Virtual Pet Store AgentCore

This document explains every AWS resource created by this project, why it exists, what role it plays, and how the pieces connect at runtime. Use it as a reference to understand what is running in your account and why.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AWS Account                                        │
│                                                                                 │
│  Caller (tests / UI)                                                            │
│       │                                                                         │
│       │  invoke_agent_runtime()                                                 │
│       ▼                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │              Amazon Bedrock AgentCore Runtime                           │   │
│  │              LangGraphAgentCoreRuntime                                  │   │
│  │              (ARM64 Docker container — ECR image)                       │   │
│  │                                                                         │   │
│  │   ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │   │  agentcore_entrypoint.py                                        │   │   │
│  │   │                                                                 │   │   │
│  │   │  1. apply_guardrail() ──────────────────────► Bedrock Guardrail │   │   │
│  │   │     (blocks bad input)                         PetStoreGuardrail│   │   │
│  │   │                                                                 │   │   │
│  │   │  2. pet_store_agent.process_request()                           │   │   │
│  │   │     LangGraph ReAct loop                                        │   │   │
│  │   │     Nova Pro (us.amazon.nova-pro-v1:0)                          │   │   │
│  │   │        │                                                        │   │   │
│  │   │        ├──► retrieve_product_info() ──► KB: ProductInformation  │   │   │
│  │   │        │                                      │                 │   │   │
│  │   │        ├──► retrieve_pet_care() ──────► KB: PetCaringKnowledge  │   │   │
│  │   │        │                                      │                 │   │   │
│  │   │        │                          Both KBs ───┼──► AOSS         │   │   │
│  │   │        │                          (vector     │    clashofagents│   │   │
│  │   │        │                          search)     │    collection   │   │   │
│  │   │        │                                      │                 │   │   │
│  │   │        ├──► get_inventory() ─────────────────────► Lambda:      │   │   │
│  │   │        │                                           Inventory    │   │   │
│  │   │        ├──► get_user_by_id() ──────────────────► Lambda:        │   │   │
│  │   │        └──► get_user_by_email() ─────────────► UserManagement   │   │   │
│  │   │                                                                 │   │   │
│  │   │  3. _apply_business_rules()                                     │   │   │
│  │   │     (deterministic: discounts, shipping, replenishment)         │   │   │
│  │   └─────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                         │   │
│  │   Logs ──────────────────────────────────────────────────────────────► │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                 │                                                               │
│                 ▼                                                               │
│  CloudWatch Logs: /aws/bedrock-agentcore/petstore-agent                        │
│                                                                                 │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  Build Pipeline (one-time, runs on terraform apply)                      │  │
│  │                                                                          │  │
│  │  Local machine                                                           │  │
│  │    ── zip source ──► S3: petstore-codebuild-{ACCOUNT}                   │  │
│  │                            │                                            │  │
│  │                            ▼                                            │  │
│  │                      CodeBuild: petstore-agent-builder (ARM64)          │  │
│  │                            │                                            │  │
│  │                            ▼                                            │  │
│  │                      ECR: petstore-agent-repo ──► AgentCore Runtime     │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  Knowledge Base Ingestion Pipeline (one-time, runs on terraform apply)   │  │
│  │                                                                          │  │
│  │  S3: petstore-knowledge-data-{ACCOUNT}                                   │  │
│  │    pet-store-products/*.txt ──► KB Data Source ──► ProductInformation KB │  │
│  │                                 (S3 sync)              │                 │  │
│  │                                                         │                │  │
│  │  Web Crawler ────────────────────────────────► PetCaringKnowledge KB    │  │
│  │                                                         │                │  │
│  │                                              Both KBs ──┼──► AOSS        │  │
│  │                                              vectorize       collection  │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Resource Inventory by Phase

The infrastructure is built in 7 sequential phases via Terraform. Each phase depends on the outputs of previous phases.

---

### Phase 1 — Foundation: IAM & Storage

#### IAM Role: `AmazonBedrockExecutionRoleForKnowledgeBase_petstore` (created)

**Why it exists:** Bedrock Knowledge Bases run as a managed service inside AWS — they are not your code. They need a dedicated IAM role they can assume to access your data sources (S3) and your vector store (AOSS). Without this role, the Knowledge Base cannot read product files or write vector embeddings.

**Trust relationship:** `bedrock.amazonaws.com` can assume this role, but only for Knowledge Base operations in your account and region (condition on the trust policy prevents cross-account abuse).

**Permissions granted:**
| Policy | Permission | On |
|--------|------------|-----|
| AOSS-APIAccess | `aoss:APIAccessAll` | All AOSS resources |
| S3-KnowledgeBucket | `s3:GetObject`, `s3:ListBucket` | Knowledge data bucket |
| Bedrock-EmbeddingModel | `bedrock:InvokeModel` | Amazon Titan Embedding v2 |

The embedding model permission is required because the KB calls Titan to convert each chunk of text into a vector before storing it in AOSS.

---

#### IAM Roles: Pre-existing (referenced, not created)

**`HCL-User-Role-PD-BedrockAgentCoreRole`** — The main execution role used by the AgentCore Runtime container, the Lambda functions, and any direct Bedrock API calls made at runtime (guardrail, retrieve). Think of this as the "runtime identity" of the application.

**`HCL-User-Role-Aiml-BedrockAgentCore-CodeBuild`** — The role that CodeBuild assumes when building the Docker image. It needs access to S3 (to download the source zip) and ECR (to push the built image). This role is managed at the account level and pre-exists this project.

---

#### S3 Bucket: `petstore-knowledge-data-{ACCOUNT_ID}`

**Why it exists:** The Bedrock Knowledge Base (ProductInformation) needs a source of truth for product data. The KB reads `.txt` files from this bucket, chunks them, vectorizes them, and stores the vectors in AOSS. Every `terraform apply` syncs the local `pet-store-products/` directory into this bucket under the `pet-store-products/` prefix.

**Key settings:**
- Versioning enabled — preserves previous versions of product files in case of accidental overwrites
- Force destroy — allows `terraform destroy` to delete the bucket even when it contains files

---

#### S3 Bucket: `petstore-codebuild-{ACCOUNT_ID}`

**Why it exists:** CodeBuild needs a place to download source code from. Terraform zips the repository and uploads it here before triggering a build. CodeBuild then downloads the zip, extracts it, and builds the Docker image.

**Key settings:**
- 7-day object lifecycle expiry — old source zips are automatically deleted (cost optimization)
- Force destroy — allows cleanup on `terraform destroy`

---

### Phase 2 — AOSS: Vector Search

#### OpenSearch Serverless Collection: `clashofagents`

**Why it exists:** Bedrock Knowledge Bases use vector search to find semantically relevant chunks of text for a given query. AOSS provides the managed, serverless vector database that stores these embeddings. Both Knowledge Bases (product catalog + pet care) share this single collection, each using a separate index.

**Type:** `VECTORSEARCH` — optimized for k-NN (k-nearest-neighbor) similarity search on embedding vectors.

**Standby replicas:** DISABLED — reduces cost. In production you would enable replicas for high availability.

---

#### AOSS Security Policies (3 policies)

AOSS has an unusual security model: access is denied by default and must be explicitly granted via three separate policy types, all of which must be in place before the collection can be used.

| Policy | Type | What it does |
|--------|------|-------------|
| `{collection}-enc-policy` | Encryption | Encrypts data at rest using an AWS-managed KMS key |
| `{collection}-net-policy` | Network | Makes the collection endpoint publicly reachable (required for Bedrock managed service to call it without a VPC endpoint) |
| `{collection}-data-policy` | Data Access | Grants specific IAM principals permission to read/write documents and manage indices |

**Data access policy principals:**
- `solution_access_role_arn` — the runtime role (allows agent to do KB retrieval)
- `HCL-User-Role-Aiml-EC2` — the Terraform provisioner's identity (allows scripts to create vector indices)
- `kb_execution_role_arn` — the Knowledge Base execution role (allows KB to write vectors)

**Policy propagation delay:** After creating data policies, Terraform waits 60 seconds (`time_sleep`) before proceeding. AOSS policies take 30–60 seconds to propagate globally. Without this wait, the index creation script would get 403 errors.

---

#### Vector Indices (created by script)

Two indices are created inside the `clashofagents` collection by `scripts/create_vector_indices.py`:

| Index | Used by | Field layout |
|-------|---------|-------------|
| `product_info_index` | ProductInformation KB | `vector` (embedding), `text` (chunk), `metadata` |
| `pet_care_index` | PetCaringKnowledge KB | `vector` (embedding), `text` (chunk), `metadata` |

These indices are not a native Terraform resource type — they are created via the OpenSearch REST API inside a `local-exec` provisioner.

---

### Phase 3 — Knowledge Bases

Knowledge Bases are Bedrock's managed RAG (Retrieval-Augmented Generation) system. They connect a data source to a vector store and expose a `retrieve()` API that the agent calls at query time.

#### Knowledge Base: `ProductInformation`

**Why it exists:** When a customer asks about a product, the agent needs accurate, up-to-date product details — price, description, features. This data lives in the S3 bucket as `.txt` files. The KB vectorizes those files so the agent can do semantic search ("self-cleaning litter box" → finds CatAutoClean CA003 even if the user didn't say the exact product name).

**Data source:** S3 — reads from `pet-store-products/` prefix in the knowledge bucket. The data source runs an ingestion job (triggered by `scripts/start_ingestion.py`) that chunks the files, calls Titan Embedding to vectorize each chunk, and stores vectors in `product_info_index`.

**Embedding model:** `amazon.titan-embed-text-v2:0` — converts text to 1536-dimensional vectors.

**Agent access:** Via environment variable `KNOWLEDGE_BASE_1_ID`. The agent calls `bedrock-agent-runtime.retrieve()` with this ID.

---

#### Knowledge Base: `PetCaringKnowledge`

**Why it exists:** Subscribed customers get personalised pet care advice alongside their order. This KB contains authoritative pet care articles from trusted web sources. The agent queries it when a subscribed customer asks a care-related question.

**Data source:** Web Crawler — crawls specified URLs and ingests the content. Created via `scripts/manage_webcrawler_datasource.py` because Terraform does not have a native resource for web crawler data sources.

**Agent access:** Via environment variable `KNOWLEDGE_BASE_2_ID`. Same `retrieve()` call, different KB ID.

---

### Phase 4 — Guardrail

#### Bedrock Guardrail: `PetStoreGuardrail`

**Why it exists:** The agent should only handle requests related to dogs and cats. Without a guardrail, users could ask about birds, fish, or reptiles (outside the store's scope), send abusive messages, or try prompt injection attacks. The guardrail is a managed filter that sits at the application boundary.

**Where it is applied:** In `agentcore_entrypoint.py`, before the agent processes any input. The entrypoint calls `bedrock-runtime.apply_guardrail()` on the raw user prompt. If the guardrail intervenes, a `Reject` response is returned immediately without the agent ever running.

> **Key architecture decision:** The guardrail is applied at the entrypoint level, not inside the LangGraph agent. This is deliberate. Applying it to the LangChain model directly would cause the guardrail to scan every intermediate ReAct reasoning step, resulting in false positives on legitimate tool outputs.

**Content filters (input only, HIGH sensitivity):**
- HATE, INSULTS, SEXUAL, VIOLENCE, MISCONDUCT — blocks toxic inputs
- PROMPT_ATTACK — blocks attempts to override the system prompt or extract confidential instructions

**Topic policy — DENY:**
- Topic: "Beyond-specialization-advice"
- Blocks queries about birds, fish, and reptiles (outside the store's specialization)
- Example blocked inputs: "How do I care for my parrot?", "What temperature for my fish tank?"

**Guardrail Version:** A published, immutable snapshot of the guardrail DRAFT. The runtime references this version number rather than DRAFT, so you can safely modify the guardrail rules without immediately affecting the live system.

---

### Phase 5 — Lambda Backends

The Lambda functions simulate backend microservices (CRM, inventory system). In a real deployment these would be real databases; here they are in-memory dictionaries.

#### Lambda: `PetStoreInventoryManagementFunction`

**Why it exists:** The agent needs to know current stock levels to:
1. Determine if a product is available to order
2. Calculate whether ordering it will trigger a replenishment flag (post-order stock ≤ reorder level)

**What it does:** Given a `product_code`, returns:
- Current quantity in stock
- Reorder level threshold
- Status: `in_stock` | `low_stock` | `out_of_stock`

The database contains 30 hardcoded products. `low_stock` means stock is at or below the reorder level but not zero — the agent still accepts the order but sets `replenishInventory: true` in the response.

**Called from:** `agentcore_entrypoint.py → _fetch_inventory()` (for business rules post-processing) and via the `get_inventory` LangGraph tool (for agent reasoning).

**Request format:**
```json
{
  "function": "getInventory",
  "parameters": [{ "name": "product_code", "value": "DD006" }]
}
```

---

#### Lambda: `PetStoreUserManagementFunction`

**Why it exists:** Subscribed users get additional benefits — pet care advice and (in a real system) loyalty pricing. The agent needs to verify whether a caller is a current subscriber.

**What it does:** Looks up a user by ID or email and returns subscription status, subscription end date, and transaction history.

**Three hardcoded users:**
| User | Email | Subscription |
|------|-------|-------------|
| usr_001 | john.doe@virtualpetstore.com | Active until 2027-01-01 |
| usr_002 | jane.smith@virtualpetstore.com | Expired 2025-01-01 |
| usr_003 | bob.wilson@virtualpetstore.com | Active until 2027-06-01 |

A lookup for any other ID or unknown email returns a `Guest` type — not an error.

**Called from:** The `get_user_by_id` and `get_user_by_email` LangGraph tools.

---

### Phase 6 — Agent Image

#### ECR Repository: `petstore-agent-repo`

**Why it exists:** AgentCore Runtime runs a Docker container. The image must be stored somewhere AWS can pull it from. ECR is the native AWS container registry — no external credentials needed, and IAM controls access.

**Lifecycle policy:** Keeps only the 5 most recent images and expires older ones. Without this, every `terraform apply` (which triggers a new build) would accumulate images indefinitely.

**Scan on push:** Enabled — ECR scans each pushed image for known CVEs automatically.

---

#### CodeBuild Project: `petstore-agent-builder`

**Why it exists:** The agent runs on ARM64 (Graviton) — the same architecture used by AgentCore Runtime containers. You cannot build an ARM64 Docker image on a standard x86 developer machine without emulation (which is very slow). CodeBuild runs natively on ARM64 (`BUILD_GENERAL1_SMALL` with `ARM_CONTAINER`), producing a correctly-targeted image.

**Build flow triggered by Terraform:**
1. `scripts/zip_source.py` — creates `petstore-source.zip` from the repository (excluding `.git`, terraform state)
2. Zip uploaded to `petstore-codebuild-{ACCOUNT}` S3 bucket
3. CodeBuild project starts
4. Container: `aws/codebuild/amazonlinux2-aarch64-standard:3.0` (ARM64)
5. `docker build --platform linux/arm64` builds the image
6. Image tagged and pushed to ECR
7. Script polls until the build completes, then AgentCore Runtime deployment proceeds

**Privileged mode:** Required because CodeBuild needs to run Docker inside the build container (Docker-in-Docker).

---

### Phase 7 — Agent Runtime

#### CloudWatch Log Group: `/aws/bedrock-agentcore/petstore-agent`

**Why it exists:** AgentCore Runtime is a managed service — you don't have SSH access to the container. CloudWatch Logs is how you observe what the agent is doing, debug failures, and review the full ReAct reasoning chain. The `/aws/bedrock-agentcore/` path prefix is picked up automatically by the CloudWatch GenAI Observability dashboard.

**Retention:** 7 days — enough for debugging; automatically expires to control cost.

---

#### AgentCore Runtime: `LangGraphAgentCoreRuntime`

**Why it exists:** This is the core managed service. AgentCore Runtime handles:
- Container lifecycle management (start, scale, stop)
- Network endpoint (the `invoke_agent_runtime()` API target)
- IAM authentication of callers
- Container environment variable injection

**Why there is no native Terraform resource:** At the time of writing, `aws_bedrockagentcore_agent_runtime` does not exist in the AWS provider. The runtime is created via `scripts/deploy_runtime.py` which calls the `bedrock-agentcore-control` API directly using boto3 inside a Terraform `local-exec` provisioner.

**What it receives at creation:**
- ECR image URI (from Phase 6)
- Execution role ARN (solution access role)
- CloudWatch log group name
- All environment variables (KB IDs, Lambda names, guardrail ID/version)

**Environment variables passed into the container:**

| Variable | Value | Used by |
|----------|-------|---------|
| `AWS_DEFAULT_REGION` | `us-east-1` | All boto3 clients |
| `KNOWLEDGE_BASE_1_ID` | ProductInformation KB ID | `retrieve_product_info.py` |
| `KNOWLEDGE_BASE_2_ID` | PetCaringKnowledge KB ID | `retrieve_pet_care.py` |
| `SYSTEM_FUNCTION_1_NAME` | `PetStoreInventoryManagementFunction` | `inventory_management.py` |
| `SYSTEM_FUNCTION_2_NAME` | `PetStoreUserManagementFunction` | `user_management.py` |
| `GUARDRAIL_ID` | PetStoreGuardrail ID | `agentcore_entrypoint.py` |
| `GUARDRAIL_VERSION` | `1` | `agentcore_entrypoint.py` |

---

## Runtime Data Flow

This shows what happens on every agent invocation — step by step, with the AWS service involved at each step.

```
Caller
  │
  │ bedrock-agentcore.invoke_agent_runtime(agentRuntimeArn, payload)
  │
  ▼
AgentCore Runtime (container)
  │
  │ agentcore_entrypoint.handler(payload)
  │
  ├─1─► bedrock-runtime.apply_guardrail(guardrailId, userPrompt)
  │         ► BLOCKED?  → return {"status": "Reject", "message": "..."}
  │         ► OK?       → continue
  │
  ├─2─► pet_store_agent.process_request(prompt)
  │       │
  │       │  LangGraph ReAct loop (up to N steps)
  │       │  LLM: us.amazon.nova-pro-v1:0
  │       │
  │       ├── TOOL: get_user_by_id / get_user_by_email
  │       │     └─► lambda.invoke(PetStoreUserManagementFunction)
  │       │           └─► Returns: {subscription_status, name, email, ...}
  │       │
  │       ├── TOOL: retrieve_product_info
  │       │     └─► bedrock-agent-runtime.retrieve(KNOWLEDGE_BASE_1_ID, query)
  │       │           └─► AOSS product_info_index (k-NN search)
  │       │                 └─► Returns: matching product chunks
  │       │
  │       ├── TOOL: retrieve_pet_care  (subscribed users only)
  │       │     └─► bedrock-agent-runtime.retrieve(KNOWLEDGE_BASE_2_ID, query)
  │       │           └─► AOSS pet_care_index (k-NN search)
  │       │                 └─► Returns: matching care article chunks
  │       │
  │       └── TOOL: get_inventory
  │             └─► lambda.invoke(PetStoreInventoryManagementFunction)
  │                   └─► Returns: {quantity, reorder_level, status}
  │
  │       └─► Agent generates JSON response (status, items, message, petAdvice)
  │
  ├─3─► _apply_business_rules(response)
  │       ► bundleDiscount:      10% on 2nd+ unit of same product
  │       ► additionalDiscount:  15% when subtotal > $300
  │       ► shippingCost:        free ≥$75; $19.95 ≥3 units; $14.95 otherwise
  │       ► total:               subtotal × (1 − additionalDiscount) + shippingCost
  │       ► replenishInventory:  live Lambda call per product, checks post-order stock
  │
  └─► Return final JSON to caller
```

---

## IAM Summary

| Principal | Assumed by | Key permissions |
|-----------|-----------|----------------|
| `HCL-User-Role-PD-BedrockAgentCoreRole` | AgentCore Runtime, Lambda functions | `bedrock:*`, `lambda:InvokeFunction`, `bedrock-agent-runtime:Retrieve`, `aoss:*`, `s3:*` (account boundary controlled) |
| `AmazonBedrockExecutionRoleForKnowledgeBase_petstore` | Bedrock Knowledge Base service | `aoss:APIAccessAll`, `s3:GetObject/ListBucket` on knowledge bucket, `bedrock:InvokeModel` on Titan embedding |
| `HCL-User-Role-Aiml-BedrockAgentCore-CodeBuild` | CodeBuild | ECR push, S3 get/put on codebuild bucket |

---

## Cost Drivers

Understanding which resources generate ongoing cost:

| Resource | Cost model | Notes |
|----------|-----------|-------|
| AOSS Collection | Hourly (OCU) | Most expensive resource; runs continuously even when idle |
| AgentCore Runtime | Per-invocation + compute time | No cost when not invoked |
| Lambda | Per-invocation | Negligible at test volumes |
| Knowledge Bases | Per query + ingestion | Low at test volumes |
| Bedrock (Nova Pro) | Per token (input + output) | Moderate; each ReAct loop generates multiple model calls |
| Bedrock Guardrail | Per text unit scanned | Very low |
| ECR | Per GB stored | Very low |
| CodeBuild | Per build-minute | One-time cost per deploy |
| S3 | Per GB + requests | Negligible |
| CloudWatch Logs | Per GB ingested | Low at test volumes |

**AOSS is the dominant cost.** If you are not actively using the project, run `terraform destroy` to tear down the collection.

---

## Deployment Topology

```
terraform apply
      │
      ├── Phase 1: IAM role + S3 buckets
      ├── Phase 2: AOSS collection + policies + wait(60s) + vector indices
      ├── Phase 3: Knowledge Bases + data sources + ingestion jobs
      ├── Phase 4: Guardrail + guardrail version
      ├── Phase 5: Lambda functions (inventory + user management)
      ├── Phase 6: ECR repo + zip source + upload to S3 + CodeBuild build
      └── Phase 7: CloudWatch log group + AgentCore Runtime deployment
                        (reads runtime_id/arn into terraform/tmp/runtime_outputs.json)

terraform output agent_runtime_arn
      └──► arn:aws:bedrock-agentcore:us-east-1:{ACCOUNT}:runtime/LangGraphAgentCoreRuntime-{ID}
```

All modules are wired together in `terraform/main.tf`, passing outputs from one module as inputs to the next.
