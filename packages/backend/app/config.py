from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    timezone: str = "Asia/Shanghai"
    trading_sessions: str = "09:30-11:30,13:00-15:00"
    snapshot_poll_interval_seconds: int = 3
    idle_backoff_seconds: int = 30
    max_active_symbols: int = 200
    cache_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"
    history_max_limit: int = 2000
    ws_ping_interval_seconds: int = 25
    cors_allow_origins: str = "http://127.0.0.1:5173"
    minute_history_max_days: int = 7
    akshare_silent_progress: bool = False
    special_trading_sessions: str = ""
    closed_dates: str = ""


def get_settings() -> Settings:
    return Settings()
