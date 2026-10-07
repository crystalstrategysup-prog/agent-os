"""Build a hash-pinned public wheel and source archive for an explicit release."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv, root, **kwargs):
    return subprocess.run(argv, cwd=root, check=True, **kwargs)


def export_commit(root, commit, source, folder, version):
    prefix = "agent-os-" + version
    run(
        [
            "git",
            "archive",
            "--format=zip",
            "--prefix=" + prefix + "/",
            "-o",
            str(source),
            commit,
        ],
        root,
    )
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        if (
            len(infos) > 100_000
            or sum(item.file_size for item in infos) > 128 * 1024 * 1024
        ):
            raise RuntimeError("SOURCE_ARCHIVE_BOUND")
        for item in infos:
            rel = Path(item.filename)
            mode = item.external_attr >> 16
            if (
                rel.is_absolute()
                or ".." in rel.parts
                or not rel.parts
                or rel.parts[0] != prefix
                or stat.S_ISLNK(mode)
            ):
                raise RuntimeError("UNSAFE_SOURCE_ARCHIVE")
        archive.extractall(folder)
        for item in infos:
            target = folder / item.filename
            mode = item.external_attr >> 16
            if not item.is_dir():
                target.chmod(0o755 if mode & 0o111 else 0o644)
    return folder / prefix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch("[0-9]+\\.[0-9]+\\.[0-9]+(?:rc[0-9]+)?", version):
        raise RuntimeError("VALIDATION_FAILED")
    pin = json.loads((root / ".release" / (version + ".json")).read_text())
    if not (
        pin["version"] == version and re.fullmatch("[0-9a-f]{64}", pin["wheel_sha256"])
    ):
        raise RuntimeError("VALIDATION_FAILED")
    if not (
        isinstance(pin["source_date_epoch"], int)
        and pin["source_date_epoch"] >= 315532800
    ):
        raise RuntimeError("VALIDATION_FAILED")
    for package, required in pin["build_versions"].items():
        if not importlib.metadata.version(package) == required:
            raise RuntimeError("build tool version mismatch")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    if not re.fullmatch("[0-9a-f]{40}", commit):
        raise RuntimeError("VALIDATION_FAILED")
    run(["git", "diff", "--quiet", "HEAD", "--"], root)
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = out / ("agent-os-" + commit + ".zip")
    with tempfile.TemporaryDirectory(prefix="agentos-release-source-") as name:
        clean = export_commit(root, commit, source, Path(name), version)
        run([sys.executable, str(clean / "tools/verify_public.py")], clean)
        env = os.environ.copy()
        env["SOURCE_DATE_EPOCH"] = str(pin["source_date_epoch"])
        env["PYTHONHASHSEED"] = "0"
        run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(out),
            ],
            clean,
            env=env,
        )
    wheel = out / ("crystal_agent_os-" + version + "-py3-none-any.whl")
    if not digest(wheel) == pin["wheel_sha256"]:
        raise RuntimeError("wheel differs from reviewed release pin")
    manifest = {
        "schema": "agentos.public-release/v1",
        "version": version,
        "source_commit": commit,
        "source_date_epoch": pin["source_date_epoch"],
        "build_versions": pin["build_versions"],
        "artifacts": {
            p.name: {"sha256": digest(p), "size": p.stat().st_size}
            for p in (wheel, source)
        },
        "verification_scope": "hash-pinned public source/wheel; installation and session adoption require separate receipts",
    }
    public_manifest = out / "MANIFEST.json"
    public_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (out / "SHA256SUMS").write_text(
        "".join(
            digest(p) + "  " + p.name + "\n" for p in (wheel, source, public_manifest)
        )
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "version": version,
                "source_commit": commit,
                "wheel_sha256": digest(wheel),
            }
        )
    )


if __name__ == "__main__":
    main()
