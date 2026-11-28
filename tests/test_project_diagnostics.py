"""Temporary diagnosis retains choices, evidence and the existing task writer.

These local fixtures exercise state transport and gates, not audit quality,
running-client adoption or a user's production migration.
"""
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from agent_os import project, project_diagnostics as d, task_metadata as tm, turns
from agent_os.safeio import GateError, atomic_json, filemap, lock, sha, within
from test_foundation import documents, review, setup as foundation_setup

setup = foundation_setup
ROOT = Path(__file__).resolve().parents[1]


def enter(setup, level=1):
    root, home, answers = setup
    answers = deepcopy(answers)
    if level is not None:
        answers["development"] = {"level": level, "scope": "project:synthetic"}
    return project.enter(root, answers, session_id="session-a", turn_id="turn-a",
                         user_home=home)["task_id"]


def mutation(setup, task_id, *, run="audit-a", session="session-a", turn="turn-a"):
    root, home, _ = setup
    current = d.status(root, task_id)
    return dict(user_home=home, session_id=session, turn_id=turn, run_id=run,
                expected_task_sha256=current["task_sha256"],
                expected_revision=current["task_revision"])


def begin(setup, task_id, **kwargs):
    return d.start(setup[0], task_id, scope="current module/service contracts",
                   reason="The next milestone depends on unverified current boundaries.",
                   **mutation(setup, task_id, **kwargs))


def result():
    return {"summary": "Existing API boundary and documentation were compared.",
            "remaining": ["UNKNOWN: user migration and rollback have not run."],
            "next_action": "Continue the permitted synthetic compatibility step.",
            "references": ["docs/agentos/DOSSIER.md#current-contracts"]}


@pytest.mark.parametrize("level", [1, 3, 5])
def test_diagnostic_cycle_preserves_ready_evidence_and_returns_selected_level(setup, level):
    root, home, _ = setup
    task = enter(setup, level)
    assert documents(setup, task)["status"] == "READY"
    assert project.run_check(root, task, "unit")["status"] == "PASS"
    before = project.load_task(root, task)
    project_bytes = project.project_file(root).read_bytes()
    turn_bytes = turns.turn_path(home, "session-a").read_bytes()
    started = begin(setup, task)
    assert started["status"] == "ACTIVE" and started["diagnostic"]["effective_level"] == 0
    assert started["diagnostic"]["return_development"] == before["answers"]["development"]
    current = project.load_task(root, task)
    assert {k: v for k, v in current.items() if k != "diagnostics"} == before
    # Diagnosis is a work mode, not a new interceptor for already approved checks.
    assert project.check_ready(root, task)["status"] == "PASS"
    with pytest.raises(GateError, match="check_not_in_stage_contract"):
        project.run_check(root, task, "not-approved")
    assert project.run_check(root, task, "unit")["status"] == "PASS"
    before_finish = {k: v for k, v in project.load_task(root, task).items()
                     if k != "diagnostics"}
    ended = d.finish(root, task, result=result(), **mutation(setup, task))
    assert ended["status"] == "COMPLETED"
    assert ended["diagnostic"]["effective_level"] == level
    assert ended["run"]["resumed_development"] == before["answers"]["development"]
    assert ended["run"]["result"]["remaining"] == result()["remaining"]
    assert ended["authority_granted"] is ended["product_writes_authorized"] is False
    assert ended["behavior_compliance"] == "NOT_PROVEN" and ended["native_hooks"] == "DISABLED"
    current = project.load_task(root, task)
    assert {k: v for k, v in current.items() if k != "diagnostics"} == before_finish
    assert current["diagnostics"]["generation"] == 2
    assert project.check_ready(root, task)["status"] == "PASS"
    assert project.assess(root, task)["status"] == "PASS"
    assert project.project_file(root).read_bytes() == project_bytes
    assert turns.turn_path(home, "session-a").read_bytes() == turn_bytes


def test_resume_keeps_active_diagnostic_and_later_owner_level_wins(setup):
    root, home, answers = setup
    task = enter(setup)
    begin(setup, task)
    resumed = project.enter(root, {**answers, "authority": "Current synthetic resumed authority."},
        session_id="session-b", turn_id="turn-b", user_home=home, resume_task=task)
    assert resumed["diagnostic"]["effective_level"] == 0
    assert resumed["development"]["level"] == 1
    with pytest.raises(GateError, match="writer_mismatch"):
        d.finish(root, task, result=result(), **mutation(setup, task))
    selected = {"level": 5, "scope": "module:compatibility"}
    project.enter(root, {"authority": "Current synthetic owner choice.", "development": selected},
        session_id="session-b", turn_id="turn-b", user_home=home, resume_task=task, reuse=True)
    ended = d.finish(root, task, result=result(),
                     **mutation(setup, task, session="session-b", turn="turn-b"))
    assert ended["run"]["captured_development"]["level"] == 1
    assert ended["run"]["resumed_development"] == selected
    assert ended["diagnostic"]["development"] == selected
    saved = project.load_task(root, task)
    assert saved["status"] == "INTAKE" and "ready" not in saved and saved["receipts"] == []


