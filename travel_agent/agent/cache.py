import asyncio
import functools
import hashlib
import json
import threading
import time
from typing import Any, Dict, Tuple


def _make_key(name: str, args: tuple, kwargs: dict) -> str:
    """Deterministic cache key — JSON dump with sorted keys, hashed."""
    try:
        payload = json.dumps(
            {"args": list(args), "kwargs": kwargs},
            sort_keys=True,
            default=str,
        )
    except (TypeError, ValueError):
        payload = repr((args, sorted(kwargs.items())))
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"{name}:{digest}"


class ToolCache:
    """Thread-safe in-memory cache for sync tool calls with TTL eviction."""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def cached(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = _make_key(func.__name__, args, kwargs)
            now = time.time()
            with self._lock:
                hit = self._cache.get(key)
                if hit and now - hit[0] < self._ttl:
                    return hit[1]
            result = func(*args, **kwargs)
            with self._lock:
                self._cache[key] = (time.time(), result)
            return result

        return wrapper

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()


class AsyncToolCache:
    """Async-safe in-memory cache with TTL eviction. Coalesces concurrent calls."""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
        self._inflight: Dict[str, asyncio.Future] = {}

    def cached(self, func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            key = _make_key(func.__name__, args, kwargs)
            now = time.time()
            async with self._lock:
                hit = self._cache.get(key)
                if hit and now - hit[0] < self._ttl:
                    return hit[1]
                inflight = self._inflight.get(key)
                if inflight is None:
                    inflight = asyncio.get_running_loop().create_future()
                    self._inflight[key] = inflight
                    owner = True
                else:
                    owner = False

            if not owner:
                return await inflight

            try:
                result = await func(*args, **kwargs)
            except Exception as exc:
                async with self._lock:
                    self._inflight.pop(key, None)
                inflight.set_exception(exc)
                raise
            async with self._lock:
                self._cache[key] = (time.time(), result)
                self._inflight.pop(key, None)
            inflight.set_result(result)
            return result

        return wrapper

    async def invalidate(self) -> None:
        async with self._lock:
            self._cache.clear()


global_tool_cache = ToolCache()
global_async_tool_cache = AsyncToolCache()
