# Simplex Stepping in an Agentic World: A Walkthrough of Running an Agent in AgentCore

*By Srikar Achanta*

---

It started with a Jupyter notebook.

AWS published a reference notebook for deploying a LangGraph ReAct agent on Bedrock AgentCore --- a 26-cell walkthrough that installs packages, creates IAM roles inline, builds Docker images with CodeBuild, and deploys the runtime with raw boto3 calls. It works. You run the cells top to bottom, and at the end you have a live agent that answers questions about a virtual pet store.

But here's the thing about notebooks: they're great for learning, terrible for operating. You can't `terraform destroy` a notebook. You can't `git diff` a cell. You can't hand one to a teammate and say "spin this up in your account." So I set out to convert the whole thing into proper infrastructure-as-code --- Terraform modules, version-controlled, repeatable, destroyable.

What I didn't expect was how much I'd learn along the way about the invisible machinery running underneath AgentCore.

---

## From Notebook to Terraform: Nine Phases

I broke the conversion into nine phases, each one a Terraform module. A few highlights from what I ran into:

**IAM was the first wall.** The account I was working in had a permissions boundary that only allows creating IAM roles matching specific naming patterns. The notebook hardcodes role names that don't match. Instead of fighting the boundary, I switched to referencing the pre-existing roles as data sources. Lesson: in enterprise environments, you don't own IAM. Design around it.

**OpenSearch Serverless has a three-layer security model** --- encryption, network, and access policies --- and all three must be in place before the collection will start. The collection itself takes 2--5 minutes to bootstrap. I learned to poll intelligently rather than sleep-and-pray.

**Bedrock Knowledge Bases validate using their own service role**, not the caller's identity. This means the execution role must have AOSS access, not just the user deploying the stack. The web crawler data source was another surprise: it's created inside a Lambda during stack setup but lives outside CloudFormation's resource graph, so it gets orphaned on `terraform destroy`. I added a destroy provisioner to clean it up.

**CodeBuild image changes didn't trigger runtime redeployment** because the ECR tag is always `:latest`. Terraform saw no change. I fixed this by computing a SHA256 hash of all agent source files and threading it through as a trigger --- any code change now forces a rebuild and redeploy automatically.

**There's no native Terraform resource for AgentCore** (it's a new service). The runtime deploy/update/delete all happen through `local-exec` provisioners calling Python scripts that use boto3. It works, but it's a reminder that infrastructure tooling always lags the services it manages.

By the end of phase nine, I had a working chat UI (Vite + React + FastAPI proxy), 22 end-to-end tests, and a `make destroy` that tears it all down cleanly.

---

## Adding Observability: Where Things Got Interesting

With the infrastructure solid, I wanted observability. Real observability --- not just CloudWatch logs, but trace waterfalls showing every LLM call, tool invocation, and ReAct reasoning step. I chose Arize AX and set up OpenTelemetry instrumentation in the agent code.

The setup looked straightforward: create a TracerProvider, point it at Arize's OTLP endpoint, instrument LangChain. Three lines of config. Should take an hour.

It took days.

### Issue 1: The Silent Redirect

Spans weren't arriving at Arize. No errors in the logs, no connection failures --- just silence. After adding diagnostic logging inside the container, I discovered that AgentCore sets an environment variable at startup:

```
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://xray.us-east-1.amazonaws.com/v1/traces
```

The OpenTelemetry SDK is designed so that environment variables override constructor arguments. My code said "send to Arize," but the SDK silently routed every span to AWS X-Ray instead. X-Ray rejected them (wrong auth format), and the BatchSpanProcessor swallowed the errors.

**Fix:** Clear the env vars before constructing the exporter:
```python
os.environ.pop("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", None)
```

### Issue 2: The Instrumentation That Wasn't

After fixing the endpoint, still no spans. CloudWatch showed a warning I'd been ignoring:

```
Attempting to instrument while already instrumented
```

AgentCore auto-instruments LangChain during its bootstrap, before my code runs. When I called `LangChainInstrumentor().instrument(tracer_provider=arize_provider)`, the instrumentor detected it was already active and silently skipped the call. My custom provider was never wired in.

**Fix:** Uninstrument first, then re-instrument:
```python
instrumentor = LangChainInstrumentor()
if instrumentor.is_instrumented_by_opentelemetry:
    instrumentor.uninstrument()
instrumentor.instrument(tracer_provider=arize_provider)
```

After these two fixes, spans started appearing in Arize. Victory, right?

Not quite.

---

## The Missing Waterfalls

