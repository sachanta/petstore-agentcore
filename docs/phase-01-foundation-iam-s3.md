# Phase 1: Foundation — IAM & S3

## Goal
Establish the security identity (IAM role) and storage (S3 buckets) that every subsequent phase depends on. Nothing AI-specific happens here — this is pure AWS plumbing. After this phase, `terraform destroy` should cleanly remove all resources.

---

## What We're Building

```
terraform/
├── main.tf
├── variables.tf
├── outputs.tf
└── modules/
    └── foundation/
        ├── main.tf
        ├── variables.tf
        └── outputs.tf

lambdas/                    (empty dirs, placeholder for Phase 5)
pet-store-products/         (already created)
```

### Resources

| Resource | Name | Purpose |
|---|---|---|
| `aws_iam_role` | `PetStoreSolutionAccessRole` | Assumed by Lambda, Bedrock, AgentCore, CodeBuild — the single service identity for this project |
| `aws_iam_role_policy` | inline policy | Grants all required service permissions (AOSS, Bedrock, Lambda, S3, ECR, CodeBuild, Logs) |
| `aws_s3_bucket` | `petstore-knowledge-data-<account_id>` | Stores the product catalog files that Bedrock will index into the knowledge base |
| `aws_s3_bucket_versioning` | on knowledge bucket | Best practice — allows rollback of document changes |
| `aws_s3_object` (×6) | one per `.txt` file | Uploads all `pet-store-products/` files into the S3 bucket under the `pet-store-products/` prefix |
| `aws_s3_bucket` | `petstore-codebuild-<account_id>` | Staging bucket used by CodeBuild in Phase 6 to store zipped source before building the Docker image |
| `aws_s3_bucket_lifecycle_configuration` | on codebuild bucket | Auto-delete objects older than 7 days — this bucket holds temporary build artifacts only |

---

## Terraform Structure

### `variables.tf`
```
variable "aws_region"       default = "us-east-1"
variable "aws_account_id"   # pulled from data source, not hardcoded
variable "project_name"     default = "petstore"
```

### `main.tf` (root)
- Configures AWS provider with region
- Calls `module "foundation"`
- Uses `data "aws_caller_identity"` to get account ID dynamically — no hardcoded account numbers

### `outputs.tf`
Exports for use in later phases:
```
solution_access_role_arn
knowledge_bucket_name
knowledge_bucket_arn
codebuild_bucket_name
```

---

## Step-by-Step Implementation

1. Create `terraform/` directory structure
2. Write `provider.tf` — AWS provider, Terraform version constraints, S3 backend (optional: local state for now)
3. Write `modules/foundation/main.tf` with all resources above
4. Write `modules/foundation/variables.tf` and `outputs.tf`
5. Wire the module from root `main.tf`
6. Run `terraform init`
7. Run `terraform plan` — review before applying
8. Run `terraform apply`
9. Verify in AWS console: IAM role exists, both S3 buckets exist, 6 `.txt` files visible under `pet-store-products/` prefix
10. Run `terraform destroy` — verify clean removal
11. Run `terraform apply` again to restore for Phase 2
12. `git push`

---

## Execution Log (Actual Run — 2026-05-05)

### Commands Executed
```bash
# Install Terraform (not present on EC2)
curl -fsSL https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip -o /tmp/terraform.zip
unzip -o /tmp/terraform.zip -d /tmp
sudo mv /tmp/terraform /usr/local/bin/
terraform version   # → Terraform v1.9.8

terraform init      # Downloaded hashicorp/aws v5.100.0
terraform plan      # 12 resources planned
terraform apply     # First attempt: partial success + IAM error
terraform plan      # 2 output changes (after IAM fix)
terraform apply     # Full success: 10 resources created
terraform destroy   # 10 resources destroyed
terraform apply     # 10 resources re-created (left up for Phase 2)
```

### Problem Encountered: IAM Role Creation Blocked

**Error:**
```
creating IAM Role (petstore-SolutionAccessRole): AccessDenied:
no permissions boundary allows the iam:CreateRole action
```

**Root cause:** The `HCL-Permissions-Boundary` policy attached to our EC2 role only allows `iam:CreateRole` for specific Bedrock-managed role name patterns (`DataZoneBedrockProject*`, `AmazonBedrockExecution*`, `BedrockStudio*`). Creating an arbitrary role named `petstore-SolutionAccessRole` is blocked.

