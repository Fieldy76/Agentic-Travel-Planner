import pytest

from travel_agent.agent.retry import async_retry


async def test_async_retry_returns_first_success():
    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        return "ok"

    assert await async_retry(op, attempts=3, base_delay=0.001) == "ok"
    assert calls["n"] == 1


async def test_async_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return calls["n"]

    assert await async_retry(op, attempts=5, base_delay=0.001) == 3
    assert calls["n"] == 3


async def test_async_retry_raises_after_exhausting_attempts():
    async def op():
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        await async_retry(op, attempts=3, base_delay=0.001)
