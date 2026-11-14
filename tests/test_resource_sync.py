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


@pytest.fixture
def project(tmp_path):
    source = tmp_path / "docs"
    target = tmp_path / "src/agent_os/resources/docs"
    source.mkdir()
    target.mkdir(parents=True)
    (source / "CURRENT.md").write_bytes(b"Current project contract.\n")
    (target / "CURRENT.md").write_bytes(b"Current project contract.\n")
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
    target = tmp_path / "src/agent_os/resources/docs"
    assert sync.synchronize(tmp_path)["changed"] == ["ONE.md"]
    assert not target.exists()
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
