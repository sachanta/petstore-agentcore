# PetStore Agent: LangGraph Internals & ReAct Architecture

## Overview

The Virtual Pet Store agent is a **ReAct (Reasoning + Acting)** agent built with LangGraph's `create_react_agent` prebuilt function. It runs Amazon Nova Pro on AWS Bedrock, uses 5 structured tools to interact with knowledge bases and Lambda backends, and applies deterministic business-rule post-processing to ensure pricing accuracy.

**Runtime**: AWS Bedrock AgentCore (Docker container, Python 3.12)
**Framework**: LangGraph + LangChain
**LLM**: Amazon Nova Pro (`us.amazon.nova-pro-v1:0`) via Bedrock Converse API
**Observability**: Arize AX via OpenTelemetry (OTLP)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      AgentCore Runtime                           │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  Guardrail   │───▶│  LangGraph   │───▶│  Business Rules  │  │
│  │  (Bedrock)   │    │  ReAct Agent │    │  Post-Processor  │  │
│  └──────────────┘    └──────┬───────┘    └──────────────────┘  │
│                             │                                   │
│              ┌──────────────┼──────────────┐                    │
│              ▼              ▼              ▼                    │
│  ┌────────────────┐ ┌────────────┐ ┌───────────────┐          │
│  │ Knowledge Bases │ │  Inventory │ │    User Mgmt  │          │
│  │   (Bedrock)     │ │  (Lambda)  │ │   (Lambda)    │          │
│  └────────────────┘ └────────────┘ └───────────────┘          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## The ReAct Pattern

### What is ReAct?

ReAct (**Re**asoning + **Act**ing) is a prompting paradigm where an LLM alternates between:

1. **Thought** — reasoning about what to do next given current context
2. **Action** — selecting and invoking a tool
3. **Observation** — receiving the tool's output

This loop repeats until the LLM has enough information to produce a final answer.

### Why ReAct?

| Pattern | Pros | Cons |
|---------|------|------|
| **Chain-of-Thought** | Good reasoning | No tool access |
| **Tool-only** | Uses tools | No explicit reasoning |
| **ReAct** | Reasons AND acts | More LLM calls (higher latency/cost) |

ReAct is ideal for the pet store agent because:
- Multi-step queries require calling 2-4 tools per request
- Business rules require the agent to reason about which tools to call and in what order
- Parallel tool calling (user lookup + product search simultaneously) improves latency

### ReAct Loop in This Agent

```
User Message
    │
    ▼
┌─────────────────────────────────────────┐
│         LLM (Nova Pro) THINKS           │
│  "User wants to buy dog food.           │
│   I need to: find the product,          │
│   check inventory, look up the user"    │
└─────────────────┬───────────────────────┘
                  │
                  ▼ (parallel tool calls)
┌─────────────────────────────────────────┐
│  retrieve_product_info("dog food")      │
│  get_user_by_email("john@example.com")  │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│        LLM OBSERVES tool results        │
│  "Found DD006 at $54.99. User is        │
│   subscribed. Need inventory check."    │
└─────────────────┬───────────────────────┘
                  │
                  ▼ (follow-up tool call)
┌─────────────────────────────────────────┐
│  get_inventory("DD006")                 │
│  retrieve_pet_care("dog food nutrition")│
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│         LLM GENERATES RESPONSE          │
│  Applies business rules, formats JSON   │
└─────────────────────────────────────────┘
```

### Implementation Details

LangGraph's `create_react_agent` abstracts the loop into a graph with two nodes:

```python
from langgraph.prebuilt import create_react_agent

agent_executor = create_react_agent(
    model,          # Nova Pro via Bedrock Converse
    tools,          # 5 structured tools
    prompt=prompt   # System prompt with business rules
)
```

Internally, LangGraph creates this state machine:

```
         ┌───────────────┐
         │     START     │
         └───────┬───────┘
                 │
                 ▼
         ┌───────────────┐
    ┌───▶│   agent node  │◀───┐
    │    │  (LLM call)   │    │
    │    └───────┬───────┘    │
    │            │            │
    │     ┌─────┴─────┐      │
    │     │           │      │
    │     ▼           ▼      │
    │  [has tools]  [no tools]
    │     │           │
    │     ▼           ▼
    │ ┌────────┐  ┌───────┐
    └─│ tools  │  │  END  │
      │ node   │  └───────┘
      └────────┘
```

