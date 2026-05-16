"""Shared pytest fixtures."""

import os
import sys
from pathlib import Path

# Make sure tests run with deterministic, mock-mode config — even if a real
# .env is sitting in the repo (it is, for the user's local dev convenience).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ["STRIPE_MODE"] = "mock"
os.environ["APP_URL"] = "http://localhost:5000"
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5000")
os.environ.setdefault("MAX_UPLOAD_MB", "1")  # Small for tests
os.environ.setdefault("REQUEST_TIMEOUT_SECONDS", "5")
# Disable Langfuse for tests (no network)
os.environ.pop("LANGFUSE_SECRET_KEY", None)
os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
# Disable Amadeus so flight tests hit the mock branch unless explicitly mocked.
os.environ.pop("FLIGHT_API_KEY", None)
os.environ.pop("FLIGHT_API_SECRET", None)

import pytest

# Reload Config so the env above takes effect even if something imported earlier.
import importlib
import travel_agent.config as _cfg_mod
importlib.reload(_cfg_mod)


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def fresh_payment_service():
    """A fresh PaymentService in mock mode for each test."""
    from travel_agent.payments import PaymentService, build_stripe_client
    client = build_stripe_client()
    svc = PaymentService(client, app_url="http://localhost:5000")
    return svc, client


@pytest.fixture
def stub_llm():
    """An LLM stub that returns canned responses provided by the test."""
    class StubLLM:
        model = "stub"

        def __init__(self, scripted=None):
            self.scripted = list(scripted or [])
            self.calls = []

        def script(self, *responses):
            self.scripted.extend(responses)

        async def call_tool(self, messages, tools):
            self.calls.append({"messages": messages, "tools": tools})
            if not self.scripted:
                return {"content": "done", "tool_calls": None}
            return self.scripted.pop(0)

    return StubLLM()


@pytest.fixture
def empty_memory():
    from travel_agent.agent.memory import InMemoryMemory
    return InMemoryMemory(max_messages=20)
