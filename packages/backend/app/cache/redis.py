from __future__ import annotations

import json

from app.cache.base import Cache


class RedisCache(Cache):
    def __init__(self, url: str) -> None:
        self._client = _get_client(url)

    def get(self, key: str):
        value = self._client.get(key)
        if not value:
            return None
        return json.loads(value)

    def set(self, key: str, value, ttl_seconds: int) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        self._client.setex(key, ttl_seconds, payload)


def _get_client(url: str):
    try:
        import redis  # type: ignore
    except Exception as exc:
        raise RuntimeError("Redis cache selected but redis package is not installed") from exc
    return redis.from_url(url, decode_responses=True)
