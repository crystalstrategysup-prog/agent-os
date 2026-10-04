"""Candidate canary provenance negative controls use synthetic package bytes."""

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from agent_os import __version__
from agent_os.handoff_store import HandoffError, sha


@pytest.fixture
def provenance(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "completion_canary_control", root / "tools/completion_canary.py"
    )
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    monkeypatch.setattr(sys, "prefix", str(prefix))
    files = {
        name: ("synthetic source " + name).encode() for name in tool.REQUIRED_MODULES
    }
    files["resources/fixture.txt"] = b"synthetic complete resource"
    wheel, source = tmp_path / "candidate.whl", tmp_path / "source.zip"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, raw in files.items():
            archive.writestr("agent_os/" + name, raw)
        archive.writestr(
            "crystal_agent_os.dist-info/METADATA",
            f"Name: crystal-agent-os\nVersion: {__version__}\n",
        )
    driver = Path(tool.__file__).read_bytes()
    repository = tmp_path / "source-repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "remote",
            "add",
            "origin",
            "git@github.com:crystalstrategysup-prog/agent-os.git",
        ],
        check=True,
    )

    def write(relative, raw):
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    write("tools/completion_canary.py", driver)
    write("docs/completion/COMPLETION_CONTRACT.md", b"synthetic contract")
    for name, raw in files.items():
        write("src/agent_os/" + name, raw)
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=Synthetic",
            "-c",
            "user.email=synthetic@example.invalid",
            "commit",
            "-qm",
            "synthetic provenance control",
        ],
        check=True,
    )
    commit = (
        subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )
    with source.open("wb") as output:
        subprocess.run(
            ["git", "-C", str(repository), "archive", "--format=zip", commit],
            stdout=output,
            check=True,
        )
    manifest = {
        "version": __version__,
        "source_commit": commit,
        "source_git_root": str(repository),
        "origin_readback": "git@github.com:crystalstrategysup-prog/agent-os.git",
        "repository_url": "https://github.com/crystalstrategysup-prog/agent-os",
        "contract_hash": sha(b"synthetic contract"),
        "wheel_path": str(wheel),
        "wheel_sha256": sha(wheel.read_bytes()),
        "source_archive_path": str(source),
        "source_archive_sha256": sha(source.read_bytes()),
        "driver_sha256": sha(driver),
        "module_hashes": {name: sha(raw) for name, raw in files.items()},
    }
    log = tmp_path / "install.log"
    log.write_bytes(b"synthetic isolated installer receipt")
    receipt = {
        "schema": "agentos.candidate-install/v1",
        "sys_prefix": str(prefix),
        "exit_code": 0,
        "version": __version__,
        "wheel_sha256": manifest["wheel_sha256"],
        "module_hashes": manifest["module_hashes"],
        "source_archive_sha256": manifest["source_archive_sha256"],
        "driver_sha256": manifest["driver_sha256"],
        "log_path": str(log),
        "log_sha256": sha(log.read_bytes()),
    }
    (prefix / ".agentos-candidate-install.json").write_text(json.dumps(receipt))
    return tool, manifest, prefix, receipt


def test_canary_checks_complete_wheel_source_and_install_receipt(provenance):
    tool, manifest, _, _ = provenance
    assert tool.verify_candidate(manifest) == manifest["module_hashes"]


@pytest.mark.parametrize(
    "changed",
    [
        "empty",
        "missing_core",
        "missing_resource",
        "wheel",
        "driver",
        "install",
        "forged_archive",
    ],
)
def test_canary_rejects_partial_or_unbound_provenance(provenance, changed):
    tool, manifest, prefix, receipt = provenance
    if changed == "empty":
        manifest["module_hashes"] = {}
    elif changed == "missing_core":
        manifest["module_hashes"].pop("completion.py")
    elif changed == "missing_resource":
        manifest["module_hashes"].pop("resources/fixture.txt")
    elif changed == "wheel":
        manifest["wheel_sha256"] = "f" * 64
    elif changed == "driver":
        manifest["driver_sha256"] = "f" * 64
    elif changed == "forged_archive":
        source = Path(manifest["source_archive_path"])
        with zipfile.ZipFile(source, "a") as archive:
            archive.writestr("forged-uncommitted.txt", b"synthetic forgery")
        manifest["source_archive_sha256"] = sha(source.read_bytes())
        receipt["source_archive_sha256"] = manifest["source_archive_sha256"]
        (prefix / ".agentos-candidate-install.json").write_text(json.dumps(receipt))
    else:
        receipt["exit_code"] = 1
        (prefix / ".agentos-candidate-install.json").write_text(json.dumps(receipt))
    with pytest.raises(HandoffError):
        tool.verify_candidate(manifest)
