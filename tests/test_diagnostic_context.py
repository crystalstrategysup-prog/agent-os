"""Diagnostic context transport and return; no claim of semantic audit quality."""
from copy import deepcopy

import pytest

from agent_os import context_gate, engineering_guidance, project, project_diagnostics as diagnosis
from agent_os import workflow
from agent_os.safeio import GateError, atomic_json, filemap
from test_development_levels import choice, enter, request
from test_foundation import setup as setup


def run_args(root, home, task):
    status = diagnosis.status(root, task)
    return dict(user_home=home, session_id="synthetic-session", turn_id="synthetic-turn",
                run_id="diagnosis-contracts", expected_task_sha256=status["task_sha256"],
                expected_revision=status["task_revision"])


def finish_result():
    return {"summary": "Current CLI contracts inspected; HTTP OpenAPI is not applicable.",
            "remaining": ["Runtime adoption remains UNKNOWN."],
            "next_action": "The writer connects the next bounded local module.",
            "references": ["existing-dossier#inspected-cli"]}


def bound(root, task):
    value = request(purpose="continuation")
    value["development_source"] = {"root": str(root), "task_id": task,
                                   "revision": project.load_task(root, task)["revision"]}
    return value


@pytest.mark.parametrize("level", [1, 3, 5])
def test_native_context_enters_diagnostics_and_returns_without_rewriting_choice(setup, tmp_path, level):
    root, home, _ = setup
    selected = choice(level, "module:synthetic-users")
    task = enter(setup, selected)["task_id"]
    req = bound(root, task)
    before = context_gate.build(tmp_path / "unused-home", req)
    started = diagnosis.start(root, task, **run_args(root, home, task),
                              scope="service contracts", reason="Substantial transition needs a current map.")
    active = context_gate.build(tmp_path / "unused-home", req)
    assert active["effective_level"] == 0
    assert active["development"] == active["goal"]["development"] == selected
    assert active["diagnostic"] == started["diagnostic"]["active"]
    assert active["foundation_guidance"]["source"] == "docs/PROCESS.md#project-diagnostics"
    assert active["foundation_guidance"]["execution"]["return_development"] == selected
    assert active["capsule_sha256"] != before["capsule_sha256"]
    assert active["authority_granted"] is False and active["native_hooks"] == "DISABLED"
    finished = diagnosis.finish(root, task, **run_args(root, home, task), result=finish_result())
    after = context_gate.build(tmp_path / "unused-home", req)
    assert after["development"] == selected
    assert after["foundation_guidance"]["source"] == "docs/PROCESS.md#project-development"
    assert "diagnostic" not in after and "effective_level" not in after
    assert after["capsule_sha256"] not in {before["capsule_sha256"], active["capsule_sha256"]}
    assert finished["task_revision"] == started["task_revision"] == 1
    assert project.load_task(root, task)["answers"]["development"] == selected


def test_explicit_stale_diagnostic_cannot_override_bound_native_state(setup, tmp_path):
    root, home, _ = setup
    task = enter(setup, choice(1))["task_id"]
    started = diagnosis.start(root, task, **run_args(root, home, task), scope="contracts", reason="Need current map.")
    req = bound(root, task)
    req["goal"]["diagnostic"] = deepcopy(started["diagnostic"]["active"])
    req["goal"]["diagnostic"]["id"] = "foreign-diagnostic"
    with pytest.raises(GateError, match="context_diagnostic_selection_mismatch"):
        context_gate.build(tmp_path, req)
    req["goal"]["diagnostic"] = started["diagnostic"]["active"]
    diagnosis.finish(root, task, **run_args(root, home, task), result=finish_result())
    with pytest.raises(GateError, match="context_diagnostic_selection_mismatch"):
        context_gate.build(tmp_path, req)


