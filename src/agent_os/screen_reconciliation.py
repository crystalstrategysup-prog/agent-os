"""Explicit evidence-bound pending reconciliation for cold same-SID adoption.

Never clears a mailbox, restarts a worker, accepts business work or replays an
operation. Native evidence provenance and owner exclusion belong to the caller's
trusted accessor/guard, not a self-authenticating JSON file.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from .safeio import create_only_bytes, digest, lock, within, _parse_json
from .screen_launch import LIMIT, worker_root
from .session_launch import LaunchError

SID = re.compile(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")


def _ref(path: Path, expected: str) -> dict:
    """Bound bytes before parsing; refuse devices, links and duplicate keys."""
    if not isinstance(expected, str) or not HASH.fullmatch(expected):
        raise LaunchError("reconciliation_hash_required", status="UNKNOWN")
    if path.is_symlink():
        raise LaunchError("reconciliation_evidence_unavailable", status="UNKNOWN")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
                raise LaunchError("reconciliation_evidence_limit", status="UNKNOWN")
            data = stream.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise LaunchError("reconciliation_evidence_limit", status="UNKNOWN")
        if hashlib.sha256(data).hexdigest() != expected:
            raise LaunchError("reconciliation_evidence_changed", status="UNKNOWN")
        value = _parse_json(data)
    except LaunchError:
        raise
    except (OSError, ValueError):
        raise LaunchError("reconciliation_evidence_unavailable", status="UNKNOWN") from None
    if not isinstance(value, dict):
        raise LaunchError("reconciliation_evidence_invalid", status="UNKNOWN")
    return value


def _path(home: Path, sid: str, operation: str) -> Path:
    return within(home, "state/screen-reconciliations/" + sid + "/" + operation + ".json")


def _ids(plan: dict) -> None:
    if (not isinstance(plan, dict) or plan.get("schema") != "agentos.screen-reconciliation-request/v1" or
            not isinstance(plan.get("old_name"), str) or
            not isinstance(plan.get("session_id"), str) or not SID.fullmatch(plan["session_id"]) or
            not isinstance(plan.get("operation_id"), str) or not SID.fullmatch(plan["operation_id"]) or
            not isinstance(plan.get("turn_id"), str) or not 1 <= len(plan["turn_id"]) <= 200):
        raise LaunchError("reconciliation_identity_invalid", status="UNKNOWN")


def _snapshot(home: Path, plan: dict) -> dict:
    _ids(plan)
    old = worker_root(home, plan.get("old_name", ""))
    op, sid = plan["operation_id"], plan["session_id"]
    pins = plan.get("old_pins")
    response_name = "responses/" + op + ".json"
    required = {"identity.json", "bootstrap.json", "startup.json", "state.json",
                "pending.json", "request.json", response_name}
    if not isinstance(pins, dict) or not required <= pins.keys() or len(pins) > 32:
        raise LaunchError("reconciliation_original_pins_required", status="UNKNOWN")
    records = {}
    total_bytes = 0
    for name, sha in pins.items():
        if (not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts or
                not name or "\\" in name or "\0" in name):
            raise LaunchError("reconciliation_original_pin_invalid", status="UNKNOWN")
        path = within(old, name)
        if not path.resolve().is_relative_to(old.resolve()):
            raise LaunchError("reconciliation_original_pin_invalid", status="UNKNOWN")
        records[name] = _ref(path, sha)
        total_bytes += path.stat().st_size
        if total_bytes > 4 * LIMIT:
            raise LaunchError("reconciliation_original_input_limit", status="UNKNOWN")
    identity, state, startup, bootstrap, pending, message, response = (
        records[n] for n in ("identity.json", "state.json", "startup.json", "bootstrap.json",
                             "pending.json", "request.json", response_name))
    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        raise LaunchError("reconciliation_request_not_bound", status="UNKNOWN")
    original = bootstrap.get("request")
    if state.get("operation") != "dispatch" or state.get("operation_id") != op:
        raise LaunchError("reconciliation_state_operation_not_bound", status="UNKNOWN")
    if (not isinstance(original, dict) or message.get("operation") != "dispatch" or pending.get("operation") != "dispatch" or
            message.get("id") != op or pending.get("operation_id") != op or response.get("id") != op or
            pending.get("status") != "PENDING" or response.get("status") != "UNKNOWN" or
            not response.get("error") or state.get("status") != "FAILED" or
            not isinstance(identity.get("worker_id"), str) or not identity["worker_id"] or
            any(r.get("worker_id") != identity["worker_id"] for r in (state, message, response)) or
            not isinstance(state.get("connection_id"), str) or not state["connection_id"] or
            any(r.get("connection_id") != state["connection_id"] for r in (message, response, startup)) or
            state.get("session_id") != sid or startup.get("session_id") != sid or
            pending.get("request_sha256") != digest(message) or response.get("request_sha256") != digest(message) or
            identity.get("request_sha256") != digest(original) or
            identity.get("bootstrap_sha256") != digest(bootstrap) or
            digest(payload.get("request")) != digest(original) or payload.get("startup") != startup or
            not isinstance(payload.get("envelope"), str) or not payload["envelope"].strip()):
        raise LaunchError("reconciliation_request_not_bound", status="UNKNOWN")
    evidence = plan.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {"terminal", "commands", "effects"}:
        raise LaunchError("reconciliation_evidence_required", status="UNKNOWN")
    values = {}
    for kind, ref in evidence.items():
        if not isinstance(ref, dict) or not isinstance(ref.get("path"), str):
            raise LaunchError("reconciliation_evidence_required", status="UNKNOWN")
        value = _ref(Path(ref["path"]), ref.get("sha256"))
        if (value.get("schema") != "agentos.screen-" + kind + "-evidence/v1" or
                value.get("session_id") != sid or value.get("turn_id") != plan["turn_id"] or
                value.get("operation_id") != op or value.get("envelope_sha256") != digest(payload["envelope"])):
            raise LaunchError("reconciliation_terminal_or_effects_not_bound", status="UNKNOWN")
        values[kind] = value
    terminal, commands, effects = (values[k] for k in ("terminal", "commands", "effects"))
    if (terminal.get("status") != "completed" or terminal.get("source_verified") is not True or
            commands.get("coverage") != "COMPLETE" or effects.get("coverage") != "COMPLETE"):
        raise LaunchError("reconciliation_incomplete_evidence", status="UNKNOWN")
    items, dispositions = commands.get("commands"), effects.get("commands")
    if not isinstance(items, list) or not items or len(items) > 2048 or not isinstance(dispositions, list):
        raise LaunchError("reconciliation_commands_required", status="UNKNOWN")
    ids = []
    for item in items:
        if (not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or
                not isinstance(item.get("command_sha256"), str) or not HASH.fullmatch(item["command_sha256"]) or
                type(item.get("exit_code")) is not int):
            raise LaunchError("reconciliation_command_invalid", status="UNKNOWN")
        ids.append(item["id"])
    if len(set(ids)) != len(ids) or len(dispositions) != len(ids):
        raise LaunchError("reconciliation_effect_coverage_invalid", status="UNKNOWN")
    effect_ids = []
    for item in dispositions:
        if (not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or
                not isinstance(item.get("disposition"), str) or item["disposition"] not in {"OBSERVED", "RECONCILED"} or
                not isinstance(item.get("evidence_refs"), list) or not item["evidence_refs"] or
                any(not isinstance(x, str) or not x for x in item["evidence_refs"]) or
                not isinstance(item.get("scope"), str) or not item["scope"]):
            raise LaunchError("reconciliation_effect_disposition_required", status="UNKNOWN")
        effect_ids.append(item.get("id"))
    if sorted(effect_ids) != sorted(ids):
        raise LaunchError("reconciliation_effect_coverage_invalid", status="UNKNOWN")
    return {"old": old, "records": records, "evidence": values}


def _absent(snapshot: dict) -> None:
    old = snapshot["old"]
    for pid in (snapshot["records"]["identity.json"].get("screen_pid"),
                snapshot["records"]["state.json"].get("worker_pid")):
        if type(pid) is not int or pid <= 1:
            raise LaunchError("reconciliation_old_pid_unknown", status="UNKNOWN")
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        except PermissionError:
            raise LaunchError("reconciliation_old_pid_unknown", status="UNKNOWN") from None
        else:
            raise LaunchError("reconciliation_old_writer_present", status="UNKNOWN")
    if (old / "worker.lock").exists() or (old / "worker.lock").is_symlink():
        raise LaunchError("reconciliation_old_lock_present", status="UNKNOWN")


def reconcile_pending(home: Path, plan: dict, *, reconciliation_guard) -> dict:
    """Publish one immutable receipt under a trusted, held owning guard.

    guard(plan) yields check(query), verifying native provenance, complete
    command/effect review and current owner/writer exclusion. This API does no
    mailbox call or native operation. Synthetic receipts grant no live authority.
    """
    # Freeze the input boundary even when a caller mutates its original object
    # or a guard accidentally changes the plan handed to it.
    try:
        raw_plan = json.dumps(plan, allow_nan=False).encode()
    except (TypeError, ValueError):
        raise LaunchError("reconciliation_plan_invalid", status="UNKNOWN") from None
    if len(raw_plan) > LIMIT:
        raise LaunchError("reconciliation_plan_limit", status="UNKNOWN")
    plan = json.loads(raw_plan)
    plan_sha = digest(plan)
    snapshot = _snapshot(home, plan)
    _absent(snapshot)
    if not callable(reconciliation_guard):
        raise LaunchError("reconciliation_live_guard_required", status="UNKNOWN")
    destination = _path(home, plan["session_id"], plan["operation_id"])
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock(destination.parent / "reconciliation.lock"), lock(snapshot["old"] / "control.lock"):
        if destination.exists() or destination.is_symlink():
            raise LaunchError("reconciliation_already_recorded", status="UNKNOWN")
        with reconciliation_guard(plan) as check:
            if digest(plan) != plan_sha:
                raise LaunchError("reconciliation_plan_changed", status="UNKNOWN")
            if not callable(check):
                raise LaunchError("reconciliation_live_guard_required", status="UNKNOWN")
            query = {"phase": "publish_reconciliation", "plan_sha256": digest(plan),
                     "session_id": plan["session_id"], "operation_id": plan["operation_id"],
                     "terminal_turn_id": plan["turn_id"], "evidence_sha256": digest(plan["evidence"])}
            result = check(query)
            if digest(plan) != plan_sha:
                raise LaunchError("reconciliation_plan_changed", status="UNKNOWN")
            if (not isinstance(result, dict) or any(result.get(k) != v for k, v in query.items()) or
                    type(result.get("observed_at")) not in (int, float) or
                    not 0 <= time.time() - result["observed_at"] <= 60 or
                    result.get("owner_exclusion_held") is not True or
                    not isinstance(result.get("owner_exclusion_token"), str) or not result["owner_exclusion_token"] or
                    result.get("source_writer_state") != "FREE" or
                    result.get("old_owned_lineage_absent") is not True or
                    result.get("native_evidence_verified") is not True or
                    result.get("command_effects_reviewed") is not True or
                    result.get("reviewed_plan_sha256") != digest(plan) or
                    not isinstance(result.get("reviewer"), str) or not result["reviewer"]):
                raise LaunchError("reconciliation_live_evidence_review_required", status="UNKNOWN")
            # Recheck after callbacks: a previously accepted read cannot mask
            # changed pending/terminal/effects or a writer appearing mid-review.
            _absent(_snapshot(home, plan))
            receipt = {"schema": "agentos.screen-reconciliation/v1", "status": "RECONCILED_FOR_COLD_ADOPTION",
                       "plan": plan, "plan_sha256": digest(plan), "review": result,
                       "original_status": "UNKNOWN", "original_pending_preserved": True,
                       "replay_authorized": False, "business_accepted": False}
            raw = (json.dumps(receipt, sort_keys=True, ensure_ascii=False) + "\n").encode()
            if len(raw) > LIMIT:
                raise LaunchError("reconciliation_receipt_limit", status="UNKNOWN")
            create_only_bytes(destination, raw)
    return {"operation_id": plan["operation_id"], "receipt_sha256": hashlib.sha256(raw).hexdigest()}


def verify_pending_reconciliation(home: Path, adoption: dict) -> dict:
    """Consume exact receipt and revalidate retained inputs; never reset them."""
    ref = adoption.get("pending_reconciliation")
    if (not isinstance(ref, dict) or not isinstance(ref.get("operation_id"), str) or
            not SID.fullmatch(ref["operation_id"]) or not isinstance(adoption.get("session_id"), str) or
            not SID.fullmatch(adoption["session_id"])):
        raise LaunchError("adoption_pending_requires_reconciliation", status="UNKNOWN")
    receipt = _ref(_path(home, adoption["session_id"], ref["operation_id"]), ref.get("receipt_sha256"))
    plan = receipt.get("plan")
    if (receipt.get("schema") != "agentos.screen-reconciliation/v1" or
            receipt.get("status") != "RECONCILED_FOR_COLD_ADOPTION" or not isinstance(plan, dict) or
            receipt.get("plan_sha256") != digest(plan) or plan.get("old_name") != adoption.get("old_name") or
            plan.get("session_id") != adoption["session_id"] or plan.get("operation_id") != ref["operation_id"] or
            receipt.get("original_pending_preserved") is not True or receipt.get("original_status") != "UNKNOWN" or
            receipt.get("replay_authorized") is not False or receipt.get("business_accepted") is not False):
        raise LaunchError("adoption_reconciliation_not_bound", status="UNKNOWN")
    review = receipt.get("review")
    if (not isinstance(review, dict) or review.get("plan_sha256") != digest(plan) or
            review.get("reviewed_plan_sha256") != digest(plan) or
            review.get("evidence_sha256") != digest(plan.get("evidence")) or
            review.get("operation_id") != plan["operation_id"] or
            review.get("session_id") != plan["session_id"] or
            review.get("terminal_turn_id") != plan.get("turn_id") or
            review.get("phase") != "publish_reconciliation" or
            review.get("native_evidence_verified") is not True or
            review.get("command_effects_reviewed") is not True or
            review.get("owner_exclusion_held") is not True or
            review.get("source_writer_state") != "FREE" or
            review.get("old_owned_lineage_absent") is not True or not review.get("reviewer")):
        raise LaunchError("adoption_reconciliation_review_required", status="UNKNOWN")
    _snapshot(home, plan)
    return receipt
