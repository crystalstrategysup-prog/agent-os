"""No-hook regressions A-F. All mutations are temporary fixture writes, not host setup."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_foundation import documents, prepared, review, start
from test_foundation import setup as foundation_setup

from agent_os import (
    foundation_cli,
    hooks,
    integration,
    observation,
    safeio,
    turns,
    workflow,
)
from agent_os import project as p
from agent_os.safeio import GateError, atomic_json, filemap, read_json, read_json_input

setup = foundation_setup


def cli(tmp_path, *args, payload="", home=None):
    env = dict(os.environ, PYTHONPATH=str(Path(p.__file__).resolve().parents[1]), PYTHONDONTWRITEBYTECODE="1", AGENTOS_USER_HOME=str(home or tmp_path / "overlay"))
    return subprocess.run(
        [sys.executable, "-m", "agent_os", *args], input=payload,
        text=True, capture_output=True, cwd=tmp_path, env=env, timeout=20, check=False,
    )


@pytest.mark.parametrize("kind", ["question", "search", "audit", "discovery"])
def test_A_fast_path_is_stateless_and_needs_no_overlay_or_project(tmp_path, kind):
    home = tmp_path / "broken-overlay"
    home.mkdir()
    (home / "config.json").write_text("{invalid JSON")
    before = filemap(tmp_path)
    result = cli(tmp_path, "workflow", "route", "--kind", kind, home=home)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["mode"] == "FAST_PATH"
    assert value["intake_required"] is False
    assert value["closeout_required"] is False
    assert value["external_authority_granted"] is False
    assert value["writes"] == []
    assert filemap(tmp_path) == before


@pytest.mark.parametrize("kind", workflow.KINDS)
def test_E_read_labels_do_not_hide_declared_local_changes(kind):
    result = workflow.route(kind, ["local-project-write"])
    assert result["mode"] == "DOCUMENTATION_FIRST"
    assert result["intake_required"] is True
    assert result["documentation_before_product_writes"] is True
    assert result["product_writes_authorized"] is False


@pytest.mark.parametrize("effect", workflow.TARGET_EFFECTS)
def test_E_each_target_effect_requires_separate_authority(effect):
    result = workflow.route("audit", [effect])
    assert result["status"] == "BLOCKED"
    assert result["target_gates_required"] == [effect]
    assert result["external_authority_granted"] is False
    # This is a declared route, not a claim that arbitrary subprocesses are sandboxed.


def test_E_cli_target_gate_is_controlled_refusal(tmp_path):
    before = filemap(tmp_path)
    result = cli(tmp_path, "workflow", "route", "--kind", "project-change", "--effect", "deploy")
    assert result.returncode == 2
    assert json.loads(result.stdout)["mode"] == "TARGET_AUTHORITY_REQUIRED"
    assert filemap(tmp_path) == before


@pytest.mark.parametrize("effects", ["deploy", ["unknown"], [None]])
def test_E_router_rejects_unknown_effects(effects):
    with pytest.raises(GateError):
        workflow.route("audit", effects)


@pytest.mark.parametrize("event", ["SessionStart", "UserPromptSubmit", "PreToolUse", "Stop", "unknown"])
@pytest.mark.parametrize("flag", [None, False, True])
def test_F_retired_callbacks_never_block_grant_or_write(tmp_path, event, flag):
    before = filemap(tmp_path)
    payload = {"hook_event_name": event, "cwd": str(tmp_path), "stop_hook_active": flag}
    for _ in range(3):
        assert hooks.handle(payload, tmp_path / "absent-home") == {}
    assert filemap(tmp_path) == before


@pytest.mark.parametrize("payload", [None, [], "broken", 123])
def test_F_retired_handle_accepts_even_invalid_legacy_shapes(tmp_path, payload):
    assert hooks.handle(payload, tmp_path / "absent-home") == {}
    assert list(tmp_path.iterdir()) == []


def test_F_retired_main_does_not_read_stdin_or_discover_home(tmp_path, monkeypatch, capsys):
    class Unreadable:
        def read(self, *args):
            raise AssertionError("retired hook must not read stdin")
    monkeypatch.setattr(sys, "stdin", Unreadable())
    from agent_os.config import AgentOSPaths
    monkeypatch.setattr(AgentOSPaths, "discover", lambda *a, **k: pytest.fail("home discovery"))
    assert foundation_cli.dispatch(["hook"]) == 0
    assert capsys.readouterr().out == "{}\n"
    assert not list(tmp_path.iterdir())


def test_F_stale_hook_cli_with_malformed_input_is_noop(tmp_path):
    before = filemap(tmp_path)
    result = cli(tmp_path, "hook", payload="this is not JSON")
    assert result.returncode == 0
    assert result.stdout == "{}\n"
    assert filemap(tmp_path) == before


@pytest.mark.parametrize("existing_hook", [None, b'{"hooks":{"Other":[{"cmd":"unrelated"}]}}', b'broken JSON'])
def test_F_integration_never_creates_restores_or_rewrites_hooks(tmp_path, existing_hook):
    codex = tmp_path / "codex"
    codex.mkdir()
    config = codex / "config.toml"
    config.write_text('[features]\nhooks = false\n# preserve unrelated config\n')
    hook_file = codex / "hooks.json"
    if existing_hook is not None:
        hook_file.write_bytes(existing_hook)
    config_before = config.read_bytes()
    (codex / "AGENTS.override.md").write_text("Owner-specific narrower host boundaries.\n")
    skills, home = tmp_path / "skills", tmp_path / "user"
    before = filemap(tmp_path)
    plan = integration.install(codex, skills, home)
    assert plan["status"] == "PLANNED"
    assert plan["required_config"] == {}
    assert all(not x.endswith("hooks.json") for x in plan["files"])
    assert filemap(tmp_path) == before
    result = integration.install(codex, skills, home, apply=True)
    assert result["status"] == "INSTALLED_MANUAL_WORKFLOW"
    assert result["hook_files_changed"] is False
    assert config.read_bytes() == config_before
    assert (hook_file.read_bytes() if hook_file.exists() else None) == existing_hook
    text = (codex / "AGENTS.override.md").read_text()
    assert text.startswith("Owner-specific narrower host boundaries.")
    assert "Native hooks are DISABLED" in text
    assert "Keep inherited project AGENTS.md concise" in text
    assert "not a size gate or prerequisite for read-only work" in text
    assert "A read-only request does not authorize rewriting instructions" in text
    assert "Read detailed knowledge on demand" in text
    assert not (codex / "AGENTS.md").exists()
    agent_bytes = (codex / "AGENTS.override.md").read_bytes()
    integration.install(codex, skills, home, apply=True)
    assert (codex / "AGENTS.override.md").read_bytes() == agent_bytes
    assert (hook_file.read_bytes() if hook_file.exists() else None) == existing_hook


def test_F_long_owner_agents_remains_intact_without_size_gate(tmp_path):
    codex = tmp_path / "codex"
    codex.mkdir()
    agents = codex / "AGENTS.md"
    owner_text = "Owner instructions.  \n" + "Project context.\n" * 800 + "trailing spaces  "
    agents.write_text(owner_text)

    result = integration.install(codex, tmp_path / "skills", tmp_path / "user", apply=True)

    assert result["status"] == "INSTALLED_MANUAL_WORKFLOW"
    assert agents.read_bytes().startswith(owner_text.encode())
    assert "not a size gate or prerequisite for read-only work" in agents.read_text()
    assert result["hook_files_changed"] is False
    integrated = agents.read_bytes()
    integration.install(codex, tmp_path / "skills", tmp_path / "user", apply=True)
    assert agents.read_bytes() == integrated


def test_F_integration_uses_selected_codex_home(tmp_path, monkeypatch):
    default = tmp_path / "default"
    selected = tmp_path / "selected"
    explicit = tmp_path / "explicit"
    monkeypatch.setattr(integration.Path, "home", lambda: default)
    monkeypatch.setenv("CODEX_HOME", str(selected))
    result, code = integration.command(["codex"], tmp_path / "user")
    assert code == 0
    assert result["agents_selected"] == str(selected / "AGENTS.md")
    result, code = integration.command(
        ["codex", "--codex-home", str(explicit)], tmp_path / "user"
    )
    assert code == 0
    assert result["agents_selected"] == str(explicit / "AGENTS.md")
    monkeypatch.setenv("CODEX_HOME", "")
    result, code = integration.command(["codex"], tmp_path / "user")
    assert code == 0
    assert result["agents_selected"] == str(default / ".codex/AGENTS.md")
    monkeypatch.setenv("CODEX_HOME", "relative/codex")
    with pytest.raises(p.GateError, match="codex_home_absolute_required"):
        integration.command(["codex"], tmp_path / "user")


@pytest.mark.parametrize("empty_override", [b"", b"  \r\n\t"])
def test_F_empty_override_does_not_shadow_owner_agents(tmp_path, empty_override):
    codex = tmp_path / "codex"
    codex.mkdir()
    base = codex / "AGENTS.md"
    base.write_bytes(b"Owner limits stay effective.\n")
    override = codex / "AGENTS.override.md"
    override.write_bytes(empty_override)
    result = integration.install(codex, tmp_path / "skills", tmp_path / "user", apply=True)
    assert result["agents_selected"] == str(base)
    assert override.read_bytes() == empty_override
    assert base.read_bytes().startswith(b"Owner limits stay effective.\n")


def test_F_integration_preserves_crlf_owner_bytes_and_rejects_reversed_markers(tmp_path):
    codex = tmp_path / "codex"
    codex.mkdir()
    base = codex / "AGENTS.md"
    owner = b"Owner section\r\nSecond line  \r\n"
    base.write_bytes(owner)
    integration.install(codex, tmp_path / "skills", tmp_path / "user", apply=True)
    assert base.read_bytes().startswith(owner)
    base.write_bytes((integration.END + "\n" + integration.START).encode())
    before = base.read_bytes()
    with pytest.raises(p.GateError, match="damaged_managed_agents_block"):
        integration.install(codex, tmp_path / "skills", tmp_path / "user", apply=True)
    assert base.read_bytes() == before


def test_F_file_inventory_rejects_fifo_without_opening_it(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO is unavailable on this platform")
    fifo = tmp_path / "waiting.pipe"
    os.mkfifo(fifo)
    with pytest.raises(GateError, match="regular_inventory_file_required"):
        filemap(tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="Unix sockets require POSIX")
def test_F_file_inventory_rejects_socket(tmp_path):
    import socket
    import tempfile

    with tempfile.TemporaryDirectory(prefix="aos-", dir="/tmp") as short_root:
        endpoint = Path(short_root) / "endpoint.sock"
        server = socket.socket(socket.AF_UNIX)
        try:
            server.bind(str(endpoint))
            with pytest.raises(GateError, match="regular_inventory_file_required"):
                filemap(Path(short_root))
        finally:
            server.close()


@pytest.mark.skipif(os.name != "posix", reason="process-group checks require POSIX")
@pytest.mark.parametrize("parent_sleep,expected_code", [(0, 125), (2, 124)])
def test_F_check_runner_stops_late_descendant_writes(tmp_path, parent_sleep, expected_code):
    late = tmp_path / "late.txt"
    child = (
        "import pathlib,time; time.sleep(1.6); "
        + f"pathlib.Path({str(late)!r}).write_text('late')"
    )
    parent = (
        "import subprocess,sys,time; "
        + f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
        + f"time.sleep({parent_sleep})"
    )
    code, output = p._bounded_check_process(
        [sys.executable, "-c", parent], tmp_path, os.environ.copy(), 1
    )
    assert code == expected_code
    assert "CHECK " in output
    time.sleep(1.8)
    assert not late.exists()


@pytest.mark.skipif(os.name != "posix", reason="process-group checks require POSIX")
def test_F_check_runner_bounds_output_and_launch_failure(tmp_path):
    code, output = p._bounded_check_process(
        [sys.executable, "-c", "print('x' * 5000000)"],
        tmp_path,
        os.environ.copy(),
        5,
    )
    assert code == 125
    assert "CHECK OUTPUT LIMIT" in output
    assert len(output.encode()) <= 200000
    code, output = p._bounded_check_process(
        [str(tmp_path / "missing-command")], tmp_path, os.environ.copy(), 1
    )
    assert code == 127
    assert "CHECK LAUNCH FAILED" in output


def test_B_failed_scaffold_leaves_no_active_or_orphan_task(setup, monkeypatch):
    root, home, answers = setup
    original = p.scaffold

    def fail_after_scaffold(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("synthetic scaffold failure")

    monkeypatch.setattr(p, "scaffold", fail_after_scaffold)
    with pytest.raises(OSError, match="synthetic scaffold failure"):
        p.enter(root, answers, session_id="failed-scaffold", turn_id="t", user_home=home)
    assert p.load_project(root).get("active_task") is None
    assert not list((root / ".agentos/tasks").glob("*/task.json"))
    assert not list((root / "docs/agentos/stages").glob("task-*.md"))


def test_B_failed_turn_bind_restores_project_and_turn(setup, monkeypatch):
    root, home, answers = setup
    original = turns.bind_turn

    def fail_after_bind(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("synthetic turn bind failure")

    monkeypatch.setattr(turns, "bind_turn", fail_after_bind)
    with pytest.raises(OSError, match="synthetic turn bind failure"):
        p.enter(root, answers, session_id="failed-bind", turn_id="t", user_home=home)
    assert p.load_project(root).get("active_task") is None
    assert not list((root / ".agentos/tasks").glob("*/task.json"))
    assert not turns.turn_path(home, "failed-bind").exists()


def test_B_interrupted_enter_recovers_before_new_task(setup, monkeypatch):
    root, home, answers = setup
    original_scaffold = p.scaffold
    original_recovery = p._recover_entry

    def fail_after_scaffold(*args, **kwargs):
        original_scaffold(*args, **kwargs)
        raise OSError("synthetic interruption")

    def interrupted_recovery(*args, **kwargs):
        raise OSError("synthetic process loss")

    monkeypatch.setattr(p, "scaffold", fail_after_scaffold)
    monkeypatch.setattr(p, "_recover_entry", interrupted_recovery)
    with pytest.raises(OSError, match="synthetic process loss"):
        p.enter(root, answers, session_id="interrupted", turn_id="t", user_home=home)
    assert (root / ".agentos/entry-transaction.json").exists()
    monkeypatch.setattr(p, "scaffold", original_scaffold)
    monkeypatch.setattr(p, "_recover_entry", original_recovery)
    with pytest.raises(GateError, match="entry_recovered_retry"):
        p.enter(root, answers, session_id="interrupted", turn_id="t", user_home=home)
    assert p.load_project(root).get("active_task") is None
    assert not list((root / ".agentos/tasks").glob("*/task.json"))
    assert not list((root / "docs/agentos/stages").glob("task-*.md"))
    result = p.enter(root, answers, session_id="interrupted", turn_id="t", user_home=home)
    assert result["status"] == "INTAKE"


def test_B_interrupted_enter_preserves_concurrent_owner_edit(setup, monkeypatch):
    root, home, answers = setup
    original_scaffold = p.scaffold
    original_recovery = p._recover_entry

    def fail_after_scaffold(*args, **kwargs):
        original_scaffold(*args, **kwargs)
        raise OSError("synthetic interruption")

    monkeypatch.setattr(p, "scaffold", fail_after_scaffold)
    monkeypatch.setattr(p, "_recover_entry", lambda *_: (_ for _ in ()).throw(OSError("process loss")))
    with pytest.raises(OSError, match="process loss"):
        p.enter(root, answers, session_id="edited", turn_id="t", user_home=home)
    project_path = root / ".agentos/project.json"
    project_path.write_bytes(project_path.read_bytes() + b"owner edit\n")
    monkeypatch.setattr(p, "_recover_entry", original_recovery)
    with pytest.raises(GateError, match="entry_recovery_conflict"):
        p.enter(root, answers, session_id="edited", turn_id="t", user_home=home)
    assert project_path.read_bytes().endswith(b"owner edit\n")


def test_F_integration_failure_restores_owner_agents_and_omits_success_receipt(
    tmp_path, monkeypatch
):
    codex, skills, home = tmp_path / "codex", tmp_path / "skills", tmp_path / "user"
    codex.mkdir()
    agents = codex / "AGENTS.md"
    owner = b"Owner rules.  \r\n"
    agents.write_bytes(owner)
    write = integration.atomic_bytes

    def fail_first_skill(path, data):
        if skills in path.parents:
            raise OSError("synthetic skill write failure")
        return write(path, data)

    monkeypatch.setattr(integration, "atomic_bytes", fail_first_skill)
    with pytest.raises(OSError, match="synthetic skill write failure"):
        integration.install(codex, skills, home, apply=True)
    assert agents.read_bytes() == owner
    assert not (codex / "agentos-integration.json").exists()
    assert not (home / "state/integration-transaction.json").exists()


@pytest.mark.parametrize("failure_position", ["first", "middle", "receipt"])
def test_F_integration_fault_after_each_phase_rolls_back(tmp_path, monkeypatch, failure_position):
    codex, skills, home = tmp_path / "codex", tmp_path / "skills", tmp_path / "user"
    codex.mkdir()
    agents = codex / "AGENTS.md"
    owner = b"Owner original\n"
    agents.write_bytes(owner)
    planned = integration.install(codex, skills, home)
    failure_at = {"first": 1, "middle": 5, "receipt": len(planned["files"]) + 1}[
        failure_position
    ]
    count = 0
    write = integration.atomic_bytes

    def fail_target_write(path, data):
        nonlocal count
        if codex in path.parents or skills in path.parents:
            count += 1
            if count == failure_at:
                raise OSError("synthetic phase failure")
        return write(path, data)

    monkeypatch.setattr(integration, "atomic_bytes", fail_target_write)
    with pytest.raises(OSError, match="synthetic phase failure"):
        integration.install(codex, skills, home, apply=True)
    assert count >= failure_at
    assert agents.read_bytes() == owner
    assert not (codex / "agentos-integration.json").exists()
    assert filemap(skills) == {}
    assert not (home / "state/integration-transaction.json").exists()


def test_F_integration_interrupted_journal_recovers_without_overwriting_owner_edit(
    tmp_path, monkeypatch
):
    codex, skills, home = tmp_path / "codex", tmp_path / "skills", tmp_path / "user"
    codex.mkdir()
    agents = codex / "AGENTS.md"
    agents.write_bytes(b"Original owner rules.\n")
    write = integration.atomic_bytes

    def fail_first_skill(path, data):
        if skills in path.parents:
            raise OSError("synthetic interruption")
        return write(path, data)

    with monkeypatch.context() as patch:
        patch.setattr(integration, "atomic_bytes", fail_first_skill)
        patch.setattr(
            integration,
            "_recover_transaction",
            lambda *args: (_ for _ in ()).throw(OSError("synthetic recovery interruption")),
        )
        with pytest.raises(OSError, match="synthetic recovery interruption"):
            integration.install(codex, skills, home, apply=True)
    assert (home / "state/integration-transaction.json").exists()
    assert not (codex / "agentos-integration.json").exists()
    assert integration.install(codex, skills, home)["status"] == "RECOVERY_REQUIRED"
    agents.write_bytes(b"New owner edit after interruption.\n")
    with pytest.raises(GateError, match="integration_recovery_conflict"):
        integration.install(codex, skills, home, apply=True)
    assert agents.read_bytes() == b"New owner edit after interruption.\n"
    assert (home / "state/integration-transaction.json").exists()
    journal = read_json(home / "state/integration-transaction.json")
    agent_row = next(row for row in journal["files"] if row["path"] == str(agents))
    assert agent_row["before"] == safeio.sha(b"Original owner rules.\n")
    # The conflict is intentionally left for a human reconciliation.


def test_F_integration_interrupted_journal_can_restore_and_retry(tmp_path, monkeypatch):
    codex, skills, home = tmp_path / "codex", tmp_path / "skills", tmp_path / "user"
    codex.mkdir()
    agents = codex / "AGENTS.md"
    original = b"Owner before interruption.\n"
    agents.write_bytes(original)
    write = integration.atomic_bytes

    def fail_first_skill(path, data):
        if skills in path.parents:
            raise OSError("synthetic interruption")
        return write(path, data)

    with monkeypatch.context() as patch:
        patch.setattr(integration, "atomic_bytes", fail_first_skill)
        patch.setattr(
            integration,
            "_recover_transaction",
            lambda *args: (_ for _ in ()).throw(OSError("synthetic recovery interruption")),
        )
        with pytest.raises(OSError, match="synthetic recovery interruption"):
            integration.install(codex, skills, home, apply=True)
    assert integration.install(codex, skills, home, apply=True)["status"] == "RECOVERED_RETRY"
    assert agents.read_bytes() == original
    assert not (home / "state/integration-transaction.json").exists()
    assert not (codex / "agentos-integration.json").exists()
    assert integration.install(codex, skills, home, apply=True)["status"] == "INSTALLED_MANUAL_WORKFLOW"


def test_F_hook_symlink_is_untouched_by_integration(tmp_path):
    codex = tmp_path / "codex"
    codex.mkdir()
    foreign = tmp_path / "foreign.json"
    foreign.write_text('{"must":"remain"}')
    (codex / "hooks.json").symlink_to(foreign)
    integration.install(codex, tmp_path / "skills", tmp_path / "overlay", apply=True)
    assert (codex / "hooks.json").is_symlink()
    assert foreign.read_text() == '{"must":"remain"}'


def test_B_stdin_project_bootstrap_and_entry(setup, monkeypatch):
    root, home, answers = setup
    fresh = root.parent / "new-project"
    fresh.mkdir()
    context = {k: "Verified local requirement from fixture input." for k in p.CONTEXT_KEYS}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(context)))
    result, code = p.command(["init", "--root", str(fresh), "--name", "New project", "--type", "general", "--context", "-"], home)
    assert code == 0 and result["status"] == "DOCUMENTATION_REQUIRED"
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(answers)))
    result, code = p.command(["enter", "--root", str(fresh), "--session", "s", "--turn", "t", "--answers", "-"], home)
    task = result["task_id"]
    assert code == 0 and result["status"] == "INTAKE"
    assert p.check_ready(fresh, task)["status"] == "BLOCKED"
    assert not (fresh / "answers.json").exists()
    assert not (fresh / "code.py").exists()
    assert documents((fresh, home, answers), task)["status"] == "READY"


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '[1,2]', 'null', '{broken', '"hello"'])
def test_B_bad_stdin_refused_before_writes(tmp_path, monkeypatch, text):
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))
    with pytest.raises((GateError, ValueError)):
        p.command(["enter", "--root", str(tmp_path), "--session", "s", "--turn", "t", "--answers", "-"], tmp_path / "user")
    assert not list(tmp_path.iterdir())


def test_B_stdin_size_limit_and_symlink_safety(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(' ' * (safeio.MAX_JSON + 1)))
    with pytest.raises(GateError):
        read_json_input(Path("-"))
    source = tmp_path / "real.json"
    source.write_text('{"ok":true}')
    linked = tmp_path / "linked.json"
    linked.symlink_to(source)
    with pytest.raises(GateError, match="symlink"):
        read_json_input(linked)
    assert read_json_input(source) == {"ok": True}
    with pytest.raises(GateError):
        read_json_input(tmp_path)


def test_B_approved_real_code_checks_then_stdin_closeout(setup, monkeypatch):
    root, home, answers = setup
    answers["checks"] = [{"id": "unit", "argv": [sys.executable, "-c", "from code import add; assert add(2, 3) == 5; assert add(-1, 1) == 0"], "timeout": 30}]
    task = start(setup)
    assert p.check_ready(root, task)["status"] == "BLOCKED"
    assert documents(setup, task)["status"] == "READY"
    (root / "code.py").write_text("def add(a, b):\n    return a + b\n")
    assert p.run_check(root, task, "unit")["status"] == "PASS"
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(review(setup, task))))
    result, code = p.command(["close", "--root", str(root), "--task", task, "--review", "-"], home)
    assert code == 0 and result["status"] == "CLOSED"
    assert p.verify_closeout(root, task)["status"] == "PASS"


def test_C_existing_undocumented_project_keeps_product_unchanged_until_docs(setup):
    fixture_root, home, answers = setup
    root = fixture_root.parent / "undocumented-existing-project"
    root.mkdir()
    (root / "code.py").write_text("# pre-existing product\ndef value():\n    return 42\n")
    before = filemap(root)
    # Inspect the actual existing source without creating metadata first.
    assert "return 42" in (root / "code.py").read_text()
    assert p.questionnaire(root, user_home=home)["existing_project"] is False
    assert not (root / ".agentos").exists()
    assert filemap(root) == before
    p.initialize(root, "Inspected legacy fixture", ["general"], [], {
        "purpose": "Document and safely change the existing value function.",
        "current_state": "Read code.py: value returns 42; no project docs or metadata.",
        "boundaries": "Local code.py and its required project documentation only.",
        "constraints": "No network, no production, no personal data; preserve source before READY.",
    })
    legacy_setup = (root, home, answers)
    task = start(legacy_setup)
    assert p.ready(root, task, "Reviewer")["status"] == "BLOCKED"
    assert (root / "code.py").read_text().endswith("    return 42\n")
    assert documents(legacy_setup, task)["status"] == "READY"


def test_D_same_scope_reuses_facts_but_not_authority(setup):
    task = prepared(setup)
    root, home, _ = setup
    q = p.questionnaire(root, user_home=home, resume_task=task)
    assert [x["id"] for x in q["questions"]] == ["authority"]
    assert q["additional_required"] == []
    assert "authority" not in q["suggested_answers"]
    assert q["known_context"]
    before = filemap(root)
    with pytest.raises(GateError):
        p.enter(root, {}, session_id="s", turn_id="t", user_home=home, resume_task=task, reuse=True)
    assert filemap(root) == before
    with pytest.raises(GateError, match="scope_changed"):
        p.reuse_answers(root, task, {"objective": "a new scope"})


def test_D_resume_does_not_reinterview_known_facts_and_resets_gate(setup, monkeypatch):
    task = prepared(setup)
    root, home, _ = setup
    p.run_check(root, task, "unit")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"authority": "Current explicit owner authority: local fixture only."})))
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("repeated question for known answer"))
    result, code = p.command(["enter", "--root", str(root), "--session", "s", "--turn", "t", "--resume-task", task, "--reuse-answers", "--interactive", "--answers", "-"], home)
    assert code == 0 and result["task_id"] == task
    value = p.load_task(root, task)
    assert value["revision"] == 2 and value["receipts"] == []
    assert "ready" not in value
    assert p.check_ready(root, task)["status"] == "BLOCKED"


@pytest.mark.parametrize("status", ["INTAKE_REQUIRED", "OBSERVATION_RECORDED"])
def test_F_abandoned_unbound_prompt_does_not_block_new_entry(setup, status):
    _, home, _ = setup
    atomic_json(turns.turn_path(home, "s"), {"schema": "agentos.turn/v1", "session_id": "s", "turn_id": "old", "root": "/different-project", "task_id": None, "status": status, "hook_seen": True})
    task = start(setup)
    receipt = read_json(turns.turn_path(home, "s"))
    assert receipt["task_id"] == task and receipt["turn_id"] == "t"
    assert receipt["hook_seen"] is False


def test_F_legacy_bound_receipt_can_advance_only_after_checkpoint(setup):
    task = start(setup)
    root, home, answers = setup
    receipt = read_json(turns.turn_path(home, "s"))
    receipt["hook_seen"] = True
    atomic_json(turns.turn_path(home, "s"), receipt)
    with pytest.raises(GateError, match="finished_or_checkpointed"):
        p.next_turn(root, home, session_id="s", previous_turn="t", turn_id="next", task_id=task)
    p.checkpoint(root, task, "Explicit migration checkpoint.", "Resume the same local change.")
    result = p.next_turn(root, home, session_id="s", previous_turn="t", turn_id="next", task_id=task)
    assert result["native_hook_proven"] is False
    assert p.enter(root, answers, session_id="s", turn_id="next", user_home=home, resume_task=task)["status"] == "INTAKE"


def test_A_optional_observations_never_overwrite_active_task(setup, monkeypatch):
    task = start(setup)
    root, home, _ = setup
    (root / "source.md").write_text("Actual temporary audit source.")
    obs = {k: "Verified local fixture evidence only." for k in ["objective", "why", "outcome", "authority", "summary", "limitations", "next_step"]}
    obs["sources"] = ["source.md"]
    before = turns.turn_path(home, "s").read_bytes()
    for turn in ["audit1", "audit2"]:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(obs)))
        result, code = p.command(["observe", "--root", str(root), "--session", "s", "--turn", turn, "--answers", "-"], home)
        assert code == 0
        assert result["receipt_path"].startswith("state/observations/")
    assert turns.turn_path(home, "s").read_bytes() == before
    assert len(list((home / "state/observations").glob("*.json"))) == 2
    with pytest.raises(GateError, match="receipt_exists"):
        observation.record(root, obs, home, "s", "audit2")
    assert p.load_task(root, task)["status"] == "INTAKE"


@pytest.mark.parametrize("operation", ["close", "checkpoint", "verify-closeout"])
def test_F_absent_task_does_not_create_fake_state(tmp_path, operation):
    with pytest.raises((GateError, FileNotFoundError)):
        if operation == "close":
            p.close(tmp_path, "task-missing", {})
        elif operation == "checkpoint":
            p.checkpoint(tmp_path, "task-missing", "Pre-entry failure.", "Report directly.")
        else:
            p.verify_closeout(tmp_path, "task-missing")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("tamper", ["docs", "log"])
def test_F_current_closeout_verification_detects_tampering(setup, tamper):
    task = prepared(setup)
    root, _, _ = setup
    p.run_check(root, task, "unit")
    assert p.close(root, task, review(setup, task))["status"] == "CLOSED"
    before = filemap(root)
    assert p.verify_closeout(root, task)["status"] == "PASS"
    assert filemap(root) == before
    if tamper == "docs":
        (root / "docs/agentos/reviewed-dossier.md").write_text("Changed after close " * 30)
    else:
        value = p.load_task(root, task)
        receipt_id = value["receipts"][-1]
        (root / f".agentos/tasks/{task}/evidence/{receipt_id}.log").write_text("FORGED PASS")
    assert p.verify_closeout(root, task)["status"] == "BLOCKED"
