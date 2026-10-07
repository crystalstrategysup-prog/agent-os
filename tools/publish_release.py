"""Publish exact pinned assets, reconciling unknown outcomes before any retry."""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

CANONICAL_REPO = "crystalstrategysup-prog/agent-os"


def gh(*args):
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, timeout=120, check=False
    )


def api(path, missing=False):
    result = gh("api", path)
    if result.returncode:
        if missing and "HTTP 404" in result.stderr:
            return None
        raise RuntimeError("GITHUB_READ_FAILED")
    return json.loads(result.stdout)


def validate_release(release, tag, commit):
    # The bounded remote tag dereference is authoritative; target_commitish may be a branch.
    if not (release["tag_name"] == tag and re.fullmatch(r"[0-9a-f]{40}", commit)):
        raise RuntimeError("VALIDATION_FAILED")
    if not (not release["draft"] and release["prerelease"]):
        raise RuntimeError("VALIDATION_FAILED")


def verify_asset(repo, tag, name, expected):
    with tempfile.TemporaryDirectory(prefix="agentos-release-readback-") as folder:
        result = gh(
            "release",
            "download",
            tag,
            "--repo",
            repo,
            "--pattern",
            name,
            "--dir",
            folder,
        )
        if result.returncode:
            raise RuntimeError("RELEASE_ASSET_READBACK_FAILED")
        data = (Path(folder) / name).read_bytes()
        if not hashlib.sha256(data).hexdigest() == expected:
            raise RuntimeError("published asset differs")


def verify_tag(repo, tag, commit):
    obj = api("repos/" + repo + "/git/ref/tags/" + tag)["object"]
    for _ in range(4):
        if obj["type"] != "tag":
            break
        obj = api("repos/" + repo + "/git/tags/" + obj["sha"])["object"]
    if not (obj["type"] == "commit" and obj["sha"] == commit):
        raise RuntimeError("VALIDATION_FAILED")


def publish(repo, tag, folder):
    if not repo == CANONICAL_REPO:
        raise RuntimeError("VALIDATION_FAILED")
    manifest = json.loads((folder / "MANIFEST.json").read_text())
    commit = manifest["source_commit"]
    if not re.fullmatch("[0-9a-f]{40}", commit):
        raise RuntimeError("VALIDATION_FAILED")
    if not (
        tag == "v" + manifest["version"]
        and re.fullmatch("v[0-9]+\\.[0-9]+\\.[0-9]+rc[0-9]+", tag)
    ):
        raise RuntimeError("VALIDATION_FAILED")
    hashes = {}
    for line in (folder / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        if not (Path(name).name == name and re.fullmatch("[A-Za-z0-9_.-]+", name)):
            raise RuntimeError("VALIDATION_FAILED")
        if not (name not in hashes and re.fullmatch("[0-9a-f]{64}", digest)):
            raise RuntimeError("VALIDATION_FAILED")
        if not hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest:
            raise RuntimeError("VALIDATION_FAILED")
        hashes[name] = digest
    if not set(hashes) == set(manifest["artifacts"]) | {"MANIFEST.json"}:
        raise RuntimeError("VALIDATION_FAILED")
    for name, item in manifest["artifacts"].items():
        if not (
            item["sha256"] == hashes[name]
            and (folder / name).stat().st_size == item["size"]
        ):
            raise RuntimeError("VALIDATION_FAILED")
    hashes["SHA256SUMS"] = hashlib.sha256(
        (folder / "SHA256SUMS").read_bytes()
    ).hexdigest()
    verify_tag(repo, tag, commit)
    route = "repos/" + repo + "/releases/tags/" + tag
    release = api(route, missing=True)
    if release is None:
        gh(
            "release",
            "create",
            tag,
            "--repo",
            repo,
            "--verify-tag",
            "--target",
            commit,
            "--prerelease",
            "--latest=false",
            "--title",
            "AgentOS " + manifest["version"],
            "--notes",
            "Bounded source-literal handoff scan and precise JSON input errors. Public assets are SHA-pinned; host installation and session behavior require separate evidence.",
        )
        release = api(route)
    validate_release(release, tag, commit)
    names = [item["name"] for item in release["assets"]]
    if not (len(names) == len(set(names)) and set(names) <= set(hashes)):
        raise RuntimeError("unexpected or duplicate assets")
    for name in names:
        verify_asset(repo, tag, name, hashes[name])
    missing = sorted(set(hashes) - set(names))
    if missing:
        gh(
            "release",
            "upload",
            tag,
            "--repo",
            repo,
            *(str(folder / name) for name in missing),
        )
        release = api(route)
        validate_release(release, tag, commit)
    names = [item["name"] for item in release["assets"]]
    if not (len(names) == len(set(names)) and set(names) == set(hashes)):
        raise RuntimeError("incomplete release after reconciliation")
    for name in names:
        verify_asset(repo, tag, name, hashes[name])
    verify_tag(repo, tag, commit)
    return {
        "status": "PASS",
        "tag": tag,
        "source_commit": commit,
        "assets_verified": hashes,
        "url": release["html_url"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--assets", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            publish(args.repo, args.tag, Path(args.assets).resolve()), sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
