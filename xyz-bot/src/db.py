"""Postgres persistence (asyncpg): snapshots + event journal.

Role in the architecture:
  - `load_snapshot(dex)` on startup → the diff's `prev` survives restarts.
    Returns `None` if there is no baseline (→ a one-time silent seed on the first run).
  - `save_snapshot(snap)` every cycle → updates the current state (upsert).
  - `record_new_events(events)` → `INSERT ... ON CONFLICT (dedup_key) DO NOTHING`,
    returns ONLY the events actually inserted. This is the anti-duplicate idempotency:
    only those get notified (the same change seen again after a restart = key already
    present = no second ping).

Types: `oi_cap` / `total_oi_cap` / `funding_mult` are NUMERIC in the DB; we handle them as
`str` in the snapshot, so we convert via `Decimal` on the way in and out.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import asyncpg

from .events import Event
from .snapshot import CoinState, Snapshot
from .util import none_or_str

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
            raise RuntimeError("Database not connected — call connect() first")
        return self._pool

    async def init_schema(self) -> None:
        """Create tables if missing (idempotent: schema.sql uses IF NOT EXISTS)."""
        await self.pool.execute(SCHEMA_PATH.read_text())

    # --- snapshots ---

    async def load_snapshot(self, dex: str) -> Snapshot | None:
        """Rebuild the last persisted snapshot, or None if there is no baseline."""
        rows = await self.pool.fetch(
            "SELECT coin, max_leverage, margin_mode, margin_table_id, oi_cap, "
            "is_listed, is_halted, funding_mult, growth_mode "
            "FROM market_state WHERE dex = $1",
            dex,
        )
        if not rows:
            return None  # no baseline → the diff will do a silent seed

        dex_row = await self.pool.fetchrow(
            "SELECT total_oi_cap FROM dex_state WHERE dex = $1", dex
        )
        snap = Snapshot(dex=dex, total_oi_cap=none_or_str(dex_row["total_oi_cap"]) if dex_row else None)
        for r in rows:
            snap.coins[r["coin"]] = CoinState(
                coin=r["coin"],
                max_leverage=r["max_leverage"],
                margin_mode=r["margin_mode"],
                margin_table_id=r["margin_table_id"],
                oi_cap=none_or_str(r["oi_cap"]),
                is_listed=r["is_listed"],
                is_halted=r["is_halted"],
                funding_mult=none_or_str(r["funding_mult"]),
                growth_mode=r["growth_mode"],
            )
        return snap

    async def save_snapshot(self, snap: Snapshot) -> None:
        """Upsert the dex state + each coin (transaction)."""
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

    async def record_new_events(self, events: list[Event]) -> list[Event]:
        """Insert events; return the ones ACTUALLY inserted (fresh dedup_key)."""
        inserted: list[Event] = []
        async with self.pool.acquire() as conn:
            for ev in events:
                row = await conn.fetchrow(
                    "INSERT INTO events (dex, coin, event_type, old_value, new_value, dedup_key) "
                    "VALUES ($1,$2,$3,$4,$5,$6) "
                    "ON CONFLICT (dedup_key) DO NOTHING RETURNING id",
                    ev.dex, ev.coin, ev.event_type, ev.old_value, ev.new_value, ev.dedup_key,
                )
                if row is not None:  # a row was created = fresh event
                    inserted.append(ev)
        return inserted

    # --- heartbeat / status (feeds the public page) ---

    async def record_heartbeat(
        self, dex: str, started_at: datetime, markets_count: int, errors: int
    ) -> None:
        """Update the bot's status row (upsert) — called every cycle."""
        await self.pool.execute(
            "INSERT INTO bot_status (dex, started_at, last_cycle_at, markets_count, consecutive_errors) "
            "VALUES ($1, $2, now(), $3, $4) "
            "ON CONFLICT (dex) DO UPDATE SET "
            "  started_at = EXCLUDED.started_at, last_cycle_at = now(), "
            "  markets_count = EXCLUDED.markets_count, consecutive_errors = EXCLUDED.consecutive_errors",
            dex, started_at, markets_count, errors,
        )

    async def get_status(self, dex: str) -> asyncpg.Record | None:
        """Current status row (or None if the bot has never run)."""
        return await self.pool.fetchrow(
            "SELECT dex, started_at, last_cycle_at, markets_count, consecutive_errors "
            "FROM bot_status WHERE dex = $1",
            dex,
        )

    async def recent_events(
        self, dex: str, limit: int = 20, offset: int = 0
    ) -> list[asyncpg.Record]:
        """A page of detected events (most recent first): `limit` rows from `offset`."""
        return await self.pool.fetch(
            "SELECT created_at, event_type, coin, old_value, new_value "
            "FROM events WHERE dex = $1 ORDER BY id DESC LIMIT $2 OFFSET $3",
            dex, limit, offset,
        )

    async def count_events(self, dex: str) -> int:
        """Total number of recorded events for `dex` (for status-page pagination)."""
        return await self.pool.fetchval(
            "SELECT count(*) FROM events WHERE dex = $1", dex
        )

    async def list_coins(self, dex: str) -> list[str]:
        """Names of the markets currently tracked for `dex` (alphabetical)."""
        rows = await self.pool.fetch(
            "SELECT coin FROM market_state WHERE dex = $1 ORDER BY coin", dex
        )
        return [r["coin"] for r in rows]

    async def mark_notified(self, dedup_keys: list[str]) -> None:
        """Set `notified_at = now()` for events actually sent.

        An event inserted but never marked (notified_at NULL) = recorded but not delivered
        (e.g. send failure) → queryable.
        """
        if not dedup_keys:
            return
        await self.pool.execute(
            "UPDATE events SET notified_at = now() WHERE dedup_key = ANY($1::text[])",
            dedup_keys,
        )


def _to_num(v: str | None) -> Decimal | None:
    return None if v is None else Decimal(v)
