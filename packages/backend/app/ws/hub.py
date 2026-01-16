from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from fastapi import WebSocket


class WebSocketHub:
    def __init__(self) -> None:
        self._subs: dict[tuple[str, str], set[WebSocket]] = defaultdict(set)
        self._active_symbols: set[str] = set()

    def subscribe(self, ws: WebSocket, symbol: str, period: str) -> None:
        self._subs[(symbol, period)].add(ws)
        self._active_symbols.add(symbol)

    def unsubscribe(self, ws: WebSocket, symbol: str, period: str) -> None:
        key = (symbol, period)
        self._subs[key].discard(ws)
        if not self._subs[key]:
            self._subs.pop(key, None)
        self._rebuild_active_symbols()

    def remove(self, ws: WebSocket) -> None:
        for key in list(self._subs.keys()):
            self._subs[key].discard(ws)
            if not self._subs[key]:
                self._subs.pop(key, None)
        self._rebuild_active_symbols()

    def get_active_symbols(self) -> list[str]:
        return sorted(self._active_symbols)

    def iter_subscribers(self, symbol: str, period: str) -> Iterable[WebSocket]:
        return list(self._subs.get((symbol, period), set()))

    def iter_all(self) -> Iterable[WebSocket]:
        seen: set[WebSocket] = set()
        for group in self._subs.values():
            for ws in group:
                if ws not in seen:
                    seen.add(ws)
                    yield ws

    def _rebuild_active_symbols(self) -> None:
        self._active_symbols = {symbol for symbol, _ in self._subs.keys()}


hub = WebSocketHub()
