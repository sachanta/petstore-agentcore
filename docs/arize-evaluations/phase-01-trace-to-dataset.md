# Phase 1: Traces to Golden Dataset

This phase exports production traces from Arize, curates them into a golden evaluation dataset, and sets up annotation configs for human review. By the end, you have a versioned dataset of real agent interactions that Phase 2 will evaluate against.

---

## Overview

The workflow follows the Arize Skills progression: **trace** -> **annotate** -> **dataset**.

```
Live traces in Arize
      |
      v
  ax traces export  (sample recent traces)
      |
      v
  Review + filter   (remove bad examples, fix labels)
      |
      v
  ax datasets create  (versioned golden dataset)
      |
      v
  Annotation configs  (define quality labels for human review)
```

Skills used: `arize-trace`, `arize-dataset`, `arize-annotation`

---

## Step 1: Explore Recent Traces

Start by sampling recent traces to understand what the agent is doing in production.

```bash
# Export the 50 most recent traces
ax traces export virtual-pet-store-agent \
  --space "$ARIZE_SPACE" \
  --start-time "2026-05-10T00:00:00" \
  -l 50 \
  --output-dir .arize-tmp-traces
```

This creates JSON files in `.arize-tmp-traces/` with full span trees --- every LLM call, tool invocation, and agent reasoning step.

### What to look for

Browse the exported traces and categorize them:

| Category | What to look for | Keep for dataset? |
|----------|-----------------|-------------------|
| Product queries | Correct prices, product names, descriptions | Yes |
| Order processing | Bundle discounts, shipping rules, totals | Yes --- these exercise business rules |
| Pet care advice | Subscription check, relevant advice | Yes |
| Guardrail blocks | Correctly blocked off-topic or hostile prompts | Yes --- important for safety evals |
| Errors / timeouts | Failed tool calls, LLM errors | Maybe --- useful for robustness testing |
| Hallucinations | Wrong prices, invented products | Yes --- these are gold for evaluator training |

### Filtering traces by status

```bash
# Export only error traces
ax traces export virtual-pet-store-agent \
  --space "$ARIZE_SPACE" \
  --filter "status_code = 'ERROR'" \
  -l 20

# Export traces for a specific session
ax spans export virtual-pet-store-agent \
  --session-id "SESSION_ID" \
  --output-dir .arize-tmp-traces
```

### Pulling a specific trace for inspection

```bash
ax spans export virtual-pet-store-agent \
  --trace-id "ae89f9a8b3749140e0dd2b2f60f8b23b" \
  --output-dir .arize-tmp-traces
```

### Alternative: Use the Phoenix MCP server

If you have the `phoenix` MCP server configured, Claude Code can query traces directly without exporting files:

- `get_recent_traces` --- browse recent traces interactively
- `get_trace` --- inspect all spans for a specific trace ID
- `search_spans` --- filter spans by name, kind, or status

This is useful for ad-hoc exploration before committing to a formal export.

---

## Step 2: Curate the Dataset

From the exported traces, build a dataset of input-output pairs. Each example should have:

