"""Community AgentOS command-line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .config import AgentOSPaths
from .doctor import run as doctor_run
from .mcp import client_config
from .onboarding import public_plan
from .session_hub import CodexRunner, discover_screens, discover_sessions
from .tasks import normalize_task


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="agentos", description="Local-first agent control plane")
    root.add_argument("--home", type=Path)
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create a private local AgentOS home")
    commands.add_parser("doctor", help="Run secret-free local checks")
    commands.add_parser("telegram-plan", help="Print Telegram Business onboarding steps")
    commands.add_parser("mcp-config", help="Print an MCP client configuration template")
    commands.add_parser("sessions", help="List local persisted Codex sessions")
    commands.add_parser("screens", help="List local GNU Screen sessions and Codex bindings")
    commands.add_parser("session-capabilities", help="Show Telegram Session Hub readiness")
    commands.add_parser("telegram-bot", help="Run the owner-only Telegram Session Hub")
    task = commands.add_parser("task", help="Normalize a bounded task brief")
    task.add_argument("objective")
    task.add_argument("--target", default="local")
    task.add_argument("--risk", default="R0")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    paths = AgentOSPaths.discover(args.home)
    if args.command == "init":
        paths.initialize()
        _print({"status": "PASS", "home": str(paths.home)})
    elif args.command == "doctor":
        _print(doctor_run(paths))
    elif args.command == "telegram-plan":
        _print(public_plan())
    elif args.command == "mcp-config":
        _print(client_config())
    elif args.command in {"sessions", "screens", "session-capabilities", "telegram-bot"}:
        from .config import load_config

        config = load_config(paths)
        if args.command == "sessions":
            _print({"sessions": [item.as_dict() for item in discover_sessions(config)]})
        elif args.command == "screens":
            _print({"screens": [item.as_dict() for item in discover_screens()]})
        elif args.command == "session-capabilities":
            from .speech import capabilities as speech_capabilities

            _print(
                {
                    "schema": "agent-os.session-hub-capabilities/v1",
                    "runtime": CodexRunner(config).capabilities(),
                    "speech": speech_capabilities(config),
                }
            )
        else:
            from .telegram_bot import run

            run(paths, config)
    elif args.command == "task":
        _print(normalize_task(args.objective, args.target, args.risk).as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
