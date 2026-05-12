#!/usr/bin/env python3
"""
Arize AX MCP Server — live trace data access via GraphQL API.

Gives Claude Code direct read access to spans, traces, and LLM stats
in the Arize AX space for the virtual-pet-store-agent project.

Environment variables:
  ARIZE_API_KEY     Your Arize API key  (required)
  ARIZE_SPACE_ID    Your Arize Space ID (required)
  ARIZE_MODEL_ID    GraphQL node ID of the model (optional, auto-discovered)
"""

import json
import os
from datetime import datetime, timedelta, timezone

import httpx
from mcp.server.fastmcp import FastMCP

# ── Config ────────────────────────────────────────────────────────────────────

API_KEY   = os.environ.get("ARIZE_API_KEY", "")
SPACE_ID  = os.environ.get("ARIZE_SPACE_ID", "")
GQL_URL   = "https://app.arize.com/graphql"
HEADERS   = {"x-api-key": API_KEY, "Content-Type": "application/json"}

mcp = FastMCP("arize-live-traces")

# ── GraphQL helper ─────────────────────────────────────────────────────────────

def gql(query: str, variables: dict | None = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = httpx.post(GQL_URL, headers=HEADERS, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return data["data"]


def _model_id() -> str:
    """Return the GraphQL node ID for the first model in the space."""
    override = os.environ.get("ARIZE_MODEL_ID")
    if override:
        return override
    data = gql(
        """query($spaceId: ID!) {
             node(id: $spaceId) {
               ... on Space {
                 models(first: 20) {
                   edges { node { id name } }
                 }
               }
             }
           }""",
        {"spaceId": SPACE_ID},
    )
    models = data["node"]["models"]["edges"]
    if not models:
        raise RuntimeError("No models found in Arize space")
    return models[0]["node"]["id"]


def _dataset_args(hours_back: int = 24, env: str = "tracing") -> dict:
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_back)
    return {
        "startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environmentName": env,
        "externalModelVersionIds": [],
        "externalBatchIds": [],
    }


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_models() -> str:
    """List all models (projects) in the Arize space with their IDs."""
    data = gql(
        """query($spaceId: ID!) {
             node(id: $spaceId) {
               ... on Space {
                 name
                 models(first: 50) {
                   edges { node { id name modelType createdAt } }
                 }
               }
             }
           }""",
        {"spaceId": SPACE_ID},
    )
    space = data["node"]
    results = [f"Space: {space['name']}\n"]
    for e in space["models"]["edges"]:
        m = e["node"]
        results.append(f"  - {m['name']}  type={m['modelType']}  id={m['id']}")
    return "\n".join(results)


@mcp.tool()
def get_recent_traces(hours_back: int = 24, limit: int = 20) -> str:
    """
    Get the most recent traces from the petstore agent.

    Args:
        hours_back: How many hours back to look (default 24)
        limit: Max number of spans to return (default 20)
    """
    model_id = _model_id()
    data = gql(
        """query($modelId: ID!, $dataset: ModelDatasetInput!, $first: Int!) {
             node(id: $modelId) {
               ... on Model {
                 spanRecordsPublic(first: $first, dataset: $dataset) {
                   edges {
                     node {
                       traceId spanId parentId name spanKind
                       statusCode startTime endTime latencyMs
                       traceTokenCounts { aggregateTotalTokenCount aggregatePromptTokenCount aggregateCompletionTokenCount }
                       totalCost { aggregateTotalCost }
                     }
                   }
                 }
               }
             }
           }""",
        {
            "modelId": model_id,
            "dataset": _dataset_args(hours_back),
            "first": limit,
        },
    )
    edges = data["node"]["spanRecordsPublic"]["edges"]
    if not edges:
        return f"No traces found in the last {hours_back} hours."

    # Group by traceId
    traces: dict[str, list] = {}
    for e in edges:
        s = e["node"]
        traces.setdefault(s["traceId"], []).append(s)

    lines = [f"Found {len(edges)} spans across {len(traces)} traces (last {hours_back}h)\n"]
    for trace_id, spans in traces.items():
        root = next((s for s in spans if not s["parentId"]), spans[0])
        tokens = root.get("traceTokenCounts") or {}
        lines.append(
            f"Trace {trace_id[:16]}..."
            f"\n  root_span : {root['name']}  kind={root['spanKind']}"
            f"\n  status    : {root['statusCode']}"
            f"\n  started   : {root['startTime']}"
            f"\n  latency   : {root['latencyMs']:.0f}ms"
            f"\n  tokens    : prompt={tokens.get('aggregatePromptTokenCount',0)} completion={tokens.get('aggregateCompletionTokenCount',0)} total={tokens.get('aggregateTotalTokenCount',0)}"
            f"\n  cost      : ${(root.get('totalCost') or {}).get('aggregateTotalCost') or 0:.4f}"
            f"\n  spans     : {len(spans)}"
        )
    return "\n\n".join(lines)


@mcp.tool()
def get_trace(trace_id: str, hours_back: int = 48) -> str:
    """
    Get all spans for a specific trace ID.

    Args:
        trace_id: The trace ID to look up
        hours_back: Search window in hours (default 48)
    """
    model_id = _model_id()
    data = gql(
        """query($modelId: ID!, $dataset: ModelDatasetInput!, $first: Int!) {
             node(id: $modelId) {
               ... on Model {
                 spanRecordsPublic(first: $first, dataset: $dataset) {
                   edges {
                     node {
                       traceId spanId parentId name spanKind
                       statusCode startTime latencyMs
                       attributes
                     }
                   }
                 }
               }
             }
           }""",
        {
            "modelId": model_id,
            "dataset": _dataset_args(hours_back),
            "first": 50,
        },
    )
    all_spans = [e["node"] for e in data["node"]["spanRecordsPublic"]["edges"]]
    spans = [s for s in all_spans if s["traceId"] == trace_id]

    if not spans:
        return f"No spans found for trace {trace_id} in the last {hours_back} hours."

    # Sort by startTime
    spans.sort(key=lambda s: s["startTime"])

    lines = [f"Trace {trace_id} — {len(spans)} spans\n"]
    for s in spans:
        indent = "  " if s["parentId"] else ""
        attrs = s.get("attributes") or {}
        input_val = attrs.get("input.value", "")
        output_val = attrs.get("output.value", "")
        lines.append(
            f"{indent}[{s['spanKind'] or 'SPAN'}] {s['name']}"
            f"\n{indent}  spanId  : {s['spanId']}"
            f"\n{indent}  status  : {s['statusCode']}"
            f"\n{indent}  latency : {s['latencyMs']:.0f}ms"
            f"\n{indent}  started : {s['startTime']}"
        )
        if input_val:
            lines.append(f"{indent}  input   : {str(input_val)[:200]}")
        if output_val:
            lines.append(f"{indent}  output  : {str(output_val)[:200]}")
    return "\n".join(lines)


@mcp.tool()
def get_stats(hours_back: int = 24) -> str:
    """
    Get LLM performance stats: latency, token counts, cost for the petstore agent.

    Args:
        hours_back: Time window in hours (default 24)
    """
    model_id = _model_id()
    ds = _dataset_args(hours_back)

    # Query stats and spans separately to stay under complexity limit
    stats_data = gql(
        """query($modelId: ID!, $dataset: ModelDatasetInput!, $timeZone: String!) {
             node(id: $modelId) {
               ... on Model {
                 llmTracingStats(dataset: $dataset, timeZone: $timeZone) {
                   latencyMsP50 latencyMsP99 tokenCountTotal costTotal
                 }
               }
             }
           }""",
        {"modelId": model_id, "dataset": ds, "timeZone": "UTC"},
    )
    span_data = gql(
        """query($modelId: ID!, $dataset: ModelDatasetInput!) {
             node(id: $modelId) {
               ... on Model {
                 spanRecordsPublic(first: 50, dataset: $dataset) {
                   edges { node { traceId statusCode spanKind } }
                 }
               }
             }
           }""",
        {"modelId": model_id, "dataset": ds},
    )

    stats = stats_data["node"].get("llmTracingStats") or {}
    spans = [e["node"] for e in span_data["node"]["spanRecordsPublic"]["edges"]]

    trace_ids = set(s["traceId"] for s in spans)
    errors = [s for s in spans if s["statusCode"] == "ERROR"]

    return (
        f"Stats for last {hours_back}h\n"
        f"  traces       : {len(trace_ids)}\n"
        f"  total spans  : {len(spans)}\n"
        f"  errors       : {len(errors)}\n"
        f"  latency p50  : {stats.get('latencyMsP50', 'n/a')}ms\n"
        f"  latency p99  : {stats.get('latencyMsP99', 'n/a')}ms\n"
        f"  total tokens : {stats.get('tokenCountTotal', 'n/a')}\n"
        f"  total cost   : ${stats.get('costTotal') or 0:.4f}"
    )


@mcp.tool()
def search_spans(name: str = "", kind: str = "", status: str = "", hours_back: int = 24) -> str:
    """
    Search spans by name, kind, or status code.

    Args:
        name: Filter by span name (partial match, case-insensitive)
        kind: Filter by span kind e.g. LLM, CHAIN, TOOL, AGENT
        status: Filter by status code e.g. OK, ERROR, UNSET
        hours_back: Search window in hours (default 24)
    """
    model_id = _model_id()
    data = gql(
        """query($modelId: ID!, $dataset: ModelDatasetInput!) {
             node(id: $modelId) {
               ... on Model {
                 spanRecordsPublic(first: 50, dataset: $dataset) {
                   edges {
                     node {
                       traceId spanId name spanKind statusCode startTime latencyMs
                     }
                   }
                 }
               }
             }
           }""",
        {"modelId": model_id, "dataset": _dataset_args(hours_back)},
    )
    spans = [e["node"] for e in data["node"]["spanRecordsPublic"]["edges"]]

    if name:
        spans = [s for s in spans if name.lower() in (s["name"] or "").lower()]
    if kind:
        spans = [s for s in spans if kind.upper() == (s["spanKind"] or "").upper()]
    if status:
        spans = [s for s in spans if status.upper() == (s["statusCode"] or "").upper()]

    if not spans:
        return f"No spans found matching name={name!r} kind={kind!r} status={status!r}"

    lines = [f"Found {len(spans)} matching spans:\n"]
    for s in spans[:50]:
        lines.append(
            f"  [{s['spanKind'] or '?'}] {s['name']}  "
            f"status={s['statusCode']}  latency={s['latencyMs']:.0f}ms  "
            f"trace={s['traceId'][:12]}...  started={s['startTime']}"
        )
    if len(spans) > 50:
        lines.append(f"\n  ... and {len(spans) - 50} more")
    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not API_KEY or not SPACE_ID:
        raise SystemExit("ARIZE_API_KEY and ARIZE_SPACE_ID must be set")
    mcp.run()
