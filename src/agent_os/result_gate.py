"""Evidence gate for truthful completion claims."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

_SHA256 = re.compile(r"[0-9a-f]{64}")


def verify_completion_execution(receipt, identity, operation, store):
    """Read captured evidence bytes; shape/hash is not provider authentication."""
    from .handoff_store import require, sha

    dependencies = (
        "source_commit",
        "contract_hash",
        "build_hash",
        "configuration_hash",
        "environment_fingerprint",
    )
    require(
        isinstance(receipt, dict)
        and set(receipt)
        == {
            "schema",
            "operation_id",
            "nonce",
            "generation",
            "ownership_epoch",
            "criterion_id",
            "run_id",
            "status",
            "exit_code",
            "recipe_id",
            "runtime",
            "workspace",
            "started_at",
            "finished_at",
            "tokens",
            "cost_units",
            "evidence_refs",
            *dependencies,
        }
        and receipt["schema"] == "agentos.completion-execution/v1",
        "INVALID_EXECUTION_RECEIPT",
    )
    require(
        all(
            receipt[k] == identity[k]
            for k in (
                "operation_id",
                "nonce",
                "generation",
                "ownership_epoch",
                *dependencies,
            )
        ),
        "EXECUTION_PROVENANCE_MISMATCH",
    )
    require(
        receipt["criterion_id"] == operation["criterion_id"]
        and receipt["recipe_id"] == operation["recipe_id"],
        "EXECUTION_RECIPE_MISMATCH",
    )
    require(
        receipt["status"] in {"PASS", "FAIL", "BLOCKED"}
        and type(receipt["exit_code"]) is int
        and (receipt["status"] != "PASS" or receipt["exit_code"] == 0),
        "UNEXECUTED_PASS",
    )
    require(
        all(
            type(receipt[k]) is int and receipt[k] >= 0
            for k in ("started_at", "finished_at", "tokens", "cost_units")
        )
        and receipt["started_at"] <= receipt["finished_at"],
        "INVALID_EXECUTION_TIME",
    )
    require(
        all(
            isinstance(receipt[k], str) and receipt[k].strip()
            for k in ("run_id", "runtime", "workspace")
        ),
        "ACTUAL_RUNTIME_REQUIRED",
    )
    refs = receipt["evidence_refs"]
    require(
        isinstance(refs, list) and 0 < len(refs) <= 64, "EXECUTION_EVIDENCE_REQUIRED"
    )
    ids = []
    for ref in refs:
        data = store.get(ref)
        ids.append(sha(data))
    require(len(ids) == len(set(ids)), "DUPLICATE_EXECUTION_EVIDENCE")
    return {
        "status": "CAPTURED_BYTES_VERIFIED",
        "evidence_hashes": ids,
        "provider_authentication": "SELECTED_ADAPTER_BOUNDARY",
    }


def evaluate_completion_release(
    snapshot,
    store,
    current_dependencies,
    checked_at,
    verify_authorization,
    verify_publication=None,
):
    """Bounded pre/postpublish decisions; performs no publication or deployment.

    Provenance readers and authority/publication verifiers belong to the selecting
    authenticated adapter. A synthetic evaluator PASS is not actual authority.
    """
    from .completion import DEPENDENCIES, clock, hash_value
    from .handoff_store import require

    clock(checked_at)
    require(
        isinstance(snapshot, dict)
        and set(snapshot)
        == {
            "schema",
            "phase",
            "candidate",
            "checks",
            "authorization_ref",
            "publication_ref",
        }
        and snapshot["schema"] == "agentos.completion-release/v1",
        "INVALID_RELEASE_SNAPSHOT",
    )
    require(snapshot["phase"] in {"PREPUBLISH", "POSTPUBLISH"}, "INVALID_RELEASE_PHASE")
    candidate = snapshot["candidate"]
    require(
        isinstance(candidate, dict)
        and set(candidate) == {"version", "target", "artifact_ref", *DEPENDENCIES},
        "INVALID_RELEASE_CANDIDATE",
    )
    import re

    for key in ("target", "version", "environment_fingerprint"):
        value = candidate[key]
        require(
            isinstance(value, str)
            and 0 < len(value.strip()) <= 512
            and value.strip().upper() not in {"UNKNOWN", "NOT_SET", "N/A"},
            "RELEASE_TARGET_OR_CONTEXT_UNKNOWN",
        )
    require(
        isinstance(candidate["source_commit"], str)
        and re.fullmatch("[0-9a-f]{40,64}", candidate["source_commit"]),
        "INVALID_RELEASE_SOURCE",
    )
    for key in ("contract_hash", "build_hash", "configuration_hash"):
        hash_value(candidate[key])
    require(
        {k: candidate[k] for k in DEPENDENCIES} == current_dependencies,
        "RELEASE_SOURCE_CHANGED",
    )
    from .handoff_store import sha

    require(
        sha(store.get(candidate["artifact_ref"])) == candidate["build_hash"],
        "RELEASE_BUILD_MISMATCH",
    )
    checks = snapshot["checks"]
    required = {"G0", "G1", "G2", "G3", "G4", "T22", "T27", "T32"}
    require(
        isinstance(checks, dict) and set(checks) == required,
        "RELEASE_CHECKS_INCOMPLETE",
    )
    blockers = []
    for key, ref in checks.items():
        receipt = store.json(ref)
        require(
            set(receipt)
            == {
                "schema",
                "check_id",
                "status",
                "checked_at",
                "evidence_refs",
                *DEPENDENCIES,
            }
            and receipt["schema"] == "agentos.completion-stage-receipt/v1"
            and receipt["check_id"] == key,
            "INVALID_STAGE_RECEIPT",
        )
        if receipt["status"] != "PASS":
            blockers.append(key)
        require(
            {k: receipt[k] for k in DEPENDENCIES} == current_dependencies,
            "STALE_STAGE_RECEIPT",
        )
        require(
            clock(receipt["checked_at"]) <= checked_at and receipt["evidence_refs"],
            "STAGE_EVIDENCE_REQUIRED",
        )
        for evidence in receipt["evidence_refs"]:
            store.get(evidence)
    if blockers:
        return {
            "status": "BLOCKED",
            "blockers": blockers,
            "can_publish": False,
            "actual_publication_proven": False,
        }
    if snapshot["authorization_ref"] is None or not callable(verify_authorization):
        return {
            "status": "BLOCKED_AUTHORIZATION",
            "can_publish": False,
            "actual_publication_proven": False,
        }
    authority = store.json(snapshot["authorization_ref"])
    require(
        verify_authorization(authority, candidate) is True,
        "RELEASE_AUTHORIZATION_UNVERIFIED",
    )
    require(
        set(authority)
        == {
            "schema",
            "target",
            "version",
            "build_hash",
            "expires_at",
            "revoked",
            "evidence_refs",
        }
        and authority["schema"] == "agentos.completion-release-authority/v1"
        and all(
            authority[k] == candidate[k] for k in ("target", "version", "build_hash")
        )
        and authority["revoked"] is False
        and clock(authority["expires_at"]) > checked_at
        and authority["evidence_refs"],
        "RELEASE_AUTHORIZATION_SCOPE_MISMATCH",
    )
    for ref in authority["evidence_refs"]:
        store.get(ref)
    if snapshot["phase"] == "PREPUBLISH":
        return {
            "status": "READY_TO_PUBLISH",
            "can_publish": True,
            "actual_publication_proven": False,
        }
    require(
        snapshot["publication_ref"] is not None and callable(verify_publication),
        "POSTPUBLISH_RECEIPT_REQUIRED",
    )
    published = store.json(snapshot["publication_ref"])
    require(
        verify_publication(published, candidate) is True,
        "ACTUAL_PUBLICATION_UNVERIFIED",
    )
    require(
        set(published)
        == {
            "schema",
            "target",
            "version",
            "build_hash",
            "retrieved_artifact_ref",
            "install_receipt_ref",
            "checked_at",
        }
        and published["schema"] == "agentos.completion-publication/v1"
        and all(
            published[k] == candidate[k] for k in ("target", "version", "build_hash")
        )
        and clock(published["checked_at"]) <= checked_at,
        "PUBLICATION_PROVENANCE_MISMATCH",
    )
    require(
        sha(store.get(published["retrieved_artifact_ref"])) == candidate["build_hash"],
        "PUBLISHED_BYTES_MISMATCH",
    )
    install = store.json(published["install_receipt_ref"])
    require(
        install.get("status") == "PASS"
        and install.get("version") == candidate["version"]
        and install.get("build_hash") == candidate["build_hash"]
        and install.get("evidence_refs"),
        "PUBLISHED_INSTALL_RECEIPT_REQUIRED",
    )
    for ref in install["evidence_refs"]:
        store.get(ref)
    return {
        "status": "PUBLISHED_VERIFIED",
        "can_publish": False,
        "actual_publication_proven": True,
    }


def _timestamp(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("evidence observed_at is required")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("evidence observed_at must include a timezone")
    return parsed.astimezone(UTC)


def evaluate_result(
    acceptance: Iterable[str],
    evidence: Iterable[dict[str, Any]],
    *,
    now: str,
    max_age_seconds: int | None = None,
) -> dict[str, Any]:
    criteria = list(
        dict.fromkeys(str(item).strip() for item in acceptance if str(item).strip())
    )
    if not criteria:
        raise ValueError("at least one acceptance criterion is required")
    if max_age_seconds is not None and max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")
    checked_at = _timestamp(now)
    latest: dict[str, tuple[datetime, dict[str, Any]]] = {}
    ignored: list[str] = []
    for raw in evidence:
        item = dict(raw)
        criterion = str(item.get("criterion") or "").strip()
        if criterion not in criteria:
            ignored.append(criterion or "<missing>")
            continue
        observed_at = _timestamp(item.get("observed_at"))
        if criterion not in latest or observed_at >= latest[criterion][0]:
            latest[criterion] = (observed_at, item)

    rows: list[dict[str, Any]] = []
    for criterion in criteria:
        selected = latest.get(criterion)
        reasons: list[str] = []
        if selected is None:
            rows.append(
                {
                    "criterion": criterion,
                    "status": "MISSING",
                    "reasons": ["missing_evidence"],
                }
            )
            continue
        observed_at, item = selected
        if observed_at > checked_at:
            reasons.append("future_dated_evidence")
        if item.get("current") is not True:
            reasons.append("not_bound_to_current_state")
        if str(item.get("status") or "").upper() != "PASS":
            reasons.append("latest_status_not_pass")
        if not str(item.get("source") or "").strip():
            reasons.append("source_missing")
        if not _SHA256.fullmatch(str(item.get("subject_sha256") or "").strip().lower()):
            reasons.append("subject_identity_missing")
        if (
            max_age_seconds is not None
            and (checked_at - observed_at).total_seconds() > max_age_seconds
        ):
            reasons.append("evidence_stale")
        rows.append(
            {
                "criterion": criterion,
                "status": "PASS" if not reasons else "BLOCKED",
                "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
                "source": str(item.get("source") or ""),
                "subject_sha256": str(item.get("subject_sha256") or ""),
                "reasons": reasons,
            }
        )
    complete = all(row["status"] == "PASS" for row in rows)
    return {
        "schema": "agent-os.result-gate/v1",
        "status": "PASS" if complete else "BLOCKED",
        "can_report_complete": complete,
        "checked_at": checked_at.isoformat().replace("+00:00", "Z"),
        "criteria": rows,
        "ignored_evidence": sorted(set(ignored)),
    }
