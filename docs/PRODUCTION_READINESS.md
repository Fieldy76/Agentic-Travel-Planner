# Agentic Travel Planner — Production-Readiness Plan

> **Status: ✅ Complete.** All 6 phases and the in-flight Phase 2.5 (real APIs)
> have shipped. Test suite is 98 tests passing at **75 % coverage** (gate at
> 70 %). For the day-to-day architecture, see
> [`ARCHITECTURE.md`](ARCHITECTURE.md). This document is the historical record
> of *what* was done and *why* — keep it for context when revisiting decisions.

## Context

Goal: take this repository from "demo / educational project" to **production-ready**: clean, bug-free, secure, properly tested, with a real payment integration.

Decisions locked in:
- **Delete `annotated/`** (single source of truth). ✅
- **Full test coverage** with `pytest-asyncio` (target ≥70%). ✅ 75 %.
- **Stripe stays**, but the payment flow is rebuilt around **Stripe Checkout Sessions + webhooks** (the right pattern for a chat agent — no PCI scope, real SCA/3DS, real money). ✅
- **Real APIs everywhere** (added after initial scope): Amadeus for flights + hotels search, Open-Meteo (geocoded) for weather, hosted/affiliate booking via Aviasales / Hotellook / RentalCars + Travelpayouts. ✅ — see Phase 2.5.

The plan is organized as 6 sequential phases. Each phase has acceptance criteria — we only moved to the next phase when the previous one passed. Phases 1–2 were small bug/security fixes; Phase 3 (payments) was the biggest single change; Phase 4 (refactor) made Phase 5 (tests) cheap; Phase 6 was hygiene & deploy. Phase 2.5 was inserted mid-stream when the booking architecture had to change.

---

## Phase 1 — Stop-the-bleed bug fixes ✅

Self-contained crash/correctness bugs. Each is a few lines.

| # | File:Line | Fix |
|---|-----------|-----|
| 1.1 | `verify_langfuse.py:69` | Replace `os.times().elapsed` with `time.time()` (script crashes today) |
| 1.2 | `travel_agent/tools/weather.py:50` | Stop using `Config.WEATHER_API_KEY` as the URL. Hardcode `https://api.open-meteo.com/v1/forecast` and drop the env var (Open-Meteo needs no key) |
| 1.3 | `travel_agent/tools/cars.py:24` | Compute `days` from `start_date`/`end_date` via `datetime.strptime`, not hardcoded `3` |
| 1.4 | `travel_agent/tools/flights.py:162` | Delete the `if origin.upper() == "NOW":` debug branch |
| 1.5 | `travel_agent/tools/flights.py:165` | Replace fragile `f"{date[:-2]}{int(date[-2:]) + 1:02d}"` with `datetime + timedelta(days=1)` |
| 1.6 | `travel_agent/agent/llm.py:319` | Guard `genai.protos.Type[v['type'].upper()]` against `KeyError`; default to `STRING` |
| 1.7 | `travel_agent/agent/llm.py:189` | Wrap `json.loads(tc.function.arguments)` in try/except; on failure surface as tool error, don't crash the loop |
| 1.8 | `travel_agent/agent/orchestrator.py:257` | `if not response:` → `if response is None:` (empty dict was being treated as failure) |
| 1.9 | `travel_agent/tools/weather.py:60,66-68` | Wrap `httpx.get` in try/except; bounds-check `daily[...][0]` before indexing |

**Acceptance:** `python verify_langfuse.py` runs to completion. A car rental for `2026-06-01`→`2026-06-10` returns 9 days. `search_flights("XYZ", "ABC", "2026-01-31")` doesn't blow up the date math.

---

## Phase 2 — Security & concurrency hardening ✅

