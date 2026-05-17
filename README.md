# Agentic Travel Planner

A production-ready conversational travel agent. The LLM plans trips and books
real inventory through a small in-process MCP server that exposes tools for
flights, hotels, cars, weather, and payments.

- **Real APIs** for search: Amadeus Self-Service (flights + hotels),
  Open-Meteo with geocoding (weather, any city).
- **Real bookings** via hosted/affiliate model: agent generates a real booking
  URL on Aviasales (flights), Hotellook (hotels), RentalCars (cars). The user
  completes payment + ticketing on the partner's secure page. Same pattern as
  Kayak / Skyscanner / Hopper. Affiliate attribution via Travelpayouts.
- **Stripe Checkout** for any charges YOU collect (concierge / service fees).
  Sessions are idempotent and tied to webhooks; no card data ever touches your
  server. Mock mode for local dev.
- **Multi-provider LLM**: OpenAI, Anthropic, Google. Async throughout.
- **External MCP servers** (optional): set `GOOGLE_MAPS_API_KEY` and the
  `@modelcontextprotocol/server-google-maps` Node subprocess spins up at
  app startup, adding `maps_geocode`, `maps_directions`,
  `maps_distance_matrix`, `maps_places_search`, etc. to the LLM's tool
  belt — alongside the in-process flights/hotels/cars tools.
- **Per-session memory** with a sliding window cap; sessions isolated by
  `X-Session-Id`.
- **Production-grade web layer**: streaming NDJSON chat, file upload size
  and MIME-magic-byte validation, CORS allowlist, per-request timeout.
- **Chat UI**: auto-linkifies raw URLs and auto-opens partner booking pages
  (Aviasales / Hotellook / RentalCars / Stripe Checkout) in a new tab so the
  user goes straight to checkout. Per-conversation `X-Session-Id` keeps server
  memory aligned with the visible chat thread.
- **Observability** (optional): Langfuse traces every agent turn + LLM call,
  with PII redacted before logging.
- **Test suite** with ≥70% coverage (pytest-asyncio + respx + freezegun).

## Quick start

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in at least one LLM key.

uvicorn web_server:app --reload --port 5000
# open http://localhost:5000
```

`STRIPE_MODE=mock` in `.env` lets you run end-to-end without Stripe credentials.

CLI alternative:

```bash
python -m travel_agent.cli
```

## Architecture

```
                ┌──────────────┐
   user chat ──▶│ FastAPI app  │── streams NDJSON ──▶ browser/CLI
                │ web_server   │
                └──────┬───────┘
                       │ per-session
                       ▼
                ┌──────────────┐    ┌──────────────────────┐
                │ Orchestrator │◀──▶│ LLM (OpenAI / etc.)   │
                └──────┬───────┘    └──────────────────────┘
                       │ tool calls
                       ▼
                ┌──────────────┐
                │ MCPServer    │   register & call tools (sync/async)
                └──────┬───────┘
                       │
   ┌────────────┬──────┴──────┬──────────────┬──────────────┐
   ▼            ▼             ▼              ▼              ▼
flights      hotels         cars          weather       payments
(Amadeus)   (Amadeus)   (RentalCars     (Open-Meteo)  (Stripe
            Search v3)   deeplink)                    Checkout)
```

Full architecture — module reference, request and webhook lifecycles, design
decisions, and extension points — is in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Booking flow (important)

| Tool | Returns | Who completes the booking |
|------|---------|---------------------------|
| `book_flight` | Aviasales URL + intent_reference | User, on Aviasales |
| `search_hotels` | Hotel offers + Hotellook URL | User, on Hotellook |
| `rent_car` | Price estimate + RentalCars URL | User, on RentalCars |
| `create_payment_session` | Stripe Checkout URL | User, on stripe.com (for *your* service fees only) |

The system prompt at `travel_agent/agent/prompts/system.md` instructs the LLM
to surface booking URLs prominently and never to claim it charged a card.

## Testing

```bash
pip install -r requirements-dev.txt
pytest --cov=travel_agent --cov-report=term-missing
```

CI runs on every push + PR and fails below 70% coverage.

## Deployment

```bash
docker build -t travel-agent .
docker run --rm -p 5000:5000 --env-file .env travel-agent
curl http://localhost:5000/healthz   # liveness
curl http://localhost:5000/readyz    # readiness
```

For Stripe in prod:
1. Set `STRIPE_MODE=live`, real `STRIPE_SECRET_KEY` (sk_live_…), and
   `STRIPE_WEBHOOK_SECRET`.
2. Point Stripe webhooks to `https://<your-host>/webhooks/stripe`.
3. Lock `ALLOWED_ORIGINS` to your real domain (never `*`).

`Config.validate()` raises at startup if any required key is missing for the
selected mode.

## Documents

The chat endpoint accepts PDF / DOCX / TXT attachments (max `MAX_UPLOAD_MB`,
default 25). Text is extracted server-side via pypdf / python-docx and
inserted into the user message as a clearly-marked block (so the LLM treats it
as data, not as instructions).

## Further reading

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — module reference, request
  and webhook lifecycles, design decisions, and extension points.
- [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md) — the
  production-readiness plan: every change made to take this repo from
  demo to production-ready, organised by phase.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — dev setup, test running, conventions.

## License

MIT. See `LICENSE` for details.
