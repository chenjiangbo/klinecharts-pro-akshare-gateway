from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from klinecharts_pro_akshare_gateway.api.router import router as api_router
from klinecharts_pro_akshare_gateway.barbuilder.builder import BarBuilder
from klinecharts_pro_akshare_gateway.cache.memory import MemoryCache
from klinecharts_pro_akshare_gateway.cache.redis import RedisCache
from klinecharts_pro_akshare_gateway.config import get_settings
from klinecharts_pro_akshare_gateway.poller import Poller
from klinecharts_pro_akshare_gateway.provider.akshare import AkshareConfig, AkshareProvider
from klinecharts_pro_akshare_gateway.provider.async_provider import AsyncProvider
from klinecharts_pro_akshare_gateway.ws.routes import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    provider = AkshareProvider(
        config=AkshareConfig(silent_progress=settings.akshare_silent_progress)
    )
    async_provider = AsyncProvider(provider)
    bar_builder = BarBuilder(tz_name=settings.timezone)
    poller = Poller(async_provider, bar_builder, settings)
    history_cache = _create_history_cache(settings)

    app.state.settings = settings
    app.state.provider = provider
    app.state.async_provider = async_provider
    app.state.bar_builder = bar_builder
    app.state.poller = poller
    app.state.history_cache = history_cache

    poller.start()
    try:
        yield
    finally:
        await poller.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="KLineChart Pro AKShare Gateway", lifespan=lifespan)
    settings = get_settings()
    allow_origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/api/v1")
    return app


app = create_app()


def _create_history_cache(settings):
    if settings.cache_backend == "redis":
        return RedisCache(settings.redis_url)
    return MemoryCache()
