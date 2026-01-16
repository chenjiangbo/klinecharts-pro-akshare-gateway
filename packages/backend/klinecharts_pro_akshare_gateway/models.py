from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SymbolInfo(BaseModel):
    symbol: str
    name: str
    exchange: str
    type: str
    currency: str = "CNY"
    timezone: str = "Asia/Shanghai"


class Bar(BaseModel):
    ts: int = Field(..., description="UTC milliseconds")
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None
    is_closed: bool | None = None


class HistoryResponse(BaseModel):
    symbol: str
    period: str
    items: list[Bar]
    next_from: int | None = None


class SymbolSearchResponse(BaseModel):
    items: list[SymbolInfo]


class SubscribeRequest(BaseModel):
    op: Literal["subscribe", "unsubscribe"]
    symbol: str
    period: str


class BarEvent(BaseModel):
    op: Literal["bar"]
    symbol: str
    period: str
    bar: Bar


class StatusEvent(BaseModel):
    op: Literal["status"]
    message: str
    level: Literal["info", "warning", "error"] = "info"
    code: str | None = None


class SubscribeAck(BaseModel):
    op: Literal["subscribed"]
    symbol: str
    period: str


class ErrorEvent(BaseModel):
    op: Literal["error"]
    reason: str


class Snapshot(BaseModel):
    ts: datetime
    last: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    volume_total: float | None = None
    amount_total: float | None = None
