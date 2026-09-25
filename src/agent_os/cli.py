"""Community AgentOS command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, full_inventory
from .config import AgentOSPaths, load_config
from .doctor import run as doctor_run
from .mcp import client_config
from .model_routing import route_task
from .onboarding import public_plan
from .result_gate import evaluate_result
from .session_hub import CodexRunner, discover_screens, discover_sessions
from .tasks import normalize_task
from .update_advisory import check as update_advisory_check


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="agentos",
        description="Documentation-first agent foundation",
        epilog="Foundation groups: project, overlay, integrate, resources, hook. Run agentos GROUP --help.",
    )
    root.add_argument("--home", "--user-home", dest="home", type=Path)
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create a private local AgentOS home")
    commands.add_parser("doctor", help="Run secret-free local checks")
    commands.add_parser(
        "telegram-plan", help="Print Telegram Business onboarding steps"
    )
    commands.add_parser("mcp-config", help="Print an MCP client configuration template")
    commands.add_parser("sessions", help="List local persisted Codex sessions")
    commands.add_parser(
        "screens", help="List local GNU Screen sessions and Codex bindings"
    )
    commands.add_parser(
        "session-capabilities", help="Show Telegram Session Hub readiness"
    )
    commands.add_parser("telegram-bot", help="Run the owner-only Telegram Session Hub")
    update = commands.add_parser(
        "update-check", help="Check the official public tag when due"
    )
    update.add_argument("--force", action="store_true")
    inventory = commands.add_parser(
        "inventory", help="Collect or select maintained project knowledge"
    )
    inventory_commands = inventory.add_subparsers(
        dest="inventory_action", required=True
    )
    collect = inventory_commands.add_parser("collect")
    collect.add_argument("--catalog", type=Path, required=True)
    collect.add_argument("--output", type=Path)
    collect.add_argument(
        "--max-files", type=int, default=full_inventory.DEFAULT_MAX_FILES
    )
    collect.add_argument(
        "--max-bytes", type=int, default=full_inventory.DEFAULT_MAX_BYTES
    )
    select = inventory_commands.add_parser("select")
    select.add_argument("--input", type=Path, required=True)
    select.add_argument("--project-id", required=True)
    select.add_argument(
        "--class",
        dest="knowledge_classes",
        action="append",
        choices=full_inventory.CLASSES[:-1],
    )
    select.add_argument("--output", type=Path)
    route = commands.add_parser(
        "route-task", help="Plan an exact model and reasoning effort"
    )
    route.add_argument("--mode", default="implementation")
    route.add_argument(
        "--complexity", choices=("low", "medium", "high", "critical"), default="medium"
    )
    route.add_argument("--role", choices=("root", "worker", "verifier"), default="root")
    gate = commands.add_parser(
        "assess-result", help="Check current evidence before reporting COMPLETE"
    )
    gate.add_argument("--file", type=Path, required=True)
    task = commands.add_parser("task", help="Normalize a bounded task brief")
    task.add_argument("objective")
    task.add_argument("--target", default="local")
    task.add_argument("--risk", default="R0")
    return root


def main(argv: list[str] | None = None) -> int:
    from .foundation_cli import dispatch

    handled = dispatch(list(sys.argv[1:] if argv is None else argv))
    if handled is not None:
        return handled
    args = parser().parse_args(argv)
    paths = AgentOSPaths.discover(args.home)
    config: dict[str, object] | None = None
    advisory: dict[str, object] | None = None
    if args.command != "init":
        config = load_config(paths)
        advisory = update_advisory_check(
            paths.state,
            config,
            __version__,
            force=args.command == "update-check" and args.force,
        )
        if (
            args.command != "update-check"
            and advisory.get("status") == "UPDATE_AVAILABLE"
        ):
            print(
                f"AgentOS {advisory['latest_version']} is available: "
                f"{advisory['latest_tag_url']}",
                file=sys.stderr,
            )
    if args.command == "init":
        paths.initialize()
        _print({"status": "PASS", "home": str(paths.home)})
    elif args.command == "doctor":
        _print(doctor_run(paths, update_advisory=advisory))
    elif args.command == "telegram-plan":
        _print(public_plan())
    elif args.command == "mcp-config":
        _print(client_config())
    elif args.command in {
        "sessions",
        "screens",
        "session-capabilities",
        "telegram-bot",
    }:
        assert config is not None
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
    elif args.command == "route-task":
        assert config is not None
        _print(
            route_task(
                config, mode=args.mode, complexity=args.complexity, role=args.role
            )
        )
    elif args.command == "assess-result":
        payload = json.loads(args.file.read_text(encoding="utf-8"))
        result = evaluate_result(
            payload["acceptance"],
            payload.get("evidence", []),
            now=payload["now"],
            max_age_seconds=payload.get("max_age_seconds"),
        )
        _print(result)
        if result["status"] != "PASS":
            return 2
    elif args.command == "task":
        _print(normalize_task(args.objective, args.target, args.risk).as_dict())
    elif args.command == "update-check":
        _print(advisory)
    elif args.command == "inventory":
        try:
            if args.inventory_action == "collect":
                result = full_inventory.collect(
                    args.catalog,
                    max_files=args.max_files,
                    max_bytes=args.max_bytes,
                )
            else:
                result = full_inventory.select(
                    args.input,
                    project_id=args.project_id,
                    classes=args.knowledge_classes,
                )
        except full_inventory.FullInventoryError as exc:
            result = {
                "schema": "agent-os.full-inventory-error/v1",
                "status": "BLOCKED",
                "reason_code": str(exc),
            }
        if args.output and result.get("status") in {"PASS", "PARTIAL"}:
            full_inventory.write_result(args.output, result)
        _print(result)
        if result.get("status") not in {"PASS", "PARTIAL"}:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
