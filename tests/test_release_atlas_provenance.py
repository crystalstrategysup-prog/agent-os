"""Public release packaging must reject stale Atlas source or resource identity."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_package_provenance", ROOT / "tools/release_package.py")
RELEASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RELEASE)


@pytest.mark.parametrize("mismatch", ["selected_source", "packaged_mirror"])
def test_release_refuses_atlas_mismatch_before_build(tmp_path, monkeypatch, capfd, mismatch):
    source = tmp_path / "source"
    source.mkdir()
    raw = b"# Synthetic Atlas instruction\n"
    pin = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    inventory = {"skills/atlas/SKILL.md": pin}
    provenance = {
        "schema": "agent-os.atlas-source/v1",
        "selected_tree_sha256": hashlib.sha256(json.dumps(
            inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "files": [{"path": "skills/atlas/SKILL.md", **pin,
                   "source_bytes": pin["bytes"], "source_sha256": pin["sha256"]}],
    }
    files = {
        "pyproject.toml": b'[project]\nname="atlas-release-fixture"\nversion="1.0.0"\n',
        ".release/1.0.0.json": json.dumps({"version": "1.0.0", "wheel_sha256": "0" * 64,
            "source_date_epoch": 1780000000, "build_versions": {}}).encode(),
        "modules/atlas/skills/atlas/SKILL.md": raw,
        "src/agent_os/resources/skills/atlas/SKILL.md": raw,
        "src/agent_os/resources/docs/ATLAS_SOURCE.json": json.dumps(provenance).encode(),
        "docs/ATLAS.md": b"Synthetic Atlas contract\n",
        "src/agent_os/resources/docs/ATLAS.md": b"Synthetic Atlas contract\n",
        "tools/verify_public.py": b'raise AssertionError("Atlas mismatch reached later release validation")\n',
    }
    changed = ("modules/atlas/skills/atlas/SKILL.md" if mismatch == "selected_source"
               else "src/agent_os/resources/skills/atlas/SKILL.md")
    files[changed] += b"Changed instruction\n"
    for name, data in files.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    shutil.copyfile(ROOT / "tools/sync_atlas.py", source / "tools/sync_atlas.py")
    shutil.copyfile(ROOT / "tools/release_package.py", source / "tools/release_package.py")
    env = {**os.environ, "GIT_AUTHOR_NAME": "Release Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "Release Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
    for args in (("init", "--quiet"), ("add", "."), ("-c", "commit.gpgsign=false", "-c",
            "core.hooksPath=/dev/null", "commit", "--quiet", "-m", "Synthetic mismatched source")):
        subprocess.run(["git", *args], cwd=source, env=env, check=True, capture_output=True)
    monkeypatch.setattr(RELEASE, "__file__", str(source / "tools/release_package.py"))
    output = tmp_path / "release"
    monkeypatch.setattr(sys, "argv", ["release_package.py", "--output", str(output)])

    with pytest.raises(subprocess.CalledProcessError) as failure:
        RELEASE.main()
    assert failure.value.cmd[-1].endswith("tools/sync_atlas.py")
    observed = capfd.readouterr().out
    assert ("ATLAS_SELECTED_SOURCE_MISMATCH" if mismatch == "selected_source" else '"status": "FAIL"') in observed
    assert not list(output.glob("*.whl"))
    assert not (output / "MANIFEST.json").exists()
