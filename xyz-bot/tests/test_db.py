"""Tests M2-bis : persistance Postgres (intégration).

Nécessite une Postgres de test. DSN via `TEST_PG_DSN` (défaut : base locale `xyzbot_test`).
Si la base n'est pas joignable, les tests sont SKIPPÉS (la suite reste verte sans DB).

Note event loop : asyncpg lie son pool à la boucle où il est créé. On exécute donc
chaque test dans UN SEUL `asyncio.run` (connexion + travail + fermeture), sans partager
le pool entre boucles.
"""
import asyncio
import os

import asyncpg
import pytest

from src.db import Database
from src.events import OI_CAP_CHANGE, diff
from src.snapshot import CoinState, Snapshot

TEST_DSN = os.getenv("TEST_PG_DSN", "postgresql://leclercqmartin@localhost:5432/xyzbot_test")


def _snapshot(oi_hood="50000000.0", total="7000000000.0") -> Snapshot:
    return Snapshot(
        dex="xyz",
        total_oi_cap=total,
        coins={
            "xyz:HOOD": CoinState("xyz:HOOD", max_leverage=10, margin_mode="noCross",
                                  margin_table_id=10, oi_cap=oi_hood, is_listed=True),
            "xyz:XYZ100": CoinState("xyz:XYZ100", max_leverage=30, margin_mode="normal",
                                    margin_table_id=30, oi_cap="100000000.0", is_listed=True),
        },
    )


def run_db_test(scenario):
    """Lance `scenario(db)` dans une base fraîche, ou skip si Postgres indisponible."""
    async def main():
        db = Database(TEST_DSN)
        try:
            await db.connect()
        except (OSError, asyncpg.PostgresError) as e:
            pytest.skip(f"Postgres de test indisponible: {e}")
        try:
            await db.init_schema()
            await db.pool.execute("TRUNCATE market_state, dex_state, events")
            await scenario(db)
        finally:
            await db.close()

    asyncio.run(main())


def test_load_returns_none_when_empty():
    async def scenario(db):
        assert await db.load_snapshot("xyz") is None
    run_db_test(scenario)


def test_save_then_load_roundtrip():
    async def scenario(db):
        await db.save_snapshot(_snapshot())
        loaded = await db.load_snapshot("xyz")
        assert loaded is not None
        assert loaded.total_oi_cap == "7000000000.0"
        assert set(loaded.coins) == {"xyz:HOOD", "xyz:XYZ100"}
        hood = loaded.coins["xyz:HOOD"]
        assert hood.max_leverage == 10
        assert hood.margin_mode == "noCross"
        assert hood.oi_cap == "50000000.0"   # str préservée après aller-retour NUMERIC
        assert hood.is_listed is True
        assert hood.is_halted is None
    run_db_test(scenario)


def test_save_is_upsert_not_duplicate():
    async def scenario(db):
        await db.save_snapshot(_snapshot(oi_hood="50000000.0"))
        await db.save_snapshot(_snapshot(oi_hood="99000000.0"))  # re-save, valeur modifiée
        loaded = await db.load_snapshot("xyz")
        assert len(loaded.coins) == 2  # pas de doublon de ligne
        assert loaded.coins["xyz:HOOD"].oi_cap == "99000000.0"  # dernière valeur gagne
    run_db_test(scenario)


def test_record_new_events_is_idempotent():
    async def scenario(db):
        prev = _snapshot(oi_hood="50000000.0")
        await db.save_snapshot(prev)
        curr = _snapshot(oi_hood="100000000.0")
        events = diff(prev, curr)
        assert [e.event_type for e in events] == [OI_CAP_CHANGE]

        first = await db.record_new_events(events)
        assert len(first) == 1            # inédit → inséré
        second = await db.record_new_events(events)
        assert second == []               # même dedup_key → rien inséré (anti-doublon)
    run_db_test(scenario)


def test_full_cycle_seed_then_change():
    """Reproduit la boucle : seed silencieux, puis détection + persistance d'un changement."""
    async def scenario(db):
        # cycle 1 : pas de baseline → seed (aucun event), on persiste
        prev = await db.load_snapshot("xyz")
        assert prev is None
        base = _snapshot(oi_hood="50000000.0")
        assert diff(prev, base) == []
        await db.save_snapshot(base)

        # cycle 2 : OI cap augmente → 1 event inédit
        prev = await db.load_snapshot("xyz")
        changed = _snapshot(oi_hood="100000000.0")
        new_events = await db.record_new_events(diff(prev, changed))
        await db.save_snapshot(changed)
        assert [e.event_type for e in new_events] == [OI_CAP_CHANGE]

        # cycle 3 : plus de changement → aucun event
        prev = await db.load_snapshot("xyz")
        assert await db.record_new_events(diff(prev, _snapshot(oi_hood="100000000.0"))) == []
    run_db_test(scenario)
