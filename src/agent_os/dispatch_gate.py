"""One-shot dispatch binding for the inherited Codex/Telegram launcher.

The caller must finish intake for the exact request first. This does not provision
or replace owner routes, and cannot turn a queued message into product evidence.
"""

from __future__ import annotations

import os
from pathlib import Path

from .safeio import GateError, atomic_json, digest, lock, now, read_json, within


def claim(
    prompt: str,
    *,
    workspace: Path | None = None,
    destination_session: str | None = None,
) -> None:
    from .config import AgentOSPaths
    from .hooks import turn_path
    from .project import check_ready, load_task

    home = AgentOSPaths.discover().home
    session = os.environ.get("AGENTOS_SESSION_ID", "")
    turn_id = os.environ.get("AGENTOS_TURN_ID", "")
    if not session or not turn_id:
        raise GateError("governed_dispatch_binding_required")
    with lock(within(home, "state/dispatch.lock")):
        turn = read_json(turn_path(home, session))
        if turn["turn_id"] != turn_id or not turn.get("task_id"):
            raise GateError("governed_dispatch_fresh_intake_required")
        root = Path(turn["root"])
        if workspace and root.resolve() != workspace.resolve():
            raise GateError("dispatch_workspace_mismatch")
        task = load_task(root, turn["task_id"])
        if check_ready(root, task["id"])["status"] != "PASS":
            raise GateError("dispatch_readiness_required")
        if digest(prompt.strip()) != digest(task["answers"]["objective"].strip()):
            raise GateError("dispatch_request_differs_from_intake")
        if task["answers"].get("destination_session") != destination_session:
            raise GateError("dispatch_destination_not_bound")
        receipt = within(home, "state/dispatch/" + digest([session, turn_id]) + ".json")
        if receipt.exists():
            raise GateError("dispatch_already_claimed_new_intake_required")
        atomic_json(
            receipt,
            {
                "schema": "agentos.dispatch-claim/v1",
                "at": now(),
                "task_id": task["id"],
                "session_id": session,
                "turn_id": turn_id,
                "prompt_sha256": digest(prompt.strip()),
                "destination_session": destination_session,
                "state": "CLAIMED_NOT_PROOF_OF_EXECUTION",
            },
        )
