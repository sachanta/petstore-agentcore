# Phase 7: AgentCore Runtime

## Goal
Deploy the AgentCore Runtime using the Docker image from Phase 6. This is the final infrastructure step — after this phase the full agent is live and queryable. This phase also wires the guardrail from Phase 4 and the environment variables (KB IDs, Lambda names) from earlier phases into the runtime. `terraform destroy` removes the runtime cleanly.

---

## What We're Building

```
terraform/
└── modules/
    └── agent_runtime/
        ├── main.tf
        ├── variables.tf
        ├── outputs.tf
        └── scripts/
            ├── deploy_runtime.py   ← creates or updates AgentCore Runtime
            └── delete_runtime.py  ← destroy-time cleanup
```

### Resources

| Resource | Terraform mechanism | Purpose |
|---|---|---|
| AgentCore Runtime `LangGraphAgentCoreRuntime` | `null_resource` + `local-exec` | No native AWS provider resource exists yet — we call the Bedrock AgentCore API directly |
| CloudWatch Log Group `/aws/bedrock-agentcore/petstore-agent` | `aws_cloudwatch_log_group` | Captures agent runtime logs for debugging; also used by the GenAI Observability dashboard |

---

## Why `null_resource` Again?

The AWS Terraform provider (as of v5.x) does not have an `aws_bedrock_agentcore_runtime` resource. This is a new AWS service. We call the API using boto3 in a Python script via `local-exec`.

As soon as the provider adds native support, migrating is straightforward — replace the `null_resource` with the native resource and import the existing runtime into Terraform state.

---

## `deploy_runtime.py` — Logic

```
1. Accept runtime_name, ecr_image_uri, role_arn, and env_vars as arguments
2. Call bedrock-agentcore-control list-agent-runtimes
3. If runtime with this name exists → call update-agent-runtime
4. If not → call create-agent-runtime
5. Poll get-agent-runtime until status is READY (max 15 min timeout)
6. Print runtime ARN and ID
7. Write runtime_id and runtime_arn to a local file for Terraform to read back
8. Exit non-zero on CREATE_FAILED or timeout
```

The runtime configuration passed to the API:

```python
{
    "agentRuntimeName": "LangGraphAgentCoreRuntime",
    "roleArn": "<SolutionAccessRoleArn>",
    "agentRuntimeArtifact": {
        "containerConfiguration": {
            "containerUri": "<ecr_image_uri>"
        }
    },
    "networkConfiguration": {
        "networkMode": "PUBLIC"
    },
    "environmentVariables": {
        "AWS_DEFAULT_REGION": "<region>",
        "KNOWLEDGE_BASE_1_ID": "<product_info_kb_id>",
        "KNOWLEDGE_BASE_2_ID": "<pet_care_kb_id>",
        "SYSTEM_FUNCTION_1_NAME": "<inventory_function_name>",
        "SYSTEM_FUNCTION_2_NAME": "<user_mgmt_function_name>"
    },
    "lifecycleConfiguration": {
        "maxLifetime": 60
    }
}
```

Key point: **environment variables are injected here at the runtime level** — the Docker image is environment-agnostic. Changing a KB ID or Lambda name just requires updating the runtime (re-running the script), not rebuilding the image.

---

## Reading Runtime Outputs Back into Terraform

Since `null_resource` can't natively output values, the script writes the runtime ID and ARN to a local JSON file:

```
terraform/modules/agent_runtime/tmp/runtime_outputs.json
{
  "agent_runtime_id": "LangGraphAgentCoreRuntime-abc123",
  "agent_runtime_arn": "arn:aws:bedrock-agentcore:us-east-1:040504913362:runtime/..."
}
```

A Terraform `local_file` data source reads this file, and outputs expose the values to the root module.

---

## `delete_runtime.py` — Destroy Logic

```
1. Read runtime ID from the outputs JSON file written during create
2. Call bedrock-agentcore-control delete-agent-runtime
3. Poll get-agent-runtime until ResourceNotFoundException (confirms deletion)
4. Exit 0
```

This is attached as a `destroy` provisioner on the `null_resource`.

---

## The GenAI Observability Dashboard

The Dockerfile sets OpenTelemetry environment variables:
```
OTEL_PYTHON_DISTRO=aws_distro
OTEL_TRACES_EXPORTER=otlp
AGENT_OBSERVABILITY_ENABLED=true
```

When the agent processes a request, it emits traces via OpenTelemetry to CloudWatch. AWS automatically populates the **GenAI Observability** dashboard in CloudWatch with:
- Per-request trace timelines showing each tool call
- Token usage per step
- Model latency
- Tool call outcomes

This is accessible in CloudWatch → Application Signals → GenAI Observability. No extra configuration needed — the OTEL env vars activate it automatically.

---

## Outputs (final — used for testing in Phase 8)

```
agent_runtime_id
agent_runtime_arn
```

---

## Step-by-Step Implementation

