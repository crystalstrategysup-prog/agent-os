from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent_os import project as p
from agent_os import safeio, source_links
from agent_os.handoff import Library, local_principal
from agent_os.safeio import GateError, digest, filemap, sha, within


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True
    ).stdout


@pytest.fixture
def linked(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    p.initialize(
        root,
        "Synthetic tracked alias",
        ["general"],
        [],
        {
            key: "Synthetic local fixture without external data or services."
            for key in p.CONTEXT_KEYS
        },
    )
    git(root, "init", "-q")
    target = root / "backend/contracts"
    target.mkdir(parents=True)
    (target / "spec.json").write_text('{"fixture":1}\n')
    (root / "backend/app").mkdir()
    link = root / "backend/app/contracts"
    link.symlink_to("../contracts", target_is_directory=True)
    git(root, "add", "--", "backend/contracts/spec.json", "backend/app/contracts")
    return root, link, target


def test_exact_ru_shape_is_metadata_only_and_source_bound(linked, monkeypatch):
    root, link, target = linked
    original = Path.read_bytes

    def no_alias_read(path):
        assert path != link and link not in path.parents
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", no_alias_read)
    snapshot = p.source_snapshot(root)
    rel = "backend/app/contracts"
    metadata = snapshot["symlinks"][rel]
    target_bytes = b"../contracts"
    oid = hashlib.sha1(b"blob 12\0" + target_bytes).hexdigest()
    assert metadata == {
        "kind": "tracked_internal_directory_symlink/v1",
        "target": "../contracts",
        "target_path": "backend/contracts",
        "git_mode": "120000",
        "git_blob_oid": oid,
        "link_sha256": sha(target_bytes),
    }
    assert snapshot["files"][rel] == digest(metadata)
    assert snapshot["files"]["backend/contracts/spec.json"] == sha(
        original(target / "spec.json")
    )
    assert not any(name.startswith(rel + "/") for name in snapshot["files"])
    assert p.source_snapshot(root) == snapshot
    (target / "spec.json").write_text('{"fixture":2}\n')
    assert p.source_snapshot(root)["sha256"] != snapshot["sha256"]


def ready_alias_task(linked, tmp_path):
    root, _, _ = linked
    answers = {
        key: "Verified synthetic local fixture, no target effects."
        for key in p.QUESTIONS
    }
    answers.update(
        change_kind="implementation",
        write_paths=["code.py", "backend"],
        acceptance=[
            {
                "id": "A1",
                "criterion": "Tracked directory alias permits normal local lifecycle.",
                "checks": ["unit"],
            }
        ],
        checks=[
            {
                "id": "unit",
                "argv": [sys.executable, "-c", 'print("fixture PASS")'],
                "timeout": 10,
            }
        ],
    )
    task = p.enter(
        root,
        answers,
        session_id="fixture",
        turn_id="alias",
        user_home=tmp_path / "user",
    )["task_id"]
    for name in p.load_task(root, task)["selection"]["required"]:
        rel = f"docs/agentos/{name}.md"
        (root / rel).write_text(
            f"# Fixture {name}\n\nTask: {task}\n\nPurpose: synthetic lifecycle regression. Scope: local alias metadata only. Authority: fixture. Acceptance: local process. Rollback: discard temporary fixture. Source: this test.\n"
        )
        p.register_document(
            root,
            name,
            rel,
            "test reviewer",
            "synthetic fixture",
            "Reviewed synthetic scope and checks.",
            task if name == "stage" else None,
        )
    assert p.ready(root, task, "test reviewer")["status"] == "READY"
    assert p.run_check(root, task, "unit")["status"] == "PASS"
    assessment = p.assess(root, task)
    assert assessment["status"] == "PASS"
    review = {
        "reviewer": "test reviewer",
        "scope_reviewed": True,
        "summary": "Synthetic alias lifecycle accepted from actual current checks.",
        "limitations": "No external runtime or hostile same-user filesystem isolation.",
        "next_step": "Discard only the temporary fixture.",
        "accepted_criteria": ["A1"],
        "reviewed_documents": p.load_task(root, task)["selection"]["required"],
        "deployment_status": "not_requested",
    }
    return root, tmp_path / "user", task, review


def assert_metadata_recovery(root, home, task, tmp_path):
    lib = Library(home / "results-library")
    manifest = lib.resolve("handoff:" + task, local_principal())["manifest"]
    metadata = p.source_snapshot(root)["symlinks"]["backend/app/contracts"]
    items = [
        item
        for item in manifest["deliverables"]
        if item["path"].startswith("source-links/")
    ]
    assert len(items) == 1
    assert json.loads(lib.store.get(items[0]["ref"])) == {
        "path": "backend/app/contracts",
        "metadata": metadata,
    }
    report = lib.restore("handoff:" + task, tmp_path / "restored", local_principal())
    assert report["status"] == "partial"
    assert any(dep.startswith("source-link:") for dep in report["missing_dependencies"])
    assert any("backend/app/contracts" in item for item in report["not_restored"])
    assert not (tmp_path / "restored/source/backend/app/contracts").exists()
    assert (
        tmp_path / "restored/source/backend/contracts/spec.json"
    ).read_bytes() == b'{"fixture":1}\n'
    assert report["executed_commands"] == [] and not report["cleanup_authorized"]


def test_ready_check_and_close_use_link_aware_snapshot(linked, tmp_path):
    root, home, task, review = ready_alias_task(linked, tmp_path)
    assert p.close(root, task, review)["status"] == "CLOSED"
    assert p.verify_closeout(root, task)["status"] == "PASS"
    assert_metadata_recovery(root, home, task, tmp_path)


def test_checkpoint_with_approved_alias_never_reads_link(linked, tmp_path, monkeypatch):
    root, home, task, _ = ready_alias_task(linked, tmp_path)
    link = linked[1]
    original = Path.read_bytes

    def no_alias_read(path):
        assert path != link and link not in path.parents
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", no_alias_read)
    assert (
        p.checkpoint(root, task, "Unfinished local fixture", "Continue")["status"]
        == "CHECKPOINT"
    )
    assert_metadata_recovery(root, home, task, tmp_path)


@pytest.mark.parametrize("terminal", ["close", "checkpoint"])
@pytest.mark.parametrize(
    "mutation", ["link", "same_link_replaced", "index", "target_index"]
)
def test_terminal_capture_refuses_link_or_index_drift(
    linked, tmp_path, monkeypatch, terminal, mutation
):
    root, home, task, review = ready_alias_task(linked, tmp_path)
    link = linked[1]
    original = Library.build_handoff

    def mutate_after_capture(library, *args, **kwargs):
        result = original(library, *args, **kwargs)
        if mutation in {"link", "same_link_replaced"}:
            link.unlink()
            link.symlink_to(
                "../contracts"
                if mutation == "same_link_replaced"
                else "../../backend/contracts"
            )
        else:
            git(
                root,
                "rm",
                "--cached",
                "--",
                "backend/app/contracts"
                if mutation == "index"
                else "backend/contracts/spec.json",
            )
        return result

    monkeypatch.setattr(Library, "build_handoff", mutate_after_capture)
    with pytest.raises(GateError, match="tracked_symlink_(identity|index)_changed"):
        if terminal == "close":
            p.close(root, task, review)
        else:
            p.checkpoint(root, task, "Unfinished fixture", "Continue")
    assert p.load_task(root, task)["status"] not in {"CLOSED", "CHECKPOINT"}
    assert (
        Library(home / "results-library").search(
            {"filters": {"handoff_id": "handoff:" + task}}, local_principal()
        )["results"]
        == []
    )


def test_strict_generic_and_path_guards_unchanged(linked):
    root, link, _ = linked
    with pytest.raises(GateError, match="symlink_directory_refused"):
        filemap(root, skip=p.SKIP)
    with pytest.raises(GateError, match="symlink_path_refused"):
        within(root, "backend/app/contracts/spec.json")
    with pytest.raises(GateError, match="symlink_file_refused"):
        safeio.read_json(link)


def test_no_link_snapshot_shape_and_identity_unchanged(linked):
    root, link, _ = linked
    link.unlink()
    snapshot = p.source_snapshot(root)
    assert set(snapshot) == {"files", "sha256", "file_count"}
    # The established snapshot excludes independently hashed lifecycle docs.
    items = {
        name: value
        for name, value in filemap(root, skip=p.SKIP).items()
        if not name.startswith("docs/agentos/")
    }
    assert snapshot == {
        "files": items,
        "sha256": digest(items),
        "file_count": len(items),
    }


@pytest.mark.parametrize(
    "scenario",
    [
        "untracked",
        "index_regular_mode",
        "dirty_target",
        "absolute",
        "escape",
        "broken",
        "target_chain",
        "cancelled_chain",
        "cancelled_missing",
        "untracked_target",
        "excluded_target",
        "file_link",
        "no_git",
        "different_git_root",
        "conflicted_index",
    ],
)
def test_unsafe_aliases_refuse(linked, tmp_path, scenario):
    root, link, target = linked
    restage = True
    if scenario == "untracked":
        git(root, "rm", "--cached", "--", "backend/app/contracts")
        restage = False
    elif scenario == "index_regular_mode":
        git(
            root,
            "update-index",
            "--cacheinfo",
            "100644,"
            + git(root, "rev-parse", ":backend/app/contracts").decode().strip()
            + ",backend/app/contracts",
        )
        restage = False
    elif scenario in {
        "dirty_target",
        "absolute",
        "escape",
        "broken",
        "cancelled_chain",
        "cancelled_missing",
        "excluded_target",
        "file_link",
    }:
        link.unlink()
        replacement = {
            "dirty_target": "../../backend/contracts",
            "absolute": str(target),
            "escape": "../../../outside",
            "broken": "../absent",
            "cancelled_chain": "../jump/../contracts",
            "cancelled_missing": "../missing/../contracts",
            "excluded_target": "../../.agentos",
            "file_link": "../contracts/spec.json",
        }[scenario]
        if scenario == "cancelled_chain":
            (root / "backend/jump").symlink_to(target, target_is_directory=True)
        link.symlink_to(replacement)
        restage = scenario != "dirty_target"
    elif scenario == "target_chain":
        moved = root / "backend/real-contracts"
        target.rename(moved)
        target.symlink_to("real-contracts", target_is_directory=True)
        restage = False
    elif scenario == "untracked_target":
        git(root, "rm", "--cached", "--", "backend/contracts/spec.json")
        restage = False
    elif scenario == "no_git":
        (root / ".git").rename(tmp_path / "removed-git")
        restage = False
    elif scenario == "different_git_root":
        root = root / "backend"
        p.initialize(
            root,
            "Nested fixture",
            ["general"],
            [],
            {key: "Synthetic nested fixture context." for key in p.CONTEXT_KEYS},
        )
        restage = False
    elif scenario == "conflicted_index":
        oid = git(root, "rev-parse", ":backend/app/contracts").decode().strip()
        subprocess.run(
            ["git", "-C", str(root), "update-index", "--index-info"],
            input=f"0 {'0' * 40}\tbackend/app/contracts\n120000 {oid} 1\tbackend/app/contracts\n".encode(),
            check=True,
            capture_output=True,
        )
        restage = False
    if restage:
        git(root, "add", "--", "backend/app/contracts")
    with pytest.raises(GateError):
        p.source_snapshot(root)


@pytest.mark.parametrize(
    "mutation",
    ["link", "same_link_replaced", "parent", "referent", "index", "target_index"],
)
def test_substitution_during_inventory_refuses(linked, monkeypatch, mutation):
    root, link, target = linked
    original = Path.read_bytes
    mutated = False

    def mutate(path):
        nonlocal mutated
        data = original(path)
        if path == target / "spec.json" and not mutated:
            mutated = True
            if mutation in {"link", "same_link_replaced"}:
                link.unlink()
                link.symlink_to(
                    "../contracts"
                    if mutation == "same_link_replaced"
                    else "../../backend/contracts"
                )
            elif mutation in {"parent", "referent"}:
                item = link.parent if mutation == "parent" else target
                moved = item.with_name(item.name + "-old")
                item.rename(moved)
                item.symlink_to(moved.name, target_is_directory=True)
            elif mutation == "index":
                git(root, "rm", "--cached", "--", "backend/app/contracts")
            else:
                git(root, "rm", "--cached", "--", "backend/contracts/spec.json")
        return data

    monkeypatch.setattr(Path, "read_bytes", mutate)
    with pytest.raises(GateError, match="tracked_symlink_(identity|index)_changed"):
        p.source_snapshot(root)


def test_git_metadata_limits_and_failure_fail_closed(linked, monkeypatch):
    root, _, _ = linked
    monkeypatch.setattr(source_links, "MAX_GIT_METADATA", 2)
    with pytest.raises(GateError, match="tracked_symlink_git_metadata_limit"):
        p.source_snapshot(root)


def test_inherited_git_environment_and_fsmonitor_do_not_execute(
    linked, tmp_path, monkeypatch
):
    root, _, _ = linked
    marker = tmp_path / "fsmonitor-executed"
    script = tmp_path / "monitor"
    script.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    script.chmod(0o700)
    git(root, "config", "core.fsmonitor", str(script))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "foreign"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "foreign-index"))
    assert "backend/app/contracts" in p.source_snapshot(root)["symlinks"]
    assert not marker.exists()


def test_sha256_git_blob_identity(tmp_path):
    root = tmp_path / "sha256-project"
    root.mkdir()
    git(root, "init", "-q", "--object-format=sha256")
    p.initialize(
        root,
        "SHA256 fixture",
        ["general"],
        [],
        {key: "Synthetic SHA256 fixture." for key in p.CONTEXT_KEYS},
    )
    (root / "real").mkdir()
    (root / "real/spec").write_text("fixture")
    (root / "alias").symlink_to("real", target_is_directory=True)
    git(root, "add", "--", "real/spec", "alias")
    assert len(p.source_snapshot(root)["symlinks"]["alias"]["git_blob_oid"]) == 64
