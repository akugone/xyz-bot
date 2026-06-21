"""Small shared utilities."""
from __future__ import annotations


def none_or_str(v: object) -> str | None:
    """`None` if `v` is `None`, otherwise its `str` representation.

    Centralizes the conversion used by snapshot / events / db (NUMERIC <-> str,
    event values) so the same helper isn't duplicated in each module.
    """
    return None if v is None else str(v)
