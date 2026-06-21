"""Entry point of the xyz-bot daemon.

`run_loop()` (prod entry): resilient loop fetch → diff → Telegram notify → persist,
with backoff on error, heartbeat, and graceful shutdown on SIGTERM (systemd).
`run_once()`: a single read cycle (debug).
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
    """Delay before the next cycle: normal poll if 0 errors, else capped exponential backoff."""
    if not errors:
        return config.poll_interval_sec
    return min(config.poll_interval_sec * (2 ** errors), config.error_backoff_max_sec)


def api_alert_action(errors: int, threshold: int, alerted: bool) -> str | None:
    """API state transition → 'down' (alert), 'up' (recovered), or None (nothing).

    'down': consecutive-error threshold reached and we haven't alerted yet.
    'up'  : a cycle just succeeded (errors == 0) while we were in the alerted state.
    """
    if errors >= threshold and not alerted:
        return "down"
    if errors == 0 and alerted:
        return "up"
    return None


async def fetch_snapshot(client: HyperliquidClient, dex: str) -> Snapshot:
    """Fetch meta + perpDexLimits and build a per-coin snapshot."""
    meta, limits = await asyncio.gather(
        client.get_meta(dex),
        client.get_perp_dex_limits(dex),
    )
    return build_snapshot(dex, meta, limits)


async def run_once() -> None:
    """A single read cycle, to check connectivity and parsing."""
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
    """One full cycle: fetch → diff → notify fresh events → persist. Returns the snapshot.

    The previous snapshot comes from Postgres if `db`, else from `prev_snapshot` (memory fallback).
    On the first run with no baseline (`prev is None`) → silent seed (no alert).
    """
    snap = await fetch_snapshot(client, config.dex_name)
    prev = await db.load_snapshot(snap.dex) if db is not None else prev_snapshot
    events = diff(prev, snap)

    if prev is None:
        log.info("seed — baseline of %d coins recorded (no alert)", len(snap.coins))
    else:
        new_events = await db.record_new_events(events) if db is not None else events
        sent = []
        for ev in new_events:
            log.info("EVENT %-20s %-14s %s -> %s",
                     ev.event_type, ev.coin or "(dex)", ev.old_value, ev.new_value)
            await notifier.send(format_event(ev))
            sent.append(ev.dedup_key)
        if db is not None and sent:
            await db.mark_notified(sent)
        if not new_events:
            log.info("cycle ok — %d coins, no change", len(snap.coins))

    if db is not None:
        await db.save_snapshot(snap)
    return snap


async def _ops_alert(notifier: TelegramNotifier, text: str) -> None:
    """Ops alert → admin chat if configured, otherwise just logged (best-effort)."""
    log.warning("OPS ALERT: %s", text)
    if config.telegram_admin_chat_id:
        try:
            await notifier.send(text, chat_id=config.telegram_admin_chat_id)
        except Exception:  # noqa: BLE001
            log.exception("ops alert send failed")


async def run_loop() -> None:
    """Production daemon loop: resilient (backoff on error), heartbeat, graceful shutdown.

    - **Backoff**: after an error the delay grows (2x, 4x… capped) to avoid hammering a
      down API; it returns to the normal poll as soon as a cycle succeeds.
    - **Heartbeat**: periodic "alive" log line (observability), no Telegram message.
    - **Graceful shutdown**: SIGTERM/SIGINT (systemd `stop`) interrupts the wait and cleanly
      closes the HTTP client, notifier, and Postgres pool.
    """
    client = HyperliquidClient()
    db = Database(config.pg_dsn) if config.pg_dsn else None
    notifier = TelegramNotifier(
        config.telegram_bot_token, config.telegram_chat_id, dry_run=config.telegram_dry_run
    )
    last_snap: Snapshot | None = None  # last snapshot (memory fallback if no DB)

    if db is not None:
        await db.connect()
        await db.init_schema()
        log.info("Postgres persistence active")
    else:
        log.warning("PG_DSN missing — persistence disabled (in-memory state, lost on restart)")
    log.info("Telegram notifications: %s", "DRY-RUN (logs)" if notifier.dry_run else "real sending")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover — platforms without add_signal_handler
            pass

    errors = 0
    last_markets = 0
    api_alerted = False  # have we already warned that the API is down?
    started_at = datetime.now(timezone.utc)
    last_heartbeat = time.monotonic()
    log.info("loop starting (poll=%ss)", config.poll_interval_sec)

    try:
        while not stop.is_set():
            try:
                last_snap = await run_cycle(client, db, notifier, last_snap)
                last_markets = len(last_snap.coins)
                errors = 0
            except Exception:  # noqa: BLE001 — daemon resilience
                errors += 1
                log.exception("cycle failed (%d consecutive), backing off", errors)

            # ops alert "API down" / "recovered" (on transition, no spam)
            action = api_alert_action(errors, config.api_down_threshold, api_alerted)
            if action == "down":
                api_alerted = True
                await _ops_alert(notifier, f"⚠️ xyz-bot: Hyperliquid API unreachable "
                                           f"({errors} consecutive errors). Alerts paused until recovery.")
            elif action == "up":
                api_alerted = False
                await _ops_alert(notifier, "✅ xyz-bot: Hyperliquid API recovered. Monitoring resumed.")

            # heartbeat to the DB (feeds the status page) — best-effort
            if db is not None:
                try:
                    await db.record_heartbeat(config.dex_name, started_at, last_markets, errors)
                except Exception:  # noqa: BLE001
                    log.exception("heartbeat write failed")

            now = time.monotonic()
            if config.heartbeat_interval_sec and now - last_heartbeat >= config.heartbeat_interval_sec:
                log.info("heartbeat — alive, %d consecutive error(s)", errors)
                last_heartbeat = now

            # wait the delay (poll or backoff), but wake up immediately if shutdown is requested
            try:
                await asyncio.wait_for(stop.wait(), timeout=backoff_delay(errors))
            except asyncio.TimeoutError:
                pass
    finally:
        log.info("shutting down — closing resources")
        await client.aclose()
        await notifier.aclose()
        if db is not None:
            await db.close()


if __name__ == "__main__":
    asyncio.run(run_loop())
