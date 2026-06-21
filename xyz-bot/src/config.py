"""Chargement de la configuration depuis les variables d'environnement."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    hl_api_url: str = os.getenv("HL_API_URL", "https://api.hyperliquid.xyz/info")
    dex_name: str = os.getenv("DEX_NAME", "xyz")
    poll_interval_sec: float = float(os.getenv("POLL_INTERVAL_SEC", "5"))
    pg_dsn: str | None = os.getenv("PG_DSN")
    telegram_bot_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = os.getenv("TELEGRAM_CHAT_ID")
    # dry-run : logue les messages au lieu de les envoyer (forcé aussi si token/chat absent)
    telegram_dry_run: bool = os.getenv("TELEGRAM_DRY_RUN", "").lower() in ("1", "true", "yes")


config = Config()
