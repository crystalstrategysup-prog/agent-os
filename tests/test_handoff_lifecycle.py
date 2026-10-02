"""Terminal transitions require accepted discovery; retirement is not deletion."""

import json
import os
from pathlib import Path

import pytest
import test_foundation
from test_foundation import documents, review, start
from test_indexed_handoff import P, accept

from agent_os import project as p
from agent_os.handoff import Library
from agent_os.handoff_lifecycle import TOPICS
from agent_os.safeio import GateError

setup = test_foundation.setup


def test_new_entry_cannot_disable_terminal_handoff(setup):
    root, home, answers = setup
    answers["handoff_required"] = False
    task = start(setup)
    assert p.load_task(root, task)["handoff_required"] is True
    assert documents(setup, task)["status"] == "READY"
    p.run_check(root, task, "unit")
    result = p.close(root, task, review(setup, task))
    assert result["handoff"]["receipt"]["status"] == "accepted"
    assert p.verify_closeout(root, task)["status"] == "PASS"
    lib = Library(home / "results-library")
    assert (
        lib.resolve("handoff:" + task, P)["manifest"]["entity"]["state"] == "completed"
    )


def test_failed_handoff_keeps_terminal_state_open(setup, monkeypatch):
    root, _, _ = setup
    task = start(setup)
    documents(setup, task)
    p.run_check(root, task, "unit")

    def fail(*args, **kwargs):
        raise GateError("synthetic handoff unavailable")

    monkeypatch.setattr("agent_os.handoff_lifecycle.deliver", fail)
    with pytest.raises(GateError):
        p.close(root, task, review(setup, task))
    assert p.load_task(root, task)["status"] != "CLOSED"
    with pytest.raises(GateError):
        p.checkpoint(root, task, "Pending", "Continue")
    assert p.load_task(root, task)["status"] != "CHECKPOINT"


def test_checkpoint_verified_but_not_complete(setup):
    root, home, _ = setup
    task = start(setup)
    result = p.checkpoint(root, task, "Synthetic unfinished work", "Obtain evidence")
    assert result["complete"] is False
    m = Library(home / "results-library").resolve("handoff:" + task, P)["manifest"]
    assert (
        m["entity"]["state"] == "active" and m["facets"]["result_type"] == "checkpoint"
    )
    assert all(item["status"] == "unknown" for item in m["results"])


def footprint(root):
    # Explicit synthetic measurement, never a discovery/search implementation.
    files = [path for path in root.rglob("*") if path.is_file()]
    return {
        "apparent_bytes": sum(path.stat().st_size for path in files),
        "allocated_bytes": sum(path.stat().st_blocks * 512 for path in files),
        "files": len(files),
    }


def test_measured_retirement_and_explicit_synthetic_fixture_disposal(tmp_path):
    session = tmp_path / "synthetic-session.tmp"
    session.write_bytes(os.urandom(4 * 1024 * 1024))
    before = footprint(tmp_path)
    lib = Library.create(tmp_path / "library", P, topics=TOPICS)
    accept(lib, 1)
    accepted = footprint(tmp_path)
    lib.retract("handoff:1", "Retire this synthetic result", P)
    retired = footprint(tmp_path)
    report = lib.retirement_report(P)
    assert (
        report["reclaimed_bytes"] == 0 and report["physical_cleanup_supported"] is False
    )
    assert session.exists() and retired["apparent_bytes"] >= accepted["apparent_bytes"]
    session_size = session.stat().st_size
    session_allocated = session.stat().st_blocks * 512
    session.unlink()  # Only this test's explicitly-created disposable fixture.
    disposed = footprint(tmp_path)
    assert retired["apparent_bytes"] - disposed["apparent_bytes"] == session_size
    assert retired["allocated_bytes"] - disposed["allocated_bytes"] == session_allocated
    result = {
        "before": before,
        "accepted": accepted,
        "retired": retired,
        "synthetic_fixture_disposed": disposed,
        "explicit_fixture_removed_bytes": session_size,
        "explicit_fixture_removed_allocated_bytes": session_allocated,
        "library_retirement": report,
        "real_session_cleanup": "NOT_RUN",
        "physical_session_cleanup_api": "NOT_IMPLEMENTED",
    }
    evidence = os.environ.get("AGENTOS_HANDOFF_EVIDENCE_DIR")
    if evidence:
        Path(evidence).mkdir(parents=True, exist_ok=True)
        (Path(evidence) / "retirement-footprint.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
