"""Disposable source selection and end-to-end archive/restore regressions."""

import json
import subprocess
from pathlib import Path

import pytest
import test_foundation
from test_foundation import documents, review, start

from agent_os import project as p
from agent_os.handoff import Library, local_principal
from agent_os.handoff_store import HandoffError, scan_secrets
from agent_os.safeio import GateError
from agent_os.source_selection import GENERATORS, SourceSelection, require_source_write_paths

setup = test_foundation.setup


def package(root, generator="@eventcatalog/core", cache=".astro"):
    base = root / "portal"
    base.mkdir(exist_ok=True)
    (base / "package.json").write_text(json.dumps({"dependencies": {generator: "1.0.0"}}))
    (base / "package-lock.json").write_text('{"lockfileVersion":3}')
    (base / "src").mkdir(exist_ok=True)
    (base / "src" / "page.astro").write_text("canonical component")
    generated = base / cache
    generated.mkdir(exist_ok=True)
    (generated / "synthetic-cache.js").write_text("regenerable output")
    return base, generated


@pytest.mark.parametrize("cache", list(GENERATORS))
def test_known_generator_cache_without_body_reads(setup, monkeypatch, cache):
    root, _, _ = setup
    base, generated = package(root, sorted(GENERATORS[cache])[0], cache)
    original = Path.read_bytes

    def guarded(path):
        assert generated not in path.parents, "cache body must not be read"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    snapshot = p.source_snapshot(root)
    assert not any(x.startswith("portal/" + cache + "/") for x in snapshot["files"])
    assert {"portal/package.json", "portal/package-lock.json", "portal/src/page.astro"} <= snapshot["files"].keys()
    record = snapshot["source_selection"]["generated_caches"]
    assert len(record) == 1
    assert record[0]["package_sha256"] == snapshot["files"]["portal/package.json"]
    assert (generated / "synthetic-cache.js").exists()


@pytest.mark.parametrize("generator", ["unrelated-tool", None])
def test_unknown_provenance_remains_source(setup, generator):
    root, _, _ = setup
    base, _ = package(root, generator or "unrelated-tool")
    if generator is None:
        (base / "package.json").unlink()
    snapshot = p.source_snapshot(root)
    assert "portal/.astro/synthetic-cache.js" in snapshot["files"]
    assert "source_selection" not in snapshot


def test_not_recursive_name_ignore_and_history_preserved(setup):
    root, _, _ = setup
    base, _ = package(root)
    nested = base / "src/.astro"
    nested.mkdir()
    (nested / "canonical.md").write_text("not a package cache")
    history = root / ".atlas/history"
    history.mkdir(parents=True)
    (history / "accepted.json").write_text('{"retained":true}')
    snapshot = p.source_snapshot(root)
    assert {"portal/src/.astro/canonical.md", ".atlas/history/accepted.json"} <= snapshot["files"].keys()


def test_registered_canonical_doc_conflicts(setup):
    root, _, _ = setup
    _, generated = package(root)
    (generated / "canonical.md").write_text("A real canonical document describing actual source ownership, the selected project contract, retained history and required review before implementation.")
    p.register_document(root, "dossier", "portal/.astro/canonical.md", "reviewer", "fixture", "Canonical document.")
    with pytest.raises(GateError, match="generated_cache_canonical_conflict"):
        p.source_snapshot(root)


def test_explicit_cache_write_conflicts(setup):
    root, _, _ = setup
    package(root)
    snapshot = p.source_snapshot(root)
    for path in ["portal/.astro", "portal/.astro/owned.js"]:
        with pytest.raises(GateError, match="generated_cache_write_conflict"):
            require_source_write_paths(snapshot, [path])
    require_source_write_paths(snapshot, ["portal", "portal/.astro-other"])


def test_tracked_cache_conflicts_without_index_write(setup):
    root, _, _ = setup
    package(root)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-f", "portal/.astro/synthetic-cache.js"], check=True)
    index = (root / ".git/index").read_bytes()
    with pytest.raises(GateError, match="generated_cache_tracked_conflict"):
        p.source_snapshot(root)
    assert (root / ".git/index").read_bytes() == index


