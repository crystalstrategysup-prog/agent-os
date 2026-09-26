"""Bounded discovery of packaged scenarios and an opt-in SSH/VNC probe."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .safeio import GateError

RESOURCE_ROOT = Path(__file__).parent / "resources" / "setup-scenarios"
ID_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
IMPLEMENTATION_STATUSES = {"guide_only", "adapter_available"}


def _read(name: str, *, max_bytes: int) -> dict[str, Any]:
    path = RESOURCE_ROOT / name
    with path.open("rb") as resource:
        data = resource.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise GateError("setup_resource_too_large")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise GateError("invalid_setup_resource")
    return value


def load_index() -> dict[str, Any]:
    index = _read("index.json", max_bytes=64 * 1024)
    if index.get("schema") != "agentos.setup-index/v1":
        raise GateError("unsupported_setup_index_schema")
    entries = index.get("scenarios")
    if not isinstance(entries, list):
        raise GateError("invalid_setup_index")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise GateError("invalid_setup_index_entry")
        identifier = entry.get("id")
        if (
            not isinstance(identifier, str)
            or not ID_PATTERN.fullmatch(identifier)
            or identifier in seen
            or entry.get("implementation_status") not in IMPLEMENTATION_STATUSES
        ):
            raise GateError("invalid_setup_index_entry")
        seen.add(identifier)
    return index


def show(identifier: str) -> dict[str, Any]:
    if not ID_PATTERN.fullmatch(identifier):
        raise GateError("invalid_setup_scenario_id")
    index = load_index()
    entry = next(
        (item for item in index["scenarios"] if item["id"] == identifier), None
    )
    if entry is None:
        raise GateError("unknown_setup_scenario")
    scenario = _read(f"{identifier}.json", max_bytes=128 * 1024)
    if (
        scenario.get("schema") != "agentos.setup-scenario/v1"
        or scenario.get("id") != identifier
        or scenario.get("implementation_status") != entry["implementation_status"]
        or scenario.get("title") != entry.get("title")
    ):
        raise GateError("setup_scenario_index_mismatch")
    return scenario


def command(argv: list[str]) -> dict[str, Any]:
    parser = argparse.ArgumentParser(prog="agentos setup")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="List published connection scenarios")
    selected = actions.add_parser("show", help="Read one published scenario")
    selected.add_argument("id")
    probe_parser = actions.add_parser("probe", help="Plan or verify one SSH/VNC route")
    probe_parser.add_argument("kind", choices=["ssh-vnc"])
    probe_parser.add_argument("--host", required=True, help="Existing SSH alias")
    probe_parser.add_argument("--vnc-port", type=int, default=5900)
    probe_parser.add_argument("--ssh-only", action="store_true")
    probe_parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "list":
        return load_index()
    if args.action == "show":
        return show(args.id)
    from .ssh_vnc_probe import probe

    return probe(
        args.host, vnc_port=args.vnc_port, ssh_only=args.ssh_only, apply=args.apply
    )
