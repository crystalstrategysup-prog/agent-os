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
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

SCHEMA = "agentos.debug-fixture-observation/v1"
ACCEPTANCE_REVISION = "agentos.causal-followup/v2"
MAX_EVENTS = 128
MAX_RECORD_BYTES = 256 * 1024
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


def entries(root: Path) -> list[dict]:
    index = root / "evidence/events.jsonl"
    if not index.exists():
        return []
    if index.is_symlink() or index.stat().st_size > 1024 * 1024:
        raise ValueError("bounded_regular_evidence_index_required")
    rows = [json.loads(line) for line in index.read_bytes().splitlines()]
    if len(rows) > MAX_EVENTS:
        raise ValueError("evidence_count_excessive")
    return rows


def observations(root: Path) -> list[dict]:
    return [read_json(root / entry["path"]) for entry in entries(root)]


def unresolved_operations(root: Path) -> set[str]:
    rows = observations(root)
    begun = {row["operation_id"] for row in rows if row["kind"] == "probe_intent"}
    completed = {row["operation_id"] for row in rows if row["kind"] == "probe" and "operation_id" in row}
    return begun - completed


def record(root: Path, kind: str, payload: dict) -> dict:
    area = root / "evidence"
    area.mkdir(exist_ok=True)
    index = area / "events.jsonl"
    previous = None
    lines = entries(root)
    if len(lines) >= MAX_EVENTS:
        raise ValueError("evidence_budget_exhausted")
    if lines:
        previous = lines[-1]["sha256"]
    seq = len(lines) + 1
    row = {"schema": SCHEMA, "seq": seq, "kind": kind,
           "previous_sha256": previous, "recorded_at_ns": time.time_ns(),
           "runner_sha256": digest(Path(__file__).read_bytes()), **payload}
    raw = encode(row)
    if len(raw) > MAX_RECORD_BYTES:
        raise ValueError("observation_byte_budget_exceeded")
    name = f"{seq:06d}.json"
    with (area / name).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    entry = {"seq": seq, "path": "evidence/" + name, "sha256": digest(raw),
             "previous_sha256": previous}
    with index.open("ab") as stream:
        stream.write(encode(entry))
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(area, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return {**row, "evidence_ref": entry["path"], "evidence_sha256": entry["sha256"]}


def configure(root: Path, assignments: list[str]) -> dict:
    config = read_json(root / "runtime.json")
    before = digest(encode(config))
    proposed = json.loads(json.dumps(config))
    try:
        if unresolved_operations(root):
            raise ValueError("original_operation_unreconciled")
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


def execute(config: dict, data: dict, telemetry: dict | None = None) -> list[dict]:
    """Run real finite admission; telemetry records actual semaphore operations."""
    validate(config)
    count = config["request_count"]
    telemetry = {} if telemetry is None else telemetry
    telemetry.update({"schema": "agentos.admission-observation/v1", "stage": "NOT_REACHED",
                      "capacity": config["limits"]["admission_slots"], "events": [],
                      "available_before": None, "available_after": None,
                      "active_after": [], "pending_after": [],
                      "queue_policy": "nonblocking_reject"})

    def replies(status, code, location):
        return [{**_reply(status, code, location), "request_id": f"request-{i + 1}"}
                for i in range(count)]

    if config["target"] == "protected":
        return replies(403, "ACCESS_DENIED", "authorization")
    if config["schema_version"] != data["schema_version"]:
        return replies(503, "SCHEMA_MISMATCH", "storage.schema")
    pool = threading.BoundedSemaphore(config["limits"]["admission_slots"])
    telemetry.update(stage="MEASURED", available_before=pool._value)
    tracking = threading.Lock()
    active: set[str] = set()
    finished: set[str] = set()
    held: list[str] = []
    attempted = threading.Condition()
    completed_attempts = 0
    release_wave = threading.Event()
    start = threading.Barrier(count + 1, timeout=3)

    def event(kind, owner):
        telemetry["events"].append({
            "seq": len(telemetry["events"]) + 1, "monotonic_ns": time.monotonic_ns(),
            "kind": kind, "owner": owner, "active_set": sorted(active),
            "available": pool._value,
        })

    def acquire(owner):
        with tracking:
            acquired = pool.acquire(blocking=False)
            if acquired:
                active.add(owner)
            event("admit" if acquired else "reject", owner)
            return acquired

    def give_back(owner):
        with tracking:
            pool.release()
            active.remove(owner)
            event("release", owner)

    def finish():
        with tracking:
            telemetry.update(available_after=pool._value, active_after=sorted(active),
                             pending_after=sorted(
                                 {f"request-{i + 1}" for i in range(count)} - finished),
                             max_active_observed=max(
                                 (len(e["active_set"]) for e in telemetry["events"]), default=0),
                             rejection_count=sum(e["kind"] == "reject"
                                                 for e in telemetry["events"]))

    def request(index: int) -> dict:
        nonlocal completed_attempts
        owner = f"request-{index + 1}"
        start.wait()
        acquired = acquire(owner)
        with attempted:
            completed_attempts += 1
            attempted.notify_all()
        try:
            if not acquired:
                return {**_reply(503, "ADMISSION_BUSY", "request.admission"),
                        "request_id": owner}
            if not release_wave.wait(timeout=3):
                return {**_reply(500, "FIXTURE_TIMEOUT", "fixture.scheduler"),
                        "request_id": owner}
            rows = data["rows"][:config["limits"]["page_size"]]
            if len(encode(rows)) > config["limits"]["max_payload_bytes"]:
                return {**_reply(503, "PAYLOAD_BUDGET", "response.serialize"),
                        "request_id": owner}
            return {**_reply(200, "OK", "response", rows), "request_id": owner}
        finally:
            if acquired:
                give_back(owner)
            with tracking:
                finished.add(owner)

    try:
        for name, enabled in config["background"].items():
            if enabled:
                owner = "background." + name
                if not acquire(owner):
                    # The wave is rejected before foreground requests start.
                    finished.update(f"request-{i + 1}" for i in range(count))
                    return replies(503, "ADMISSION_BUSY", "background.admission")
                held.append(owner)
        with ThreadPoolExecutor(max_workers=count) as executor:
            futures = [executor.submit(request, i) for i in range(count)]
            start.wait()
            with attempted:
                all_attempted = attempted.wait_for(lambda: completed_attempts == count,
                                                    timeout=3)
            release_wave.set()
            results = [future.result(timeout=4) for future in futures]
            if not all_attempted:
                return replies(500, "FIXTURE_TIMEOUT", "fixture.scheduler")
            return results
    finally:
        release_wave.set()
        for owner in reversed(held):
            give_back(owner)
        finish()


def _identity(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
        raise ValueError("bounded_operation_id_required")
    return value


def begin_probe(root: Path, *, expected: str, question: str,
                operation_id: str | None = None) -> dict:
    """Retain intent before execution, including when later delivery is lost."""
    config = read_json(root / "runtime.json")
    validate(config)
    if not question.strip() or len(question) > 2000 or expected not in {"pass", "fail", "unknown"}:
        raise ValueError("bounded_pre_run_question_and_prediction_required")
    operation_id = _identity(operation_id or f"probe-{len(entries(root)) + 1:06d}")
    previous = observations(root)
    unresolved = unresolved_operations(root)
    if unresolved or any(row.get("operation_id") == operation_id for row in previous):
        return record(root, "probe_refused", {
            "config": config, "config_sha256": digest(encode(config)),
            "operation_id": operation_id, "error": "original_operation_requires_lookup",
            "unresolved_operation_ids": sorted(unresolved),
        })
    # Reserve a terminal receipt before admitting an effect.
    if len(entries(root)) + 2 > MAX_EVENTS:
        raise ValueError("intent_and_result_budget_required")
    return record(root, "probe_intent", {
        "operation_id": operation_id, "expected": expected, "question": question,
        "config": config, "config_sha256": digest(encode(config)),
        "dataset_sha256": digest((root / "dataset.json").read_bytes()),
        "request_count": config["request_count"],
    })


def complete_probe(root: Path, intent: dict) -> dict:
    started = time.time_ns()
    config = read_json(root / "runtime.json")
    data_raw = (root / "dataset.json").read_bytes()
    if (config != intent["config"] or digest(data_raw) != intent["dataset_sha256"]):
        raise ValueError("intent_inputs_changed")
    data = read_json(root / "dataset.json")
    admission: dict = {}
    try:
        results = execute(config, data, admission)
        error = None
    except (ValueError, KeyError, TypeError) as exception:
        results = [_reply(500, "FIXTURE_CONFIGURATION_INVALID", "fixture.configuration")]
        error = str(exception)
    passed = (len(results) == config.get("request_count") and
              all(item["status"] == 200 and item["rows"] == data["rows"]
                  for item in results))
    return {"operation_id": intent["operation_id"],
            "intent_ref": intent["evidence_ref"], "intent_sha256": intent["evidence_sha256"],
            "config": config, "config_sha256": digest(encode(config)),
            "dataset_sha256": digest(data_raw), "started_at_ns": started,
            "completed_at_ns": time.time_ns(), "expected": intent["expected"],
            "question": intent["question"], "error": error, "results": results,
            "admission": admission, "outcome": "PASS" if passed else "FAIL"}


def probe(root: Path, *, expected: str = "unknown", question: str = "",
          operation_id: str | None = None) -> dict:
    intent = begin_probe(root, expected=expected, question=question, operation_id=operation_id)
    if intent["kind"] == "probe_refused":
        return intent
    return record(root, "probe", complete_probe(root, intent))


def retain_unreceived_probe(root: Path, operation_id: str, question: str) -> dict:
    """Preparation only: execute once, retain its result, withhold delivery.

    This models a stopped initiating chat with an unknown outcome. It does not
    start, stop or simulate control over an owner process or an external service.
    """
    intent = begin_probe(root, expected="pass", question=question, operation_id=operation_id)
    if intent["kind"] != "probe_intent":
        raise ValueError("new_pending_operation_required")
    result = complete_probe(root, intent)
    retained = {"schema": "agentos.synthetic-operation/v1",
                "operation_id": operation_id, "status": "COMPLETED",
                "process_observation": "TERMINAL_RECEIPT_RETAINED",
                "effect_count": 1, "result": result}
    area = root / "operations"
    if area.is_symlink():
        raise ValueError("operation_directory_symlink_refused")
    area.mkdir(exist_ok=True)
    with (area / (operation_id + ".json")).open("xb") as stream:
        stream.write(encode(retained))
        stream.flush()
        os.fsync(stream.fileno())
    return intent


def operation_get(root: Path, operation_id: str) -> dict:
    """Read original outcome; append audit/readback only, never rerun the wave."""
    operation_id = _identity(operation_id)
    rows = observations(root)
    intent = next((row for row in rows if row["kind"] == "probe_intent"
                   and row["operation_id"] == operation_id), None)
    if intent is None:
        raise ValueError("original_operation_not_found")
    current = read_json(root / "runtime.json")
    retained_path = root / "operations" / (operation_id + ".json")
    if retained_path.parent.is_symlink():
        raise ValueError("operation_directory_symlink_refused")
    terminal = next((row for row in rows if row["kind"] == "probe"
                     and row.get("operation_id") == operation_id), None)
    retained = read_json(retained_path) if retained_path.exists() else None
    if retained is not None:
        if (retained.get("schema") != "agentos.synthetic-operation/v1"
                or retained.get("operation_id") != operation_id
                or retained.get("status") != "COMPLETED"
                or retained.get("effect_count") != 1
                or retained["result"]["operation_id"] != operation_id):
            raise ValueError("retained_operation_binding_invalid")
        result = retained["result"]
        original = entries(root)[intent["seq"] - 1]
        if (result["intent_ref"] != original["path"]
                or result["intent_sha256"] != original["sha256"]
                or result["config"] != intent["config"]):
            raise ValueError("retained_operation_intent_mismatch")
    status = "COMPLETED" if terminal is not None or retained is not None else "UNKNOWN"
    if len(entries(root)) + (2 if retained and terminal is None else 1) > MAX_EVENTS:
        raise ValueError("readback_and_result_budget_required")
    readback = record(root, "operation_readback", {
        "config": current, "config_sha256": digest(encode(current)),
        "operation_id": operation_id, "status": status,
        "effect_count": 1 if status == "COMPLETED" else None,
        "process_observation": "TERMINAL_RECEIPT_RETAINED" if status == "COMPLETED" else "UNKNOWN",
        "retained_result_ref": "operations/" + operation_id + ".json" if retained else None,
        "retained_result_sha256": digest(retained_path.read_bytes()) if retained else None,
        "executes_operation": False,
    })
    if retained is not None and terminal is None:
        terminal = record(root, "probe", {**retained["result"],
                                          "reconciled_by": readback["evidence_ref"]})
    return {"operation_id": operation_id, "status": status, "readback": readback,
            "observation": terminal, "executes_operation": False}


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
    observe.add_argument("--question", required=True,
                         help="Pre-run hypothesis and differing predicted outcomes")
    observe.add_argument("--operation-id", help="Stable identity for lookup after an uncertain result")
    lookup = commands.add_parser("operation-get", help="Read original outcome; never repeat its execution")
    lookup.add_argument("--operation-id", required=True)
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
    elif args.command == "operation-get":
        output = operation_get(root, args.operation_id)
    else:
        if len(args.question) > 2000:
            parser.error("question must fit 2000 characters")
        output = probe(root, expected=args.expect, question=args.question,
                       operation_id=args.operation_id)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 2 if output.get("kind") in {"configure_refused", "probe_refused"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
