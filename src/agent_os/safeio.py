"""Bounded, atomic local storage. Not a boundary against a hostile same-UID process."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

MAX_JSON = 4 * 1024 * 1024


class GateError(ValueError):
    """A controlled refusal, safe to return to a caller."""


def now() -> str:
    return datetime.now(UTC).isoformat()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value: Any) -> str:
    return sha(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )


def read_json(path: Path) -> Any:
    if path.is_symlink():
        raise GateError("symlink_file_refused")
    if path.stat().st_size > MAX_JSON:
        raise GateError("json_size_limit")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise GateError("duplicate_json_key:" + key)
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def within(root: Path, rel: str, *, allow_missing: bool = True) -> Path:
    raw = PurePosixPath(rel)
    if (
        not rel
        or raw.is_absolute()
        or ".." in raw.parts
        or "\\" in rel
        or "\x00" in rel
    ):
        raise GateError("unsafe_relative_path")
    base = root.resolve()
    current = root
    for part in raw.parts:
        current = current / part
        if current.is_symlink():
            raise GateError("symlink_path_refused")
    result = current.resolve()
    if result == base or base not in result.parents:
        raise GateError("path_outside_root")
    if not allow_missing and not result.is_file():
        raise GateError("file_missing:" + rel)
    return result


def atomic_bytes(path: Path, data: bytes, mode: int = 0o600) -> None:
    if path.is_symlink():
        raise GateError("symlink_destination_refused")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".agentos-tmp-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(
        path,
        (
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode(),
    )


@contextmanager
def lock(directory: Path) -> Iterator[None]:
    directory.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise GateError("symlink_lock_refused")
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError as e:
        raise GateError("busy_or_stale_lock_manual_review_required") from e
    try:
        atomic_json(directory / "holder.json", {"pid": os.getpid(), "at": now()})
        yield
    finally:
        (directory / "holder.json").unlink(missing_ok=True)
        directory.rmdir()


def nonempty(value: Any, name: str, limit: int = 12000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise GateError("missing_or_invalid:" + name)
    if re.search(r"\[REQUIRED\]|\bTBD\b|\bTODO\b", value, re.IGNORECASE):
        raise GateError("placeholder:" + name)
    return value.strip()


def identifier(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value
    ):
        raise GateError("invalid_identifier")
    return value


def separated(a: Path, b: Path) -> None:
    a, b = a.expanduser().resolve(), b.expanduser().resolve()
    if a == b or a in b.parents or b in a.parents:
        raise GateError("core_and_user_roots_must_be_disjoint")


def filemap(
    root: Path,
    *,
    skip: set[str] | None = None,
    limit: int = 20000,
    max_bytes: int = 128 * 1024 * 1024,
) -> dict[str, str]:
    result: dict[str, str] = {}
    total = 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in (skip or set()))
        for d in dirs:
            if (Path(parent) / d).is_symlink():
                raise GateError("symlink_directory_refused")
        for name in sorted(files):
            path = Path(parent) / name
            if path.is_symlink():
                raise GateError("symlink_file_refused")
            rel = path.relative_to(root).as_posix()
            size = path.stat().st_size
            total += size
            if len(result) >= limit or total > max_bytes:
                raise GateError("tree_inventory_limit")
            result[rel] = sha(path.read_bytes())
    return result
