"""Explicit project-entry receipts. No prompt callbacks or tool interception."""

from __future__ import annotations

from pathlib import Path

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


def turn_path(home: Path, session_id: str) -> Path:
    nonempty(session_id, "session_id", 200)
    return within(home, "state/turns/" + digest(session_id) + ".json")


def bind_turn(
    home: Path, session_id: str, turn_id: str, root: Path, task_id: str
) -> None:
    from .overlay import validate_roots

    validate_roots(home)
    with lock(within(home, "state/turns.lock")):
        path = turn_path(home, session_id)
        validate_entry(home, session_id, turn_id, root)
        value = {
            "schema": "agentos.turn/v1",
            "session_id": session_id,
            "turn_id": turn_id,
            "root": str(root.resolve()),
            "task_id": task_id,
            "status": "ENTERED",
            "entered_at": now(),
            "hook_seen": False,
            "source": "standalone_cli",
        }
        atomic_json(path, value)


def advance_standalone_turn(
    home: Path,
    session_id: str,
    previous_turn: str,
    next_turn: str,
    root: Path,
    task_id: str,
) -> dict:
    """Advance a terminal task receipt; legacy hook provenance grants no authority."""
    from .overlay import validate_roots

    validate_roots(home)
    nonempty(previous_turn, "previous_turn", 200)
    nonempty(next_turn, "next_turn", 200)
    if previous_turn == next_turn:
        raise GateError("next_turn_must_be_new")
    with lock(within(home, "state/turns.lock")):
        path = turn_path(home, session_id)
        if not path.exists():
            raise GateError("standalone_previous_turn_missing")
        value = read_json(path)
        if (
            value.get("schema") != "agentos.turn/v1"
            or value.get("session_id") != session_id
            or value.get("turn_id") != previous_turn
            or value.get("root") != str(root.resolve())
            or value.get("task_id") != task_id
            or value.get("status") != "ENTERED"
        ):
            raise GateError("standalone_turn_transition_mismatch")
        result = {
            "schema": "agentos.turn/v1",
            "session_id": session_id,
            "turn_id": next_turn,
            "root": str(root.resolve()),
            "task_id": None,
            "status": "INTAKE_REQUIRED",
            "at": now(),
            "hook_seen": False,
            "source": "standalone_cli",
        }
        atomic_json(path, result)
    return {
        "status": "INTAKE_REQUIRED",
        "session_id": session_id,
        "turn_id": next_turn,
        "root": str(root.resolve()),
        "previous_task": task_id,
        "native_hook_proven": False,
    }


def validate_entry(home: Path, session_id: str, turn_id: str, root: Path) -> None:
    """Reject conflicting bound tasks, not abandoned prompt/observation receipts."""
    path = turn_path(home, session_id)
    if not path.exists():
        return
    value = read_json(path)
    if (
        not isinstance(value, dict)
        or value.get("schema") != "agentos.turn/v1"
        or value.get("session_id") != session_id
    ):
        raise GateError("invalid_turn_receipt")
    if not value.get("task_id"):
        if value.get("status") not in {"INTAKE_REQUIRED", "OBSERVATION_RECORDED"}:
            raise GateError("invalid_unbound_turn_receipt")
        return
    if value.get("turn_id") != turn_id or value.get("root") != str(root.resolve()):
        raise GateError("turn_binding_mismatch_reenter_correct_turn")
