"""One-shot diagnostic level 0 in an existing task, without changing its level.

Only the diagnostic state is written. The selected 1–5 development choice,
readiness, evidence, authority and task revision are retained. A recorded audit
result is supplied context, not proof that an audit or production action passed.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import re

from .development_level import effective, normalize
from .safeio import (GateError, identifier, lock, now, read_json, read_json_input,
                     sha, within)
from . import task_metadata as tm

SCHEMA = "agentos.project-diagnostics/v1"
MAX_GENERATION = 2147483647
STATES = {"ACTIVE", "COMPLETED", "CANCELLED"}


def _text(value: object, name: str, limit: int) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or "\x00" in value):
        raise GateError("diagnostic_invalid_" + name)
    return value.strip()


def _actor(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"session_id", "turn_id"}:
        raise GateError("diagnostic_invalid_actor")
    return {key: _text(value[key], key, 200) for key in ("session_id", "turn_id")}


def _timestamp(value: object) -> str:
    value = _text(value, "timestamp", 64)
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
    except ValueError as exc:
        raise GateError("diagnostic_invalid_timestamp") from exc
    return value


def normalize_selection(value: object) -> dict:
    """Portable active descriptor; never a saved development level or authority."""
    if (not isinstance(value, dict)
            or set(value) != {"id", "scope", "reason", "captured_development"}):
        raise GateError("diagnostic_selection_required")
    return {
        "id": identifier(value["id"]),
        "scope": _text(value["scope"], "scope", 200),
        "reason": _text(value["reason"], "reason", 2000),
        "captured_development": normalize(value["captured_development"]),
    }


def _result(value: object, *, cancelled: bool = False) -> dict:
    fields = {"summary", "remaining", "next_action", "references"}
    if not isinstance(value, dict) or set(value) != fields:
        raise GateError("diagnostic_result_required")
    result = {
        "summary": _text(value["summary"], "summary", 4000),
        "next_action": _text(value["next_action"], "next_action", 2000),
    }
    for key in ("remaining", "references"):
        values = value[key]
        if (not isinstance(values, list) or len(values) > 32
                or (key == "references" and not cancelled and not values)):
            raise GateError("diagnostic_invalid_" + key)
        result[key] = [_text(item, key, 1000) for item in values]
        if len(set(result[key])) != len(result[key]):
            raise GateError("diagnostic_duplicate_" + key)
    return result


def normalize_state(value: object) -> dict:
    """Validate retained compact runs; corrupt or ambiguous history is refused."""
    if (not isinstance(value, dict) or set(value) != {"schema", "generation", "runs"}
            or value.get("schema") != SCHEMA
            or type(value.get("generation")) is not int
            or not 1 <= value["generation"] <= MAX_GENERATION
            or not isinstance(value.get("runs"), list) or not value["runs"]):
        raise GateError("diagnostic_state_invalid")
    rows, identities, active_count, transitions = [], set(), 0, 0
    for index, raw in enumerate(value["runs"]):
        if not isinstance(raw, dict):
            raise GateError("diagnostic_run_invalid")
        status = raw.get("status")
        if not isinstance(status, str):
            raise GateError("diagnostic_run_invalid")
        fields = {"id", "scope", "reason", "captured_development", "status",
                  "started_at", "started_by"}
        if status in {"COMPLETED", "CANCELLED"}:
            fields |= {"finished_at", "finished_by", "result", "resumed_development"}
        if status not in STATES or set(raw) != fields:
            raise GateError("diagnostic_run_invalid")
        row = normalize_selection({key: raw[key] for key in
                                   ("id", "scope", "reason", "captured_development")})
        if row["id"] in identities:
            raise GateError("diagnostic_duplicate_run")
        identities.add(row["id"])
        row.update(status=status, started_at=_timestamp(raw["started_at"]),
                   started_by=_actor(raw["started_by"]))
        transitions += 1
        if status == "ACTIVE":
            active_count += 1
            if index != len(value["runs"]) - 1:
                raise GateError("diagnostic_active_run_must_be_last")
        else:
            row.update(finished_at=_timestamp(raw["finished_at"]),
                       finished_by=_actor(raw["finished_by"]),
                       result=_result(raw["result"], cancelled=status == "CANCELLED"),
                       resumed_development=normalize(raw["resumed_development"]))
            if datetime.fromisoformat(row["finished_at"]) < datetime.fromisoformat(row["started_at"]):
                raise GateError("diagnostic_timestamp_order")
            transitions += 1
        rows.append(row)
    if active_count > 1 or value["generation"] != transitions:
        raise GateError("diagnostic_generation_invalid")
    return {"schema": SCHEMA, "generation": value["generation"], "runs": rows}


def _state(task: dict) -> dict:
    return (normalize_state(task["diagnostics"]) if "diagnostics" in task else
            {"schema": SCHEMA, "generation": 0, "runs": []})


def active(task: dict) -> dict | None:
    state = _state(task)
    return next((row for row in state["runs"] if row["status"] == "ACTIVE"), None)


def context_selection(task: dict) -> dict | None:
    row = active(task)
    return None if row is None else normalize_selection({key: row[key] for key in
        ("id", "scope", "reason", "captured_development")})


def view(task: dict) -> dict:
    state = _state(task)
    selection = context_selection(task)
    development = effective(task["answers"])
    return {
        "state": "ACTIVE" if selection else "INACTIVE",
        "generation": state["generation"],
        "active": selection,
        "development": development,
        "effective_level": 0 if selection else development["level"],
        "return_development": development,
    }


def _read(root: Path, task_id: str) -> tuple[dict, bytes]:
    from .project import load_task

    raw = tm.read_bytes(root, task_id)
    if tm.path(root, task_id).stat().st_nlink != 1:
        raise GateError("diagnostic_hardlink_refused")
    task = load_task(root, task_id)
    if tm.read_bytes(root, task_id) != raw:
        raise GateError("diagnostic_task_changed_during_read")
    _state(task)
    return task, raw


def _readback(root: Path, task: dict, raw: bytes, *, changed: bool = False,
              run_id: str | None = None) -> dict:
    state = _state(task)
    selected = (next((row for row in state["runs"] if row["id"] == run_id), None)
                if run_id is not None else (state["runs"][-1] if state["runs"] else None))
    if run_id is not None and selected is None:
        raise GateError("diagnostic_run_missing")
    return {
        "schema": "agentos.project-diagnostic-readback/v1",
        "status": selected["status"] if selected else "NOT_STARTED",
        "root": str(root), "project_id": task["project_id"], "task_id": task["id"],
        "task_revision": task["revision"], "task_sha256": sha(raw),
        "changed": changed, "diagnostic": view(task), "run": selected,
        "authority_granted": False, "product_writes_authorized": False,
        "native_hooks": "DISABLED", "behavior_compliance": "NOT_PROVEN",
        "note": "Diagnostic state/result recorded only; no audit PASS or new READY. Use existing result references and remaining work.",
        "writes": [str(tm.path(root, task["id"]))] if changed else [],
    }


def status(root: Path, task_id: str, run_id: str | None = None) -> dict:
    from .project import root_path, load_project

    root = root_path(root)
    identifier(task_id)
    if run_id is not None:
        identifier(run_id)
    task, raw = _read(root, task_id)
    if task.get("project_id") != load_project(root).get("id"):
        raise GateError("diagnostic_project_mismatch")
    return _readback(root, task, raw, run_id=run_id)


def _writer(root: Path, home: Path, task: dict, session_id: str, turn_id: str) -> tuple[bytes, bytes]:
    from .project import load_project, project_file
    from .turns import turn_path

    current_project = load_project(root)
    if task.get("project_id") != current_project.get("id"):
        raise GateError("diagnostic_project_mismatch")
    if current_project.get("active_task") != task["id"]:
        raise GateError("diagnostic_active_task_required")
    if task.get("status") not in {"INTAKE", "READY", "VERIFYING", "CHECKPOINT"}:
        raise GateError("diagnostic_task_not_writable")
    if task.get("session_id") != session_id or task.get("turn_id") != turn_id:
        raise GateError("diagnostic_writer_mismatch")
    if task.get("handoff_user_home") not in (None, str(home)):
        raise GateError("diagnostic_user_home_mismatch")
    path = turn_path(home, session_id)
    receipt = read_json(path)
    if path.stat().st_nlink != 1:
        raise GateError("diagnostic_hardlink_refused")
    if (not isinstance(receipt, dict) or receipt.get("schema") != "agentos.turn/v1"
            or receipt.get("session_id") != session_id or receipt.get("turn_id") != turn_id
            or receipt.get("root") != str(root) or receipt.get("task_id") != task["id"]
            or receipt.get("status") != "ENTERED"):
        raise GateError("diagnostic_turn_binding_mismatch")
    return project_file(root).read_bytes(), path.read_bytes()


def _change(root: Path, task_id: str, *, user_home: Path, session_id: str, turn_id: str,
            run_id: str, action: str, expected_task_sha256: str, expected_revision: int,
            scope: str | None = None, reason: str | None = None,
            result: dict | None = None) -> dict:
    from .project import root_path, _require_entry_recovered, project_file
    from .turns import turn_path

    root = root_path(root)
    identifier(task_id)
    identifier(run_id)
    actor = _actor({"session_id": session_id, "turn_id": turn_id})
    if (not isinstance(expected_task_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_task_sha256) is None
            or type(expected_revision) is not int or not 1 <= expected_revision <= MAX_GENERATION):
        raise GateError("diagnostic_cas_required")
    if action == "start":
        scope = _text(scope, "scope", 200)
        reason = _text(reason, "reason", 2000)
    elif action in {"finish", "cancel"}:
        result = _result(result, cancelled=action == "cancel")
    else:
        raise GateError("diagnostic_action_invalid")
    home = user_home.expanduser().resolve()
    _require_entry_recovered(root)
    # A bad/missing owner binding must not create a new owner state directory.
    current_task, _ = _read(root, task_id)
    _writer(root, home, current_task, actor["session_id"], actor["turn_id"])
    with lock(within(root, ".agentos/write.lock")), lock(within(home, "state/turns.lock")):
        _require_entry_recovered(root)
        task, before = _read(root, task_id)
        if sha(before) != expected_task_sha256 or task["revision"] != expected_revision:
            raise GateError("diagnostic_task_cas_mismatch")
        project_before, turn_before = _writer(root, home, task, actor["session_id"], actor["turn_id"])
        state = _state(task)
        existing = next((row for row in state["runs"] if row["id"] == run_id), None)
        if action == "start":
            if existing is not None:
                if (existing["scope"] != scope or existing["reason"] != reason
                        or existing["started_by"] != actor):
                    raise GateError("diagnostic_run_id_conflict")
                return _readback(root, task, before, run_id=run_id)
            if active(task) is not None:
                raise GateError("diagnostic_already_active")
            state["runs"].append({
                "id": run_id, "scope": scope, "reason": reason,
                "captured_development": effective(task["answers"]), "status": "ACTIVE",
                "started_at": now(), "started_by": actor,
            })
        else:
            if existing is None:
                raise GateError("diagnostic_run_missing")
            desired = "COMPLETED" if action == "finish" else "CANCELLED"
            if existing["status"] != "ACTIVE":
                if existing["status"] != desired or existing["result"] != result:
                    raise GateError("diagnostic_completed_run_immutable")
                return _readback(root, task, before, run_id=run_id)
            existing.update(status=desired, finished_at=now(), finished_by=actor,
                            result=result, resumed_development=effective(task["answers"]))
        state["generation"] += 1
        updated = deepcopy(task)
        updated["diagnostics"] = normalize_state(state)
        # Preserve the ordinary task revision and readiness. This generation is
        # bound by full task bytes; no audit-only reset of accepted checks.
        expected_bytes = tm.encoded(updated, tm.limit(root))
        if (tm.read_bytes(root, task_id) != before
                or project_file(root).read_bytes() != project_before
                or turn_path(home, actor["session_id"]).read_bytes() != turn_before):
            raise GateError("diagnostic_state_changed_before_write")
        tm.write_task(root, updated)
        after = tm.read_bytes(root, task_id)
        if after != expected_bytes:
            raise GateError("diagnostic_readback_mismatch")
        return _readback(root, updated, after, changed=True, run_id=run_id)


def start(root: Path, task_id: str, **kwargs) -> dict:
    return _change(root, task_id, action="start", **kwargs)


def finish(root: Path, task_id: str, **kwargs) -> dict:
    return _change(root, task_id, action="finish", **kwargs)


def cancel(root: Path, task_id: str, **kwargs) -> dict:
    return _change(root, task_id, action="cancel", **kwargs)


def command(argv: list[str], user_home: Path) -> tuple[dict, int]:
    parser = argparse.ArgumentParser(prog="agentos project diagnose", allow_abbrev=False)
    subs = parser.add_subparsers(dest="action", required=True)
    for action in ("start", "status", "finish", "cancel"):
        child = subs.add_parser(action, allow_abbrev=False)
        child.add_argument("--root", type=Path, required=True)
        child.add_argument("--task", required=True)
        child.add_argument("--run", required=action != "status")
        if action == "status":
            continue
        child.add_argument("--session", required=True)
        child.add_argument("--turn", required=True)
        child.add_argument("--expected-task-sha256", required=True)
        child.add_argument("--expected-revision", type=int, required=True)
        if action == "start":
            child.add_argument("--scope", required=True)
            child.add_argument("--reason", required=True)
        else:
            child.add_argument("--result", type=Path, required=True,
                               help="Existing result JSON: summary, remaining, next_action, references")
    args = parser.parse_args(argv)
    if args.action == "status":
        return status(args.root, args.task, args.run), 0
    kwargs = dict(user_home=user_home, session_id=args.session, turn_id=args.turn,
                  run_id=args.run, expected_task_sha256=args.expected_task_sha256,
                  expected_revision=args.expected_revision)
    if args.action == "start":
        kwargs.update(scope=args.scope, reason=args.reason)
    else:
        kwargs["result"] = read_json_input(args.result)
    return _change(args.root, args.task, action=args.action, **kwargs), 0
