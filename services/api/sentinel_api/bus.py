"""Event bus: Redis-protocol pub/sub (Valkey) for real-time fan-out to WebSocket clients.

Durable state lives in Postgres; the bus only carries "something changed"
notifications. Swapping to Kafka for statewide scale means replacing this one
module — publish()/subscribe() are the whole contract.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import redis.asyncio as redis

from .config import get_settings

_client: redis.Redis | None = None


async def init_bus() -> None:
    global _client
    _client = redis.from_url(get_settings().redis_url, decode_responses=True)
    await _client.ping()


async def close_bus() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None


def _default(o: Any):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


async def publish(event_type: str, payload: dict[str, Any]) -> None:
    if _client is None:
        return
    msg = {"type": event_type, "at": datetime.now(timezone.utc).isoformat(), **payload}
    await _client.publish(get_settings().bus_channel, json.dumps(msg, default=_default))


async def subscribe() -> AsyncIterator[str]:
    assert _client is not None
    pubsub = _client.pubsub()
    channel = get_settings().bus_channel
    await pubsub.subscribe(channel)
    try:
        async for m in pubsub.listen():
            if m.get("type") == "message":
                yield m["data"]
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
