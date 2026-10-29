"""Guarded cold owning-transport adoption; never stops or resets an old worker."""
from __future__ import annotations

import hashlib
import os
import re
import stat
import time
from pathlib import Path

from .safeio import atomic_json, digest, lock
from .screen_launch import LIMIT, ScreenLaunchProvider, _read, worker_root
from .session_launch import LaunchError, LaunchJournal, launch, validate_request

SID = re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\Z")


def _old_readback(home: Path, adoption: dict) -> tuple[Path, dict]:
    """Current local checks supplement, never replace, the held owning guard."""
    sid = adoption.get("session_id")
    if not isinstance(sid, str) or not SID.fullmatch(sid):
        raise LaunchError("adoption_session_invalid")
    old = worker_root(home, adoption.get("old_name", ""))
    pins = adoption.get("old_pins")
    required = {"identity.json", "bootstrap.json", "startup.json", "state.json"}
    if not isinstance(pins, dict) or not required <= set(pins) or len(pins) > 32:
        raise LaunchError("adoption_old_pins_required", status="UNKNOWN")
    total_bytes = 0
    for name, expected in pins.items():
        if (not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts
                or not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected)):
            raise LaunchError("adoption_old_pin_invalid")
        path = old / name
        if path.is_symlink() or not path.resolve().is_relative_to(old.resolve()):
            raise LaunchError("adoption_old_source_changed", status="UNKNOWN")
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT or total_bytes + info.st_size > 4 * LIMIT:
                    raise LaunchError("adoption_old_pin_input_limit", status="UNKNOWN")
                data = stream.read(LIMIT + 1)
        except OSError:
            raise LaunchError("adoption_old_source_unavailable", status="UNKNOWN") from None
        total_bytes += len(data)
        if len(data) > LIMIT or total_bytes > 4 * LIMIT:
            raise LaunchError("adoption_old_pin_input_limit", status="UNKNOWN")
        if hashlib.sha256(data).hexdigest() != expected:
            raise LaunchError("adoption_old_source_changed", status="UNKNOWN")
    identity, state, retained = (_read(old / p) for p in ("identity.json", "state.json", "startup.json"))
    if state.get("worker_id") != identity.get("worker_id") or state.get("session_id") != sid or retained.get("session_id") != sid:
        raise LaunchError("adoption_old_identity_changed", status="UNKNOWN")
    if (old / "pending.json").exists():
        raise LaunchError("adoption_pending_requires_reconciliation", status="UNKNOWN")
    for pid in (identity.get("screen_pid"), state.get("worker_pid")):
        if type(pid) is not int or pid <= 1:
            raise LaunchError("adoption_old_process_identity_unknown", status="UNKNOWN")
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        except PermissionError:
            raise LaunchError("adoption_old_process_state_unknown", status="UNKNOWN") from None
        else:
            raise LaunchError("adoption_old_worker_still_present", status="UNKNOWN")
    # The worker holds safeio.lock: a directory removed on normal exit, not a
    # persistent flock file. Existing paths require owning reconciliation;
    # never remove/recreate them or infer safety from an unlocked descriptor.
    path = old / "worker.lock"
    if path.exists() or path.is_symlink():
        raise LaunchError("adoption_old_lock_requires_reconciliation", status="UNKNOWN")
    return old, retained


def _live_guard(check, request: dict, adoption: dict, attempt: str, phase: str,
                worker: dict | None, owner_token: list) -> dict:
    record = check({"phase": phase, "attempt_id": attempt, "request_sha256": digest(request),
                    "adoption_sha256": digest(adoption), "new_worker": worker})
    if (not isinstance(record, dict) or record.get("phase") != phase
            or record.get("attempt_id") != attempt or record.get("request_sha256") != digest(request)
            or record.get("adoption_sha256") != digest(adoption)):
        raise LaunchError("adoption_live_guard_not_bound", status="UNKNOWN")
    stamp = record.get("observed_at")
    token = record.get("owner_exclusion_token")
    if (type(stamp) not in (int, float) or not 0 <= time.time() - stamp <= 60
            or not isinstance(token, str) or not 1 <= len(token) <= 200
            or record.get("owner_exclusion_held") is not True):
        raise LaunchError("adoption_live_owner_exclusion_required", status="UNKNOWN")
    if owner_token and token != owner_token[0]:
        raise LaunchError("adoption_owner_changed", status="UNKNOWN")
    if not owner_token:
        owner_token.append(token)
    # This is an independent authority/terminal/effects route, not proof from a
    # cached PID, old READY marker, absent pending, or a lock-file existence.
    expected_writer = "FREE" if phase == "before_transport" else "NEW_WORKER_OWNED"
    if (record.get("session_id") != adoption["session_id"]
            or record.get("terminal_effects_reconciled") is not True
            or record.get("old_owned_lineage_absent") is not True
            or not isinstance(record.get("terminal_turn_id"), str) or not record["terminal_turn_id"]
            or not record.get("evidence_ref") or record.get("source_writer_state") != expected_writer
            or worker is not None and record.get("new_worker_sha256") != digest(worker)):
        raise LaunchError("adoption_live_reconciliation_required", status="UNKNOWN")
    return record


