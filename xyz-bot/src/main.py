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
    """Boucle daemon (M2 : diff en mémoire ; M3/M2-bis : notif + persistance Postgres).

    État actuel : le snapshot précédent est gardé EN MÉMOIRE (pas encore Postgres).
    Au 1er cycle `prev is None` → seed silencieux (aucun event). Les events apparaissent
    dès le 2e cycle. TODO M2-bis/M3 :
      - charger/persister le snapshot depuis Postgres (au lieu de la mémoire)
      - pour chaque event : ping Telegram (dedup_key anti-doublon)
    """
    client = HyperliquidClient()
    prev: Snapshot | None = None
    try:
        while True:
            try:
                snap = await fetch_snapshot(client, config.dex_name)
                events = diff(prev, snap)
                if prev is None:
                    log.info("seed — baseline de %d coins mémorisée (aucune alerte)", len(snap.coins))
                elif events:
                    for ev in events:
                        log.info("EVENT %-20s %-14s %s → %s",
                                 ev.event_type, ev.coin or "(dex)", ev.old_value, ev.new_value)
                else:
                    log.info("cycle ok — %d coins, aucun changement", len(snap.coins))
                prev = snap  # TODO M2-bis : remplacer par save_snapshot(snap) en Postgres
            except Exception:  # noqa: BLE001 — résilience daemon
                log.exception("cycle en erreur, on continue")
            await asyncio.sleep(config.poll_interval_sec)
    finally:
        await client.aclose()


if __name__ == "__main__":
    # M1 : `run_once()` (un cycle de lecture). M2 : `run_loop()` (boucle + diff en mémoire).
    asyncio.run(run_loop())
