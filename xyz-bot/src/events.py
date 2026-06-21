"""Diff engine: compares two snapshots and produces typed events.

Heart of M2. No dependency on Postgres or Telegram — pure computation over `Snapshot`
objects, so fully testable in memory. Persistence (db) and notification (telegram) consume
the list of `Event` produced here.

Key rules (see CLAUDE.md / SPEC):
  - **Silent seed**: if `prev is None` (first run, no baseline), produce NO event. We just
    record/persist the current snapshot.
  - We ignore prices (oraclePx/markPx): they aren't even in the snapshot.
  - `marginMode` is already normalized (`absent → "normal"`) in the snapshot, so the move to
    cross shows up as `noCross → normal`.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .snapshot import CoinState, Snapshot
from .util import none_or_str

# --- event types (aligned with events.event_type in the DB) ---
NEW_MARKET = "new_market"
OI_CAP_CHANGE = "oi_cap_change"
TOTAL_OI_CAP_CHANGE = "total_oi_cap_change"
MARGIN_MODE_CHANGE = "margin_mode_change"
LEVERAGE_CHANGE = "leverage_change"
GROWTH_MODE_CHANGE = "growth_mode_change"
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
        """Idempotency key: sha256(dex|coin|type|new_value).

        Two identical detections (e.g. seeing the same cap again after a restart) produce the
        same key → `INSERT ... ON CONFLICT DO NOTHING` in the DB, hence a single Telegram ping.
        """
        raw = f"{self.dex}|{self.coin or ''}|{self.event_type}|{self.new_value or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()


def _halted(c: CoinState) -> bool:
    """Halt state normalized to a boolean (is_halted absent/None = not halted)."""
    return bool(c.is_halted)


def diff(prev: Snapshot | None, curr: Snapshot) -> list[Event]:
    """List of changes between `prev` and `curr`. `prev is None` → seed (no event)."""
    if prev is None:
        return []  # silent seed: don't ping the initial baseline

    events: list[Event] = []
    dex = curr.dex

    # --- dex level: global OI cap ---
    if prev.total_oi_cap != curr.total_oi_cap:
        events.append(Event(dex, None, TOTAL_OI_CAP_CHANGE, prev.total_oi_cap, curr.total_oi_cap))

    # --- coin level ---
    for coin, c in curr.coins.items():
        p = prev.coins.get(coin)

        if p is None:
            # Coin present now, absent before → newly listed market.
            new_val = f"lev={c.max_leverage};mode={c.margin_mode};oi_cap={c.oi_cap}"
            events.append(Event(dex, coin, NEW_MARKET, None, new_val))
            continue

        if p.oi_cap != c.oi_cap:
            events.append(Event(dex, coin, OI_CAP_CHANGE, p.oi_cap, c.oi_cap))

        if p.margin_mode != c.margin_mode:
            events.append(Event(dex, coin, MARGIN_MODE_CHANGE, p.margin_mode, c.margin_mode))

        if p.max_leverage != c.max_leverage:
            events.append(Event(dex, coin, LEVERAGE_CHANGE,
                                none_or_str(p.max_leverage), none_or_str(c.max_leverage)))

        # growth mode toggled (only on a real True↔False flip; ignore None/absent edges)
        if p.growth_mode is not None and c.growth_mode is not None \
                and p.growth_mode != c.growth_mode:
            events.append(Event(dex, coin, GROWTH_MODE_CHANGE,
                                _growth_label(p.growth_mode), _growth_label(c.growth_mode)))

        # halt / resume — API mechanism to confirm (see HANDOVER.md).
        # Implemented provisionally by treating is_halted absent/None = not halted.
        if _halted(p) != _halted(c):
            etype = HALT if _halted(c) else UNHALT
            events.append(Event(dex, coin, etype, _halt_label(p), _halt_label(c)))

        # delisting: market that goes listed → delisted (is_listed True → False).
        if p.is_listed and not c.is_listed:
            events.append(Event(dex, coin, DELISTED, "listed", "delisted"))

    return events


def _halt_label(c: CoinState) -> str:
    return "halted" if _halted(c) else "active"


def _growth_label(v: bool) -> str:
    return "enabled" if v else "disabled"
