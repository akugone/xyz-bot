"""Normalisation de l'état du dex en un snapshot par coin.

Un snapshot = photo figée de la config structurelle à un instant T.
On EXCLUT volontairement oraclePx/markPx (bruit, maj ~3 s) : seuls les champs
structurels sont suivis pour le diff.
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
    oi_cap: str | None = None               # notional cap (coinToOiCap), string décimal
    is_listed: bool = True
    is_halted: bool | None = None           # mécanisme halt à confirmer avec fb (cf. DEBRIEF-FB.md)
    funding_mult: str | None = None
    growth_mode: bool | None = None


@dataclass
class Snapshot:
    dex: str
    total_oi_cap: str | None = None
    coins: dict[str, CoinState] = field(default_factory=dict)


def build_snapshot(dex: str, meta: dict[str, Any], limits: dict[str, Any]) -> Snapshot:
    """Construit un Snapshot à partir des réponses `meta` et `perpDexLimits`."""
    snap = Snapshot(dex=dex, total_oi_cap=none_or_str(limits.get("totalOiCap")))

    oi_caps = {coin: none_or_str(cap) for coin, cap in limits.get("coinToOiCap", [])}

    for u in meta.get("universe", []):
        name = u["name"]
        snap.coins[name] = CoinState(
            coin=name,
            max_leverage=u.get("maxLeverage"),
            margin_mode=_margin_mode(u),
            margin_table_id=u.get("marginTableId"),
            oi_cap=oi_caps.get(name),
            is_listed=not u.get("isDelisted", False),
            is_halted=u.get("isHalted"),  # M1: absent tant qu'aucun marché halté ; à confirmer sur un vrai halt
            growth_mode=_growth(u.get("growthMode")),
            # funding_mult : pas dans `meta` (cf. perpDexs.assetToFundingMultiplier) — à brancher en M2
        )
    return snap


def _margin_mode(u: dict[str, Any]) -> str:
    """Mode de marge normalisé.

    Constat M1 (données réelles) : `marginMode` n'est présent que pour les marchés
    isolés (`strictIsolated` / `noCross`, avec `onlyIsolated: true`). Quand un marché
    autorise le cross (fin de la progression `strict → noCross → normal`), le champ
    DISPARAÎT de l'API. On le normalise donc en `"normal"` pour que le diff capte bien
    le passage en cross (l'event que fb veut surveiller), au lieu de voir `noCross → None`.
    """
    return u.get("marginMode") or "normal"


def _growth(v: Any) -> bool | None:
    if v is None:
        return None
    return v == "enabled" if isinstance(v, str) else bool(v)
