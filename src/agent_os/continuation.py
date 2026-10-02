"""Opt-in stage continuation and durable dispatch metadata, never a dispatcher.

The parent adapter owns authorization, provider I/O and receipt verification.
Unknown delivery stays owned until reconciled; this module never starts a worker.
"""
from __future__ import annotations

import argparse
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import continuation_causal as causal
from .safeio import (
    GateError,
    atomic_json,
    digest,
    lock,
    nonempty,
    now,
    read_json,
    within,
)

SCHEMA = "agentos.stage-continuation/v1"
ITEM_SCHEMA = "agentos.continuation-item/v2"
LEGACY_ITEM_SCHEMA = "agentos.continuation-item/v1"
RECEIPT_SCHEMA = "agentos.continuation-delivery-receipt/v2"
MAX_DELIVERIES = 128
KINDS = {"review", "next-stage", "owner-decision", "verify-target"}
STATES = {"PENDING", "CLAIMED", "DELIVERY_UNKNOWN", "ACKNOWLEDGED"}


def _timestamp(value: str) -> datetime:
    nonempty(value, "receipt_timestamp", 100)
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GateError("invalid_receipt_timestamp") from exc
    if result.tzinfo is None:
        raise GateError("receipt_timestamp_requires_timezone")
    return result.astimezone(UTC)


def _receipt_key(receipt: dict) -> str:
    if receipt.get('schema') == causal.RECEIPT_SCHEMA:
        return causal.receipt_key(receipt)
    evidence = ({"rejection_id": receipt["rejection_id"]}
                if receipt["status"] == "CONFIRMED_NOT_SENT"
                else {"user_event_id": receipt["user_event_id"], "later_activity_id": receipt["later_activity_id"]})
    return digest({"provider": receipt["provider"], "target_owner": receipt["target_owner"],
                   "status": receipt["status"], **evidence})


def _receipt_shape(receipt: dict, action: str) -> None:
    if not isinstance(receipt, dict):
        raise GateError("continuation_delivery_receipt_required")
    expected = {"schema", "attempt_id", "delivery_generation", "delivery_nonce",
                "target_owner", "provider", "checked_at", "status"}
    expected |= ({"user_event_id", "later_activity_id", "user_event_at", "later_activity_at"}
                 if action == "acknowledge" else {"rejection_id"})
    if set(receipt) != expected or receipt["schema"] != RECEIPT_SCHEMA:
        raise GateError("invalid_continuation_delivery_receipt")
    if receipt["status"] != ("ACCEPTED" if action == "acknowledge" else "CONFIRMED_NOT_SENT"):
        raise GateError("ambiguous_or_wrong_delivery_outcome")
    generation = receipt["delivery_generation"]
    if isinstance(generation, bool) or not isinstance(generation, int) or not 1 <= generation <= MAX_DELIVERIES:
        raise GateError("invalid_delivery_generation")
    for key in expected - {"delivery_generation"}:
        nonempty(receipt[key], "receipt_" + key, 300)


def _check_receipt(item: dict, receipt: dict, action: str) -> str:
    _receipt_shape(receipt, action)
    if (receipt["attempt_id"] != item["attempt_id"]
            or receipt["delivery_generation"] != item["delivery_generation"]
            or receipt["delivery_nonce"] != item["delivery_nonce"]
            or receipt["target_owner"] != item["continuation"]["next_owner"]):
        raise GateError("continuation_delivery_identity_mismatch")
    if receipt["status"] != ("ACCEPTED" if action == "acknowledge" else "CONFIRMED_NOT_SENT"):
        raise GateError("ambiguous_or_wrong_delivery_outcome")
    receipt_key = _receipt_key(receipt)
    if receipt_key in item["consumed_receipt_ids"]:
        raise GateError("delivery_receipt_already_consumed")
    started = _timestamp(item["delivery_started_at"])
    checked = _timestamp(receipt["checked_at"])
    if checked < started or checked > datetime.now(UTC) + timedelta(minutes=5):
        raise GateError("delivery_receipt_time_outside_attempt")
    if action == "acknowledge":
        user_at = _timestamp(receipt["user_event_at"])
        later_at = _timestamp(receipt["later_activity_at"])
        if (receipt["user_event_id"] == receipt["later_activity_id"]
                or not started <= user_at < later_at <= checked):
            raise GateError("accepted_event_and_later_activity_order_required")
    return receipt_key


