"""Bounded metadata at the original handoff refusal; never a scanner or retry.

Metadata is local same-owner evidence, not authorization or proof of a credential.
Only precomputed, explicitly supplied capture metadata may enrich an asset hash.
No source, blob, manifest body, exception text or match is read or serialized.
"""
from __future__ import annotations

import json
import os
import re
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .safeio import GateError, _parse_json, create_only_bytes, within

SCHEMA = "agentos.handoff-failure-diagnostic/v1"
ENVELOPE = "agentos.handoff-failure-envelope/v1"
MAX_RECEIPT = 16 * 1024
ASSET_FIELDS = {"asset_id", "path", "sha256", "bytes"}
FIELDS = {"schema", "status", "error", "category", "task_id", "revision", "profile",
          "attempt_id", "attempted_at", "recorded_at", "session_id", "turn_id",
          "stage", "payload_fingerprint", "source_snapshot_sha256", "asset",
          "capture_manifest", "candidate_ref", "gaps"}
STAGES = {"library_open", "source_snapshot", "document_check", "capture",
          "build_handoff", "publish_handoff", "verify_handoff", "embedded_asset"}


def _id(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,199}", value) else None


def _task(value):
    return value if isinstance(value, str) and re.fullmatch(r"task-[0-9a-f]{16}", value) else None


def _attempt(value):
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) else None


def _digest(value):
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) else None


