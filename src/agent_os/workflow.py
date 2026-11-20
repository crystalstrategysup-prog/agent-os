"""Optional, side-effect-free workflow routing from explicitly declared effects.

This is not prompt classification, tool authorization or an OS sandbox. Ordinary
read-only questions do not need to call it. All target mutations require a
separate verified capability at the executor, never an --authorized flag here.
"""

from __future__ import annotations

import argparse

from .safeio import GateError

KINDS = ("question", "search", "audit", "discovery", "project-change")
TARGET_EFFECTS = (
    "external-send", "production-write", "runtime-write", "db-write",
    "credentials", "destructive", "deploy",
)
EFFECTS = ("local-project-write", *TARGET_EFFECTS)


def route(kind: str, effects: list[str] | None = None) -> dict:
    if kind not in KINDS:
        raise GateError("unknown_request_kind")
    effects = [] if effects is None else effects
    if (
        not isinstance(effects, list)
        or any(not isinstance(e, str) or e not in EFFECTS for e in effects)
    ):
        raise GateError("unknown_request_effect")
    selected = sorted(set(effects))
    project_change = kind == "project-change" or "local-project-write" in selected
    target = sorted(set(selected) & set(TARGET_EFFECTS))
    mode = (
        "TARGET_AUTHORITY_REQUIRED" if target
        else "DOCUMENTATION_FIRST" if project_change else "FAST_PATH"
    )
    result = {
        "schema": "agentos.workflow-route/v1",
        "status": "BLOCKED" if target else "PASS",
        "mode": mode,
        "kind": kind,
        "effects": selected,
        "intake_required": project_change,
        "documentation_before_product_writes": project_change,
        "closeout_required": "registered_task_only" if project_change else False,
        "target_gates_required": target,
        "product_writes_authorized": False,
        "external_authority_granted": False,
        "native_hooks": "DISABLED",
        "writes": [],
        "note": "Routing only. Existing read access is still required; target effects need separate scoped authority.",
    }
    if project_change:
        from .engineering_guidance import load

        result["foundation_guidance"] = load()
    return result


def command(argv: list[str]) -> tuple[dict, int]:
    from .engineering_guidance import DEFAULT_METHOD, METHODS, load

    p = argparse.ArgumentParser(prog="agentos workflow")
    p.add_argument("action", choices=["route", "guidance"])
    p.add_argument("--kind", choices=KINDS)
    p.add_argument("--effect", choices=EFFECTS, action="append", default=[])
    p.add_argument("--method", choices=METHODS)
    a = p.parse_args(argv)
    if a.action == "guidance":
        if a.kind is not None or a.effect:
            raise GateError("engineering_guidance_does_not_accept_route_arguments")
        return load(a.method or DEFAULT_METHOD), 0
    if a.method is not None:
        p.error("--method is only valid for guidance")
    if a.kind is None:
        p.error("route requires --kind")
    result = route(a.kind, a.effect)
    return result, 2 if result["status"] == "BLOCKED" else 0
