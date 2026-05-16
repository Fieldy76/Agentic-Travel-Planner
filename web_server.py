import asyncio
import json
import logging
import os
import sys
import time
import uuid
from typing import AsyncGenerator, Dict, Optional, Tuple

import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from travel_agent.agent.memory import InMemoryMemory
from travel_agent.agent.orchestrator import AgentOrchestrator
from travel_agent.config import Config, ConfigError, setup_logging
from travel_agent.payments.stripe_client import PaymentProviderError
from travel_agent.setup import build_llm, build_mcp_server
from travel_agent.tools.payment import get_payment_service

setup_logging()
logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}

MAGIC_BYTES = {
    "application/pdf": b"%PDF-",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK\x03\x04",
}


def _sniff(content: bytes, declared_mime: str) -> bool:
    if declared_mime not in ALLOWED_UPLOAD_MIMES:
        return False
    expected = MAGIC_BYTES.get(declared_mime)
    if expected is None:
        try:
            content[:1024].decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return content.startswith(expected)


class SessionManager:
    """Per-session AgentOrchestrator with its own fresh InMemoryMemory.

    Shared LLM + MCPServer (both stateless) keep cost down; each session gets
    its own memory so users don't see each other's conversation history.
    """

    def __init__(self, llm, server, *, max_sessions: int, ttl_seconds: int):
        self._llm = llm
        self._server = server
        self._max_sessions = max_sessions
        self._ttl = ttl_seconds
        self._sessions: Dict[str, Tuple[float, AgentOrchestrator]] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, session_id: str) -> AgentOrchestrator:
        async with self._lock:
            self._evict_expired()
            existing = self._sessions.get(session_id)
            if existing is not None:
                _, agent = existing
                self._sessions[session_id] = (time.time(), agent)
                return agent
            if len(self._sessions) >= self._max_sessions:
                oldest_sid = min(self._sessions.items(), key=lambda kv: kv[1][0])[0]
                del self._sessions[oldest_sid]
            agent = AgentOrchestrator(self._llm, self._server, InMemoryMemory())
            self._sessions[session_id] = (time.time(), agent)
            logger.info("Created session %s (total=%d)", session_id, len(self._sessions))
            return agent

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [sid for sid, (ts, _) in self._sessions.items() if now - ts > self._ttl]
        for sid in expired:
            del self._sessions[sid]


class MockSessionManager:
    """Stand-in when no LLM provider is configured."""

    async def get_or_create(self, session_id: str):  # noqa: ARG002
        return _MockAgent()


class _MockAgent:
    async def run_generator(self, user_input, file_data=None, mime_type=None, request_id="mock"):
        yield {"type": "message", "content": f"(mock) received: {user_input!r}"}
        if file_data:
            yield {"type": "message", "content": f"(mock) file: {len(file_data)} bytes"}
        yield {"type": "tool_call", "name": "mock_tool", "arguments": {"query": "test"}}
        await asyncio.sleep(0)
        yield {"type": "tool_result", "name": "mock_tool", "content": "Mock result", "is_error": False}
        yield {"type": "message", "content": "This is a mock response (no LLM key configured)."}


def _build_session_manager() -> SessionManager | MockSessionManager:
    # In production (STRIPE_MODE=live) we refuse to start with missing config —
    # we want a noisy crash, not a silent MockAgent serving real users.
    if Config.STRIPE_MODE == "live":
        Config.validate()

    llm = build_llm()
    if llm is None:
        logger.warning("Falling back to MockAgent")
        return MockSessionManager()
    return SessionManager(
        llm,
        build_mcp_server(),
        max_sessions=Config.MAX_SESSIONS,
        ttl_seconds=Config.SESSION_TTL_SECONDS,
    )


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.ALLOWED_ORIGINS or ["http://localhost:5000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

sessions: SessionManager | MockSessionManager = _build_session_manager()


def get_session_id(x_session_id: Optional[str] = Header(default=None)) -> str:
    return x_session_id or str(uuid.uuid4())


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/healthz")
async def healthz():
    """Liveness probe — does the process respond?"""
    return {
        "status": "ok",
        "stripe_mode": Config.STRIPE_MODE,
        "llm_configured": Config.has_llm_key(),
    }


@app.get("/readyz")
async def readyz():
    """Readiness probe — is the app configured to serve requests?

    Returns 200 only if a real LLM provider is wired up (i.e. not running on the
    MockAgent fallback). Stripe is not pinged on every check to avoid hammering
    their API — Config.validate() at startup catches misconfiguration there.
    """
    if isinstance(sessions, MockSessionManager):
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "no LLM provider configured"},
        )
    return {"status": "ready", "stripe_mode": Config.STRIPE_MODE}


@app.post("/api/chat")
async def chat(
    request: Request,
    message: str = Form(...),
    file: UploadFile = File(None),
    session_id: str = Depends(get_session_id),
):
    """Streaming chat (NDJSON). Per-session memory keyed by X-Session-Id header."""
    if not message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    file_data: Optional[bytes] = None
    mime_type: Optional[str] = None

    if file is not None:
        max_bytes = Config.MAX_UPLOAD_MB * 1024 * 1024
        declared_size = request.headers.get("content-length")
        if declared_size and int(declared_size) > max_bytes * 2:
            raise HTTPException(status_code=413, detail=f"Upload exceeds {Config.MAX_UPLOAD_MB} MB")

        content = await file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise HTTPException(status_code=413, detail=f"Upload exceeds {Config.MAX_UPLOAD_MB} MB")

        declared_mime = file.content_type or "application/octet-stream"
        if not _sniff(content, declared_mime):
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported or malformed file: {declared_mime}. Allowed: PDF, DOCX, TXT.",
            )
        file_data = content
        mime_type = declared_mime
        logger.info("Upload accepted: %s (%s, %d bytes)", file.filename, mime_type, len(content))

    agent = await sessions.get_or_create(session_id)
    timeout = Config.REQUEST_TIMEOUT_SECONDS

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async with asyncio.timeout(timeout):
                async for event in agent.run_generator(
                    message, file_data=file_data, mime_type=mime_type, request_id=session_id
                ):
                    yield json.dumps(event) + "\n"
        except asyncio.TimeoutError:
            logger.warning("Streaming response timed out after %ss (session=%s)", timeout, session_id)
            yield json.dumps({"type": "error", "content": "Response timed out. Please retry."}) + "\n"
        except Exception:
            logger.exception("Unhandled error in event stream (session=%s)", session_id)
            yield json.dumps({"type": "error", "content": "Internal error. Please retry."}) + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers={"X-Session-Id": session_id},
    )


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Stripe webhook endpoint. Verifies signature and dispatches to PaymentService.

    Stripe requires the raw request body for signature verification; we must
    NOT parse JSON first.
    """
    sig_header = request.headers.get("stripe-signature", "")
    payload = await request.body()
    try:
        service = get_payment_service()
        event = service.verify_webhook(payload, sig_header)
    except PaymentProviderError as e:
        logger.warning("Stripe webhook rejected: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    await service.handle_webhook(event)
    return {"received": True}


@app.get("/payment/success")
async def payment_success(sid: str):
    return JSONResponse({"status": "ok", "session_id": sid, "message": "Payment received. Return to chat."})


@app.get("/payment/cancel")
async def payment_cancel(sid: str):
    return JSONResponse({"status": "cancelled", "session_id": sid, "message": "Payment cancelled."})


@app.exception_handler(ConfigError)
async def config_error_handler(_: Request, exc: ConfigError):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


if __name__ == "__main__":
    uvicorn.run("web_server:app", host="0.0.0.0", port=5000, reload=True)
