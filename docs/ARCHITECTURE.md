# Architecture

This document describes how the Agentic Travel Planner is put together —
module-by-module, the request/webhook lifecycles, the key design decisions,
and the extension points. For the *why this is production-ready* narrative,
see [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md).

---

## Top-level layout

```
.
├── web_server.py                 # FastAPI app, streaming chat, Stripe webhook
├── travel_agent/
│   ├── config.py                 # Env-driven Config + structured JSON logging
│   ├── setup.py                  # build_llm / build_mcp_server / build_agent
│   ├── cli.py                    # Interactive CLI (no web)
│   ├── agent/
│   │   ├── orchestrator.py       # The LLM ↔ tools loop
│   │   ├── llm.py                # OpenAI / Anthropic / Google providers
│   │   ├── memory.py             # Sliding-window conversation memory
│   │   ├── cache.py              # Sync + async TTL caches
│   │   ├── retry.py              # async_retry helper
│   │   ├── documents.py          # PDF / DOCX / TXT extraction
│   │   └── prompts/system.md     # Externalised system prompt
│   ├── mcp/
│   │   ├── protocol.py           # JSON-RPC 2.0 + MCP Pydantic models
│   │   └── mcp_server.py         # In-process tool registry & dispatcher
│   ├── tools/
│   │   ├── flights.py            # Amadeus search + Aviasales deeplink
│   │   ├── hotels.py             # Amadeus Hotel Search v3 + Hotellook deeplink
│   │   ├── cars.py               # RentalCars deeplink + price estimate
│   │   ├── weather.py            # Open-Meteo forecast + climate proxy
│   │   ├── payment.py            # create_payment_session / get_payment_status
│   │   └── datetime_tool.py      # Current date/time
│   └── payments/
│       ├── models.py             # CheckoutRequest / CheckoutResponse / etc.
│       ├── stripe_client.py      # StripeClient + StripeMockClient
│       └── service.py            # PaymentService: idempotency, webhook dedup
├── scripts/                      # debug_gemini.py, verify_langfuse.py
├── tests/                        # pytest-asyncio + respx + freezegun
└── docs/                         # PRODUCTION_READINESS.md, ARCHITECTURE.md
```

---

## Component map

```
                ┌───────────────────┐
   HTTP chat ──▶│ web_server.py     │── NDJSON stream ──▶ browser/CLI
                │ (FastAPI)         │
                └─┬──────┬──────┬───┘
        per-sess.│      │      │ POST /webhooks/stripe
                 ▼      │      ▼
        ┌──────────────┐│   ┌──────────────────┐
        │ Orchestrator ││   │ PaymentService   │
        └─┬───────┬────┘│   │ (idempotency +   │
   tool   │       │ LLM │   │ webhook dedup)   │
   calls  │       ▼     │   └────────┬─────────┘
          │   ┌──────────┴──┐         │
          │   │ LLMProvider │         │
          │   │ (OAI/Ant/G) │         │ Stripe API ◀──────┐
          │   └─────────────┘         ▼                    │
          ▼                    ┌──────────────┐            │
   ┌──────────────┐            │ StripeClient │ ◀── HTTPS ─┘
   │ MCPServer    │            │  (or Mock)   │
   │ (registry +  │            └──────────────┘
   │  dispatcher) │
   └──────┬───────┘
          │
  ┌──────┬┴───────┬──────────┬──────────┬─────────────┬──────────┐
  ▼      ▼        ▼          ▼          ▼             ▼          ▼
flights hotels  cars      weather   create_payment  get_payment datetime
                                    _session       _status
  ▲      ▲        ▲          ▲
  │      │        │          │
  │ Amadeus       │      Open-Meteo
  │ Self-Service  │   (geocoding +
  │ (flights +    │    forecast +
  │  hotels)      │    archive)
  │               │
  Aviasales      RentalCars
  affiliate       affiliate
  deeplink        deeplink
```

---

## Module reference

