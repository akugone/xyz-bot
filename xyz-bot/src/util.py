"""Small shared utilities."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation


def none_or_str(v: object) -> str | None:
    """`None` if `v` is `None`, otherwise its `str` representation.

    Centralizes the conversion used by snapshot / events / db (NUMERIC <-> str,
    event values) so the same helper isn't duplicated in each module.
    """
    return None if v is None else str(v)


def format_amount(v: str | None) -> str:
    """Format a notional: "5000000.0" → "5,000,000". Raw value if non-numeric, "?" if None.

    Shared by the Telegram messages and the status page so both render amounts the same way.
    """
    if v is None:
        return "?"
    try:
        d = Decimal(v)
    except (InvalidOperation, ValueError):
        return v
    if d == d.to_integral_value():
        return f"{int(d):,}"
    return f"{d:,}"
