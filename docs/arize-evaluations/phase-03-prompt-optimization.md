# Phase 3: Prompt Optimization

This phase closes the evaluation loop. Using the scores and failure patterns from Phase 2, you extract the current system prompt from traces, identify weaknesses, generate an improved prompt via meta-prompting, and validate the improvement through an A/B experiment.

---

## Overview

```
Evaluation scores (Phase 2)
      |
      v
  Extract current prompt   (from LLM span attributes)
      |
      v
  Analyze failure patterns (low scores, wrong labels, regressions)
      |
      v
  Meta-prompt optimization (LLM rewrites the system prompt)
      |
      v
  A/B experiment           (original vs. optimized prompt)
      |
      v
  Compare & deploy         (if improved, update pet_store_agent.py)
```

Skills used: `arize-prompt-optimization`, `arize-experiment`, `arize-link`

---

## Step 1: Extract the Current Prompt

The agent's system prompt lives in `pet_store_agent.py` as the `SYSTEM_PROMPT` variable. But in production, the actual prompt sent to the LLM includes additional context from tool calls and conversation history. Extract what the LLM actually sees from trace data.

### Export recent LLM spans

```bash
ax spans export virtual-pet-store-agent \
  --space "$ARIZE_SPACE" \
  --output-dir .arize-tmp-traces \
  -l 20
```

### Locate the prompt in span attributes

The system prompt appears in `attributes.llm.input_messages` on spans with `span_kind = LLM`. Look for the `system` role message:

```bash
# Extract system prompts from exported spans
cat .arize-tmp-traces/*.json | python3 -c "
import json, sys
for line in sys.stdin:
    span = json.loads(line)
    msgs = span.get('attributes', {}).get('llm.input_messages', [])
    for m in msgs:
        if m.get('message', {}).get('role') == 'system':
            print(m['message']['content'][:200])
            print('---')
            break
" | head -50
```

Save the current system prompt to a file for reference:

```bash
# Copy directly from source
grep -A 200 'SYSTEM_PROMPT' pet_store_agent/pet_store_agent.py > current-prompt.txt
```

---

## Step 2: Analyze Failure Patterns

Pull the evaluation results from Phase 2 and identify where the agent consistently fails.

### Export experiment results

```bash
ax experiments export petstore-baseline-v1 \
  --space "$ARIZE_SPACE" > baseline-results.json
```

### Find failure patterns

```python
#!/usr/bin/env python3
"""Analyze evaluation failures to identify prompt improvement areas."""
import json

with open("baseline-results.json") as f:
    runs = json.load(f)

failures = []
for run in runs:
    for ev in run.get("evaluations", []):
        if ev.get("label") in ("incorrect", "unsafe", "wrong_tools"):
            failures.append({
                "input": run.get("input", ""),
                "output": run.get("output", "")[:200],
                "evaluator": ev.get("name"),
                "label": ev.get("label"),
                "explanation": ev.get("explanation", ""),
            })

print(f"Total failures: {len(failures)}")
print()
for f in failures:
    print(f"[{f['evaluator']}] {f['label']}")
    print(f"  Input: {f['input'][:100]}")
    print(f"  Explanation: {f['explanation'][:200]}")
    print()
```

### Common failure categories for the pet store agent

| Pattern | Example | Prompt fix |
|---------|---------|------------|
| Wrong prices | Agent hallucinates a price not in the knowledge base | Add instruction: "Always retrieve prices from the product knowledge base. Never guess prices." |
| Discount miscalculation | Agent applies discount logic inconsistently | Add explicit discount rules to system prompt (though business rules are also enforced server-side) |
| Pet care to guests | Agent gives pet care advice without checking subscription | Strengthen the subscription check instruction |
| Off-topic leakage | Agent partially answers a blocked topic before the guardrail fires | Add instruction: "If a topic is outside cats and dogs, decline immediately without providing partial information." |
| Unnecessary tool calls | Agent calls get_user_by_id when no user info is provided | Add instruction: "Only call user lookup tools when the user provides an email or user ID." |

