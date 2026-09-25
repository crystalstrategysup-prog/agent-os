"""Foundation CLI extension without optional network/config prerequisites."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .safeio import GateError


def dispatch(argv: list[str]) -> int | None:
    # Global --home is accepted before the command, matching the original CLI.
    prefix = argparse.ArgumentParser(add_help=False)
    prefix.add_argument("--home", "--user-home", dest="home", type=Path)
    global_args, rest = prefix.parse_known_args(argv)
    if not rest or rest[0] not in {
        "project",
        "overlay",
        "integrate",
        "resources",
        "hook",
    }:
        return None
    try:
        from .config import AgentOSPaths

        home = AgentOSPaths.discover(global_args.home).home
        cmd = rest.pop(0)
        if cmd == "project":
            from .project import command

            result, code = command(rest, home)
        elif cmd == "overlay":
            from .overlay import command

            result, code = command(rest, home)
        elif cmd == "integrate":
            from .integration import command

            result, code = command(rest, home)
        elif cmd == "hook":
            from .hooks import handle

            result = handle(json.load(sys.stdin), home)
            code = 0
        else:
            p = argparse.ArgumentParser(prog="agentos resources")
            p.add_argument("--list", action="store_true")
            p.parse_args(rest)
            root = Path(__file__).parent / "resources"
            result = {
                "root": str(root),
                "files": sorted(
                    str(x.relative_to(root)) for x in root.rglob("*") if x.is_file()
                ),
            }
            code = 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
    except (GateError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        return 2
