"""Normalize the dex state into a per-coin snapshot.

A snapshot = frozen photo of the structural config at time T.
We deliberately EXCLUDE oraclePx/markPx (noise, updated ~3s): only structural fields
are tracked for the diff.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .util import none_or_str


@dataclass
class CoinState:
    coin: str
    max_leverage: int | None = None
    margin_mode: str | None = None          # strictIsolated | noCross | normal
    margin_table_id: int | None = None
    oi_cap: str | None = None               # notional cap (coinToOiCap), decimal string
    is_listed: bool = True
    is_halted: bool | None = None           # halt mechanism to confirm (see HANDOVER.md)
    funding_mult: str | None = None
    growth_mode: bool | None = None


@dataclass
class Snapshot:
    dex: str
    total_oi_cap: str | None = None
    coins: dict[str, CoinState] = field(default_factory=dict)


def build_snapshot(dex: str, meta: dict[str, Any], limits: dict[str, Any],
                   perp_dex: dict[str, Any] | None = None) -> Snapshot:
    """Build a Snapshot from `meta`, `perpDexLimits`, and (optionally) the `perpDexs` entry
    for this dex (source of the per-asset funding multiplier)."""
    snap = Snapshot(dex=dex, total_oi_cap=none_or_str(limits.get("totalOiCap")))

    oi_caps = {coin: none_or_str(cap) for coin, cap in limits.get("coinToOiCap", [])}
    funding_mults = {
        coin: none_or_str(m)
        for coin, m in (perp_dex or {}).get("assetToFundingMultiplier", [])
    }

    for u in meta.get("universe", []):
        name = u["name"]
        snap.coins[name] = CoinState(
            coin=name,
            max_leverage=u.get("maxLeverage"),
            margin_mode=_margin_mode(u),
            margin_table_id=u.get("marginTableId"),
            oi_cap=oi_caps.get(name),
            is_listed=not u.get("isDelisted", False),
            is_halted=u.get("isHalted"),  # absent while no market is halted; confirm on a real halt
            funding_mult=funding_mults.get(name),
            growth_mode=_growth(u.get("growthMode")),
        )
    return snap


def _margin_mode(u: dict[str, Any]) -> str:
    """Normalized margin mode.

    Finding (real data): `marginMode` is only present for isolated markets
    (`strictIsolated` / `noCross`, with `onlyIsolated: true`). When a market allows cross
    (end of the `strict → noCross → normal` progression), the field DISAPPEARS from the API.
    We normalize it to `"normal"` so the diff correctly catches the move to cross (the event
    of interest), instead of seeing `noCross → None`.
    """
    return u.get("marginMode") or "normal"


def _growth(v: Any) -> bool | None:
    if v is None:
        return None
    return v == "enabled" if isinstance(v, str) else bool(v)