def test_portable_read_only_audit_has_no_home_or_registration_effects(tmp_path):
    selected = choice(1, "project:portable")
    req = request(selected, purpose="audit")
    req["goal"]["diagnostic"] = {
        "id": "diagnosis-portable", "scope": "existing project", "reason": "Uncertain dependencies.",
        "captured_development": selected,
    }
    before = filemap(tmp_path)
    result = context_gate.build(tmp_path / "absent-home", req)
    assert result["status"] == "MATERIALIZED" and result["effective_level"] == 0
    assert result["development"] == selected
    assert filemap(tmp_path) == before and not (tmp_path / "absent-home").exists()
    req["goal"].pop("diagnostic")
    assert context_gate.build(tmp_path / "absent-home", req)["status"] == "FAST_PATH"
    assert workflow.route("audit")["intake_required"] is False


def test_portable_diagnostic_requires_explicit_current_choice(tmp_path):
    req = request(purpose="audit")
    req["goal"]["diagnostic"] = {"id": "d", "scope": "project", "reason": "Check direction.",
                                 "captured_development": choice(5)}
    with pytest.raises(GateError, match="context_diagnostic_saved_development_required"):
        context_gate.build(tmp_path, req)
    req["goal"]["development"] = choice(1)  # A later explicit choice can differ.
    assert context_gate.build(tmp_path, req)["development"] == choice(1)


def test_native_default_was_captured_without_inventing_a_saved_owner_choice(setup, tmp_path):
    root, home, _ = setup
    task = enter(setup)["task_id"]
    req = bound(root, task)
    with pytest.raises(GateError, match="context_development_task_choice_missing"):
        context_gate.build(tmp_path, req)
    diagnosis.start(root, task, **run_args(root, home, task), scope="project", reason="Inspect current structure.")
    assert context_gate.build(tmp_path, req)["development"] == {"level": 3, "scope": "task"}
    diagnosis.finish(root, task, **run_args(root, home, task), result=finish_result())
    assert context_gate.build(tmp_path, req)["development"] == {"level": 3, "scope": "task"}
    assert "development" not in project.load_task(root, task)["answers"]


@pytest.mark.parametrize("field", ["reason", "scope", "captured_scope"])
def test_native_and_portable_diagnostic_fields_share_secret_guard(setup, tmp_path, field):
    root, home, _ = setup
    token = "synthetic sk-" + "A" * 24
    selected = choice(1, token if field == "captured_scope" else "project")
    task = enter(setup, selected)["task_id"]
    started = diagnosis.start(root, task, **run_args(root, home, task),
                              scope=token if field == "scope" else "contracts",
                              reason=token if field == "reason" else "Review dependencies.")
    req = bound(root, task)
    with pytest.raises(GateError, match="context_secret_like_value_refused"):
        context_gate.build(tmp_path, req)
    portable = request(choice(1), purpose="audit")
    portable["goal"]["diagnostic"] = started["diagnostic"]["active"]
    with pytest.raises(GateError, match="context_secret_like_value_refused"):
        context_gate.build(tmp_path, portable)


def test_diagnostic_change_during_materialization_refuses_mixed_capsule(setup, tmp_path, monkeypatch):
    root, home, _ = setup
    task = enter(setup, choice(1))["task_id"]
    diagnosis.start(root, task, **run_args(root, home, task), scope="contracts", reason="Check project map.")
    original = engineering_guidance.load

    def concurrent_update(*args, **kwargs):
        result = original(*args, **kwargs)
        value = project.load_task(root, task)
        value["diagnostics"]["runs"][-1]["reason"] = "A concurrent writer changed this context."
        atomic_json(project.task_path(root, task), value)
        return result

    monkeypatch.setattr(engineering_guidance, "load", concurrent_update)
    with pytest.raises(GateError, match="context_development_source_changed_during_read"):
        context_gate.build(tmp_path, bound(root, task))


def test_zero_guidance_is_stateless_and_does_not_accept_zero_as_permanent_choice():
    result, code = workflow.command(["guidance", "--method", "project-diagnostics",
                                     "--development-level", "5", "--development-scope", "project"])
    assert code == 0 and result["development"] == {"level": 5, "scope": "project"}
    assert result["execution"]["lifecycle"] == "GUIDANCE_ONLY" and result["writes"] == []
    assert result["authority_granted"] is False
    with pytest.raises(GateError, match="diagnostic_zero_use_project_diagnostics"):
        workflow.command(["guidance", "--development-level", "0", "--development-scope", "project"])