def _path(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 1024:
        return None
    parts = value.split("/")
    if len(parts) > 32 or any(not p or p.startswith(".") for p in parts):
        return None
    return value if all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", p) for p in parts) else None


def asset_context(item, size):
    """Called only for the actual failed embedded put. No bytes accepted here."""
    if not isinstance(item, dict):
        return None
    # Library._build scans before its complete manifest validation, so the
    # proposed manifest path is not yet admitted. Only lifecycle capture may
    # later supply an already checked path. Never echo that proposal here.
    return {"asset_id": _id(item.get("asset_id")), "path": None,
            "sha256": None, "bytes": size if type(size) is int and 0 <= size <= 16 * 1024 * 1024 else None}


def new_attempt():
    # Diagnostics must not introduce a failure into a previously valid workflow.
    try:
        return uuid.uuid4().hex, datetime.now(timezone.utc).isoformat()
    except Exception:
        return None, None


def _receipt_path(task_id, attempt_id):
    if _task(task_id) is None or _attempt(attempt_id) is None:
        raise GateError("diagnostic_identity_invalid")
    return f".agentos/tasks/{task_id}/diagnostics/{attempt_id}.json"


def _asset(value, captures):
    if not isinstance(value, dict) or set(value) != ASSET_FIELDS:
        return None
    result = asset_context(value, value.get("bytes"))
    # Lifecycle capture already checked SHA against the exact immutable bytes.
    # No hash is recomputed and no caller/source/object is opened for diagnostics.
    known = captures.get(result["asset_id"]) if isinstance(captures, dict) else None
    if isinstance(known, dict) and known.get("bytes") == result["bytes"]:
        result["sha256"] = _digest(known.get("sha256"))
        result["path"] = _path(known.get("path"))
    return result


def _gaps(value):
    gaps = ["specific_category"] + [key for key in ("session_id", "turn_id", "payload_fingerprint",
                           "source_snapshot_sha256", "capture_manifest", "candidate_ref")
            if value[key] is None]
    for key in ASSET_FIELDS:
        if value["asset"] is None or value["asset"][key] is None:
            gaps.append("asset." + key)
    return sorted(gaps)


def _timestamp(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 40:
        return False
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return t.tzinfo is not None and t.utcoffset().total_seconds() == 0
    except ValueError:
        return False


def _reference(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"object_id", "locator", "size_bytes", "media_type"}:
        return None
    oid = value.get("object_id")
    if (not isinstance(oid, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", oid)
            or not isinstance(value["locator"], str)
            or not re.fullmatch(r"aos://[A-Za-z0-9_.:@-]{1,160}/objects/sha256/" + oid[7:], value["locator"])
            or type(value["size_bytes"]) is not int or not 0 <= value["size_bytes"] <= 16 * 1024 * 1024
            or value["media_type"] != "application/json"):
        return None
    return {k:value[k] for k in ("object_id", "locator", "size_bytes", "media_type")}


def validate_receipt(value):
    """Reject extra/unsafe data rather than returning an arbitrary saved JSON."""
    ok = isinstance(value, dict) and set(value) == FIELDS
    if not ok:
        raise GateError("diagnostic_receipt_invalid")
    ok = (value["schema"] == SCHEMA and value["status"] == "BLOCKED"
          and value["error"] == value["category"] == "SECRET_DETECTED"
          and _task(value["task_id"]) is not None and _attempt(value["attempt_id"]) is not None
          and type(value["revision"]) is int and 1 <= value["revision"] <= 2147483647
          and value["profile"] in {"checkpoint", "completion"} and value["stage"] in STAGES
          and _timestamp(value["attempted_at"]) and _timestamp(value["recorded_at"]))
    for key in ("session_id", "turn_id"):
        ok = ok and (value[key] is None or _id(value[key]) == value[key])
    for key in ("payload_fingerprint", "source_snapshot_sha256"):
        ok = ok and (value[key] is None or _digest(value[key]) == value[key])
    # No separate capture-manifest ref exists at this producer boundary.
    ok = ok and value["capture_manifest"] is None
    ok = ok and (value["candidate_ref"] is None or _reference(value["candidate_ref"]) == value["candidate_ref"])
    asset = value["asset"]
    if asset is not None:
        ok = ok and isinstance(asset, dict) and set(asset) == ASSET_FIELDS
        if ok:
            ok = (asset["asset_id"] is None or _id(asset["asset_id"]) == asset["asset_id"])
            ok = ok and (asset["path"] is None or _path(asset["path"]) == asset["path"])
            ok = ok and (asset["sha256"] is None or _digest(asset["sha256"]) == asset["sha256"])
            ok = ok and (asset["bytes"] is None or type(asset["bytes"]) is int and 0 <= asset["bytes"] <= 16 * 1024 * 1024)
    if not ok or value["gaps"] != _gaps(value):
        raise GateError("diagnostic_receipt_invalid")
    return value


def record_failure(root, task, exc, *, profile, attempt, stage, fingerprint=None,
                   source_sha=None, captures=None, candidate_ref=None):
    """Best effort only: original caller must always re-raise its original error.

    No diagnostic for a non-SECRET error; no fallback sink; no task transition.
    Partial write/durability outcomes remain UNKNOWN, never success or a retry.
    """
    if getattr(exc, "code", None) != "SECRET_DETECTED":
        return None
    attempt_id, started = attempt
    envelope = None
    try:
        task_id = _task(task.get("id"))
        if not task_id or _attempt(attempt_id) is None or not _timestamp(started):
            return None
        rel = _receipt_path(task_id, attempt_id)
        envelope = {"schema": ENVELOPE, "attempt_id": attempt_id,
                    "metadata_status": "WRITE_FAILED_OR_UNKNOWN", "receipt": None}
        asset = _asset(getattr(exc, "handoff_asset", None), captures)
        value = {"schema": SCHEMA, "status": "BLOCKED", "error": "SECRET_DETECTED",
                 "category": "SECRET_DETECTED", "task_id": task_id, "revision": task.get("revision"),
                 "profile": profile, "attempt_id": attempt_id, "attempted_at": started,
                 "recorded_at": datetime.now(timezone.utc).isoformat(),
                 "session_id": _id(task.get("session_id")), "turn_id": _id(task.get("turn_id")),
                 "stage": "embedded_asset" if asset is not None else stage,
                 "payload_fingerprint": _digest(fingerprint), "source_snapshot_sha256": _digest(source_sha),
                 "asset": asset, "capture_manifest": None, "candidate_ref": _reference(candidate_ref), "gaps": []}
        value["gaps"] = _gaps(value)
        validate_receipt(value)
        raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        if len(raw) > MAX_RECEIPT:
            return envelope
        path = within(root, rel)
        # The existing owning task must exist. No alternate project or sink.
        task_path = within(root, f".agentos/tasks/{task_id}/task.json", allow_missing=False)
        if not task_path.is_file() or task_path.is_symlink():
            return envelope
        create_only_bytes(path, raw, mode=0o600)
        from .handoff_store import sync_directory
        sync_directory(path.parent)
        sync_directory(path.parent.parent)
        # Verify bounded receipt only; never open an asset or source.
        loaded = _read(path)
        if loaded != raw:
            return envelope
        from .safeio import sha
        envelope.update(metadata_status="SAVED", receipt={"path": rel, "bytes": len(raw), "sha256": sha(raw)})
    except Exception:
        # Includes receipt construction, path/size/write/fsync/readback failures.
        # No exception text can leak, and the original guard remains decisive.
        pass
    return envelope


def public_envelope(exc):
    value = getattr(exc, "handoff_diagnostic", None)
    if not isinstance(value, dict) or set(value) != {"schema", "attempt_id", "metadata_status", "receipt"}:
        return None
    if value["schema"] != ENVELOPE or _attempt(value["attempt_id"]) is None or value["metadata_status"] not in {"SAVED", "WRITE_FAILED_OR_UNKNOWN"}:
        return None
    r = value["receipt"]
    if r is not None:
        if not isinstance(r, dict) or set(r) != {"path", "bytes", "sha256"}:
            return None
        if (not isinstance(r["path"], str) or not re.fullmatch(r"\.agentos/tasks/task-[0-9a-f]{16}/diagnostics/" + value["attempt_id"] + r"\.json", r["path"])
                or type(r["bytes"]) is not int or not 0 < r["bytes"] <= MAX_RECEIPT or _digest(r["sha256"]) is None):
            return None
    if (value["metadata_status"] == "SAVED") != (r is not None):
        return None
    return value


def _read(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_RECEIPT:
            raise GateError("diagnostic_receipt_invalid")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_RECEIPT + 1)
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(raw) > MAX_RECEIPT or len(raw) != before.st_size or any(getattr(before,k) != getattr(after,k) for k in fields):
            raise GateError("diagnostic_receipt_invalid")
        return raw
    finally:
        os.close(fd)


def read_failure(root, task_id, revision, attempt_id=None):
    """Read the exact saved record; never discover objects, scan or reconstruct."""
    if _task(task_id) is None or type(revision) is not int or not 1 <= revision <= 2147483647:
        raise GateError("diagnostic_identity_invalid")
    from .project import load_task
    task = load_task(root, task_id)
    if type(task.get("revision")) is not int or revision > task["revision"]:
        raise GateError("diagnostic_revision_invalid")
    unavailable = {"schema": SCHEMA, "status": "METADATA_UNAVAILABLE", "task_id": task_id,
                   "revision": revision, "attempt_id": attempt_id,
                   "gaps": ["saved_receipt", "failing_asset", "asset_path", "asset_sha256", "specific_category"],
                   "reconstructed": False, "scanner_invoked": False}
    if attempt_id is None:
        unavailable["gaps"].insert(0, "attempt_id")
        return unavailable
    path = within(root, _receipt_path(task_id, attempt_id))
    if not path.exists():
        return unavailable
    try:
        value = validate_receipt(_parse_json(_read(path)))
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        # Do not expose a parser's duplicate key or malformed input text even
        # through an explicit exception cause in this new metadata API.
        raise GateError("diagnostic_receipt_invalid") from None
    if (value["task_id"], value["revision"], value["attempt_id"]) != (task_id, revision, attempt_id):
        raise GateError("diagnostic_receipt_identity_mismatch")
    return {"schema": SCHEMA, "status": "SAVED_METADATA", "metadata": value,
            "reconstructed": False, "scanner_invoked": False}
