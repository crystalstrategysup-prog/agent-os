from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

from agent_os import (
    dispatch_gate,
    doc_catalog,
    hooks,
    integration,
    observation,
    overlay,
    safeio,
    turns,
)
from agent_os import (
    project as p,
)
from agent_os.config import AgentOSPaths, default_config
from agent_os.safeio import (
    GateError,
    atomic_json,
    filemap,
    lock,
    read_json,
    within,
)


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    home = tmp_path / "user"
    p.initialize(
        root,
        "Fixture",
        ["general"],
        [],
        {
            k: "Verified synthetic local fixture, no external service or actual user data."
            for k in p.CONTEXT_KEYS
        },
    )
    answers = {
        k: "Synthetic local fixture contract; reviewer checks exact source and current local result."
        for k in p.QUESTIONS
    }
    answers.update(
        change_kind="implementation",
        write_paths=["code.py"],
        acceptance=[
            {
                "id": "A1",
                "criterion": "Local approved process exits successfully.",
                "checks": ["unit"],
            }
        ],
        checks=[
            {
                "id": "unit",
                "argv": [sys.executable, "-c", 'print("fixture PASS")'],
                "timeout": 30,
            }
        ],
    )
    return root, home, answers


def start(setup):
    root, home, answers = setup
    value = p.enter(root, answers, session_id="s", turn_id="t", user_home=home)
    return value["task_id"]


def documents(setup, task):
    root = setup[0]
    for doc_id in p.load_task(root, task)["selection"]["required"]:
        rel = f"docs/agentos/reviewed-{doc_id}.md"
        (root / rel).write_text(
            f"# Fixture {doc_id}\n\nTask: {task}\n\n"
            + "Purpose: test a local fixture. Scope: no real user data or remote writes. "
            + "Verification: exact contracted local process. Rollback: remove only temporary fixture. "
            + "Next step: a new documented task. Sources: this test file; not live evidence.\n"
        )
        p.register_document(
            root,
            doc_id,
            rel,
            "test reviewer",
            "test fixture source",
            "Content reviewed for fixture.",
            task if doc_id == "stage" else None,
        )
    return p.ready(root, task, "test reviewer")


def prepared(setup):
    task = start(setup)
    assert documents(setup, task)["status"] == "READY"
    return task


def review(setup, task):
    return {
        "reviewer": "test reviewer",
        "summary": "Synthetic local contract reviewed.",
        "next_step": "New task entry.",
        "limitations": "No actual client or target test.",
        "scope_reviewed": True,
        "accepted_criteria": ["A1"],
        "reviewed_documents": p.load_task(setup[0], task)["selection"]["required"],
        "deployment_status": "not_requested",
    }


@pytest.mark.parametrize(
    "key", list(p.QUESTIONS) + ["change_kind", "write_paths", "acceptance", "checks"]
)
def test_required_answers(setup, key):
    root, home, a = setup
    a.pop(key)
    with pytest.raises((ValueError, TypeError)):
        p.enter(root, a, session_id="s", turn_id="t", user_home=home)


@pytest.mark.parametrize("field", ["checks", "acceptance"])
def test_malformed_contract_record_is_a_controlled_refusal(setup, field):
    root, home, answers = setup
    answers[field] = ["not an object"]
    with pytest.raises(GateError):
        p.enter(root, answers, session_id="s", turn_id="t", user_home=home)


@pytest.mark.parametrize("typ", doc_catalog.TYPES)
def test_selection_types(typ):
    result = doc_catalog.select([typ], [])
    assert set(doc_catalog.BASE) <= set(result["required"])
    assert not set(result["required"]) & set(result["not_applicable"])


@pytest.mark.parametrize("feature", doc_catalog.FEATURES)
def test_selection_features(feature):
    result = doc_catalog.select(["general"], [feature])
    assert doc_catalog.FEATURE_DOCS[feature] <= set(result["required"])


def test_bad_selection():
    with pytest.raises(ValueError):
        doc_catalog.select(["not-a-type"], [])
    with pytest.raises(ValueError):
        doc_catalog.select(["general"], ["unknown"])


def test_ready_requires_registered_real_docs(setup):
    task = start(setup)
    assert p.ready(setup[0], task, "reviewer")["status"] == "BLOCKED"


