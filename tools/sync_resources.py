#!/usr/bin/env python3
"""Check exact public Markdown mirrors; apply updates without deleting orphans."""

from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from pathlib import Path

MAX_FILES = 1000
MAX_BYTES = 32 * 1024 * 1024


def _directory(root: Path, relative: str, *, required: bool = False) -> Path:
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError("DOCUMENT_DIRECTORY_INVALID")
    if required and not path.is_dir():
        raise ValueError("DOCUMENT_SOURCE_REQUIRED")
    return path


def _read(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("DOCUMENT_REGULAR_FILE_REQUIRED")
    if path.stat().st_size > limit:
        raise ValueError("DOCUMENT_BYTE_BOUND")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("DOCUMENT_BYTE_BOUND")
    return raw


def _inventory(directory: Path) -> dict[str, bytes]:
    result = {}
    total = 0
    for path in sorted(directory.glob("*.md")):
        if len(result) >= MAX_FILES:
            raise ValueError("DOCUMENT_FILE_BOUND")
        raw = _read(path, MAX_BYTES - total)
        total += len(raw)
        result[path.name] = raw
    return result


def synchronize(root: Path, *, apply: bool = False) -> dict:
    """Compare both inventories before any write, preserving unsupported extras.

    Only top-level Markdown mirrors belong to this operation. JSON provenance,
    nested resources and historical artifacts are outside its write scope.
    Individual replacements are atomic; this is not a multi-file transaction.
    """
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("DOCUMENT_ROOT_REQUIRED")
    source_dir = _directory(root, "docs", required=True)
    target_dir = _directory(root, "src/agent_os/resources/docs")
    source = _inventory(source_dir)
    if not source:
        raise ValueError("DOCUMENT_SOURCE_EMPTY")
    target = _inventory(target_dir)
    changed = sorted(name for name, raw in source.items() if target.get(name) != raw)
    orphaned = sorted(set(target) - set(source))
    result = {
        "status": "FAIL" if changed or orphaned else "PASS",
        "changed": changed,
        "orphaned": orphaned,
        "documents": sorted(source),
        "effects": "NONE",
    }
    # Never hide an obsolete instruction by deleting it, or update some files
    # before reporting an orphan that requires an explicit source decision.
    if not apply or orphaned or not changed:
        return result
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in changed:
        _directory(root, "src/agent_os/resources/docs", required=True)
        source_path, target_path = source_dir / name, target_dir / name
        if _read(source_path, MAX_BYTES) != source[name]:
            raise ValueError("DOCUMENT_SOURCE_CHANGED")
        observed = _read(target_path, MAX_BYTES) if target_path.exists() or target_path.is_symlink() else None
        if observed != target.get(name):
            raise ValueError("DOCUMENT_TARGET_CHANGED")
        mode = stat.S_IMODE(target_path.stat().st_mode) if target_path.exists() else 0o644
        fd, temporary = tempfile.mkstemp(prefix="." + name + ".sync-", dir=target_dir)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(source[name])
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, target_path)
            if _read(target_path, MAX_BYTES) != source[name]:
                raise ValueError("DOCUMENT_SYNC_READBACK")
        finally:
            Path(temporary).unlink(missing_ok=True)
    result.update(status="SYNCED", effects="SELECTED_MARKDOWN_MIRRORS_ONLY")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = synchronize(Path(__file__).resolve().parents[1], apply=args.apply)
    except (ValueError, OSError) as exc:
        result = {"status": "REFUSED", "code": str(exc)}
    report = dict(result)
    if "documents" in report:
        report["document_count"] = len(report.pop("documents"))
    print(json.dumps(report, sort_keys=True))
    return 0 if result["status"] in ("PASS", "SYNCED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
