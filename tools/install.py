#!/usr/bin/env python3
"""Offline release installer. No sudo, service edits, network, or user-data writes.

Run plan first, then apply with the exact reported --expected-current identifier.
This script deliberately does not retire a different/private AgentOS runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path


class InstallError(ValueError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path: Path, value: dict) -> None:
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def normalized(path: Path) -> Path:
    path = path.expanduser().absolute()
    # /var -> /private/var is common on macOS. Reject the destination itself
    # and rely on resolved containment checks for ancestors.
    if path.is_symlink():
        raise InstallError("destination_symlink_refused:" + str(path))
    return path.resolve()


def separate(a: Path, b: Path) -> None:
    a, b = a.resolve(), b.resolve()
    if a == b or a in b.parents or b in a.parents:
        raise InstallError("core_and_user_paths_must_be_disjoint")


def release(root: Path, identifier: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}", identifier):
        raise InstallError("invalid_release_id")
    path = root / "releases" / identifier
    if path.is_symlink() or (root / "releases").is_symlink():
        raise InstallError("release_symlink_refused")
    return path


def read_manifest(path: Path) -> dict:
    marker = path / "INSTALL.json"
    if marker.is_symlink() or not marker.is_file() or (path / "INCOMPLETE").exists():
        raise InstallError("release_not_complete:" + path.name)
    data = json.loads(marker.read_text())
    if data.get("schema") != "agentos.install/v1" or data.get("overlay_schema") != 1:
        raise InstallError("release_schema_incompatible")
    wheel = path / data["wheel_name"]
    if (
        wheel.parent != path
        or wheel.is_symlink()
        or not wheel.is_file()
        or digest(wheel) != data["wheel_sha256"]
    ):
        raise InstallError("installed_wheel_hash_mismatch")
    return data


def check_user_compatibility(user: Path, manifest: dict) -> None:
    """Read only the schema headers that the selected release can consume."""
    if (
        manifest.get("overlay_schema") != 1
        or manifest.get("config_schema") != "agent-os.community-config/v5"
    ):
        raise InstallError("release_user_schema_contract_unsupported")

    def read_metadata(name: str) -> dict | None:
        path = user / name
        if path.is_symlink():
            raise InstallError("user_metadata_symlink_refused:" + name)
        if not path.exists():
            return None
        if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            raise InstallError("user_metadata_not_bounded_file:" + name)

        def unique(pairs: list[tuple[str, object]]) -> dict:
            value = {}
            for key, item in pairs:
                if key in value:
                    raise InstallError("user_metadata_duplicate_key:" + name)
                value[key] = item
            return value

        try:
            value = json.loads(
                path.read_text(encoding="utf-8"), object_pairs_hook=unique
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise InstallError("user_metadata_invalid_json:" + name) from exc
        if not isinstance(value, dict):
            raise InstallError("user_metadata_not_object:" + name)
        return value

    overlay = read_metadata("overlay.json")
    if overlay is not None and overlay.get("schema") != "agentos.user-overlay/v1":
        raise InstallError("user_overlay_schema_unsupported")
    config = read_metadata("config.json")
    if config is not None and config.get("schema") not in {
        f"agent-os.community-config/v{version}" for version in range(1, 6)
    }:
        raise InstallError("user_config_schema_unsupported")


def current_id(root: Path) -> str:
    current = root / "current"
    if not current.exists() and not current.is_symlink():
        return "none"
    if not current.is_symlink():
        raise InstallError("refuse_replace_unmanaged_current")
    target = current.resolve()
    if target.parent != (root / "releases").resolve():
        raise InstallError("refuse_replace_foreign_current")
    read_manifest(target)
    return target.name


def run(argv: list[str], *, timeout: int = 180) -> str:
    env = {
        **os.environ,
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        argv, capture_output=True, text=True, timeout=timeout, env=env, check=False
    )
    if result.returncode:
        raise InstallError("subprocess_failed:" + result.stderr[-4000:])
    return result.stdout


def probe(path: Path, expected_version: str) -> dict:
    code = """import json; from pathlib import Path; import agent_os
