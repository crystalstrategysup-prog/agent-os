from __future__ import annotations

from agent_os.result_gate import evaluate_result


def evidence(criterion, **overrides):
    value = {
        "criterion": criterion,
        "status": "PASS",
        "current": True,
        "observed_at": "2026-09-17T23:59:00Z",
        "source": "test",
        "subject_sha256": "a" * 64,
    }
    value.update(overrides)
    return value


def test_current_evidence_passes():
    result = evaluate_result(["tests", "flow"], [evidence("tests"), evidence("flow")], now="2026-09-18T00:00:00Z")
    assert result["can_report_complete"] is True


def test_missing_stale_and_newer_failure_block_complete():
    result = evaluate_result(
        ["missing", "flow"],
        [
            evidence("flow", observed_at="2026-09-17T23:00:00Z"),
            evidence("flow", observed_at="2026-09-17T23:59:00Z", status="FAIL"),
        ],
        now="2026-09-18T00:00:00Z",
        max_age_seconds=300,
    )
    assert result["can_report_complete"] is False
    assert result["criteria"][0]["status"] == "MISSING"
    assert "latest_status_not_pass" in result["criteria"][1]["reasons"]


def test_non_sha_subject_identity_blocks_complete():
    result = evaluate_result(
        ["flow"],
        [evidence("flow", subject_sha256="current")],
        now="2026-09-18T00:00:00Z",
    )
    assert "subject_identity_missing" in result["criteria"][0]["reasons"]