| # | File:Line | Fix |
|---|-----------|-----|
| 2.1 | `web_server.py:46` | CORS: replace `allow_origins=["*"]` with comma-split `ALLOWED_ORIGINS` env var (no wildcard in prod) |
| 2.2 | `web_server.py:148` | Enforce 25 MB upload limit; reject before reading body into memory |
| 2.3 | `web_server.py:149` | Whitelist MIME types (`application/pdf`, DOCX, `text/plain`); sniff magic bytes via `python-magic`, don't trust client header |
| 2.4 | `web_server.py:157` | Wrap streaming generator in `asyncio.wait_for(..., timeout=300)`; on timeout yield a clean SSE error |
| 2.5 | `travel_agent/tools/flights.py:115` | Replace `random.randint` booking refs with `secrets.token_urlsafe(8).upper()` |
| 2.6 | `travel_agent/agent/orchestrator.py:151` | Redact PII from Langfuse metadata: strip emails, digit runs ≥8, the document body |
| 2.7 | `travel_agent/agent/orchestrator.py:406` | Generic user-facing error message; full traceback only to logger |
| 2.8 | `web_server.py:53,125` | Initialize `agent` before `uvicorn.run` (no startup-hook race); create a fresh `InMemoryMemory` per session (new `X-Session-Id` header or generated UUID) so users don't share history |
| 2.9 | `travel_agent/tools/flights.py:8-9` | Wrap `_amadeus_token_cache` mutation in an `asyncio.Lock`; refactor into a tiny `AmadeusTokenCache` class |
| 2.10 | `travel_agent/agent/cache.py` | Add `AsyncToolCache` (proper `async def wrapper`); `weather.py:7` switches to it; sync `ToolCache` kept only for sync tools |

**Acceptance:** `curl -H "Origin: http://evil"` is rejected. 100 MB upload returns 413. Two parallel chat sessions get independent histories. `pytest tests/test_security.py` (new, written in Phase 5) passes.

---

## Phase 3 — Stripe Checkout end-to-end rewrite ✅

This replaces the demo payment flow with a real production flow. Stays in Stripe.

### 3.1 Architecture (the new flow)

```
LLM tool call: create_payment_session(amount, currency, booking_metadata)
        │
        ▼
PaymentService.create_checkout_session()
   • stripe.checkout.Session.create(
        mode="payment",
        line_items=[{price_data, quantity}],
        success_url=APP_URL + "/payment/success?sid={CHECKOUT_SESSION_ID}",
        cancel_url=APP_URL + "/payment/cancel?sid={CHECKOUT_SESSION_ID}",
        metadata={booking_id, flight_id, ...},
        customer_email=...,
        payment_intent_data={ idempotency_key: booking_id }
     )
        │
        ▼
Tool returns hosted Stripe URL + session_id → user clicks in chat
        │
        ▼
User pays on Stripe-hosted page (cards / Apple Pay / Google Pay, SCA auto)
        │
        ▼
Stripe POST → POST /webhooks/stripe (signed)
   • stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
   • on "checkout.session.completed" → BookingService.finalize(metadata.booking_id)
   • on "checkout.session.expired" / "payment_failed" → mark booking cancelled
        │
        ▼
Agent polls BookingService (or webhook pushes to session store) → confirms in chat
```

### 3.2 New / changed files

- **`travel_agent/payments/__init__.py`** — package boundary.
- **`travel_agent/payments/stripe_client.py`** — `StripeClient` wraps `stripe` SDK. Centralizes `api_key`, retry, error mapping. Exposes:
  - `create_checkout_session(amount_cents, currency, customer_email, metadata, success_url, cancel_url) -> CheckoutSession`
  - `verify_webhook(payload: bytes, sig_header: str) -> stripe.Event` (raises on bad signature)
  - `retrieve_session(session_id) -> stripe.checkout.Session`
- **`travel_agent/payments/service.py`** — `PaymentService` is the business layer (provider-agnostic interface so future providers slot in). Owns idempotency, persistence of payment intent → booking_id mapping (in-memory dict for v1, behind a `PaymentStore` interface).
- **`travel_agent/payments/models.py`** — Pydantic models: `CheckoutRequest`, `CheckoutResponse`, `WebhookEvent`, `PaymentStatus` enum (`pending`, `succeeded`, `failed`, `cancelled`, `expired`).
- **`travel_agent/tools/payment.py`** — replaced. New tools:
  - `create_payment_session(amount, currency, customer_email, booking_id) -> {url, session_id, expires_at}`
  - `get_payment_status(session_id) -> {status, amount_paid, ...}`
  - Old `process_payment` removed (it was the hardcoded-card hack).