def test_default_capture_cancel_and_read_only_status_do_not_invent_saved_choice(setup):
    root, home, _ = setup
    task = enter(setup, None)
    before = filemap(root), filemap(home)
    absent = d.status(root, task)
    assert absent["status"] == "NOT_STARTED" and absent["writes"] == []
    assert (filemap(root), filemap(home)) == before
    started = begin(setup, task)
    assert started["run"]["captured_development"] == {"level": 3, "scope": "task"}
    assert "readiness_required" in project.check_ready(root, task)["errors"]
    assert project.run_check(root, task, "unit")["status"] == "BLOCKED"
    cancelled_result = {**result(), "summary": "Audit cancelled after identifying the current source.",
                        "references": []}
    ended = d.cancel(root, task, result=cancelled_result, **mutation(setup, task))
    assert ended["status"] == "CANCELLED" and ended["diagnostic"]["effective_level"] == 3
    saved = project.load_task(root, task)
    assert "development" not in saved["answers"]
    assert saved["status"] == "INTAKE" and "ready" not in saved
    assert "readiness_required" in project.check_ready(root, task)["errors"]


def test_close_requires_finishing_only_this_active_diagnostic_not_new_readiness(setup):
    root, home, _ = setup
    task = enter(setup)
    begin(setup, task)
    before = filemap(root), filemap(home)
    closed = project.close(root, task, review(setup, task), user_home=home)
    assert closed["status"] == "BLOCKED"
    assert closed["errors"] == ["diagnostic_finish_or_cancel_before_close"]
    assert (filemap(root), filemap(home)) == before
    d.finish(root, task, result=result(), **mutation(setup, task))
    still_unready = project.close(root, task, review(setup, task), user_home=home)
    assert still_unready["status"] == "BLOCKED"
    assert "readiness_required" in still_unready["errors"]
    assert "diagnostic_finish_or_cancel_before_close" not in still_unready["errors"]


def test_checkpoint_suspends_diagnosis_without_blocking_another_task(setup, monkeypatch):
    from agent_os import handoff_lifecycle
    root, home, answers = setup
    # Test the project lifecycle with its delivery boundary isolated; this is
    # neither a Library/host delivery test nor a claim about an actual handoff.
    monkeypatch.setattr(handoff_lifecycle, "deliver", lambda *a, **kw:
                        {"status": "SYNTHETIC_HANDOFF", "external_effects": False})
    task = enter(setup)
    begin(setup, task)
    assert project.checkpoint(root, task, "Audit suspended with current findings.",
        "Resume this task for its remaining audit.", user_home=home)["status"] == "CHECKPOINT"
    old_run = deepcopy(d.active(project.load_task(root, task)))
    other = project.enter(root, {**answers, "development": {"level": 3, "scope": "other task"}},
        session_id="session-other", turn_id="turn-other", user_home=home)["task_id"]
    assert d.view(project.load_task(root, other))["effective_level"] == 3
    assert d.active(project.load_task(root, other)) is None
    assert d.active(project.load_task(root, task)) == old_run
    with pytest.raises(GateError, match="active_task_required"):
        d.finish(root, task, result=result(), **mutation(setup, task))
    project.checkpoint(root, other, "Independent work checkpoint.",
                       "Resume its own current plan.", user_home=home)
    resumed = project.enter(root, {"authority": "Current owner resumed the suspended audit."},
        session_id="session-resume", turn_id="turn-resume", user_home=home,
        resume_task=task, reuse=True)
    assert resumed["diagnostic"]["effective_level"] == 0
    assert d.active(project.load_task(root, task)) == old_run
    ended = d.finish(root, task, result=result(),
        **mutation(setup, task, session="session-resume", turn="turn-resume"))
    assert ended["diagnostic"]["effective_level"] == 1


