"""Synthetic capability/authority claims test a pure proposal, never launch models."""

from __future__ import annotations

import copy

import pytest

from agent_os.config import AgentOSPaths, default_config, load_config
from agent_os.model_routing import EFFORTS, effort, route_task


def row(model, family, release, available=True, efforts=None):
    return {
        "id": model,
        "family": family,
        "release": release,
        "available": available,
        "efforts": list(EFFORTS) if efforts is None else efforts,
    }


@pytest.fixture
def inputs():
    return {
        "catalog": {
            "current": True,
            "source": "synthetic selected-client catalog",
            "observed_at": "2026-10-02T00:00:00Z",
            "models": [
                row("gpt-6-sol", "sol", [6, 0]),
                row("gpt-6.1-sol", "sol", [6, 1]),
                row("gpt-6-luna", "luna", [6]),
                row("gpt-6-astra", "astra", [6]),
            ],
        },
        "environment": {
            "supported_efforts": list(EFFORTS),
            "source": "synthetic host capabilities",
        },
        "quality_criteria": [
            "Registered scoped checks pass; current source/result evidence is read back."
        ],
        "escalation_reason": "This work needs explicit goal/dependency judgement; verify scope and owned remainder.",
    }


def plan(inputs, **kwargs):
    arguments = {**inputs, **kwargs}
    return route_task(
        default_config(),
        mode=arguments.pop("mode", "implementation"),
        role=arguments.pop("role", "worker"),
        complexity=arguments.pop("complexity", "medium"),
        **arguments,
    )


def benefit(baseline="high"):
    return {
        "verified": True,
        "evidence_refs": ["evidence:synthetic-comparison"],
        "baseline_effort": baseline,
        "quality_baseline": 0.7,
        "quality_candidate": 0.9,
        "latency_baseline_ms": 100,
        "latency_candidate_ms": 250,
        "cost_baseline": 1,
        "cost_candidate": 2,
        "tradeoff_reason": "Measured criterion failures reduced; owner accepts this explicit delay/cost tradeoff.",
    }


@pytest.mark.parametrize(
    ("mode", "complexity", "role", "profile", "level"),
    [
        ("implementation", "medium", "root", "coordinator", "medium"),
        ("implementation", "medium", "worker", "worker", "low"),
        ("classification", "low", "worker", "fast", "low"),
        ("review", "medium", "verifier", "reviewer", "medium"),
        ("anything", "high", "worker", "coordinator", "high"),
        ("anything", "critical", "root", "critical", "high"),
    ],
)
def test_model_route_matrix(inputs, mode, complexity, role, profile, level):
    value = plan(inputs, mode=mode, complexity=complexity, role=role)
    assert (
        value["status"] == "PLANNED"
        and value["profile"] == profile
        and value["reasoning_effort"] == level
    )
    assert (
        value["model"] == "gpt-6.1-sol"
        and value["runtime_proof_required"]
        and not value["delegate_by_default"]
        and not value["runtime_changed"]
    )


def test_critical_profile_is_root_only(inputs):
    with pytest.raises(ValueError, match="root_only"):
        plan(inputs, mode="analysis", complexity="critical")


def test_current_catalog_latest_and_unavailable_are_not_hardcoded(inputs):
    inputs["catalog"]["models"] += [
        row("gpt-7.2-sol", "sol", [7, 2]),
        row("gpt-8-sol", "sol", [8], False),
    ]
    assert plan(inputs)["model"] == "gpt-7.2-sol"
    inputs["environment"]["allowed_models"] = ["gpt-6-sol"]
    assert plan(inputs)["model"] == "gpt-6-sol"


@pytest.mark.parametrize("missing", ["catalog", "environment"])
def test_unknown_capabilities_do_not_guess(inputs, missing):
    inputs[missing] = None
    result = plan(inputs)
    assert (
        result["status"] == "BLOCKED"
        and result["model"] is None
        and result["actual"]["status"] == "UNKNOWN"
    )


@pytest.mark.parametrize("bad", ["none", "minimal", "ultra", "extreme", True, []])
def test_unsupported_effort_refuses(inputs, bad):
    with pytest.raises((ValueError, TypeError), match="unsupported_reasoning_effort"):
        plan(inputs, requested={"reasoning_effort": bad})


