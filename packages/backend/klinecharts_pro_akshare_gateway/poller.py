from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from klinecharts_pro_akshare_gateway.barbuilder.builder import BarBuilder
from klinecharts_pro_akshare_gateway.config import Settings
from klinecharts_pro_akshare_gateway.models import BarEvent, StatusEvent
from klinecharts_pro_akshare_gateway.provider.async_provider import AsyncProvider
from klinecharts_pro_akshare_gateway.ws.hub import hub

logger = logging.getLogger(__name__)


@dataclass
class Backoff:
    base_seconds: int = 3
    max_seconds: int = 10
    _current: int = 0

    def next(self) -> int:
        if self._current == 0:
            self._current = self.base_seconds
        else:
            self._current = min(self.max_seconds, self._current + 2)
        return self._current

    def reset(self) -> None:
        self._current = 0


class TradingClock:
    def __init__(
        self,
        tz_name: str,
        sessions: str,
        special_sessions: dict[str, list[tuple[time, time]]],
        closed_dates: set[str],
    ) -> None:
        self._tz = ZoneInfo(tz_name)
        self._sessions = _parse_sessions(sessions)
        self._special_sessions = special_sessions
        self._closed_dates = closed_dates
        self._calendar: set[str] | None = None

    def now(self) -> datetime:
        return datetime.now(tz=self._tz)

    def is_trading_time(self, dt: datetime) -> bool:
        if not self.is_trading_day(dt):
            return False
        t = dt.time()
        sessions = self._special_sessions.get(dt.date().isoformat(), self._sessions)
        return any(start <= t <= end for start, end in sessions)

    def is_trading_day(self, dt: datetime) -> bool:
        if dt.date().isoformat() in self._closed_dates:
            return False
        if self._calendar is None:
            return dt.weekday() < 5
        return dt.date().isoformat() in self._calendar

    def update_calendar(self, calendar: set[str]) -> None:
        self._calendar = calendar


class Poller:
    def __init__(
        self,
        provider: AsyncProvider,
        bar_builder: BarBuilder,
        settings: Settings,
    ) -> None:
        self._provider = provider
        self._bar_builder = bar_builder
        self._settings = settings
        self._clock = TradingClock(
            settings.timezone,
            settings.trading_sessions,
            _parse_special_sessions(settings.special_trading_sessions),
            _parse_closed_dates(settings.closed_dates),
        )
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def run(self) -> None:
        backoff = Backoff()
        await self._refresh_calendar()
        while not self._stop_event.is_set():
            now = self._clock.now()
            if not self._clock.is_trading_time(now):
                await asyncio.sleep(self._settings.idle_backoff_seconds)
                continue

            symbols = hub.get_active_symbols()
            if not symbols:
                await asyncio.sleep(self._settings.snapshot_poll_interval_seconds)
                continue

            try:
                snapshots = await self._provider.get_realtime_snapshot_batch(symbols)
            except Exception:
                logger.exception("snapshot failed")
                await _broadcast_status("snapshot failed", code="snapshot_failed", level="error")
                await asyncio.sleep(backoff.next())
                continue

            backoff.reset()
            events = self._bar_builder.apply_snapshots(snapshots)
            for symbol, period, bar in events:
                await _broadcast_bar(symbol, period, bar)

            await asyncio.sleep(self._settings.snapshot_poll_interval_seconds)
            if now.hour == 0 and now.minute < 5:
                await self._refresh_calendar()

    async def _refresh_calendar(self) -> None:
        try:
            calendar = await self._provider.get_trading_calendar()
            if calendar:
                self._clock.update_calendar(calendar)
        except Exception:
            logger.exception("trading calendar load failed")
            await _broadcast_status("trading calendar load failed", code="calendar_failed", level="warning")


async def _broadcast_bar(symbol: str, period: str, bar) -> None:
    event = BarEvent(op="bar", symbol=symbol, period=period, bar=bar)
    payload = event.model_dump()
    for ws in hub.iter_subscribers(symbol, period):
        await ws.send_json(payload)


async def _broadcast_status(message: str, code: str | None = None, level: str = "info") -> None:
    event = StatusEvent(op="status", message=message, code=code, level=level)
    payload = event.model_dump()
    for ws in hub.iter_all():
        await ws.send_json(payload)


def _parse_sessions(value: str) -> list[tuple[time, time]]:
    sessions: list[tuple[time, time]] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        start_s, end_s = part.split("-")
        start = _parse_time(start_s)
        end = _parse_time(end_s)
        sessions.append((start, end))
    return sessions


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _parse_special_sessions(value: str) -> dict[str, list[tuple[time, time]]]:
    value = value.strip()
    if not value:
        return {}
    try:
        import json

        raw = json.loads(value)
    except Exception:
        logger.warning("invalid special_trading_sessions")
        return {}
    sessions: dict[str, list[tuple[time, time]]] = {}
    for date_str, session_str in raw.items():
        if not isinstance(session_str, str):
            continue
        sessions[date_str] = _parse_sessions(session_str)
    return sessions


def _parse_closed_dates(value: str) -> set[str]:
    value = value.strip()
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}