---

## Step 3: Generate an Optimized Prompt

Use meta-prompting: feed the current prompt plus failure data to an LLM and ask it to produce an improved version.

### The meta-prompt template

This follows the Arize prompt optimization methodology --- provide the original prompt, performance data with inputs/outputs/evaluations, and rules against overfitting:

```
You are a prompt engineer optimizing a system prompt for an AI pet store agent.

## Current System Prompt
{current_prompt}

## Performance Data
Below are examples where the agent performed poorly, along with evaluator explanations:

{failure_records}

## Rules
- DO NOT copy example inputs or outputs verbatim into the prompt
- Extract underlying principles from failures, don't patch individual cases
- Preserve all {variable} template placeholders
- Keep working sections of the prompt unchanged
- Create synthetic examples if examples are needed, never use test data
- The prompt must remain compatible with the ReAct tool-calling loop

## Task
Produce a revised system prompt that addresses the failure patterns while maintaining the agent's existing capabilities. Explain each change you make.
```

### Run the optimization

```bash
# Using the arize-prompt-optimization skill workflow:
# 1. Gather failure records
# 2. Apply meta-prompt with an LLM
# 3. Output the revised prompt

python3 -c "
import json

# Load failures
with open('baseline-results.json') as f:
    runs = json.load(f)

failure_records = []
for run in runs:
    for ev in run.get('evaluations', []):
        if ev.get('label') in ('incorrect', 'unsafe', 'wrong_tools'):
            failure_records.append(
                f\"Input: {run.get('input','')}\\n\"
                f\"Output: {run.get('output','')[:200]}\\n\"
                f\"Evaluator: {ev.get('name')}\\n\"
                f\"Label: {ev.get('label')}\\n\"
                f\"Explanation: {ev.get('explanation','')}\\n\"
            )

with open('current-prompt.txt') as f:
    current_prompt = f.read()

# Write the meta-prompt for manual or automated LLM invocation
meta = f'''You are a prompt engineer optimizing a system prompt for an AI pet store agent.

## Current System Prompt
{current_prompt}

## Performance Data ({len(failure_records)} failures)
{'---'.join(failure_records[:20])}

## Rules
- DO NOT copy example inputs or outputs verbatim into the prompt
- Extract underlying principles from failures
- Preserve all template placeholders
- Keep working sections unchanged

## Task
Produce a revised system prompt that addresses these failure patterns.
'''

with open('meta-prompt.txt', 'w') as f:
    f.write(meta)

print(f'Meta-prompt written ({len(failure_records)} failures included)')
print('Feed meta-prompt.txt to your LLM of choice to generate the optimized prompt.')
"
```

You can feed `meta-prompt.txt` to Claude, GPT-4, or any capable model. Or let Claude Code handle it directly using the `arize-prompt-optimization` skill.

The `arize-live-traces` MCP server can also be used to inspect LLM spans directly from Claude Code, which is helpful for extracting system prompts without a full export.

---

## Step 4: A/B Experiment

Validate the optimized prompt by running the same golden dataset against both the original and optimized versions.

### Deploy the optimized prompt

Update `pet_store_agent/pet_store_agent.py` with the new `SYSTEM_PROMPT`, rebuild, and deploy to a separate runtime or qualifier. Alternatively, make the system prompt configurable via an environment variable so you can A/B test without redeploying:

```python
SYSTEM_PROMPT = os.environ.get("AGENT_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
```

### Run the experiment with the optimized prompt

```bash
# Run the golden dataset against the optimized agent
python3 run_experiment.py --output optimized-runs.json

ax experiments create \
  --name "petstore-optimized-v1" \
  --dataset petstore-golden-v1 \
  --space "$ARIZE_SPACE" \
  --file optimized-runs.json
```

### Run evaluators on the new experiment

