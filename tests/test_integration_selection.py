"""Exact skill selection preserves unrelated installations and transaction guards."""

from contextlib import contextmanager
from pathlib import Path

import pytest

from agent_os import integration
from agent_os.safeio import GateError, atomic_json, read_json, sha


def snapshot(root):
    return {str(path.relative_to(root)):
            ("symlink", str(path.readlink())) if path.is_symlink() else
            ("file", path.read_bytes()) if path.is_file() else ("directory",)
            for path in root.rglob("*")}


@pytest.fixture
def homes(tmp_path):
    codex, skills, owner = tmp_path / "codex", tmp_path / "skills", tmp_path / "owner"
    codex.mkdir()
    skills.mkdir()
    (codex / "AGENTS.md").write_bytes(b"Preserve owner instructions.\n")
    return codex, skills, owner


def test_exact_selection_skips_foreign_symlink_preserves_manifest_and_default_refusal(homes, tmp_path):
    codex, skills, owner = homes
    foreign = tmp_path / "independent-project"
    foreign.mkdir()
    (foreign / "SKILL.md").write_bytes(b"Independent installation.\n")
    linked = skills / "function-extractor"
    linked.symlink_to(foreign, target_is_directory=True)
    historical = {str(linked / "SKILL.md"): sha(b"Previously managed version.\n")}
    receipt = codex / "agentos-integration.json"
    atomic_json(receipt, {"managed_files": historical})
    before = snapshot(tmp_path)

    with pytest.raises(GateError, match="symlink_path_refused"):
        integration.install(codex, skills, owner, apply=True)
    assert snapshot(tmp_path) == before

    selected = ["crystal-microscope", "agentos-project-entry"]
    planned = integration.install(codex, skills, owner, skills=selected)
    assert planned["status"] == "PLANNED"
    assert snapshot(tmp_path) == before
    expected = {str(codex / "AGENTS.md")}
    for name in selected:
        packaged = Path(integration.__file__).parent / "resources/skills" / name
        expected.update(str(skills / name / path.relative_to(packaged))
                        for path in packaged.rglob("*") if path.is_file())
    assert set(planned["files"]) == expected

    installed = integration.install(codex, skills, owner, skills=selected, apply=True)
    assert installed["status"] == "INSTALLED_MANUAL_WORKFLOW"
    assert installed["skill_selection"] == {
        "mode": "EXPLICIT", "names": sorted(selected), "unselected_files_verified": False,
    }
    assert read_json(receipt) == installed
    assert {key: installed["managed_files"][key] for key in historical} == historical
    assert linked.is_symlink() and linked.readlink() == foreign
    assert (foreign / "SKILL.md").read_bytes() == b"Independent installation.\n"
    for name in expected - {str(codex / "AGENTS.md")}:
        source = Path(integration.__file__).parent / "resources/skills" / Path(name).relative_to(skills)
        assert Path(name).read_bytes() == source.read_bytes()
    assert (codex / "AGENTS.md").read_bytes().startswith(b"Preserve owner instructions.\n")
    assert not (codex / "hooks.json").exists()
    assert not (codex / "config.toml").exists()

    # A later partial operation retains earlier ownership hashes without claiming
    # those unselected files were freshly inspected or replacing their content.
    prior_files = {name: Path(name).read_bytes() for name in expected}
    later = integration.install(codex, skills, owner, skills=["atlas"], apply=True)
    assert all(later["managed_files"][key] == value for key, value in installed["managed_files"].items())
    assert {name: Path(name).read_bytes() for name in expected} == prior_files
    assert linked.is_symlink()


@pytest.mark.parametrize("apply", [False, True])
def test_selected_symlink_still_refuses_without_touching_it(homes, tmp_path, apply):
    codex, skills, owner = homes
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "SKILL.md").write_bytes(b"Independent content.\n")
    (skills / "crystal-microscope").symlink_to(foreign, target_is_directory=True)
    before = snapshot(tmp_path)
    with pytest.raises(GateError, match="symlink_path_refused"):
        integration.install(codex, skills, owner, skills=["crystal-microscope"], apply=apply)
    assert snapshot(tmp_path) == before


def test_selected_unmanaged_content_conflicts_instead_of_being_overwritten(homes, tmp_path):
    codex, skills, owner = homes
    target = skills / "crystal-microscope/SKILL.md"
    target.parent.mkdir()
    target.write_bytes(b"Owner-specific skill.\n")
    before = snapshot(tmp_path)
    result = integration.install(codex, skills, owner, skills=["crystal-microscope"], apply=True)
    assert result["status"] == "CONFLICT"
    assert result["conflicts"] == [str(target)]
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("selected,code", [
    ([], "integration_skill_name_invalid"),
    ("atlas", "integration_skill_name_invalid"),
    ([None], "integration_skill_name_invalid"),
    (["../atlas"], "integration_skill_name_invalid"),
    (["atlas/*"], "integration_skill_name_invalid"),
    (["not-a-shipped-skill"], "integration_skill_unknown"),
])
def test_invalid_or_unknown_names_refuse_before_any_write(homes, tmp_path, selected, code):
    before = snapshot(tmp_path)
    with pytest.raises(GateError, match=code):
        integration.install(*homes, skills=selected, apply=True)
    assert snapshot(tmp_path) == before