def validate(value: dict) -> dict:
    """An opted-in local stage remains an unfinished project, with an exact owner."""
    keys = {"schema", "parent_owner", "stage_owner", "next_owner", "next_action", "project_complete"}
    if not isinstance(value, dict) or set(value) != keys or value.get("schema") != SCHEMA:
        raise GateError("invalid_continuation_contract")
    if value["project_complete"] is not False:
        raise GateError("local_stage_is_not_project_completion")
    for key in ("parent_owner", "stage_owner", "next_owner"):
        nonempty(value[key], key, 200)
    action = value["next_action"]
    if (not isinstance(action, dict) or set(action) != {"kind", "summary"}
            or action.get("kind") not in KINDS):
        raise GateError("invalid_continuation_action")
    nonempty(action["summary"], "next_action_summary", 1000)
    if action["kind"] == "review" and value["next_owner"] == value["stage_owner"]:
        raise GateError("review_owner_must_differ_from_stage_owner")
    return {**value, "next_action": dict(action)}


def _path(home: Path, item_id: str) -> Path:
    if not isinstance(item_id, str) or len(item_id) != 64 or any(c not in "0123456789abcdef" for c in item_id):
        raise GateError("invalid_continuation_id")
    return within(home, f"state/continuations/{item_id}.json")


def read(home: Path, item_id: str) -> dict:
    item = read_json(_path(home, item_id))
    if (not isinstance(item, dict) or item.get("schema") not in {ITEM_SCHEMA, LEGACY_ITEM_SCHEMA, causal.ITEM_SCHEMA}
            or item.get("id") != item_id
            or item.get("state") not in (STATES if item.get('schema') != causal.ITEM_SCHEMA
                                        else {'PENDING', 'CLAIMED', 'DELIVERY_UNKNOWN'} | causal.TERMINAL)
            or isinstance(item.get("revision"), bool)
            or not isinstance(item.get("revision"), int) or item["revision"] < 1):
        raise GateError("invalid_continuation_item")
    validate(item["continuation"])
    if digest(item["identity"]) != item_id:
        raise GateError("continuation_identity_mismatch")
    if item["schema"] in {ITEM_SCHEMA, causal.ITEM_SCHEMA}:
        generation = item.get("delivery_generation")
        if (isinstance(generation, bool) or not isinstance(generation, int)
                or not 0 <= generation <= MAX_DELIVERIES):
            raise GateError("invalid_delivery_generation")
        if generation:
            nonce = item.get("delivery_nonce")
            if not isinstance(nonce, str) or len(nonce) != 32 or any(c not in "0123456789abcdef" for c in nonce):
                raise GateError("invalid_delivery_nonce")
            _timestamp(item.get("delivery_started_at"))
        elif (item.get("delivery_nonce") is not None or item.get("delivery_started_at") is not None
              or item["state"] in {"DELIVERY_UNKNOWN", "ACKNOWLEDGED"} | causal.TERMINAL):
            raise GateError("delivery_generation_state_mismatch")
        consumed = item.get("consumed_receipt_ids")
        history = item.get("receipt_history")
        if (not isinstance(consumed, list) or not isinstance(history, list)
                or len(consumed) != len(history) or len(consumed) > MAX_DELIVERIES):
            raise GateError("invalid_delivery_receipt_history")
        if any(not isinstance(key, str) or len(key) != 64 for key in consumed):
            raise GateError("invalid_consumed_receipt_identity")
        for receipt in history:
            if not isinstance(receipt, dict):
                raise GateError("invalid_delivery_receipt_history")
            if item['schema'] == causal.ITEM_SCHEMA:
                causal.receipt_shape(receipt)
            else:
                action = "acknowledge" if receipt.get("status") == "ACCEPTED" else "not-sent"
                _receipt_shape(receipt, action)
        if len(set(consumed)) != len(consumed) or consumed != [_receipt_key(r) for r in history]:
            raise GateError("delivery_receipt_history_mismatch")
        generations = [r["delivery_generation"] for r in history]
        if generations != sorted(set(generations)) or any(g > generation for g in generations):
            raise GateError("delivery_receipt_history_order_mismatch")
        if item['schema'] == causal.ITEM_SCHEMA:
            if item.get('receipt_acceptance_scope') != causal.SCOPE:
                raise GateError('causal_received_only_item_required')
            if generation:
                causal.validate_request(item)
                if item['state'] in {'PENDING', 'CLAIMED'}:
                    raise GateError('causal_unknown_cannot_reopen')
            elif item.get('delivery_request') is not None:
                raise GateError('causal_unadmitted_request_refused')
            if item['state'] in causal.TERMINAL:
                if not history or item.get('receipt') != history[-1] or item['state'] != history[-1]['status']:
                    raise GateError('causal_terminal_receipt_mismatch')
                if len(history) != 1:
                    raise GateError('causal_single_delivery_history_required')
                causal.check_receipt({**item, 'consumed_receipt_ids': []}, history[-1])
            elif item.get('receipt') is not None or history:
                raise GateError('causal_unknown_history_mismatch')
    return item


