"""Codex lifecycle adapter. Hooks are guardrails, not a complete OS sandbox.

No hook silently enables itself or changes the Codex trust store. Unknown local
tools are denied until intake/readiness; hosted/opt-out paths need host controls.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any

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


def arm_turn(
    home: Path, session_id: str, turn_id: str, root: Path, prompt: str
) -> dict:
    nonempty(turn_id, "turn_id", 200)
    from .overlay import validate_roots

    validate_roots(home)
    with lock(within(home, "state/turns.lock")):
        value = {
            "schema": "agentos.turn/v1",
            "session_id": session_id,
            "turn_id": turn_id,
            "root": str(root.resolve()),
            "status": "INTAKE_REQUIRED",
            "at": now(),
            "prompt_sha256": digest(prompt),
            "task_id": None,
        }
        atomic_json(turn_path(home, session_id), value)
    return value


def bind_turn(
    home: Path, session_id: str, turn_id: str, root: Path, task_id: str
) -> None:
    from .overlay import validate_roots

    validate_roots(home)
    with lock(within(home, "state/turns.lock")):
        path = turn_path(home, session_id)
        value = read_json(path) if path.exists() else None
        if value and (
            value["turn_id"] != turn_id or value["root"] != str(root.resolve())
        ):
            raise GateError("turn_binding_mismatch_reenter_correct_turn")
        value = {
            **(value or {}),
            "schema": "agentos.turn/v1",
            "session_id": session_id,
            "turn_id": turn_id,
            "root": str(root.resolve()),
            "task_id": task_id,
            "status": "ENTERED",
            "entered_at": now(),
            "hook_seen": value is not None,
        }
        atomic_json(path, value)


def _pending(home: Path, payload: dict) -> dict:
    path = turn_path(home, str(payload.get("session_id") or ""))
    if not path.exists():
        raise GateError("fresh_intake_required_no_turn_receipt")
    turn = read_json(path)
    if not payload.get("turn_id") or turn["turn_id"] != payload["turn_id"]:
        raise GateError("stale_turn_receipt")
    if Path(payload.get("cwd") or ".").resolve() != Path(turn["root"]).resolve():
        raise GateError("project_changed_reenter_required")
    return turn


def _allow_context(event: str, text: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _safe_shell(command: str) -> bool:
    # Intentionally conservative: no pipeline, expansion, redirects, substitutions,
    # multiple commands, interpreter snippets, output flags, or arbitrary git flags.
    if any(c in command for c in "\n\r;|&><`$"):
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if not argv:
        return False
    if Path(argv[0]).name == "agentos":
        args = argv[1:]
        while args and args[0] in {"--home", "--user-home"}:
            if len(args) < 3:
                return False
            args = args[2:]
        if args and args[0] in {"resources", "--version"}:
            return True
        if len(args) >= 2 and args[0] == "overlay" and args[1] in {"status", "index"}:
            return True
        return (
            len(args) >= 2
            and args[0] == "project"
            and args[1]
            in {
                "questions",
                "init",
                "enter",
                "document",
                "ready",
                "gate",
                "status",
                "snapshot",
                "check",
                "assess",
                "close",
                "checkpoint",
                "observe",
            }
        )
    if argv[0] in {"pwd", "whoami", "hostname"}:
        return len(argv) == 1
    if argv[0] == "git":
        # Only metadata commands; configured pagers/diff drivers may execute code.
        return (
            len(argv) >= 2
            and argv[1] in {"status", "rev-parse", "ls-files"}
            and not any(
                a.startswith(("--output", "--ext-diff", "--textconv", "--config", "-c"))
                for a in argv[2:]
            )
        )
    if argv[0] in {"ls", "cat", "head", "tail", "wc"}:
        return not any(a in {"--follow", "-f"} for a in argv[1:])
    if argv[0] == "rg":
        return not any(a == "--pre" or a.startswith("--pre=") for a in argv[1:])
    return False


def _docs_patch(root: Path, content: str) -> bool:
    paths = re.findall(
        r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$",
        content,
        re.MULTILINE,
    )
    if not paths:
        return False
    try:
        return all(p.startswith("docs/agentos/") and within(root, p) for p in paths)
    except GateError:
        return False


def handle(payload: dict[str, Any], home: Path) -> dict:
    if not isinstance(payload, dict):
        raise GateError("hook_payload_must_be_object")
    event = payload.get("hook_event_name")
    root = Path(payload.get("cwd") or ".").resolve()
    if event == "SessionStart":
        from .overlay import metadata

        info = metadata(home)
        return _allow_context(
            event,
            "AgentOS: public core="
            + str(Path(__file__).parent)
            + "; separate user home="
            + str(home)
            + ". Each new project task must run agentos project questions / enter; "
            "read selected docs and overlay index, never preload history. Overlay="
            + info["status"],
        )
    if event == "UserPromptSubmit":
        value = arm_turn(
            home,
            str(payload.get("session_id") or ""),
            str(payload.get("turn_id") or ""),
            root,
            str(payload.get("prompt") or ""),
        )
        return _allow_context(
            event,
            "AGENTOS INTAKE REQUIRED. Session="
            + value["session_id"]
            + "; turn="
            + value["turn_id"]
            + ". Reuse verified project facts; resolve new scope and criteria. "
            "Run agentos project enter for this exact session/turn before implementation. "
            "You may inspect and prepare documentation first. Closed tasks need a new entry.",
        )
    if event == "PreToolUse":
        name = str(payload.get("tool_name") or "")
        inputs = payload.get("tool_input") or {}
        if isinstance(inputs, dict):
            command = str(
                inputs.get("command")
                or inputs.get("patch")
                or inputs.get("input")
                or ""
            )
        else:
            command = inputs if isinstance(inputs, str) else ""
        # Discovery and preparation are allowed even with a missing/failed intake.
        if name in {"read_file", "list_dir", "grep_files", "update_plan"}:
            return {}
        if name in {"Bash", "exec_command", "shell_command"} and _safe_shell(command):
            return {}
        if name in {"apply_patch", "Edit", "Write"} and _docs_patch(root, command):
            return {}
        try:
            turn = _pending(home, payload)
            if not turn.get("task_id"):
                return _deny(
                    "Run the mandatory project intake for this turn; no task is bound."
                )
            from .project import check_ready, load_task

            gate = check_ready(root, turn["task_id"])
            task = load_task(root, turn["task_id"])
            if gate["status"] != "PASS":
                return _deny(
                    "Documentation/readiness required: " + ", ".join(gate["errors"])
                )
            if task["answers"]["change_kind"] == "observe":
                return _deny(
                    "Observation does not authorize this potentially mutating tool."
                )
            return _allow_context(
                event,
                "AgentOS readiness valid; stay inside approved write_paths. "
                "This does not grant target-system or external-send authority.",
            )
        except (OSError, ValueError, KeyError) as e:
            return _deny("AgentOS fail-closed: " + str(e))
    if event == "Stop":
        try:
            turn = _pending(home, payload)
            if turn.get("observation"):
                from .observation import verify

                verify(root, turn["observation"])
                return _allow_context(
                    event,
                    "Verified read-only observation; do not claim implementation or live deployment.",
                )
            if not turn.get("task_id"):
                raise GateError("task_intake_not_recorded")
            from .project import document_check, load_task, source_snapshot

            task = load_task(root, turn["task_id"])
            if task["status"] == "CHECKPOINT":
                return _allow_context(
                    event,
                    "Report CHECKPOINT, limitations and next step; do not claim completion.",
                )
            if task["status"] == "CLOSED":
                if (
                    source_snapshot(root)["sha256"]
                    != task["closeout"]["assessment"]["source_sha256"]
                ):
                    raise GateError("source_changed_after_close")
                docs = document_check(root, task)
                if (
                    docs["status"] != "PASS"
                    or docs["documents_digest"]
                    != task["closeout"]["documents"]["documents_digest"]
                ):
                    raise GateError("documentation_changed_after_close")
                return {}
            raise GateError("closeout_or_checkpoint_required")
        except (OSError, ValueError, KeyError) as e:
            # Stop-loop guard is honest: no false COMPLETE, but don't trap the user.
            if payload.get("stop_hook_active") is True:
                return {"systemMessage": "AgentOS NOT COMPLETE: " + str(e)}
            return {
                "decision": "block",
                "reason": "AgentOS: "
                + str(e)
                + ". Record verified closeout or a truthful checkpoint.",
            }
    return {}


def main() -> int:
    try:
        from .config import AgentOSPaths

        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise GateError("hook_input_limit")
        payload = json.loads(raw)
        home = AgentOSPaths.discover().home
        result = handle(payload, home)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001 - a failed guard must block every error
        # Exit 2 blocks supported tool hooks; never return a permissive success.
        print(
            "AgentOS hook failed closed: " + type(exc).__name__ + ": " + str(exc),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