### `web_server.py`
FastAPI entrypoint. Holds the `SessionManager` (per-session
`AgentOrchestrator` instances keyed by `X-Session-Id`) and exposes:

| Endpoint | Purpose |
|---|---|
| `GET  /` | Serves the static chat UI (`static/index.html`) |
| `GET  /healthz` | Liveness — always 200 if the process is up |
| `GET  /readyz` | Readiness — 503 when running on the MockAgent fallback |
| `POST /api/chat` | Multipart: `message` + optional `file`. Streams NDJSON events |
| `POST /webhooks/stripe` | Raw body, signature-verified, dispatched to `PaymentService` |
| `GET  /payment/success` | Stripe redirect target after successful checkout |
| `GET  /payment/cancel` | Stripe redirect target after cancellation |

Key safeguards: CORS allowlist (no `*`), 25 MB upload cap, MIME magic-byte
sniffing, per-request `asyncio.timeout(REQUEST_TIMEOUT_SECONDS)`, per-session
memory isolation.

### `travel_agent/config.py`
Single source of truth for environment configuration.

- `Config` — class-level attributes read from `os.getenv` at import time
  (after `load_dotenv()`).
- `Config.validate()` — raises `ConfigError` if required keys are missing for
  the current `STRIPE_MODE`. Live mode additionally requires `sk_live_…`.
- `setup_logging()` — installs an idempotent JSON formatter on the root logger
  (`JsonFormatter` emits structured records with `request_id`/`session_id` when
  passed via `extra=`).

Test code reads/writes attributes directly via `monkeypatch.setattr(Config, …)`
rather than reloading the module — that avoids creating divergent `Config`
classes that other already-imported modules don't see.

### `travel_agent/setup.py`
Shared agent-construction surface used by both `web_server.py` and `cli.py`:

- `select_provider()` → `(provider_name, api_key)` from `Config`, preferring
  `Config.LLM_PROVIDER`, falling back to whichever provider has a key.
- `build_llm()` → an `LLMProvider`, or `None` if nothing is configured.
- `build_mcp_server()` → fresh `MCPServer` with all production tools
  registered (single source of truth for tool registration).
- `build_agent()` → full `AgentOrchestrator` for CLI / one-shot use.

### `travel_agent/agent/orchestrator.py`
The agent loop. One method matters: `run_generator(user_input, file_data,
mime_type, request_id)`. It:

1. Creates a Langfuse trace (no-op if Langfuse is disabled).
2. Extracts text from any attached PDF/DOCX/TXT via `DocumentProcessor` and
   inlines it into the user message as a clearly-marked block.
3. Loops up to `Config.MAX_TURNS` times:
   - Prepends a fresh `system` message (static prompt from
     `prompts/system.md` + a dynamic `CRITICAL DATE CONTEXT` block).
   - Calls `llm.call_tool(messages, tools)` via `async_retry` —
     `Config.MAX_LLM_RETRIES` attempts.
   - Yields `{type: "message"}` for any text content; stops if no tool calls.
   - For each tool call, dispatches to `MCPServer.call_tool` (also wrapped in
     `async_retry`), yields `tool_call` + `tool_result` events, and appends
     the result to memory.
4. Ends/flushes the Langfuse trace.

PII is redacted (`_redact_pii`: emails and digit runs ≥ 8) before anything
reaches the observability layer.

### `travel_agent/agent/llm.py`
Abstract `LLMProvider` + three implementations:

- `OpenAIProvider` — `AsyncOpenAI` chat.completions. Defensive
  `json.loads` for tool-call args (malformed JSON surfaces as a
  `{"__error__": ...}` payload rather than crashing the loop).
- `AnthropicProvider` — `AsyncAnthropic` messages with content-block
  conversion (`tool_use`, `tool_result`).
