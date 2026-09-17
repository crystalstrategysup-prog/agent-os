"""Evidence gate for truthful completion claims."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

_SHA256 = re.compile(r"[0-9a-f]{64}")


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
    criteria = list(dict.fromkeys(str(item).strip() for item in acceptance if str(item).strip()))
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
            rows.append({"criterion": criterion, "status": "MISSING", "reasons": ["missing_evidence"]})
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
        if max_age_seconds is not None and (checked_at - observed_at).total_seconds() > max_age_seconds:
            reasons.append("evidence_stale")
        rows.append({
            "criterion": criterion,
            "status": "PASS" if not reasons else "BLOCKED",
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "source": str(item.get("source") or ""),
            "subject_sha256": str(item.get("subject_sha256") or ""),
            "reasons": reasons,
        })
    complete = all(row["status"] == "PASS" for row in rows)
    return {
        "schema": "agent-os.result-gate/v1",
        "status": "PASS" if complete else "BLOCKED",
        "can_report_complete": complete,
        "checked_at": checked_at.isoformat().replace("+00:00", "Z"),
        "criteria": rows,
        "ignored_evidence": sorted(set(ignored)),
    }
