"""Structural evidence admission; no source authentication or semantic acceptance."""
from __future__ import annotations

import hashlib
from pathlib import Path


def primary_issues(observation: dict, *, output_root: Path, role: str = "primary") -> list[str]:
    """Check one canonical terminal observation and its retained artifacts.

    A forged ledger can pass. The caller must verify provenance, command scope,
    required script coverage and the evidence's meaning separately.
    """
    issues = []
    if role != "primary" or observation.get("role", "primary") != "primary":
        issues.append("context_cannot_support_primary_claim")
    if observation.get("schema") != "agentos.observed-command/v1":
        issues.append("unsupported_observation")
    if observation.get("event") != "finished":
        issues.append("terminal_observation_required")
    if (observation.get("status") != "FINISHED" or
            observation.get("command_exit") != 0 or observation.get("wrapper_exit") != 0 or
            observation.get("target_started") is not True):
        issues.append("successful_command_required")
    if (observation.get("input_binding") != "bounded-bytes/v1" or
            observation.get("script_inputs_stable") is not True):
        issues.append("stable_bound_inputs_required")
    if observation.get("output_complete") is not True:
        issues.append("complete_output_required")
    root = Path(output_root).resolve()
    for name in ("stdin", "stdout", "stderr"):
        ref = observation.get(name + "_ref")
        try:
            if not isinstance(ref, str) or not ref or Path(ref).is_absolute():
                raise ValueError()
            path = root / ref
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError()
            # Observer artifacts have fixed bounds; refuse replaced huge files.
            with path.open("rb") as stream:
                data = stream.read(262145)
            if len(data) > 262144 or hashlib.sha256(data).hexdigest() != observation.get(name + "_sha256"):
                raise ValueError()
        except (OSError, ValueError):
            issues.append(name + "_artifact_missing_or_changed")
    return issues


def aggregate_required(statuses: list[str]) -> str:
    """Aggregate declared required criteria, never universal completeness.

    Known unfinished work dominates uncertainty. Empty or unrecognized input
    stays UNKNOWN; only a nonempty all-PASS set returns PASS.
    """
    if any(s in {"FAIL", "INCOMPLETE", "PENDING_ACCEPTANCE", "OPEN"} for s in statuses):
        return "INCOMPLETE"
    if statuses and all(s == "PASS" for s in statuses):
        return "PASS"
    return "UNKNOWN"