- `GoogleProvider` — `google.generativeai`. Default model is `gemini-2.5-flash`
  (the `gemini-2.0-flash` default was retired by Google's free-tier quota
  policy; `2.5-flash` is the current widely-available alternative). Caches
  `GenerativeModel` instances keyed on `(model_name, system_instruction)` so
  the model object isn't rebuilt on every call. Tool schema types fall back
  to `STRING` on unknown values (Gemini is strict about its enum).

Langfuse observability lives in three free functions: `langfuse_trace`,
`langfuse_generation`, `langfuse_flush`. They handle v2 and v3 SDK shapes
and never raise — failures are logged and the trace simply becomes `None`.

### `travel_agent/agent/memory.py`
`AgentMemory` ABC + `InMemoryMemory` (sliding window, default
`Config.MAX_MESSAGES = 50`). `add_message` validates that each entry has a
`role`; `get_messages` returns a copy so callers can't mutate state.

### `travel_agent/agent/cache.py`
- `ToolCache` — sync, thread-safe (uses `threading.Lock`), JSON+sha256
  cache key, TTL eviction.
- `AsyncToolCache` — async-safe (`asyncio.Lock`), additionally coalesces
  concurrent calls for the same key via a shared in-flight `Future`.

### `travel_agent/agent/retry.py`
`async_retry(operation, *, attempts, base_delay, label, extra)` — single
helper used by the orchestrator for both LLM and tool calls. Backs off
linearly (`base_delay * (i + 1)`), logs at WARNING with `exc_info`,
re-raises the last exception if all attempts fail.

### `travel_agent/agent/documents.py`
`DocumentProcessor` — static `supports(mime_type)` + `extract(data, mime_type)`.
PDF via `pypdf`, DOCX via `python-docx`, TXT via UTF-8 decode. Returns
`None` on failure; the orchestrator falls back to forwarding the raw bytes.

### `travel_agent/agent/prompts/system.md`
Externalised system prompt. Tells the LLM how to plan trips, how to format
output, and — critically — that bookings finish on partner-hosted pages and
the LLM must never claim to have charged a card.

### `travel_agent/mcp/protocol.py`
Pydantic models for JSON-RPC 2.0 (`JsonRpcRequest`, `JsonRpcResponse`) and
the MCP `Tool` / `CallToolRequest` / `CallToolResult`. `create_tool_definition`
produces the dict shape we hand to the LLM.

### `travel_agent/mcp/mcp_server.py`
In-process tool registry + dispatcher.

- `register_tool(func)` — infers a JSON Schema from the function signature
  (`int`/`float`/`bool`/`list`/`dict` → JSON Schema types; everything else
  defaults to `"string"`). Uses `inspect.getdoc()` for the tool description.
- `call_tool(name, arguments)` — drops unknown args (LLMs hallucinate),
  validates required ones are present, dispatches sync vs async, JSON-encodes
  dict/list results so structure isn't flattened to `str(dict)`, returns a
  `CallToolResult`. `ValueError` from tools is surfaced cleanly; other
  exceptions are logged with `logger.exception` and returned as `isError`.

### `travel_agent/tools/*`
Each tool is a plain function (sync or async). Inputs are simple types — the
LLM's tool-call JSON schema is derived from the signature. Validation is done
inside the function and raised as `ValueError` (which `MCPServer.call_tool`
turns into a clean `"Invalid input"` payload).

| Tool | What it does | Real-API source |
|---|---|---|
| `search_flights` | Real-time flight offers | Amadeus Self-Service v2/shopping/flight-offers |
| `book_flight` | Generates a real Aviasales booking URL + intent ref | Travelpayouts affiliate deeplink (no commercial agreement needed) |
| `search_hotels` | Real hotel offers; falls back to deeplink-only on API failure | Amadeus Hotel Search v3 (`hotels/by-city` + `hotel-offers`) |
| `rent_car` | Computes a price estimate + real RentalCars URL | RentalCars + Travelpayouts deeplink |
| `get_forecast` | Live forecast within 14 days; same-date-last-year archive proxy beyond; geocoding for any city | Open-Meteo (no key required) |
| `create_payment_session` | Hosted Stripe Checkout URL | Stripe Checkout (real / mock based on `STRIPE_MODE`) |
| `get_payment_status` | Refreshes session status from Stripe + local cache | Stripe Checkout |
| `get_current_datetime` | Current date/time for the LLM's reasoning | Local clock |

