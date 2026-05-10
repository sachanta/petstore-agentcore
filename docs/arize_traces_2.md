# Arize AX Tracing — Deep Dive: AgentCore Runtime Interference

This document covers the advanced debugging session that followed the initial setup in [arize_traces.md](arize_traces.md). It documents two critical discoveries about how AgentCore Runtime's internal telemetry pipeline conflicts with custom OTLP exporters, and the exact fixes applied.

---

## Context

After completing the setup in [arize_traces.md](arize_traces.md) — correct auth headers, correct span attributes, HTTP instead of gRPC — spans still weren't appearing in Arize AX. CloudWatch logs showed:

```
Connection aborted. ConnectionAbortedError(103, 'Software caused connection abort')
```

and earlier:

```
Transient error Internal Server Error encountered while exporting span batch
```

The code was verified correct by running the same exporter locally (this EC2 machine) and confirming spans landed in Arize. The container environment was doing something different.

---

## Discovery 1: AgentCore hijacks the OTLP traces endpoint via environment variable

### What we found

Added a diagnostic block to `tracing.py` to log all OTEL-related environment variables at startup:

```python
for var in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            "OTEL_EXPORTER_OTLP_PROTOCOL", "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"):
    logger.info("  %s=%s", var, os.environ.get(var, "<not set>"))
```

CloudWatch output from inside the container:

```
OTEL_EXPORTER_OTLP_ENDPOINT=<not set>
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://xray.us-east-1.amazonaws.com/v1/traces
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=<not set>
```

### Why this matters

`OTLPSpanExporter` from the OpenTelemetry Python SDK reads environment variables at construction time. Specifically, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` **overrides** any `endpoint=` argument passed in code. This is by design in the OTel spec — env vars take precedence.

So even though our code said:
```python
OTLPSpanExporter(endpoint="https://otlp.arize.com/v1/traces", ...)
```

The SDK silently sent every span to `https://xray.us-east-1.amazonaws.com/v1/traces` (AWS X-Ray) instead. The `Connection aborted (103)` errors were X-Ray rejecting our Arize-formatted payloads, or the connection being terminated because our auth headers weren't valid for X-Ray.

### The runtime network mode is PUBLIC

A key finding during this investigation: the AgentCore runtime is deployed with `networkMode: PUBLIC`. This rules out VPC security groups, NAT gateways, or subnet egress rules as the cause. The container has direct internet access — the problem was 100% the env var redirect to X-Ray.

### Fix

Unset the conflicting env vars **before** constructing `OTLPSpanExporter`:

```python
# AgentCore sets OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://xray.us-east-1.amazonaws.com/v1/traces
# which overrides our explicit endpoint, routing spans to X-Ray instead of Arize.
# We must unset it before constructing OTLPSpanExporter.
os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
os.environ.pop("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", None)
```

This does **not** break AgentCore's own telemetry — AgentCore's exporter was already constructed at startup before our code runs. Unsetting the env var only prevents our exporter from being misconfigured.

---

## Discovery 2: AgentCore auto-instruments LangChain before user code runs

### What we found

Even after fixing the endpoint redirect, no spans appeared in Arize. CloudWatch logs still showed:

```
Attempting to instrument while already instrumented
```

This warning comes from `openinference-instrumentation-langchain`. When `LangChainInstrumentor().instrument()` is called and LangChain is already instrumented, the call is **silently ignored** — no re-instrumentation happens, and no `tracer_provider` argument is applied.

### Why this happens

AgentCore Runtime uses `OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true` and its own auto-instrumentation bootstrap. As part of that bootstrap, it calls `LangChainInstrumentor().instrument()` with its own `TracerProvider` (which routes spans to X-Ray via the env var above). This happens before `agentcore_entrypoint.py` is loaded.

So when our `setup_tracing()` later calls:
```python
LangChainInstrumentor().instrument(tracer_provider=arize_provider)
```

The instrumentor detects it's already active and skips the call entirely. LangChain continues sending spans to AgentCore's X-Ray provider. Our `arize_provider` receives nothing.

### Fix

Explicitly uninstrument first, then re-instrument with our provider:

```python
instrumentor = LangChainInstrumentor()
if instrumentor.is_instrumented_by_opentelemetry:
    instrumentor.uninstrument()
instrumentor.instrument(tracer_provider=arize_provider)
```

`uninstrument()` removes all LangChain patches. `instrument(tracer_provider=arize_provider)` then re-applies them routing to Arize. AgentCore's X-Ray telemetry for LangChain calls is lost at this point, but AgentCore's own infrastructure spans (invocation start/end, etc.) continue working since those are instrumented separately.