@pytest.mark.parametrize("initial_level, new_development", [
    (None, None), (2, {"level": 4, "scope": "stage:catalog-contracts"}),
])
def test_published_checkpoint_restores_portable_active_diagnosis(setup, tmp_path, initial_level, new_development):
    from agent_os import context_gate
    from agent_os.handoff import Library, local_principal
    from test_development_levels import request

    root, home, _ = setup
    task = enter(setup, initial_level)
    reason, next_step = "Current contract work is recorded.", "Continue the catalog review."
    started = begin(setup, task)
    if new_development is not None:
        project.enter(root, {"authority": "Current scoped owner choice.", "development": new_development},
            session_id="session-a", turn_id="turn-a", user_home=home, resume_task=task, reuse=True)
    assert project.checkpoint(root, task, reason, next_step)["status"] == "CHECKPOINT"
    lib, principal, handoff_id = Library(home / "results-library"), local_principal(), "handoff:" + task
    first_ref = lib.resolve(handoff_id, principal)["row"]["manifest_ref"]["object_id"]
    first = lib.read_evidence(handoff_id, "evidence:review", principal)
    assert first["captured_bytes_verified"]
    delivered = json.loads(first["bytes"])
    portable = request(purpose="continuation")
    portable["goal"].update(delivered["continuation"])
    cap = context_gate.build(tmp_path / "absent-recipient-home", portable)
    assert cap["effective_level"] == 0 and not cap["authority_granted"]
    assert cap["diagnostic"] == started["diagnostic"]["active"]
    assert cap["development"] == (new_development or {"level": 3, "scope": "task"})

    # Only the current pass travels. A later snapshot cannot reactivate it or alter old bytes.
    d.finish(root, task, result=result(), **mutation(setup, task))
    assert project.checkpoint(root, task, reason, next_step)["status"] == "CHECKPOINT"
    current = json.loads(lib.read_evidence(handoff_id, "evidence:review", principal)["bytes"])
    assert "continuation" not in current
    assert lib.read_evidence(handoff_id, "evidence:review", principal, revision=first_ref)["bytes"] == first["bytes"]


def test_portable_diagnosis_applies_recipient_secret_filter_before_publication(setup):
    from agent_os.handoff import Library, local_principal

    root, home, _ = setup
    task = enter(setup)
    project.checkpoint(root, task, "Before inspecting the contract.", "Inspect the adapter.")
    lib, principal, handoff_id = Library(home / "results-library"), local_principal(), "handoff:" + task
    first = lib.read_evidence(handoff_id, "evidence:review", principal)["bytes"]
    assert "continuation" not in json.loads(first)
    synthetic_value = "gho_" + "A" * 24
    d.start(root, task, scope="contract", reason=synthetic_value, **mutation(setup, task))
    with pytest.raises(GateError, match="context_secret_like_value_refused"):
        project.checkpoint(root, task, "Inspecting the adapter.", "Continue the contract review.")
    assert lib.read_evidence(handoff_id, "evidence:review", principal)["bytes"] == first
    assert d.status(root, task)["diagnostic"]["effective_level"] == 0


@pytest.mark.parametrize("boundary", ["before_publish", "after_publish"])
def test_pre_diagnostic_checkpoint_retry_preserves_candidate_and_journal(setup, monkeypatch, boundary):
    from agent_os import handoff_lifecycle
    from agent_os.handoff import Library, local_principal

    root, home, _ = setup
    task = enter(setup, 2)
    started = begin(setup, task)
    def checkpoint():
        return project.checkpoint(root, task, "Contract under review.", "Continue the catalog review.")

    original = handoff_lifecycle.deliver
    def legacy(root, value, *args, **kwargs):
        return original(root, {k: v for k, v in value.items() if k != "diagnostics"}, *args, **kwargs)
    def interrupt(*args, **kwargs):
        raise OSError("synthetic interrupted checkpoint")

    with monkeypatch.context() as old:
        old.setattr(handoff_lifecycle, "deliver", legacy)
        if boundary == "before_publish":
            old.setattr(Library, "publish_handoff", interrupt)
        else:
            old.setattr(tm, "write_task", interrupt)
        with pytest.raises((GateError, OSError), match="synthetic interrupted checkpoint"):
            checkpoint()

    folder = root / ".agentos/tasks" / task
    paths = list(folder.glob("handoff-checkpoint-*.json"))
    assert len(paths) == 1
    journal_bytes = paths[0].read_bytes()
    retained = json.loads(journal_bytes)
    lib, principal, hid = Library(home / "results-library"), local_principal(), "handoff:" + task
    for _ in range(2):
        assert checkpoint()["status"] == "CHECKPOINT"
        assert list(folder.glob("handoff-checkpoint-*.json")) == paths
        assert paths[0].read_bytes() == journal_bytes
        assert lib.resolve(hid, principal)["row"]["manifest_ref"] == retained["candidate_ref"]
        assert "continuation" not in json.loads(lib.read_evidence(hid, "evidence:review", principal)["bytes"])
    assert d.status(root, task)["diagnostic"]["active"] == started["diagnostic"]["active"]

    # The same text for a newly active run must not be swallowed by the old journal.
    d.finish(root, task, result=result(), **mutation(setup, task))
    next_run = begin(setup, task, run="audit-later")
    assert checkpoint()["status"] == "CHECKPOINT"
    assert len(list(folder.glob("handoff-checkpoint-*.json"))) == 2
    current = json.loads(lib.read_evidence(hid, "evidence:review", principal)["bytes"])
    assert current["continuation"]["diagnostic"] == next_run["diagnostic"]["active"]