def adopt_screen(home: Path, name: str, request: dict, adoption: dict, *, screen_binary: Path,
                 codex_binary: Path, environment: dict[str, str], adoption_guard,
                 dispatch_claim, target_guard=None, timeout: float = 30, work_timeout: float = 1800) -> dict:
    """Resume SAME SID once inside a caller-held live owning-exclusion context.

    adoption_guard(request, adoption) must be a context manager yielding a fresh
    callable check(query). Hold controller ownership across the entire context;
    do not hold the source-writer flock across new unchanged wrapper startup.
    Before transport it proves writer FREE; before resume/dispatch it proves the
    writer belongs to the supplied actual new-worker lineage. A record alone
    never supplies this independent owning implementation or authority.
    """
    validate_request(request)
    if not callable(adoption_guard):
        raise LaunchError("adoption_live_guard_required", status="UNKNOWN")
    _, retained = _old_readback(home, adoption)
    bootstrap = _read(worker_root(home, adoption["old_name"]) / "bootstrap.json")
    original_contract = {key: bootstrap["request"].get(key) for key in
                         ("original_goal", "scope", "acceptance", "context", "authority")}
    if request["context"].get("adopted_original_contract") != original_contract:
        raise LaunchError("adoption_original_contract_not_retained", status="UNKNOWN")
    if (bootstrap.get("codex_binary") != str(codex_binary)
            or bootstrap.get("codex_home") != environment.get("CODEX_HOME")
            or request["workspace"] != retained.get("workspace")
            or request["executor"] != bootstrap["request"]["executor"]):
        raise LaunchError("adoption_retained_environment_changed", status="UNKNOWN")
    if retained.get("sandbox") != "danger-full-access" or retained.get("approval_policy") != "never":
        raise LaunchError("adoption_permission_profile_unsupported", status="UNKNOWN")
    root = home / "state" / "screen-adoptions"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    journal = root / (adoption["session_id"] + ".json")
    # SID, not launch/operation ID: a renamed attempt cannot replay UNKNOWN.
    with lock(root / (adoption["session_id"] + ".lock")):
        if journal.exists():
            raise LaunchError("adoption_sid_requires_reconciliation", status="UNKNOWN", receipt=_read(journal))
        with adoption_guard(request, adoption) as check:
            if not callable(check):
                raise LaunchError("adoption_live_guard_required", status="UNKNOWN")
            receipt = {"schema": "agentos.screen-adoption/v1", "session_id": adoption["session_id"],
                       "request_sha256": digest(request), "adoption_sha256": digest(adoption),
                       "status": "RESERVED", "resume_may_have_started": False, "work_accepted": False}
            atomic_json(journal, receipt)
            owner_token = []

            class Adapter:
                inner = None

                def guarded(self, attempt, phase):
                    _old_readback(home, adoption)
                    worker = self.inner._state() if self.inner is not None else None
                    record = _live_guard(check, request, adoption, attempt, phase, worker, owner_token)
                    receipt[phase] = record
                    atomic_json(journal, receipt)

                def describe(self, bound, attempt):
                    self.attempt = attempt
                    self.guarded(attempt, "before_transport")
                    self.inner = ScreenLaunchProvider.start(home, name, bound, screen_binary=screen_binary,
                        codex_binary=codex_binary, environment=environment, timeout=timeout,
                        work_timeout=work_timeout, retained_startup=retained)
                    return self.inner.describe_adoption(bound, retained, attempt)

                def create(self, bound, attempt):
                    self.guarded(attempt, "before_resume")
                    receipt.update(status="RESUMING", resume_may_have_started=True)
                    atomic_json(journal, receipt)
                    return self.inner.resume(bound, retained, attempt)

                def probe(self, bound, startup, attempt):
                    return self.inner.probe(bound, startup, attempt)

                def dispatch(self, bound, startup, envelope):
                    self.guarded(startup["attempt_id"], "before_dispatch")
                    return self.inner.dispatch(bound, startup, envelope)

            adapter = Adapter()
            try:
                def guarded_claim():
                    adapter.guarded(adapter.attempt, "before_dispatch")
                    dispatch_claim()

                result = launch(request, adapter, target_guard=target_guard, dispatch_claim=guarded_claim,
                                journal=LaunchJournal(home, request["launch_id"]))
                result["screen"] = adapter.inner._state()
                result["original_startup"] = retained
                result["adopted_original_contract"] = original_contract
                result["adoption_sha256"] = digest(adoption)
                atomic_json(adapter.inner.root / "launch.json", result)
                receipt.update(status="DISPATCH_OBSERVED", result=result)
                atomic_json(journal, receipt)
                return result
            except BaseException:
                receipt["status"] = "RECONCILIATION_REQUIRED"
                atomic_json(journal, receipt)
                raise
