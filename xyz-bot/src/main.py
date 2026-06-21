"""Point d'entrée du daemon xyz-bot.

`run_loop()` (entrée prod) : boucle résiliente fetch → diff → notif Telegram → persiste,
avec backoff sur erreur, heartbeat et arrêt propre sur SIGTERM (systemd).
`run_once()` : un seul cycle de lecture (debug M1).
"""
from __future__ import annotations

import asyncio
import logging
import signal
import time
from datetime import datetime, timezone

from .config import config
from .db import Database
from .events import diff
from .hl_client import HyperliquidClient
from .messages import format_event
from .snapshot import Snapshot, build_snapshot
from .telegram import TelegramNotifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("xyz-bot")


def backoff_delay(errors: int) -> float:
    """Délai avant le prochain cycle : poll normal si 0 erreur, sinon backoff exp. plafonné."""
    if not errors:
        return config.poll_interval_sec
    return min(config.poll_interval_sec * (2 ** errors), config.error_backoff_max_sec)


def api_alert_action(errors: int, threshold: int, alerted: bool) -> str | None:
    """Transition de l'état API → 'down' (à alerter), 'up' (rétabli), ou None (rien).

    'down' : on a atteint le seuil d'erreurs consécutives et on n'a pas encore alerté.
    'up'   : un cycle vient de réussir (errors == 0) alors qu'on était en état alerté.
    """
    if errors >= threshold and not alerted:
        return "down"
    if errors == 0 and alerted:
        return "up"
    return None


async def fetch_snapshot(client: HyperliquidClient, dex: str) -> Snapshot:
    """Récupère meta + perpDexLimits et construit un snapshot par coin."""
    meta, limits = await asyncio.gather(
        client.get_meta(dex),
        client.get_perp_dex_limits(dex),
    )
    return build_snapshot(dex, meta, limits)


async def run_once() -> None:
    """M1 : un cycle de lecture, pour vérifier la connectivité et le parsing."""
    client = HyperliquidClient()
    try:
        snap = await fetch_snapshot(client, config.dex_name)
        log.info("dex=%s total_oi_cap=%s coins=%d", snap.dex, snap.total_oi_cap, len(snap.coins))
        for coin, s in sorted(snap.coins.items()):
            log.info(
                "  %-14s lev=%-4s mode=%-14s oi_cap=%-12s listed=%s",
                coin, s.max_leverage, s.margin_mode, s.oi_cap, s.is_listed,
            )
    finally:
        await client.aclose()


async def run_cycle(
    client: HyperliquidClient,
    db: Database | None,
    notifier: TelegramNotifier,
    prev_snapshot: Snapshot | None,
) -> Snapshot:
    """Un cycle complet : fetch → diff → notifie les inédits → persiste. Renvoie le snapshot.

    Le snapshot précédent vient de Postgres si `db`, sinon de `prev_snapshot` (fallback mémoire).
    Au 1er run sans baseline (`prev is None`) → seed silencieux (aucune alerte).
    """
    snap = await fetch_snapshot(client, config.dex_name)
    prev = await db.load_snapshot(snap.dex) if db is not None else prev_snapshot
    events = diff(prev, snap)

    if prev is None:
        log.info("seed — baseline de %d coins enregistrée (aucune alerte)", len(snap.coins))
    else:
        new_events = await db.record_new_events(events) if db is not None else events
        sent = []
        for ev in new_events:
            log.info("EVENT %-20s %-14s %s → %s",
                     ev.event_type, ev.coin or "(dex)", ev.old_value, ev.new_value)
            await notifier.send(format_event(ev))
            sent.append(ev.dedup_key)
        if db is not None and sent:
            await db.mark_notified(sent)
        if not new_events:
            log.info("cycle ok — %d coins, aucun changement", len(snap.coins))

    if db is not None:
        await db.save_snapshot(snap)
    return snap


