"""Petits utilitaires partagés."""
from __future__ import annotations


def none_or_str(v: object) -> str | None:
    """`None` si `v` est `None`, sinon sa représentation `str`.

    Centralise la conversion utilisée par snapshot / events / db (NUMERIC ↔ str,
    valeurs d'event), pour éviter de dupliquer le même helper dans chaque module.
    """
    return None if v is None else str(v)
