# Arize AX Tracing — Part 3: Fixing Trace Waterfall Views

This document covers the third phase of the Arize tracing investigation. After the fixes in [arize_traces_2.md](arize_traces_2.md), spans were confirmed to be landing in Arize — but the Arize UI showed no waterfall views. Every span appeared as an isolated fragment, not as part of a tree.

Previous docs:
- [arize_traces.md](arize_traces.md) — initial setup, auth, gRPC vs HTTP, span attributes
- [arize_traces_2.md](arize_traces_2.md) — AgentCore OTEL env var hijack, re-instrumentation fix

---

## The Problem

Spans were visible in Arize's span list, but clicking into any trace showed a single isolated span — no parent-child hierarchy, no waterfall timing diagram. Arize was treating every span as an independent trace fragment.

---

## Investigation

### Querying the GraphQL API directly

Using the custom `arize-live-traces` MCP server ([mcp/arize/server.py](../mcp/arize/server.py)), we fetched spans from the last 24 hours and inspected their `parentId` fields:

```python
spans = [e["node"] for e in data["node"]["spanRecordsPublic"]["edges"]]
all_span_ids = {s["spanId"] for s in spans}

orphaned = [s for s in spans if s["parentId"] and s["parentId"] not in all_span_ids]
```

Result with 50 spans fetched:
- **42 out of 50 spans** had a `parentId` that did not exist anywhere in Arize
- The top-level `LangGraph` span (our expected root) itself had a `parentId` pointing to an unknown span

This meant Arize was receiving child spans whose parents didn't exist in its system. It cannot build a waterfall from dangling references.

### Where were the missing parents?

The missing parent spans belonged to AgentCore's own infrastructure. AgentCore wraps every invocation in its own OTel trace — a span that tracks the full round-trip from the Bedrock API gateway into the container. That span is exported to **AWS X-Ray** (see [arize_traces_2.md](arize_traces_2.md) — `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` points to X-Ray by default).

Our LangChain spans inherit the trace context from AgentCore's active span. So every span we export to Arize has a `traceId` and `parentId` that belong to AgentCore's X-Ray trace. Arize receives the children, X-Ray receives the root — neither system has a complete picture.

### The span hierarchy

What actually exists across systems:

```
X-Ray only:
  [AgentCore] InvokeAgentRuntime          ← root, traceId=abc123, spanId=aaaa
    [AgentCore] container_dispatch        ← traceId=abc123, parentId=aaaa

Arize only (orphaned children):
    [CHAIN] LangGraph                     ← traceId=abc123, parentId=bbbb (X-Ray only!)
      [AGENT] agent                       ← traceId=abc123, parentId=LangGraph.spanId
      [LLM] ChatBedrockConverse           ← traceId=abc123, parentId=agent.spanId
      ...
```

Arize has the `LangGraph` span and everything under it, but can't connect it to a root because the root (`bbbb`) is in X-Ray. So Arize renders `LangGraph` as if it were an isolated span rather than part of a tree.

---

## The Fix

### Approach: detach AgentCore's trace context before each invocation

The solution is to break the OTel parent-child link at the point where we hand off to LangChain. By attaching an empty `Context` object before calling `process_request()`, we tell the OTel SDK: "start fresh, no parent." LangChain then creates a new `LangGraph` root span with no `parentId` — making it a genuine trace root in Arize.

### Change in `agentcore_entrypoint.py`

Added import:
```python
from opentelemetry import context as otel_context
```

Wrapped the agent invocation in the `handler()` function:
```python
@app.entrypoint
def handler(payload):
    prompt = payload.get("prompt", "...")

    blocked = _check_guardrail(prompt)
    if blocked:
        return blocked

    # Detach AgentCore's trace context so our LangChain spans become root spans
    # in Arize instead of orphaned children whose parent only exists in X-Ray.
    token = otel_context.attach(otel_context.Context())
    try:
        response = pet_store_agent.process_request(prompt)
    finally:
        otel_context.detach(token)

    return _apply_business_rules(response)
```

### How it works

`otel_context.Context()` creates a new, empty context with no active span and no trace parent. `otel_context.attach()` makes this the current context for the duration of the `try` block. Any span created by LangChain during `process_request()` will see no parent in context and will start a fresh trace.

`otel_context.detach(token)` in `finally` restores AgentCore's original context, so AgentCore's own infrastructure spans continue working normally after the call returns.

The `opentelemetry` package is already installed as a dependency of the OTLP exporter — no new requirements needed.

### No impact on AgentCore telemetry

This fix only affects what LangChain sees as its parent context during our agent invocation. AgentCore's own span (the InvokeAgentRuntime wrapper) continues to exist and export to X-Ray. Our LangChain spans are now in a completely separate trace in Arize — which is exactly what we want.

---

## Verification

After deploying the fix (`terraform apply` → CodeBuild → runtime update), the test suite was run:

```
Ran 22 tests in 120s — OK
```

GraphQL query against Arize confirmed root spans:

```
=== Arize Span Breakdown (last 45 min, sample of 20) ===
  unique traces   : 13
  root spans      : 2  ← proper LangGraph roots (fix working!)
  in-Arize parent : 3
  orphan (~X-Ray) : 15

Root spans (waterfall-ready in Arize UI):
  ✓ [CHAIN] LangGraph  trace=ae89f9a8b3749140  latency=5370ms  status=OK
  ✓ [CHAIN] LangGraph  trace=221739b11508cea5  latency=3996ms  status=OK
```

The remaining orphaned spans in the sample window were from invocations that ran before the fix was live (they were correctly absent from the new root traces).

The Arize UI confirmed: clicking into a `LangGraph` root trace now shows the full waterfall with all child spans nested and timed correctly.

---

## Summary of all three fixes

By the end of this investigation, three separate AgentCore interference issues had been found and fixed:

| # | Problem | File changed | Fix |
|---|---|---|---|
| 1 | `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` routes spans to X-Ray | `tracing.py` | `os.environ.pop()` before constructing `OTLPSpanExporter` |
| 2 | AgentCore pre-instruments LangChain; re-instrumentation silently ignored | `tracing.py` | `uninstrument()` before `instrument(tracer_provider=arize_provider)` |
| 3 | LangChain spans inherit AgentCore's trace context; appear as orphaned children in Arize | `agentcore_entrypoint.py` | Wrap invocation with `otel_context.attach(otel_context.Context())` |

All three are required. Fix 1 and Fix 2 ensure spans reach Arize. Fix 3 ensures they form a coherent tree instead of dangling fragments.

---

## Key principle

AgentCore and your agent code share the same OTel SDK instance inside the container. This means:

- AgentCore's env vars affect your exporter configuration
- AgentCore's instrumentation state affects your re-instrumentation
- AgentCore's active span propagates into your LangChain calls

Each of these requires an explicit override. The OTel SDK was designed for single-owner scenarios; when two systems (AgentCore and your code) both try to own telemetry in the same process, you have to deliberately isolate yours.
