from __future__ import annotations

from typing import Protocol, TypeVar

T = TypeVar("T")


class Cache(Protocol):
    def get(self, key: str) -> T | None:
        ...

    def set(self, key: str, value: T, ttl_seconds: int) -> None:
        ...
