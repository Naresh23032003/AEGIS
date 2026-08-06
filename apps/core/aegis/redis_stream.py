"""Shared Redis client and stream key for event fan-out.

plan/01-architecture.md: Redis Streams is the event transport. `aegis:events`
carries every envelope; core-api tails it for the WS fanout (plan/02).
"""

from __future__ import annotations

import os

import redis.asyncio as redis

STREAM_KEY = "aegis:events"

_client: redis.Redis | None = None


def redis_url() -> str:
    url = os.environ.get("REDIS_URL")
    if not url:
        raise RuntimeError("REDIS_URL is not set")
    return url


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(redis_url(), decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