The agent node calls the LLM. If the LLM response contains tool calls, execution routes to the tools node which invokes them. Results are appended to the message list and control returns to the agent node. When the LLM responds without tool calls, the loop ends.

---

## File Structure

```
pet_store_agent/
├── pet_store_agent.py          # Core: agent graph, system prompt, process_request()
├── agentcore_entrypoint.py     # Handler: guardrail, business rules post-processing
├── retrieve_product_info.py    # Tool: product catalog KB retrieval
├── retrieve_pet_care.py        # Tool: pet care advice KB retrieval
├── inventory_management.py     # Tool: Lambda inventory queries
├── user_management.py          # Tool: Lambda user lookups
├── tracing.py                  # Arize OTLP tracing setup
└── lambda_function.py          # Alternative Lambda entry point
```

---

## Entry Point & Message Flow

### Handler (`agentcore_entrypoint.py`)

```python
def handler(payload):
    prompt = payload.get("prompt", "")
    
    # Step 1: Input guardrail
    guardrail_result = _check_guardrail(prompt)
    if guardrail_result:
        return guardrail_result  # Blocked → {"status": "Reject", ...}
    
    # Step 2: Invoke ReAct agent
    response = pet_store_agent.process_request(prompt)
    
    # Step 3: Deterministic business rules
    final = _apply_business_rules(response)
    return final
```

### Agent Invocation (`pet_store_agent.py`)

```python
def process_request(prompt: str) -> str:
    messages = [HumanMessage(content=prompt)]
    thread_id = str(uuid.uuid4())
    
    response = agent.invoke(
        {"messages": messages},
        {"configurable": {"thread_id": thread_id}}
    )
    
    # Extract final AI message
    final_message = response["messages"][-1]
    content = final_message.content
    
    # Strip Nova Pro's <thinking> tags
    content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL).strip()
    return content
```

---

## Tools

### 1. `retrieve_product_info`

| Field | Value |
|-------|-------|
| **Purpose** | Search product catalog |
| **Backend** | Bedrock Knowledge Base (S3 data source with product .txt files) |
| **Parameters** | `text` (query), `numberOfResults` (default 10), `score` (threshold 0.25) |
| **Returns** | Product name, ID, relevance score, description |

### 2. `retrieve_pet_care`

| Field | Value |
|-------|-------|
| **Purpose** | Retrieve pet care advice |
| **Backend** | Bedrock Knowledge Base (web crawler source) |
| **Parameters** | Same as `retrieve_product_info` |
| **Returns** | Pet care guidance (nutrition, health, grooming) |

### 3. `get_inventory`

| Field | Value |
|-------|-------|
| **Purpose** | Query stock levels |
| **Backend** | Lambda function (`PetStoreInventoryManagementFunction`) |
| **Parameters** | `product_code` (optional — omit for all products) |
| **Returns** | JSON with `quantity`, `status`, `reorder_level`, `last_updated` |

### 4. `get_user_by_id`

| Field | Value |
|-------|-------|
| **Purpose** | Look up user by ID |
| **Backend** | Lambda function (`PetStoreUserManagementFunction`) |
| **Parameters** | `user_id` (e.g., "usr_001") |
| **Returns** | JSON with `name`, `email`, `subscription_status`, `transactions` |

### 5. `get_user_by_email`

| Field | Value |
|-------|-------|
| **Purpose** | Look up user by email |
| **Backend** | Lambda function (`PetStoreUserManagementFunction`) |
| **Parameters** | `user_email` |
| **Returns** | Same as `get_user_by_id` |

---

## System Prompt & Business Rules

The system prompt (190 lines in `pet_store_agent.py`) instructs the agent to:

1. **Analyze** the customer input — identify user details, product requests
2. **Execute in parallel**:
   - Look up the user (by ID or email), check subscription status
   - Search for products, check inventory for each match
3. **Apply business rules** (pricing, shipping, discounts)
4. **Return JSON** in a strict schema

### Business Rules (Enforced in Post-Processing)

| Rule | Logic |
|------|-------|
| **Bundle discount** | 10% off 2nd+ units of same product |
| **Order discount** | 15% when subtotal > $300 |
| **Free shipping** | Subtotal ≥ $75 |
| **Standard shipping** | $14.95 (< 3 units) or $19.95 (≥ 3 units) |
| **Replenishment flag** | `true` when post-order qty ≤ reorder_level |
| **Customer type** | "Subscribed" only with active subscription |
| **Pet advice** | Only for active subscribers |
| **Scope** | Dogs and cats only — all other animals blocked |

