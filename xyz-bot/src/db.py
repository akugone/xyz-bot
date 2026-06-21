"""Persistance Postgres (asyncpg) : snapshots + journal d'events.

Rôle dans l'archi :
  - `load_snapshot(dex)` au démarrage → le `prev` du diff survit aux redémarrages.
    Renvoie `None` si aucune baseline en base (→ seed silencieux au 1er run jamais).
  - `save_snapshot(snap)` à chaque cycle → met à jour l'état courant (upsert).
  - `record_new_events(events)` → `INSERT ... ON CONFLICT (dedup_key) DO NOTHING`,
    renvoie UNIQUEMENT les events réellement insérés. C'est l'idempotence anti-doublon :
    M3 ne notifiera que ceux-là (un même changement revu après redémarrage = clé déjà
    présente = pas de second ping).

Types : `oi_cap` / `total_oi_cap` / `funding_mult` sont des NUMERIC en base ; on les
manipule en `str` côté snapshot, donc on convertit via `Decimal` à l'aller et au retour.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import asyncpg

from .snapshot import CoinState, Snapshot

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


class Database:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=4)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database non connectée — appeler connect() d'abord")
        return self._pool

    async def init_schema(self) -> None:
        """Crée les tables si absentes (idempotent : schema.sql utilise IF NOT EXISTS)."""
        await self.pool.execute(SCHEMA_PATH.read_text())

    # --- snapshots ---

    async def load_snapshot(self, dex: str) -> Snapshot | None:
        """Reconstruit le dernier snapshot persisté, ou None s'il n'y a pas de baseline."""
        rows = await self.pool.fetch(
            "SELECT coin, max_leverage, margin_mode, margin_table_id, oi_cap, "
            "is_listed, is_halted, funding_mult, growth_mode "
            "FROM market_state WHERE dex = $1",
            dex,
        )
        if not rows:
            return None  # pas de baseline → le diff fera un seed silencieux

        dex_row = await self.pool.fetchrow(
            "SELECT total_oi_cap FROM dex_state WHERE dex = $1", dex
        )
        snap = Snapshot(dex=dex, total_oi_cap=_num_to_str(dex_row["total_oi_cap"]) if dex_row else None)
        for r in rows:
            snap.coins[r["coin"]] = CoinState(
                coin=r["coin"],
                max_leverage=r["max_leverage"],
                margin_mode=r["margin_mode"],
                margin_table_id=r["margin_table_id"],
                oi_cap=_num_to_str(r["oi_cap"]),
                is_listed=r["is_listed"],
                is_halted=r["is_halted"],
                funding_mult=_num_to_str(r["funding_mult"]),
                growth_mode=r["growth_mode"],
            )
        return snap

    async def save_snapshot(self, snap: Snapshot) -> None:
        """Upsert de l'état dex + de chaque coin (transaction)."""
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO dex_state (dex, total_oi_cap, updated_at) "
                "VALUES ($1, $2, now()) "
                "ON CONFLICT (dex) DO UPDATE SET total_oi_cap = EXCLUDED.total_oi_cap, updated_at = now()",
                snap.dex, _to_num(snap.total_oi_cap),
            )
            for c in snap.coins.values():
                await conn.execute(
                    "INSERT INTO market_state "
                    "(dex, coin, max_leverage, margin_mode, margin_table_id, oi_cap, "
                    " is_listed, is_halted, funding_mult, growth_mode, updated_at) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10, now()) "
                    "ON CONFLICT (dex, coin) DO UPDATE SET "
                    "  max_leverage = EXCLUDED.max_leverage, margin_mode = EXCLUDED.margin_mode, "
                    "  margin_table_id = EXCLUDED.margin_table_id, oi_cap = EXCLUDED.oi_cap, "
                    "  is_listed = EXCLUDED.is_listed, is_halted = EXCLUDED.is_halted, "
                    "  funding_mult = EXCLUDED.funding_mult, growth_mode = EXCLUDED.growth_mode, "
                    "  updated_at = now()",
                    snap.dex, c.coin, c.max_leverage, c.margin_mode, c.margin_table_id,
                    _to_num(c.oi_cap), c.is_listed, c.is_halted, _to_num(c.funding_mult),
                    c.growth_mode,
                )

    # --- events ---

    async def record_new_events(self, events: list) -> list:
        """Insère les events ; renvoie ceux RÉELLEMENT insérés (dedup_key inédit).

        `events` : liste d'`Event` (src.events). On garde le type souple pour éviter
        un import circulaire ; on lit juste leurs attributs.
        """
        inserted = []
        async with self.pool.acquire() as conn:
            for ev in events:
                row = await conn.fetchrow(
                    "INSERT INTO events (dex, coin, event_type, old_value, new_value, dedup_key) "
                    "VALUES ($1,$2,$3,$4,$5,$6) "
                    "ON CONFLICT (dedup_key) DO NOTHING RETURNING id",
                    ev.dex, ev.coin, ev.event_type, ev.old_value, ev.new_value, ev.dedup_key,
                )
                if row is not None:  # une ligne créée = event inédit
                    inserted.append(ev)
        return inserted

    async def mark_notified(self, dedup_keys: list[str]) -> None:
        """Marque `notified_at = now()` pour les events effectivement envoyés.

        Un event inséré mais jamais marqué (notified_at NULL) = enregistré mais non
        délivré (ex. échec d'envoi) → traçable par une requête.
        """
        if not dedup_keys:
            return
        await self.pool.execute(
            "UPDATE events SET notified_at = now() WHERE dedup_key = ANY($1::text[])",
            dedup_keys,
        )


def _to_num(v: str | None) -> Decimal | None:
    return None if v is None else Decimal(v)


def _num_to_str(v: object) -> str | None:
    return None if v is None else str(v)