async def _ops_alert(notifier: TelegramNotifier, text: str) -> None:
    """Alerte d'exploitation → chat admin si configuré, sinon seulement loggée (best-effort)."""
    log.warning("OPS ALERT: %s", text)
    if config.telegram_admin_chat_id:
        try:
            await notifier.send(text, chat_id=config.telegram_admin_chat_id)
        except Exception:  # noqa: BLE001
            log.exception("envoi alerte ops KO")


async def run_loop() -> None:
    """Boucle daemon de prod : résiliente (backoff sur erreur), heartbeat, arrêt propre.

    - **Backoff** : après une erreur, le délai croît (2×, 4×… plafonné) pour ne pas
      marteler une API en panne ; il revient au poll normal dès qu'un cycle réussit.
    - **Heartbeat** : ligne de log « vivant » périodique (observabilité), pas d'envoi Telegram.
    - **Arrêt propre** : SIGTERM/SIGINT (systemd `stop`) interrompt l'attente et ferme
      proprement client HTTP, notifier et pool Postgres.
    """
    client = HyperliquidClient()
    db = Database(config.pg_dsn) if config.pg_dsn else None
    notifier = TelegramNotifier(
        config.telegram_bot_token, config.telegram_chat_id, dry_run=config.telegram_dry_run
    )
    last_snap: Snapshot | None = None  # dernier snapshot (fallback mémoire si pas de DB)

    if db is not None:
        await db.connect()
        await db.init_schema()
        log.info("persistance Postgres active")
    else:
        log.warning("PG_DSN absent — persistance désactivée (état en mémoire, perdu au redémarrage)")
    log.info("notifications Telegram : %s", "DRY-RUN (logs)" if notifier.dry_run else "envoi réel")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover — plateformes sans add_signal_handler
            pass

    errors = 0
    last_markets = 0
    api_alerted = False  # a-t-on déjà prévenu que l'API est down ?
    started_at = datetime.now(timezone.utc)
    last_heartbeat = time.monotonic()
    log.info("démarrage de la boucle (poll=%ss)", config.poll_interval_sec)

    try:
        while not stop.is_set():
            try:
                last_snap = await run_cycle(client, db, notifier, last_snap)
                last_markets = len(last_snap.coins)
                errors = 0
            except Exception:  # noqa: BLE001 — résilience daemon
                errors += 1
                log.exception("cycle en erreur (%d consécutive[s]), backoff", errors)

            # alerte ops « API down » / « rétablie » (sur transition, pas de spam)
            action = api_alert_action(errors, config.api_down_threshold, api_alerted)
            if action == "down":
                api_alerted = True
                await _ops_alert(notifier, f"⚠️ xyz-bot: Hyperliquid API unreachable "
                                           f"({errors} consecutive errors). Alerts paused until recovery.")
            elif action == "up":
                api_alerted = False
                await _ops_alert(notifier, "✅ xyz-bot: Hyperliquid API recovered. Monitoring resumed.")

            # heartbeat en base (alimente la page de statut) — best-effort
            if db is not None:
                try:
                    await db.record_heartbeat(config.dex_name, started_at, last_markets, errors)
                except Exception:  # noqa: BLE001
                    log.exception("heartbeat en base KO")

            now = time.monotonic()
            if config.heartbeat_interval_sec and now - last_heartbeat >= config.heartbeat_interval_sec:
                log.info("heartbeat — vivant, %d erreur(s) consécutive(s)", errors)
                last_heartbeat = now

            # attendre le délai (poll ou backoff), mais se réveiller aussitôt si arrêt demandé
            try:
                await asyncio.wait_for(stop.wait(), timeout=backoff_delay(errors))
            except asyncio.TimeoutError:
                pass
    finally:
        log.info("arrêt — fermeture des ressources")
        await client.aclose()
        await notifier.aclose()
        if db is not None:
            await db.close()


if __name__ == "__main__":
    asyncio.run(run_loop())
