# Arize AX Tracing — Setup & Troubleshooting

Traces every LLM call, tool invocation, and ReAct reasoning step from the PetStore AgentCore agent and sends them to [app.arize.com](https://app.arize.com) under the project `virtual-pet-store-agent`.

---

## Configuration

### 1. Arize credentials

Create `terraform/.env` (gitignored):

```
TF_VAR_arize_space_id=<your-space-id>
TF_VAR_arize_api_key=<your-api-key>
TF_VAR_arize_project_name=virtual-pet-store-agent
```

Find your Space ID and API key at [app.arize.com](https://app.arize.com) → Settings → API Keys.

### 2. Deploy

```bash
cd terraform
make apply
```

Terraform passes `ARIZE_SPACE_ID`, `ARIZE_API_KEY`, and `ARIZE_PROJECT_NAME` as environment variables to the AgentCore Runtime container. The `arize_api_key_hash` trigger in `agent_runtime/main.tf` ensures the runtime redeploys whenever the key changes.

### 3. Agent code

| File | Role |
|---|---|
| `pet_store_agent/tracing.py` | Sets up the Arize OTLP/HTTP exporter and instruments LangChain |
| `pet_store_agent/agentcore_entrypoint.py` | Calls `setup_tracing()` once at startup |
| `pet_store_agent/requirements.txt` | Adds `arize-otel`, `openinference-instrumentation-langchain`, `opentelemetry-exporter-otlp-proto-http` |

### 4. How it works

`setup_tracing()` in `tracing.py`:

1. Creates a dedicated `TracerProvider` (separate from AgentCore's own provider)
2. Adds an `_ArizeProjectProcessor` that stamps every span with `arize.project.name`
3. Adds a `BatchSpanProcessor` with an OTLP/HTTP exporter pointing to `https://otlp.arize.com/v1/traces`
4. Instruments LangChain via `LangChainInstrumentor().instrument(tracer_provider=arize_provider)`

---

## Issues & Fixes

### Issue 1: `tracing.py` not in CodeBuild hash trigger

**Symptom:** `make apply` completed but CloudWatch still showed old log messages — the container image was never rebuilt after `tracing.py` was created.

**Root cause:** `terraform/modules/agent_image/main.tf` computes `agent_code_hash` from a list of `filesha256()` calls. `tracing.py` was missing from the list so no hash change was detected.

**Fix:** Added `tracing.py` to the hash list:
```hcl
filesha256("${path.root}/../pet_store_agent/tracing.py"),
```

---

### Issue 2: "Tracing already initialised — skipping"

**Symptom:** CloudWatch showed this log message. No spans were sent.

**Root cause:** AgentCore Runtime pre-initialises its own `TracerProvider` via `OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true`. The original code checked `isinstance(provider, TracerProvider)` and exited early when it found one already set.

**Fix:** Instead of creating a new global provider, we create a **dedicated** `TracerProvider` for Arize only and pass it directly to `LangChainInstrumentor().instrument(tracer_provider=arize_provider)`. This leaves AgentCore's provider untouched.

---

### Issue 3: `StatusCode.UNKNOWN` on export (gRPC blocked)

**Symptom:** `Failed to export traces to otlp.arize.com, error code: StatusCode.UNKNOWN`

**Root cause:** The original exporter used `opentelemetry-exporter-otlp-proto-grpc`, which sends spans over gRPC/HTTP2. The AgentCore container's VPC blocks or mangles gRPC traffic — the request never reached Arize's server.

**Fix:** Switched to `opentelemetry-exporter-otlp-proto-http` which sends spans as protobuf over plain HTTPS. Port 443 HTTPS is universally allowed outbound.

```python
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

exporter = OTLPSpanExporter(
    endpoint="https://otlp.arize.com/v1/traces",
    ...
)
```

---

### Issue 4: HTTP 500 — wrong auth header

**Symptom:** `Transient error Internal Server Error encountered while exporting span batch`

**Root cause:** The exporter headers used `"api_key": api_key` (copied from the gRPC Arize SDK pattern). The Arize HTTP OTLP endpoint expects `Authorization: Bearer <key>`.

**Fix:**
```python
headers={
    "authorization": f"Bearer {api_key}",
    "space_id": space_id,
}
```

---

### Issue 5: HTTP 500 — missing `arize.project.name` span attribute

**Symptom:** Same 500 error persisted after fixing the auth header. Full error from a local test:
```
rpc error: code = InvalidArgument desc = model_id span resource attribute
or arize.project.name span attribute is required
```

**Root cause:** Arize requires `arize.project.name` to be set as a **span attribute** on every span (not as a resource attribute on the provider, and not just as an HTTP header).

**Fix:** Added a `SpanProcessor` that stamps every span automatically on start:
```python
class _ArizeProjectProcessor(SpanProcessor):
    def on_start(self, span, parent_context=None):
        span.set_attribute("arize.project.name", project_name)
    def on_end(self, span): pass
    def shutdown(self): pass
    def force_flush(self, timeout_millis=30000): return True
```

---

### Issue 6: Runtime not redeploying after image rebuild

**Symptom:** After `make apply` rebuilt the Docker image, the running container still used the old image. CloudWatch showed old log messages.

**Root cause:** The `agent_runtime` `null_resource` triggers on `ecr_image_uri`, which is always `repo:latest` — the tag never changes, so Terraform sees no diff and skips the runtime redeploy.

**Fix (short-term):** `terraform taint module.agent_runtime.null_resource.agent_runtime` forces a redeploy on the next `make apply`.

**Fix (permanent):** Wired `agent_code_hash` from `agent_image` through to `agent_runtime` triggers. Now whenever the image is rebuilt (source files change), the runtime automatically redeploys:
- `agent_image/outputs.tf` — exports `agent_code_hash`
- `agent_runtime/variables.tf` — accepts `agent_code_hash`
- `agent_runtime/main.tf` — adds it to triggers
- `main.tf` — passes `module.agent_image.agent_code_hash` to the runtime module

---

### Issue 7: New runtime ARN after each redeploy

**Symptom:** `ResourceNotFoundException` when invoking — the runtime suffix changes on every redeploy (e.g. `LangGraphAgentCoreRuntime-dEgatWFDLE` → `LangGraphAgentCoreRuntime-TXH9fmG3mz`).

**Root cause:** AgentCore generates a new random suffix each time a runtime is created.

**Workaround:** After any full redeploy, get the new ARN and update `ui/.env`:
```bash
terraform -chdir=terraform output agent_runtime_arn
# then update ui/.env RUNTIME_ARN=...
```
