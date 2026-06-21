"""Moteur de diff : compare deux snapshots et produit des events typés.

Cœur de M2. Aucune dépendance à Postgres ni à Telegram — pur calcul sur des
`Snapshot`, donc entièrement testable en mémoire. La persistance (M2 bis) et la
notification (M3) consommeront la liste d'`Event` produite ici.

Règles clés (cf. CLAUDE.md / SPEC) :
  - **Seed silencieux** : si `prev is None` (1er run, pas de baseline), on ne
    génère AUCUN event. On se contente de mémoriser/persister le snapshot courant.
  - On ignore les prix (oraclePx/markPx) : ils ne sont même pas dans le snapshot.
  - Le `marginMode` est déjà normalisé (`absent → "normal"`) côté snapshot, donc
    le passage en cross apparaît comme `noCross → normal`.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .snapshot import CoinState, Snapshot

# --- types d'events (alignés sur events.event_type en base) ---
NEW_MARKET = "new_market"
OI_CAP_CHANGE = "oi_cap_change"
TOTAL_OI_CAP_CHANGE = "total_oi_cap_change"
MARGIN_MODE_CHANGE = "margin_mode_change"
LEVERAGE_CHANGE = "leverage_change"
HALT = "halt"
UNHALT = "unhalt"
DELISTED = "delisted"


@dataclass(frozen=True)
class Event:
    dex: str
    coin: str | None
    event_type: str
    old_value: str | None
    new_value: str | None

    @property
    def dedup_key(self) -> str:
        """Clé d'idempotence anti-doublon : sha256(dex|coin|type|new_value).

        Deux détections identiques (ex. on revoit le même cap après redémarrage)
        produisent la même clé → `INSERT ... ON CONFLICT DO NOTHING` en base, donc
        un seul ping Telegram.
        """
        raw = f"{self.dex}|{self.coin or ''}|{self.event_type}|{self.new_value or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()


def _halted(c: CoinState) -> bool:
    """État de halt normalisé en booléen (is_halted absent/None = non halté)."""
    return bool(c.is_halted)


def diff(prev: Snapshot | None, curr: Snapshot) -> list[Event]:
    """Liste des changements entre `prev` et `curr`. `prev is None` → seed (aucun event)."""
    if prev is None:
        return []  # seed silencieux : on ne pinge pas la baseline initiale

    events: list[Event] = []
    dex = curr.dex

    # --- niveau dex : plafond d'OI global ---
    if prev.total_oi_cap != curr.total_oi_cap:
        events.append(Event(dex, None, TOTAL_OI_CAP_CHANGE, prev.total_oi_cap, curr.total_oi_cap))

    # --- niveau coin ---
    for coin, c in curr.coins.items():
        p = prev.coins.get(coin)

        if p is None:
            # Coin présent maintenant, absent avant → nouveau marché listé.
            new_val = f"lev={c.max_leverage};mode={c.margin_mode};oi_cap={c.oi_cap}"
            events.append(Event(dex, coin, NEW_MARKET, None, new_val))
            continue

        if p.oi_cap != c.oi_cap:
            events.append(Event(dex, coin, OI_CAP_CHANGE, p.oi_cap, c.oi_cap))

        if p.margin_mode != c.margin_mode:
            events.append(Event(dex, coin, MARGIN_MODE_CHANGE, p.margin_mode, c.margin_mode))

        if p.max_leverage != c.max_leverage:
            events.append(Event(dex, coin, LEVERAGE_CHANGE,
                                _s(p.max_leverage), _s(c.max_leverage)))

        # halt / reprise — mécanisme API à confirmer avec fb (cf. DEBRIEF-FB.md).
        # Implémenté de façon provisoire en traitant is_halted absent/None = non halté.
        if _halted(p) != _halted(c):
            etype = HALT if _halted(c) else UNHALT
            events.append(Event(dex, coin, etype, _halt_label(p), _halt_label(c)))

        # delisting : marché qui passe listé → delisté (is_listed True → False).
        if p.is_listed and not c.is_listed:
            events.append(Event(dex, coin, DELISTED, "listed", "delisted"))

    return events


def _s(v: object) -> str | None:
    return None if v is None else str(v)


def _halt_label(c: CoinState) -> str:
    return "halted" if _halted(c) else "active"