`flights.py` and `hotels.py` share an `AmadeusTokenCache` (async-locked OAuth
token cache that refreshes 60 s before expiry to avoid thundering herd).

### `travel_agent/payments/*`
A small payments package with a clean provider boundary:

- `models.py` — `CheckoutRequest` (Pydantic; validates amount, currency
  whitelist, email format), `CheckoutResponse`, `PaymentRecord` (server-side
  state), `PaymentStatus` enum.
- `stripe_client.py` — `StripeClient` (real) and `StripeMockClient`
  (in-memory, for `STRIPE_MODE=mock` and tests). Both implement the same
  protocol: `create_checkout_session`, `retrieve_session`, `verify_webhook`.
  The real client maps every `stripe.error.*` to a small set of user-safe
  `PaymentProviderError` messages so raw exceptions never leak to chat output.
  `build_stripe_client()` picks the implementation based on `Config.STRIPE_MODE`.
- `service.py` — `PaymentService` owns the in-memory `PaymentRecord` store
  (by booking_id and by session_id) and the set of processed webhook event
  IDs. Two guarantees:
  - **Idempotency**: re-calling `create_checkout` with the same `booking_id`
    returns the existing session.
  - **Webhook deduplication**: each `event.id` is processed at most once.

  All mutating paths are guarded by an `asyncio.Lock`.

### `travel_agent/cli.py`
Thin interactive REPL. Loads config, builds the agent via `setup.build_agent`,
prints streamed events to stdout.

### `static/`
The chat UI (vanilla HTML/CSS/JS, no build step). `static/js/app.js`:

- Generates a per-conversation ID (`currentConversationId`) and sends it as
  the `X-Session-Id` request header on every `POST /api/chat`. This keeps the
  server-side `SessionManager` aligned with the user-visible thread — new
  threads get new memory; existing threads recover full history.
- Renders assistant messages by auto-linkifying both Markdown-style `[text](url)`
  and raw `http(s)://` URLs.
- Auto-opens any URL whose host matches `aviasales.com`, `hotellook.com`,
  `rentalcars.com`, or `checkout.stripe.com` in a new tab so the user lands
  on the partner's checkout without an extra click. Subject to browser
  popup-blocker rules — the inline link is the always-clickable fallback.

---

## Request lifecycle: `POST /api/chat`

```
[client] ──multipart── webserver.chat ──┬─► validate message non-empty (400 if blank)
                                        │
                                        ├─► if file: read up to MAX_UPLOAD_MB bytes
                                        │      reject if oversize (413)
                                        │      sniff magic bytes (PDF / DOCX / TXT)
                                        │      reject on mismatch (415)
                                        │
                                        ├─► SessionManager.get_or_create(session_id)
                                        │      creates per-session AgentOrchestrator
                                        │      (shared LLM + MCPServer, fresh memory)
                                        │
                                        └─► async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                                                async for event in agent.run_generator(...):
                                                    yield NDJSON line

agent.run_generator turn loop:
  1. langfuse_trace(...)                       # observability (no-op if disabled)
  2. extract document if attached              # DocumentProcessor
  3. memory.add_message(user_message)
  4. while turn < MAX_TURNS:
     - messages = [system + memory.get_messages()]
     - response = async_retry(llm.call_tool, attempts=MAX_LLM_RETRIES)
     - yield {type: "message", content} if any text
     - if no tool_calls: break
     - for each tool_call:
         yield {type: "tool_call", ...}
         result = async_retry(server.call_tool, attempts=MAX_TOOL_RETRIES)
         yield {type: "tool_result", ...}
         memory.add_message(tool result)
  5. trace.end(); langfuse_flush()
```