---

## Final working tracing.py

```python
import logging
import os

logger = logging.getLogger(__name__)
_tracing_initialised = False


def setup_tracing() -> None:
    global _tracing_initialised
    if _tracing_initialised:
        return
    _tracing_initialised = True

    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from opentelemetry.sdk.trace import TracerProvider, SpanProcessor
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    except ImportError as e:
        logger.warning("Tracing packages not installed — skipping. (%s)", e)
        return

    space_id     = os.environ.get("ARIZE_SPACE_ID", "")
    api_key      = os.environ.get("ARIZE_API_KEY", "")
    project_name = os.environ.get("ARIZE_PROJECT_NAME", "virtual-pet-store-agent")

    if not space_id or not api_key:
        logger.warning("ARIZE_SPACE_ID or ARIZE_API_KEY not set — tracing disabled.")
        return

    class _ArizeProjectProcessor(SpanProcessor):
        """Stamps every span with arize.project.name so Arize routes it correctly."""
        def on_start(self, span, parent_context=None):
            span.set_attribute("arize.project.name", project_name)
        def on_end(self, span): pass
        def shutdown(self): pass
        def force_flush(self, timeout_millis=30000): return True

    # Fix 1: Clear AgentCore's X-Ray endpoint override before constructing exporter
    os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    os.environ.pop("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", None)

    arize_exporter = OTLPSpanExporter(
        endpoint="https://otlp.arize.com/v1/traces",
        headers={
            "authorization": f"Bearer {api_key}",
            "space_id": space_id,
        },
    )

    arize_provider = TracerProvider()
    arize_provider.add_span_processor(_ArizeProjectProcessor())
    arize_provider.add_span_processor(BatchSpanProcessor(arize_exporter))

    # Fix 2: Uninstrument AgentCore's prior LangChain instrumentation before applying ours
    instrumentor = LangChainInstrumentor()
    if instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.uninstrument()
    instrumentor.instrument(tracer_provider=arize_provider)

    logger.info("Arize AX tracing enabled (project: %s)", project_name)
```

---

## Diagnostic method — how to reproduce these findings

If you encounter similar issues in the future, add this block early in `setup_tracing()` and redeploy:

```python
# Dump all OTEL env vars inside the container
import os, logging
logger = logging.getLogger(__name__)
for k, v in os.environ.items():
    if k.startswith("OTEL_"):
        logger.info("ENV %s=%s", k, v)
```

Then check CloudWatch:
```bash
aws logs filter-log-events \
  --log-group-name "/aws/bedrock-agentcore/runtimes/<RUNTIME_ID>-DEFAULT" \
  --filter-pattern "ENV OTEL" \
  --start-time $(date -d '5 minutes ago' +%s000) \
  --region us-east-1 \
  --query 'events[].message' --output text
```

---

## AgentCore telemetry environment — summary

Based on this investigation, AgentCore Runtime (PUBLIC network mode, `us-east-1`) sets the following at container startup, before user code runs:

| Environment Variable | Value | Effect |
|---|---|---|
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `https://xray.us-east-1.amazonaws.com/v1/traces` | Redirects all OTLP span exports to X-Ray |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | Forces HTTP/protobuf (not gRPC) |
| `OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED` | `true` | Auto-instruments logging and LangChain |

AgentCore also calls `LangChainInstrumentor().instrument()` automatically as part of its bootstrap, routing LangChain spans to its own X-Ray TracerProvider.

---

## Key takeaways for future custom OTLP exporters in AgentCore

1. **Never rely on `OTEL_EXPORTER_OTLP_*` env vars** — AgentCore sets them to point at X-Ray. Always `os.environ.pop()` them before constructing your exporter.
2. **Always uninstrument before re-instrumenting** — AgentCore auto-instruments LangChain. Any `instrument()` call after that is silently ignored unless you call `uninstrument()` first.
3. **Use HTTP, not gRPC** — `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` is set by AgentCore. More importantly, gRPC connections to external endpoints were unreliable in the container environment.
4. **Use a dedicated `TracerProvider`** — Don't try to add to AgentCore's provider. It's locked and shared. Create your own isolated provider and pass it explicitly to `instrument()`.
5. **`arize.project.name` must be a span attribute** — Setting it as a resource attribute on the provider is not enough. Arize requires it on each individual span. Use a `SpanProcessor.on_start()` to stamp it automatically.