def test_draft_rejected(setup):
    start(setup)
    with pytest.raises(ValueError):
        p.register_document(
            setup[0],
            "dossier",
            "docs/agentos/DOSSIER.md",
            "reviewer",
            "fixture",
            "draft",
        )


def test_stage_wrong_task_rejected(setup):
    task = start(setup)
    path = setup[0] / "docs/agentos/x.md"
    path.write_text("Actual facts without the task identity. " * 10)
    with pytest.raises(ValueError):
        p.register_document(
            setup[0], "stage", "docs/agentos/x.md", "reviewer", "fixture", "stage", task
        )


def test_stale_docs_block(setup):
    task = prepared(setup)
    (setup[0] / "docs/agentos/reviewed-dossier.md").write_text("new facts " * 30)
    assert p.check_ready(setup[0], task)["status"] == "BLOCKED"


def test_missing_checks_block(setup):
    task = prepared(setup)
    assert p.assess(setup[0], task)["status"] == "BLOCKED"


def test_current_evidence_and_close(setup):
    task = prepared(setup)
    root = setup[0]
    assert p.run_check(root, task, "unit")["status"] == "PASS"
    assert p.close(root, task, review(setup, task))["status"] == "CLOSED"
    assert (
        hooks.handle(
            {
                "hook_event_name": "Stop",
                "session_id": "s",
                "turn_id": "t",
                "cwd": str(root),
            },
            setup[1],
        )
        == {}
    )


def test_stale_source_invalidates_pass(setup):
    task = prepared(setup)
    p.run_check(setup[0], task, "unit")
    (setup[0] / "code.py").write_text("x=2\n")
    assert p.assess(setup[0], task)["status"] == "BLOCKED"


def test_ready_cannot_replace_approved_source_baseline(setup):
    task = prepared(setup)
    root = setup[0]
    baseline = p.load_task(root, task)["ready"]
    (root / "unapproved.py").write_text("changed\n")
    with pytest.raises(GateError, match="ready_invalid_state"):
        p.ready(root, task, "second reviewer")
    assert p.load_task(root, task)["ready"] == baseline
    assert p.assess(root, task)["status"] == "BLOCKED"


def test_out_of_scope_even_with_fresh_check(setup):
    task = prepared(setup)
    (setup[0] / "unapproved.py").write_text("x=1\n")
    p.run_check(setup[0], task, "unit")
    assert p.assess(setup[0], task)["out_of_scope"] == ["unapproved.py"]


def test_approved_change_passes(setup):
    task = prepared(setup)
    (setup[0] / "code.py").write_text("x=1\n")
    p.run_check(setup[0], task, "unit")
    assert p.assess(setup[0], task)["status"] == "PASS"


def test_mutating_check_fails(setup):
    setup[2]["checks"][0]["argv"] = [
        sys.executable,
        "-c",
        'from pathlib import Path;Path("code.py").write_text("x=1")',
    ]
    task = prepared(setup)
    assert p.run_check(setup[0], task, "unit")["status"] == "FAIL"


def test_timeout_fails(setup):
    setup[2]["checks"][0].update(
        argv=[sys.executable, "-c", "import time;time.sleep(2)"], timeout=1
    )
    task = prepared(setup)
    r = p.run_check(setup[0], task, "unit")
    assert r["return_code"] == 124 and r["status"] == "FAIL"


def test_missing_command_fails(setup):
    setup[2]["checks"][0]["argv"] = ["/this-command-does-not-exist/agentos-test"]
    task = prepared(setup)
    assert p.run_check(setup[0], task, "unit")["return_code"] == 127


def test_tampered_log_fails(setup):
    task = prepared(setup)
    r = p.run_check(setup[0], task, "unit")
    (setup[0] / r["log"]).write_text("tampered")
    assert p.assess(setup[0], task)["status"] == "BLOCKED"


def test_stale_time_fails(setup):
    task = prepared(setup)
    r = p.run_check(setup[0], task, "unit")
    r["finished_at"] = "2000-01-01T00:00:00+00:00"
    atomic_json(setup[0] / f".agentos/tasks/{task}/evidence/{r['id']}.json", r)
    assert p.assess(setup[0], task)["status"] == "BLOCKED"


def test_changed_scope_blocks(setup):
    task = prepared(setup)
    t = p.load_task(setup[0], task)
    t["answers"]["scope_in"] = "Changed scope"
    atomic_json(p.task_path(setup[0], task), t)
    assert p.check_ready(setup[0], task)["status"] == "BLOCKED"


