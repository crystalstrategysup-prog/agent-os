"""Bounded append-only successor selection, never journal reset or authority."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat

from .safeio import _parse_json, digest, within
from .screen_launch import LIMIT, _read, worker_root
from .screen_reconciliation import HASH, SID, verify_pending_reconciliation
from .session_launch import LaunchError


def _journal(path: Path) -> tuple[dict, str]:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
                raise LaunchError("successor_journal_limit", status="UNKNOWN")
            raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise LaunchError("successor_journal_limit", status="UNKNOWN")
        value = _parse_json(raw)
    except LaunchError:
        raise
    except (OSError, ValueError):
        raise LaunchError("successor_journal_unavailable", status="UNKNOWN") from None
    if not isinstance(value, dict):
        raise LaunchError("successor_journal_invalid", status="UNKNOWN")
    return value, hashlib.sha256(raw).hexdigest()


def _edge(home: Path, sid: str, predecessor: str) -> Path:
    return within(home, "state/screen-adoption-successors/" + sid + "/" + predecessor + ".json")


def _successful(row: dict, sid: str) -> dict:
    result = row.get("result")
    if (row.get("schema") not in {"agentos.screen-adoption/v1", "agentos.screen-adoption-successor/v1"} or
            row.get("session_id") != sid or row.get("status") != "DISPATCH_OBSERVED" or
            not isinstance(result, dict) or result.get("phase") != "DISPATCH_OBSERVED" or
            result.get("session_id") != sid):
        raise LaunchError("successor_predecessor_not_successful", status="UNKNOWN")
    work, startup, screen = (result.get(k) for k in ("work", "startup", "screen"))
    if (not all(isinstance(v, dict) for v in (work, startup, screen)) or
            work.get("status") != "completed" or work.get("session_id") != sid or
            work.get("delivery") != "accepted" or work.get("proof_source") != "same_connection_provider_events" or
            not isinstance(work.get("turn_id"), str) or not work["turn_id"] or
            startup.get("session_id") != sid or screen.get("session_id") != sid or
            not isinstance(row.get("request_sha256"), str) or not HASH.fullmatch(row["request_sha256"]) or
            result.get("request_sha256") != row["request_sha256"] or
            result.get("adoption_sha256") != row.get("adoption_sha256")):
        raise LaunchError("successor_predecessor_evidence_incomplete", status="UNKNOWN")
    if row["schema"] == "agentos.screen-adoption-successor/v1":
        link = row.get("successor")
        if not isinstance(link, dict) or link.get("destination_name") != screen.get("name"):
            raise LaunchError("successor_chain_link_invalid", status="UNKNOWN")
    return result


@dataclass(frozen=True)
class SuccessorSelection:
    journal: Path
    binding: dict
    pins: tuple[tuple[Path, str], ...]

    def verify(self) -> None:
        for path, expected in self.pins:
            if _journal(path)[1] != expected:
                raise LaunchError("successor_predecessor_changed", status="UNKNOWN")


def select_successor(home: Path, name: str, adoption: dict) -> SuccessorSelection:
    """Call under the existing SID lock; select only the successful chain tip.

    No input path is trusted as a predecessor. A pending reconciliation and
    fresh held owner guard remain mandatory; this helper grants no authority.
    """
    supplied, sid = adoption.get("successor"), adoption.get("session_id")
    if (not isinstance(supplied, dict) or set(supplied) != {"predecessor_sha256"} or
            not isinstance(supplied["predecessor_sha256"], str) or not HASH.fullmatch(supplied["predecessor_sha256"]) or
            not isinstance(sid, str) or not SID.fullmatch(sid)):
        raise LaunchError("successor_reference_invalid", status="UNKNOWN")
    # Validate destination grammar with the existing canonical route, no writes.
    worker_root(home, name)
    path = within(home, "state/screen-adoptions/" + sid + ".json")
    pins = []
    if "pre_resume_history" in adoption:
        from .screen_pre_resume import history_root
        path, history_pins = history_root(home, adoption)
        pins.extend(history_pins)
    for _ in range(32):
        row, sha = _journal(path)
        result = _successful(row, sid)
        pins.append((path, sha))
        child = _edge(home, sid, sha)
        if sha == supplied["predecessor_sha256"]:
            if child.exists() or child.is_symlink():
                raise LaunchError("successor_predecessor_already_consumed", status="UNKNOWN")
            break
        if not child.exists():
            raise LaunchError("successor_predecessor_not_current", status="UNKNOWN")
        next_row, _ = _journal(child)
        if (next_row.get("schema") != "agentos.screen-adoption-successor/v1" or
                not isinstance(next_row.get("successor"), dict) or
                next_row["successor"].get("predecessor_sha256") != sha):
            raise LaunchError("successor_chain_link_invalid", status="UNKNOWN")
        path = child
    else:
        raise LaunchError("successor_chain_bound", status="UNKNOWN")
    reconciled = verify_pending_reconciliation(home, adoption)
    plan = reconciled["plan"]
    old = worker_root(home, adoption["old_name"])
    identity, state, startup, bootstrap = (_read(old / n) for n in
                                          ("identity.json", "state.json", "startup.json", "bootstrap.json"))
    screen = result["screen"]
    identity_keys = ("worker_id", "name", "screen_pid", "request_sha256", "bootstrap_sha256")
    state_keys = (*identity_keys, "worker_pid", "connection_id", "socket")
    if (screen.get("name") != adoption["old_name"] or name == adoption["old_name"] or
            any(k not in screen or screen[k] != identity.get(k) for k in identity_keys) or
            any(k not in screen or screen[k] != state.get(k) for k in state_keys) or
            startup != result["startup"] or digest(bootstrap.get("request")) != row["request_sha256"]):
        raise LaunchError("successor_predecessor_worker_mismatch", status="UNKNOWN")
    if (screen.get("operation") != "dispatch" or not isinstance(screen.get("operation_id"), str) or
            not SID.fullmatch(screen["operation_id"]) or plan["operation_id"] == screen["operation_id"] or
            plan["turn_id"] == result["work"]["turn_id"]):
        raise LaunchError("successor_distinct_later_operation_required", status="UNKNOWN")
    binding = {"predecessor_sha256": sha, "predecessor_worker_sha256": digest({k: screen[k] for k in state_keys}),
               "destination_name": name, "old_name": adoption["old_name"],
               "later_operation_id": plan["operation_id"], "reviewed_terminal_turn_id": plan["turn_id"],
               "reconciliation_receipt_sha256": adoption["pending_reconciliation"]["receipt_sha256"]}
    return SuccessorSelection(child, binding, tuple(pins))