@pytest.mark.parametrize("linked", ["cache", "manifest"])
def test_generated_symlinks_refused(setup, tmp_path, linked):
    root, _, _ = setup
    base, generated = package(root)
    if linked == "cache":
        (generated / "synthetic-cache.js").unlink()
        generated.rmdir()
        generated.symlink_to(tmp_path, target_is_directory=True)
    else:
        saved = tmp_path / "package.json"
        saved.write_bytes((base / "package.json").read_bytes())
        (base / "package.json").unlink()
        (base / "package.json").symlink_to(saved)
    with pytest.raises(GateError, match="symlink"):
        p.source_snapshot(root)


def test_duplicate_provenance_and_changing_manifest_refused(setup, monkeypatch):
    root, _, _ = setup
    base, _ = package(root)
    (base / "package.json").write_text('{"dependencies":{},"dependencies":{"astro":"1"}}')
    with pytest.raises(GateError, match="duplicate_json_key"):
        p.source_snapshot(root)
    (base / "package.json").write_text('{"dependencies":{"astro":"1"}}')
    original = SourceSelection.exclude_directory

    def change(self, path):
        result = original(self, path)
        if result:
            (base / "package.json").write_text('{"dependencies":{}}')
        return result

    monkeypatch.setattr(SourceSelection, "exclude_directory", change)
    with pytest.raises(GateError, match="generated_cache_provenance_changed"):
        p.source_snapshot(root)


def test_source_identity_stable_only_for_cache_edits(setup):
    root, _, _ = setup
    base, generated = package(root)
    before = p.source_snapshot(root)
    (generated / "synthetic-cache.js").write_text("rebuilt output")
    assert p.source_snapshot(root) == before
    (base / "src/page.astro").write_text("changed source")
    assert p.source_snapshot(root)["sha256"] != before["sha256"]


def test_changed_policy_invalidates_old_ready(setup, monkeypatch):
    root, _, _ = setup
    task = start(setup)
    documents(setup, task)
    p.run_check(root, task, "unit")
    assert p.assess(root, task)["status"] == "PASS"
    monkeypatch.setattr("agent_os.source_selection.POLICY_VERSION", "agentos.source-selection/future")
    assert p.assess(root, task)["status"] == "BLOCKED"


def test_scanner_still_refuses_canonical_secret_shape():
    # Synthetic fixture, assembled so no complete secret-shaped literal is
    # accidentally distributed in the public test source.
    with pytest.raises(HandoffError, match="SECRET_DETECTED"):
        scan_secrets(("-----BEGIN " + "PRIVATE KEY-----\n" + "fixture\n").encode())


def test_lifecycle_archives_source_not_cache_and_retains_refusal(setup):
    root, home, answers = setup
    package(root)
    answers["write_paths"] = ["portal"]
    task = start(setup)
    documents(setup, task)
    p.run_check(root, task, "unit")
    # Historical safe metadata is not an input to a new terminal payload.
    old = root / f".agentos/tasks/{task}/diagnostics"
    old.mkdir()
    receipt = old / "synthetic-prior-refusal.json"
    receipt.write_text('{"error":"SECRET_DETECTED","original":true}')
    saved = receipt.read_bytes()
    result = p.close(root, task, review(setup, task))
    assert result["status"] == "CLOSED"
    assert p.verify_closeout(root, task)["status"] == "PASS"
    manifest = Library(home / "results-library").resolve("handoff:" + task, local_principal())["manifest"]
    paths = {d["path"] for d in manifest["deliverables"]}
    assert "source/portal/src/page.astro" in paths
    assert not any("/.astro/" in path for path in paths)
    assert "Generated cache portal/.astro" in manifest["recovery"]["not_restored"]
    assert manifest["recovery"]["level"] == "external_required"
    assert receipt.read_bytes() == saved


