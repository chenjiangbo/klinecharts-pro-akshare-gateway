from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class BarState:
    bucket_start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None
    is_closed: bool = False


@dataclass
class SymbolState:
    cur_bar: BarState | None = None
    prev_volume_total: float | None = None
    prev_amount_total: float | None = None
    last_trade_date: str | None = None