Errors that surface to the client are generic strings (full trace stays in
logs). On timeout, a single `{"type": "error", "content": "Response timed
out. Please retry."}` line is appended and the stream closes.

---

## Webhook lifecycle: `POST /webhooks/stripe`

```
Stripe ── raw body + Stripe-Signature header ──▶ /webhooks/stripe
                                                       │
                                                       ▼
                                       PaymentService.verify_webhook
                                       (= StripeClient.verify_webhook,
                                        constructs+validates Event)
                                                       │
                                  bad sig?─────────────┴────► 400
                                                       │
                                                       ▼
                                       PaymentService.handle_webhook
                                         - dedupe by event.id
                                         - look up PaymentRecord by session_id
                                         - map event.type → PaymentStatus
                                              checkout.session.completed → SUCCEEDED
                                              .async_payment_failed       → FAILED
                                              .expired                    → EXPIRED
                                              payment_intent.payment_failed → FAILED
                                         - record.updated_at = now
                                                       │
                                                       ▼
                                                  {received: true}
```

The agent never charges directly during a turn. The flow is:

1. Agent calls `create_payment_session(...)` and returns the `url` to the user.
2. User pays on Stripe's hosted page (SCA/3DS handled by Stripe).
3. Stripe fires `checkout.session.completed` to `/webhooks/stripe`.
4. Next time the agent calls `get_payment_status(session_id)`, it sees
   `SUCCEEDED` and can confirm in chat.

---

## Key design decisions

