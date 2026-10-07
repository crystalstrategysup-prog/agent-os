"""Synthetic GitHub receipt reconciliation; no external operations."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "agentos_publish_release",
    Path(__file__).resolve().parents[1] / "tools/publish_release.py",
)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
COMMIT = "a" * 40
TAG = "v0.8.0rc2"
REPO = publisher.CANONICAL_REPO


@pytest.fixture
def package(tmp_path):
    manifest = {"version": "0.8.0rc2", "source_commit": COMMIT, "artifacts": {}}
    for name in ["synthetic.whl", "synthetic-source.zip"]:
        p = tmp_path / name
        p.write_bytes(b"synthetic-public-artifact")
        manifest["artifacts"][name] = {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "size": p.stat().st_size,
        }
    p = tmp_path / "MANIFEST.json"
    p.write_text(json.dumps(manifest))
    hashes = {name: item["sha256"] for name, item in manifest["artifacts"].items()}
    hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    p = tmp_path / "SHA256SUMS"
    p.write_text("".join(v + "  " + n + "\n" for n, v in hashes.items()))
    hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return tmp_path, hashes


def remote(
    monkeypatch,
    package,
    *,
    existing=True,
    missing=(),
    unknown_create=False,
    incomplete_upload=False,
):
    _folder, hashes = package
    state = {"release": existing, "names": set(hashes) - set(missing), "calls": []}

    def release():
        return {
            "tag_name": TAG,
            "target_commitish": COMMIT,
            "draft": False,
            "prerelease": True,
            "assets": [{"name": name} for name in sorted(state["names"])],
            "html_url": "https://github.com/" + REPO + "/releases/tag/" + TAG,
        }

    def api(path, missing=False):
        if "/git/ref/" in path:
            return {"object": {"type": "commit", "sha": COMMIT}}
        return release() if state["release"] else None

    def gh(*args):
        state["calls"].append(args)
        if args[:2] == ("release", "create"):
            state["release"] = True
            state["names"] = set()
            return SimpleNamespace(returncode=1 if unknown_create else 0)
        if args[:2] == ("release", "upload"):
            if not incomplete_upload:
                state["names"].update(hashes)
            return SimpleNamespace(returncode=1 if incomplete_upload else 0)
        raise AssertionError("unexpected mutation")

    monkeypatch.setattr(publisher, "api", api)
    monkeypatch.setattr(publisher, "gh", gh)
    monkeypatch.setattr(publisher, "verify_asset", lambda repo, tag, name, digest: None)
    return state


def test_existing_release_is_verified_without_republishing(package, monkeypatch):
    state = remote(monkeypatch, package)
    assert publisher.publish(REPO, TAG, package[0])["status"] == "PASS"
    assert state["calls"] == []


def test_only_missing_assets_are_uploaded(package, monkeypatch):
    state = remote(monkeypatch, package, missing=["SHA256SUMS"])
    publisher.publish(REPO, TAG, package[0])
    assert len(state["calls"]) == 1
    assert state["calls"][0][-1] == str(package[0] / "SHA256SUMS")


def test_unknown_create_is_reconciled_before_upload(package, monkeypatch):
    state = remote(monkeypatch, package, existing=False, unknown_create=True)
    assert publisher.publish(REPO, TAG, package[0])["status"] == "PASS"
    assert [call[1] for call in state["calls"]] == ["create", "upload"]


def test_unknown_incomplete_upload_does_not_blindly_repeat(package, monkeypatch):
    state = remote(monkeypatch, package, missing=["SHA256SUMS"], incomplete_upload=True)
    with pytest.raises(RuntimeError, match="incomplete release"):
        publisher.publish(REPO, TAG, package[0])
    assert len(state["calls"]) == 1


def test_conflicting_remote_asset_stops_before_upload(package, monkeypatch):
    state = remote(monkeypatch, package, missing=["SHA256SUMS"])

    def conflict(*args):
        raise RuntimeError("published asset differs")

    monkeypatch.setattr(publisher, "verify_asset", conflict)
    with pytest.raises(RuntimeError, match="differs"):
        publisher.publish(REPO, TAG, package[0])
    assert state["calls"] == []


def test_local_artifact_drift_stops_before_external_mutation(package, monkeypatch):
    state = remote(monkeypatch, package)
    (package[0] / "synthetic.whl").write_bytes(b"drift")
    with pytest.raises(RuntimeError):
        publisher.publish(REPO, TAG, package[0])
    assert state["calls"] == []


def test_unapproved_repository_stops_before_external_mutation(package, monkeypatch):
    state = remote(monkeypatch, package)
    with pytest.raises(RuntimeError):
        publisher.publish("other/repository", TAG, package[0])
    assert state["calls"] == []


def test_remote_tag_mismatch_stops_before_release_mutation(package, monkeypatch):
    state = remote(monkeypatch, package)
    original = publisher.api

    def api(path, missing=False):
        if "/git/ref/" in path:
            return {"object": {"type": "commit", "sha": "b" * 40}}
        return original(path, missing)

    monkeypatch.setattr(publisher, "api", api)
    with pytest.raises(RuntimeError):
        publisher.publish(REPO, TAG, package[0])
    assert state["calls"] == []


def test_annotated_tag_binds_commit_even_with_branch_release_metadata(
    package, monkeypatch
):
    state = remote(monkeypatch, package)
    original = publisher.api

    def api(path, missing=False):
        if "/git/ref/" in path:
            return {"object": {"type": "tag", "sha": "c" * 40}}
        if "/git/tags/" in path:
            return {"object": {"type": "commit", "sha": COMMIT}}
        value = original(path, missing)
        value["target_commitish"] = "main"
        return value

    monkeypatch.setattr(publisher, "api", api)
    assert publisher.publish(REPO, TAG, package[0])["source_commit"] == COMMIT
    assert state["calls"] == []


def test_unexpected_remote_asset_is_refused_without_upload(package, monkeypatch):
    state = remote(monkeypatch, package)
    state["names"].add("unrelated.zip")
    with pytest.raises(RuntimeError, match="unexpected"):
        publisher.publish(REPO, TAG, package[0])
    assert state["calls"] == []


def test_commit_export_excludes_dirty_untracked_and_ignored_sources(tmp_path):
    import subprocess

    spec = importlib.util.spec_from_file_location(
        "agentos_release_package",
        Path(__file__).resolve().parents[1] / "tools/release_package.py",
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True)

    git("init", "-q")
    (root / "source.py").write_text("committed_value = 1\n")
    (root / ".gitignore").write_text("ignored.py\n")
    git("add", "source.py", ".gitignore")
    git(
        "-c",
        "user.name=Synthetic Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "Synthetic public fixture",
    )
    commit = git("rev-parse", "HEAD").strip()
    (root / "source.py").write_text("dirty_value = 2\n")
    (root / "untracked.py").write_text("untracked_value = 3\n")
    (root / "ignored.py").write_text("ignored_value = 4\n")
    exported = builder.export_commit(
        root, commit, tmp_path / "source.zip", tmp_path / "export", "0.8.0rc2"
    )
    assert (exported / "source.py").read_text() == "committed_value = 1\n"
    assert not (exported / "untracked.py").exists()
    assert not (exported / "ignored.py").exists()
