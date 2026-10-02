"""Behavioral stage/parent boundary regressions; all sources and actors synthetic."""
from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_foundation import documents, review, start
from test_foundation import setup as foundation_setup

from agent_os import continuation as c
from agent_os import foundation_cli, hooks, workflow
from agent_os import project as p
from agent_os.safeio import GateError, filemap

setup = foundation_setup


def contract():
    return {"schema": c.SCHEMA, "parent_owner": "parent", "stage_owner": "author",
            "next_owner": "independent-reviewer", "next_action": {"kind": "review", "summary": "Review frozen final source; then choose next safe stage."},
            "project_complete": False}


def closed(setup, required=True):
    root, _, answers = setup
    answers["continuation_required"] = required
    task = start(setup)
    assert documents(setup, task)["status"] == "READY"
    assert p.run_check(root, task, "unit")["status"] == "PASS"
    packet = review(setup, task)
    packet["continuation"] = contract()
    assert p.close(root, task, packet)["status"] == "CLOSED"
    return task


def queued(setup):
    task = closed(setup)
    return c.reconcile(setup[1], setup[0], task)


def move(home, item, action, receipt=None, actor="parent"):
    return c.transition(home, item["id"], actor, item["revision"], action, receipt)


def accepted(item):
    started = datetime.fromisoformat(item["delivery_started_at"])
    user_at = started + timedelta(microseconds=1)
    later_at = started + timedelta(microseconds=2)
    return {"schema": c.RECEIPT_SCHEMA, "attempt_id": item["attempt_id"],
            "delivery_generation": item["delivery_generation"], "delivery_nonce": item["delivery_nonce"],
            "target_owner": "independent-reviewer", "provider": "synthetic-parent-adapter",
            "checked_at": max(datetime.now(UTC), later_at).isoformat(), "status": "ACCEPTED",
            "user_event_id": "accepted-user-event", "later_activity_id": "review-started-event",
            "user_event_at": user_at.isoformat(), "later_activity_at": later_at.isoformat()}


def rejected(item, rejection_id="exact-rejected-call"):
    return {"schema": c.RECEIPT_SCHEMA, "attempt_id": item["attempt_id"],
            "delivery_generation": item["delivery_generation"], "delivery_nonce": item["delivery_nonce"],
            "target_owner": "independent-reviewer", "provider": "synthetic-parent-adapter",
            "checked_at": datetime.now(UTC).isoformat(), "status": "CONFIRMED_NOT_SENT",
            "rejection_id": rejection_id}


def test_completed_stage_preserves_unfinished_project_owner_and_review(setup):
    item = queued(setup)
    task = p.load_task(setup[0], item["identity"]["task_id"])
    assert task["status"] == "CLOSED"
    assert task["closeout"]["continuation"] == contract()
    assert item["state"] == "PENDING"
    assert item["continuation"]["project_complete"] is False
    assert item["continuation"]["parent_owner"] == "parent"
    assert item["continuation"]["next_owner"] == "independent-reviewer"
    assert c.status(setup[1])["dispatchable"] == [item["id"]]
    assert item["worker_started"] is False


def test_required_continuation_cannot_close_without_owner_action(setup):
    setup[2]["continuation_required"] = True
    task = start(setup)
    documents(setup, task)
    p.run_check(setup[0], task, "unit")
    with pytest.raises(GateError, match="invalid_continuation_contract"):
        p.close(setup[0], task, review(setup, task))
    assert p.load_task(setup[0], task)["status"] != "CLOSED"


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(project_complete=True),
    lambda x: x.update(next_owner="author"),
    lambda x: x.update(parent_owner=""),
    lambda x: x["next_action"].update(kind="shell"),
    lambda x: x.update(command="start-any-worker"),
])
def test_incomplete_or_arbitrary_contract_is_refused(mutate):
    value = contract()
    mutate(value)
    with pytest.raises(GateError):
        c.validate(value)


def test_old_closeout_contract_remains_valid_without_opt_in(setup):
    task = start(setup)
    documents(setup, task)
    p.run_check(setup[0], task, "unit")
    assert p.close(setup[0], task, review(setup, task))["status"] == "CLOSED"
    assert p.verify_closeout(setup[0], task)["status"] == "PASS"
    with pytest.raises(GateError, match="invalid_continuation_contract"):
        c.reconcile(setup[1], setup[0], task)


