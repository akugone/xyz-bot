"""Load configuration from environment variables."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    hl_api_url: str = os.getenv("HL_API_URL", "https://api.hyperliquid.xyz/info")
    dex_name: str = os.getenv("DEX_NAME", "xyz")
    poll_interval_sec: float = float(os.getenv("POLL_INTERVAL_SEC", "5"))
    # cap of the exponential backoff on repeated errors (s)
    error_backoff_max_sec: float = float(os.getenv("ERROR_BACKOFF_MAX_SEC", "60"))
    # interval of the "still alive" heartbeat log line (s) — 0 to disable
    heartbeat_interval_sec: float = float(os.getenv("HEARTBEAT_INTERVAL_SEC", "3600"))
    pg_dsn: str | None = os.getenv("PG_DSN")
    # DSN for the status page (read-only Postgres role); falls back to pg_dsn if unset
    web_pg_dsn: str | None = os.getenv("WEB_PG_DSN")
    telegram_bot_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = os.getenv("TELEGRAM_CHAT_ID")
    # ops alerts chat (API down…) — private/admin; if unset, those alerts stay in logs
    telegram_admin_chat_id: str | None = os.getenv("TELEGRAM_ADMIN_CHAT_ID")
    # number of consecutive errors before raising an "API down" alert
    api_down_threshold: int = int(os.getenv("API_DOWN_THRESHOLD", "3"))
    # dry-run: log messages instead of sending them (also forced if token/chat is missing)
    telegram_dry_run: bool = os.getenv("TELEGRAM_DRY_RUN", "").lower() in ("1", "true", "yes")
    # public status page (separate web service)
    web_host: str = os.getenv("WEB_HOST", "0.0.0.0")
    web_port: int = int(os.getenv("WEB_PORT", "8080"))


config = Config()