@pytest.mark.parametrize(
    ("code", "full"),
    [("L", "low"), ("M", "medium"), ("H", "high"), ("E", "xhigh"), ("max", "max")],
)
def test_codes_and_max_are_distinct(inputs, code, full):
    result = plan(
        inputs,
        requested={"reasoning_effort": code},
        benefit=benefit("xhigh" if full == "max" else "high"),
    )
    assert (
        effort(code) == full
        and result["reasoning_effort"] == full
        and result["effort_code"] == code
    )


def test_minimum_supported_intersection_and_no_silent_downgrade(inputs):
    inputs["catalog"]["models"][1]["efforts"] = ["medium", "high"]
    assert plan(inputs)["reasoning_effort"] == "medium"
    assert plan(inputs, requested={"reasoning_effort": "low"})["status"] == "BLOCKED"
    inputs["environment"]["supported_efforts"] = ["low"]
    assert (
        plan(inputs, mode="planning")["selection_reason"]
        == "NO_SUFFICIENT_SUPPORTED_EFFORT"
    )


@pytest.mark.parametrize("family", ["luna", "astra"])
def test_no_automatic_family_switch_or_saved_profile_authority(inputs, family):
    inputs["catalog"]["models"] = [
        r for r in inputs["catalog"]["models"] if r["family"] == family
    ]
    assert plan(inputs)["selection_reason"] == "NO_AVAILABLE_SOL"
    model = inputs["catalog"]["models"][0]["id"]
    assert (
        plan(inputs, requested={"model": model})["selection_reason"]
        == "EXPLICIT_MODEL_AGREEMENT_REQUIRED"
    )
    agreement = {
        "model": model,
        "agreement_ref": "agreement:synthetic-scoped",
        "source": "synthetic authorized caller",
        "reason": "Explicit individual exception for this exact model.",
    }
    assert (
        plan(inputs, requested={"model": model}, agreement=agreement)["model"] == model
    )
    agreement["model"] = "gpt-5.6-sol"
    assert (
        plan(inputs, requested={"model": model}, agreement=agreement)["status"]
        == "BLOCKED"
    )


def test_escalation_reason_and_measurable_acceptance_required(inputs):
    assert (
        plan(inputs, role="root", escalation_reason=None)["selection_reason"]
        == "ESCALATION_REASON_REQUIRED"
    )
    assert (
        plan(inputs, quality_criteria=[])["selection_reason"]
        == "QUALITY_ACCEPTANCE_REQUIRED"
    )
    assert (
        plan(inputs, role="root", requested={"reasoning_effort": "L"})[
            "selection_reason"
        ]
        == "BELOW_TASK_MINIMUM"
    )
    assert (
        plan(
            inputs, role="root", complexity="low", mode="read", escalation_reason=None
        )["reasoning_effort"]
        == "low"
    )
    assert plan(inputs, mode="planning")["reasoning_effort"] == "medium"


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "unverified",
        "no-gain",
        "no-cost",
        "nonfinite",
        "no-ref",
        "no-tradeoff",
        "same-baseline",
    ],
)
def test_xhigh_requires_referenced_benefit_and_latency_cost(inputs, damage):
    value = benefit()
    if damage == "missing":
        value = None
    elif damage == "unverified":
        value["verified"] = False
    elif damage == "no-gain":
        value["quality_candidate"] = value["quality_baseline"]
    elif damage == "no-cost":
        value.pop("cost_candidate")
    elif damage == "nonfinite":
        value["latency_candidate_ms"] = float("inf")
    elif damage == "no-ref":
        value["evidence_refs"] = []
    elif damage == "no-tradeoff":
        value["tradeoff_reason"] = ""
    else:
        value["baseline_effort"] = "xhigh"
    result = plan(inputs, requested={"reasoning_effort": "E"}, benefit=value)
    assert (
        result["selection_reason"] == "VERIFIED_BENEFIT_TRADEOFF_REQUIRED"
        and result["model"] is None
    )


