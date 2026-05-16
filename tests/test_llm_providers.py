"""Sanity-check LLM provider construction + dispatcher."""

import pytest

from travel_agent.agent import llm as llm_mod
from travel_agent.agent.llm import (
    AnthropicProvider,
    GoogleProvider,
    LLMProvider,
    OpenAIProvider,
    get_llm_provider,
)


def test_get_llm_provider_dispatch():
    assert isinstance(get_llm_provider("openai", "sk-x"), OpenAIProvider)
    assert isinstance(get_llm_provider("anthropic", "sk-x"), AnthropicProvider)
    assert isinstance(get_llm_provider("google", "sk-x"), GoogleProvider)


def test_get_llm_provider_unknown():
    with pytest.raises(ValueError):
        get_llm_provider("phrenology", "sk-x")


def test_provider_base_class():
    p = OpenAIProvider("sk-x")
    assert isinstance(p, LLMProvider)


def test_google_model_cache_key_isolation():
    p = GoogleProvider("sk-x")
    m_a = p._model_for("system A")
    m_a2 = p._model_for("system A")
    m_b = p._model_for("system B")
    assert m_a is m_a2
    assert m_a is not m_b


async def test_openai_tool_call_handles_malformed_json(monkeypatch):
    """Regression: malformed JSON in tool args must surface as an error payload, not crash the loop."""
    from types import SimpleNamespace

    class FakeChoice:
        def __init__(self, msg):
            self.message = msg

    class FakeResponse:
        def __init__(self, msg):
            self.choices = [FakeChoice(msg)]

    class FakeToolCall:
        def __init__(self):
            self.id = "tc_1"
            self.function = SimpleNamespace(name="fake", arguments="not-json{")

    class FakeMessage:
        def __init__(self):
            self.content = None
            self.tool_calls = [FakeToolCall()]

    class FakeChat:
        def __init__(self):
            self.completions = self
        async def create(self, **kw):
            return FakeResponse(FakeMessage())

    p = OpenAIProvider("sk-x")
    p.client = SimpleNamespace(chat=FakeChat())
    response = await p.call_tool([], [])
    assert response["tool_calls"][0]["arguments"]["__error__"].startswith("Malformed JSON")


def test_langfuse_flush_is_safe_when_disabled(monkeypatch):
    monkeypatch.setattr(llm_mod, "LANGFUSE_ENABLED", False)
    monkeypatch.setattr(llm_mod, "langfuse_client", None)
    # Should not raise even though langfuse is disabled.
    llm_mod.langfuse_flush()
