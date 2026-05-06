# Phase 9: Chat UI

## Goal

Build a local chat interface that lets staff interact with the live AgentCore Runtime through a browser instead of raw CLI or test scripts. The UI renders structured agent responses (order items, pricing, discounts, pet advice) as formatted cards rather than raw JSON.

---

## Architecture

```
Browser (Vite + React)
    ↓  POST /api/chat { "prompt": "..." }
FastAPI proxy  (ui/server.py)
    ↓  invoke_agent_runtime (boto3, IAM role auth)
AgentCore Runtime (AWS)
    ↓  JSON response
FastAPI returns parsed JSON → browser renders card
```

The proxy is necessary because browsers cannot sign AWS Signature V4 requests. The EC2 instance role supplies credentials transparently to boto3 — no keys to manage.

---

## Stack

Same stack as the evolveai-framework project:

| Layer | Technology |
|---|---|
| Frontend bundler | Vite 6 + TypeScript |
| UI framework | React 18 |
| Styling | Tailwind CSS v3 (emerald/green theme) |
| Components | Radix UI primitives |
| Icons | lucide-react |
| Routing | react-router-dom (stub for future pages) |
| Utilities | clsx, tailwind-merge, class-variance-authority |
| Backend proxy | FastAPI + uvicorn |
| AWS client | boto3 |

---

## File Structure

```
ui/
├── server.py               # FastAPI proxy — one route: POST /api/chat
├── requirements.txt        # fastapi, uvicorn, boto3, python-dotenv
├── .env.example            # RUNTIME_ARN, AWS_DEFAULT_REGION, PORT
├── index.html
├── vite.config.ts          # /api proxy → localhost:8000
├── tailwind.config.ts      # brand = emerald alias
├── tsconfig.json
├── package.json
└── src/
    ├── main.tsx
    ├── App.tsx             # State + two-panel grid layout
    ├── types.ts            # ChatMessage, AgentResponse, OrderItem
    ├── api.ts              # fetch wrapper for POST /api/chat
    ├── lib/
    │   └── utils.ts        # cn() helper
    └── components/
        ├── Sidebar.tsx          # Branding + example prompt buttons
        ├── ChatArea.tsx         # Scrollable history + auto-scroll
        ├── MessageBubble.tsx    # User bubble (right) vs agent card (left)
        ├── AgentResponseCard.tsx # Structured response renderer
        ├── ItemsTable.tsx        # Product line items with replenish flag
        ├── FinancialSummary.tsx  # Subtotal / discount / shipping / total
        ├── StatusBadge.tsx       # Accept (green) / Reject (red) / Error (yellow)
        └── ChatInput.tsx         # Textarea + Send button (Enter to send)
```

---

## Agent Response Rendering

The agent returns this JSON shape:

```json
{
  "status": "Accept",
  "message": "Dear Customer...",
  "customerType": "Guest",
  "items": [
    {
      "productId": "DD006",
      "price": 54.99,
      "quantity": 1,
      "bundleDiscount": 0,
      "total": 54.99,
      "replenishInventory": false
    }
  ],
  "shippingCost": 14.95,
  "petAdvice": "",
  "subtotal": 54.99,
  "additionalDiscount": 0,
  "total": 69.94
}
```

`AgentResponseCard` renders conditionally:

| Field | Rendered when |
|---|---|
| `StatusBadge` + `customerType` tag | Always |
| `message` | Always |
| `ItemsTable` | `items` is non-empty |
| `FinancialSummary` | `status === "Accept"` and `subtotal` present |
| Pet advice box | `petAdvice` is non-empty |

A Reject response shows only the red badge and the sorry message — no table, no financials.

---

## Example Prompts (Sidebar)

```
"What is the price of Doggy Delights?"
"I want 2 Bark Park Buddies"
"Do you have a self-cleaning litter box?"
"I want the SmartFeed Automatic Dog Feeder"
"CustomerId: usr_001 — I want the Bark Park Buddy. Good for bathing my dog?"
"I want the CleanPaws Litter Box and SmartFeed Feeder"
```

---

## Key Implementation Notes

**Double-JSON decoding in the proxy:** The runtime response body is a JSON string containing another JSON string (the agent returns `json.dumps(dict)` and the entrypoint wraps it again). `server.py` must call `json.loads()` twice when the first decode yields a string.

**Thinking-token stripping in the proxy:** Nova Pro may emit `<thinking>...</thinking>` before the JSON. Strip with `re.sub(r'<thinking>.*?</thinking>', '', raw, flags=re.DOTALL)` before parsing.

**Vite proxy config:** All `/api` requests from the dev server forward to `http://localhost:8000` to avoid CORS. In production both can be served from the same origin.

**Loading state:** Append a placeholder `ChatMessage` with `loading: true` immediately on send, then replace it with the real response. This gives instant feedback without a separate loading overlay.

---

## Development Workflow

```bash
# Terminal 1 — backend proxy
cd ui
pip install -r requirements.txt
cp .env.example .env        # set RUNTIME_ARN
python server.py             # starts on :8000 with --reload

# Terminal 2 — frontend
cd ui
npm install
npm run dev                  # Vite on :5173, proxies /api → :8000
```

Open `http://localhost:5173`.

---

## For Srikar's Understanding

### Homework

**1. Why does the UI need a proxy server at all?**
The browser cannot make signed AWS API calls — Signature V4 signing requires secret keys which cannot be safely embedded in frontend code. The proxy holds credentials (via the EC2 instance role) and signs requests server-side. What would need to change to deploy this UI to a public URL safely?

**2. Why is the proxy kept intentionally thin?**
`server.py` does exactly what `test_agent.py` does: invoke, strip thinking tags, double-decode JSON, return. No caching, no session management, no auth. This means the proxy is easy to reason about and the agent's behaviour in the UI is identical to behaviour in tests. What would you add if this needed to support multiple concurrent users with their own conversation history?

**3. What does `loading: true` in the ChatMessage give you?**
Rather than a global spinner that blocks the whole page, each message slot knows its own loading state. This makes it possible to show "typing" indicators per message, display partial streaming responses in the future, or retry individual messages. How would you change the architecture to support streaming responses from the agent?

**4. Why render the financial summary in the UI rather than in a plain text message?**
The agent's `message` field is capped at 250 characters (from the response schema). It cannot reliably fit a full itemised receipt. The structured fields (`items`, `subtotal`, `shippingCost`, `total`) exist precisely so the frontend can render a proper receipt without parsing natural language. What breaks in the UI if the agent returns `status: "Accept"` but an empty `items` array?
