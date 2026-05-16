import asyncio
import time

import pytest

from travel_agent.agent.cache import AsyncToolCache, ToolCache


def test_sync_cache_hit():
    cache = ToolCache(ttl_seconds=60)
    counter = {"n": 0}

    @cache.cached
    def f(x):
        counter["n"] += 1
        return x * 2

    assert f(3) == 6
    assert f(3) == 6
    assert counter["n"] == 1


def test_sync_cache_expires(monkeypatch):
    cache = ToolCache(ttl_seconds=1)
    counter = {"n": 0}

    @cache.cached
    def f(x):
        counter["n"] += 1
        return x

    f(1)
    # Move the clock past TTL by direct manipulation of internal cache.
    cache._cache[next(iter(cache._cache))] = (time.time() - 100, 1)
    f(1)
    assert counter["n"] == 2


def test_sync_cache_distinguishes_kwargs():
    cache = ToolCache(ttl_seconds=60)
    calls = []

    @cache.cached
    def f(a, b=1):
        calls.append((a, b))
        return (a, b)

    f(1, b=2)
    f(1, b=3)
    assert len(calls) == 2


async def test_async_cache_coalesces_concurrent_calls():
    cache = AsyncToolCache(ttl_seconds=60)
    counter = {"n": 0}

    @cache.cached
    async def slow(x):
        counter["n"] += 1
        await asyncio.sleep(0.05)
        return x * 2

    results = await asyncio.gather(slow(5), slow(5), slow(5))
    assert results == [10, 10, 10]
    assert counter["n"] == 1


async def test_async_cache_invalidate():
    cache = AsyncToolCache(ttl_seconds=60)

    @cache.cached
    async def f(x):
        return x

    await f(1)
    await cache.invalidate()
    assert cache._cache == {}
