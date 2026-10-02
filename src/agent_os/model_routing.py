"""Pure model/effort proposals; adapters supply current capabilities and authority.

No discovery, launch, setting change or authentication is performed here.
"""

from __future__ import annotations

import copy
import math
import re
from datetime import datetime

EFFORTS = ("low", "medium", "high", "xhigh", "max")
CODES = dict(zip(EFFORTS, ("L", "M", "H", "E", "max"), strict=True))


def effort(value):
    if not isinstance(value, str):
        raise TypeError("unsupported_reasoning_effort")
    aliases = {v: k for k, v in CODES.items()}
    result = aliases.get(value, value)
    if result not in EFFORTS:
        raise ValueError("unsupported_reasoning_effort")
    return result


def nonempty(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 4000


def observed_time(value):
    try:
        return (
            nonempty(value)
            and datetime.fromisoformat(value).tzinfo is not None
        )
    except ValueError:
        return False


def actual_observation(metadata):
    unknown = {
        "status": "UNKNOWN",
        "model": None,
        "reasoning_effort": None,
        "effort_code": None,
    }
    if not isinstance(metadata, dict) or metadata.get("kind") != "runtime_observation":
        return unknown
    if not all(
        nonempty(metadata.get(k)) for k in ["source", "session_id", "turn_id"]
    ) or not observed_time(metadata.get("observed_at")):
        return unknown
    model = metadata.get("model")
    level = metadata.get("reasoning_effort")
    if model is not None and not nonempty(model):
        raise ValueError("invalid_runtime_metadata")
    if level is not None and not nonempty(level):
        raise ValueError("invalid_runtime_metadata")
    return {
        "status": "OBSERVED" if model is not None or level is not None else "UNKNOWN",
        "model": model,
        "reasoning_effort": level,
        "effort_code": CODES.get(level),
        "source": metadata["source"],
        "observed_at": metadata["observed_at"],
        "session_id": metadata["session_id"],
        "turn_id": metadata["turn_id"],
    }


def catalog_rows(catalog):
    if not isinstance(catalog, dict) or catalog.get("current") is not True:
        return None
    if not nonempty(catalog.get("source")) or not observed_time(
        catalog.get("observed_at")
    ):
        raise ValueError("catalog_provenance_required")
    rows = catalog.get("models")
    if not isinstance(rows, list) or len(rows) > 128:
        raise ValueError("invalid_model_catalog")
    ids = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not nonempty(row.get("id"))
            or not nonempty(row.get("family"))
        ):
            raise ValueError("invalid_model_catalog")
        if row["id"] in ids or type(row.get("available")) is not bool:
            raise ValueError("invalid_model_catalog")
        ids.add(row["id"])
        rank = row.get("release")
        if (
            not isinstance(rank, list)
            or not 1 <= len(rank) <= 6
            or any(type(n) is not int or n < 0 for n in rank)
        ):
            raise ValueError("invalid_release_rank")
        if row["family"] == "sol":
            match = re.fullmatch(
                r"gpt-(\d+(?:\.\d+)*)-sol(?:-\d{4}-\d{2}-\d{2})?", row["id"]
            )
            version = [int(n) for n in match[1].split(".")] if match else None
            if version is None or rank[: len(version)] != version:
                raise ValueError("model_family_version_binding")
        levels = row.get("efforts")
        if (
            not isinstance(levels, list)
            or not levels
            or len(levels) > 5
            or any(x not in EFFORTS for x in levels)
            or len(set(levels)) != len(levels)
        ):
            raise ValueError("invalid_model_efforts")
    return rows