```bash
ax tasks create \
  --name "petstore-eval-optimized" \
  --project virtual-pet-store-agent \
  --space "$ARIZE_SPACE" \
  --evaluators '[
    {"evaluator_name": "PetStore Correctness"},
    {"evaluator_name": "PetStore Safety"},
    {"evaluator_name": "PetStore Tool Usage"}
  ]'

ax tasks trigger-run <TASK_ID>
```

### Compare results

```bash
# Export both experiments
ax experiments export petstore-baseline-v1 --space "$ARIZE_SPACE" > baseline.json
ax experiments export petstore-optimized-v1 --space "$ARIZE_SPACE" > optimized.json

# Compare scores
python3 -c "
import json

def score_summary(filename):
    with open(filename) as f:
        runs = json.load(f)
    labels = {}
    for run in runs:
        for ev in run.get('evaluations', []):
            key = (ev.get('name',''), ev.get('label',''))
            labels[key] = labels.get(key, 0) + 1
    return labels

baseline = score_summary('baseline.json')
optimized = score_summary('optimized.json')

print('Evaluator             | Label              | Baseline | Optimized')
print('----------------------|--------------------|----------|----------')
all_keys = sorted(set(list(baseline.keys()) + list(optimized.keys())))
for key in all_keys:
    name, label = key
    b = baseline.get(key, 0)
    o = optimized.get(key, 0)
    delta = '  +' if o > b else '  -' if o < b else '   '
    print(f'{name:22}| {label:19}| {b:8} | {o:8}{delta}')
"
```

### Decision criteria

| Outcome | Action |
|---------|--------|
| Correctness improved, no safety regression | Deploy optimized prompt to production |
| Mixed results (some better, some worse) | Iterate --- refine the meta-prompt with the new failures |
| No improvement or regression | Keep the original prompt; investigate failure patterns more deeply |

Statistical significance requires at least 30 examples per evaluator. If your golden dataset is smaller, interpret results directionally rather than conclusively.

### Generate a link to view results in Arize

```bash
ax link trace --trace-id <trace-id> --space "$ARIZE_SPACE" --project virtual-pet-store-agent
```

Or link to the experiment comparison view directly in the Arize UI.

---

## Step 5: Deploy and Iterate

If the optimized prompt passes the A/B test:

1. Update `SYSTEM_PROMPT` in `pet_store_agent/pet_store_agent.py`
2. Rebuild and deploy: `cd terraform && make apply`
3. Continuous monitoring (set up in Phase 2) will automatically evaluate the new production traces
4. After 1--2 days of production data, run a new experiment comparing pre/post deployment scores

### The iteration loop

This isn't a one-time process. The full cycle is:

```
Traces → Dataset → Evaluators → Experiment → Scores → Optimize → Deploy → Traces → ...
```

Each cycle should:
- Add newly discovered failure cases to the golden dataset (`ax datasets append`)
- Version the evaluator prompt if the classification criteria need refinement (`ax evaluators create-version`)
- Keep a log of prompt versions and their experiment scores for tracking improvement over time

---

## Outputs

By the end of Phase 3, you have:

| Artifact | Where | Purpose |
|----------|-------|---------|
| Failure analysis | Local files | Understanding of where the agent struggles |
| Meta-prompt template | `meta-prompt.txt` | Reusable prompt optimization workflow |
| Optimized system prompt | `pet_store_agent.py` | Improved agent behavior |
| A/B experiment results | Arize Experiments | Evidence that the optimization worked |
| Iteration playbook | This doc | Repeatable process for future improvements |

---

## Summary: The Full Pipeline

```
Phase 1                    Phase 2                      Phase 3
────────                   ────────                     ────────
Export traces        →     Create evaluators      →     Analyze failures
Curate dataset       →     Run experiments         →     Meta-prompt optimization
Set up annotations   →     Continuous monitoring    →     A/B experiment
                                                         Deploy improved prompt
                                                              │
                                                              └──→ back to Phase 1
                                                                   (new traces to analyze)
```

This is the evaluation flywheel: production data drives evaluation, evaluation drives optimization, optimization drives better production data.
