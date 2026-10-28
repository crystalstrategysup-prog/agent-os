"""V3 recovery entry using the existing bounded supported-tool stdio bridge.

The trusted embedding executes the challenged tool and uses the re-exported
accounting/projection helpers on its actual in-memory return. Neither stdin nor
a Python callback authenticates that embedding. No recorded-observation input,
cursor override, new transport or automatic recovery authority is supplied.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import project
from . import refusal_recovery as recovery
from .interrupted_bridge import (
    MetadataResponseAccounting,
    StdioToolBridge,
    prepare_metadata_response,
)
from .interrupted_continuation import SupportedReadThreadObserver
from .safeio import GateError


def _inputs(argv):
    parser = argparse.ArgumentParser(prog="python -m agent_os.refusal_recovery_bridge")
    parser.add_argument("action", choices=["acknowledge", "advance", "reconcile"])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--task", required=True)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--permit", required=True, type=Path)
    args = parser.parse_args(argv)
    args.root = args.root.resolve()
    args.home = args.home.resolve()
    request = recovery.document(args.request)
    permit = recovery.document(args.permit)
    recovery.validate_request(args.root, args.home, args.task, request)
    if request["schema"] != recovery.WORKFLOW_REQUEST:
        recovery.fail("recovery_bridge_v3_required")
    return args, request, permit


def _execute(args, request, permit, observer):
    if args.action == "advance":
        return project.next_turn(
            args.root, args.home, session_id=request["session_id"],
            previous_turn=request["expected"]["bound_turn_id"],
            turn_id=permit.get("current_turn_id"), task_id=args.task,
            recovery_request=request, recovery_permit=permit,
            recovery_observer=observer,
        )
    function = recovery.acknowledge if args.action == "acknowledge" else recovery.reconcile
    return function(args.root, args.home, args.task, request, permit, observer=observer)


def command(argv, *, read_thread=None):
    """Embedding API; the owner selects the actual supported tool callable."""
    args, request, permit = _inputs(argv)
    if read_thread is None:
        recovery.fail("recovery_supported_observer_unavailable")
    return _execute(args, request, permit, SupportedReadThreadObserver(read_thread))


def main(argv=None):
    args, request, permit = _inputs(argv)
    bridge = StdioToolBridge(
        recovery.sha(recovery.enc(request)),
        native_thread_id=request["native_origin"]["thread_id"],
    )
    result = _execute(args, request, permit, SupportedReadThreadObserver(bridge))
    print(json.dumps({"schema": "agentos.app-tool-final/v1", "result": result},
                     separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    previous_tty = None
    try:
        if sys.stdin.isatty():
            import termios
            previous_tty = termios.tcgetattr(sys.stdin.fileno())
            settings = list(previous_tty)
            settings[6] = list(previous_tty[6])
            settings[3] &= ~(termios.ECHO | termios.ICANON)
            settings[6][termios.VMIN] = 1
            settings[6][termios.VTIME] = 0
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, settings)
        sys.exit(main())
    except GateError as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}), flush=True)
        sys.exit(2)
    finally:
        if previous_tty is not None:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, previous_tty)