from agent_os.mcp_server import TOOLS
r = Path(agent_os.__file__).parent/'resources'
assert (r/'skills/agentos-project-entry/SKILL.md').is_file()
assert (r/'schemas/project.schema.json').is_file()
assert len(TOOLS) == 6
print(json.dumps({'version': agent_os.__version__, 'tools': len(TOOLS), 'resources': True}))
"""
    value = json.loads(run([str(path / ".venv/bin/python"), "-I", "-c", code]))
    if value["version"] != expected_version:
        raise InstallError("installed_version_mismatch")
    return value


def activate(root: Path, identifier: str, old: str) -> None:
    if current_id(root) != old:
        raise InstallError("current_changed_during_install")
    previous = {
        "schema": "agentos.previous/v1",
        "previous": old,
        "selected": identifier,
        "at_unix": time.time(),
    }
    write_json(root / "PREVIOUS.json", previous)
    temp = root / (".current-" + uuid.uuid4().hex)
    try:
        temp.symlink_to(Path("releases") / identifier, target_is_directory=True)
        os.replace(temp, root / "current")
    finally:
        temp.unlink(missing_ok=True)
    if current_id(root) != identifier:
        raise InstallError("activation_readback_failed")


def execute(args: argparse.Namespace) -> dict:
    if os.name != "posix":
        raise InstallError("managed_installer_supports_POSIX_only")
    if sys.version_info < (3, 11):  # noqa: UP036 - this script runs before package installation
        raise InstallError("Python_3_11_or_newer_required")
    root, user = normalized(args.core_home), normalized(args.user_home)
    separate(root, user)
    separate(Path(__file__).resolve().parent.parent, root)
    old = current_id(root)
    if args.action == "rollback":
        target = release(root, args.release_id)
        manifest = read_manifest(target)
        identifier = target.name
    else:
        wheel = args.wheel.expanduser().absolute()
        if wheel.is_symlink() or not wheel.is_file() or wheel.suffix != ".whl":
            raise InstallError("local_regular_wheel_required")
        expected = args.sha256.lower()
        if not re.fullmatch("[0-9a-f]{64}", expected) or digest(wheel) != expected:
            raise InstallError("wheel_sha256_mismatch")
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", args.version):
            raise InstallError("invalid_version")
        identifier = args.version + "-" + expected[:12]
        target = release(root, identifier)
        manifest = {
            "schema": "agentos.install/v1",
            "version": args.version,
            "wheel_sha256": expected,
            "wheel_name": wheel.name,
            "overlay_schema": 1,
            "config_schema": "agent-os.community-config/v5",
        }
    check_user_compatibility(user, manifest)
    plan = {
        "status": "PLANNED",
        "action": args.action,
        "core_home": str(root),
        "user_home": str(user),
        "expected_current": old,
        "release_id": identifier,
        "user_data_writes": [],
        "service_changes": [],
        "network_required": False,
        "activation_proven": False,
    }
    if not args.apply:
        return plan
    if args.expected_current is None or args.expected_current != old:
        raise InstallError("explicit_matching_expected_current_required")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = root / ".install.lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        raise InstallError("installation_lock_exists_manual_review_required")
    try:
        write_json(lock / "owner.json", {"pid": os.getpid(), "at_unix": time.time()})
        if current_id(root) != old:
            raise InstallError("current_changed_before_install")
        if args.action == "install":
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if target.exists():
                stored = read_manifest(target)
                if (
                    stored["wheel_sha256"] != manifest["wheel_sha256"]
                    or stored["version"] != manifest["version"]
                ):
                    raise InstallError("immutable_release_conflict")
            else:
                # Build at final immutable path: venv scripts contain absolute paths.
                target.mkdir(mode=0o700)
                (target / "INCOMPLETE").write_text(
                    "Do not activate. Inspect/retry in a different reviewed release directory.\n"
                )
                shutil.copyfile(wheel, target / wheel.name)
                if digest(target / wheel.name) != manifest["wheel_sha256"]:
                    raise InstallError("wheel_changed_during_copy")
                run([sys.executable, "-I", "-m", "venv", str(target / ".venv")])
                run(
                    [
                        str(target / ".venv/bin/python"),
                        "-I",
                        "-m",
                        "pip",
                        "--isolated",
                        "install",
                        "--no-index",
                        "--no-deps",
                        "--disable-pip-version-check",
                        str(target / wheel.name),
                    ]
                )
                evidence = probe(target, manifest["version"])
                manifest["probe"] = evidence
                manifest["created_at_unix"] = time.time()
                write_json(target / "INSTALL.json", manifest)
                (target / "INCOMPLETE").unlink()
        evidence = probe(target, manifest["version"])
        check_user_compatibility(user, manifest)
        activate(root, identifier, old)
        return {
            **plan,
            "status": "INSTALLED" if args.action == "install" else "ROLLED_BACK",
            "activation_proven": True,
            "local_probe": evidence,
            "previous": old,
            "next": "Import separate overlay, then integrate AGENTS/skills and read back in a new session. Keep native hooks disabled. No live service was replaced.",
        }
    finally:
        (lock / "owner.json").unlink(missing_ok=True)
        lock.rmdir()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    for action in ("install", "rollback"):
        s = sub.add_parser(action)
        s.add_argument(
            "--core-home",
            type=Path,
            default=Path.home() / ".local/share/agentos-foundation",
        )
        s.add_argument("--user-home", type=Path, default=Path.home() / ".agentos-user")
        s.add_argument("--apply", action="store_true")
        s.add_argument("--expected-current")
        if action == "install":
            s.add_argument("--wheel", type=Path, required=True)
            s.add_argument("--sha256", required=True)
            s.add_argument("--version", required=True)
        else:
            s.add_argument("--release-id", required=True)
    return p


def main() -> int:
    try:
        print(json.dumps(execute(parser().parse_args()), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as e:
        print(json.dumps({"status": "BLOCKED", "error": str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