**Fix:** Replaced `resource "aws_iam_role"` with `data "aws_iam_role"` to reference two pre-existing roles in the account:
- `HCL-User-Role-PD-BedrockAgentCoreRole` → trusted by Lambda, Bedrock, AgentCore
- `HCL-User-Role-Aiml-BedrockAgentCore-CodeBuild` → trusted by CodeBuild, AgentCore

**Impact on plan docs:** Phase 1 doc updated. Phase 6 and 7 docs (CodeBuild, AgentCore) now use these two specific role ARNs from outputs. The `Prerequisites` section is updated accordingly — there is no IAM role to create manually; the roles already exist.

### What S3 Resources Created Successfully on First Apply
Despite the IAM error, Terraform created all S3 resources before hitting the IAM error (resources are created in parallel):
- `petstore-knowledge-data-040504913362` with versioning enabled
- `petstore-codebuild-040504913362` with 7-day lifecycle expiry
- All 6 product `.txt` files under `pet-store-products/` prefix

### Final Outputs
```
codebuild_bucket_name    = "petstore-codebuild-040504913362"
codebuild_role_arn       = "arn:aws:iam::040504913362:role/HCL-User-Role-Aiml-BedrockAgentCore-CodeBuild"
knowledge_bucket_arn     = "arn:aws:s3:::petstore-knowledge-data-040504913362"
knowledge_bucket_name    = "petstore-knowledge-data-040504913362"
solution_access_role_arn = "arn:aws:iam::040504913362:role/HCL-User-Role-PD-BedrockAgentCoreRole"
```

### Destroy Verification
`terraform destroy` removed all 10 managed resources cleanly:
- 6 S3 objects (product files)
- 2 S3 buckets
- 1 S3 versioning config
- 1 S3 lifecycle config
The two IAM `data` sources were not touched (they are read-only references).

---

## IAM Role — Permission Design

The role needs to be trusted by multiple services:

```json
{
  "Principal": {
    "Service": [
      "lambda.amazonaws.com",
      "bedrock.amazonaws.com",
      "bedrock-agentcore.amazonaws.com",
      "codebuild.amazonaws.com"
    ]
  }
}
```

Permissions granted (broad for this challenge — in production these would be scoped):
- `aoss:*` — OpenSearch Serverless (Phase 2)
- `bedrock:*` and `bedrock-agent:*` — Knowledge bases, guardrails (Phases 3, 4)
- `bedrock-agentcore:*` — Runtime (Phase 7)
- `lambda:InvokeFunction` — Agent calling backend Lambdas (Phase 5)
- `s3:GetObject`, `s3:ListBucket` — Bedrock reading product files (Phase 3)
- `ecr:*` — CodeBuild pushing Docker image (Phase 6)
- `codebuild:*` — Running the build (Phase 6)
- `logs:*` — Lambda and CodeBuild writing logs

---

## Verify & Test

After `terraform apply`:
```bash
# Confirm role exists
aws iam get-role --role-name PetStoreSolutionAccessRole

# Confirm knowledge bucket has files
aws s3 ls s3://petstore-knowledge-data-<account_id>/pet-store-products/

# Confirm codebuild bucket exists
aws s3 ls s3://petstore-codebuild-<account_id>/
```

After `terraform destroy`:
```bash
# All three should return errors/empty — confirming clean teardown
aws iam get-role --role-name PetStoreSolutionAccessRole
aws s3 ls s3://petstore-knowledge-data-<account_id>/
aws s3 ls s3://petstore-codebuild-<account_id>/
```

---

## For Srikar's Understanding

### Homework

**1. IAM Trust Policy vs Permission Policy — what's the difference?**
The role has two separate policy documents. Look at what we wrote and answer: which one controls *who can use* the role, and which one controls *what the role can do*? Why does this role need to trust four different AWS services?

**2. Why does the S3 bucket name include the account ID?**
S3 bucket names are globally unique across all AWS accounts worldwide. Try to create a bucket called `petstore-data` and observe what happens. What strategy did we use to avoid naming collisions?

**3. Terraform state — where does it live after `terraform apply`?**
Look for a file called `terraform.tfstate` after applying. Open it and read it. What information does Terraform store there? What would happen if you deleted this file and ran `terraform destroy`?

**4. `terraform plan` vs `terraform apply` — why run plan first?**
Run `terraform plan` and read the output carefully. What does the `+` symbol mean? What would `-` mean? Why is reviewing the plan important before applying in a real production environment?

**5. The `data "aws_caller_identity"` block — why not hardcode the account ID?**
We used a data source to get the account ID dynamically. What is the risk of hardcoding `040504913362` directly in Terraform files that get pushed to git?
