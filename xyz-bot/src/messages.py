"""Format events into Telegram messages (text).

Pure module (no network): `format_event(Event) -> str`. The formats follow the SPEC.
Testable in isolation; consumed by `src/telegram.py`.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .events import (
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


def format_event(ev: Event) -> str:
    coin = ev.coin or ev.dex
    t = ev.event_type

    if t == OI_CAP_CHANGE:
        return f"🟢 OI cap changed — {coin}\n{_amount(ev.old_value)} → {_amount(ev.new_value)} USDC"

    if t == TOTAL_OI_CAP_CHANGE:
        return f"🟢 Dex-wide OI cap — {ev.dex}\n{_amount(ev.old_value)} → {_amount(ev.new_value)} USDC"

    if t == MARGIN_MODE_CHANGE:
        extra = " (cross enabled)" if ev.new_value == "normal" else ""
        return f"⚙️ Margin mode — {coin}\n{ev.old_value} → {ev.new_value}{extra}"

    if t == LEVERAGE_CHANGE:
        return f"📈 Max leverage — {coin}\n{ev.old_value}x → {ev.new_value}x"

    if t == NEW_MARKET:
        return f"🆕 New market listed — {coin}\n{_new_market_detail(ev.new_value)}"

    if t == HALT:
        return f"⛔ Trading halted — {coin}"

    if t == UNHALT:
        return f"✅ Trading resumed — {coin}"

    if t == DELISTED:
        return f"🗑️ Market delisted — {coin}"

    # generic fallback (shouldn't happen if all types are handled)
    return f"ℹ️ {t} — {coin}: {ev.old_value} → {ev.new_value}"


def _amount(v: str | None) -> str:
    """Format a notional: "5000000.0" → "5,000,000". Returns the raw value if non-numeric."""
    if v is None:
        return "?"
    try:
        d = Decimal(v)
    except (InvalidOperation, ValueError):
        return v
    if d == d.to_integral_value():
        return f"{int(d):,}"
    return f"{d:,}"


def _new_market_detail(v: str | None) -> str:
    """Unpack a new market's new_value ("lev=10;mode=strictIsolated;oi_cap=2000000.0")."""
    parts = dict(p.split("=", 1) for p in v.split(";") if "=" in p) if v else {}
    lev = parts.get("lev", "?")
    mode = parts.get("mode", "?")
    oi = _amount(parts.get("oi_cap"))
    return f"leverage {lev}x · {mode} · OI cap {oi}"