def _binding(item: dict) -> None:
    """Keep an admitted attempt bound to its immutable stage after later work."""
    from . import project

    identity = item["identity"]
    root = Path(identity["root"])
    task = project.load_task(root, identity["task_id"])
    if (task["status"] != "CLOSED" or task["project_id"] != identity["project_id"]
            or task["revision"] != identity["task_revision"]
            or task["closeout"]["assessment"]["source_sha256"] != identity["source_sha256"]
            or validate(task["closeout"]["continuation"]) != item["continuation"]):
        raise GateError("continuation_stage_binding_changed")


def _current(item: dict) -> None:
    from . import project

    _binding(item)
    identity = item["identity"]
    check = project.verify_closeout(Path(identity["root"]), identity["task_id"])
    if check["status"] != "PASS" or check["source_sha256"] != identity["source_sha256"]:
        raise GateError("continuation_source_or_contract_stale")


def _inflight_peer(home: Path, item: dict) -> bool:
    directory = within(home, "state/continuations")
    paths = list(directory.glob("*.json"))
    if len(paths) > 1000:
        raise GateError("continuation_index_limit")
    for path in paths:
        peer = read(home, path.stem)
        if (peer["id"] != item["id"] and peer["state"] in {"CLAIMED", "DELIVERY_UNKNOWN"}
                and peer["identity"]["root"] == item["identity"]["root"]
                and peer["identity"]["project_id"] == item["identity"]["project_id"]):
            return True
    return False


def reconcile(home: Path, root: Path, task_id: str) -> dict:
    return _reconcile(home, root, task_id, ITEM_SCHEMA)


def reconcile_causal(home: Path, root: Path, task_id: str) -> dict:
    """Explicit v3 creation; existing v1/v2 are never silently reinterpreted."""
    return _reconcile(home, root, task_id, causal.ITEM_SCHEMA)


