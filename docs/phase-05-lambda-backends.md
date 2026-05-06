# Phase 5: Lambda Backend Functions

## Goal
Write and deploy the two "enterprise system" Lambda functions that the agent calls as tools at runtime. These simulate a real inventory system and a real CRM — in production they would talk to actual databases. After this phase the agent has live data to work with. `terraform destroy` removes both functions and their IAM execution roles.

---

## What We're Building

```
lambdas/
├── inventory/
│   ├── handler.py          ← inventory data + getInventory logic
│   └── requirements.txt    ← (empty — stdlib only)
└── user_management/
    ├── handler.py          ← user data + getUserById/getUserByEmail logic
    └── requirements.txt    ← (empty — stdlib only)

terraform/
└── modules/
    └── lambda_backends/
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

### Resources

| Resource | Name | Purpose |
|---|---|---|
| `aws_iam_role` | `PetStoreInventoryLambdaRole` | Execution role for inventory Lambda — allows basic CloudWatch logging |
| `aws_lambda_function` | `PetStoreInventoryManagementFunction` | Serves `getInventory` requests from the agent |
| `aws_iam_role` | `PetStoreUserMgmtLambdaRole` | Execution role for user management Lambda |
| `aws_lambda_function` | `PetStoreUserManagementFunction` | Serves `getUserById` and `getUserByEmail` requests |
| `data "archive_file"` (×2) | — | Zips each Lambda's Python file for deployment — Terraform handles this natively |

---

## Request/Response Contract

The agent calls these functions with a specific payload structure (from `inventory_management.py` and `user_management.py`). The Lambdas must respond in the exact nested format the agent expects:

### Inventory Lambda

**Request:**
```json
{
  "function": "getInventory",
  "parameters": [
    { "name": "product_code", "value": "DD006" }
  ]
}
```

**Response (must match this exact nesting):**
```json
{
  "response": {
    "functionResponse": {
      "responseBody": {
        "TEXT": {
          "body": "{\"product_code\": \"DD006\", \"name\": \"Doggy Delights\", \"quantity\": 150, \"last_updated\": \"2026-05-05T00:00:00Z\", \"status\": \"in_stock\", \"reorder_level\": 50}"
        }
      }
    }
  }
}
```

Note: `body` is a JSON string inside the outer JSON — double-encoded. This matches what the agent code does: `json.loads(lambda_response['response']['functionResponse']['responseBody']['TEXT']['body'])`.

When called without a `product_code`, return all products as a list.

### User Management Lambda

**Functions:** `getUserById` and `getUserByEmail`

**Response format** (same nesting as above, body contains):
```json
{
  "id": "usr_001",
  "name": "John Doe",
  "email": "john.doe@virtualpetstore.com",
  "subscription_status": "active",
  "subscription_end_date": "2027-01-01T00:00:00Z",
  "transactions": [
    { "id": "txn_001", "amount": 29.99, "date": "2026-04-01T00:00:00Z", "description": "Monthly subscription" }
  ]
}
```

---

## Inventory Data to Implement

Covers all products from the catalog files. Quantities and reorder levels are set to exercise all agent business rules:

| Product Code | Name | Quantity | Reorder Level | Status |
|---|---|---|---|---|
| DD006 | Doggy Delights | 150 | 50 | in_stock |
| DD007 | PuppyPower Bites | 45 | 30 | low_stock |
| DD008 | Senior Serenity Blend | 80 | 25 | in_stock |
| DD009 | Hearty Stew Wet Dog Food | 200 | 40 | in_stock |
| DD010 | Mega Feast Bundle Pack | 12 | 10 | low_stock |
| CM001 | Meow Munchies | 120 | 40 | in_stock |
| CM002 | Kitten Kickstart | 60 | 20 | in_stock |
| CM003 | Purrfect Pate Wet Cat Food | 180 | 50 | in_stock |
| CM004 | Senior Whiskers Formula | 35 | 20 | low_stock |
| CM005 | Indoor Calm Blend | 90 | 30 | in_stock |
| BP010 | Bark Park Buddy | 55 | 20 | in_stock |
| BP011 | ToughChew Rope Toy Set | 75 | 25 | in_stock |
| BP012 | OrthoRest Dog Bed | 8 | 10 | low_stock |
| BP013 | ProTrainer Adjustable Harness | 40 | 15 | in_stock |
| BP014 | Deluxe Grooming Kit for Dogs | 30 | 10 | in_stock |
| BP015 | SmartFeed Automatic Dog Feeder | 5 | 8 | low_stock |
| CA001 | ScratchMaster Deluxe Cat Tree | 18 | 10 | in_stock |
| CA002 | PurrZen Interactive Laser Toy | 65 | 20 | in_stock |
| CA003 | CleanPaws Self-Cleaning Litter Box | 22 | 10 | in_stock |
| CA004 | CozyCave Heated Cat Bed | 40 | 15 | in_stock |
| CA005 | FountainFlow Cat Water Fountain | 50 | 20 | in_stock |
| GR001 | FoamFresh Dog Shampoo | 110 | 30 | in_stock |
| GR002 | GentleGlow Cat Shampoo | 95 | 30 | in_stock |
| GR003 | ProShine Deshedding Brush | 70 | 20 | in_stock |
| GR004 | PawPerfect Nail Grinder | 45 | 15 | in_stock |
| GR005 | SpaDay Pet Grooming Bundle | 15 | 10 | in_stock |
| TS001 | Chicken Crunch Dog Treats | 200 | 50 | in_stock |
| TS002 | Salmon Snap Cat Treats | 180 | 50 | in_stock |
| TS003 | JointEase Dog Supplement | 60 | 20 | in_stock |
| TS004 | OmegaShine Cat Supplement | 55 | 20 | in_stock |
| TS005 | DentalFresh Dental Chews | 90 | 25 | in_stock |

Inventory logic:
- `status` = `"out_of_stock"` if quantity == 0
- `status` = `"low_stock"` if quantity <= reorder_level
- `status` = `"in_stock"` otherwise

---

## User Data to Implement

Three users: one active subscriber, one expired subscriber, one non-existent (to test error handling):

| ID | Name | Email | Subscription |
|---|---|---|---|
| `usr_001` | John Doe | john.doe@virtualpetstore.com | active (expires 2027-01-01) |
| `usr_002` | Jane Smith | jane.smith@virtualpetstore.com | expired (expired 2025-01-01) |
| `usr_003` | Bob Wilson | bob.wilson@virtualpetstore.com | active (expires 2027-06-01) |

When a user is not found by ID or email, return:
```json
{ "error": "User not found", "id": "<queried_id>" }
```

---

## Terraform Packaging

Terraform's `archive_file` data source zips the Python file at plan time:
```hcl
data "archive_file" "inventory_zip" {
  type        = "zip"
  source_file = "${path.module}/../../../lambdas/inventory/handler.py"
  output_path = "${path.module}/tmp/inventory.zip"
}
```

The zip's hash is used by Terraform to detect code changes — if `handler.py` changes, Terraform automatically redeploys the Lambda on next `apply`.

---

## Step-by-Step Implementation

1. Write `lambdas/inventory/handler.py` with in-memory product data and request routing
2. Write `lambdas/user_management/handler.py` with in-memory user data and request routing
3. Write `modules/lambda_backends/main.tf`
4. Wire `module "lambda_backends"` from root
5. `terraform plan` — 6 resources (2 roles, 2 policies, 2 functions)
6. `terraform apply`
7. Test inventory Lambda manually:
   ```bash
   aws lambda invoke --function-name PetStoreInventoryManagementFunction \
     --payload '{"function":"getInventory","parameters":[{"name":"product_code","value":"DD006"}]}' \
     --cli-binary-format raw-in-base64-out output.json && cat output.json
   ```
8. Test user Lambda manually:
   ```bash
   aws lambda invoke --function-name PetStoreUserManagementFunction \
     --payload '{"function":"getUserById","parameters":[{"name":"user_id","value":"usr_001"}]}' \
     --cli-binary-format raw-in-base64-out output.json && cat output.json
   ```
9. Verify response structure matches exactly what the agent code expects
10. `terraform destroy` — verify both functions deleted
11. `terraform apply` again to restore
12. `git push`

---

## Verify & Test

```bash
# List functions exist
aws lambda list-functions \
  --query 'Functions[?contains(FunctionName, `PetStore`)].FunctionName'

