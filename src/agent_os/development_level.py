"""Scoped development selection carried by existing task/context objects.

This changes planning/check depth only. It is neither readiness nor authority,
and introduces no independent settings store or implicit history lookup.
"""

from __future__ import annotations

from .safeio import GateError


def normalize(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"level", "scope"}:
        raise GateError("development_selection_requires_level_and_scope")
    level = value["level"]
    if isinstance(level, str) and level.casefold() == "1d":
        level = 1
    if type(level) is not int or not 1 <= level <= 5:
        raise GateError("development_level_must_be_1_to_5")
    scope = value["scope"]
    if not isinstance(scope, str) or not scope.strip() or len(scope) > 200:
        raise GateError("development_scope_required")
    return {"level": level, "scope": scope.strip()}


def default() -> dict:
    return {"level": 3, "scope": "task"}


def effective(container: dict, inherited: dict | None = None) -> dict:
    """Use a carried choice before the default; absence never erases inheritance."""
    if "development" in container:
        return normalize(container["development"])
    if inherited is not None and "development" in inherited:
        return normalize(inherited["development"])
    return default()
