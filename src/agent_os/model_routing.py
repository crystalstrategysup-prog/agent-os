"""Deterministic, host-neutral model routing plans."""

from __future__ import annotations


def route_task(
    config: dict[str, object],
    *,
    mode: str,
    complexity: str = "medium",
    role: str = "root",
) -> dict[str, object]:
    routing = config.get("model_routing")
    if not isinstance(routing, dict) or routing.get("enabled") is not True:
        raise ValueError("model_routing_disabled")
    profiles = routing.get("profiles")
    if not isinstance(profiles, dict):
        raise TypeError("model_profiles_missing")
    if role not in {"root", "worker", "verifier"}:
        raise ValueError("model_role_not_allowed")
    if complexity not in {"low", "medium", "high", "critical"}:
        raise ValueError("model_complexity_not_allowed")

    if complexity == "critical":
        if role != "root":
            raise ValueError("critical_model_is_root_only")
        profile_name = "critical"
        reason = "critical_root_escalation"
    elif role == "verifier" or mode in {"review", "verify"}:
        profile_name = "reviewer"
        reason = "independent_review"
    elif role == "root" or complexity == "high":
        profile_name = "coordinator"
        reason = "root_coordination"
    elif mode in {"classification", "extraction", "routing"}:
        profile_name = "fast"
        reason = "bounded_fast_work"
    else:
        profile_name = "worker"
        reason = "bounded_worker"

    profile = profiles.get(profile_name)
    if not isinstance(profile, dict):
        raise TypeError(f"model_profile_missing:{profile_name}")
    model = str(profile.get("model") or "").strip()
    effort = str(profile.get("reasoning_effort") or "").strip()
    if not model or not effort:
        raise ValueError(f"model_profile_incomplete:{profile_name}")
    return {
        "schema": "agent-os.model-route/v1",
        "status": "PLANNED",
        "profile": profile_name,
        "model": model,
        "reasoning_effort": effort,
        "role": role,
        "mode": mode,
        "complexity": complexity,
        "selection_reason": reason,
        "delegate_by_default": bool(routing.get("delegate_by_default", False)),
        "runtime_proof_required": True,
        "note": "A route is a plan, not proof that a model or subagent ran.",
    }