@pytest.mark.parametrize(
    "setting",
    [
        {"fixed_model": "gpt-6-astra"},
        {"fixed_effort": "xhigh"},
        {"fixed_effort": "ultra"},
    ],
)
def test_higher_priority_fixed_settings_preserved_without_runtime_guess(
    inputs, setting
):
    inputs["environment"].update(setting)
    result = plan(inputs, requested={"model": "gpt-6.1-sol", "reasoning_effort": "low"})
    assert (
        result["status"] == "PRESERVE_CONSTRAINT"
        and result["model"] is None
        and not result["runtime_changed"]
    )
    assert (
        result["environment_constraints"] == inputs["environment"]
        and result["actual"]["model"] is None
    )


def test_mandatory_bounds_and_unknown_rules_never_ignored(inputs):
    inputs["environment"].update(minimum_effort="high", maximum_effort="high")
    assert plan(inputs)["reasoning_effort"] == "high"
    assert plan(inputs, requested={"reasoning_effort": "low"})["status"] == "BLOCKED"
    inputs["environment"]["maximum_effort"] = "low"
    assert plan(inputs)["selection_reason"] == "CONFLICTING_EFFORT_LIMITS"
    inputs["environment"]["mandatory_extra_rule"] = "Do not launch this operation."
    assert plan(inputs)["selection_reason"] == "UNINTERPRETED_ENVIRONMENT_CONSTRAINT"


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {},
        {"kind": "assignment", "model": "gpt-6.1-sol", "reasoning_effort": "max"},
        {
            "kind": "runtime_observation",
            "model": "gpt-6.1-sol",
            "source": "fixture",
            "observed_at": "2026-10-02T00:00:00Z",
        },
    ],
)
def test_unknown_actual_not_inferred_from_requested_assigned_or_unbound_metadata(
    inputs, metadata
):
    assigned = {"model": "gpt-6-astra", "reasoning_effort": "max"}
    result = plan(
        inputs, requested={"model": "gpt-6.1-sol"}, assigned=assigned, actual=metadata
    )
    assert (
        result["actual"]["status"] == "UNKNOWN"
        and result["actual"]["model"] is None
        and result["assigned"] == assigned
    )


def test_bound_runtime_observation_independent_and_inputs_immutable(inputs):
    actual = {
        "kind": "runtime_observation",
        "model": "gpt-6-sol",
        "reasoning_effort": "max",
        "source": "synthetic provider metadata",
        "observed_at": "2026-10-02T00:00:00Z",
        "session_id": "session:fixture",
        "turn_id": "turn:fixture",
    }
    original = copy.deepcopy(inputs)
    actualcopy = copy.deepcopy(actual)
    result = plan(inputs, actual=actual)
    assert (
        result["model"] == "gpt-6.1-sol"
        and result["actual"]["model"] == "gpt-6-sol"
        and result["actual"]["effort_code"] == "max"
    )
    assert result["assigned"] is None and inputs == original and actual == actualcopy
    result["environment_constraints"]["supported_efforts"].clear()
    assert inputs == original


def test_ambiguous_or_spoofed_sol_catalog_refuses(inputs):
    inputs["catalog"]["models"].append(row("gpt-6.1-sol-2026-10-02", "sol", [6, 1]))
    assert plan(inputs)["selection_reason"] == "AMBIGUOUS_LATEST_SOL"
    inputs["catalog"]["models"][-1].update(id="gpt-9-astra", release=[6, 1])
    with pytest.raises(ValueError, match="model_family_version_binding"):
        plan(inputs)


def test_upgrade_preserves_legacy_values_without_using_as_agreement(inputs, tmp_path):
    import json

    paths = AgentOSPaths.discover(tmp_path / "user")
    paths.initialize()
    original = {
        "schema": "agent-os.community-config/v3",
        "model_routing": {
            "profiles": {
                "worker": {"model": "gpt-5.6-terra", "reasoning_effort": "high"}
            }
        },
    }
    paths.config.write_text(json.dumps(original))
    before = paths.config.read_bytes()
    config = load_config(paths)
    assert (
        config["model_routing"]["profiles"]["worker"]["model"] == "gpt-5.6-terra"
        and paths.config.read_bytes() == before
    )
    result = route_task(config, mode="implementation", role="worker", **inputs)
    assert result["model"] == "gpt-6.1-sol" and result["reasoning_effort"] == "low"