def _reconcile(home: Path, root: Path, task_id: str, schema: str) -> dict:
    """Recover one explicitly selected CLOSED stage; no project/history scan."""
    from . import project
    from .overlay import validate_roots

    validate_roots(home)
    root = project.root_path(root)
    task = project.load_task(root, task_id)
    if task.get("status") != "CLOSED" or not task.get("closeout"):
        raise GateError("registered_closeout_required")
    contract = validate(task["closeout"].get("continuation"))
    identity = {"root": str(root), "project_id": task["project_id"], "task_id": task_id,
                "task_revision": task["revision"],
                "source_sha256": task["closeout"]["assessment"]["source_sha256"]}
    item_id = digest(identity)
    with lock(within(home, "state/continuations.lock")):
        path = _path(home, item_id)
        if path.exists():
            item = read(home, item_id)
            if schema == causal.ITEM_SCHEMA and item['schema'] != schema:
                raise GateError('existing_noncausal_item_preserve_and_hold')
            if item["identity"] != identity or item["continuation"] != contract:
                raise GateError("continuation_reconciliation_conflict")
            # Recovery of an admitted attempt is separate from new admission.
            # Source drift or aged checks cannot erase its unknown/known outcome.
            _binding(item)
            return item
        item = {"schema": schema, "id": item_id,
                "identity": identity, "continuation": contract, "revision": 1,
                "state": "PENDING", "at": now(), "attempt_id": None,
                "delivery_generation": 0, "delivery_nonce": None,
                "delivery_started_at": None, "consumed_receipt_ids": [], "receipt_history": [],
                "receipt": None, "external_authority_granted": False,
                "worker_started": False}
        if schema == causal.ITEM_SCHEMA:
            item.update(delivery_request=None, receipt_acceptance_scope=causal.SCOPE)
        _current(item)
        atomic_json(path, item)
    return item


def status(home: Path) -> dict:
    """Return bounded local metadata; read-only turns cannot clear open actions."""
    directory = within(home, "state/continuations")
    paths = sorted(directory.glob("*.json")) if directory.exists() else []
    if len(paths) > 1000:
        raise GateError("continuation_index_limit")
    items = [read(home, p.stem) for p in paths]
    dispatchable = []
    admissions = {}
    for item in items:
        if item["state"] != "PENDING":
            continue
        try:
            if item["schema"] not in {ITEM_SCHEMA, causal.ITEM_SCHEMA}:
                raise GateError("legacy_delivery_binding_requires_owner_reconciliation")
            _current(item)
            if _inflight_peer(home, item):
                raise GateError("same_project_delivery_already_owned")
        except (GateError, OSError, KeyError, TypeError, ValueError):
            admissions[item["id"]] = "BLOCKED_CURRENT_SOURCE_OR_OWNERSHIP"
        else:
            admissions[item["id"]] = "READY_LOCAL_METADATA_ONLY"
            dispatchable.append(item["id"])
    return {"schema": "agentos.continuation-status/v1", "items": items,
            "dispatchable": dispatchable, "admissions": admissions,
            "project_completion_proven": False, "external_authority_granted": False}