def test_cli_repeated_exact_names_and_agents_only_are_unambiguous(homes, tmp_path):
    codex, skills, owner = homes
    args = ["codex", "--codex-home", str(codex), "--skills-home", str(skills)]
    result, code = integration.command(
        args + ["--skill", "crystal-microscope", "--skill", "atlas", "--skill", "atlas"], owner)
    assert code == 0 and result["skill_selection"]["names"] == ["atlas", "crystal-microscope"]
    before = snapshot(tmp_path)
    with pytest.raises(GateError, match="integration_skill_selection_conflict"):
        integration.command(args + ["--agents-only", "--skill", "atlas", "--apply"], owner)
    assert snapshot(tmp_path) == before
    agents, code = integration.command(args + ["--agents-only", "--apply"], owner)
    assert code == 0 and agents["files"] == [str(codex / "AGENTS.md")]
    assert agents["skill_selection"]["mode"] == "AGENTS_ONLY"
    assert list(skills.iterdir()) == []


def test_concurrent_receipt_update_refuses_stale_selected_manifest(homes, monkeypatch):
    codex, skills, owner = homes
    receipt = codex / "agentos-integration.json"
    atomic_json(receipt, {"managed_files": {"old": "accepted"}})
    competing = {"managed_files": {"new": "accepted"}}
    original_agents = (codex / "AGENTS.md").read_bytes()
    original_lock = integration.lock

    @contextmanager
    def change_before_lock(path):
        atomic_json(receipt, competing)
        with original_lock(path):
            yield

    monkeypatch.setattr(integration, "lock", change_before_lock)
    with pytest.raises(GateError, match="integration_target_changed_replan"):
        integration.install(codex, skills, owner, skills=["crystal-microscope"], apply=True)
    assert read_json(receipt) == competing
    assert (codex / "AGENTS.md").read_bytes() == original_agents
    assert list(skills.iterdir()) == []


def test_selected_failure_rolls_back_through_existing_journal(homes, monkeypatch):
    codex, skills, owner = homes
    agents_before = (codex / "AGENTS.md").read_bytes()
    receipt = codex / "agentos-integration.json"
    atomic_json(receipt, {"managed_files": {"historical": "retained"}})
    receipt_before = receipt.read_bytes()
    write = integration.atomic_bytes
    failed = False

    def fail_selected_once(path, data):
        nonlocal failed
        if skills in path.parents and not failed:
            failed = True
            raise OSError("synthetic selected write failure")
        return write(path, data)

    monkeypatch.setattr(integration, "atomic_bytes", fail_selected_once)
    with pytest.raises(OSError, match="synthetic selected write failure"):
        integration.install(codex, skills, owner, skills=["crystal-microscope"], apply=True)
    assert (codex / "AGENTS.md").read_bytes() == agents_before
    assert receipt.read_bytes() == receipt_before
    assert not (owner / "state/integration-transaction.json").exists()
    assert not any(path.is_file() for path in skills.rglob("*"))


@pytest.mark.parametrize("pending_skill", ["atlas", "crystal-microscope"])
def test_pending_recovery_cannot_expand_an_explicit_skill_scope(homes, tmp_path, pending_skill):
    codex, skills, owner = homes
    pending = skills / pending_skill / "SKILL.md"
    pending.parent.mkdir()
    pending.write_bytes(b"Interrupted write.\n")
    journal = owner / "state/integration-transaction.json"
    atomic_json(journal, {"schema": "agentos.integration-transaction/v1",
                         "codex_home": str(codex), "skills_home": str(skills),
                         "files": [{"path": str(pending), "before": None,
                                    "after": sha(pending.read_bytes()), "backup": None}]})
    before = snapshot(tmp_path)
    planned = integration.install(codex, skills, owner, skills=["crystal-microscope"])
    assert planned["status"] == "RECOVERY_REQUIRED" and snapshot(tmp_path) == before
    if pending_skill == "atlas":
        with pytest.raises(GateError, match="integration_recovery_skill_scope_mismatch"):
            integration.install(codex, skills, owner, skills=["crystal-microscope"], apply=True)
        assert snapshot(tmp_path) == before
    else:
        recovered = integration.install(codex, skills, owner, skills=["crystal-microscope"], apply=True)
        assert recovered["status"] == "RECOVERED_RETRY"
        assert not pending.exists() and not journal.exists()
