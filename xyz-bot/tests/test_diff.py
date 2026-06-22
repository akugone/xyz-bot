"""Diff engine tests.

Pure in-memory computation — no DB, no network. We build snapshots by hand and check
the produced events.
"""
import copy

import pytest

from src.events import (
    DELISTED,
    GROWTH_MODE_CHANGE,
    HALT,
    LEVERAGE_CHANGE,
    MARGIN_MODE_CHANGE,
    NEW_MARKET,
    OI_CAP_CHANGE,
    RELISTED,
    TOTAL_OI_CAP_CHANGE,
    UNHALT,
    diff,
)
from src.snapshot import CoinState, Snapshot


def base_snapshot() -> Snapshot:
    return Snapshot(
        dex="xyz",
        total_oi_cap="7000000000.0",
        coins={
            "xyz:HOOD": CoinState("xyz:HOOD", max_leverage=10, margin_mode="noCross",
                                  margin_table_id=10, oi_cap="50000000.0", is_listed=True),
            "xyz:XYZ100": CoinState("xyz:XYZ100", max_leverage=30, margin_mode="normal",
                                    margin_table_id=30, oi_cap="100000000.0", is_listed=True),
        },
    )


def test_seed_first_run_emits_nothing():
    """prev is None → silent seed: no event (we don't ping the baseline)."""
    assert diff(None, base_snapshot()) == []


def test_no_change_emits_nothing():
    prev = base_snapshot()
    curr = copy.deepcopy(prev)
    assert diff(prev, curr) == []


def test_oi_cap_change():
    prev = base_snapshot()
    curr = copy.deepcopy(prev)
    curr.coins["xyz:HOOD"].oi_cap = "100000000.0"
    events = diff(prev, curr)
    assert len(events) == 1
    e = events[0]
    assert (e.event_type, e.coin, e.old_value, e.new_value) == (
        OI_CAP_CHANGE, "xyz:HOOD", "50000000.0", "100000000.0")


def test_total_oi_cap_change_is_dex_level():
    prev = base_snapshot()
    curr = copy.deepcopy(prev)
    curr.total_oi_cap = "8000000000.0"
    events = diff(prev, curr)
    assert len(events) == 1
    assert events[0].event_type == TOTAL_OI_CAP_CHANGE
    assert events[0].coin is None


def test_margin_mode_to_cross():
    """The move to cross shows up as noCross → normal (see finding)."""
    prev = base_snapshot()
    curr = copy.deepcopy(prev)
    curr.coins["xyz:HOOD"].margin_mode = "normal"
    events = diff(prev, curr)
    assert len(events) == 1
    assert (events[0].event_type, events[0].old_value, events[0].new_value) == (
        MARGIN_MODE_CHANGE, "noCross", "normal")


def test_leverage_change():
    prev = base_snapshot()
    curr = copy.deepcopy(prev)
    curr.coins["xyz:HOOD"].max_leverage = 20
    events = diff(prev, curr)
    assert len(events) == 1
    assert (events[0].event_type, events[0].old_value, events[0].new_value) == (
        LEVERAGE_CHANGE, "10", "20")


def test_new_market():
    prev = base_snapshot()
    curr = copy.deepcopy(prev)
    curr.coins["xyz:NVDA"] = CoinState("xyz:NVDA", max_leverage=10, margin_mode="strictIsolated",
                                       margin_table_id=10, oi_cap="2000000.0", is_listed=True)
    events = diff(prev, curr)
    assert len(events) == 1
    assert events[0].event_type == NEW_MARKET
    assert events[0].coin == "xyz:NVDA"
    assert events[0].old_value is None


def test_halt_and_unhalt():
    prev = base_snapshot()
    # halt: is_halted None/False → True
    curr = copy.deepcopy(prev)
    curr.coins["xyz:HOOD"].is_halted = True
    events = diff(prev, curr)
    assert [e.event_type for e in events] == [HALT]

    # resume: True → False
    prev2 = copy.deepcopy(curr)
    curr2 = copy.deepcopy(curr)
    curr2.coins["xyz:HOOD"].is_halted = False
    events2 = diff(prev2, curr2)
    assert [e.event_type for e in events2] == [UNHALT]


def test_delisting():
    prev = base_snapshot()
    curr = copy.deepcopy(prev)
    curr.coins["xyz:HOOD"].is_listed = False
    events = diff(prev, curr)
    assert [e.event_type for e in events] == [DELISTED]


def test_relisting():
    """A delisted market coming back (is_listed False → True) fires `relisted`, not new_market."""
    prev = base_snapshot()
    prev.coins["xyz:HOOD"].is_listed = False     # was delisted
    curr = copy.deepcopy(prev)
    curr.coins["xyz:HOOD"].is_listed = True      # comes back
    events = diff(prev, curr)
    assert [e.event_type for e in events] == [RELISTED]
    assert (events[0].old_value, events[0].new_value) == ("delisted", "listed")


def test_growth_mode_toggle():
    prev = base_snapshot()
    prev.coins["xyz:HOOD"].growth_mode = True
    curr = copy.deepcopy(prev)
    curr.coins["xyz:HOOD"].growth_mode = False
    events = diff(prev, curr)
    assert len(events) == 1
    assert (events[0].event_type, events[0].old_value, events[0].new_value) == (
        GROWTH_MODE_CHANGE, "enabled", "disabled")


def test_growth_mode_none_edges_no_event():
    """A None/absent growth_mode edge must not fire (avoids noise)."""
    prev = base_snapshot()                      # growth_mode defaults to None
    curr = copy.deepcopy(prev)
    curr.coins["xyz:HOOD"].growth_mode = True   # None → True must NOT emit
    assert not any(e.event_type == GROWTH_MODE_CHANGE for e in diff(prev, curr))


def test_multiple_changes_one_coin():
    prev = base_snapshot()
    curr = copy.deepcopy(prev)
    curr.coins["xyz:HOOD"].oi_cap = "100000000.0"
    curr.coins["xyz:HOOD"].max_leverage = 20
    events = diff(prev, curr)
    types = {e.event_type for e in events}
    assert types == {OI_CAP_CHANGE, LEVERAGE_CHANGE}


def test_dedup_key_stable_and_distinct():
    prev = base_snapshot()
    curr = copy.deepcopy(prev)
    curr.coins["xyz:HOOD"].oi_cap = "100000000.0"
    e1 = diff(prev, curr)[0]
    e2 = diff(prev, copy.deepcopy(curr))[0]
    # same change detected twice → same dedup_key (idempotency)
    assert e1.dedup_key == e2.dedup_key
    # a different event → different key
    other = base_snapshot()
    other.coins["xyz:HOOD"].max_leverage = 20
    assert diff(prev, other)[0].dedup_key != e1.dedup_key


def test_unchanged_halt_none_no_event():
    """is_halted None → None must not produce an event (nominal case, no halt)."""
    prev = base_snapshot()
    curr = copy.deepcopy(prev)
    assert not any(e.event_type in (HALT, UNHALT) for e in diff(prev, curr))
