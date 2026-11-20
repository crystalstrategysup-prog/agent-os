"""Scoped development choices through real entry, resume and context paths.

These tests prove selection/transport and unchanged gates, not a worker's
reasoning, speed, live adoption or the acceptance of a user's business system.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from test_foundation import documents
from test_foundation import setup as foundation_setup

from agent_os import context_gate, engineering_guidance, project, workflow
from agent_os.safeio import GateError, filemap

setup = foundation_setup
ROOT = Path(__file__).resolve().parents[1]


def choice(level=1, scope="project:synthetic-platform"):
    return {"level": level, "scope": scope}


def request(selected=None, purpose="project-change"):
    goal = {
        "original": "Connect the next module to the synthetic platform.",
        "scope": "Temporary local fixture; no external effects or user data.",
        "acceptance": ["The new link works in the retained common stand."],
        "known_answers": {"stand": "reuse the accepted local synthetic fixture"},
        "authority_ref": "synthetic-current-instruction",
        "source_ref": "synthetic-existing-plan",
    }
    if selected is not None:
        goal["development"] = selected
    return {
        "schema": "agentos.context-request/v1", "session_id": "synthetic-session",
        "turn_id": "synthetic-turn", "purpose": purpose,
        "profile_keys": [], "index_keys": [], "goal": goal,
    }


def enter(setup, selected=None, **kwargs):
    root, home, answers = setup
    supplied = deepcopy(answers)
    if selected is not None:
        supplied["development"] = selected
    return project.enter(root, supplied, session_id="synthetic-session",
                         turn_id="synthetic-turn", user_home=home, **kwargs)


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
def test_all_five_choices_are_stored_and_do_not_grant_readiness(setup, level):
    root, _, _ = setup
    selected = choice(level)
    result = enter(setup, selected)
    saved = project.load_task(root, result["task_id"])
    assert result["development"] == saved["answers"]["development"] == selected
    assert result["status"] == saved["status"] == "INTAKE"
    assert saved["receipts"] == [] and "ready" not in saved
    assert project.check_ready(root, saved["id"])["status"] == "BLOCKED"
    assert project.run_check(root, saved["id"], "unit")["status"] == "BLOCKED"


@pytest.mark.parametrize("level", [1, 3, 5])
def test_full_resume_in_new_session_retains_choice_and_invalidates_old_ready(setup, level):
    root, home, answers = setup
    selected = choice(level, "module:synthetic-platform/catalog")
    task = enter(setup, selected)["task_id"]
    assert documents(setup, task)["status"] == "READY"
    resumed_answers = {**answers, "authority": "Synthetic current instruction for the resumed fixture."}
    result = project.enter(root, resumed_answers, session_id="resumed-session",
                           turn_id="resumed-turn", user_home=home, resume_task=task)
    saved = project.load_task(root, task)
    assert result["task_id"] == task
    assert result["development"] == saved["answers"]["development"] == selected
    assert saved["answers"]["authority"] == resumed_answers["authority"]
    assert saved["session_id"] == "resumed-session" and saved["turn_id"] == "resumed-turn"
    assert saved["revision"] == 2 and saved["receipts"] == [] and "ready" not in saved
    assert project.check_ready(root, task)["status"] == "BLOCKED"


def test_mode_change_reuses_scope_but_still_requires_fresh_authority(setup):
    root, home, answers = setup
    task = enter(setup, choice(1))["task_id"]
    for level in (3, 5, 1):
        selected = choice(level)
        supplied = {"development": selected}
        before = filemap(root)
        with pytest.raises(GateError):
            project.enter(root, supplied, session_id="synthetic-session",
                          turn_id="synthetic-turn", user_home=home,
                          resume_task=task, reuse=True)
        assert filemap(root) == before
        supplied["authority"] = "Synthetic fresh authority for this mode change."
        result = project.enter(root, supplied, session_id="synthetic-session",
                               turn_id="synthetic-turn", user_home=home,
                               resume_task=task, reuse=True)
        saved = project.load_task(root, task)
        assert result["development"] == saved["answers"]["development"] == selected
        assert saved["answers"]["objective"] == answers["objective"]
        assert saved["answers"]["write_paths"] == answers["write_paths"]
        assert saved["answers"]["acceptance"] == answers["acceptance"]
        assert saved["answers"]["checks"] == answers["checks"]
        assert saved["answers"]["authority"] == supplied["authority"]
    with pytest.raises(GateError, match="scope_changed"):
        project.reuse_answers(root, task, {
            "development": choice(1), "authority": "Synthetic current instruction.",
            "objective": "Unrelated replacement goal without full intake.",
        })


def test_resume_questionnaire_reuses_choice_without_inheriting_authority(setup):
    root, home, _ = setup
    selected = choice(1, "stage:synthetic-common-stand")
    task = enter(setup, selected)["task_id"]
    result = project.questionnaire(root, user_home=home, resume_task=task)
    assert result["development"] == selected
    assert result["suggested_answers"]["development"] == selected
    assert "authority" not in result["suggested_answers"]
    assert [item["id"] for item in result["questions"]] == ["authority"]


@pytest.mark.parametrize("alias", ["1D", "1d"])
def test_case_alias_normalizes_to_one_not_a_sixth_level(setup, alias):
    result = enter(setup, choice(alias))
    saved = project.load_task(setup[0], result["task_id"])
    assert result["development"] == saved["answers"]["development"] == choice(1)


@pytest.mark.parametrize("selected", [
    {"level": True, "scope": "task"}, {"level": 0, "scope": "task"},
    {"level": 6, "scope": "task"}, {"level": 1.0, "scope": "task"},
    {"level": "1Dx", "scope": "task"}, {"level": 1, "scope": " "},
    {"level": 1, "scope": "x" * 201}, {"level": 1},
    {"level": 1, "scope": "task", "authority_granted": True},
])
def test_invalid_selection_cannot_change_project_metadata(setup, selected):
    root, home, _ = setup
    before = filemap(root)
    with pytest.raises(GateError):
        enter(setup, selected)
    assert filemap(root) == before
    assert not home.exists()


def test_explicit_null_cannot_erase_an_inherited_choice(setup):
    root, home, answers = setup
    task = enter(setup, choice(1))["task_id"]
    before = filemap(root)
    with pytest.raises(GateError):
        project.enter(root, {**answers, "development": None}, session_id="synthetic-session",
                      turn_id="synthetic-turn", user_home=home, resume_task=task)
    assert filemap(root) == before


def test_legacy_default_is_three_without_rewriting_legacy_answers_or_goal(setup, tmp_path):
    result = enter(setup)
    assert result["development"] == choice(3, "task")
    assert project.load_task(setup[0], result["task_id"])["answers"] == setup[2]
    raw = request()
    capsule = context_gate.build(tmp_path / "unused", raw)
    assert capsule["goal"] == raw["goal"]
    assert capsule["development"] == capsule["foundation_guidance"]["development"] == choice(3, "task")


@pytest.mark.parametrize("level", [1, 3, 5])
def test_context_carries_scoped_choice_across_session_and_turn_without_claiming_adoption(tmp_path, level):
    home = tmp_path / "unselected-owner"
    raw = request(choice(level, "module:synthetic-platform/topics"))
    initial = deepcopy(raw)
    first = context_gate.build(home, raw)
    resumed = {**raw, "purpose": "continuation", "session_id": "resumed-session",
               "turn_id": "resumed-turn", "goal": deepcopy(first["goal"])}
    current = context_gate.build(home, resumed)
    assert raw == initial
    assert current["goal"] == first["goal"]
    selected = raw["goal"]["development"]
    assert current["development"] == current["foundation_guidance"]["development"] == selected
    assert current["capsule_sha256"] != first["capsule_sha256"]
    assert current["authority_granted"] is False and current["native_hooks"] == "DISABLED"
    assert current["behavior_compliance"] == "NOT_PROVEN" and not home.exists()
    receipt = {key: current[key] for key in ("session_id", "turn_id", "capsule_sha256")}
    receipt.update(event_kind="tool_result", event_ref="synthetic-materialized-context-result")
    checked = context_gate.verify(home, resumed, receipt)
    assert checked["status"] == "CURRENT_BINDING_MATCH"
    assert checked["behavior_compliance"] == "NOT_PROVEN" and checked["authority_granted"] is False
    changed = deepcopy(resumed)
    changed["goal"]["development"] = choice(5 if level != 5 else 1, selected["scope"])
    with pytest.raises(GateError, match="binding_mismatch"):
        context_gate.verify(home, changed, receipt)


@pytest.mark.parametrize("level", [1, 3, 5])
def test_actual_guidance_cli_and_target_route_preserve_selection_and_gates(tmp_path, level):
    selected = choice(level, "stage:synthetic-connection")
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    process = subprocess.run(
        [sys.executable, "-m", "agent_os", "workflow", "guidance",
         "--development-level", str(level), "--development-scope", selected["scope"]],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=15,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    actual = json.loads(process.stdout)
    assert actual == engineering_guidance.load(development=selected)
    assert actual["development"] == selected
    assert actual["behavior_compliance"] == "NOT_PROVEN" and actual["authority_granted"] is False
    local = workflow.route("project-change", ["local-project-write"], development=selected)
    assert local["foundation_guidance"]["development"] == selected
    assert local["product_writes_authorized"] is False
    blocked = workflow.route("project-change", list(workflow.TARGET_EFFECTS), development=selected)
    assert blocked["status"] == "BLOCKED" and blocked["mode"] == "TARGET_AUTHORITY_REQUIRED"
    assert blocked["target_gates_required"] == sorted(workflow.TARGET_EFFECTS)
    assert blocked["product_writes_authorized"] is blocked["external_authority_granted"] is False
    assert blocked["native_hooks"] == "DISABLED" and blocked["writes"] == []


def test_development_options_do_not_create_a_gate_for_ordinary_reads():
    assert workflow.route("audit")["mode"] == "FAST_PATH"
    with pytest.raises(GateError):
        workflow.route("audit", development=choice(1))


@pytest.mark.parametrize("level", [1, 3, 5])
def test_new_scope_field_keeps_existing_context_secret_filter(tmp_path, level):
    synthetic_secret_like_scope = "sk-" + "synthetic" * 4
    home = tmp_path / "unselected-owner"
    with pytest.raises(GateError, match="secret_like_value_refused"):
        context_gate.build(home, request(choice(level, synthetic_secret_like_scope)))
    assert not home.exists()


@pytest.mark.parametrize("arguments", [
    ["--development-level", "1"], ["--development-scope", "task"],
])
def test_cli_requires_both_level_and_its_scope(arguments):
    with pytest.raises((SystemExit, GateError)):
        workflow.command(["guidance", *arguments])
