#!/usr/bin/env python3
"""Check public Markdown mirrors and exact skill deliveries without deleting orphans."""

from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from pathlib import Path

MAX_FILES = 1000
MAX_BYTES = 32 * 1024 * 1024
SKILL_DELIVERY_MIRRORS = (
    ("docs/CRYSTAL_MICROSCOPE.md",
     "src/agent_os/resources/skills/crystal-microscope/references/CRYSTAL_MICROSCOPE.md"),
    ("docs/CRYSTAL_MICROSCOPE_OBSERVABILITY.md",
     "src/agent_os/resources/skills/crystal-microscope/references/CRYSTAL_MICROSCOPE_OBSERVABILITY.md"),
)


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


def _declared_deliveries(root: Path, source: dict[str, bytes]) -> list[tuple[str, str, bytes, bytes | None]]:
    """Read only the two declared pairs; never discover arbitrary skill files."""
    skill_root = root / "src/agent_os/resources/skills/crystal-microscope"
    active = any(Path(name).name in source for name, _target in SKILL_DELIVERY_MIRRORS)
    if not active and not skill_root.exists() and not skill_root.is_symlink():
        return []
    result = []
    for source_name, target_name in SKILL_DELIVERY_MIRRORS:
        if Path(source_name).name not in source:
            raise ValueError("DECLARED_DELIVERY_SOURCE_REQUIRED")
        _directory(root, str(Path(source_name).parent), required=True)
        _directory(root, str(Path(target_name).parent))
        path = root / target_name
        before = _read(path, MAX_BYTES) if path.exists() or path.is_symlink() else None
        result.append((source_name, target_name, source[Path(source_name).name], before))
    return result


def _check_pair(root: Path, pair: tuple[str, str, bytes, bytes | None]) -> None:
    source_name, target_name, expected, before = pair
    _directory(root, str(Path(source_name).parent), required=True)
    _directory(root, str(Path(target_name).parent))
    if _read(root / source_name, MAX_BYTES) != expected:
        raise ValueError("DOCUMENT_SOURCE_CHANGED")
    path = root / target_name
    observed = _read(path, MAX_BYTES) if path.exists() or path.is_symlink() else None
    if observed != before:
        raise ValueError("DOCUMENT_TARGET_CHANGED")


def _replace_pair(root: Path, pair: tuple[str, str, bytes, bytes | None]) -> None:
    _check_pair(root, pair)
    _source_name, target_name, expected, _before = pair
    target_path = root / target_name
    target_dir = target_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    _check_pair(root, pair)
    mode = stat.S_IMODE(target_path.stat().st_mode) if target_path.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix="." + target_path.name + ".sync-", dir=target_dir)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(expected)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        _check_pair(root, pair)
        os.replace(temporary, target_path)
        if _read(target_path, MAX_BYTES) != expected:
            raise ValueError("DOCUMENT_SYNC_READBACK")
    finally:
        Path(temporary).unlink(missing_ok=True)


def synchronize(root: Path, *, apply: bool = False) -> dict:
    """Compare both inventories before any write, preserving unsupported extras.

    The generic inventory remains top-level Markdown only. In addition, exactly
    SKILL_DELIVERY_MIRRORS deliver canonical docs to named skill references.
    JSON provenance, other skill files and historical artifacts are outside its
    write scope. All selected preconditions are read before writing; individual
    replacements are atomic, not a multi-file transaction or OS-level CAS.
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
    deliveries = _declared_deliveries(root, source)
    changed_deliveries = [pair for pair in deliveries if pair[2] != pair[3]]
    result = {
        "status": "FAIL" if changed or orphaned or changed_deliveries else "PASS",
        "changed": changed,
        "orphaned": orphaned,
        "documents": sorted(source),
        "effects": "NONE",
        "skill_deliveries": {
            "scope": "EXACT_DECLARED_PAIRS_ONLY",
            "active": bool(deliveries),
            "pairs": [{"source": source_name, "target": target_name}
                      for source_name, target_name in SKILL_DELIVERY_MIRRORS],
            "changed": [pair[1] for pair in changed_deliveries],
        },
        "writes": [],
    }
    # Never hide an obsolete instruction by deleting it, or update some files
    # before reporting an orphan that requires an explicit source decision.
    if not apply or orphaned or not (changed or changed_deliveries):
        return result
    pairs = [("docs/" + name, "src/agent_os/resources/docs/" + name,
              source[name], target.get(name)) for name in changed] + changed_deliveries
    # A known conflict in either group must not allow earlier selected writes.
    for pair in pairs:
        _check_pair(root, pair)
    for pair in pairs:
        _replace_pair(root, pair)
    if changed and changed_deliveries:
        effects = "SELECTED_MARKDOWN_MIRRORS_AND_EXACT_SKILL_DELIVERIES"
    elif changed_deliveries:
        effects = "EXACT_SKILL_DELIVERIES_ONLY"
    else:
        effects = "SELECTED_MARKDOWN_MIRRORS_ONLY"
    result.update(status="SYNCED", effects=effects, writes=[pair[1] for pair in pairs])
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
