import pytest

from travel_agent.payments import PaymentService, build_stripe_client
from travel_agent.payments.models import CheckoutRequest, PaymentStatus
from travel_agent.payments.stripe_client import StripeMockClient


async def _make_service():
    client = build_stripe_client()  # mock mode per conftest
    return PaymentService(client, app_url="http://localhost:5000"), client


async def test_create_session_returns_url_and_pending():
    svc, _ = await _make_service()
    req = CheckoutRequest(amount=10.5, currency="usd", description="Fee",
                          customer_email="a@b.co", booking_id="bk_a")
    resp = await svc.create_checkout(req)
    assert resp.status == PaymentStatus.PENDING
    assert resp.url.startswith("https://mock.stripe.test/")
    assert resp.booking_id == "bk_a"


async def test_idempotency_same_booking_id():
    svc, _ = await _make_service()
    req = CheckoutRequest(amount=10, currency="usd", description="x",
                          customer_email="a@b.co", booking_id="bk_idem")
    r1 = await svc.create_checkout(req)
    r2 = await svc.create_checkout(req)
    assert r1.session_id == r2.session_id


async def test_different_booking_ids_different_sessions():
    svc, _ = await _make_service()
    req1 = CheckoutRequest(amount=10, currency="usd", description="x",
                           customer_email="a@b.co", booking_id="bk_1")
    req2 = CheckoutRequest(amount=10, currency="usd", description="x",
                           customer_email="a@b.co", booking_id="bk_2")
    r1 = await svc.create_checkout(req1)
    r2 = await svc.create_checkout(req2)
    assert r1.session_id != r2.session_id


async def test_webhook_completion_updates_status():
    svc, client = await _make_service()
    req = CheckoutRequest(amount=42, currency="usd", description="x",
                          customer_email="a@b.co", booking_id="bk_w")
    resp = await svc.create_checkout(req)
    event = client.simulate_completion(resp.session_id, status="complete", payment_status="paid")
    await svc.handle_webhook(event)
    status = await svc.get_status(resp.session_id)
    assert status["status"] == "succeeded"
    assert status["amount_paid"] == 42.0


async def test_webhook_replay_idempotent():
    svc, client = await _make_service()
    req = CheckoutRequest(amount=10, currency="usd", description="x",
                          customer_email="a@b.co", booking_id="bk_r")
    resp = await svc.create_checkout(req)
    event = client.simulate_completion(resp.session_id, status="complete", payment_status="paid")
    await svc.handle_webhook(event)
    await svc.handle_webhook(event)  # replay
    status = await svc.get_status(resp.session_id)
    assert status["status"] == "succeeded"


async def test_webhook_failed_payment():
    svc, client = await _make_service()
    req = CheckoutRequest(amount=10, currency="usd", description="x",
                          customer_email="a@b.co", booking_id="bk_f")
    resp = await svc.create_checkout(req)
    event = client.simulate_completion(resp.session_id, status="open", payment_status="failed")
    await svc.handle_webhook(event)
    status = await svc.get_status(resp.session_id)
    assert status["status"] == "failed"


async def test_unknown_session_status():
    svc, _ = await _make_service()
    status = await svc.get_status("cs_mock_does_not_exist")
    assert status["status"] == "unknown"


def test_request_rejects_invalid_amount():
    with pytest.raises(Exception):
        CheckoutRequest(amount=0, currency="usd", description="x",
                        customer_email="a@b.co", booking_id="bk_bad")


def test_request_rejects_bad_currency():
    with pytest.raises(Exception):
        CheckoutRequest(amount=10, currency="xxx", description="x",
                        customer_email="a@b.co", booking_id="bk_bad")


def test_request_rejects_bad_email():
    with pytest.raises(Exception):
        CheckoutRequest(amount=10, currency="usd", description="x",
                        customer_email="not-an-email", booking_id="bk_bad")


async def test_create_payment_session_tool_validation():
    from travel_agent.tools.payment import create_payment_session, reset_payment_service
    reset_payment_service()
    bad = await create_payment_session(amount=-5, currency="usd", description="x",
                                       customer_email="a@b.co", booking_id="bk_validate")
    assert bad.get("error") == "validation_error"


async def test_create_payment_session_tool_happy_path():
    from travel_agent.tools.payment import create_payment_session, reset_payment_service
    reset_payment_service()
    r = await create_payment_session(amount=12.0, currency="usd", description="x",
                                     customer_email="a@b.co", booking_id="bk_tool_happy")
    assert r["status"] == "pending"
    assert "url" in r


async def test_mock_client_verify_webhook_parses_json():
    client = StripeMockClient()
    event = client.verify_webhook(b'{"id": "evt_1", "type": "checkout.session.completed"}', "any-sig")
    assert event["id"] == "evt_1"
