# Arize MCP Servers — Setup Guide

Three MCP (Model Context Protocol) servers give Claude Code direct access to Arize documentation, instrumentation help, and live trace data.

| Server | Purpose |
|---|---|
| `arize-tracing-assistant` | Live instrumentation help, span debugging, best practices, code examples |
| `arize-ax-docs` | Full-text search across all Arize AX documentation and API references |
| `arize-live-traces` | **Custom** — live read access to actual trace data via Arize GraphQL API (`app.arize.com`) |

---

## Prerequisites

### 1. Install `uv` / `uvx`

`arize-tracing-assistant` runs via `uvx`, which is part of the `uv` Python package manager. It does **not** require sudo.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

`uv` and `uvx` are installed to `~/.local/bin`. Add to your PATH if not already there:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

To make it permanent, add that line to your `~/.bashrc` or `~/.zshrc`.

Verify:
```bash
uvx --version
```

### 2. Claude Code CLI

You need Claude Code installed and accessible as the `claude` command. These servers are added to your Claude Code project config, not globally.

---

## Adding the MCP Servers

Run all three commands from inside your project directory:

```bash
# Arize Tracing Assistant — instrumentation help and span debugging
claude mcp add arize-tracing-assistant uvx arize-tracing-assistant@latest

# Arize AX Docs — full documentation search
claude mcp add arize-ax-docs --transport http https://arize.com/docs/mcp
```

Both commands write to `.claude.json` in your project root (or `~/.claude.json` if using global scope). This file is project-scoped by default, meaning the servers are only active when working in this project.

---

## Verifying the Setup

```bash
claude mcp list
```

Expected output:
```
arize-tracing-assistant: uvx arize-tracing-assistant@latest - ✓ Connected
arize-ax-docs: https://arize.com/docs/mcp (HTTP) - ✓ Connected
arize-live-traces: python3 .../mcp/arize/server.py ... - ✓ Connected
```

If a server shows `✗ Failed` instead of `✓ Connected`:
- For `arize-tracing-assistant`: check that `uvx` is on your PATH (`which uvx`)
- For `arize-ax-docs`: check outbound HTTPS access to `arize.com`
- For `arize-live-traces`: check that `ARIZE_API_KEY` and `ARIZE_SPACE_ID` are correct

---

## How Claude Uses These Servers

Once connected, Claude can invoke these servers automatically when working on tracing issues. No special command needed — Claude will use them when relevant.

**What `arize-tracing-assistant` can help with:**
- Correct instrumentation patterns for LangChain, LangGraph, and other frameworks
- Debugging why spans aren't appearing in Arize AX
- Setting required span attributes (`arize.project.name`, `model_id`, etc.)
- Manual instrumentation with decorators
- Context propagation across tool calls
- Sensitive data redaction from spans

**What `arize-ax-docs` can help with:**
- Looking up any Arize AX API reference
- Finding configuration options for OTLP exporters
- Searching for specific integration guides (e.g. AgentCore, Bedrock)
- Offline evaluation setup, prompt learning, dataset configuration

---

## Why This Was Added

During the AgentCore tracing setup (documented in [arize_traces.md](arize_traces.md) and [arize_traces_3.md](arize_traces_3.md)), debugging required multiple rounds of copy-pasting error messages to Arize support and relaying answers back. With these MCP servers, Claude can:

1. Query `arize-ax-docs` to look up the correct OTLP header format
2. Ask `arize-tracing-assistant` about AgentCore-specific instrumentation issues
3. Get answers inline without interrupting your workflow

---

## Custom MCP Server — `arize-live-traces`

This is a custom MCP server built specifically for this project. It connects directly to the Arize GraphQL API (`https://app.arize.com/graphql`) using `x-api-key` authentication and exposes five tools:

| Tool | What it does |
|---|---|
| `list_models` | Lists all models/projects in the Arize space |
| `get_recent_traces` | Returns recent traces with latency, tokens, cost grouped by trace ID |
| `get_trace` | Returns all spans for a specific trace ID in tree order |
| `get_stats` | Returns aggregate stats: p50/p99 latency, total tokens, total cost, error count |
| `search_spans` | Filters spans by name, kind (LLM/CHAIN/TOOL/AGENT), or status (OK/ERROR) |

### Source

[mcp/arize/server.py](../mcp/arize/server.py) — built with `mcp[cli]` + `httpx`.

### Auth discovery

During setup, several auth header formats were tried against `https://app.arize.com/graphql`:
- `Authorization: Bearer <key>` → 401 Unauthorized
- `space_id` + `api_key` headers → 401 Unauthorized
- `x-api-key: <key>` → ✓ 200 OK

The GraphQL schema was introspected live to discover the correct query structure (`node` → `Space` → `models` → `spanRecordsPublic` with `ModelDatasetInput`). The environment name for OTLP traces is `tracing` (not `production`).

### Adding the custom server

```bash
claude mcp add arize-live-traces \
  python3 /path/to/petstore-agentcore/mcp/arize/server.py \
  -e ARIZE_API_KEY=<your-key> \
  -e ARIZE_SPACE_ID=<your-space-id>
```

---

## Removing a Server

```bash
claude mcp remove arize-tracing-assistant
claude mcp remove arize-ax-docs
claude mcp remove arize-live-traces
```

## Updating to the Latest Version

`arize-tracing-assistant` uses `@latest` so it always pulls the newest version when invoked. No manual update needed.

For the docs server (`arize-ax-docs`), it's an HTTP endpoint maintained by Arize — always current.

For `arize-live-traces`, update the source at `mcp/arize/server.py` directly.
