from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from klinecharts_pro_akshare_gateway.models import Bar, Snapshot, SymbolInfo


class MarketDataProvider(Protocol):
    def search_symbols(self, q: str, limit: int) -> list[SymbolInfo]:
        ...

    def get_daily_history(self, symbol: str, start: date, end: date) -> list[Bar]:
        ...

    def get_minute_history(
        self, symbol: str, period: str, start: datetime, end: datetime
    ) -> list[Bar]:
        ...

    def get_realtime_snapshot_batch(self, symbols: list[str]) -> dict[str, Snapshot]:
        ...

    def get_trading_calendar(self) -> set[str]:
        ...
