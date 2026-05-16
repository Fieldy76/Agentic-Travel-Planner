import logging

import pytest

from travel_agent.config import Config, ConfigError, _split_csv, setup_logging


def test_split_csv_handles_empty_and_whitespace():
    assert _split_csv("") == []
    assert _split_csv(None) == []
    assert _split_csv("a, b , c") == ["a", "b", "c"]


def test_validate_raises_when_no_llm_key(monkeypatch):
    monkeypatch.setattr(Config, "OPENAI_API_KEY", None)
    monkeypatch.setattr(Config, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(Config, "GOOGLE_API_KEY", None)
    monkeypatch.setattr(Config, "STRIPE_MODE", "mock")
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        Config.validate()


def test_validate_requires_stripe_keys_in_test_mode(monkeypatch):
    monkeypatch.setattr(Config, "OPENAI_API_KEY", "sk_test_x")
    monkeypatch.setattr(Config, "STRIPE_MODE", "test")
    monkeypatch.setattr(Config, "STRIPE_SECRET_KEY", None)
    monkeypatch.setattr(Config, "STRIPE_WEBHOOK_SECRET", None)
    with pytest.raises(ConfigError, match="STRIPE_SECRET_KEY"):
        Config.validate()


def test_validate_passes_in_mock_mode_with_llm_key(monkeypatch):
    monkeypatch.setattr(Config, "OPENAI_API_KEY", "sk_test_x")
    monkeypatch.setattr(Config, "STRIPE_MODE", "mock")
    Config.validate()  # no raise


def test_live_mode_requires_sk_live_key(monkeypatch):
    monkeypatch.setattr(Config, "OPENAI_API_KEY", "sk_test_x")
    monkeypatch.setattr(Config, "STRIPE_MODE", "live")
    monkeypatch.setattr(Config, "STRIPE_SECRET_KEY", "sk_test_oops")
    monkeypatch.setattr(Config, "STRIPE_WEBHOOK_SECRET", "whsec_x")
    monkeypatch.setattr(Config, "APP_URL", "https://prod.example.com")
    with pytest.raises(ConfigError, match="sk_live_"):
        Config.validate()


def test_setup_logging_is_idempotent():
    setup_logging()
    setup_logging()
    handlers = [h for h in logging.getLogger().handlers if h.get_name() == "travel_agent_json"]
    assert len(handlers) == 1


def test_has_llm_key_reads_class_attrs(monkeypatch):
    monkeypatch.setattr(Config, "OPENAI_API_KEY", "x")
    assert Config.has_llm_key() is True
    monkeypatch.setattr(Config, "OPENAI_API_KEY", None)
    monkeypatch.setattr(Config, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(Config, "GOOGLE_API_KEY", None)
    assert Config.has_llm_key() is False
