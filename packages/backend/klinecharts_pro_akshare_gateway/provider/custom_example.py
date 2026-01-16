from __future__ import annotations

from datetime import date, datetime

from klinecharts_pro_akshare_gateway.models import Bar, Snapshot, SymbolInfo
from klinecharts_pro_akshare_gateway.provider.base import MarketDataProvider


class CustomProvider(MarketDataProvider):
    """Example provider template.

    Replace the method bodies with your own data source implementation.
    """

    def search_symbols(self, q: str, limit: int) -> list[SymbolInfo]:
        return []

    def get_daily_history(self, symbol: str, start: date, end: date) -> list[Bar]:
        return []

    def get_minute_history(
        self, symbol: str, period: str, start: datetime, end: datetime
    ) -> list[Bar]:
        return []

    def get_realtime_snapshot_batch(self, symbols: list[str]) -> dict[str, Snapshot]:
        return {}

    def get_trading_calendar(self) -> set[str]:
        return set()