def test_review_cannot_claim_live(setup):
    task = prepared(setup)
    p.run_check(setup[0], task, "unit")
    r = review(setup, task)
    r["deployment_status"] = "live_verified"
    with pytest.raises(ValueError):
        p.close(setup[0], task, r)


@pytest.mark.parametrize(
    "field,value",
    [("scope_reviewed", False), ("accepted_criteria", []), ("reviewed_documents", [])],
)
def test_semantic_review_required(setup, field, value):
    task = prepared(setup)
    p.run_check(setup[0], task, "unit")
    r = review(setup, task)
    r[field] = value
    with pytest.raises(ValueError):
        p.close(setup[0], task, r)


def test_checkpoint_is_not_complete(setup):
    task = start(setup)
    r = p.checkpoint(setup[0], task, "Evidence pending", "Get actual evidence")
    assert r["complete"] is False


def test_resume_resets_gate(setup):
    task = prepared(setup)
    p.run_check(setup[0], task, "unit")
    p.checkpoint(setup[0], task, "Pause fixture", "Resume fixture")
    p.next_turn(setup[0], setup[1], session_id="s", previous_turn="t", turn_id="t2", task_id=task)
    p.enter(
        setup[0],
        setup[2],
        session_id="s",
        turn_id="t2",
        user_home=setup[1],
        resume_task=task,
    )
    t = p.load_task(setup[0], task)
    assert t["revision"] == 2 and t["receipts"] == [] and "ready" not in t


def test_standalone_cli_next_turn_resumes_checkpoint_without_hook_claim(setup):
    root, home, answers = setup
    task = start(setup)
    assert read_json(turns.turn_path(home, "s"))["hook_seen"] is False
    assert documents(setup, task)["status"] == "READY"
    p.checkpoint(root, task, "Synthetic pause", "Continue in a new CLI turn")
    next_result, code = p.command(
        [
            "next-turn",
            "--root",
            str(root),
            "--session",
            "s",
            "--from-turn",
            "t",
            "--turn",
            "t2",
            "--task",
            task,
        ],
        home,
    )
    assert code == 0 and next_result["status"] == "INTAKE_REQUIRED"
    assert read_json(turns.turn_path(home, "s"))["hook_seen"] is False
    answers_file = root / "answers.json"
    atomic_json(answers_file, answers)
    resumed, code = p.command(
        [
            "enter",
            "--root",
            str(root),
            "--session",
            "s",
            "--turn",
            "t2",
            "--resume-task",
            task,
            "--answers",
            str(answers_file),
        ],
        home,
    )
    assert code == 0 and resumed["task_id"] == task
    assert read_json(turns.turn_path(home, "s"))["hook_seen"] is False
    updated = p.load_task(root, task)
    assert updated["status"] == "INTAKE" and "ready" not in updated
    assert updated["revision"] == 2 and updated["receipts"] == []


def test_standalone_cli_next_turn_after_close_starts_new_task(setup):
    root, home, answers = setup
    task = prepared(setup)
    p.run_check(root, task, "unit")
    p.close(root, task, review(setup, task))
    p.next_turn(
        root, home, session_id="s", previous_turn="t", turn_id="t2", task_id=task
    )
    result = p.enter(root, answers, session_id="s", turn_id="t2", user_home=home)
    assert result["task_id"] != task
    assert p.load_task(root, task)["status"] == "CLOSED"


def test_standalone_cli_next_turn_refuses_mismatched_receipt(setup):
    root, home, _ = setup
    task = start(setup)
    p.checkpoint(root, task, "Synthetic pause", "Continue after review")
    path = turns.turn_path(home, "s")
    before = path.read_bytes()
    for previous, new_task in [("wrong", task), ("t", "task-wrong")]:
        with pytest.raises(GateError):
            p.next_turn(root, home, session_id="s", previous_turn=previous,
                        turn_id="t2", task_id=new_task)
        assert path.read_bytes() == before
    with pytest.raises(GateError, match="standalone_turn_transition_mismatch"):
        turns.advance_standalone_turn(home, "s", "t", "t2", root.parent / "different", task)
    assert path.read_bytes() == before


def test_active_task_conflict(setup):
    start(setup)
    with pytest.raises(ValueError):
        start(setup)


