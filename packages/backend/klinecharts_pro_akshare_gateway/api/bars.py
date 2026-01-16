from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request

from klinecharts_pro_akshare_gateway.models import HistoryResponse
from klinecharts_pro_akshare_gateway.cache.memory import MemoryCache

router = APIRouter()


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    request: Request,
    symbol: str = Query(...),
    period: str = Query(...),
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    limit: int = Query(2000, ge=1, le=2000),
):
    settings = request.app.state.settings
    if limit > settings.history_max_limit:
        limit = settings.history_max_limit

    cache: MemoryCache = request.app.state.history_cache
    cache_key = f"history:{symbol}:{period}:{from_}:{to}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return HistoryResponse.model_validate(cached)

    provider = request.app.state.async_provider
    if _is_daily_period(period):
        start = _parse_date(from_)
        end = _parse_date(to)
        items = await provider.get_daily_history(symbol, start, end)
        if period in {"1w", "1M"}:
            items = _aggregate_bars(items, period, settings.timezone)
    elif _is_minute_period(period):
        start_dt = _parse_datetime(from_, settings.timezone)
        end_dt = _parse_datetime(to, settings.timezone)
        if end_dt < start_dt:
            raise HTTPException(status_code=400, detail="invalid range")
        max_days = settings.minute_history_max_days
        if end_dt - start_dt > timedelta(days=max_days):
            start_dt = end_dt - timedelta(days=max_days)
        try:
            items = await provider.get_minute_history(symbol, period, start_dt, end_dt)
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail="minute history not implemented") from exc
        if not items:
            items = await _fallback_recent_minute_history(provider, symbol, period, end_dt, settings)
    else:
        raise HTTPException(status_code=400, detail="unsupported period")

    items = items[:limit]
    next_from = None
    if items:
        next_from = items[-1].ts + 1

    response = HistoryResponse(symbol=symbol, period=period, items=items, next_from=next_from)
    ttl = 6 * 60 * 60 if _is_daily_period(period) else 10 * 60
    cache.set(cache_key, response.model_dump(), ttl_seconds=ttl)
    return response


def _is_daily_period(period: str) -> bool:
    return period in {"1d", "1w", "1M"}


def _is_minute_period(period: str) -> bool:
    return period.endswith("m")


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid date format") from exc


def _parse_datetime(value: str, tz_name: str) -> datetime:
    if value.isdigit():
        ts = int(value)
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=ZoneInfo(tz_name))
        return dt
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid datetime format") from exc


async def _fallback_recent_minute_history(provider, symbol, period, end_dt, settings):
    try:
        calendar = await provider.get_trading_calendar()
    except Exception:
        return []
    if not calendar:
        return []
    tz = ZoneInfo(settings.timezone)
    target_date = end_dt.astimezone(tz).date()
    candidates = sorted([d for d in calendar if d <= target_date.isoformat()])
    if not candidates:
        return []
    last_date = datetime.fromisoformat(candidates[-1]).date()
    start_dt = datetime.combine(last_date, datetime.min.time(), tzinfo=tz).replace(
        hour=9, minute=30
    )
    end_dt = datetime.combine(last_date, datetime.min.time(), tzinfo=tz).replace(hour=15, minute=0)
    try:
        return await provider.get_minute_history(symbol, period, start_dt, end_dt)
    except Exception:
        return []


def _aggregate_bars(items, period: str, tz_name: str):
    tz = ZoneInfo(tz_name)
    buckets: dict[str, list] = {}
    for bar in items:
        dt = datetime.fromtimestamp(bar.ts / 1000, tz=timezone.utc).astimezone(tz)
        if period == "1w":
            start = dt.date() - timedelta(days=dt.weekday())
        else:
            start = dt.date().replace(day=1)
        key = start.isoformat()
        buckets.setdefault(key, []).append((start, bar))

    aggregated = []
    for key in sorted(buckets.keys()):
        bars = buckets[key]
        bars.sort(key=lambda item: item[1].ts)
        _, first = bars[0]
        _, last = bars[-1]
        high = max(item[1].high for item in bars)
        low = min(item[1].low for item in bars)
        volume = sum(item[1].volume for item in bars)
        amount = sum((item[1].amount or 0.0) for item in bars)
        start_date = bars[0][0]
        bucket_start = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        aggregated.append(
            type(first)(
                ts=int(bucket_start.astimezone(timezone.utc).timestamp() * 1000),
                open=first.open,
                high=high,
                low=low,
                close=last.close,
                volume=volume,
                amount=amount,
                is_closed=True,
            )
        )
    return aggregated
