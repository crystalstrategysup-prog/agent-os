"""Real disposable Library/lifecycle fixtures, never proof of native admission."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import test_foundation
from test_foundation import documents, start

from agent_os import accepted_checkpoint_history as history
from agent_os import interrupted_continuation as ic
from agent_os import project as p
from agent_os import refusal_recovery as rr
from agent_os.handoff import Library, local_principal
from agent_os.safeio import GateError, atomic_json, sha
from agent_os.turns import advance_standalone_turn, turn_path

setup = test_foundation.setup


@pytest.fixture
def case(setup):
    root, home, answers = setup
    task = start(setup)
    p.checkpoint(root, task, "Retain unfinished history", "Fresh entry")
    advance_standalone_turn(home, "s", "t", "old", root, task)
    p.enter(root, answers, session_id="s", turn_id="old", user_home=home, resume_task=task)
    documents(setup, task)
    return root, home, task, answers


def qualified(case):
    root, home, task, _ = case
    value = p.load_task(root, task)
    return history.qualify(root, home, task_id=task, project_id=value["project_id"], revision=value["revision"])


def request(case, schema=ic.COMPLETED_HISTORY_SCHEMA):
    root, home, task, _ = case
    value = p.load_task(root, task)
    paths = {"project": root / ".agentos/project.json", "task": root / f".agentos/tasks/{task}/task.json",
             "events": root / f".agentos/tasks/{task}/events.jsonl", "turn": turn_path(home, "s")}
    expected = {key + "_sha256": sha(path.read_bytes()) for key, path in paths.items()}
    expected["source_sha256"] = ic.source(root)
    result = {"schema": schema, "operation_id": "a" * 32, "root": str(root), "user_home": str(home),
              "project_id": value["project_id"], "task_id": task, "revision": value["revision"],
              "session_id": "s", "native_thread_id": "native", "actor_id": "native",
              "previous_turn": "old", "current_turn": "new", "expected": expected,
              "goal_sha256": sha(ic.encoded(value["answers"])),
              "native_mapping": {"native_cwd": str(root), "workflow_session_id": "s", "bound_turn_id": "old",
                                 "task_sha256": expected["task_sha256"], "turn_sha256": expected["turn_sha256"],
                                 "evidence_ref": "synthetic:fixture-not-live"}}
    if schema == ic.COMPLETED_HISTORY_SCHEMA:
        result["accepted_checkpoint_history_sha256"] = qualified(case)["sha256"]
    return result


def authority(r):
    now = datetime.now(timezone.utc)
    return {"schema": ic.authority_schema(r), "request_sha256": sha(ic.encoded(r)),
            "actor_id": r["actor_id"], "session_id": r["session_id"], "current_turn": r["current_turn"],
            "root": r["root"], "task_id": r["task_id"], "decision_ref": "synthetic:current-owner",
            "decision_sha256": "f" * 64, "valid_from": (now - timedelta(seconds=5)).isoformat(),
            "valid_until": (now + timedelta(seconds=300)).isoformat(), "revoked": False}


def observer(r, *, old="completed", current="inProgress", effect=None):
    def read_thread(**params):
        if effect:
            effect()
        return {"thread": {"id": r["native_thread_id"], "cwd": r["native_mapping"]["native_cwd"]},
                "turns": [{"id": "new", "status": current}] if "cursor" not in params else [{"id": "old", "status": old}],
                "page": {"hasMore": "cursor" not in params, "nextCursor": "older" if "cursor" not in params else None}}
    return ic.SupportedReadThreadObserver(read_thread)


def metadata(case):
    root, home, task, _ = case
    paths = [root / ".agentos/project.json", root / f".agentos/tasks/{task}/task.json",
             root / f".agentos/tasks/{task}/events.jsonl", turn_path(home, "s")]
    return {str(path): path.read_bytes() for path in paths}


def journals(case):
    root, _, task, _ = case
    return {path.name: path.read_bytes() for path in (root / f".agentos/tasks/{task}").glob("handoff-*") if path.is_file()}


def one_journal(case):
    root, _, task, _ = case
    return next((root / f".agentos/tasks/{task}").glob("handoff-checkpoint-*.json"))


def test_real_accepted_history_continues_to_full_entry_ready_and_check(case):
    root, home, task, answers = case
    before = journals(case)
    q = qualified(case)
    assert len(q["journals"]) == 1 and q["ready_granted"] is False
    r = request(case)
    receipt = ic.advance(root, home, r, authority(r), observer=observer(r))
    assert receipt["schema"] == "agentos.completed-continuation-receipt/v2"
    assert receipt["status"] == "FULL_ENTRY_REQUIRED" and receipt["ready_granted"] is False
    assert p.check_ready(root, task)["status"] == "BLOCKED"
    answers = copy.deepcopy(answers)
    answers["authority"] += " synthetic:current-owner"
    result = p.enter(root, answers, session_id="s", turn_id="new", user_home=home, resume_task=task)
    assert result["task_id"] == task
    documents((root, home, answers), task)
    assert p.run_check(root, task, "unit")["status"] == "PASS"
    assert journals(case) == before
    assert p.load_task(root, task)["answers"]["objective"] == answers["objective"]
    assert Library(home / "results-library").reconcile(q["journals"][0]["idempotency_key"], local_principal())["status"] == "accepted"


@pytest.mark.parametrize("schema", [ic.COMPLETED_SCHEMA, ic.SCHEMA])
def test_old_routes_still_refuse_accepted_history(case, schema):
    root, home, *_ = case
    r = request(case, schema)
    before = metadata(case)
    with pytest.raises(GateError, match="recovery_publication_unreconciled"):
        ic.advance(root, home, r, authority(r), observer=observer(r))
    assert metadata(case) == before
    with pytest.raises(GateError, match="recovery_publication_unreconciled"):
        rr._reject_handoff_journals(root, r["task_id"])


@pytest.mark.parametrize("change", ["idempotency", "payload", "root", "extra", "manifest", "unaccepted"])
def test_malformed_or_unaccepted_journal_does_not_qualify(case, change):
    path = one_journal(case)
    journal = json.loads(path.read_text())
    if change == "idempotency": journal["idempotency_key"] += "x"
    if change == "payload": journal["payload_sha256"] = "0" * 64
    if change == "root": journal["library_root"] += "/foreign"
    if change == "extra": journal["accepted"] = True
    if change == "manifest": journal["candidate_ref"]["locator"] += "x"
    if change == "unaccepted":
        lib = Library(case[1] / "results-library")
        m = lib.resolve("handoff:" + case[2], local_principal())["manifest"]
        m = copy.deepcopy(m)
        m["facets"]["summary"] += " not published"
        # A valid staged manifest is not an accepted operation/registry revision.
        from test_indexed_handoff import make
        m, assets = make(lib, 99, state="active")
        journal["candidate_ref"] = lib.build_handoff(m, None, local_principal(), assets=assets, acceptance_profile="checkpoint")
    atomic_json(path, journal)
    before = metadata(case)
    with pytest.raises(GateError, match="accepted_checkpoint_history_"):
        qualified(case)
    assert metadata(case) == before


@pytest.mark.parametrize("name", ["handoff-completion-x.json", "handoff-unknown.json", "HANDOFF-checkpoint-x.json"])
def test_unknown_handoff_names_never_qualify(case, name):
    path = one_journal(case).parent / name
    path.write_text("{}")
    with pytest.raises(GateError, match="unqualified_journal"):
        qualified(case)


def test_symlink_journal_never_qualifies(case):
    path = one_journal(case)
    data = path.read_bytes()
    destination = path.parent / "saved.json"
    destination.write_bytes(data)
    path.unlink()
    path.symlink_to(destination)
    with pytest.raises(GateError, match="unqualified_journal"):
        qualified(case)


def test_corrupt_required_object_fails_without_metadata_change(case):
    q = qualified(case)
    lib = Library(case[1] / "results-library")
    m = lib.resolve("handoff:" + case[2], local_principal())["manifest"]
    oid = m["evidence"][0]["ref"]["object_id"][7:]
    lib.store.path(f"objects/sha256/{oid[:2]}/{oid}").write_bytes(b"corrupt disposable fixture")
    before = metadata(case)
    with pytest.raises(GateError, match="unqualified"):
        qualified(case)
    assert metadata(case) == before and len(q["journals"]) == 1


def test_current_acl_revocation_is_not_replaced_by_historical_acceptance(case):
    qualified(case)
    path = case[1] / "results-library/ROOT.json"
    root = json.loads(path.read_text())
    root["access"]["readers"] = []
    atomic_json(path, root)
    with pytest.raises(GateError, match="unqualified"):
        qualified(case)


@pytest.mark.parametrize("mutation", ["digest", "authority", "source", "current", "previous", "refusal", "entry"])
def test_v2_preserves_existing_controls(case, mutation):
    root, home, *_ = case
    r = request(case)
    if mutation == "digest": r["accepted_checkpoint_history_sha256"] = "0" * 64
    a = authority(r)
    if mutation == "authority": a["revoked"] = True
    if mutation == "source": (root / "code.py").write_text("# drift")
    if mutation == "refusal": rr.pending(root).mkdir()
    if mutation == "entry": (root / ".agentos/entry-transaction.json").write_text("{}")
    before = metadata(case)
    ob = observer(r, old="inProgress" if mutation == "previous" else "completed", current="completed" if mutation == "current" else "inProgress")
    with pytest.raises(GateError):
        ic.advance(root, home, r, a, observer=ob)
    assert metadata(case) == before and not ic.marker(root).exists()


def test_post_observer_new_journal_stops_before_reservation(case):
    root, home, *_ = case
    r = request(case)
    before = metadata(case)
    def effect():
        (one_journal(case).parent / "handoff-unknown.json").write_text("{}")
    with pytest.raises(GateError, match="unqualified_journal"):
        ic.advance(root, home, r, authority(r), observer=observer(r, effect=effect))
    assert metadata(case) == before and not ic.marker(root).exists()


def test_required_ref_budget_is_enforced(case, monkeypatch):
    monkeypatch.setattr(history, "MAX_REQUIRED_BYTES", 1)
    with pytest.raises(GateError, match="required_object_limit"):
        qualified(case)


def test_committed_advance_is_not_replayed_and_reconcile_keeps_history(case):
    root, home, *_ = case
    r = request(case)
    before = journals(case)
    a = authority(r)
    first = ic.advance(root, home, r, a, observer=observer(r))
    after = metadata(case)
    with pytest.raises(GateError, match="already_committed"):
        ic.advance(root, home, r, a, observer=observer(r))
    second = ic.reconcile(root, home, r, a, observer=observer(r))
    assert first == second and metadata(case) == after and journals(case) == before


def test_partial_commit_reconciles_exact_operation(case, monkeypatch):
    root, home, *_ = case
    r = request(case)
    before = journals(case)
    original = ic.atomic_bytes
    def crash_at_turn(path, raw):
        if path == turn_path(home, "s"):
            raise OSError("synthetic interrupted write")
        return original(path, raw)
    monkeypatch.setattr(ic, "atomic_bytes", crash_at_turn)
    with pytest.raises(OSError, match="synthetic interrupted"):
        ic.advance(root, home, r, authority(r), observer=observer(r))
    assert ic.marker(root).exists()
    monkeypatch.setattr(ic, "atomic_bytes", original)
    receipt = ic.reconcile(root, home, r, authority(r), observer=observer(r))
    assert receipt["status"] == "FULL_ENTRY_REQUIRED"
    assert not ic.marker(root).exists() and journals(case) == before


def test_original_goal_and_acceptance_are_not_relaxed(case):
    root, home, task, answers = case
    r = request(case)
    ic.advance(root, home, r, authority(r), observer=observer(r))
    changed = copy.deepcopy(answers)
    changed["authority"] += " synthetic:current-owner"
    changed["objective"] = "Different goal"
    with pytest.raises(GateError, match="original_goal_must_remain"):
        p.enter(root, changed, session_id="s", turn_id="new", user_home=home, resume_task=task)
    assert p.check_ready(root, task)["status"] == "BLOCKED"


def test_foreign_project_or_nonhistorical_revision_is_rejected(case):
    root, home, task, _ = case
    current = p.load_task(root, task)
    for project_id, revision in [("project-foreign", current["revision"]), (current["project_id"], 1)]:
        with pytest.raises(GateError, match="manifest_identity"):
            history.qualify(root, home, task_id=task, project_id=project_id, revision=revision)


def test_saved_digest_is_not_proof_if_library_object_disappears(case):
    root, home, task, _ = case
    r = request(case)
    lib = Library(home / "results-library")
    m = lib.resolve("handoff:" + task, local_principal())["manifest"]
    oid = m["evidence"][0]["ref"]["object_id"][7:]
    lib.store.path(f"objects/sha256/{oid[:2]}/{oid}").unlink()
    before = metadata(case)
    with pytest.raises(GateError, match="accepted_checkpoint_history_unqualified"):
        ic.advance(root, home, r, authority(r), observer=observer(r))
    assert metadata(case) == before and not ic.marker(root).exists()


def test_retracted_checkpoint_does_not_qualify(case):
    root, home, task, _ = case
    old = qualified(case)
    library = Library(home / "results-library")
    library.retract("handoff:" + task, "Synthetic explicit retraction", local_principal())
    # Immutable accepted operation receipt still exists; it is not enough.
    assert library.reconcile(old["journals"][0]["idempotency_key"], local_principal())["status"] == "accepted"
    with pytest.raises(GateError, match="publication_state"):
        qualified(case)


def test_retraction_during_observation_stops_before_reservation(case):
    root, home, task, _ = case
    r = request(case)
    before = metadata(case)
    once = []
    def effect():
        if not once:
            Library(home / "results-library").retract("handoff:" + task, "Synthetic concurrent retraction", local_principal())
            once.append(True)
    with pytest.raises(GateError, match="publication_state"):
        ic.advance(root, home, r, authority(r), observer=observer(r, effect=effect))
    assert metadata(case) == before and not ic.marker(root).exists()


def test_superseded_accepted_history_remains_available(case):
    root, home, task, answers = case
    p.checkpoint(root, task, "Second accepted checkpoint", "Continue original work")
    advance_standalone_turn(home, "s", "old", "later", root, task)
    p.enter(root, answers, session_id="s", turn_id="later", user_home=home, resume_task=task)
    result = qualified(case)
    assert len(result["journals"]) == 2
    assert {row["publication_state"] for row in result["journals"]} == {"accepted", "superseded"}


def test_unknown_publication_state_is_not_assumed_accepted(case, monkeypatch):
    resolve = Library.resolve
    def changed(*args, **kwargs):
        result = resolve(*args, **kwargs)
        result["row"]["publication_state"] = "unknown"
        return result
    monkeypatch.setattr(Library, "resolve", changed)
    with pytest.raises(GateError, match="publication_state"):
        qualified(case)


def test_retraction_after_resolve_in_final_qualification_cannot_advance(case, monkeypatch):
    root, home, task, _ = case
    r = request(case)
    before = metadata(case)
    original_observe, original_resolve = ic.observe, Library.resolve
    state = {"armed": False, "attempted": False}
    def arm(*args, **kwargs):
        value = original_observe(*args, **kwargs)
        state["armed"] = True
        return value
    def withdraw(self, *args, **kwargs):
        value = original_resolve(self, *args, **kwargs)
        if state["armed"] and not state["attempted"]:
            state["attempted"] = True
            Library(home / "results-library").retract("handoff:" + task, "Synthetic competing retraction", local_principal())
        return value
    monkeypatch.setattr(ic, "observe", arm)
    monkeypatch.setattr(Library, "resolve", withdraw)
    with pytest.raises(GateError):
        ic.advance(root, home, r, authority(r), observer=observer(r))
    assert state["attempted"] and metadata(case) == before and not ic.marker(root).exists()


def test_library_shared_lock_retained_through_commit_then_released(case, monkeypatch):
    from agent_os.handoff_store import HandoffError
    root, home, task, _ = case
    r = request(case)
    original = ic.atomic_bytes
    attempted = []
    def at_commit(path, raw):
        if path == ic.marker(root) and not attempted:
            with pytest.raises(HandoffError, match="GENERATION_CONFLICT"):
                Library(home / "results-library").retract("handoff:" + task, "Synthetic competing commit", local_principal())
            attempted.append(True)
        return original(path, raw)
    monkeypatch.setattr(ic, "atomic_bytes", at_commit)
    assert ic.advance(root, home, r, authority(r), observer=observer(r))["status"] == "FULL_ENTRY_REQUIRED"
    assert attempted
    # No lease survives return; a separately authorized fixture write now works.
    Library(home / "results-library").retract("handoff:" + task, "Synthetic later retraction", local_principal())


def test_library_busy_stops_only_this_operation(case):
    from agent_os.handoff_store import publisher_lock
    root, home, *_ = case
    r = request(case)
    before = metadata(case)
    with publisher_lock(home / "results-library/publisher.lock"):
        with pytest.raises(GateError, match="library_busy_or_unavailable"):
            ic.advance(root, home, r, authority(r), observer=observer(r))
    assert metadata(case) == before and not ic.marker(root).exists()


def test_missing_publisher_lock_is_not_created_by_qualification(case):
    path = case[1] / "results-library/publisher.lock"
    path.rename(path.with_name("retained-publisher-lock"))
    with pytest.raises(GateError, match="library_busy_or_unavailable"):
        qualified(case)
    assert not path.exists()


def test_native_provider_roundtrip_does_not_hold_library_lock(case):
    root, home, *_ = case
    r = request(case)
    once = []
    def effect():
        if not once:
            Library(home / "results-library").register_topics([
                {"topic_id": "fixture:unrelated", "title": "Unrelated", "aliases": [], "redirect": None}
            ], local_principal())
            once.append(True)
    assert ic.advance(root, home, r, authority(r), observer=observer(r, effect=effect))["status"] == "FULL_ENTRY_REQUIRED"
    assert once
