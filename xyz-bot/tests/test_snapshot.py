"""Tests M1 : construction du snapshot à partir des réponses meta + perpDexLimits.

Sans réseau : on alimente `build_snapshot` avec les fixtures capturées sur l'API réelle.
"""
from src.snapshot import build_snapshot

from .fixtures import META_RESPONSE, PERP_DEX_LIMITS_RESPONSE


def make_snapshot():
    return build_snapshot("xyz", META_RESPONSE, PERP_DEX_LIMITS_RESPONSE)


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
    """Découverte M1 : marginMode absent = marché cross → doit devenir "normal".

    Garantit que le diff captera bien la transition `noCross → normal (cross)`
    au lieu de voir `noCross → None`.
    """
    assert make_snapshot().coins["xyz:XYZ100"].margin_mode == "normal"


def test_delisted_market_flagged():
    assert make_snapshot().coins["xyz:DXY"].is_listed is False
    assert make_snapshot().coins["xyz:HOOD"].is_listed is True


def test_oi_cap_values_are_strings():
    """Les caps restent des strings décimales (pas de float) pour éviter toute
    perte de précision sur de gros notionnels."""
    snap = make_snapshot()
    assert isinstance(snap.total_oi_cap, str)
    assert isinstance(snap.coins["xyz:XYZ100"].oi_cap, str)


def test_halt_field_absent_when_no_halt():
    """Aucun champ isHalted dans la fixture (aucun marché halté) → is_halted = None.
    À reconfirmer sur un vrai halt avant M2."""
    assert make_snapshot().coins["xyz:HOOD"].is_halted is None


def test_coin_missing_oi_cap_is_none():
    """Un coin présent dans meta mais absent de coinToOiCap → oi_cap = None (pas d'erreur)."""
    meta = {"universe": [{"name": "xyz:GHOST", "maxLeverage": 5, "marginTableId": 5,
                          "onlyIsolated": True, "marginMode": "noCross"}],
            "marginTables": []}
    snap = build_snapshot("xyz", meta, {"totalOiCap": "1.0", "coinToOiCap": []})
    assert snap.coins["xyz:GHOST"].oi_cap is None
