# Arize Skills Evaluation Pipeline

This three-phase guide sets up a production evaluation pipeline for the Virtual Pet Store Agent using [Arize Skills](https://github.com/Arize-ai/arize-skills) and the `ax` CLI. By the end, the agent has automated LLM-as-judge evaluators running continuously on live traces, a curated golden dataset built from real production data, and a prompt optimization loop driven by evaluation scores.

## Why Arize Skills?

We already have tracing flowing to Arize (see [arize_traces.md](../arize_traces.md) through [arize_traces_3.md](../arize_traces_3.md)). The next step is to close the loop: use those traces to evaluate quality, catch regressions, and improve prompts --- all without leaving the CLI or Claude Code.

Arize Skills are pre-built instruction sets that give coding agents (Claude Code, Cursor, etc.) native knowledge of Arize workflows. Instead of explaining how to export traces or create evaluators from scratch, Claude can invoke skills like `arize-trace`, `arize-evaluator`, and `arize-experiment` directly.

## The Three Phases

| Phase | What it does | Key skills used |
|-------|-------------|-----------------|
| [Phase 1](phase-01-trace-to-dataset.md) | Export production traces, curate a golden dataset, set up annotation configs | `arize-trace`, `arize-dataset`, `arize-annotation` |
| [Phase 2](phase-02-evaluators-and-experiments.md) | Create LLM-as-judge evaluators, run experiments against the dataset, set up continuous monitoring | `arize-evaluator`, `arize-experiment`, `arize-ai-provider-integration` |
| [Phase 3](phase-03-prompt-optimization.md) | Analyze evaluation results, optimize the system prompt, validate improvements through A/B experiments | `arize-prompt-optimization`, `arize-experiment`, `arize-link` |

## Prerequisites

Before starting Phase 1, complete this setup:

### 1. Install the `ax` CLI

```bash
uv tool install arize-ax-cli
# or
pipx install arize-ax-cli
```

Verify:
```bash
ax --version
```

### 2. Configure authentication

```bash
ax profiles create --api-key <your-arize-api-key>
```

Or set environment variables:
```bash
export ARIZE_API_KEY="ak-..."
export ARIZE_SPACE="U3BhY2U6MTE0MzY6SmRmRA=="
```

Verify:
```bash
ax profiles show
```

### 3. Install Arize Skills into this project

```bash
cd /path/to/petstore-agentcore
npx skills add Arize-ai/arize-skills --skill '*' --yes
```

This installs all 10 skills into `.agents/skills/`:

| Skill | Purpose |
|-------|---------|
| `arize-trace` | Export and inspect traces/spans |
| `arize-dataset` | Create, version, and manage golden datasets |
| `arize-experiment` | Run experiments against datasets |
| `arize-evaluator` | Create LLM-as-judge evaluators |
| `arize-ai-provider-integration` | Configure LLM provider credentials for judges |
| `arize-annotation` | Set up annotation configs and queues |
| `arize-prompt-optimization` | Meta-prompt optimization using eval scores |
| `arize-link` | Generate deep links to Arize UI views |
| `arize-compliance-audit` | Audit tracing and eval coverage |
| `arize-instrumentation` | Add/verify OpenTelemetry instrumentation |

### 4. Confirm traces are flowing

The agent must already be sending traces to Arize. Verify:
```bash
ax traces export virtual-pet-store-agent --space "$ARIZE_SPACE" -l 5
```

If no traces appear, see [arize_traces.md](../arize_traces.md) for setup.

### 5. Confirm MCP servers (optional but recommended)

Claude Code should have the Arize MCP servers configured (see [arize_mcp.md](../arize_mcp.md)):
```bash
claude mcp list
# Should show: arize-tracing-assistant, arize-ax-docs, phoenix
```

The `phoenix` server (`@arizeai/phoenix-mcp`) provides direct access to traces, spans, datasets, experiments, prompts, and annotations from within Claude Code. It uses the same API key as Arize (`ARIZE_API_KEY` / `PHOENIX_API_KEY` are interchangeable for Arize-hosted Phoenix).

## Architecture

```
Live Agent Traffic
      |
      v
  Arize AX (traces + spans)
      |
      +-- Phase 1: Export traces --> curate golden dataset
      |
      +-- Phase 2: LLM-as-judge evaluators --> continuous monitoring
      |                                           |
      |                                    scores + annotations
      |                                           |
      +-- Phase 3: Prompt optimization <----------+
                       |
                       v
                 Improved system prompt
                       |
                       v
                 A/B experiment to validate
```
