# Virtual Pet Store Agent

A demo AI agent for a virtual pet store, built with LangGraph and deployed on AWS Bedrock AgentCore. The entire stack --- agent runtime, knowledge bases, guardrails, Lambda backends, ECR image builds, and observability --- is orchestrated with Terraform for one-command spin-up and teardown.

The agent handles product inquiries, order processing with bundle discounts and shipping logic, pet care advice via RAG, user account lookups, and inventory replenishment flags. It runs Amazon Nova Pro as the foundation model and uses a ReAct tool-calling loop.

## Architecture

```
User  -->  Chat UI (Vite + React)
             |
             v
           FastAPI proxy (server.py)
             |
             v
        Bedrock AgentCore Runtime
          |-- LangGraph ReAct agent (Amazon Nova Pro)
          |-- Tool: retrieve_product_info (Bedrock Knowledge Base, S3)
          |-- Tool: retrieve_pet_care (Bedrock Knowledge Base, web crawler)
          |-- Tool: get_inventory / get_user (Lambda backends)
          |-- Guardrail: topic + content filters (Bedrock Guardrail)
          |-- Tracing: OpenTelemetry --> Arize AX
```

See [docs/aws-architecture.md](docs/aws-architecture.md) for the full component diagram.

## Prerequisites

- AWS account with Bedrock AgentCore access (us-east-1)
- IAM role with AgentCore, Bedrock, ECR, CodeBuild, Lambda, S3, OpenSearch Serverless permissions
- Python 3.12+
- Node.js 18+ and npm (for the chat UI)
- Terraform 1.5+
- AWS CLI v2 configured with credentials
- (Optional) Arize AX account for tracing

See [docs/prerequisites.md](docs/prerequisites.md) for the full setup checklist.

## Quick Start

### 1. Deploy the infrastructure

```bash
cd terraform

# First time: copy and fill in credentials
cp .env.example .env
# Edit .env --- add your Arize API key (or leave blank to skip tracing)

# Deploy everything: IAM, S3, OpenSearch, Knowledge Bases, Guardrail,
# Lambda backends, ECR repo, CodeBuild image, AgentCore Runtime
source .env && terraform init && terraform apply
```

Or use the Makefile:

```bash
cd terraform
make apply
```

This takes ~10 minutes on first run (CodeBuild image build is ~8 min). Terraform outputs the runtime ARN when done.

### 2. Start the Chat UI

```bash
cd ui

# Set the runtime ARN (auto-populated by terraform output)
echo "RUNTIME_ARN=$(cd ../terraform && terraform output -raw agent_runtime_arn)" > .env

# Install and start
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install

# Start both the FastAPI proxy and Vite dev server
uvicorn server:app --port 8000 &
npm run dev
```

Open http://localhost:5173 in your browser.

See [docs/phase-09-chat-ui.md](docs/phase-09-chat-ui.md) for details.

### 3. Run the test suite

```bash
export RUNTIME_ARN=$(cd terraform && terraform output -raw agent_runtime_arn)
python3 tests/test_agent.py
```

22 end-to-end tests covering product queries, subscriptions, pricing rules, guardrails, and edge cases. Each test invokes the live runtime.

See [docs/phase-08-testing-and-teardown.md](docs/phase-08-testing-and-teardown.md) for test categories and expected results.

### 4. Tear down

```bash
cd terraform
make destroy
```

This deletes the AgentCore Runtime, CodeBuild project, ECR images, Lambda functions, Knowledge Bases, OpenSearch collection, and all supporting resources.

## Arize AX Tracing (Optional)

The agent exports OpenTelemetry traces to Arize AX for observability --- every LLM call, tool invocation, and ReAct step is captured with latency, token counts, and cost.

### Enable tracing

1. Get your Space ID and API key from https://app.arize.com
2. Add them to `terraform/.env`:
   ```
   export TF_VAR_arize_space_id=<your-space-id>
   export TF_VAR_arize_api_key=<your-api-key>
   ```
3. Redeploy: `make apply` (from `terraform/`)

Traces appear in the Arize UI under the `virtual-pet-store-agent` project.

### Tracing docs

The tracing setup required solving three AgentCore interference issues. Each is documented in detail:

| Doc | What it covers |
|-----|----------------|
| [arize_traces.md](docs/arize_traces.md) | Initial setup: auth headers, gRPC vs HTTP, span attributes |
| [arize_traces_2.md](docs/arize_traces_2.md) | AgentCore OTEL env var hijack, re-instrumentation collision |
| [arize_traces_3.md](docs/arize_traces_3.md) | Waterfall fix: orphaned parent spans, trace context detachment |

## MCP Servers (Claude Code)

Three MCP servers are configured for use with Claude Code, giving Claude direct access to Arize docs and live trace data.

