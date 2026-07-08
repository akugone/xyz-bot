"""Render an event into a compact "card" PNG (logo on the left, text on the right).

Why a card and not a raw logo photo: Telegram's `sendPhoto` always shows a full-width
image. Sending the bare logo looks huge and ugly; composing a tight banner (logo tile +
text) gives a clean, controlled layout. The flat text still travels as the photo *caption*
(see `telegram.send_photo`), so it stays copyable and drives the push-notification preview.

Logos are a **static pack** under `assets/logos/{SYMBOL}.png`, built once by
`scripts/fetch_logos.py` — never fetched at runtime. Tickers with no logo (forex, indices,
commodities, brand-new listings) fall back to a colored category tile showing the symbol,
so rendering never fails. A bundled font (`assets/fonts/`) keeps the output identical on
the Linux VPS.
"""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .events import (
    DELISTED,
    FUNDING_MULT_CHANGE,
    GROWTH_MODE_CHANGE,
    HALT,
    LEVERAGE_CHANGE,
    MARGIN_MODE_CHANGE,
    NEW_MARKET,
    OI_CAP_CHANGE,
    RELISTED,
    TOTAL_OI_CAP_CHANGE,
    UNHALT,
    Event,
)
from .messages import event_parts

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
_LOGOS = _ASSETS / "logos"
_FONTS = _ASSETS / "fonts"

# --- canvas geometry ---
W, H = 1000, 240
_PAD = 28
_TILE = H - 2 * _PAD  # square logo/fallback tile side
_TEXT_X = _PAD + _TILE + 40
_TEXT_W = W - _TEXT_X - _PAD  # available width for the text column

# --- palette ---
_BG = (24, 37, 51)
_WHITE = (255, 255, 255)
_TITLE = (233, 237, 240)
_SUB = (160, 174, 184)
_GREEN = (45, 212, 120)
_BLUE = (90, 170, 255)
_RED = (240, 90, 90)
_AMBER = (230, 180, 70)

# event_type → accent color of the badge line
_ACCENT = {
    NEW_MARKET: _GREEN,
    OI_CAP_CHANGE: _GREEN,
    TOTAL_OI_CAP_CHANGE: _GREEN,
    GROWTH_MODE_CHANGE: _GREEN,
    UNHALT: _GREEN,
    RELISTED: _GREEN,
    MARGIN_MODE_CHANGE: _BLUE,
    LEVERAGE_CHANGE: _BLUE,
    FUNDING_MULT_CHANGE: _AMBER,
    HALT: _RED,
    DELISTED: _RED,
}

# --- asset-class fallback tiles (no logo available / not trustworthy) ---
_METALS = {"GOLD", "SILVER", "PLATINUM", "PALLADIUM", "COPPER", "ALUMINIUM"}
_ENERGY = {"CL", "BRENTOIL", "NATGAS", "TTF", "XLE"}
_AGRI = {"CORN", "WHEAT"}
_FOREX = {"EUR", "JPY", "GBP", "KRW", "DXY"}
_INDEX = {"SP500", "VIX", "JP225", "NIFTY", "KR200", "IBOV",
          "EWY", "EWJ", "EWZ", "EWT", "SMH", "URNM", "URANIUM"}

# category → (tile background, text color)
_CAT_STYLE = {
    "metal": ((212, 175, 55), (40, 32, 0)),
    "energy": ((224, 122, 63), _WHITE),
    "agri": ((120, 180, 90), (24, 37, 18)),
    "forex": ((80, 170, 160), _WHITE),
    "index": ((150, 120, 220), _WHITE),
    "other": ((90, 104, 120), _WHITE),
}


def symbol_of(subject: str) -> str:
    """"xyz:NVDA" -> "NVDA"; "xyz" -> "XYZ" (the dex itself)."""
    return subject.split(":", 1)[1] if ":" in subject else subject.upper()


def category_of(symbol: str) -> str:
    """Asset class of a symbol, for the fallback tile color/grouping."""
    if symbol in _METALS:
        return "metal"
    if symbol in _ENERGY:
        return "energy"
    if symbol in _AGRI:
        return "agri"
    if symbol in _FOREX:
        return "forex"
    if symbol in _INDEX:
        return "index"
    return "other"


# trade.xyz brand fonts (Geist family, SIL OFL). Geist for text, Geist Mono for the
# numeric detail line — mirrors the trading UI. Variable fonts: weight set per instance.
_SANS = "Geist.ttf"
_MONO = "GeistMono.ttf"


@lru_cache(maxsize=24)
def _font(mono: bool, weight: str, size: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(_FONTS / (_MONO if mono else _SANS)), size)
    try:
        f.set_variation_by_name(weight)  # "Regular" / "Bold" (named instance)
    except OSError:
        pass  # non-variable build → keep default weight
    return f


def _fit_font(draw: ImageDraw.ImageDraw, text: str, size: int, max_w: int,
              *, mono: bool = False, weight: str = "Bold",
              min_size: int = 22) -> ImageFont.FreeTypeFont:
    """Largest font (down to min_size) at which `text` fits in `max_w`."""
    while size > min_size:
        f = _font(mono, weight, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return _font(mono, weight, min_size)


def _logo_path(symbol: str) -> Path | None:
    p = _LOGOS / f"{symbol}.png"
    return p if p.exists() else None


def _draw_tile(img: Image.Image, draw: ImageDraw.ImageDraw, symbol: str) -> None:
    """Left square: real logo on white if we have one, else a colored category tile."""
    x0, y0, x1, y1 = _PAD, _PAD, _PAD + _TILE, _PAD + _TILE
    logo = _logo_path(symbol)
    if logo is not None:
        draw.rounded_rectangle([x0, y0, x1, y1], radius=28, fill=_WHITE)
        lg = Image.open(logo).convert("RGBA")
        box = _TILE - 36
        lg.thumbnail((box, box))
        img.paste(lg, (x0 + (_TILE - lg.width) // 2, y0 + (_TILE - lg.height) // 2), lg)
        return
    # fallback tile: category color + symbol text
    bg, fg = _CAT_STYLE[category_of(symbol)]
    draw.rounded_rectangle([x0, y0, x1, y1], radius=28, fill=bg)
    f = _fit_font(draw, symbol, 58, _TILE - 24, weight="Bold", min_size=20)
    tw = draw.textlength(symbol, font=f)
    bb = f.getbbox(symbol)
    th = bb[3] - bb[1]
    draw.text((x0 + (_TILE - tw) / 2, y0 + (_TILE - th) / 2 - bb[1]), symbol, font=f, fill=fg)


def render_card(ev: Event) -> bytes:
    """Render `ev` as a PNG banner and return the raw bytes (for `sendPhoto`)."""
    p = event_parts(ev)
    accent = _ACCENT.get(ev.event_type, _BLUE)

    img = Image.new("RGB", (W, H), _BG)
    draw = ImageDraw.Draw(img)

    _draw_tile(img, draw, symbol_of(p.subject))

    # right column: badge (Geist bold) · subject (Geist bold, big) · detail (Geist Mono)
    badge = p.label.upper()
    draw.text((_TEXT_X, 50), badge, font=_font(False, "Bold", 30), fill=accent)

    title_font = _fit_font(draw, p.subject, 52, _TEXT_W, weight="Bold")
    draw.text((_TEXT_X, 92), p.subject, font=title_font, fill=_TITLE)

    if p.detail:
        detail_font = _fit_font(draw, p.detail, 28, _TEXT_W,
                                mono=True, weight="Regular", min_size=16)
        draw.text((_TEXT_X, 162), p.detail, font=detail_font, fill=_SUB)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