Spans were in Arize, but clicking into any trace showed a single isolated span --- no parent-child tree, no waterfall timing diagram. Arize was treating every span as an unrelated fragment. For observability, this is useless. The whole point of tracing is seeing how a 5-second request breaks down: 200ms on the knowledge base lookup, 1.8 seconds on the LLM call, 400ms on the inventory Lambda.

This is where talking to **Alyx** changed things.

### Asking the Arize AI Agent

Alyx is Arize's AI support agent. I described the symptoms --- spans visible but no waterfall --- and Alyx immediately identified the pattern: *"This is a classic AgentCore telemetry collision."*

Alyx explained that AgentCore wraps every invocation in its own trace span. That span is the root of the trace, and it only exists in X-Ray. My LangChain spans inherit AgentCore's trace context (same `traceId`, a `parentId` pointing back to AgentCore's span). Arize receives the children but never the root. Without the root, it can't build a tree.

This was the insight I needed. But debugging it further required querying actual trace data --- checking `parentId` values, seeing which spans existed where. I was copy-pasting GraphQL queries to Arize's API, relaying results, cross-referencing. Slow and error-prone.

### Giving Claude Code Direct Access

I realized the bottleneck was me. I was the human relay between the AI tools and the observability platform. So I did something that felt like a natural next step in an agentic workflow: I gave Claude Code direct access to Arize.

I added three MCP (Model Context Protocol) servers:

1. **arize-tracing-assistant** --- Arize's official instrumentation assistant. Claude could now ask it about AgentCore-specific patterns directly.
2. **arize-ax-docs** --- Full-text search of all Arize documentation. No more tab-switching to look up OTLP header formats.
3. **arize-live-traces** --- A custom MCP server I built that queries the Arize GraphQL API. Five tools: list models, get recent traces, get a specific trace, get stats, search spans.

The custom server was surprisingly straightforward --- ~300 lines of Python using `mcp[cli]` and `httpx`. The main discovery was the auth format: `Authorization: Bearer` returns 401, `space_id` + `api_key` headers return 401, but `x-api-key` works. You don't find this in the docs.

With the MCP servers connected, Claude could now query live trace data directly. The first thing it did was fetch 50 spans and check every `parentId`:

```
42 out of 50 spans have a parentId not found in Arize.
```

Every `LangGraph` span --- our expected root --- had a `parentId` pointing to a span that only existed in X-Ray. Arize was receiving children without parents. No wonder it couldn't build waterfalls.

### The Three-Line Fix

The solution was elegant. At the point where the handler invokes the agent, detach AgentCore's trace context:

```python
from opentelemetry import context as otel_context

token = otel_context.attach(otel_context.Context())
try:
    response = pet_store_agent.process_request(prompt)
finally:
    otel_context.detach(token)
```

`otel_context.Context()` creates an empty context with no parent span. LangChain sees no active trace and starts a fresh one. The `LangGraph` span becomes a genuine root in Arize. The `finally` block restores AgentCore's context so its own infrastructure telemetry continues working.

After deploying this fix, the Arize UI showed exactly what I wanted: full waterfall views with every span nested under the `LangGraph` root, latency breakdown per step, token counts, cost attribution. Real observability.

---

## What I Took Away

**Infrastructure-as-code isn't just about reproducibility.** It's about making the invisible visible. The notebook worked, but I never would have discovered the OTEL endpoint hijack or the auto-instrumentation collision if I hadn't been forced to understand every layer of the stack.

**AgentCore's telemetry is opinionated.** It assumes it owns the OpenTelemetry pipeline. If you want to export to a third-party observability platform, you're working against three layers of interference: env var overrides, pre-instrumentation, and inherited trace context. All fixable, but none documented.

**The MCP server pattern is powerful.** Giving your AI assistant direct access to your observability platform removes you as the relay bottleneck. The orphaned parent span issue was found in seconds once Claude could query the GraphQL API directly. Without that access, I'd still be copy-pasting JSON.

**Agentic workflows compound.** The pet store agent is simple --- four tools, one LLM, deterministic business rules. But the infrastructure around it (IAM boundaries, OTEL conflicts, trace context propagation, knowledge base service roles) is genuinely complex. Each layer interacts with the others in ways that notebooks don't surface. Terraform surfaces them because it forces you to declare every dependency.

The notebook is still there in the repo. I keep it as a reminder of where this started. But the real system is the Terraform modules, the tracing pipeline, the test suite, the MCP servers. A `make apply` brings it all up. A `make destroy` takes it down. And when something breaks, the traces show me exactly where.

That's the simplex step: one phase at a time, each one revealing something the previous one hid.

---

*The full project, including all nine Terraform phases, the tracing debugging trilogy, and the custom MCP server, is available on GitHub. The docs folder alone is worth browsing --- every gotcha is documented so you don't have to rediscover it.*
