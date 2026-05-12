# Arize MCP Servers — Setup Guide

Three MCP (Model Context Protocol) servers give Claude Code direct access to Arize documentation, instrumentation help, and live trace/experiment data.

| Server | Purpose |
|---|---|
| `arize-tracing-assistant` | Live instrumentation help, span debugging, best practices, code examples |
| `arize-ax-docs` | Full-text search across all Arize AX documentation and API references |
| `phoenix` | Official Arize Phoenix MCP — traces, spans, datasets, experiments, prompts, annotations |

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

Run both commands from inside your project directory:

```bash
# Arize Tracing Assistant — instrumentation help and span debugging
claude mcp add arize-tracing-assistant uvx arize-tracing-assistant@latest

# Arize AX Docs — full documentation search
claude mcp add arize-ax-docs --transport http https://arize.com/docs/mcp
```

Both commands write to `.claude.json` in your project root (or `~/.claude.json` if using global scope). This file is project-scoped by default, meaning the servers are only active when working in this project.

### Phoenix MCP (official — replaces the custom arize-live-traces server)

```bash
claude mcp add phoenix -- npx -y @arizeai/phoenix-mcp@latest \
  --baseUrl https://app.phoenix.arize.com \
  --apiKey <your-arize-api-key>
```

The Phoenix API key is the same as your Arize API key (`ak-...`). This server provides tools for traces, spans, datasets, experiments, prompts, and annotations — a superset of the custom `arize-live-traces` server it replaces.

---

## Verifying the Setup

```bash
claude mcp list
```

Expected output:
```
arize-tracing-assistant: uvx arize-tracing-assistant@latest - ✓ Connected
arize-ax-docs: https://arize.com/docs/mcp (HTTP) - ✓ Connected
phoenix: npx -y @arizeai/phoenix-mcp@latest ... - ✓ Connected
```

If a server shows `✗ Failed` instead of `✓ Connected`:
- For `arize-tracing-assistant`: check that `uvx` is on your PATH (`which uvx`)
- For `arize-ax-docs`: check outbound HTTPS access to `arize.com`
- For `phoenix`: check that `npx` is available and your API key is valid

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

---

## Archived: Custom MCP Server — `arize-live-traces`

> **Deprecated (2026-05)**: This custom server has been replaced by the official `@arizeai/phoenix-mcp` server (the `phoenix` entry above), which provides broader functionality. The source is kept at [mcp/arize/server.py](../mcp/arize/server.py) as a reference for the Arize GraphQL API auth discovery (`x-api-key` header).

The custom server connected to `https://app.arize.com/graphql` and exposed 5 tools: `list_models`, `get_recent_traces`, `get_trace`, `get_stats`, `search_spans`. Auth discovery found that the only working header format was `x-api-key: <key>` (not `Authorization: Bearer`). The GraphQL schema used `node` → `Space` → `models` → `spanRecordsPublic` with `ModelDatasetInput`, and the environment name for OTLP traces was `tracing` (not `production`).

---

## Removing a Server

```bash
claude mcp remove arize-tracing-assistant
claude mcp remove arize-ax-docs
```

## Updating to the Latest Version

`arize-tracing-assistant` uses `@latest` so it always pulls the newest version when invoked. No manual update needed.

For the docs server (`arize-ax-docs`), it's an HTTP endpoint maintained by Arize — always current.
