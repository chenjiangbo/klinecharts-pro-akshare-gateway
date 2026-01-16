from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from klinecharts_pro_akshare_gateway.barbuilder.models import BarState, SymbolState
from klinecharts_pro_akshare_gateway.models import Bar, Snapshot


class BarBuilder:
    def __init__(self, tz_name: str = "Asia/Shanghai", periods: list[str] | None = None) -> None:
        self._states: dict[tuple[str, str], SymbolState] = {}
        self._tz = ZoneInfo(tz_name)
        self._periods = periods or ["1m", "5m", "15m", "30m", "60m", "1d", "1w", "1M"]

    def apply_snapshots(self, snapshots: dict[str, Snapshot]) -> list[tuple[str, str, Bar]]:
        events: list[tuple[str, str, Bar]] = []
        for symbol, snap in snapshots.items():
            for period in self._periods:
                events.extend(self._apply_snapshot(symbol, period, snap))
        return events

    def _apply_snapshot(self, symbol: str, period: str, snap: Snapshot) -> list[tuple[str, str, Bar]]:
        state = self._states.setdefault((symbol, period), SymbolState())
        snap_ts = snap.ts.astimezone(self._tz)
        trade_date = snap_ts.date().isoformat()

        bucket_start = _bucket_start(snap_ts, period, self._tz)
        if bucket_start is None:
            return []

        events: list[tuple[str, str, Bar]] = []
        if state.last_trade_date is None:
            state.last_trade_date = trade_date
        elif state.last_trade_date != trade_date:
            if state.cur_bar is not None:
                state.cur_bar.is_closed = True
                events.append((symbol, period, _to_bar(state.cur_bar)))
            state.cur_bar = None
            state.prev_volume_total = None
            state.prev_amount_total = None
            state.last_trade_date = trade_date

        if state.cur_bar is None or state.cur_bar.bucket_start != bucket_start:
            if state.cur_bar is not None:
                state.cur_bar.is_closed = True
                events.append((symbol, period, _to_bar(state.cur_bar)))
            state.cur_bar = BarState(
                bucket_start=bucket_start,
                open=snap.last,
                high=snap.last,
                low=snap.last,
                close=snap.last,
                volume=0.0,
                amount=0.0,
            )

        cur = state.cur_bar
        cur.high = max(cur.high, snap.last)
        cur.low = min(cur.low, snap.last)
        cur.close = snap.last

        _apply_totals(cur, state, snap, reset_add=_reset_add_for_period(period))
        events.append((symbol, period, _to_bar(cur)))
        return events


def _apply_totals(cur: BarState, state: SymbolState, snap: Snapshot, reset_add: bool) -> None:
    if snap.volume_total is not None:
        if state.prev_volume_total is None:
            cur.volume += float(snap.volume_total)
        elif snap.volume_total < state.prev_volume_total:
            cur.volume = (cur.volume if reset_add else 0.0) + float(snap.volume_total)
        else:
            cur.volume += max(0.0, snap.volume_total - state.prev_volume_total)
        state.prev_volume_total = snap.volume_total

    if snap.amount_total is not None:
        if state.prev_amount_total is None:
            cur.amount = (cur.amount or 0.0) + float(snap.amount_total)
        elif snap.amount_total < state.prev_amount_total:
            cur.amount = (cur.amount if reset_add else 0.0) + float(snap.amount_total)
        else:
            cur.amount = (cur.amount or 0.0) + max(0.0, snap.amount_total - state.prev_amount_total)
        state.prev_amount_total = snap.amount_total


def _to_bar(state: BarState) -> Bar:
    ts = int(state.bucket_start.astimezone(timezone.utc).timestamp() * 1000)
    return Bar(
        ts=ts,
        open=state.open,
        high=state.high,
        low=state.low,
        close=state.close,
        volume=state.volume,
        amount=state.amount,
        is_closed=state.is_closed,
    )


def _bucket_start(ts: datetime, period: str, tz: ZoneInfo) -> datetime | None:
    if period.endswith("m"):
        minutes = int(period[:-1])
        total_minutes = ts.hour * 60 + ts.minute
        bucket_minutes = total_minutes - (total_minutes % minutes)
        return ts.replace(
            hour=bucket_minutes // 60,
            minute=bucket_minutes % 60,
            second=0,
            microsecond=0,
        )
    if period == "1d":
        return datetime.combine(ts.date(), time.min, tzinfo=tz)
    if period == "1w":
        start = ts.date() - timedelta(days=ts.weekday())
        return datetime.combine(start, time.min, tzinfo=tz)
    if period == "1M":
        start = ts.date().replace(day=1)
        return datetime.combine(start, time.min, tzinfo=tz)
    return None


def _reset_add_for_period(period: str) -> bool:
    return period in {"1w", "1M"}
