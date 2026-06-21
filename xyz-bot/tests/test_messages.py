"""Tests M3 : formatage des events en messages Telegram (pur, sans réseau)."""
from src.events import (
    DELISTED,
    HALT,
    LEVERAGE_CHANGE,
    MARGIN_MODE_CHANGE,
    NEW_MARKET,
    OI_CAP_CHANGE,
    TOTAL_OI_CAP_CHANGE,
    UNHALT,
    Event,
)
from src.messages import format_event


def test_oi_cap_change_formats_amounts():
    msg = format_event(Event("xyz", "xyz:NVDA", OI_CAP_CHANGE, "5000000.0", "10000000.0"))
    assert "OI cap changed — xyz:NVDA" in msg
    assert "5,000,000 → 10,000,000 USDC" in msg


def test_total_oi_cap_change_is_dex_level():
    msg = format_event(Event("xyz", None, TOTAL_OI_CAP_CHANGE, "7000000000.0", "8000000000.0"))
    assert "Dex-wide OI cap — xyz" in msg
    assert "7,000,000,000 → 8,000,000,000 USDC" in msg


def test_margin_mode_to_cross_mentions_cross():
    msg = format_event(Event("xyz", "xyz:TSLA", MARGIN_MODE_CHANGE, "noCross", "normal"))
    assert "Margin mode — xyz:TSLA" in msg
    assert "noCross → normal (cross enabled)" in msg


def test_margin_mode_without_cross_has_no_suffix():
    msg = format_event(Event("xyz", "xyz:TSLA", MARGIN_MODE_CHANGE, "strictIsolated", "noCross"))
    assert "strictIsolated → noCross" in msg
    assert "cross enabled" not in msg


def test_leverage_change_has_x_suffix():
    msg = format_event(Event("xyz", "xyz:AAPL", LEVERAGE_CHANGE, "10", "20"))
    assert "Max leverage — xyz:AAPL" in msg
    assert "10x → 20x" in msg


def test_new_market_detail_unpacked():
    ev = Event("xyz", "xyz:META", NEW_MARKET, None,
               "lev=10;mode=strictIsolated;oi_cap=2000000.0")
    msg = format_event(ev)
    assert "New market listed — xyz:META" in msg
    assert "leverage 10x · strictIsolated · OI cap 2,000,000" in msg


def test_halt_and_unhalt():
    assert "⛔" in format_event(Event("xyz", "xyz:AMZN", HALT, "active", "halted"))
    assert "✅" in format_event(Event("xyz", "xyz:AMZN", UNHALT, "halted", "active"))


def test_delisted():
    assert "delisted — xyz:DXY" in format_event(Event("xyz", "xyz:DXY", DELISTED, "listed", "delisted"))


def test_amount_keeps_non_integer_and_raw():
    # valeur fractionnaire conservée
    msg = format_event(Event("xyz", "xyz:X", OI_CAP_CHANGE, "1000000.5", "2000000.25"))
    assert "1,000,000.5 → 2,000,000.25" in msg
    # valeur non numérique → brute, pas de crash
    msg2 = format_event(Event("xyz", "xyz:X", OI_CAP_CHANGE, None, "n/a"))
    assert "? → n/a" in msg2