def test_superseded_legacy_checkpoint_does_not_capture_new_diagnosis(setup):
    from agent_os.handoff import Library, local_principal

    root, home, _ = setup
    task = enter(setup, 4)
    first, next_step = "Original summary.", "Continue the contract review."
    project.checkpoint(root, task, first, next_step)
    project.checkpoint(root, task, "Superseding summary.", next_step)
    started = begin(setup, task)
    assert project.checkpoint(root, task, first, next_step)["status"] == "CHECKPOINT"
    lib = Library(home / "results-library")
    payload = json.loads(lib.read_evidence("handoff:" + task, "evidence:review", local_principal())["bytes"])
    assert payload["continuation"]["diagnostic"] == started["diagnostic"]["active"]


def test_run_identity_prevents_nested_duplicate_and_reopened_diagnostics(setup):
    root, home, _ = setup
    task = enter(setup)
    begin(setup, task)
    before = filemap(root), filemap(home)
    repeated = begin(setup, task)
    assert not repeated["changed"] and repeated["writes"] == []
    assert (filemap(root), filemap(home)) == before
    with pytest.raises(GateError, match="already_active"):
        begin(setup, task, run="audit-b")
    with pytest.raises(GateError, match="run_id_conflict"):
        d.start(root, task, scope="different scope", reason="Changed cause.", **mutation(setup, task))
    d.finish(root, task, result=result(), **mutation(setup, task))
    before = filemap(root), filemap(home)
    assert d.finish(root, task, result=result(), **mutation(setup, task))["changed"] is False
    assert begin(setup, task)["status"] == "COMPLETED"
    with pytest.raises(GateError, match="completed_run_immutable"):
        d.cancel(root, task, result=result(), **mutation(setup, task))
    assert (filemap(root), filemap(home)) == before
    begin(setup, task, run="audit-b")
    saved = project.load_task(root, task)
    assert [r["status"] for r in saved["diagnostics"]["runs"]] == ["COMPLETED", "ACTIVE"]
    assert saved["diagnostics"]["generation"] == 3


@pytest.mark.parametrize("field,value", [("expected_task_sha256", "0" * 64), ("expected_revision", 99)])
def test_stale_cas_refuses_without_changing_any_metadata(setup, field, value):
    root, home, _ = setup
    task = enter(setup)
    args = mutation(setup, task)
    args[field] = value
    before = filemap(root), filemap(home)
    with pytest.raises(GateError, match="cas_mismatch"):
        d.start(root, task, scope="task", reason="Current inventory required.", **args)
    assert (filemap(root), filemap(home)) == before


def test_existing_project_lock_prevents_a_second_writer(setup):
    root, _, _ = setup
    task = enter(setup)
    args = mutation(setup, task)
    with lock(within(root, ".agentos/write.lock")):
        with pytest.raises(GateError, match="busy_or_stale_lock"):
            d.start(root, task, scope="task", reason="Current inventory required.", **args)
    assert d.status(root, task)["status"] == "NOT_STARTED"


def test_conflicting_task_write_between_read_and_write_is_preserved(setup, monkeypatch):
    root, _, _ = setup
    task = enter(setup)
    args = mutation(setup, task)
    original = tm.encoded
    concurrent = None
    def competing_writer(value, *a, **kw):
        nonlocal concurrent
        encoded = original(value, *a, **kw)
        if "diagnostics" in value and concurrent is None:
            concurrent = project.load_task(root, task)
            concurrent["concurrent_note"] = "Independent current writer update; never discard."
            atomic_json(project.task_path(root, task), concurrent)
        return encoded
    monkeypatch.setattr(tm, "encoded", competing_writer)
    with pytest.raises(GateError, match="changed_before_write"):
        d.start(root, task, scope="task", reason="Current inventory required.", **args)
    assert project.load_task(root, task) == concurrent
    assert "diagnostics" not in concurrent


