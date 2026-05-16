"""Small async retry helper used by the orchestrator for LLM + tool calls."""

import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def async_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    base_delay: float = 1.0,
    label: str = "operation",
    extra: dict | None = None,
) -> T:
    """Run an async callable with exponential-ish backoff.

    Raises the last exception if all attempts fail.
    """
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return await operation()
        except Exception as e:
            last_exc = e
            logger.warning(
                "%s failed (attempt %s/%s)", label, i + 1, attempts,
                extra=extra, exc_info=True,
            )
            if i == attempts - 1:
                break
            await asyncio.sleep(base_delay * (i + 1))
    assert last_exc is not None
    raise last_exc
