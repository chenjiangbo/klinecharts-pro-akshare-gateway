from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import date, datetime
import io
from zoneinfo import ZoneInfo

from app.cache.memory import MemoryCache
from app.models import Bar, Snapshot, SymbolInfo


@dataclass
class AkshareConfig:
    symbols_ttl_seconds: int = 24 * 60 * 60
    calendar_ttl_seconds: int = 24 * 60 * 60
    silent_progress: bool = True


class AkshareProvider:
    def __init__(self, config: AkshareConfig | None = None) -> None:
        self._config = config or AkshareConfig()
        self._symbols_cache = MemoryCache()
        self._calendar_cache = MemoryCache()

    def search_symbols(self, q: str, limit: int) -> list[SymbolInfo]:
        if not q:
            return []
        symbols = self._load_symbols()
        q_lower = q.lower()
        items = [
            item
            for item in symbols
            if q_lower in item.symbol.lower() or q in item.name
        ]
        return items[:limit]

    def get_daily_history(self, symbol: str, start: date, end: date) -> list[Bar]:
        ak = _import_akshare()
        with _silence(self._config.silent_progress):
            df = ak.stock_zh_a_hist(
                symbol=symbol.split(".", 1)[0],
                period="daily",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="",
            )
        bars: list[Bar] = []
        tz = ZoneInfo("Asia/Shanghai")
        for _, row in df.iterrows():
            dt = datetime.strptime(str(row["日期"]), "%Y-%m-%d")
            dt = dt.replace(tzinfo=tz)
            bars.append(
                Bar(
                    ts=int(dt.timestamp() * 1000),
                    open=float(row["开盘"]),
                    high=float(row["最高"]),
                    low=float(row["最低"]),
                    close=float(row["收盘"]),
                    volume=float(row.get("成交量", 0)),
                    amount=float(row.get("成交额", 0)) if "成交额" in row else None,
                    is_closed=True,
                )
            )
        return bars

    def get_minute_history(
        self, symbol: str, period: str, start: datetime, end: datetime
    ) -> list[Bar]:
        if not period.endswith("m"):
            raise ValueError("minute period expected")
        period_value = period[:-1]
        ak = _import_akshare()
        code = symbol.split(".", 1)[0]
        start_s = _to_shanghai(start).strftime("%Y-%m-%d %H:%M:%S")
        end_s = _to_shanghai(end).strftime("%Y-%m-%d %H:%M:%S")
        with _silence(self._config.silent_progress):
            try:
                df = ak.stock_zh_a_hist_min_em(
                    symbol=code,
                    period=period_value,
                    start_date=start_s,
                    end_date=end_s,
                    adjust="",
                )
            except TypeError:
                df = ak.stock_zh_a_hist_min_em(
                    symbol=code,
                    period=period_value,
                    start_date=start_s,
                    end_date=end_s,
                )
        tz = ZoneInfo("Asia/Shanghai")
        bars: list[Bar] = []
        for _, row in df.iterrows():
            ts_str = _row_get(row, ["时间", "datetime", "时间戳", "time"])
            if not ts_str:
                continue
            dt = _parse_datetime(str(ts_str)).replace(tzinfo=tz)
            bars.append(
                Bar(
                    ts=int(dt.timestamp() * 1000),
                    open=float(_row_get(row, ["开盘", "open"]) or 0),
                    high=float(_row_get(row, ["最高", "high"]) or 0),
                    low=float(_row_get(row, ["最低", "low"]) or 0),
                    close=float(_row_get(row, ["收盘", "close"]) or 0),
                    volume=float(_row_get(row, ["成交量", "volume"]) or 0),
                    amount=float(_row_get(row, ["成交额", "amount"]) or 0),
                    is_closed=True,
                )
            )
        return bars

    def get_realtime_snapshot_batch(self, symbols: list[str]) -> dict[str, Snapshot]:
        if not symbols:
            return {}
        ak = _import_akshare()
        with _silence(self._config.silent_progress):
            df = ak.stock_zh_a_spot_em()
        tz = ZoneInfo("Asia/Shanghai")
        now = datetime.now(tz=tz)
        out: dict[str, Snapshot] = {}
        symbol_set = set(symbols)
        for _, row in df.iterrows():
            code = str(row.get("代码") or row.get("code") or "").zfill(6)
            full_symbol = _to_internal_symbol(code)
            if full_symbol not in symbol_set:
                continue
            out[full_symbol] = Snapshot(
                ts=now,
                last=float(row.get("最新价", 0)),
                open=_as_float(row, "今开"),
                high=_as_float(row, "最高"),
                low=_as_float(row, "最低"),
                prev_close=_as_float(row, "昨收"),
                volume_total=_as_float(row, "成交量"),
                amount_total=_as_float(row, "成交额"),
            )
        return out

    def get_trading_calendar(self) -> set[str]:
        cached = self._calendar_cache.get("trading_calendar")
        if cached is not None:
            return cached
        ak = _import_akshare()
        with _silence(self._config.silent_progress):
            df = ak.tool_trade_date_hist_sina()
        dates: set[str] = set()
        for _, row in df.iterrows():
            value = _row_get(row, ["trade_date", "date", "日期"])
            if not value:
                continue
            dates.add(str(value))
        self._calendar_cache.set(
            "trading_calendar", dates, ttl_seconds=self._config.calendar_ttl_seconds
        )
        return dates

    def _load_symbols(self) -> list[SymbolInfo]:
        cached = self._symbols_cache.get("symbols")
        if cached is not None:
            return cached
        ak = _import_akshare()
        with _silence(self._config.silent_progress):
            df = ak.stock_info_a_code_name()
        items: list[SymbolInfo] = []
        for _, row in df.iterrows():
            code = str(row.get("code") or row.get("股票代码") or "").zfill(6)
            name = str(row.get("name") or row.get("股票简称") or "")
            symbol = _to_internal_symbol(code)
            items.append(
                SymbolInfo(
                    symbol=symbol,
                    name=name,
                    exchange=_exchange_from_symbol(symbol),
                    type="stock",
                    currency="CNY",
                    timezone="Asia/Shanghai",
                )
            )
        self._symbols_cache.set(
            "symbols", items, ttl_seconds=self._config.symbols_ttl_seconds
        )
        return items


def _import_akshare():
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:
        raise RuntimeError("AKShare is not installed") from exc
    return ak


def _to_internal_symbol(code: str) -> str:
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    if code.startswith(("0", "2", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def _exchange_from_symbol(symbol: str) -> str:
    if symbol.endswith(".SH"):
        return "SSE"
    if symbol.endswith(".SZ"):
        return "SZSE"
    if symbol.endswith(".BJ"):
        return "BSE"
    return ""


def _to_akshare_symbol(symbol: str) -> str:
    code, suffix = symbol.split(".", 1)
    suffix = suffix.lower()
    return f"{suffix}{code}"


def _as_float(row, key: str) -> float | None:
    value = row.get(key) if hasattr(row, "get") else None
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


@contextmanager
def _silence(enabled: bool):
    if not enabled:
        yield
        return
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        yield


def _row_get(row, keys: list[str]):
    for key in keys:
        try:
            value = row.get(key)
        except Exception:
            value = None
        if value is not None:
            return value
    return None


def _parse_datetime(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(value)


def _to_shanghai(value: datetime) -> datetime:
    tz = ZoneInfo("Asia/Shanghai")
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)
