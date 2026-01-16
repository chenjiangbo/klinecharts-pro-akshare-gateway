from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TypeVar

from klinecharts_pro_akshare_gateway.cache.base import Cache

T = TypeVar("T")


@dataclass
class _Entry:
    value: object
    expires_at: float


class MemoryCache(Cache):
    def __init__(self) -> None:
        self._store: dict[str, _Entry] = {}

    def get(self, key: str) -> T | None:
        entry = self._store.get(key)
        if not entry:
            return None
        if entry.expires_at < time.time():
            self._store.pop(key, None)
            return None
        return entry.value  # type: ignore[return-value]

    def set(self, key: str, value: T, ttl_seconds: int) -> None:
        self._store[key] = _Entry(value=value, expires_at=time.time() + ttl_seconds)