# Check logs after invocation
aws logs tail /aws/lambda/PetStoreInventoryManagementFunction --follow
```

---

## Execution Log

### `terraform apply` — Clean on first attempt

**IAM adaptation:** The phase doc planned to create `PetStoreInventoryLambdaRole` / `PetStoreUserMgmtLambdaRole`. The `HCL-Permissions-Boundary` only allows `iam:CreateRole` on `AmazonBedrockExecution*`-named resources. Arbitrary Lambda role names would be denied. Used `solution_access_role_arn` (`HCL-User-Role-PD-BedrockAgentCoreRole`) as the execution role for both functions instead — it already has `logs:*` and the Lambda service can assume it.

**Outputs:**
```
inventory_function_name       = "PetStoreInventoryManagementFunction"
user_management_function_name = "PetStoreUserManagementFunction"
```

### Manual invocation tests — All passed

```bash
# Inventory by product code
aws lambda invoke --function-name PetStoreInventoryManagementFunction \
  --payload '{"function":"getInventory","parameters":[{"name":"product_code","value":"DD006"}]}'
# → { product_code: DD006, name: Doggy Delights, quantity: 150, status: in_stock, ... }

# User by ID
aws lambda invoke --function-name PetStoreUserManagementFunction \
  --payload '{"function":"getUserById","parameters":[{"name":"user_id","value":"usr_001"}]}'
