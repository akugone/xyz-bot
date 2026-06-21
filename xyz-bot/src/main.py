"""Point d'entrée du daemon xyz-bot.

État actuel : M1 amorcé — fetch + construction + affichage d'un snapshot.
À compléter (voir CLAUDE.md / SPEC) :
  - M2 : persistance Postgres + moteur de diff (avec seed silencieux au 1er run)
  - M3 : notifications Telegram + dedup_key
  - M4 : boucle daemon robuste (backoff, heartbeat) sous systemd
"""
from __future__ import annotations

import asyncio
import logging

from .config import config
from .db import Database
from .events import diff
from .hl_client import HyperliquidClient
from .snapshot import Snapshot, build_snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("xyz-bot")


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


async def run_loop() -> None:
    """Boucle daemon : fetch → diff → persiste. Notif Telegram = M3 (encore en logs).

    Persistance : si `PG_DSN` est défini, le snapshot précédent vient de Postgres
    (survit aux redémarrages) et les events inédits sont journalisés via `dedup_key`.
    Sinon, fallback EN MÉMOIRE (utile pour un run sans base). Dans les deux cas, au tout
    premier run sans baseline `prev is None` → seed silencieux.
    """
    client = HyperliquidClient()
    db = Database(config.pg_dsn) if config.pg_dsn else None
    prev_mem: Snapshot | None = None  # fallback mémoire si pas de DB

    if db is not None:
        await db.connect()
        await db.init_schema()
        log.info("persistance Postgres active")
    else:
        log.warning("PG_DSN absent — persistance désactivée (état en mémoire, perdu au redémarrage)")

    try:
        while True:
            try:
                snap = await fetch_snapshot(client, config.dex_name)
                prev = await db.load_snapshot(snap.dex) if db is not None else prev_mem
                events = diff(prev, snap)

                if prev is None:
                    log.info("seed — baseline de %d coins enregistrée (aucune alerte)", len(snap.coins))
                else:
                    new_events = await db.record_new_events(events) if db is not None else events
                    if new_events:
                        for ev in new_events:
                            # M3 : c'est ici qu'on enverra le message Telegram.
                            log.info("EVENT %-20s %-14s %s → %s",
                                     ev.event_type, ev.coin or "(dex)", ev.old_value, ev.new_value)
                    else:
                        log.info("cycle ok — %d coins, aucun changement", len(snap.coins))

                if db is not None:
                    await db.save_snapshot(snap)
                else:
                    prev_mem = snap
            except Exception:  # noqa: BLE001 — résilience daemon
                log.exception("cycle en erreur, on continue")
            await asyncio.sleep(config.poll_interval_sec)
    finally:
        await client.aclose()
        if db is not None:
            await db.close()


if __name__ == "__main__":
    # M1 : `run_once()` (un cycle de lecture). M2 : `run_loop()` (boucle + diff en mémoire).
    asyncio.run(run_loop())
