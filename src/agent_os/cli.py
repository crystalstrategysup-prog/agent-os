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
    elif args.command == "task":
        _print(normalize_task(args.objective, args.target, args.risk).as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