def test_turn_mismatch_no_task_side_effect(setup):
    task = start(setup)
    before = filemap(setup[0])
    with pytest.raises(ValueError):
        p.enter(setup[0], setup[2], session_id="s", turn_id="wrong", user_home=setup[1], resume_task=task)
    assert filemap(setup[0]) == before


def test_observation_no_project_writes(tmp_path):
    root = tmp_path / "readonly"
    root.mkdir()
    (root / "README.md").write_text("Actual fixture observation source.")
    home = tmp_path / "user"
    before = filemap(root)
    a = {
        k: "Read-only fixture source inspection, not a deployment."
        for k in (
            "objective",
            "why",
            "outcome",
            "authority",
            "summary",
            "limitations",
            "next_step",
        )
    }
    a["sources"] = ["README.md"]
    result = observation.record(root, a, home, "s", "t")
    assert filemap(root) == before
    receipt = read_json(home / result["receipt_path"])
    observation.verify(root, receipt)
    assert not turns.turn_path(home, "s").exists()
    (root / "README.md").write_text("changed")
    with pytest.raises(GateError, match="observation_source_changed"):
        observation.verify(root, receipt)


@pytest.mark.parametrize(
    "rel", ["../escape", "/absolute", "x/../../escape", "bad\\file"]
)
def test_path_escape(rel, tmp_path):
    with pytest.raises(ValueError):
        within(tmp_path, rel)


def test_symlink_file_refused(tmp_path):
    (tmp_path / "real").write_text("data")
    (tmp_path / "sym").symlink_to(tmp_path / "real")
    with pytest.raises(ValueError):
        within(tmp_path, "sym")


def test_lock_conflict(tmp_path):
    with lock(tmp_path / "lock"), pytest.raises(ValueError), lock(tmp_path / "lock"):
        pass


