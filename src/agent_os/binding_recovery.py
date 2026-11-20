"""Explicit missing-root recovery of one chat binding, never of its old task.

The shared turns lock serializes cooperating AgentOS writers. Like safeio, this
is not a security boundary against a hostile process running as the same user.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import tempfile

from .safeio import (
    GateError, MAX_JSON, _parse_json, atomic_bytes, atomic_json,
    create_only_bytes, digest, identifier, lock, nonempty, now, sha, within,
)

MAX_TURN_RECEIPTS = 10000
MAX_REGISTRY_BYTES = 32 * 1024 * 1024
REQUEST_SCHEMA = "agentos.binding-recovery-request/v1"
JOURNAL_SCHEMA = "agentos.binding-recovery/v1"


def _exact_string(value: str, name: str, limit: int = 200) -> str:
    if nonempty(value, name, limit) != value:
        raise GateError("binding_recovery_exact_value_required:" + name)
    return value


def _canonical_root(root: str | Path) -> str:
    value = _exact_string(str(root), "root", 4096)
    if (not os.path.isabs(value) or os.path.normpath(value) != value
            or value.startswith("//") or "\x00" in value or "\\" in value):
        raise GateError("binding_recovery_absolute_canonical_root_required")
    return value


def _require_missing_root(root: str) -> None:
    """Only ENOENT proves absence; never resolve or follow a symlink."""
    selected = Path(root)
    for path in [*reversed(selected.parents), selected]:
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            return
        except OSError as exc:
            raise GateError("binding_recovery_root_unverifiable") from exc
        if stat.S_ISLNK(mode):
            raise GateError("binding_recovery_root_symlink_refused")
        if not stat.S_ISDIR(mode):
            raise GateError("binding_recovery_root_not_directory")
    raise GateError("binding_recovery_old_root_present")


def _directory_identity(path: Path) -> tuple[int, int]:
    for part in [*reversed(path.parents), path]:
        try:
            info = part.lstat()
        except OSError as exc:
            raise GateError("binding_recovery_state_directory_unverifiable") from exc
        if not stat.S_ISDIR(info.st_mode):
            raise GateError("binding_recovery_plain_state_directory_required")
    return info.st_dev, info.st_ino


def _file_identity(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _read_receipt(path: Path) -> tuple[bytes, dict]:
    """Read one bounded, stable regular JSON file without following links."""
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise GateError("binding_recovery_regular_receipt_required")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if _file_identity(opened) != _file_identity(before):
                raise GateError("binding_recovery_receipt_changed")
            raw = stream.read(MAX_JSON + 1)
            after = os.fstat(stream.fileno())
        if (_file_identity(before) != _file_identity(after)
                or _file_identity(after) != _file_identity(path.lstat())):
            raise GateError("binding_recovery_receipt_changed")
    except OSError as exc:
        raise GateError("binding_recovery_receipt_unreadable") from exc
    if len(raw) > MAX_JSON:
        raise GateError("binding_recovery_receipt_size_limit")
    try:
        value = _parse_json(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise GateError("binding_recovery_invalid_receipt") from exc
    if not isinstance(value, dict):
        raise GateError("binding_recovery_invalid_receipt")
    return raw, value


def _require_entered(value: dict, request: dict) -> None:
    expected = {
        "schema": "agentos.turn/v1", "status": "ENTERED",
        "session_id": request["session_id"], "turn_id": request["previous_turn"],
        "task_id": request["task_id"], "root": request["root"],
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise GateError("binding_recovery_receipt_mismatch")


def _check_executor_conflicts(home: Path, session: str, root: str, task: str) -> None:
    """Check registered bindings; historical dispatch claims are not live leases."""
    directory = within(home, "state/turns")
    _directory_identity(directory)
    total = 0
    with os.scandir(directory) as entries:
        for count, entry in enumerate(entries, 1):
            if count > MAX_TURN_RECEIPTS:
                raise GateError("binding_recovery_registry_limit")
            if not entry.name.endswith(".json") or entry.name == digest(session) + ".json":
                continue
            raw, value = _read_receipt(directory / entry.name)
            total += len(raw)
            if total > MAX_REGISTRY_BYTES:
                raise GateError("binding_recovery_registry_limit")
            other_session = _exact_string(value.get("session_id"), "registered_session_id")
            _exact_string(value.get("turn_id"), "registered_turn_id")
            other_root = _canonical_root(value.get("root"))
            if (value.get("schema") != "agentos.turn/v1"
                    or entry.name != digest(other_session) + ".json"):
                raise GateError("binding_recovery_registry_invalid")
            if value.get("status") == "ENTERED":
                other_task = identifier(value.get("task_id"))
                if other_root == root or other_task == task:
                    raise GateError("binding_recovery_executor_conflict")
            elif (value.get("status") not in {"INTAKE_REQUIRED", "OBSERVATION_RECORDED"}
                    or value.get("task_id") is not None):
                raise GateError("binding_recovery_registry_invalid")


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _after_receipt(request: dict, recovery_id: str, prepared_at: str) -> dict:
    return {
        "schema": "agentos.turn/v1", "session_id": request["session_id"],
        "turn_id": request["turn_id"], "root": request["root"], "task_id": None,
        "status": "INTAKE_REQUIRED", "at": prepared_at, "hook_seen": False,
        "source": "standalone_cli", "recovery_id": recovery_id,
    }


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _publish_archive(archive: Path, request: dict, before: bytes) -> None:
    parent = archive.parent
    parent.mkdir(mode=0o700, exist_ok=True)
    _directory_identity(parent)
    _fsync_directory(parent.parent)
    # Publish a complete bundle. An interruption during staging never exposes a
    # partial authoritative archive or changes the active receipt.
    staging = Path(tempfile.mkdtemp(prefix=".preparing-" + archive.name[:12] + "-", dir=parent))
    prepared_at = now()
    after = _json_bytes(_after_receipt(request, archive.name, prepared_at))
    journal = {
        "schema": JOURNAL_SCHEMA, "recovery_id": archive.name, "state": "PREPARED",
        "before_sha256": sha(before), "after_sha256": sha(after),
        "prepared_at": prepared_at,
    }
    for name, data in {
        "receipt.before.json": before, "receipt.after.json": after,
        "request.json": _json_bytes(request), "journal.json": _json_bytes(journal),
    }.items():
        create_only_bytes(staging / name, data)
    _fsync_directory(staging)
    if archive.exists() or archive.is_symlink():
        raise GateError("binding_recovery_archive_already_exists")
    os.rename(staging, archive)
    _fsync_directory(parent)


def _load_archive(archive: Path, request: dict) -> tuple[bytes, bytes, dict]:
    _directory_identity(archive)
    _, saved_request = _read_receipt(archive / "request.json")
    before, original = _read_receipt(archive / "receipt.before.json")
    after, _ = _read_receipt(archive / "receipt.after.json")
    _, journal = _read_receipt(archive / "journal.json")
    if (saved_request != request or digest(saved_request) != archive.name
            or sha(before) != request["expected_receipt_sha256"]
            or journal.get("schema") != JOURNAL_SCHEMA
            or journal.get("recovery_id") != archive.name
            or journal.get("before_sha256") != sha(before)
            or journal.get("after_sha256") != sha(after)
            or journal.get("state") not in {"PREPARED", "COMMITTED"}):
        raise GateError("binding_recovery_archive_integrity_mismatch")
    _require_entered(original, request)
    at = _exact_string(journal.get("prepared_at"), "prepared_at")
    if after != _json_bytes(_after_receipt(request, archive.name, at)):
        raise GateError("binding_recovery_archive_integrity_mismatch")
    if journal["state"] == "COMMITTED":
        _exact_string(journal.get("committed_at"), "committed_at")
    return before, after, journal


def _commit_receipt(path: Path, expected_bytes: bytes, new_bytes: bytes) -> None:
    parent_identity = _directory_identity(path.parent)
    current, _ = _read_receipt(path)
    if current != expected_bytes:
        raise GateError("binding_recovery_compare_and_swap_failed")
    if _directory_identity(path.parent) != parent_identity:
        raise GateError("binding_recovery_state_directory_changed")
    atomic_bytes(path, new_bytes)
    _fsync_directory(path.parent)


def _mark_committed(archive: Path, journal: dict) -> None:
    if journal["state"] != "COMMITTED":
        atomic_json(archive / "journal.json", {
            **journal, "state": "COMMITTED", "committed_at": now(),
        })
    _fsync_directory(archive)


def recover_binding(
    root: str | Path,
    user_home: Path,
    *,
    session_id: str,
    previous_turn: str,
    turn_id: str,
    task_id: str,
    expected_receipt_sha256: str,
    allow_unverifiable_detach: bool = False,
) -> dict:
    """Detach exactly one absent-root binding with an immutable recovery record.

    Retry the same request after an uncertain result. Only its original receipt
    or exact planned postimage can be reconciled; later entries are never reset.
    The permission flag acknowledges that task/external executor state cannot be
    verified. It confers no task completion, readiness or execution authority.
    """
    from .overlay import validate_roots
    from .turns import turn_path

    root = _canonical_root(root)
    for name, value in (("session_id", session_id), ("previous_turn", previous_turn),
                        ("turn_id", turn_id)):
        _exact_string(value, name)
    identifier(task_id)
    if previous_turn == turn_id:
        raise GateError("next_turn_must_be_new")
    if (not isinstance(expected_receipt_sha256, str)
            or not re.fullmatch(r"[a-f0-9]{64}", expected_receipt_sha256)):
        raise GateError("binding_recovery_expected_sha256_required")
    if allow_unverifiable_detach is not True:
        raise GateError("binding_recovery_unverifiable_detach_permission_required")
    home = user_home.expanduser().absolute()
    validate_roots(home)
    _directory_identity(home / "state" / "turns")
    request = {
        "schema": REQUEST_SCHEMA, "session_id": session_id,
        "previous_turn": previous_turn, "turn_id": turn_id, "task_id": task_id,
        "root": root, "expected_receipt_sha256": expected_receipt_sha256,
        "allow_unverifiable_detach": True,
    }
    recovery_id = digest(request)
    with lock(within(home, "state/turns.lock")):
        path = turn_path(home, session_id)
        current, value = _read_receipt(path)
        archive = within(home, "state/binding-recoveries/" + recovery_id)
        existed = archive.exists()
        if existed:
            before, after, journal = _load_archive(archive, request)
            # A failed flush after a successful rename can leave a visible but
            # not yet durable bundle or journal. Re-establish durability first.
            _fsync_directory(archive)
            _fsync_directory(archive.parent)
            _fsync_directory(archive.parent.parent)
            if current == after:
                # Receipt publication can precede journal completion at a crash.
                # No binding change is performed on this reconciliation path.
                _fsync_directory(path.parent)
                _mark_committed(archive, journal)
                replayed = True
            elif current == before and journal["state"] == "PREPARED":
                replayed = False
            else:
                raise GateError("binding_recovery_binding_changed_since_recovery")
        else:
            if sha(current) != expected_receipt_sha256:
                raise GateError("binding_recovery_compare_and_swap_failed")
            _require_entered(value, request)
            replayed = False
        if not replayed:
            _require_missing_root(root)
            _check_executor_conflicts(home, session_id, root, task_id)
            if not existed:
                _publish_archive(archive, request, current)
                before, after, journal = _load_archive(archive, request)
            # The original bytes and prepared journal are durable before the
            # last precondition checks and CAS publication of the unbound turn.
            _check_executor_conflicts(home, session_id, root, task_id)
            _require_missing_root(root)
            _commit_receipt(path, before, after)
            _mark_committed(archive, journal)
    return {
        "status": "INTAKE_REQUIRED", "session_id": session_id, "turn_id": turn_id,
        "root": root, "task_id": None, "previous_task": task_id,
        "recovery_id": recovery_id, "archive": str(archive), "replayed": replayed,
        "task_state_verified": False, "old_task_changed": False,
        "native_hook_proven": False, "authority_granted": False,
        "production_authorized": False,
    }
