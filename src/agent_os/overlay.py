"""Separate user-owned overlay: metadata-only discovery and create-only import."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .safeio import (
    GateError,
    atomic_bytes,
    atomic_json,
    create_only_bytes,
    filemap,
    lock,
    now,
    read_json,
    separated,
    sha,
    within,
)

SCHEMA = "agentos.user-overlay/v1"


def package_root() -> Path:
    return Path(__file__).resolve().parent


def validate_roots(user_home: Path, core_home: Path | None = None) -> None:
    selected = core_home or Path(os.environ.get("AGENTOS_CORE_HOME", package_root()))
    separated(selected, user_home)
    # Source and installed package roots are both protected, even with an env override.
    separated(package_root(), user_home)
    source = package_root().parent.parent
    if (source / "pyproject.toml").is_file():
        separated(source, user_home)
    absolute = user_home.expanduser().absolute()
    for path in [absolute, *absolute.parents]:
        # Resolved core separation above is mandatory; reject a symlink destination.
        if path.is_symlink() and path == absolute:
            raise GateError("user_home_symlink_refused")


def metadata(home: Path) -> dict:
    validate_roots(home)
    path = home / "overlay.json"
    if not path.exists():
        return {"status": "NOT_INITIALIZED", "user_home": str(home), "schema": SCHEMA}
    value = read_json(path)
    if value.get("schema") != SCHEMA:
        raise GateError("overlay_schema_unsupported_no_automatic_downgrade")
    return {
        "status": "PASS",
        "user_home": str(home),
        "schema": SCHEMA,
        "overlay_id": value.get("overlay_id"),
        "overlay_version": value.get("version"),
        "host_binding": value.get("host_binding"),
        "core_path": str(package_root()),
        "secrets_returned": False,
    }


def knowledge_index(home: Path, host_id: str | None = None) -> dict:
    metadata(home)
    path = within(home, "knowledge/INDEX.json")
    if not path.exists():
        return {"schema": "agentos.knowledge-index/v1", "entries": []}
    value = read_json(path)
    entries = [
        e
        for e in value.get("entries", [])
        if not host_id or e.get("host_id") in {None, host_id}
    ]
    # No content, no history autoload, no secret or arbitrary file read surface.
    return {
        "schema": "agentos.knowledge-index/v1",
        "entries": entries,
        "policy": "Read only the selected current context; reference entries need revalidation.",
    }


def inspect_import(source: Path, destination: Path) -> dict:
    source, destination = source.resolve(), destination.expanduser().resolve()
    validate_roots(destination)
    separated(source, destination)
    manifest = read_json(within(source, "OVERLAY_MANIFEST.json", allow_missing=False))
    if manifest.get("schema") != "agentos.overlay-manifest/v1":
        raise GateError("unsupported_overlay_manifest")
    overlay = read_json(within(source, "overlay.json", allow_missing=False))
    if overlay.get("schema") != SCHEMA:
        raise GateError("unsupported_overlay_schema")
    entries = manifest.get("files")
    if not isinstance(entries, dict) or not entries or len(entries) > 10000:
        raise GateError("invalid_overlay_manifest")
    created = []
    same = []
    conflicts = []
    for rel, expected in entries.items():
        if not isinstance(rel, str) or not rel or not Path(rel).parts:
            raise GateError("invalid_overlay_relative_path")
        if Path(rel).parts[0] not in {
            "config.json",
            "overlay.json",
            "preferences",
            "knowledge",
            "extensions",
            "projects",
            "README.md",
        }:
            raise GateError("overlay_path_not_importable:" + rel)
        if (
            Path(rel).parts[0] in {"config.json", "overlay.json", "README.md"}
            and len(Path(rel).parts) != 1
        ):
            raise GateError("overlay_root_file_cannot_be_directory:" + rel)
        src = within(source, rel, allow_missing=False)
        target = within(destination, rel)
        if src.stat().st_size > 16 * 1024 * 1024:
            raise GateError("overlay_file_size_limit")
        if sha(src.read_bytes()) != expected:
            raise GateError("overlay_hash_mismatch:" + rel)
        if target.exists():
            if not target.is_file() or sha(target.read_bytes()) != expected:
                conflicts.append(rel)
            else:
                same.append(rel)
        else:
            created.append(rel)
    actual = filemap(source)
    if set(actual) != set(entries) | {"OVERLAY_MANIFEST.json"}:
        raise GateError("unmanifested_overlay_files")
    return {
        "status": "CONFLICT" if conflicts else "READY",
        "create": created,
        "same": same,
        "conflicts": conflicts,
        "files": entries,
        "source": str(source),
        "destination": str(destination),
        "deletions": [],
        "overwrites": [],
        "manifest_sha256": sha((source / "OVERLAY_MANIFEST.json").read_bytes()),
    }


def import_overlay(source: Path, destination: Path, *, apply: bool = False) -> dict:
    validate_roots(destination)
    plan = inspect_import(source, destination)
    if not apply or plan["status"] != "READY":
        return plan
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock(within(destination, "state/overlay-import.lock")):
        plan = inspect_import(source, destination)
        if plan["status"] != "READY":
            return plan
        # Publish complete files only. A failed write leaves no target to conflict
        # with a later retry; existing user files are never overwritten.
        for rel in plan["create"]:
            src = within(source, rel, allow_missing=False)
            target = within(destination, rel)
            data = src.read_bytes()
            if sha(data) != plan["files"][rel]:
                raise GateError("overlay_changed_during_import")
            create_only_bytes(target, data)
        receipt = {
            "schema": "agentos.overlay-import-receipt/v1",
            "at": now(),
            "manifest_sha256": plan["manifest_sha256"],
            "created": plan["create"],
            "preserved_identical": plan["same"],
            "overwritten": [],
            "deleted": [],
        }
        atomic_json(within(destination, "state/last-overlay-import.json"), receipt)
    return {"status": "IMPORTED", **receipt}


def migrate_config(home: Path, *, apply: bool = False) -> dict:
    """v1-v4 community config -> v5 with explicit backup; unknown keys preserved."""
    from .config import AgentOSPaths, load_config

    validate_roots(home)
    path = within(home, "config.json", allow_missing=False)
    raw = path.read_bytes()
    old = read_json(path)
    loaded = load_config(AgentOSPaths.discover(home))
    if old == loaded:
        return {"status": "CURRENT", "writes": []}
    before = sha(raw)
    backup = f"backups/config-{before}.json"
    plan = {
        "status": "PLANNED",
        "from": old.get("schema"),
        "to": loaded["schema"],
        "before_sha256": before,
        "backup": backup,
        "unknown_keys_preserved": True,
    }
    if not apply:
        return plan
    with lock(within(home, "state/config-migration.lock")):
        if sha(path.read_bytes()) != before:
            raise GateError("config_changed_since_plan")
        backup_path = within(home, backup)
        if backup_path.exists() and backup_path.read_bytes() != raw:
            raise GateError("backup_conflict")
        if not backup_path.exists():
            atomic_bytes(backup_path, raw)
        atomic_json(path, loaded)
        if read_json(path) != loaded:
            raise GateError("config_readback_failed_backup_retained")
    return {**plan, "status": "MIGRATED", "after_sha256": sha(path.read_bytes())}


def command(argv: list[str], home: Path) -> tuple[dict, int]:
    p = argparse.ArgumentParser(prog="agentos overlay")
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("status")
    idx = sub.add_parser("index")
    idx.add_argument("--host-id")
    imp = sub.add_parser("import")
    imp.add_argument("--source", type=Path, required=True)
    imp.add_argument("--apply", action="store_true")
    mig = sub.add_parser("migrate-config")
    mig.add_argument("--apply", action="store_true")
    args = p.parse_args(argv)
    if args.action == "status":
        result = metadata(home)
    elif args.action == "index":
        result = knowledge_index(home, args.host_id)
    elif args.action == "import":
        result = import_overlay(args.source, home, apply=args.apply)
    else:
        result = migrate_config(home, apply=args.apply)
    return result, 2 if result.get("status") == "CONFLICT" else 0