def test_lifecycle_rejects_canonical_source_secret_and_stays_open(setup):
    root, _, answers = setup
    base, _ = package(root)
    answers["write_paths"] = ["portal"]
    (base / "src/unsafe.txt").write_text("-----BEGIN " + "PRIVATE KEY-----\nfixture\n")
    task = start(setup)
    documents(setup, task)
    p.run_check(root, task, "unit")
    with pytest.raises(GateError, match="handoff_acceptance_failed:SECRET_DETECTED"):
        p.close(root, task, review(setup, task))
    assert p.load_task(root, task)["status"] == "VERIFYING"


def test_limits_still_apply_to_canonical_source(setup, monkeypatch):
    root, _, _ = setup
    package(root)
    monkeypatch.setattr(p, "inventory_budget", lambda _: {"max_files": 1, "max_bytes": 1000000})
    with pytest.raises(GateError, match="tree_inventory_limit"):
        p.source_snapshot(root)


@pytest.mark.parametrize("tracked", [True, False])
@pytest.mark.parametrize("relative_root", [True, False])
def test_nested_project_respects_enclosing_git_index(setup, monkeypatch, tracked, relative_root):
    root, _, _ = setup
    base, generated = package(root)
    p.initialize(base, "Nested project", ["general"], [],
                 {k: "Synthetic nested-root cache ownership fixture only." for k in p.CONTEXT_KEYS})
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    paths = ["portal/package.json"]
    if tracked:
        paths.append("portal/.astro/synthetic-cache.js")
    subprocess.run(["git", "-C", str(root), "add", "-f", *paths], check=True)
    index = (root / ".git/index").read_bytes()
    source = (generated / "synthetic-cache.js").read_bytes()
    selected = base
    if relative_root:
        monkeypatch.chdir(base)
        selected = Path(".")
    if tracked:
        with pytest.raises(GateError, match="generated_cache_tracked_conflict"):
            p.source_snapshot(selected)
    else:
        snapshot = p.source_snapshot(selected)
        assert "package.json" in snapshot["files"]
        assert not any(x.startswith(".astro/") for x in snapshot["files"])
    assert (root / ".git/index").read_bytes() == index
    assert (generated / "synthetic-cache.js").read_bytes() == source


def test_nested_project_in_git_worktree_refuses_tracked_cache(setup, tmp_path):
    root, _, _ = setup
    package(root)
    commands = [["init", "-q", str(root)],
                ["-C", str(root), "add", "-f", "portal"],
                ["-C", str(root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Synthetic fixture"]]
    for args in commands:
        subprocess.run(["git", *args], check=True)
    worktree = tmp_path / "worktree"
    subprocess.run(["git", "-C", str(root), "worktree", "add", "--detach", "-q", str(worktree)], check=True)
    base = worktree / "portal"
    p.initialize(base, "Nested worktree", ["general"], [],
                 {k: "Disposable nested worktree ownership fixture only." for k in p.CONTEXT_KEYS})
    assert (worktree / ".git").is_file()
    before = (base / ".astro/synthetic-cache.js").read_bytes()
    with pytest.raises(GateError, match="generated_cache_tracked_conflict"):
        p.source_snapshot(base)
    assert (base / ".astro/synthetic-cache.js").read_bytes() == before


def test_unknown_enclosing_git_metadata_fails_closed(setup, monkeypatch):
    root, _, _ = setup
    package(root)
    original = Path.lstat
    def unknown(path, *args, **kwargs):
        if path == root.parent / ".git":
            raise PermissionError("Synthetic metadata uncertainty")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "lstat", unknown)
    with pytest.raises(GateError, match="generated_cache_tracking_unknown"):
        p.source_snapshot(root)


def test_enclosing_git_reader_failure_does_not_exclude(setup, monkeypatch):
    root, _, _ = setup
    package(root)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    def fail(*args):
        raise GateError("tracked_symlink_git_read_failed")
    monkeypatch.setattr("agent_os.source_links._entries", fail)
    with pytest.raises(GateError, match="tracked_symlink_git_read_failed"):
        p.source_snapshot(root)