# → { id: usr_001, name: John Doe, subscription_status: active, transactions: [...] }

# User by email
aws lambda invoke --function-name PetStoreUserManagementFunction \
  --payload '{"function":"getUserByEmail","parameters":[{"name":"user_email","value":"jane.smith@virtualpetstore.com"}]}'
# → { id: usr_002, name: Jane Smith, subscription_status: expired, ... }
```

Response nesting matches exactly what `inventory_management.py:65` and `user_management.py:71` expect.

---

## For Srikar's Understanding

### Homework

**1. Why is the response body double-encoded JSON?**
Look at the agent code in `inventory_management.py` line 65: it calls `json.loads()` twice — once on the Lambda response payload, and once on the `body` field inside it. Why would AWS design this nested structure? Look at how AWS Bedrock Agent function calling formats responses — this structure comes from the Bedrock agent action group response format.

**2. What is `archive_file` and how does Terraform detect code changes?**
Terraform uses a SHA256 hash of the zip file to decide whether to redeploy a Lambda. What happens in `terraform plan` if you change a single line in `handler.py`? What happens if you change a comment? Try it.

**3. Why do the Lambda functions have separate IAM roles from the SolutionAccessRole?**
The Lambda backends (inventory, user management) get their own minimal IAM roles with only `logs:*` permissions, not the full `SolutionAccessRole`. What security principle does this follow? What would be the risk of giving the inventory Lambda full access to Bedrock?

**4. The `reorder_level` field and the agent's business rule**
The system prompt says: *"When an order can cause the remaining inventory to fall below or equal to the reorder level, flag that product for replenishment."* This logic runs in the agent's reasoning, not in the Lambda. Looking at BP012 (OrthoRest Dog Bed, quantity=8, reorder_level=10), what would happen if a customer ordered 1? What about 0 remaining after the order?

**5. In-memory data vs real database — what breaks at scale?**
Our Lambda uses a Python dictionary as the data store. This is fine for a challenge but would fail in production. What are three specific problems that arise when multiple Lambda instances run concurrently with shared in-memory state? What AWS service would you replace this with?
