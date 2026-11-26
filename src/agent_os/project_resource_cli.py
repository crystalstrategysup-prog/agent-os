"""Effect-free CLI adapter for an explicitly selected resource observation.

No owner discovery, recursive inventory, registry, reservation or physical
cleanup is performed. Private descriptor paths never enter errors or output.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys

from .safeio import GateError

MAX_INPUT_BYTES = 256 * 1024


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        # argparse's default includes supplied values, possibly private paths.
        raise GateError("resource_plan_arguments_invalid")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GateError("resource_plan_input_duplicate_key")
        result[key] = value
    return result


def _constant(_value):
    raise GateError("resource_plan_input_invalid_json")


def read_input(selected: str) -> dict:
    try:
        if selected == "-":
            stream = getattr(sys.stdin, "buffer", sys.stdin)
            raw = stream.read(MAX_INPUT_BYTES + 1)
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
        else:
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            # Refuse a link even on a platform without O_NOFOLLOW. Metadata
            # reading remains observational, not a qualified deletion fence.
            before = os.lstat(selected)
            if not stat.S_ISREG(before.st_mode):
                raise GateError("resource_plan_input_regular_required")
            fd = os.open(selected, flags)
            with os.fdopen(fd, "rb") as stream:
                opened = os.fstat(stream.fileno())
                if (not stat.S_ISREG(opened.st_mode)
                        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)):
                    raise GateError("resource_plan_input_identity_changed")
                if opened.st_size > MAX_INPUT_BYTES:
                    raise GateError("resource_plan_input_bound")
                raw = stream.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise GateError("resource_plan_input_bound")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_constant)
        if not isinstance(value, dict):
            raise GateError("resource_plan_input_object_required")
        return value
    except GateError:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        raise GateError("resource_plan_input_unavailable_or_invalid") from exc


def command(argv: list[str]) -> tuple[dict, int]:
    parser = _Parser(prog="agentos project resource")
    sub = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    plan = sub.add_parser("plan", help="Observe explicit resources and capacity; never reserve or delete")
    plan.add_argument("--input", required=True, metavar="PATH|-",
                      help="Private observation descriptor, at most 256 KiB; '-' reads stdin")
    args = parser.parse_args(argv)
    from .project_resources import observe_plan

    return observe_plan(read_input(args.input)), 0
