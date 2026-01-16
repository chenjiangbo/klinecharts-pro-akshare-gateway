from fastapi import APIRouter

from klinecharts_pro_akshare_gateway.api import bars, health, symbols

router = APIRouter()
router.include_router(symbols.router, prefix="/symbols", tags=["symbols"])
router.include_router(bars.router, prefix="/bars", tags=["bars"])
router.include_router(health.router, tags=["health"])