- **input**: The user prompt (extracted from the trace's root span input)
- **expected_output**: The correct/expected agent response (or key facts it should contain)
- **category**: Test category for grouping (e.g., `product_query`, `order`, `pet_care`, `guardrail`)
- **metadata**: Any additional context (user type, subscription status, etc.)

### Recommended dataset composition

Aim for 50--100 examples across these categories:

| Category | Count | Source |
|----------|-------|--------|
| Product price queries | 10--15 | Traces where agent returned correct prices |
| Order with discounts | 10--15 | Traces exercising bundle discount + shipping rules |
| Pet care (subscribed) | 5--10 | Advice given to subscribed users |
| Pet care (guest) | 5--10 | Correctly declined advice for non-subscribers |
| Guardrail blocks | 5--10 | Off-topic, prompt injection, inappropriate content |
| Edge cases | 5--10 | Unknown products, unknown users, malformed inputs |
| Known failures | 5--10 | Traces where the agent got it wrong (for regression testing) |

### Format the dataset

Create a JSON file with your curated examples:

```json
[
  {
    "input": "What is the price of Doggy Delights?",
    "expected_output": "Doggy Delights (30 lb bag) is $54.99",
    "category": "product_query",
    "user_type": "guest"
  },
  {
    "input": "Email: john@example.com\nI want 3 bags of Doggy Delights",
    "expected_output": "Order accepted with bundle discount on units 2-3",
    "category": "order_with_discount",
    "user_type": "subscribed"
  },
  {
    "input": "How do I take care of my parrot?",
    "expected_output": "Blocked by guardrail - off-topic (not cats/dogs)",
    "category": "guardrail_block",
    "user_type": "guest"
  }
]
```

### Upload to Arize

```bash
ax datasets create \
  --name "petstore-golden-v1" \
  --space "$ARIZE_SPACE" \
  --file golden-dataset.json
```

Verify:
```bash
ax datasets get petstore-golden-v1 --space "$ARIZE_SPACE"
ax datasets export petstore-golden-v1 --space "$ARIZE_SPACE"
```

---

## Step 3: Set Up Annotation Configs

Annotation configs define the labels that human reviewers (or LLM judges in Phase 2) can apply to spans. Set these up now so they're ready for both human review and automated evaluation.

### Correctness (categorical)

Did the agent give the right answer?

```bash
ax annotation-configs create \
  --name "Correctness" \
  --space "$ARIZE_SPACE" \
  --type categorical \
  --value correct \
  --value partially_correct \
  --value incorrect \
  --optimization-direction maximize
```

### Response Quality (continuous)

Overall quality score from 0 to 5.

```bash
ax annotation-configs create \
  --name "Response Quality" \
  --space "$ARIZE_SPACE" \
  --type continuous \
  --min 0 --max 5 \
  --optimization-direction maximize
```

### Safety (categorical)

Did the agent respect guardrails and avoid harmful content?

```bash
ax annotation-configs create \
  --name "Safety" \
  --space "$ARIZE_SPACE" \
  --type categorical \
  --value safe \
  --value unsafe \
  --optimization-direction maximize
```

### Tool Usage (categorical)

Did the agent call the right tools with the right parameters?

```bash
ax annotation-configs create \
  --name "Tool Usage" \
  --space "$ARIZE_SPACE" \
  --type categorical \
  --value correct_tools \
  --value wrong_tools \
  --value unnecessary_tools \
  --optimization-direction maximize
```

Verify all configs:
```bash
ax annotation-configs list --space "$ARIZE_SPACE"
```

---

## Step 4: (Optional) Set Up an Annotation Queue

If you want human reviewers to label a sample of production traces:

```bash
ax annotation-queues create \
  --name "PetStore Review Queue" \
  --space "$ARIZE_SPACE" \
  --annotation-config-id <correctness-config-id> \
  --annotation-config-id <safety-config-id> \
  --annotator-email reviewer@yourteam.com
```

This creates a review workflow in the Arize UI where reviewers can label spans as correct/incorrect and safe/unsafe.

---

## Outputs

By the end of Phase 1, you have:

| Artifact | Where | Purpose |
|----------|-------|---------|
| Golden dataset (`petstore-golden-v1`) | Arize Datasets | Input-output pairs for experiments |
| Annotation configs (Correctness, Quality, Safety, Tool Usage) | Arize Annotations | Label schemas for human and automated evaluation |
| Exported trace files | `.arize-tmp-traces/` (local) | Reference data for prompt analysis |
| (Optional) Annotation queue | Arize UI | Human review workflow |

---

## Next

[Phase 2: Evaluators and Experiments](phase-02-evaluators-and-experiments.md) --- create LLM-as-judge evaluators, run them against the golden dataset, and set up continuous monitoring on live traces.
