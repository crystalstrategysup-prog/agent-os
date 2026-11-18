"""Actual guidance bytes through entry, continuation, CLI and integration.

These tests prove loading/binding, not fresh-session reasoning or host adoption.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from agent_os import cli, context_gate, integration, workflow
from agent_os import engineering_guidance as guidance
from agent_os.config import AgentOSPaths
from agent_os.safeio import GateError, sha

ROOT = Path(__file__).resolve().parents[1]


def request(purpose="project-change"):
    return {"schema": "agentos.context-request/v1", "session_id": "synthetic-session",
            "turn_id": "synthetic-turn", "purpose": purpose,
            "profile_keys": [], "index_keys": [], "goal": {
                "original": "Repair the local list service",
                "scope": "Disposable synthetic fixture only",
                "acceptance": ["All local requests return the expected records"],
                "known_answers": {"target": "isolated local fixture"},
                "authority_ref": "current-synthetic-test-task",
                "source_ref": "synthetic-test-input"}}


def body(raw):
    return raw.decode().split(guidance.START, 1)[1].split(guidance.END, 1)[0].strip()


def assert_actual(result, raw):
    expected = body(raw)
    assert result["content"] == expected
    assert result["content_sha256"] == sha(expected.encode())
    assert result["document_sha256"] == sha(raw)
    assert result["content_bytes"] == len(expected.encode())
    assert result["authority_granted"] is False
    assert result["behavior_compliance"] == "NOT_PROVEN"
    assert result["native_hooks"] == "DISABLED"
    assert result["writes"] == []


def run_cli(*args, cwd=None):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run([sys.executable, "-m", "agent_os", *args], cwd=cwd,
                            env=environment, capture_output=True, text=True,
                            timeout=15, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_guidance_cli_returns_canonical_bytes_without_home_or_network(monkeypatch, capsys):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("guidance must not touch owner state or update network")

    monkeypatch.setattr(AgentOSPaths, "discover", forbidden)
    monkeypatch.setattr(cli, "update_advisory_check", forbidden)
    assert cli.main(["workflow", "guidance"]) == 0
    observed = json.loads(capsys.readouterr().out)
    raw = (ROOT / "docs/PROCESS.md").read_bytes()
    assert raw == guidance.PROCESS_PATH.read_bytes()
    assert_actual(observed, raw)


def test_real_subprocess_route_loads_same_installed_resource(tmp_path):
    direct = run_cli("workflow", "guidance", cwd=tmp_path)
    routed = run_cli("workflow", "route", "--kind", "project-change", cwd=tmp_path)
    assert routed["foundation_guidance"] == direct
    assert routed["product_writes_authorized"] is False
    assert_actual(direct, guidance.PROCESS_PATH.read_bytes())


@pytest.mark.parametrize("purpose", ["project-change", "continuation"])
def test_actual_context_cli_start_and_continue_load_body_and_keep_goal(tmp_path, purpose):
    path = tmp_path / "request.json"
    task = request(purpose)
    path.write_text(json.dumps(task))
    absent_home = tmp_path / "unselected-owner"
    result = run_cli("--home", str(absent_home), "context", "build", "--request", str(path),
                     cwd=tmp_path)
    assert_actual(result["foundation_guidance"], guidance.PROCESS_PATH.read_bytes())
    assert result["goal"] == task["goal"]
    assert result["profile_selection"]["status"] == "NOT_REQUESTED"
    assert result["behavior_compliance"] == "NOT_PROVEN"
    assert not absent_home.exists()


def test_changed_actual_guidance_invalidates_old_capsule_binding(tmp_path, monkeypatch):
    path = tmp_path / "PROCESS.md"
    path.write_bytes(guidance.PROCESS_PATH.read_bytes())
    monkeypatch.setattr(guidance, "PROCESS_PATH", path)
    task = request("continuation")
    original = context_gate.build(tmp_path / "unused", task)
    receipt = {"session_id": task["session_id"], "turn_id": task["turn_id"],
               "capsule_sha256": original["capsule_sha256"], "event_kind": "tool_result",
               "event_ref": "synthetic-observed-tool-result"}
    assert context_gate.verify(tmp_path, task, receipt)["status"] == "CURRENT_BINDING_MATCH"
    path.write_text(path.read_text().replace(guidance.END, "\nSynthetic updated instruction.\n" + guidance.END))
    revised = context_gate.build(tmp_path, task)
    assert_actual(revised["foundation_guidance"], path.read_bytes())
    assert revised["capsule_sha256"] != original["capsule_sha256"]
    assert revised["goal"] == original["goal"]
    with pytest.raises(GateError, match="context_receipt_binding_mismatch"):
        context_gate.verify(tmp_path, task, receipt)


def test_mid_read_guidance_drift_is_detected_from_actual_bytes(tmp_path, monkeypatch):
    path = tmp_path / "PROCESS.md"
    path.write_bytes(guidance.PROCESS_PATH.read_bytes())
    monkeypatch.setattr(guidance, "PROCESS_PATH", path)
    actual_load = guidance.load
    calls = []

    def drifting_load():
        if calls:
            path.write_text(path.read_text().replace(guidance.END, "\nChanged during read.\n" + guidance.END))
        calls.append(True)
        return actual_load()

    monkeypatch.setattr(guidance, "load", drifting_load)
    with pytest.raises(GateError, match="context_foundation_guidance_changed_during_read"):
        context_gate.build(tmp_path, request())
    assert len(calls) == 2


@pytest.mark.parametrize("purpose", ["question", "search", "audit", "discovery"])
def test_ordinary_reads_do_not_depend_on_guidance_or_profiles(tmp_path, monkeypatch, purpose):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("unrelated reading was made dependent on engineering context")

    monkeypatch.setattr(guidance, "load", forbidden)
    monkeypatch.setattr(AgentOSPaths, "discover", forbidden)
    monkeypatch.setattr(context_gate.profile_adapter, "context", forbidden)
    task = request(purpose)
    task["goal"] = None
    assert context_gate.build(tmp_path / "absent", task)["status"] == "FAST_PATH"
    assert workflow.route(purpose)["mode"] == "FAST_PATH"
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("invalid", ["missing", "duplicate", "reversed", "empty", "oversize", "document", "utf8", "symlink"])
def test_guidance_refuses_invalid_actual_resource_without_fabricated_fallback(tmp_path, monkeypatch, invalid):
    path = tmp_path / "PROCESS.md"
    data = (guidance.START + "\nSynthetic selected body.\n" + guidance.END).encode()
    if invalid == "missing":
        data = b"No selected section."
    elif invalid == "duplicate":
        data += data
    elif invalid == "reversed":
        data = (guidance.END + "\nBody\n" + guidance.START).encode()
    elif invalid == "empty":
        data = (guidance.START + "\n\n" + guidance.END).encode()
    elif invalid == "oversize":
        data = guidance.START.encode() + b"x" * (guidance.MAX_SECTION_BYTES + 1) + guidance.END.encode()
    elif invalid == "document":
        data += b"x" * guidance.MAX_DOCUMENT_BYTES
    elif invalid == "utf8":
        data += b"\xff"
    path.write_bytes(data)
    if invalid == "symlink":
        target = tmp_path / "linked.md"
        target.write_bytes(data)
        path.unlink()
        path.symlink_to(target)
    monkeypatch.setattr(guidance, "PROCESS_PATH", path)
    with pytest.raises(GateError, match="engineering_guidance"):
        guidance.load()
    assert workflow.route("audit")["mode"] == "FAST_PATH"


def test_installed_managed_entry_routes_to_actual_materialized_body(tmp_path):
    codex, skills, owner = tmp_path / "codex", tmp_path / "skills", tmp_path / "owner"
    codex.mkdir()
    (codex / "AGENTS.md").write_text("# Existing owner instructions\nKeep these exact bytes.\n")
    protected = {"config.toml": b"# synthetic settings sentinel\n",
                 "auth.json": b'{"synthetic_sentinel": true}\n'}
    for name, raw in protected.items():
        (codex / name).write_bytes(raw)
    result = integration.install(codex, skills, owner, apply=True)
    assert result["native_hooks"] == "DISABLED"
    installed = (codex / "AGENTS.md").read_text()
    assert installed.startswith("# Existing owner instructions\nKeep these exact bytes.\n")
    commands = re.findall(r"`(agentos workflow guidance)`", installed)
    assert commands == ["agentos workflow guidance"]
    actual = run_cli(*commands[0].split()[1:], cwd=tmp_path)
    assert_actual(actual, guidance.PROCESS_PATH.read_bytes())
    for name, raw in protected.items():
        assert (codex / name).read_bytes() == raw
    assert not (codex / "hooks").exists()
    selected_skill = skills / "agentos-project-entry/SKILL.md"
    packaged_skill = ROOT / "src/agent_os/resources/skills/agentos-project-entry/SKILL.md"
    assert selected_skill.read_bytes() == packaged_skill.read_bytes()
    assert actual["behavior_compliance"] == "NOT_PROVEN"


def test_guidance_does_not_accept_effect_arguments():
    with pytest.raises(GateError, match="does_not_accept_route_arguments"):
        workflow.command(["guidance", "--effect", "deploy"])
