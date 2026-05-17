import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


class Config:
    """Configuration management for the Travel Agent."""

    # LLM
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

    # Flight (Amadeus)
    FLIGHT_API_KEY = os.getenv("FLIGHT_API_KEY")
    FLIGHT_API_SECRET = os.getenv("FLIGHT_API_SECRET")

    # Cars (Travelpayouts / RentalCars affiliate)
    TRAVELPAYOUTS_MARKER = os.getenv("TRAVELPAYOUTS_MARKER")
    CARS_AFFILIATE_HOST = os.getenv("CARS_AFFILIATE_HOST", "https://tp.media/r")

    # Payment (Stripe)
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
    STRIPE_MODE = os.getenv("STRIPE_MODE", "test").lower()  # test | live | mock

    # Observability (Langfuse)
    LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
    LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
    LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    # External MCP subprocesses (optional — registration is key-gated)
    # When set, the Google Maps MCP server (npx) is spawned at app startup and
    # its tools (maps_geocode / maps_directions / maps_places / ...) become
    # available to the LLM alongside the in-process tools.
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

    # Web server
    APP_URL = os.getenv("APP_URL", "http://localhost:5000")
    ALLOWED_ORIGINS = _split_csv(os.getenv("ALLOWED_ORIGINS", "http://localhost:5000"))
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
    REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "300"))
    SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
    MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "1000"))

    # Agent loop
    MAX_TURNS = int(os.getenv("MAX_TURNS", "10"))
    MAX_LLM_RETRIES = int(os.getenv("MAX_LLM_RETRIES", "3"))
    MAX_TOOL_RETRIES = int(os.getenv("MAX_TOOL_RETRIES", "3"))
    MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", "50"))

    @classmethod
    def has_llm_key(cls) -> bool:
        return bool(cls.OPENAI_API_KEY or cls.ANTHROPIC_API_KEY or cls.GOOGLE_API_KEY)

    @classmethod
    def validate(cls, *, require_stripe_live: bool | None = None) -> None:
        """Raise ConfigError if required configuration is missing.

        require_stripe_live: when True, also requires Stripe live keys.
        Defaults to True iff STRIPE_MODE=live.
        """
        missing: list[str] = []

        if not cls.has_llm_key():
            missing.append("OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY (at least one)")

        if require_stripe_live is None:
            require_stripe_live = cls.STRIPE_MODE == "live"

        if cls.STRIPE_MODE != "mock":
            if not cls.STRIPE_SECRET_KEY:
                missing.append("STRIPE_SECRET_KEY")
            if not cls.STRIPE_WEBHOOK_SECRET:
                missing.append("STRIPE_WEBHOOK_SECRET")
            if not cls.APP_URL:
                missing.append("APP_URL")

        if require_stripe_live:
            if cls.STRIPE_SECRET_KEY and not cls.STRIPE_SECRET_KEY.startswith("sk_live_"):
                missing.append("STRIPE_SECRET_KEY must start with sk_live_ when STRIPE_MODE=live")

        if missing:
            raise ConfigError("Missing required configuration: " + "; ".join(missing))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id
        if hasattr(record, "session_id"):
            log_record["session_id"] = record.session_id
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


_LOGGING_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging on the root logger (idempotent)."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.set_name("travel_agent_json")

    root = logging.getLogger()
    root.setLevel(level)

    for existing in list(root.handlers):
        if existing.get_name() == "travel_agent_json":
            root.removeHandler(existing)
    root.addHandler(handler)
    _LOGGING_CONFIGURED = True
