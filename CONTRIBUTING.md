# Contributing

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env  # fill in keys you need
```

You only need one of `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` to
get the agent running. For local dev without Stripe credentials, set
`STRIPE_MODE=mock` in `.env`.

## Running the app

```bash
# Web (chat UI on http://localhost:5000)
uvicorn web_server:app --reload --port 5000

# CLI
python -m travel_agent.cli
```

## Tests

```bash
pytest                                              # full suite
pytest tests/test_orchestrator.py                   # one file
pytest --cov=travel_agent --cov-report=term-missing # with coverage
```

Coverage target is **≥70%**, enforced in CI.

Tests use:
- `pytest-asyncio` (auto mode — `async def test_*` works without a marker)
- `respx` for mocking httpx calls (Amadeus, Open-Meteo)
- `freezegun` for deterministic date/time

## Writing new tools

1. Add the function to `travel_agent/tools/<name>.py`. Tool parameters should be
   simple types (str / int / float / bool / list / dict) — the schema is inferred
   from the signature.
2. Validate inputs at the top of the function and raise `ValueError` on bad
   input — `MCPServer` surfaces those cleanly to the LLM.
3. Re-export it in `travel_agent/tools/__init__.py`.
4. Register it in `travel_agent/setup.py::build_mcp_server`.
5. Add tests in `tests/test_tools_<name>.py`.
6. Update the system prompt at `travel_agent/agent/prompts/system.md` if the
   LLM needs guidance on when to call it.

## Adding a new LLM provider

Subclass `LLMProvider` in `travel_agent/agent/llm.py`, then add a branch to
`get_llm_provider`. Implement both `generate_text` and `call_tool`.

## Booking architecture

This app does **not** charge customer cards for travel inventory itself.
Bookings complete on partner-hosted pages (Aviasales, Hotellook, RentalCars)
via affiliate deeplinks. Stripe Checkout (`create_payment_session`) is reserved
for *your own* charges — service fees, concierge subscriptions, etc.

See `docs/PRODUCTION_READINESS.md` for the full architecture rationale.

## Style

- One-line docstrings preferred. Reserve long explanations for non-obvious code.
- Use `logging.getLogger(__name__)`, never `print` (CI logs swallow stdout).
- Don't add deps without pinning bounds in `requirements.txt`.