def test_postwrite_divergence_is_not_reported_as_success(setup, monkeypatch):
    root, _, _ = setup
    task = enter(setup)
    args = mutation(setup, task)
    original = tm.write_task
    def overwrite_after(value_root, value):
        original(value_root, value)
        changed = deepcopy(value)
        changed["external_note"] = "Changed immediately after canonical readback."
        atomic_json(project.task_path(root, task), changed)
    monkeypatch.setattr(tm, "write_task", overwrite_after)
    with pytest.raises(GateError, match="readback_mismatch"):
        d.start(root, task, scope="task", reason="Current inventory required.", **args)
    # Outcome is retained for status/reconciliation; no implicit rollback/replay.
    assert d.status(root, task)["status"] == "ACTIVE"


@pytest.mark.parametrize("status", [[], {}, "UNKNOWN"])
def test_corrupt_diagnostic_is_controlled_refusal_not_a_default_or_typeerror(setup, status):
    root, _, _ = setup
    task = enter(setup)
    begin(setup, task)
    saved = project.load_task(root, task)
    saved["diagnostics"]["runs"][0]["status"] = status
    atomic_json(project.task_path(root, task), saved)
    before = project.task_path(root, task).read_bytes()
    with pytest.raises(GateError, match="diagnostic"):
        project.check_ready(root, task)
    with pytest.raises(GateError, match="diagnostic"):
        d.status(root, task)
    assert project.task_path(root, task).read_bytes() == before


@pytest.mark.parametrize("changed", ["project_id", "active_task", "receipt", "session", "home", "closed", "recovery"])
def test_exact_current_binding_and_nonrecovery_task_are_required(setup, tmp_path, changed):
    root, home, _ = setup
    task = enter(setup)
    args = mutation(setup, task)
    if changed == "project_id":
        saved = project.load_task(root, task); saved["project_id"] = "another-project"
        atomic_json(project.task_path(root, task), saved)
    elif changed == "active_task":
        saved = project.load_project(root); saved["active_task"] = "task-other"
        atomic_json(project.project_file(root), saved)
    elif changed == "receipt":
        path = turns.turn_path(home, "session-a")
        receipt = json.loads(path.read_text()); receipt["task_id"] = "task-other"
        atomic_json(path, receipt)
    elif changed == "session":
        args["session_id"] = "session-other"
    elif changed == "home":
        args["user_home"] = tmp_path / "unused-home"
    else:
        saved = project.load_task(root, task)
        saved["status"] = "CLOSED" if changed == "closed" else "RECOVERY_REQUIRED"
        atomic_json(project.task_path(root, task), saved)
    before = filemap(root), filemap(home)
    with pytest.raises(GateError, match="diagnostic"):
        d.start(root, task, scope="task", reason="Current inventory required.", **args)
    assert (filemap(root), filemap(home)) == before
    assert not (tmp_path / "unused-home").exists()


@pytest.mark.parametrize("link", ["symlink", "hardlink"])
def test_linked_task_metadata_is_not_rewritten(setup, tmp_path, link):
    root, _, _ = setup
    task = enter(setup)
    args = mutation(setup, task)
    path = project.task_path(root, task)
    retained = tmp_path / "retained-task.json"
    original = path.read_bytes()
    retained.write_bytes(original)
    path.unlink()
    if link == "symlink":
        path.symlink_to(retained)
    else:
        os.link(retained, path)
    with pytest.raises(GateError, match="link"):
        d.start(root, task, scope="task", reason="Current inventory required.", **args)
    assert retained.read_bytes() == original


def test_real_project_command_and_task_schema(setup, tmp_path):
    import jsonschema
    root, home, _ = setup
    task = enter(setup)
    before = d.status(root, task)
    started, code = project.command(["diagnose", "start", "--root", str(root), "--task", task,
        "--run", "audit-cli", "--session", "session-a", "--turn", "turn-a",
        "--expected-task-sha256", before["task_sha256"], "--expected-revision", str(before["task_revision"]),
        "--scope", "task", "--reason", "Compare the current source and contracts."], home)
    assert code == 0 and started["status"] == "ACTIVE"
    schema = json.loads((ROOT / "schemas/project-task-v1.schema.json").read_text())
    jsonschema.validate(project.load_task(root, task), schema)
    path = tmp_path / "result.json"
    atomic_json(path, result())
    ended, code = project.command(["diagnose", "finish", "--root", str(root), "--task", task,
        "--run", "audit-cli", "--session", "session-a", "--turn", "turn-a",
        "--expected-task-sha256", started["task_sha256"], "--expected-revision", str(started["task_revision"]),
        "--result", str(path)], home)
    assert code == 0 and ended["status"] == "COMPLETED"
    jsonschema.validate(project.load_task(root, task), schema)