- **`web_server.py`** — add `POST /webhooks/stripe` route (raw body required; **not** behind JSON parsing). Verifies signature, dispatches to `PaymentService.handle_webhook(event)`.
- **`tests/test_payments.py`** — new (Phase 5).
- **`travel_agent/agent/orchestrator.py`** — system prompt updated: explain the new flow to the LLM (it must return the Checkout URL to the user, then call `get_payment_status` to confirm before finalizing booking).
- **`.env.example`** — add `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `APP_URL` (used for `success_url`/`cancel_url`).
- **`travel_agent/config.py`** — add the new keys; validate that webhook secret is set if `STRIPE_MODE=live`.

### 3.3 Idempotency, retries, errors

- Pass `idempotency_key=booking_id` to every Stripe write (`checkout.Session.create`). Re-running `create_payment_session` for the same booking returns the existing session, never double-charges.
- Wrap Stripe API calls in a small retry helper (3 tries, exponential backoff, only on `stripe.error.APIConnectionError` / `RateLimitError` — never on `CardError` or `InvalidRequestError`).
- Map Stripe errors → user-safe messages in `StripeClient._map_error`. Never leak `stripe.error.*` to chat output.
- Webhook handler must be idempotent (we'll receive duplicate `checkout.session.completed` in retries) — keyed on `event.id`, processed-events stored in `PaymentStore`.

### 3.4 What goes away

- `pm_card_visa` hardcoded test card — gone.
- `confirm=True` auto-confirmation — gone (Checkout handles confirmation).
- "mock if no Stripe key" silent fallback — gone (we fail loud at startup if `STRIPE_SECRET_KEY` missing). A separate `STRIPE_MODE=mock` env var explicitly opts into the mock path for local dev.

### 3.5 Acceptance

- End-to-end test mode: `stripe listen --forward-to localhost:8000/webhooks/stripe` running locally; agent creates session, test card `4242 4242 4242 4242` completes on hosted page, webhook fires, booking marked confirmed in `BookingService`, agent confirms in chat.
- 3DS test card `4000 0027 6000 3184` succeeds through SCA challenge.
- Failing card `4000 0000 0000 9995` (insufficient funds) → webhook fires with `checkout.session.async_payment_failed`, booking marked failed, agent tells user.
- Webhook with bad signature returns 400.
- Replaying the same webhook event twice produces one finalized booking.
- `pytest tests/test_payments.py` passes (mocks `stripe` SDK with `respx`-style fixtures).

---

## Phase 4 — Refactor & code quality ✅

Done after payments so the refactor doesn't fight an in-flight rewrite.

| # | Where | Change |
|---|-------|--------|
| 4.1 | `travel_agent/agent/orchestrator.py:23-141` | Move 120-line system prompt to `travel_agent/agent/prompts/system.md`, load on init |
| 4.2 | `travel_agent/agent/orchestrator.py:158-200` | Extract `DocumentProcessor` class to `travel_agent/agent/documents.py`; orchestrator just calls it. Document context goes to **system** prompt, not user message |
| 4.3 | `travel_agent/agent/orchestrator.py:245-255, 309-321` | Extract `_async_retry(coro_factory, *, attempts, base_delay)` helper; use for both LLM and tool retry |
| 4.4 | `travel_agent/agent/orchestrator.py:211,243,305` | All retry/turn caps move to `Config` (`MAX_TURNS`, `MAX_LLM_RETRIES`, `MAX_TOOL_RETRIES`) |
| 4.5 | `travel_agent/agent/llm.py` | New `travel_agent/agent/llm/` package: `base.py`, `openai.py`, `anthropic.py`, `google.py`, `schema.py` (single `SchemaBuilder`), `observability.py` (Langfuse decorator). Eliminates 3-way duplication of `generate_text` and tool-schema conversion |
| 4.6 | `travel_agent/agent/llm/google.py` | Cache `GenerativeModel` instances keyed on `(model_name, system_instruction)` — stop rebuilding every call (`llm.py:385-389`) |
| 4.7 | `travel_agent/agent/llm/*` | Replace all `print()` with `logging.getLogger(__name__)` |
| 4.8 | `travel_agent/agent/memory.py:26` | Sliding-window: keep last `MAX_MESSAGES` (configurable, default 50) |
| 4.9 | `travel_agent/cli.py` & `web_server.py` | Extract shared `travel_agent/setup.py::build_agent(provider) -> Agent` — kills the dup |
| 4.10 | `travel_agent/tools/*` | All tools take Pydantic models for args: `FlightSearchArgs`, `CarRentalArgs`, `WeatherArgs` with validators (IATA regex, date format, `start < end`, currency whitelist, amount > 0) |
| 4.11 | `travel_agent/tools/flights.py:84-97,132-142` | Hoist `airline_map` to module-level constant |
| 4.12 | `travel_agent/mcp/mcp_server.py:103` | `str(result)` → `json.dumps(result, default=str)`; validate required args from signature before invocation |
| 4.13 | Dead code sweep | Remove: `travel_agent/agent/cache.py:36` unused global, `travel_agent/mcp/protocol.py:27-30` unused `Tool`, `travel_agent/mcp/mcp_server.py:12,31-56` orphaned `tool_models`, `travel_agent/agent/orchestrator.py:343` unused `run()`, `debug_gemini.py` → `scripts/` |
| 4.14 | `travel_agent/config.py` | Convert to `@dataclass(frozen=True)`; `load_dotenv()` becomes lazy (`@functools.cache`); `validate()` raises `ConfigError` |

**Acceptance:** `ruff check .` clean; `mypy travel_agent/` clean; no `print()` in `travel_agent/`; same behavior as before refactor (verified by Phase 5 tests).

---

## Phase 5 — Test suite (target ≥70% coverage) ✅ (75 %)

| File | What it covers |
|------|----------------|
| `tests/conftest.py` | Shared fixtures: `mock_llm`, `in_memory_memory`, `mcp_server_with_tools`, `httpx_mock` (via `respx`), `stripe_mock`, frozen time via `freezegun` |
| `tests/test_llm_openai.py` | Init, `generate_text`, tool-call round-trip, malformed JSON arg handling (Phase 1 #7), error mapping |
| `tests/test_llm_anthropic.py` | Same |
| `tests/test_llm_google.py` | Same + schema-type fallback (Phase 1 #6) + model caching (Phase 4 #6) |
| `tests/test_schema_builder.py` | Cross-provider schema conversion correctness |
| `tests/test_mcp_server.py` | `register_tool` schema inference, async vs sync tools, missing-arg validation, JSON-result serialization |
| `tests/test_tools_flights.py` | Mock Amadeus via `respx`; token cache; book_flight idempotency; date arithmetic edge cases (month rollover) |
| `tests/test_tools_cars.py` | Day calculation, validation errors |
| `tests/test_tools_weather.py` | Real-API success + fallback to mock on httpx error, bounds-checked daily array |
| `tests/test_tools_datetime.py` | Timezone arg, deterministic via `freezegun` |
| `tests/test_payments.py` | `create_checkout_session` (mocked Stripe), webhook signature verification, idempotent webhook replay, 3DS success path (simulated), failed-payment path, mode=mock |
| `tests/test_orchestrator.py` | Replace existing weak tests. New: full agentic loop with mocked LLM + tools, document extraction (PDF/DOCX/TXT fixtures), retry/backoff assertions, max-turns cap, language consistency |
| `tests/test_documents.py` | PDF/DOCX/TXT extraction, oversize file rejection, malformed file handling |
| `tests/test_memory.py` | Sliding-window eviction, add/get round-trip |
| `tests/test_config.py` | Missing required keys raise; validation passes with full env |
| `tests/test_web_server.py` | Streaming response, file upload (size cap, MIME sniff), CORS rejection, session isolation, webhook route |
| `tests/test_security.py` | Booking-ref entropy, PII redaction, CORS, upload limits |

Dev deps added to new `requirements-dev.txt`: `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`, `freezegun`, `ruff`, `mypy`. `pytest.ini` sets `asyncio_mode = auto`, coverage gate at 70%.

**Acceptance:** `pytest --cov=travel_agent --cov-fail-under=70` green. CI runs it on every PR (Phase 6).

---

## Phase 6 — Hygiene, config, deploy ✅

| # | Change |
|---|--------|
| 6.1 | **Delete `annotated/`**. Update README to drop section 230-239 |
| 6.2 | Delete root-level `test_api_integration.py` (broken stale path); keep `tests/test_api_integration.py` only after rewriting it |
| 6.3 | Move `debug_gemini.py` and `verify_langfuse.py` to `scripts/`; remove from repo root |
| 6.4 | `.env.example` rewrite: rename `WEATHER_API_KEY` → drop (Open-Meteo no key); add `LLM_PROVIDER`, `STRIPE_MODE`, `STRIPE_WEBHOOK_SECRET`, `APP_URL`, `ALLOWED_ORIGINS`, `MAX_TURNS`, `MAX_MESSAGES`. Add comments per group |
| 6.5 | `.gitignore`: tighten `.env` → `/.env`; add `.coverage`, `htmlcov/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` |
| 6.6 | `requirements.txt`: pin upper bounds on `stripe`, `openai`, `anthropic`, `google-generativeai`, `fastapi`. Split out `requirements-dev.txt` |
| 6.7 | `Dockerfile`: pin via `ARG PYTHON_VERSION=3.11`; add `HEALTHCHECK` hitting new `GET /healthz`; switch `CMD` → `ENTRYPOINT`; drop `.env.example` from final stage; add non-root user check |
| 6.8 | `web_server.py`: add `GET /healthz` (returns `{status: "ok", version, langfuse_enabled, stripe_mode}`) and `GET /readyz` (verifies LLM provider + Stripe reachable) |
| 6.9 | Add `.github/workflows/ci.yml`: `ruff check`, `mypy`, `pytest --cov-fail-under=70`, `docker build`. Run on every PR + push to main |
| 6.10 | `README.md` rewrite: drop "framework-free" claim, fix Amadeus/mock-default note, add **Testing**, **Architecture**, **Deployment**, **Stripe webhook setup** sections; remove annotated/ section |
| 6.11 | Add `CONTRIBUTING.md`: dev setup, test running, lint, commit style |
| 6.12 | Production startup check: `Config.validate()` raises at startup if any **required-for-mode** key missing (LLM key, Stripe key when `STRIPE_MODE=live`, `STRIPE_WEBHOOK_SECRET`, `APP_URL`) |

**Acceptance:** Fresh clone → `cp .env.example .env` → fill in keys → `docker build && docker run` → `/healthz` returns 200, `/readyz` returns 200, end-to-end chat + payment flow works against Stripe test mode. CI green on a clean branch.

---

## Critical files

Core agent: `travel_agent/agent/orchestrator.py`, `travel_agent/agent/llm.py` → `llm/` package, `travel_agent/agent/memory.py`, `travel_agent/agent/cache.py`, `travel_agent/agent/documents.py` (new)
Tools: `travel_agent/tools/{flights,cars,weather,payment,datetime_tool}.py`
Payments: `travel_agent/payments/{stripe_client,service,models}.py` (new)
MCP: `travel_agent/mcp/mcp_server.py`, `travel_agent/mcp/protocol.py`
Web: `web_server.py`, `travel_agent/cli.py`, `travel_agent/setup.py` (new)
Config & infra: `travel_agent/config.py`, `.env.example`, `Dockerfile`, `requirements.txt`, `requirements-dev.txt` (new), `.github/workflows/ci.yml` (new)
Tests: every file in `tests/` + new `tests/conftest.py`

## Existing utilities to reuse (do not reinvent)

- `travel_agent/agent/cache.py::ToolCache` — extend with `AsyncToolCache`
- `travel_agent/agent/memory.py::AgentMemory` ABC — subclass for any future persistence
- `travel_agent/mcp/mcp_server.py::MCPServer.register_tool` — already infers schemas from signatures; extend rather than replicate
- `travel_agent/config.py::Config` — single source of truth for env; new code reads from here, never from `os.environ` directly

## End-to-end verification (run after Phase 6)

1. `rm -rf venv && python -m venv venv && source venv/bin/activate`
2. `pip install -r requirements.txt -r requirements-dev.txt`
3. `cp .env.example .env` → fill in `OPENAI_API_KEY` (or other LLM), `STRIPE_SECRET_KEY` (test), `STRIPE_WEBHOOK_SECRET`, `APP_URL=http://localhost:8000`, `ALLOWED_ORIGINS=http://localhost:3000`
4. `ruff check .` → clean. `mypy travel_agent/` → clean.
5. `pytest --cov=travel_agent --cov-fail-under=70` → green.
6. `stripe listen --forward-to localhost:8000/webhooks/stripe` (in one terminal)
7. `uvicorn web_server:app --reload` (in another)
8. Open the chat UI, plan a trip, book a flight, complete payment with `4242 4242 4242 4242`, verify the agent confirms the booking after webhook lands.
9. Repeat with 3DS card `4000 0027 6000 3184` and decline card `4000 0000 0000 9995`.
10. `docker build -t travel-agent . && docker run --rm -p 8000:8000 --env-file .env travel-agent` → `curl localhost:8000/healthz` returns 200.

## Out of scope

- Frontend rewrite (existing `static/` chat UI stays as-is; just gets a "Pay" link click-through).
- Persistent database (memory + payment store stay in-memory behind an interface — adding Postgres is a follow-up).
- Auth / multi-tenant (single-user demo → single-user prod; user accounts are a separate project).
- Production Langfuse host & retention policy (we just keep the integration correct).

---

## Phase 2.5 — Real APIs everywhere (booking via hosted/affiliate model) ✅

Added after the user clarified: "every call for booking hotels, cars, flights, and retrieve the weather has to be real with api."

The unavoidable constraint: real **search** APIs are accessible to developers; real **bookings that charge the user** require commercial agreements with each provider (Amadeus production, Hertz, Hilton, etc.). The honest production architecture is the same one used by Kayak, Skyscanner, and Hopper:

- **Real APIs** for search + data retrieval.
- **Hosted/affiliate pages** (Aviasales / Hotellook / RentalCars) for the final booking + payment.
- Travelpayouts affiliate marker for commission attribution.

### Implementation (done)

| Tool | Provider | What's real |
|------|----------|-------------|
| `get_forecast` | Open-Meteo (no key) | Live forecast within 14 days; historical archive proxy beyond; geocoding for any city |
| `search_flights` | Amadeus Self-Service | Real flight offers (test endpoint, no commercial agreement needed for read) |
| `book_flight` | Aviasales deeplink + Travelpayouts affiliate | Returns a real booking URL; user completes payment + ticketing on partner site |
| `search_hotels` (new) | Amadeus Hotel Search v3 | Real hotel offers; falls back to Hotellook deeplink on API failure |
| `rent_car` | RentalCars deeplink + Travelpayouts affiliate | Computed price estimate + real booking URL |

System prompt updated so the LLM explicitly explains the deeplink flow to the user and never claims to have charged a card. Stripe is reserved for explicit "service fee" scenarios.

### New env vars (added to `Config`)
- `TRAVELPAYOUTS_MARKER` (optional) — affiliate marker; URLs work without it but you forfeit attribution.
- `CARS_AFFILIATE_HOST` (default `https://tp.media/r`) — Travelpayouts redirect host.

---

## Payment-provider rationale (why Stripe over alternatives)

| Provider | Fit | Why / why not |
|---|---|---|
| **Stripe** ✅ | Best | Best Python SDK & docs; Payment Intents/Checkout handle SCA/3DS automatically; 135+ currencies; world-class test mode; robust webhooks; already wired up |
| PayPal/Braintree | Weak | Worse DX, more redirect glue, heavy SDKs, weaker test mode |
| Adyen | Overkill | Enterprise-grade but heavy onboarding, weaker docs, slow to integrate |
| Square | Wrong fit | Strong for in-person; weaker international, weaker for travel/variable amounts |
| Checkout.com | Niche | Strong in EU/MEA but smaller ecosystem, harder ramp-up |
| Paddle/LemonSqueezy (Merchant of Record) | Wrong fit | Designed for SaaS subscriptions; awkward for one-off variable charges |

For a **chat-based agent**, the additional architectural decision is to use **Stripe Checkout Sessions** (hosted) rather than collecting card details in-conversation. The agent returns a hosted URL to the user, Stripe handles all card UI / SCA / wallets, and webhooks confirm the booking server-side.
