"""Formatage des events en messages Telegram (texte).

Module pur (aucun réseau) : `format_event(Event) -> str`. Les formats suivent le SPEC §7.
Testable isolément ; consommé par `src/telegram.py`.
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
        return f"🟢 OI cap modifié — {coin}\n{_amount(ev.old_value)} → {_amount(ev.new_value)} USDC"

    if t == TOTAL_OI_CAP_CHANGE:
        return f"🟢 OI cap global du dex {ev.dex}\n{_amount(ev.old_value)} → {_amount(ev.new_value)} USDC"

    if t == MARGIN_MODE_CHANGE:
        extra = " (cross activé)" if ev.new_value == "normal" else ""
        return f"⚙️ Mode de marge — {coin}\n{ev.old_value} → {ev.new_value}{extra}"

    if t == LEVERAGE_CHANGE:
        return f"📈 Levier max — {coin}\n{ev.old_value}x → {ev.new_value}x"

    if t == NEW_MARKET:
        return f"🆕 Nouveau marché listé — {coin}\n{_new_market_detail(ev.new_value)}"

    if t == HALT:
        return f"⛔ Trading halté — {coin}"

    if t == UNHALT:
        return f"✅ Trading repris — {coin}"

    if t == DELISTED:
        return f"🗑️ Marché delisté — {coin}"

    # fallback générique (ne devrait pas arriver si tous les types sont gérés)
    return f"ℹ️ {t} — {coin} : {ev.old_value} → {ev.new_value}"


def _amount(v: str | None) -> str:
    """Formate un notionnel : "5000000.0" → "5,000,000". Renvoie la valeur brute si non numérique."""
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
    """Déplie le new_value d'un nouveau marché ("lev=10;mode=strictIsolated;oi_cap=2000000.0")."""
    parts = dict(p.split("=", 1) for p in v.split(";") if "=" in p) if v else {}
    lev = parts.get("lev", "?")
    mode = parts.get("mode", "?")
    oi = _amount(parts.get("oi_cap"))
    return f"levier {lev}x · {mode} · OI cap {oi}"