def transition(home: Path, item_id: str, actor: str, revision: int,
               action: str, receipt: dict | None = None, *, delivery: dict | None = None) -> dict:
    """CAS state transition. Unknown delivery never expires or auto-retries."""
    from .overlay import validate_roots

    validate_roots(home)
    with lock(within(home, "state/continuations.lock")):
        item = read(home, item_id)
        if actor != item["continuation"]["parent_owner"]:
            raise GateError("continuation_parent_owner_mismatch")
        if isinstance(revision, bool) or revision != item["revision"]:
            raise GateError("continuation_revision_conflict")
        if item["schema"] not in {ITEM_SCHEMA, causal.ITEM_SCHEMA}:
            raise GateError("legacy_delivery_binding_requires_owner_reconciliation")
        is_causal = item['schema'] == causal.ITEM_SCHEMA
        if (is_causal and action in {'acknowledge', 'not-sent'}) or (not is_causal and (action == 'record-receipt' or delivery is not None)):
            raise GateError('receipt_contract_or_non_delivery_scope_mismatch')
        if action in {"claim", "begin-delivery"}:
            _current(item)
            if _inflight_peer(home, item):
                raise GateError("same_project_delivery_already_owned")
        else:
            # A received provider acknowledgement remains true after later edits.
            # Recording it never admits another stale delivery or grants authority.
            _binding(item)
        if action == "claim" and item["state"] == "PENDING":
            item["state"] = "CLAIMED"
        elif action == "begin-delivery" and item["state"] == "CLAIMED":
            # Commit uncertainty BEFORE provider I/O, including a lost response.
            if item["delivery_generation"] >= MAX_DELIVERIES:
                raise GateError("delivery_limit_requires_owner_review")
            item["attempt_id"] = item["attempt_id"] or digest({"id": item_id, "actor": actor, "revision": revision})
            item["delivery_generation"] += 1
            item["delivery_nonce"] = uuid.uuid4().hex
            item["delivery_started_at"] = now()
            item["receipt"] = None
            item["state"] = "DELIVERY_UNKNOWN"
            if is_causal:
                item['delivery_request'] = causal.make_request(item, delivery)
        elif action == 'record-receipt' and is_causal and item['state'] == 'DELIVERY_UNKNOWN':
            receipt_key = causal.check_receipt(item, receipt)
            item['state'] = receipt['status']
            item['receipt'] = dict(receipt)
            item['consumed_receipt_ids'].append(receipt_key)
            item['receipt_history'].append(dict(receipt))
        elif action in {"acknowledge", "not-sent"} and item["state"] == "DELIVERY_UNKNOWN":
            receipt_key = _check_receipt(item, receipt, action)
            if action == "acknowledge":
                item["state"] = "ACKNOWLEDGED"
            else:
                # Preserve operation identity; only proven non-delivery permits retry.
                item["state"] = "CLAIMED"
            item["receipt"] = dict(receipt)
            item["consumed_receipt_ids"].append(receipt_key)
            item["receipt_history"].append(dict(receipt))
        else:
            raise GateError("invalid_continuation_transition")
        item["revision"] += 1
        item["at"] = now()
        atomic_json(_path(home, item_id), item)
        return item


def command(argv: list[str], home: Path) -> tuple[dict, int]:
    from .safeio import read_json_input

    parser = argparse.ArgumentParser(prog="agentos continuation")
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ('reconcile', 'reconcile-causal'):
        sync = sub.add_parser(name)
        sync.add_argument("--root", type=Path, required=True)
        sync.add_argument("--task", required=True)
    sub.add_parser("status")
    migrate = sub.add_parser("migrate-legacy")
    migrate.add_argument("--id", required=True)
    migrate.add_argument("--actor", required=True)
    migrate.add_argument("--revision", type=int, required=True)
    migrate.add_argument("--apply", action="store_true")
    migrate.add_argument("--expected-sha256")
    for action in ("claim", "begin-delivery", "acknowledge", "not-sent", 'record-receipt'):
        child = sub.add_parser(action)
        child.add_argument("--id", required=True)
        child.add_argument("--actor", required=True)
        child.add_argument("--revision", type=int, required=True)
        if action in {"acknowledge", "not-sent", 'record-receipt'}:
            child.add_argument("--receipt", type=Path, required=True)
        if action == 'begin-delivery':
            child.add_argument('--delivery', type=Path)
    args = parser.parse_args(argv)
    if args.action == "status":
        return status(home), 0
    if args.action == "reconcile":
        return reconcile(home, args.root, args.task), 0
    if args.action == 'reconcile-causal':
        return reconcile_causal(home, args.root, args.task), 0
    if args.action == "migrate-legacy":
        from .continuation_migration import migrate

        result = migrate(home, args.id, args.actor, args.revision,
                         apply=args.apply, expected_sha256=args.expected_sha256)
        return result, 2 if result["status"] == "HOLD_LEGACY_UNBOUND" else 0
    receipt = read_json_input(args.receipt) if hasattr(args, "receipt") else None
    delivery = read_json_input(args.delivery) if getattr(args, 'delivery', None) is not None else None
    return transition(home, args.id, args.actor, args.revision, args.action, receipt, delivery=delivery), 0
