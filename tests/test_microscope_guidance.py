"""Microscope method delivery preserves mode and permissions; no profiling claim."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

import pytest

from agent_os import cli, integration, project, project_diagnostics
from agent_os import engineering_guidance as guidance
from agent_os.config import AgentOSPaths
from agent_os.safeio import filemap
from test_causal_guidance_loading import assert_actual
from test_development_levels import choice, enter
from test_diagnostic_context import finish_result, run_args
from test_foundation import setup as setup

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("level", [1, 3, 5])
def test_microscope_cli_only_delivers_method_with_saved_scope(tmp_path, monkeypatch, capsys, level):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Method lookup cannot initialize owner state, contact updates or launch a process")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(AgentOSPaths, "discover", forbidden)
    monkeypatch.setattr(cli, "update_advisory_check", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    before = filemap(tmp_path)
    assert cli.main(["workflow", "guidance", "--method", "crystal-microscope",
                     "--development-level", str(level),
                     "--development-scope", "module:synthetic-chain"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert_actual(result, guidance.PROCESS_PATH.read_bytes(), "crystal-microscope")
    assert result["development"] == choice(level, "module:synthetic-chain")
    assert "execution" not in result
    assert filemap(tmp_path) == before


@pytest.mark.parametrize("level", [1, 3, 5])
def test_microscope_lookup_inside_zero_preserves_active_run_and_return_choice(setup, level):
    root, home, _ = setup
    selected = choice(level, "module:synthetic-chain")
    task = enter(setup, selected)["task_id"]
    project_diagnostics.start(root, task, **run_args(root, home, task),
                              scope="Selected chain", reason="A material dependency is unknown.")
    before = filemap(root), filemap(home)
    active = project_diagnostics.status(root, task)
    result = guidance.load("crystal-microscope", development=selected)
    assert result["development"] == selected
    assert "execution" not in result
    assert result["authority_granted"] is False
    assert (filemap(root), filemap(home)) == before
    assert project_diagnostics.status(root, task) == active
    finished = project_diagnostics.finish(root, task, **run_args(root, home, task),
                                          result=finish_result())
    assert finished["diagnostic"]["effective_level"] == level
    assert project.load_task(root, task)["answers"]["development"] == selected


def test_cli_contract_declares_actual_methods_and_read_only_effect():
    source = ROOT / "schemas/cli-contract-v1.json"
    mirror = ROOT / "src/agent_os/resources/contracts/cli-contract-v1.json"
    assert source.read_bytes() == mirror.read_bytes()
    contract = json.loads(source.read_text())
    command = next(row for row in contract["commands"] if row["name"] == "workflow guidance")
    assert tuple(command["methods"]) == guidance.METHODS
    assert command["effect"] == "read_only" and command["write_surfaces"] == []


def test_existing_installer_delivers_exact_microscope_skill_and_tool(tmp_path):
    codex, skills, owner = tmp_path / "codex", tmp_path / "skills", tmp_path / "owner"
    result = integration.install(codex, skills, owner, apply=True)
    source = ROOT / "src/agent_os/resources/skills/crystal-microscope"
    assert (source / "SKILL.md").is_file()
    assert (source / "scripts/microscope.py").is_file()
    expected = {path.relative_to(source): path.read_bytes()
                for path in source.rglob("*") if path.is_file()}
    installed = skills / "crystal-microscope"
    actual = {path.relative_to(installed): path.read_bytes()
              for path in installed.rglob("*") if path.is_file()}
    assert actual == expected
    # Exact document copies retain their canonical basenames so reciprocal
    # relative links still resolve after the skill leaves the source tree.
    for document in (installed / "SKILL.md", installed / "references/CRYSTAL_MICROSCOPE.md",
                     installed / "references/CRYSTAL_MICROSCOPE_OBSERVABILITY.md"):
        for target in re.findall(r"\]\(([^)]+\.md)\)", document.read_text()):
            assert (document.parent / target).is_file(), (document, target)
    assert result["native_hooks"] == "DISABLED"
    assert result["auth_changes"] is False and result["model_changes"] is False
    entry = (skills / "agentos-project-entry/SKILL.md").read_text()
    assert "--method crystal-microscope" in entry
