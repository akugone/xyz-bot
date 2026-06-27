"""Format events into Telegram messages (text).

Pure module (no network). Two entry points:
  - `event_parts(Event) -> EventParts`: the structured pieces (emoji, label, subject,
    detail) — the single source of truth for an event's wording. Consumed by `cards.py`
    to render the image and by `format_event` below.
  - `format_event(Event) -> str`: the flat text used as the message / photo caption.

The formats follow the SPEC. Testable in isolation; consumed by `src/telegram.py`.
"""
from __future__ import annotations

from dataclasses import dataclass

from .events import (
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
    Event,
)
from .util import format_amount as _amount


@dataclass(frozen=True)
class EventParts:
    """An event broken into display pieces, shared by the text and the card renderer."""

    emoji: str
    label: str  # short human label, e.g. "OI cap changed"
    subject: str  # the coin (e.g. "xyz:NVDA") or the dex for dex-wide events
    detail: str | None  # second line, e.g. "5,000,000 → 25,000,000 USDC"; None = no detail


def event_parts(ev: Event) -> EventParts:
    coin = ev.coin or ev.dex
    t = ev.event_type

    if t == OI_CAP_CHANGE:
        return EventParts("🟢", "OI cap changed", coin,
                          f"{_amount(ev.old_value)} → {_amount(ev.new_value)} USDC")

    if t == TOTAL_OI_CAP_CHANGE:
        return EventParts("🟢", "Dex-wide OI cap", ev.dex,
                          f"{_amount(ev.old_value)} → {_amount(ev.new_value)} USDC")

    if t == MARGIN_MODE_CHANGE:
        extra = " (cross enabled)" if ev.new_value == "normal" else ""
        return EventParts("⚙️", "Margin mode", coin, f"{ev.old_value} → {ev.new_value}{extra}")

    if t == LEVERAGE_CHANGE:
        return EventParts("📈", "Max leverage", coin, f"{ev.old_value}x → {ev.new_value}x")

    if t == GROWTH_MODE_CHANGE:
        return EventParts("🌱", "Growth mode", coin, f"{ev.old_value} → {ev.new_value}")

    if t == NEW_MARKET:
        return EventParts("🆕", "New market listed", coin, _new_market_detail(ev.new_value))

    if t == HALT:
        return EventParts("⛔", "Trading halted", coin, None)

    if t == UNHALT:
        return EventParts("✅", "Trading resumed", coin, None)

    if t == DELISTED:
        return EventParts("🗑️", "Market delisted", coin, None)

    if t == RELISTED:
        return EventParts("♻️", "Market relisted", coin, None)

    # generic fallback (shouldn't happen if all types are handled)
    return EventParts("ℹ️", t, coin, f"{ev.old_value} → {ev.new_value}")


def format_event(ev: Event) -> str:
    """Flat text for a message / photo caption, composed from `event_parts`."""
    p = event_parts(ev)
    head = f"{p.emoji} {p.label} · {p.subject}"
    return f"{head}\n{p.detail}" if p.detail else head


def _new_market_detail(v: str | None) -> str:
    """Unpack a new market's new_value ("lev=10;mode=strictIsolated;oi_cap=2000000.0")."""
    parts = dict(p.split("=", 1) for p in v.split(";") if "=" in p) if v else {}
    lev = parts.get("lev", "?")
    mode = parts.get("mode", "?")
    oi = _amount(parts.get("oi_cap"))
    return f"leverage {lev}x · {mode} · OI cap {oi}"
