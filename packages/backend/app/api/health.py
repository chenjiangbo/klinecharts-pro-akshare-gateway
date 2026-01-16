from datetime import datetime, timezone

from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/health")
async def health(request: Request):
    settings = request.app.state.settings
    poller = request.app.state.poller
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "cache_backend": settings.cache_backend,
        "timezone": settings.timezone,
        "trading_calendar_size": len(request.app.state.poller._clock._calendar or []),
        "poller_running": poller is not None,
    }