### Response Schema

```json
{
  "status": "Accept | Reject",
  "message": "Customer-facing message",
  "customerType": "Guest | Subscribed",
  "items": [
    {
      "productId": "DD006",
      "price": 54.99,
      "quantity": 2,
      "bundleDiscount": 0.10,
      "total": 104.48,
      "replenishInventory": false
    }
  ],
  "shippingCost": 0.0,
  "subtotal": 104.48,
  "additionalDiscount": 0,
  "orderTotal": 104.48,
  "petAdvice": "Nutritional guidance..."
}
```

---

## Guardrails

### Input Guardrail (Bedrock Guardrail Service)

Applied **before** the agent runs. Blocks:
- Out-of-scope animals (parrots, fish, reptiles, etc.)
- Prompt injection attempts
- Offensive or harmful content
- Requests outside the pet store domain

```python
def _check_guardrail(prompt: str) -> str | None:
    response = bedrock_client.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        source="INPUT",
        content=[{"text": {"text": prompt}}]
    )
    if response["action"] == "GUARDRAIL_INTERVENED":
        return json.dumps({"status": "Reject", "message": "..."})
    return None  # Proceed
```

### Deterministic Post-Processing

Applied **after** the agent responds. Recalculates all pricing to prevent LLM arithmetic errors:
- Bundle discounts
- Item totals
- Subtotal and order total
- Shipping cost
- Replenishment flags (fetches live inventory)

This hybrid approach (LLM for reasoning + deterministic code for math) ensures correctness.

---

## Observability (Trace Structure)

Every request produces an OpenTelemetry trace with this span hierarchy:

```
LangGraph (root span)
├── agent (ReAct loop iteration)
│   ├── call_model
│   │   └── ChatBedrockConverse (LLM call)
│   ├── tools
│   │   ├── retrieve_product_info
│   │   └── get_user_by_email
│   └── call_model
│       └── ChatBedrockConverse (follow-up LLM call)
├── agent (second iteration, if needed)
│   ├── call_model
│   │   └── ChatBedrockConverse
│   └── tools
│       └── get_inventory
└── agent (final — no tool calls, generates response)
    └── call_model
        └── ChatBedrockConverse
```

Traces flow to Arize AX for monitoring, evaluation, and debugging.

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `KNOWLEDGE_BASE_1_ID` | Product catalog Knowledge Base |
| `KNOWLEDGE_BASE_2_ID` | Pet care Knowledge Base |
| `SYSTEM_FUNCTION_1_NAME` | Inventory Lambda function name |
| `SYSTEM_FUNCTION_2_NAME` | User management Lambda function name |
| `GUARDRAIL_ID` | Bedrock Guardrail ID |
| `GUARDRAIL_VERSION` | Guardrail version |
| `AWS_REGION` | AWS region (default: us-west-2) |
| `ARIZE_SPACE_ID` | Arize space for tracing |
| `ARIZE_API_KEY` | Arize API key |

---

## Enhancement: LangChain Deep Agents Pattern

### The Limitation of ReAct

Our current agent uses a simple ReAct loop — effective for single-turn queries but limited when tasks require:
- **Multi-step planning** across many tool calls
- **Long-running execution** that exceeds context windows
- **Delegation** of subtasks to specialized agents
- **Persistent memory** across conversations

The agent handles each request independently with no memory of past interactions and no ability to break complex requests into a tracked plan.

### What Are Deep Agents?

