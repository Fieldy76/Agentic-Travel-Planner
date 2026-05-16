import asyncio
import io
import time

import pytest
from fastapi.testclient import TestClient

import web_server


@pytest.fixture
def client():
    return TestClient(web_server.app)


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_empty_message_rejected(client):
    r = client.post("/api/chat", data={"message": "   "})
    assert r.status_code == 400


def test_upload_too_large_rejected(client, monkeypatch):
    from travel_agent.config import Config
    monkeypatch.setattr(Config, "MAX_UPLOAD_MB", 1)
    big = b"X" * (1 * 1024 * 1024 + 100)
    r = client.post(
        "/api/chat",
        data={"message": "hi"},
        files={"file": ("big.pdf", big, "application/pdf")},
    )
    assert r.status_code == 413


def test_upload_bad_magic_rejected(client):
    r = client.post(
        "/api/chat",
        data={"message": "hi"},
        files={"file": ("fake.pdf", b"NOT_A_PDF", "application/pdf")},
    )
    assert r.status_code == 415


def test_upload_disallowed_mime(client):
    r = client.post(
        "/api/chat",
        data={"message": "hi"},
        files={"file": ("evil.exe", b"MZ\x90\x00", "application/x-msdownload")},
    )
    assert r.status_code == 415


async def test_session_isolation():
    a = await web_server.sessions.get_or_create("sess-A")
    b = await web_server.sessions.get_or_create("sess-B")
    a2 = await web_server.sessions.get_or_create("sess-A")
    assert a is a2
    assert a is not b
    assert a.memory is not b.memory


def test_webhook_rejects_bad_payload(client):
    r = client.post("/webhooks/stripe", content=b"not json", headers={"stripe-signature": "x"})
    assert r.status_code == 400