def overlay_source(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    atomic_json(
        src / "overlay.json",
        {"schema": overlay.SCHEMA, "version": "1.0.0", "overlay_id": "fixture"},
    )
    atomic_json(src / "config.json", default_config())
    atomic_json(
        src / "OVERLAY_MANIFEST.json",
        {"schema": "agentos.overlay-manifest/v1", "files": filemap(src)},
    )
    return src


def test_overlay_dry_apply_idempotent(tmp_path):
    src = overlay_source(tmp_path)
    dest = tmp_path / "user"
    assert overlay.import_overlay(src, dest)["status"] == "READY" and not dest.exists()
    assert overlay.import_overlay(src, dest, apply=True)["status"] == "IMPORTED"
    assert overlay.import_overlay(src, dest, apply=True)["created"] == []


def test_overlay_conflict_no_overwrite(tmp_path):
    src = overlay_source(tmp_path)
    dest = tmp_path / "user"
    dest.mkdir()
    (dest / "config.json").write_text("original")
    assert overlay.import_overlay(src, dest, apply=True)["status"] == "CONFLICT"
    assert (
        not (dest / "overlay.json").exists()
        and (dest / "config.json").read_text() == "original"
    )


def test_create_only_publish_failure_leaves_no_partial_target(tmp_path, monkeypatch):
    target = tmp_path / "user" / "config.json"

    def fail_sync(_fd):
        raise OSError("injected write failure")

    monkeypatch.setattr(safeio.os, "fsync", fail_sync)
    with pytest.raises(OSError, match="injected write failure"):
        safeio.create_only_bytes(target, b"complete contents")
    assert not target.exists()
    assert list(target.parent.iterdir()) == []


def test_create_only_publish_never_overwrites_raced_target(tmp_path, monkeypatch):
    target = tmp_path / "user" / "config.json"
    original_link = safeio.os.link

    def concurrent_create(source, destination):
        Path(destination).write_bytes(b"existing user bytes")
        original_link(source, destination)

    monkeypatch.setattr(safeio.os, "link", concurrent_create)
    with pytest.raises(FileExistsError):
        safeio.create_only_bytes(target, b"new bytes")
    assert target.read_bytes() == b"existing user bytes"
    assert list(target.parent.iterdir()) == [target]


def test_overlay_bad_hash(tmp_path):
    src = overlay_source(tmp_path)
    (src / "config.json").write_text("{}")
    with pytest.raises(ValueError):
        overlay.inspect_import(src, tmp_path / "user")


def test_overlay_unlisted_file(tmp_path):
    src = overlay_source(tmp_path)
    (src / "extra.txt").write_text("unlisted")
    with pytest.raises(ValueError):
        overlay.inspect_import(src, tmp_path / "user")


def test_overlay_root_file_cannot_be_imported_as_directory(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    atomic_json(src / "overlay.json", {"schema": overlay.SCHEMA, "version": "1.0.0"})
    (src / "config.json").mkdir()
    (src / "config.json" / "nested").write_text("invalid layout")
    atomic_json(
        src / "OVERLAY_MANIFEST.json",
        {"schema": "agentos.overlay-manifest/v1", "files": filemap(src)},
    )
    with pytest.raises(GateError, match="overlay_root_file_cannot_be_directory"):
        overlay.inspect_import(src, tmp_path / "user")


def test_overlay_future_schema(tmp_path):
    home = tmp_path / "u"
    home.mkdir()
    atomic_json(home / "overlay.json", {"schema": "agentos.user-overlay/v99"})
    with pytest.raises(ValueError):
        overlay.metadata(home)


def test_config_backup_preserves_unknown(tmp_path):
    home = tmp_path / "user"
    home.mkdir()
    old = {"schema": "agent-os.community-config/v1", "owner_custom": {"retain": True}}
    atomic_json(home / "config.json", old)
    before = (home / "config.json").read_bytes()
    result = overlay.migrate_config(home, apply=True)
    assert read_json(home / "config.json")["owner_custom"] == {"retain": True}
    assert (home / result["backup"]).read_bytes() == before


def test_ambiguous_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTOS_USER_HOME", str(tmp_path / "a"))
    monkeypatch.setenv("AGENT_OS_HOME", str(tmp_path / "b"))
    with pytest.raises(ValueError):
        AgentOSPaths.discover()
    assert AgentOSPaths.discover(tmp_path / "explicit").home == tmp_path / "explicit"


def test_nested_core_user_refused(tmp_path):
    with pytest.raises(ValueError):
        overlay.validate_roots(tmp_path / "core/u", tmp_path / "core")
    with pytest.raises(ValueError):
        overlay.validate_roots(tmp_path, tmp_path / "core")


def test_user_symlink_refused(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "sym").symlink_to(tmp_path / "real", target_is_directory=True)
    with pytest.raises(ValueError):
        AgentOSPaths.discover(tmp_path / "sym")


def test_integration_preserves_user_content(tmp_path):
    ch = tmp_path / "codex"
    ch.mkdir()
    sh = tmp_path / "skills"
    home = tmp_path / "user"
    (ch / "AGENTS.override.md").write_text("Existing owner policy.\n")
    atomic_json(
        ch / "hooks.json",
        {
            "hooks": {
                "Stop": [
                    {"hooks": [{"type": "command", "command": "existing-safe-hook"}]}
                ]
            }
        },
    )
    r = integration.install(ch, sh, home)
    assert not (sh / "agentos-project-entry").exists()
    r = integration.install(ch, sh, home, apply=True)
    assert r["hook_trust_changed"] is False
    assert "Existing owner policy." in (ch / "AGENTS.override.md").read_text()
    guide = Path(integration.__file__).parent / "resources/docs/HANDOFF_DISCOVERY.md"
    assert guide.is_file()
    assert str(guide) in (ch / "AGENTS.override.md").read_text()
    assert not (ch / "AGENTS.md").exists()
    assert not (ch / "config.toml").exists()
    assert "existing-safe-hook" in (ch / "hooks.json").read_text()
    before = (ch / "hooks.json").read_bytes()
    integration.install(ch, sh, home, apply=True)
    assert (ch / "hooks.json").read_bytes() == before
    assert "agentosManaged" not in before.decode()


def test_integration_modified_skill_conflict(tmp_path):
    ch = tmp_path / "codex"
    sh = tmp_path / "skills"
    home = tmp_path / "user"
    integration.install(ch, sh, home, apply=True)
    (sh / "agentos-project-entry/SKILL.md").write_text(
        "Custom owner skill; must preserve."
    )
    assert integration.install(ch, sh, home, apply=True)["status"] == "CONFLICT"


def test_dispatch_missing_turn_rejected(monkeypatch):
    monkeypatch.delenv("AGENTOS_SESSION_ID", raising=False)
    monkeypatch.delenv("AGENTOS_TURN_ID", raising=False)
    with pytest.raises(ValueError):
        dispatch_gate.claim("request")


def test_dispatch_exact_one_shot(setup, monkeypatch):
    prepared(setup)
    monkeypatch.setenv("AGENTOS_USER_HOME", str(setup[1]))
    monkeypatch.delenv("AGENT_OS_HOME", raising=False)
    monkeypatch.setenv("AGENTOS_SESSION_ID", "s")
    monkeypatch.setenv("AGENTOS_TURN_ID", "t")
    with pytest.raises(ValueError):
        dispatch_gate.claim("wrong request", workspace=setup[0])
    dispatch_gate.claim(setup[2]["objective"], workspace=setup[0])
    with pytest.raises(ValueError):
        dispatch_gate.claim(setup[2]["objective"], workspace=setup[0])


def test_all_reference_schemas_are_valid():
    import jsonschema

    resources = Path(p.__file__).parent / "resources/schemas"
    for path in resources.glob("*.json"):
        jsonschema.Draft202012Validator.check_schema(read_json(path))


def test_actual_project_matches_schema(setup):
    import jsonschema

    schema = read_json(
        Path(p.__file__).parent / "resources/schemas/project.schema.json"
    )
    jsonschema.validate(p.load_project(setup[0]), schema)


def test_duplicate_json_key_refused(tmp_path):
    path = tmp_path / "x.json"
    path.write_text('{"schema":1,"schema":2}')
    with pytest.raises(ValueError):
        read_json(path)


def test_register_code_does_not_hide_source(setup):
    prepared(setup)
    root = setup[0]
    (root / "code.py").write_text(
        "# Source must not disappear when registered as documentation.\n" * 5
    )
    p.register_document(
        root,
        "dossier",
        "code.py",
        "reviewer",
        "fixture",
        "Check registered code cannot hide source",
    )
    assert "code.py" in p.source_snapshot(root)["files"]


def test_latest_failure_supersedes_pass(setup):
    setup[2]["checks"][0]["argv"] = [
        sys.executable,
        "-c",
        'import os,sys;sys.exit(int(os.environ.get("AGENTOS_FIXTURE_FAIL","0")))',
    ]
    task = prepared(setup)
    assert p.run_check(setup[0], task, "unit")["status"] == "PASS"
    os.environ["AGENTOS_FIXTURE_FAIL"] = "1"
    try:
        assert p.run_check(setup[0], task, "unit")["status"] == "FAIL"
    finally:
        os.environ.pop("AGENTOS_FIXTURE_FAIL", None)
    assert p.assess(setup[0], task)["status"] == "BLOCKED"


def test_mcp_rejects_wrong_input_type():
    from agent_os.mcp_server import _call, response

    assert _call("agentos_normalize_task", {"objective": 123})["isError"] is True
    assert _call("agentos_select_documents", {"types": [{}]})["isError"] is True
    assert (
        response(
            {
                "id": 1,
                "method": "tools/call",
                "params": {"name": "agentos_doctor", "arguments": []},
            }
        )["result"]["isError"]
        is True
    )


def test_config_symlink_refused(tmp_path):
    root = tmp_path / "user"
    root.mkdir()
    outside = tmp_path / "outside.json"
    atomic_json(outside, default_config())
    (root / "config.json").symlink_to(outside)
    from agent_os.config import load_config

    with pytest.raises(ValueError):
        load_config(AgentOSPaths.discover(root))


def test_core_cannot_be_overlay():
    source = Path(p.__file__).resolve().parents[2]
    with pytest.raises(ValueError):
        AgentOSPaths.discover(source / "user")


def test_closed_task_source_change_blocks_explicit_verification(setup):
    task = prepared(setup)
    p.run_check(setup[0], task, "unit")
    p.close(setup[0], task, review(setup, task))
    assert p.verify_closeout(setup[0], task)["status"] == "PASS"
    (setup[0] / "code.py").write_text("changed")
    result = p.verify_closeout(setup[0], task)
    assert result["status"] == "BLOCKED"
    assert "source_changed_after_close" in result["errors"]


def test_installer_root_separation_and_wheel_hash(tmp_path):
    script = Path(__file__).resolve().parents[1] / "tools/install.py"
    spec = importlib.util.spec_from_file_location("agentos_installer_fixture", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pytest.raises(ValueError):
        mod.separate(tmp_path / "core", tmp_path / "core/user")
    wheel = tmp_path / "fake.whl"
    wheel.write_bytes(b"synthetic wheel fixture, not installable")
    args = mod.parser().parse_args(
        [
            "install",
            "--wheel",
            str(wheel),
            "--sha256",
            "0" * 64,
            "--version",
            "0.5.0-beta.4",
            "--core-home",
            str(tmp_path / "core"),
            "--user-home",
            str(tmp_path / "user"),
        ]
    )
    with pytest.raises(ValueError):
        mod.execute(args)
    assert not (tmp_path / "core").exists()


@pytest.mark.parametrize(
    ("name", "contents"),
    [
        ("overlay.json", '{"schema":"agentos.user-overlay/v99"}'),
        ("config.json", '{"schema":"agent-os.community-config/v99"}'),
        (
            "config.json",
            '{"schema":"agent-os.community-config/v5","schema":"agent-os.community-config/v5"}',
        ),
    ],
)
def test_installer_refuses_incompatible_user_metadata_before_activation(
    tmp_path, name, contents
):
    script = Path(__file__).resolve().parents[1] / "tools/install.py"
    spec = importlib.util.spec_from_file_location("agentos_installer_fixture", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    core = tmp_path / "core"
    user = tmp_path / "user"
    user.mkdir()
    (user / name).write_text(contents)
    wheel = tmp_path / "synthetic.whl"
    wheel.write_bytes(b"fixture wheel bytes")
    release_id = "0.0.0-fixture-" + mod.digest(wheel)[:12]
    release_dir = core / "releases" / release_id
    release_dir.mkdir(parents=True)
    (release_dir / wheel.name).write_bytes(wheel.read_bytes())
    mod.write_json(
        release_dir / "INSTALL.json",
        {
            "schema": "agentos.install/v2",
            "version": "0.0.0-fixture",
            "wheel_name": wheel.name,
            "wheel_sha256": mod.digest(wheel),
            "script_sha256": {"agentos": "0" * 64},
            "overlay_schema": 1,
            "config_schema": "agent-os.community-config/v5",
        },
    )
    (core / "current").symlink_to("releases/" + release_id)
    original_pointer = os.readlink(core / "current")
    install_args = mod.parser().parse_args(
        [
            "install",
            "--wheel",
            str(wheel),
            "--sha256",
            mod.digest(wheel),
            "--version",
            "0.5.0-beta.4",
            "--core-home",
            str(core),
            "--user-home",
            str(user),
            "--apply",
            "--expected-current",
            release_id,
        ]
    )
    rollback_args = mod.parser().parse_args(
        [
            "rollback",
            "--release-id",
            release_id,
            "--core-home",
            str(core),
            "--user-home",
            str(user),
            "--apply",
            "--expected-current",
            release_id,
        ]
    )
    for args in (install_args, rollback_args):
        with pytest.raises(
            mod.InstallError,
            match="user_.*schema_unsupported|user_metadata_duplicate_key",
        ):
            mod.execute(args)
        assert os.readlink(core / "current") == original_pointer
        assert not (core / ".install.lock").exists()


def test_installer_accepts_legacy_config_without_mutation(tmp_path):
    script = Path(__file__).resolve().parents[1] / "tools/install.py"
    spec = importlib.util.spec_from_file_location("agentos_installer_fixture", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    user = tmp_path / "user"
    user.mkdir()
    config = user / "config.json"
    config.write_bytes(b'{"schema":"agent-os.community-config/v4","owner_key":true}\n')
    before = config.read_bytes()
    mod.check_user_compatibility(
        user, {"overlay_schema": 1, "config_schema": "agent-os.community-config/v5"}
    )
    assert config.read_bytes() == before


def test_installer_refuses_symlinked_user_metadata(tmp_path):
    script = Path(__file__).resolve().parents[1] / "tools/install.py"
    spec = importlib.util.spec_from_file_location("agentos_installer_fixture", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    user = tmp_path / "user"
    user.mkdir()
    (user / "overlay.json").symlink_to(tmp_path / "absent")
    with pytest.raises(mod.InstallError, match="user_metadata_symlink_refused"):
        mod.check_user_compatibility(
            user, {"overlay_schema": 1, "config_schema": "agent-os.community-config/v5"}
        )



def test_installed_canon_matches_maintained_docs():
    root = Path(__file__).resolve().parents[1]
    for doc in (root / "docs").glob("*.md"):
        assert (
            root / "src/agent_os/resources/docs" / doc.name
        ).read_bytes() == doc.read_bytes()