1. Write `modules/agent_runtime/main.tf` — CloudWatch log group, null_resource with create + destroy provisioners
2. Write `deploy_runtime.py` and `delete_runtime.py` under `terraform/scripts/`
3. Wire `module "agent_runtime"` from root, passing outputs from all previous phases:
   - `ecr_image_uri` from Phase 6
   - `solution_access_role_arn` from Phase 1
   - `product_info_kb_id` + `pet_care_kb_id` from Phase 3
   - `inventory_function_name` + `user_mgmt_function_name` from Phase 5
4. `terraform plan` — 2 resources (log group + null_resource)
5. `terraform apply` — runtime creation takes 3-5 minutes to reach READY status
6. Verify runtime is READY:
   ```bash
   aws bedrock-agentcore-control list-agent-runtimes \
     --query 'agentRuntimes[?agentRuntimeName==`LangGraphAgentCoreRuntime`].status'
   ```
7. Test invoke (see Phase 8 for detailed test plan)
8. `terraform destroy` — runtime deleted, ECR repo deleted, all resources cleaned
9. `terraform apply` again to restore (full apply from scratch: ~20 minutes)
10. `git push`

---

## Verify & Test

After `terraform apply`:
```bash
# Check runtime status
aws bedrock-agentcore-control list-agent-runtimes \
  --query 'agentRuntimes[?agentRuntimeName==`LangGraphAgentCoreRuntime`].{name:agentRuntimeName,status:status,id:agentRuntimeId}'

# Quick smoke test invoke
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <runtime_arn> \
  --qualifier DEFAULT \
  --content-type application/json \
  --payload '{"prompt": "A new user is asking about the price of Doggy Delights"}'
```

After `terraform destroy`:
```bash
# Should return empty list
aws bedrock-agentcore-control list-agent-runtimes \
  --query 'agentRuntimes[?agentRuntimeName==`LangGraphAgentCoreRuntime`]'
```

---

## Execution Log

### `terraform apply` — Clean on first attempt

Runtime created and READY in **23 seconds**.

**Note on outputs:** Terraform's `file()` function is evaluated at plan time, so `agent_runtime_id` and `agent_runtime_arn` outputs show as empty strings on the first apply (the JSON file doesn't exist yet at plan time). A second `terraform apply` (no-op) reads the now-existing file and resolves the outputs correctly. This is an inherent limitation of `null_resource` + `file()` for output passing.

**Runtime:**
```
agent_runtime_id  = "LangGraphAgentCoreRuntime-wl5A1CH151"
agent_runtime_arn = "arn:aws:bedrock-agentcore:us-east-1:040504913362:runtime/LangGraphAgentCoreRuntime-wl5A1CH151"
```

### Smoke test — PASSED

```
Prompt: "What is the price of Doggy Delights?"

Response:
{
  "status": "Accept",
  "message": "Dear Customer! We offer our 30lb bag of Doggy Delights for just $54.99...",
  "customerType": "Guest",
  "items": [{ "productId": "DD006", "price": 54.99, "quantity": 1, "total": 54.99 }],
  "shippingCost": 14.95,
  "subtotal": 69.94,
  "total": 69.94
}
```

Agent correctly: retrieved price from ProductInformation KB, checked inventory (DD006 in stock), returned full order summary.

---

## For Srikar's Understanding

### Homework

**1. What does `networkMode: PUBLIC` mean and is it safe?**
The runtime is configured with `PUBLIC` network mode. This means the runtime endpoint is reachable over the public internet. What protects it from unauthorised callers? (Hint: look at how `invoke-agent-runtime` is called — what authentication mechanism does it use?) What would `PRIVATE` network mode require?

**2. What is `maxLifetime: 60` in the lifecycle configuration?**
The runtime has a `maxLifetime` of 60 minutes. After 60 minutes of activity, AgentCore does something to the runtime container. What is it, and why is this useful for a stateless agent? What would happen to an in-progress conversation if the runtime recycled mid-session?

**3. OpenTelemetry — what is it and why use it instead of print statements?**
The agent uses `opentelemetry-instrument` as the process entrypoint. OpenTelemetry is a vendor-neutral observability standard. What does "instrumentation" mean in this context? What is the difference between a trace, a span, and a metric? Why does the GenAI Observability dashboard understand the agent's tool calls specifically?

**4. Environment variables vs baked-in config — what's the advantage?**
KB IDs and Lambda names are injected as environment variables into the runtime, not baked into the Docker image. If the ProductInformation KB ID changes (e.g. after a destroy + apply), what do you need to do to the runtime vs what you'd need to do to the image? Why does this separation matter for a CI/CD pipeline?

**5. No native Terraform resource yet — how would you migrate when one arrives?**
When AWS adds `aws_bedrock_agentcore_runtime` to the Terraform provider, you'll want to switch from `null_resource` to the native resource. What is `terraform import` and how would you use it to bring an existing runtime under native Terraform management without destroying and recreating it?
