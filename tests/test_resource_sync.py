"""Canonical Markdown deletion must not leave silently accepted wheel instructions."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/sync_resources.py"
SPEC = importlib.util.spec_from_file_location("resource_sync_under_test", SCRIPT)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


def declared_sources(root, *, mirrored):
    for source, target in sync.SKILL_DELIVERY_MIRRORS:
        source_path = root / source
        source_path.parent.mkdir(parents=True, exist_ok=True)
        content = ("Canonical document: " + source + "\n").encode()
        source_path.write_bytes(content)
        if mirrored:
            for target_name in (target, "src/agent_os/resources/docs/" + source_path.name):
                target_path = root / target_name
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(content)


@pytest.fixture
def project(tmp_path):
    source = tmp_path / "docs"
    target = tmp_path / "src/agent_os/resources/docs"
    source.mkdir()
    target.mkdir(parents=True)
    (source / "CURRENT.md").write_bytes(b"Current project contract.\n")
    (target / "CURRENT.md").write_bytes(b"Current project contract.\n")
    declared_sources(tmp_path, mirrored=True)
    return tmp_path, source, target


@pytest.mark.parametrize("apply", [False, True])
def test_retired_copy_refuses_before_updates_and_preserves_every_file(project, apply):
    root, source, target = project
    (source / "CURRENT.md").write_bytes(b"Reviewed successor contract.\n")
    (source / "NEW.md").write_bytes(b"New canonical document.\n")
    (target / "RETIRED.md").write_bytes(b"Retired instruction must be reconciled.\n")
    before = {p.name: p.read_bytes() for p in target.iterdir()}

    result = sync.synchronize(root, apply=apply)

    assert result["status"] == "FAIL"
    assert result["orphaned"] == ["RETIRED.md"]
    assert result["changed"] == ["CURRENT.md", "NEW.md"]
    assert result["effects"] == "NONE"
    assert {p.name: p.read_bytes() for p in target.iterdir()} == before


def test_check_and_apply_are_distinct_and_preserve_other_resource_types(project):
    root, source, target = project
    (source / "CURRENT.md").write_bytes(b"Updated canonical contract.\n")
    (source / "NEW.md").write_bytes(b"New contract.\n")
    retained = {"PROVENANCE.json": b'{"historical":true}\n', "notes.txt": b"Retained notes.\n"}
    for name, raw in retained.items():
        (target / name).write_bytes(raw)
    original = (target / "CURRENT.md").read_bytes()

    assert sync.synchronize(root)["status"] == "FAIL"
    assert (target / "CURRENT.md").read_bytes() == original
    assert not (target / "NEW.md").exists()

    result = sync.synchronize(root, apply=True)

    assert result["status"] == "SYNCED"
    assert result["effects"] == "SELECTED_MARKDOWN_MIRRORS_ONLY"
    for name in ("CURRENT.md", "NEW.md"):
        assert (target / name).read_bytes() == (source / name).read_bytes()
    assert {name: (target / name).read_bytes() for name in retained} == retained
    assert sync.synchronize(root)["status"] == "PASS"
    assert sync.synchronize(root, apply=True)["effects"] == "NONE"
    assert not list(target.glob(".*.sync-*"))


def test_missing_target_is_created_only_on_apply(tmp_path):
    source = tmp_path / "docs"
    source.mkdir()
    (source / "ONE.md").write_bytes(b"One canonical document.\n")
    declared_sources(tmp_path, mirrored=False)
    target = tmp_path / "src/agent_os/resources/docs"
    checked = sync.synchronize(tmp_path)
    assert checked["changed"] == ["CRYSTAL_MICROSCOPE.md", "CRYSTAL_MICROSCOPE_OBSERVABILITY.md", "ONE.md"]
    assert len(checked["skill_deliveries"]["changed"]) == 2
    assert not target.exists()
    assert not (tmp_path / "src/agent_os/resources/skills").exists()
    assert sync.synchronize(tmp_path, apply=True)["status"] == "SYNCED"
    assert (target / "ONE.md").read_bytes() == (source / "ONE.md").read_bytes()


@pytest.mark.parametrize("side", ["source", "target", "target-parent"])
def test_symlinked_inputs_refuse_without_touching_outside(project, tmp_path, side):
    root, source, target = project
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "CURRENT.md"
    sentinel.write_bytes(b"Unrelated owner content.\n")
    if side == "source":
        (source / "CURRENT.md").unlink()
        (source / "CURRENT.md").symlink_to(sentinel)
    elif side == "target":
        (target / "CURRENT.md").unlink()
        (target / "CURRENT.md").symlink_to(sentinel)
    else:
        shutil.rmtree(target)
        target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="DOCUMENT_(REGULAR_FILE_REQUIRED|DIRECTORY_INVALID)"):
        sync.synchronize(root, apply=True)
    assert sentinel.read_bytes() == b"Unrelated owner content.\n"


@pytest.mark.parametrize("bound,value,code", [("MAX_FILES", 0, "DOCUMENT_FILE_BOUND"),
                                             ("MAX_BYTES", 1, "DOCUMENT_BYTE_BOUND")])
def test_bounds_fail_before_writing(project, monkeypatch, bound, value, code):
    root, _source, target = project
    before = (target / "CURRENT.md").read_bytes()
    monkeypatch.setattr(sync, bound, value)
    with pytest.raises(ValueError, match=code):
        sync.synchronize(root, apply=True)
    assert (target / "CURRENT.md").read_bytes() == before


def test_cli_reports_orphan_as_failure_in_check_and_apply(project):
    root, _source, target = project
    tools = root / "tools"
    tools.mkdir()
    script = tools / SCRIPT.name
    shutil.copyfile(SCRIPT, script)
    orphan = target / "RETIRED.md"
    orphan.write_bytes(b"Retained orphan.\n")
    for argv in ([], ["--apply"]):
        observed = subprocess.run([sys.executable, "-B", str(script), *argv],
                                  check=False, capture_output=True, text=True, timeout=10)
        assert observed.returncode == 1
        assert json.loads(observed.stdout)["orphaned"] == ["RETIRED.md"]
        assert orphan.read_bytes() == b"Retained orphan.\n"


def test_exact_skill_delivery_drift_is_checked_and_repaired_without_other_skill_writes(project):
    root, source, target = project
    relative = sync.SKILL_DELIVERY_MIRRORS[0][1]
    delivered = root / relative
    delivered.write_bytes(b"Stale delivery\n")
    delivered.chmod(0o640)
    retained = delivered.parent / "independent.md"
    retained.write_bytes(b"Unrelated skill document\n")
    docs_before = {p.name: p.read_bytes() for p in target.iterdir()}
    checked = sync.synchronize(root)
    assert checked["status"] == "FAIL" and checked["effects"] == "NONE"
    assert checked["changed"] == [] and checked["writes"] == []
    assert checked["skill_deliveries"]["scope"] == "EXACT_DECLARED_PAIRS_ONLY"
    assert checked["skill_deliveries"]["changed"] == [relative]
    assert delivered.read_bytes() == b"Stale delivery\n"
    applied = sync.synchronize(root, apply=True)
    assert applied["effects"] == "EXACT_SKILL_DELIVERIES_ONLY"
    assert applied["writes"] == [relative]
    assert delivered.read_bytes() == (source / "CRYSTAL_MICROSCOPE.md").read_bytes()
    assert delivered.stat().st_mode & 0o777 == 0o640
    assert retained.read_bytes() == b"Unrelated skill document\n"
    assert {p.name: p.read_bytes() for p in target.iterdir()} == docs_before
    assert sync.synchronize(root)["status"] == "PASS"


def test_generic_legacy_tree_keeps_original_sync_without_installing_an_extension(tmp_path):
    source = tmp_path / "docs/CURRENT.md"
    target = tmp_path / "src/agent_os/resources/docs/CURRENT.md"
    source.parent.mkdir()
    target.parent.mkdir(parents=True)
    source.write_bytes(b"Updated ordinary document.\n")
    target.write_bytes(b"Earlier ordinary document.\n")
    planned = sync.synchronize(tmp_path)
    assert planned["changed"] == ["CURRENT.md"] and planned["effects"] == "NONE"
    assert planned["skill_deliveries"]["active"] is False
    applied = sync.synchronize(tmp_path, apply=True)
    assert applied["effects"] == "SELECTED_MARKDOWN_MIRRORS_ONLY"
    assert applied["writes"] == ["src/agent_os/resources/docs/CURRENT.md"]
    assert target.read_bytes() == source.read_bytes()
    assert not (tmp_path / "src/agent_os/resources/skills").exists()
    assert sync.synchronize(tmp_path)["status"] == "PASS"


def test_present_extension_marker_requires_the_complete_declared_group(tmp_path):
    source = tmp_path / "docs/CURRENT.md"
    source.parent.mkdir()
    source.write_bytes(b"Ordinary document.\n")
    marker = tmp_path / "src/agent_os/resources/skills/crystal-microscope/SKILL.md"
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"Installed extension marker.\n")
    with pytest.raises(ValueError, match="DECLARED_DELIVERY_SOURCE_REQUIRED"):
        sync.synchronize(tmp_path, apply=True)
    assert not (tmp_path / "src/agent_os/resources/docs").exists()


@pytest.mark.parametrize("damage", ["symlink", "missing-source"])
def test_declared_delivery_preflight_refuses_before_document_writes(project, tmp_path, damage):
    root, source, target = project
    original = (target / "CURRENT.md").read_bytes()
    (source / "CURRENT.md").write_bytes(b"New selected document\n")
    source_name, target_name = sync.SKILL_DELIVERY_MIRRORS[0]
    if damage == "symlink":
        outside = tmp_path / "outside.md"
        outside.write_bytes(b"Independent data\n")
        (root / target_name).unlink()
        (root / target_name).symlink_to(outside)
        code = "DOCUMENT_REGULAR_FILE_REQUIRED"
    else:
        (root / source_name).unlink()
        code = "DECLARED_DELIVERY_SOURCE_REQUIRED"
    with pytest.raises(ValueError, match=code):
        sync.synchronize(root, apply=True)
    assert (target / "CURRENT.md").read_bytes() == original
    if damage == "symlink":
        assert outside.read_bytes() == b"Independent data\n"


def test_declared_target_change_preserves_competing_bytes_before_any_selected_write(project, monkeypatch):
    root, source, target = project
    original = (target / "CURRENT.md").read_bytes()
    (source / "CURRENT.md").write_bytes(b"New selected document\n")
    delivered = root / sync.SKILL_DELIVERY_MIRRORS[0][1]
    delivered.write_bytes(b"Stale delivery\n")
    read = sync._read
    calls = 0

    def competing_write(path, limit):
        nonlocal calls
        if path == delivered:
            calls += 1
            if calls == 2:
                path.write_bytes(b"Competing accepted content\n")
        return read(path, limit)

    monkeypatch.setattr(sync, "_read", competing_write)
    with pytest.raises(ValueError, match="DOCUMENT_TARGET_CHANGED"):
        sync.synchronize(root, apply=True)
    assert (target / "CURRENT.md").read_bytes() == original
    assert delivered.read_bytes() == b"Competing accepted content\n"
    assert not list(delivered.parent.glob(".*.sync-*"))
