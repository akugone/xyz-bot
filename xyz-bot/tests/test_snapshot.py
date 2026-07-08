"""Snapshot building tests, from meta + perpDexLimits responses.

No network: `build_snapshot` is fed with fixtures captured from the real API.
"""
from src.snapshot import build_snapshot

from .fixtures import META_RESPONSE, PERP_DEX_LIMITS_RESPONSE, XYZ_PERP_DEX


def make_snapshot():
    return build_snapshot("xyz", META_RESPONSE, PERP_DEX_LIMITS_RESPONSE, XYZ_PERP_DEX)


def test_funding_multiplier_parsed():
    hood = make_snapshot().coins["xyz:HOOD"]
    assert hood.funding_mult == "0.5"


def test_funding_multiplier_absent_when_no_perp_dex():
    # perp_dex omitted (e.g. endpoint unavailable) → funding_mult stays None, no crash
    snap = build_snapshot("xyz", META_RESPONSE, PERP_DEX_LIMITS_RESPONSE)
    assert snap.coins["xyz:HOOD"].funding_mult is None


def test_snapshot_basics():
    snap = make_snapshot()
    assert snap.dex == "xyz"
    assert snap.total_oi_cap == "7000000000.0"
    assert set(snap.coins) == {"xyz:HOOD", "xyz:MINIMAX", "xyz:XYZ100", "xyz:DXY"}


def test_structural_fields_parsed():
    hood = make_snapshot().coins["xyz:HOOD"]
    assert hood.max_leverage == 10
    assert hood.margin_table_id == 10
    assert hood.oi_cap == "50000000.0"
    assert hood.growth_mode is True


def test_margin_mode_isolated_preserved():
    coins = make_snapshot().coins
    assert coins["xyz:HOOD"].margin_mode == "noCross"
    assert coins["xyz:MINIMAX"].margin_mode == "strictIsolated"


def test_margin_mode_absent_normalized_to_normal():
    """Finding: absent marginMode = cross market → must become "normal".

    Ensures the diff catches the `noCross → normal (cross)` transition instead of seeing
    `noCross → None`.
    """
    assert make_snapshot().coins["xyz:XYZ100"].margin_mode == "normal"


def test_delisted_market_flagged():
    assert make_snapshot().coins["xyz:DXY"].is_listed is False
    assert make_snapshot().coins["xyz:HOOD"].is_listed is True


def test_oi_cap_values_are_strings():
    """Caps stay decimal strings (not floats) to avoid precision loss on large notionals."""
    snap = make_snapshot()
    assert isinstance(snap.total_oi_cap, str)
    assert isinstance(snap.coins["xyz:XYZ100"].oi_cap, str)


def test_halt_field_absent_when_no_halt():
    """No isHalted field in the fixture (no halted market) → is_halted = None.
    To re-confirm on a real halt."""
    assert make_snapshot().coins["xyz:HOOD"].is_halted is None


def test_coin_missing_oi_cap_is_none():
    """A coin present in meta but absent from coinToOiCap → oi_cap = None (no error)."""
    meta = {"universe": [{"name": "xyz:GHOST", "maxLeverage": 5, "marginTableId": 5,
                          "onlyIsolated": True, "marginMode": "noCross"}],
            "marginTables": []}
    snap = build_snapshot("xyz", meta, {"totalOiCap": "1.0", "coinToOiCap": []})
    assert snap.coins["xyz:GHOST"].oi_cap is None