### Why hosted/affiliate bookings instead of real PNRs?
Real bookings that actually charge and reserve at Hertz/Hilton/Lufthansa require
**signed commercial agreements** with each provider (or Amadeus production).
That's a commercial gate, not a technical one. The hosted/affiliate model
(used by Kayak, Skyscanner, Hopper, Google Flights' affiliate path) is the
only end-to-end-real path open to a developer without those contracts —
and it's a real booking, just completed on the partner's site, with
attribution earning us a commission.

### Why Stripe stays even though we don't charge for bookings?
For any service fee, concierge subscription, or premium upsell the operator
wants to collect directly. The Checkout pattern is the right one for a chat
agent: the agent hands the user a hosted URL, the user pays, the webhook
finalises server-side. No card data ever touches our server (PCI scope = 0).

### Why an in-process MCP server instead of stdio MCP?
The model-context-protocol spec assumes tools live in a separate process and
the agent talks to them over stdio. That decouples but adds latency, process
management, and serialization overhead. For a single-process FastAPI app
serving a chat UI, an in-process registry that exposes the same JSON-RPC
shape is functionally equivalent and dramatically simpler. The
`mcp/protocol.py` Pydantic models match the wire format so a future move to
real stdio MCP is a straight lift-and-shift.

### Why per-session orchestrators?
Memory is per-session because conversations aren't shared across users.
LLM + MCPServer are stateless and shared (cost: one LLM client object, one
tool registry). Sessions are evicted via TTL + LRU when `MAX_SESSIONS` is
exceeded — bounded memory without paying for a Redis/DB on day one.

### Why a custom `async_retry` instead of tenacity?
We need retry in exactly two places (LLM call, tool call), with consistent
log shape (`extra={"request_id": ...}`, `exc_info=True`). 25 lines, zero
deps, no learning curve.

### Why a sliding-window memory cap?
Long-running sessions otherwise grow unbounded — both memory and prompt
token cost. The window is small (default 50 messages, configurable). A
follow-up that wanted summary-compression instead can subclass `AgentMemory`
without touching the orchestrator.

### Why externalise the system prompt?
Three reasons: (1) it can be edited without a Python file change; (2) it's
loadable from disk for tests that need to verify prompt contents; (3) it
unblocks A/B-testing different prompts via env var.

### Why `StripeMockClient` instead of mocking `stripe.checkout.Session.create`?
Mocking at the SDK boundary couples tests to the SDK's surface and breaks
on SDK upgrades. The `StripeClient` / `StripeMockClient` protocol is OUR
boundary, owned by us, with a `simulate_completion` helper that builds
realistic webhook events for tests. Same pattern works for any future
provider (PayPal, Adyen) — implement the protocol, no test changes.

---

## Extension points

### Adding a new tool
1. Write a function in `travel_agent/tools/<name>.py` with simple typed args.
   Raise `ValueError` for bad input.
2. Re-export from `travel_agent/tools/__init__.py`.
3. Register it in `travel_agent/setup.py::build_mcp_server`.
4. Add tests in `tests/test_tools_<name>.py`.
5. If non-obvious, add guidance in `travel_agent/agent/prompts/system.md`.

### Adding a new LLM provider
1. Subclass `LLMProvider` in `travel_agent/agent/llm.py`. Implement both
   `generate_text` and `call_tool`.
2. Add a branch in `get_llm_provider`.
3. Add construction-smoke + tool-conversion tests in
   `tests/test_llm_providers.py`.

### Adding a new payment provider
1. Implement the `StripeClientProtocol` shape from
   `travel_agent/payments/stripe_client.py` — `create_checkout_session`,
   `retrieve_session`, `verify_webhook`.
2. Plug it into `build_stripe_client()` behind a new `STRIPE_MODE` value (or
   rename — e.g. `PAYMENT_PROVIDER`).
3. `PaymentService` doesn't change.

### Adding persistence (memory + payments)
Both `AgentMemory` and `PaymentService` store state behind interfaces. To
swap to Postgres/Redis:
- Subclass `AgentMemory` with DB-backed `add_message` / `get_messages` /
  `clear`.
- Swap the `_by_booking` / `_by_session` dicts in `PaymentService` for a
  small `PaymentStore` interface with the same methods (`get_by_booking`,
  `get_by_session`, `upsert`).

Both changes are localised — orchestrator, web server, and tools are
unaffected.

---

## Operational concerns

### Logging
- JSON-only via `JsonFormatter` (`travel_agent/config.py`).
- Every record carries `timestamp`, `level`, `message`, `module`, `function`.
- `request_id` and `session_id` are propagated via `extra={...}` on
  `logger.info/warning/error/exception` calls.
- PII (emails, digit runs ≥ 8) is redacted by `_redact_pii` in
  `orchestrator.py` before any field reaches Langfuse or chat error
  messages.

### Secrets
- All loaded from `.env` via `python-dotenv` (read once at import).
- `.gitignore` blocks `/.env` from the repo root; `.env.example` is the
  template.
- `Config.validate()` raises `ConfigError` when a required key for the
  current `STRIPE_MODE` is missing; `web_server.py` invokes it eagerly in
  `live` mode and refuses to start without all required keys.

### Sessions
- Keyed on the `X-Session-Id` request header; generated if absent.
- `SessionManager` holds a dict of `(timestamp, orchestrator)` per session.
- Evicted by TTL (`SESSION_TTL_SECONDS`) and LRU when over `MAX_SESSIONS`.
- Each session's memory is independent; LLM + MCPServer are shared.

### Observability
- Langfuse is optional (no keys → no-op). The wrapper handles SDK v2 and v3.
- One trace per agent turn (`name="agent-turn"`); one generation per LLM call
  (`name="llm-call"`, model + token counts).
- Failures in observability never break the turn — they're logged and the
  trace becomes `None`.

### Health / readiness
- `/healthz` is liveness — always 200 if the process responds.
- `/readyz` returns 503 if we're running on the `MockSessionManager`
  fallback (no LLM key), 200 otherwise.
- Docker `HEALTHCHECK` hits `/healthz` every 30 s.

### CI
- `.github/workflows/ci.yml` runs `pytest --cov=travel_agent
  --cov-fail-under=70` on Python 3.11 + 3.12, plus a `docker build` job
  that depends on the tests passing.