| Server | Purpose | How to add |
|--------|---------|------------|
| `arize-tracing-assistant` | Instrumentation help, span debugging | `claude mcp add arize-tracing-assistant uvx arize-tracing-assistant@latest` |
| `arize-ax-docs` | Full Arize documentation search | `claude mcp add arize-ax-docs --transport http https://arize.com/docs/mcp` |
| `arize-live-traces` | Live trace queries via Arize GraphQL API | See below |

### Custom MCP server: arize-live-traces

```bash
claude mcp add arize-live-traces \
  python3 mcp/arize/server.py \
  -e ARIZE_API_KEY=<your-key> \
  -e ARIZE_SPACE_ID=<your-space-id>
```

Tools: `list_models`, `get_recent_traces`, `get_trace`, `get_stats`, `search_spans`.

See [docs/arize_mcp.md](docs/arize_mcp.md) for full setup and auth details.

## Evaluation Suite

An offline evaluation suite using Arize Phoenix with 22 test cases:

```bash
cd tests
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-eval.txt

export RUNTIME_ARN=$(cd ../terraform && terraform output -raw agent_runtime_arn)

# Against local Phoenix server
python3 eval_arize.py

# Against Arize cloud
export PHOENIX_ENDPOINT=https://app.phoenix.arize.com
export PHOENIX_API_KEY=<your-key>
python3 eval_arize.py
```

## Project Structure

```
pet_store_agent/          Agent source code (deployed to AgentCore)
  agentcore_entrypoint.py   Runtime handler + guardrail + business rules
  pet_store_agent.py        LangGraph ReAct agent (Nova Pro)
  tracing.py                Arize AX OpenTelemetry instrumentation
  requirements.txt          Python dependencies for the container

terraform/                Infrastructure as code
  main.tf                   Root module wiring
  modules/
    agent_image/            ECR repo + CodeBuild image build
    agent_runtime/          AgentCore Runtime deploy/update/delete
  scripts/
    deploy_runtime.py       Create or update runtime via boto3
    delete_runtime.py       Delete runtime on terraform destroy
  .env.example              Template for credentials
  Makefile                  Convenience targets (apply, destroy, plan)

ui/                       Chat frontend
  src/                      Vite + React + Tailwind
  server.py                 FastAPI proxy to AgentCore
  .env                      RUNTIME_ARN (auto-set after deploy)

tests/
  test_agent.py             22 end-to-end tests against live runtime
  eval_arize.py             Arize Phoenix evaluation suite

mcp/arize/                Custom MCP server for live trace access
  server.py                 GraphQL client with 5 tools
  requirements.txt          mcp[cli] + httpx

docs/                     Build guides, architecture, troubleshooting
  phase-01 through 09       Step-by-step infrastructure build
  arize_traces 1-3          Tracing setup and debugging trilogy
  arize_mcp.md              MCP server setup
  aws-architecture.md       Full architecture diagram
  terraform-troubleshooting.md  Common ops issues and fixes
```

## Docs Index

| Doc | Description |
|-----|-------------|
| [prerequisites.md](docs/prerequisites.md) | Full prerequisites and deployment plan |
| [phase-01-foundation-iam-s3.md](docs/phase-01-foundation-iam-s3.md) | IAM roles and S3 buckets |
| [phase-02-aoss.md](docs/phase-02-aoss.md) | OpenSearch Serverless collection |
| [phase-03-knowledge-bases.md](docs/phase-03-knowledge-bases.md) | Bedrock Knowledge Bases (S3 + web crawler) |
| [phase-04-guardrail.md](docs/phase-04-guardrail.md) | Bedrock Guardrail configuration |
| [phase-05-lambda-backends.md](docs/phase-05-lambda-backends.md) | Inventory + user management Lambdas |
| [phase-06-docker-ecr.md](docs/phase-06-docker-ecr.md) | Dockerfile and ECR image build |
| [phase-07-agentcore-runtime.md](docs/phase-07-agentcore-runtime.md) | AgentCore Runtime deployment |
| [phase-08-testing-and-teardown.md](docs/phase-08-testing-and-teardown.md) | Test suite and teardown |
| [phase-09-chat-ui.md](docs/phase-09-chat-ui.md) | Vite + React chat UI |
| [arize_traces.md](docs/arize_traces.md) | Arize tracing setup |
| [arize_traces_2.md](docs/arize_traces_2.md) | AgentCore OTEL interference fixes |
| [arize_traces_3.md](docs/arize_traces_3.md) | Waterfall view fix |
| [arize_mcp.md](docs/arize_mcp.md) | MCP server setup for Claude Code |
| [aws-architecture.md](docs/aws-architecture.md) | Full AWS architecture |
| [agentcore-cli.md](docs/agentcore-cli.md) | AgentCore CLI reference |
| [terraform-troubleshooting.md](docs/terraform-troubleshooting.md) | Terraform ops troubleshooting |

## License

MIT-0 (see source headers)