[LangChain Deep Agents](https://www.langchain.com/deep-agents) (`langchain-ai/deepagents`) is a framework built on LangGraph that adds four capabilities on top of a basic ReAct loop:

| Capability | What It Does | Current Agent | Deep Agent |
|-----------|--------------|---------------|------------|
| **Planning Tool** | Breaks tasks into tracked todo items | No planning — single-shot reasoning | `write_todos` tool creates/updates a plan |
| **Sub-Agents** | Spawns isolated child agents for subtasks | Single flat agent | `task` tool delegates to specialist agents |
| **File System** | Reads/writes to persistent storage | No persistent context | Virtual FS offloads context, survives restarts |
| **Detailed Prompt** | Rich system instructions with examples | Has this already | Enhanced with planning/delegation guidance |

### Architecture Comparison

```
CURRENT (Simple ReAct)              ENHANCED (Deep Agent)
━━━━━━━━━━━━━━━━━━━━━              ━━━━━━━━━━━━━━━━━━━━━━
                                    
User ──▶ Agent ──▶ Tools           User ──▶ Orchestrator Agent
              │                                  │
              └── Response                ┌──────┼──────┐
                                          ▼      ▼      ▼
                                       Planner  Sub-   File
                                       (todos)  Agents  System
                                                  │
                                          ┌───────┼───────┐
                                          ▼       ▼       ▼
                                       Product  User   Inventory
                                       Agent    Agent   Agent
```

### How It Would Apply to the Pet Store

#### 1. Planning Tool (`write_todos`)

For complex orders (multiple products, user verification, pet care advice), the agent would create an explicit plan:

```
□ Look up user by email → verify subscription
□ Search for "premium dog food" → get product ID
□ Search for "dog bowl" → get product ID  
□ Check inventory for both products
□ Retrieve pet care advice for subscriber
□ Calculate pricing with bundle discount
□ Generate final response
```

Each step is tracked and checked off, making the agent's reasoning transparent and debuggable in traces.

#### 2. Sub-Agent Delegation (`task` tool)

Instead of one agent handling everything, specialized sub-agents could handle isolated concerns:

| Sub-Agent | Responsibility |
|-----------|---------------|
| **Product Research Agent** | Searches catalog, compares options, handles "which is better?" queries |
| **Order Processing Agent** | Calculates pricing, applies discounts, validates inventory |
| **Pet Care Advisor Agent** | Provides nutrition, health, and grooming guidance for subscribers |
| **User Account Agent** | Handles user lookups, subscription verification, transaction history |

Benefits:
- Each sub-agent has a focused context window (no pollution from unrelated tool results)
- Sub-agents can be tested and evaluated independently
- Failures in one sub-agent don't crash the entire request

#### 3. Virtual File System

The file system enables:
- **Session notes**: Agent writes intermediate findings to files, reads them back when needed
- **Context overflow management**: Large tool results (e.g., 50 product matches) stored in files instead of message history
- **Cross-request memory**: "Last time this user ordered DD006, they also asked about grooming"

#### 4. Persistent Memory (LangGraph Store)

Using LangGraph's Memory Store, the agent could:
- Remember user preferences across sessions
- Track order history patterns
- Build up product knowledge over time
- Recall previous pet care recommendations

### Implementation Sketch

```python
from deepagents import create_deep_agent
from deepagents.tools import write_todos, task, filesystem_tools
from langgraph.checkpoint.memory import MemorySaver

# Define sub-agents
product_agent = create_react_agent(model, [retrieve_product_info, get_inventory])
user_agent = create_react_agent(model, [get_user_by_id, get_user_by_email])
care_agent = create_react_agent(model, [retrieve_pet_care])

# Create the deep agent orchestrator
orchestrator = create_deep_agent(
    model=model,
    tools=[
        write_todos,                    # Planning
        task(product_agent, "product"), # Delegation
        task(user_agent, "user"),       # Delegation
        task(care_agent, "care"),       # Delegation
        *filesystem_tools(),            # Context management
    ],
    prompt=orchestrator_prompt,
    checkpointer=MemorySaver(),
)
```

### When to Upgrade

| Signal | Current Agent Handles It | Deep Agent Needed |
|--------|--------------------------|-------------------|
| Single product query | Yes | No |
| Multi-product comparison | Struggles with context | Yes — delegate to product sub-agent |
| "What did I order last time?" | Cannot remember | Yes — persistent memory |
| Complex multi-step orders | Works but opaque | Yes — planning makes it traceable |
| Batch processing (10+ orders) | Would overflow context | Yes — file system offloads results |
| "Find the cheapest option across categories" | Limited reasoning depth | Yes — sub-agent can do deep research |

### Migration Path

1. **Phase 1**: Add `write_todos` planning to the existing agent (no architectural change — just a new tool)
2. **Phase 2**: Extract product search into a sub-agent for better context isolation
3. **Phase 3**: Add file system for cross-session memory and large result handling
4. **Phase 4**: Full deep agent with orchestrator pattern and persistent memory store

Each phase is independently deployable and backwards-compatible with the existing test suite.

### References

- [LangChain Deep Agents Overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [Deep Agents GitHub](https://github.com/langchain-ai/deepagents)
- [LangChain Blog: Deep Agents](https://blog.langchain.com/deep-agents/)
- [Build a Deep Research Agent](https://docs.langchain.com/oss/python/deepagents/deep-research)
- [LangGraph Academy: Deep Research](https://academy.langchain.com/courses/deep-research-with-langgraph)
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
