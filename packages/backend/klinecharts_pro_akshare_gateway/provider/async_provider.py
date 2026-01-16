from __future__ import annotations

from datetime import date, datetime

import anyio

from klinecharts_pro_akshare_gateway.models import Bar, Snapshot, SymbolInfo
from klinecharts_pro_akshare_gateway.provider.base import MarketDataProvider


class AsyncProvider:
    def __init__(self, provider: MarketDataProvider) -> None:
        self._provider = provider

    async def search_symbols(self, q: str, limit: int) -> list[SymbolInfo]:
        return await anyio.to_thread.run_sync(self._provider.search_symbols, q, limit)

    async def get_daily_history(self, symbol: str, start: date, end: date) -> list[Bar]:
        return await anyio.to_thread.run_sync(self._provider.get_daily_history, symbol, start, end)

    async def get_minute_history(
        self, symbol: str, period: str, start: datetime, end: datetime
    ) -> list[Bar]:
        return await anyio.to_thread.run_sync(
            self._provider.get_minute_history, symbol, period, start, end
        )

    async def get_realtime_snapshot_batch(self, symbols: list[str]) -> dict[str, Snapshot]:
        return await anyio.to_thread.run_sync(self._provider.get_realtime_snapshot_batch, symbols)

    async def get_trading_calendar(self) -> set[str]:
        return await anyio.to_thread.run_sync(self._provider.get_trading_calendar)
