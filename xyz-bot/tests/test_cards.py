"""Card rendering tests — pure (no network). Asserts valid PNG output + classification."""
import io

from PIL import Image

from src.cards import category_of, render_card, symbol_of
from src.events import (
    GROWTH_MODE_CHANGE,
    HALT,
    NEW_MARKET,
    OI_CAP_CHANGE,
    TOTAL_OI_CAP_CHANGE,
    Event,
)


def _open(png: bytes) -> Image.Image:
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "output is not a PNG"
    im = Image.open(io.BytesIO(png))
    im.load()
    return im


def test_symbol_of():
    assert symbol_of("xyz:NVDA") == "NVDA"
    assert symbol_of("xyz") == "XYZ"  # the dex itself


def test_category_classification():
    assert category_of("GOLD") == "metal"
    assert category_of("CL") == "energy"
    assert category_of("EUR") == "forex"
    assert category_of("SP500") == "index"
    assert category_of("CORN") == "agri"
    assert category_of("NVDA") == "other"  # equity → logo or slate tile


def test_render_with_real_logo_returns_png():
    # NVDA is in the committed logo pack → uses the white logo tile path
    im = _open(render_card(Event("xyz", "xyz:NVDA", NEW_MARKET, None,
                                 "lev=10;mode=noCross;oi_cap=25000000.0")))
    assert im.size == (1000, 240)


def test_render_with_fallback_tile_returns_png():
    # GOLD has no logo (and must NOT) → colored category tile, still a valid card
    im = _open(render_card(Event("xyz", "xyz:GOLD", OI_CAP_CHANGE, "1000000.0", "2000000.0")))
    assert im.size == (1000, 240)


def test_render_event_without_detail_line():
    # HALT has no second line — must still render fine
    _open(render_card(Event("xyz", "xyz:AMZN", HALT, "active", "halted")))


def test_render_dex_level_event():
    # coin is None (dex-wide) → subject is the dex, symbol resolves to "XYZ"
    _open(render_card(Event("xyz", None, TOTAL_OI_CAP_CHANGE, "7000000000.0", "8000000000.0")))


def test_render_long_symbol_without_logo():
    # long fallback ticker must not overflow / crash (font auto-fit)
    _open(render_card(Event("xyz", "xyz:SOFTBANK", GROWTH_MODE_CHANGE, "enabled", "disabled")))