def benefit_valid(value, selected):
    if not isinstance(value, dict) or value.get("verified") is not True:
        return False
    refs = value.get("evidence_refs")
    if (
        not isinstance(refs, list)
        or not refs
        or len(refs) > 64
        or not all(nonempty(r) for r in refs)
    ):
        return False
    if (
        not nonempty(value.get("tradeoff_reason"))
        or value.get("baseline_effort") not in EFFORTS
    ):
        return False
    if EFFORTS.index(value["baseline_effort"]) >= EFFORTS.index(selected):
        return False
    fields = [
        "quality_baseline",
        "quality_candidate",
        "latency_baseline_ms",
        "latency_candidate_ms",
        "cost_baseline",
        "cost_candidate",
    ]
    if any(
        type(value.get(k)) not in {int, float}
        or not math.isfinite(value[k])
        or value[k] < 0
        for k in fields
    ):
        return False
    return value["quality_candidate"] > value["quality_baseline"]


def route_task(
    config,
    *,
    mode,
    complexity="medium",
    role="root",
    catalog=None,
    environment=None,
    requested=None,
    assigned=None,
    actual=None,
    agreement=None,
    escalation_reason=None,
    benefit=None,
    quality_criteria=None,
):
    routing = config.get("model_routing")
    if not isinstance(routing, dict) or routing.get("enabled") is not True:
        raise ValueError("model_routing_disabled")
    if role not in {"root", "worker", "verifier"} or complexity not in {
        "low",
        "medium",
        "high",
        "critical",
    }:
        raise ValueError("model_role_or_complexity_not_allowed")
    if complexity == "critical" and role != "root":
        raise ValueError("critical_model_is_root_only")
    if not nonempty(mode):
        raise ValueError("invalid_task_mode")
    profile = (
        "critical"
        if complexity == "critical"
        else "reviewer"
        if role == "verifier" or mode in {"review", "verify"}
        else "coordinator"
        if role == "root" or complexity == "high"
        else "fast"
        if mode in {"classification", "extraction", "routing"}
        else "worker"
    )
    execution = mode in {
        "implementation",
        "execution",
        "build",
        "classification",
        "extraction",
        "routing",
        "check",
        "read",
        "format",
        "edit",
    }
    basis = (
        "high"
        if complexity in {"high", "critical"}
        else "low"
        if execution and (role == "worker" or complexity == "low")
        else "medium"
    )
    request = {} if requested is None else requested
    env = routing.get("environment") if environment is None else environment
    env = {} if env is None else env
    if (
        not isinstance(request, dict)
        or not isinstance(env, dict)
        or assigned is not None
        and not isinstance(assigned, dict)
    ):
        raise ValueError("invalid_selection_input")
    out = {
        "schema": "agent-os.model-route/v2",
        "status": "BLOCKED",
        "profile": profile,
        "model": None,
        "reasoning_effort": None,
        "effort_code": None,
        "role": role,
        "mode": mode,
        "complexity": complexity,
        "minimum_basis": basis,
        "requested": copy.deepcopy(request),
        "assigned": copy.deepcopy(assigned),
        "actual": actual_observation(actual),
        "environment_constraints": copy.deepcopy(env),
        "delegate_by_default": False,
        "runtime_changed": False,
        "runtime_proof_required": True,
        "note": "Proposal only; catalog, authority and verified benefit are authenticated-adapter responsibilities.",
    }

    def block(reason):
        out["selection_reason"] = reason
        return out

    # Never reinterpret a mandatory active setting as permission to switch it.
    if env.get("fixed_model") is not None or env.get("fixed_effort") is not None:
        out["status"] = "PRESERVE_CONSTRAINT"
        return block("HIGHER_PRIORITY_FIXED_SETTINGS")
    if set(env) - {
        "supported_efforts",
        "allowed_models",
        "minimum_effort",
        "maximum_effort",
        "source",
        "reason",
    }:
        return block("UNINTERPRETED_ENVIRONMENT_CONSTRAINT")
    rows = catalog_rows(routing.get("catalog") if catalog is None else catalog)
    if rows is None:
        return block("CURRENT_CATALOG_REQUIRED")
    out["catalog_provenance"] = {
        k: (routing.get("catalog") if catalog is None else catalog)[k]
        for k in ["source", "observed_at"]
    }
    supported = env.get("supported_efforts")
    if (
        not isinstance(supported, list)
        or not supported
        or len(supported) > 5
        or any(x not in EFFORTS for x in supported)
        or len(set(supported)) != len(supported)
    ):
        return block("ENVIRONMENT_EFFORTS_REQUIRED")
    allowed = env.get("allowed_models")
    if allowed is not None and (
        not isinstance(allowed, list)
        or len(allowed) > 128
        or not all(nonempty(x) for x in allowed)
    ):
        raise ValueError("invalid_allowed_models")
    available = [
        r for r in rows if r["available"] and (allowed is None or r["id"] in allowed)
    ]
    model_id = request.get("model")
    if model_id is None:
        candidates = [r for r in available if r["family"] == "sol"]
        if not candidates:
            return block("NO_AVAILABLE_SOL")
        latest = max(tuple(r["release"]) for r in candidates)
        candidates = [r for r in candidates if tuple(r["release"]) == latest]
        if len(candidates) != 1:
            return block("AMBIGUOUS_LATEST_SOL")
    else:
        candidates = [r for r in available if r["id"] == model_id]
        if not candidates:
            return block("REQUESTED_MODEL_UNAVAILABLE")
    selected = candidates[0]
    if selected["family"] != "sol":
        if (
            not isinstance(agreement, dict)
            or agreement.get("model") != selected["id"]
            or not all(
                nonempty(agreement.get(k))
                for k in ["agreement_ref", "source", "reason"]
            )
        ):
            return block("EXPLICIT_MODEL_AGREEMENT_REQUIRED")
        out["model_agreement"] = copy.deepcopy(agreement)
    lower = effort(env.get("minimum_effort", "low"))
    upper = effort(env.get("maximum_effort", "max"))
    if EFFORTS.index(lower) > EFFORTS.index(upper):
        return block("CONFLICTING_EFFORT_LIMITS")
    eligible = [
        x
        for x in EFFORTS
        if x in selected["efforts"]
        and x in supported
        and EFFORTS.index(lower) <= EFFORTS.index(x) <= EFFORTS.index(upper)
    ]
    desired = (
        effort(request["reasoning_effort"]) if "reasoning_effort" in request else basis
    )
    if "reasoning_effort" in request:
        if EFFORTS.index(desired) < EFFORTS.index(basis):
            return block("BELOW_TASK_MINIMUM")
        if desired not in eligible:
            return block("UNSUPPORTED_OR_CONSTRAINED_EFFORT")
        chosen = desired
    else:
        levels = [x for x in eligible if EFFORTS.index(x) >= EFFORTS.index(desired)]
        if not levels:
            return block("NO_SUFFICIENT_SUPPORTED_EFFORT")
        chosen = levels[0]
    if (
        not isinstance(quality_criteria, list)
        or not quality_criteria
        or len(quality_criteria) > 64
        or not all(nonempty(x) for x in quality_criteria)
    ):
        return block("QUALITY_ACCEPTANCE_REQUIRED")
    if chosen != "low" and not nonempty(escalation_reason):
        return block("ESCALATION_REASON_REQUIRED")
    if chosen in {"xhigh", "max"}:
        if not benefit_valid(benefit, chosen):
            return block("VERIFIED_BENEFIT_TRADEOFF_REQUIRED")
        out["benefit_evidence"] = copy.deepcopy(benefit)
        out["benefit_verification"] = (
            "CALLER_ATTESTED; ADAPTER_MUST_READ_BOUND_EVIDENCE"
        )
    out.update(
        status="PLANNED",
        model=selected["id"],
        reasoning_effort=chosen,
        effort_code=CODES[chosen],
        selection_reason="LATEST_AVAILABLE_SOL"
        if model_id is None
        else "EXPLICIT_MODEL_REQUEST",
        escalation_reason=escalation_reason,
        quality_criteria=copy.deepcopy(quality_criteria),
        supported_intersection=eligible,
    )
    return out
