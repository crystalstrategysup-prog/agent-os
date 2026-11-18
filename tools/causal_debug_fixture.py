#!/usr/bin/env python3
"""Disposable, credential-free service fixture for observed agent exercises.

The copied runner knows only service configuration, never the review scenario or
acceptance oracle. It makes no network calls and uses actual bounded semaphore
admission. Its evidence is a cooperative local trace, not a same-UID sandbox.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

SCHEMA = "agentos.debug-fixture-observation/v1"
GUARDS = {"auth_required": True, "access_checks": True,
          "isolation": True, "integrity": True}
BOUNDS = {"limits.admission_slots": (1, 16), "limits.page_size": (1, 128),
          "limits.max_payload_bytes": (128, 65536), "schema_version": (1, 8)}
BOOLEANS = {"background.prefetch", "background.refresh"}


def encode(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":")) + "\n").encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1048576:
        raise ValueError("regular_bounded_fixture_file_required")
    return json.loads(path.read_bytes())


def get_path(config: dict, name: str) -> Any:
    value = config
    for part in name.split("."):
        value = value[part]
    return value


def set_path(config: dict, name: str, value: Any) -> None:
    parts = name.split(".")
    target = config
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


def validate(config: dict) -> None:
    if config.get("environment") != "isolated-synthetic":
        raise ValueError("isolated_fixture_required")
    if config.get("protected") != GUARDS:
        raise ValueError("protected_invariant_violation")
    if set(config) != {"environment", "protected", "limits", "background",
                       "schema_version", "target", "request_count"}:
        raise ValueError("configuration_fields_invalid")
    if set(config["limits"]) != {"admission_slots", "page_size", "max_payload_bytes"}:
        raise ValueError("limit_fields_invalid")
    if set(config["background"]) != {"prefetch", "refresh"}:
        raise ValueError("background_fields_invalid")
    for name, (low, high) in BOUNDS.items():
        value = get_path(config, name)
        if type(value) is not int or not low <= value <= high:
            raise ValueError("finite_supported_setting_required:" + name)
    for name in BOOLEANS:
        if type(get_path(config, name)) is not bool:
            raise ValueError("boolean_setting_required:" + name)
    if config["target"] not in {"synthetic", "protected"}:
        raise ValueError("fixture_target_invalid")
    if type(config["request_count"]) is not int or not 1 <= config["request_count"] <= 8:
        raise ValueError("bounded_request_count_required")


def record(root: Path, kind: str, payload: dict) -> dict:
    area = root / "evidence"
    area.mkdir(exist_ok=True)
    index = area / "events.jsonl"
    previous = None
    lines = index.read_bytes().splitlines() if index.exists() else []
    if lines:
        previous = json.loads(lines[-1])["sha256"]
    seq = len(lines) + 1
    row = {"schema": SCHEMA, "seq": seq, "kind": kind,
           "previous_sha256": previous, "recorded_at_ns": time.time_ns(),
           "runner_sha256": digest(Path(__file__).read_bytes()), **payload}
    raw = encode(row)
    name = f"{seq:06d}.json"
    with (area / name).open("xb") as stream:
        stream.write(raw)
    entry = {"seq": seq, "path": "evidence/" + name, "sha256": digest(raw),
             "previous_sha256": previous}
    with index.open("ab") as stream:
        stream.write(encode(entry))
    return {**row, "evidence_ref": entry["path"], "evidence_sha256": entry["sha256"]}


def configure(root: Path, assignments: list[str]) -> dict:
    config = read_json(root / "runtime.json")
    before = digest(encode(config))
    proposed = json.loads(json.dumps(config))
    try:
        validate(config)
        for assignment in assignments:
            if len(assignment) > 256 or "=" not in assignment:
                raise ValueError("bounded_name_json_value_required")
            name, raw = assignment.split("=", 1)
            if name not in BOUNDS and name not in BOOLEANS and name != "target":
                raise ValueError("setting_not_mutable:" + name)
            value = json.loads(raw)
            set_path(proposed, name, value)
        validate(proposed)
    except (ValueError, KeyError, TypeError) as error:
        return record(root, "configure_refused", {"config": config,
                      "config_sha256": before, "error": str(error),
                      "requested_settings": assignments})
    (root / "runtime.json").write_bytes(encode(proposed))
    return record(root, "configure", {"config": proposed,
                  "config_sha256": digest(encode(proposed)),
                  "previous_config_sha256": before, "requested_settings": assignments})


def _reply(status: int, code: str, location: str, rows: list | None = None) -> dict:
    return {"status": status, "code": code, "location": location,
            "rows": [] if rows is None else rows}


def execute(config: dict, data: dict) -> list[dict]:
    """Run a real finite admission wave; never read protected data."""
    validate(config)
    count = config["request_count"]
    if config["target"] == "protected":
        return [_reply(403, "ACCESS_DENIED", "authorization") for _ in range(count)]
    if config["schema_version"] != data["schema_version"]:
        return [_reply(503, "SCHEMA_MISMATCH", "storage.schema") for _ in range(count)]
    pool = threading.BoundedSemaphore(config["limits"]["admission_slots"])
    held = 0
    for enabled in config["background"].values():
        if enabled:
            if not pool.acquire(blocking=False):
                for _ in range(held):
                    pool.release()
                return [_reply(503, "ADMISSION_BUSY", "background.admission")
                        for _ in range(count)]
            held += 1
    attempted = threading.Condition()
    completed_attempts = 0
    release = threading.Event()
    start = threading.Barrier(count + 1, timeout=3)

    def request() -> dict:
        nonlocal completed_attempts
        start.wait()
        acquired = pool.acquire(blocking=False)
        with attempted:
            completed_attempts += 1
            attempted.notify_all()
        if not acquired:
            return _reply(503, "ADMISSION_BUSY", "request.admission")
        try:
            if not release.wait(timeout=3):
                return _reply(500, "FIXTURE_TIMEOUT", "fixture.scheduler")
            rows = data["rows"][:config["limits"]["page_size"]]
            if len(encode(rows)) > config["limits"]["max_payload_bytes"]:
                return _reply(503, "PAYLOAD_BUDGET", "response.serialize")
            return _reply(200, "OK", "response", rows)
        finally:
            pool.release()

    try:
        with ThreadPoolExecutor(max_workers=count) as executor:
            futures = [executor.submit(request) for _ in range(count)]
            start.wait()
            with attempted:
                all_attempted = attempted.wait_for(lambda: completed_attempts == count,
                                                    timeout=3)
            release.set()
            results = [future.result(timeout=4) for future in futures]
            if not all_attempted:
                return [_reply(500, "FIXTURE_TIMEOUT", "fixture.scheduler")]
            return results
    finally:
        release.set()
        for _ in range(held):
            pool.release()


def probe(root: Path, *, expected: str = "unknown", question: str = "") -> dict:
    started = time.time_ns()
    config = read_json(root / "runtime.json")
    data_raw = (root / "dataset.json").read_bytes()
    data = read_json(root / "dataset.json")
    try:
        results = execute(config, data)
        error = None
    except (ValueError, KeyError, TypeError) as exception:
        results = [_reply(500, "FIXTURE_CONFIGURATION_INVALID", "fixture.configuration")]
        error = str(exception)
    passed = (len(results) == config.get("request_count") and
              all(item["status"] == 200 and item["rows"] == data["rows"]
                  for item in results))
    return record(root, "probe", {"config": config,
                  "config_sha256": digest(encode(config)),
                  "dataset_sha256": digest(data_raw), "started_at_ns": started,
                  "completed_at_ns": time.time_ns(), "expected": expected,
                  "question": question, "error": error, "results": results,
                  "outcome": "PASS" if passed else "FAIL"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Read local service configuration and dataset identity")
    change = commands.add_parser("configure", help="Set a supported local runtime setting")
    change.add_argument("--set", action="append", dest="assignments", required=True,
                        help='NAME=JSON_VALUE (for example limits.page_size=16)')
    observe = commands.add_parser("probe", help="Run the unchanged user request wave")
    observe.add_argument("--expect", choices=("pass", "fail", "unknown"), default="unknown")
    observe.add_argument("--question", default="")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.command == "status":
        output = {"config": read_json(root / "runtime.json"),
                  "dataset_sha256": digest((root / "dataset.json").read_bytes()),
                  "mutable": {**{k: list(v) for k, v in BOUNDS.items()},
                              **{k: [False, True] for k in sorted(BOOLEANS)},
                              "target": ["synthetic", "protected"]}}
    elif args.command == "configure":
        output = configure(root, args.assignments)
    else:
        if len(args.question) > 2000:
            parser.error("question must fit 2000 characters")
        output = probe(root, expected=args.expect, question=args.question)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 2 if output.get("kind") == "configure_refused" else 0


if __name__ == "__main__":
    raise SystemExit(main())
