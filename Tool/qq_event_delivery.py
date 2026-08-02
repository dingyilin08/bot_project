"""QQ management-event message delivery helpers."""

import asyncio
from typing import Awaitable, Callable, TypeVar


_ResultT = TypeVar("_ResultT")


async def send_event_with_retry(
    send_once: Callable[[], Awaitable[_ResultT]],
    *,
    attempts: int = 3,
    initial_delay: float = 0.5,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> _ResultT:
    """Send an event response with bounded exponential-backoff retries."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if initial_delay < 0:
        raise ValueError("initial_delay cannot be negative")

    delay = initial_delay
    for attempt in range(1, attempts + 1):
        try:
            return await send_once()
        except Exception:
            if attempt == attempts:
                raise
            await sleep(delay)
            delay *= 2

    raise RuntimeError("unreachable retry state")