def test_reconcile_after_lost_completion_signal_is_idempotent(setup):
    task = closed(setup)
    item = c.reconcile(setup[1], setup[0], task)
    before = filemap(setup[1])
    assert c.reconcile(setup[1], setup[0], task) == item
    assert filemap(setup[1]) == before
    assert len(c.status(setup[1])["items"]) == 1


def test_report_only_turn_does_not_overwrite_or_consume_pending_review(setup, capsys):
    item = queued(setup)
    before = filemap(setup[1])
    assert foundation_cli.dispatch(["--home", str(setup[1]), "workflow", "route", "--kind", "audit"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "FAST_PATH"
    assert hooks.handle({"hook_event_name": "Stop"}) == {}
    assert c.reconcile(setup[1], setup[0], item["identity"]["task_id"]) == item
    assert filemap(setup[1]) == before
    assert c.status(setup[1])["dispatchable"] == [item["id"]]


def test_transport_accepts_but_response_is_lost_no_duplicate_writer(setup):
    home = setup[1]
    item = move(home, queued(setup), "claim")
    item = move(home, item, "begin-delivery")
    # Provider accepts exactly once, then its transport response is lost.
    sends = [accepted(item)]
    with pytest.raises(TimeoutError):
        raise TimeoutError("synthetic lost provider response")
    recovered = c.reconcile(home, setup[0], item["identity"]["task_id"])
    assert recovered["state"] == "DELIVERY_UNKNOWN"
    for action in ["claim", "begin-delivery"]:
        with pytest.raises(GateError, match="invalid_continuation_transition"):
            move(home, recovered, action)
    with pytest.raises(GateError, match="parent_owner_mismatch"):
        move(home, recovered, "claim", actor="replacement-parent")
    assert c.status(home)["dispatchable"] == []
    # Actual adapter reconciliation supplies the accepted event and later activity.
    final = move(home, recovered, "acknowledge", sends[0])
    assert final["state"] == "ACKNOWLEDGED" and len(sends) == 1
    assert final["continuation"] == contract()
    assert final["worker_started"] is False
    assert c.status(home)["project_completion_proven"] is False


def test_io_failure_after_attempt_commit_is_recoverable_without_resend(setup, monkeypatch):
    home = setup[1]
    item = move(home, queued(setup), "claim")
    original = c.atomic_json

    def commit_then_lose_response(path, value):
        original(path, value)
        raise OSError("synthetic response loss after atomic commit")

    monkeypatch.setattr(c, "atomic_json", commit_then_lose_response)
    with pytest.raises(OSError):
        move(home, item, "begin-delivery")
    monkeypatch.setattr(c, "atomic_json", original)
    recovered = c.read(home, item["id"])
    assert recovered["state"] == "DELIVERY_UNKNOWN"
    with pytest.raises(GateError):
        move(home, recovered, "begin-delivery")


def test_proven_non_delivery_retries_same_operation_identity(setup):
    home = setup[1]
    item = move(home, move(home, queued(setup), "claim"), "begin-delivery")
    receipt = rejected(item)
    retry = move(home, move(home, item, "not-sent", receipt), "begin-delivery")
    assert retry["attempt_id"] == item["attempt_id"]
    assert retry["delivery_generation"] == item["delivery_generation"] + 1
    assert retry["delivery_nonce"] != item["delivery_nonce"]
    assert retry["state"] == "DELIVERY_UNKNOWN"


@pytest.mark.parametrize("field,value", [("target_owner", "other-reviewer"), ("attempt_id", "wrong-attempt"),
                                       ("later_activity_id", "accepted-user-event"), ("status", "UNKNOWN")])
def test_wrong_or_unproven_delivery_cannot_acknowledge(setup, field, value):
    home = setup[1]
    item = move(home, move(home, queued(setup), "claim"), "begin-delivery")
    receipt = accepted(item)
    receipt[field] = value
    before = filemap(home)
    with pytest.raises(GateError):
        move(home, item, "acknowledge", receipt)
    assert filemap(home) == before


def test_cas_prevents_two_claims_for_the_same_completed_stage(setup):
    home = setup[1]
    pending = queued(setup)
    claimed = move(home, pending, "claim")
    with pytest.raises(GateError, match="revision_conflict"):
        move(home, pending, "claim")
    assert c.read(home, pending["id"]) == claimed


def test_source_change_after_stage_close_blocks_dispatch(setup):
    item = queued(setup)
    (setup[0] / "code.py").write_text("new unreviewed source\n")
    before = filemap(setup[1])
    with pytest.raises(GateError, match="stale"):
        move(setup[1], item, "claim")
    assert filemap(setup[1]) == before


def test_provider_acknowledgement_survives_later_source_change(setup):
    home = setup[1]
    item = move(home, move(home, queued(setup), "claim"), "begin-delivery")
    (setup[0] / "code.py").write_text("later successor source; old attempt already admitted\n")
    result = move(home, item, "acknowledge", accepted(item))
    assert result["state"] == "ACKNOWLEDGED"
    assert result["identity"] == item["identity"]
    assert result["continuation"]["project_complete"] is False
    with pytest.raises(GateError):
        move(home, result, "begin-delivery")


def test_unknown_delivery_blocks_new_stage_replacement_claim(setup):
    home = setup[1]
    first = move(home, move(home, queued(setup), "claim"), "begin-delivery")
    # A separately completed local stage cannot erase a prior uncertain dispatch.
    task = p.enter(setup[0], setup[2], session_id="later-author", turn_id="later-stage", user_home=home)["task_id"]
    documents(setup, task)
    p.run_check(setup[0], task, "unit")
    packet = review(setup, task)
    packet["continuation"] = contract()
    p.close(setup[0], task, packet)
    second = c.reconcile(home, setup[0], task)
    with pytest.raises(GateError, match="already_owned"):
        move(home, second, "claim")
    assert c.status(home)["dispatchable"] == []
    assert c.read(home, first["id"])["state"] == "DELIVERY_UNKNOWN"
    move(home, first, "acknowledge", accepted(first))
    assert c.status(home)["dispatchable"] == [second["id"]]


def test_status_never_advertises_stale_source_as_dispatchable(setup):
    item = queued(setup)
    (setup[0] / "code.py").write_text("unreviewed successor source\n")
    before = filemap(setup[1])
    status = c.status(setup[1])
    assert status["dispatchable"] == []
    assert status["admissions"][item["id"]] == "BLOCKED_CURRENT_SOURCE_OR_OWNERSHIP"
    assert filemap(setup[1]) == before


def test_symlink_queue_cannot_escape_overlay(setup, tmp_path):
    queued(setup)
    target = tmp_path / "outside"
    target.mkdir()
    queue = setup[1] / "state/continuations"
    for path in queue.iterdir():
        path.unlink()
    queue.rmdir()
    queue.symlink_to(target, target_is_directory=True)
    with pytest.raises(GateError, match="symlink"):
        c.status(setup[1])


def test_continuation_cli_uses_candidate_module_and_reports_no_authority(setup):
    queued(setup)
    result, code = c.command(["status"], setup[1])
    assert code == 0 and result["external_authority_granted"] is False
    assert Path(c.__file__).resolve().parents[1] == Path(__file__).resolve().parents[1] / "src"
    assert workflow.route("project-change", ["deploy"])["status"] == "BLOCKED"


def test_opt_in_flag_is_typed_without_changing_original_answers(setup):
    answers = copy.deepcopy(setup[2])
    answers["continuation_required"] = "yes"
    with pytest.raises(GateError, match="must_be_boolean"):
        p._answers(answers)


def test_generic_guide_is_packaged_with_source_parity():
    root = Path(__file__).resolve().parents[1]
    guide = (root / "docs/WORK_CONTINUATION.md").read_bytes()
    assert guide == (Path(c.__file__).parent / "resources/docs/WORK_CONTINUATION.md").read_bytes()
    assert b"DELIVERY_UNKNOWN" in guide and b"parent adapter" in guide
    assert b"/" + b"Users" + b"/" not in guide
