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
    # M4 : plafond du backoff exponentiel en cas d'erreurs répétées (s)
    error_backoff_max_sec: float = float(os.getenv("ERROR_BACKOFF_MAX_SEC", "60"))
    # M4 : intervalle du heartbeat « still alive » dans les logs (s) — 0 pour désactiver
    heartbeat_interval_sec: float = float(os.getenv("HEARTBEAT_INTERVAL_SEC", "3600"))
    pg_dsn: str | None = os.getenv("PG_DSN")
    # DSN dédié à la page web (rôle Postgres read-only) ; défaut = pg_dsn si non fourni
    web_pg_dsn: str | None = os.getenv("WEB_PG_DSN")
    telegram_bot_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = os.getenv("TELEGRAM_CHAT_ID")
    # canal d'alertes ops (API down…) — privé/admin ; si vide, ces alertes restent en logs
    telegram_admin_chat_id: str | None = os.getenv("TELEGRAM_ADMIN_CHAT_ID")
    # nb d'erreurs consécutives avant d'alerter « API down »
    api_down_threshold: int = int(os.getenv("API_DOWN_THRESHOLD", "3"))
    # dry-run : logue les messages au lieu de les envoyer (forcé aussi si token/chat absent)
    telegram_dry_run: bool = os.getenv("TELEGRAM_DRY_RUN", "").lower() in ("1", "true", "yes")
    # page de statut publique (service web séparé)
    web_host: str = os.getenv("WEB_HOST", "0.0.0.0")
    web_port: int = int(os.getenv("WEB_PORT", "8080"))


config = Config()
