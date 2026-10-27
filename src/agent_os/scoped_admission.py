"""Finite same-task file admission. No source inventory or command runner.

Cooperative single-writer POSIX storage, not a hostile same-UID sandbox.
Authority is supplied by the caller and must be verified by the target adapter.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath

from .safeio import GateError, MAX_JSON, atomic_bytes, digest, lock, now, read_json_input, sha, within

SCHEMA = "agentos.scoped-file-admission/v1"
MAX_FILE = 1024 * 1024


def _fail(condition, code):
    if not condition:
        raise GateError("scoped_" + code)


def _rel(value):
    _fail(isinstance(value, str) and bool(value) and len(value) <= 1024, "path")
    p = PurePosixPath(value)
    _fail(not p.is_absolute() and str(p) == value and not set(p.parts) & {".", ".."}
          and "\\" not in value and not any(ord(c) < 32 for c in value), "path")
    return value


def _hash(value, absent=False):
    _fail((absent and value is None) or (isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)), "hash")


def _bytes(root, rel, limit=MAX_FILE):
    p = within(root, _rel(rel))
    try:
        s = p.lstat()
    except FileNotFoundError:
        return None
    _fail(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, "regular_single_link_required")
    _fail(s.st_size <= limit, "size_limit")
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        f = os.fstat(fd)
        _fail((s.st_dev, s.st_ino, s.st_size) == (f.st_dev, f.st_ino, f.st_size), "file_changed")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            b = stream.read(limit + 1)
        _fail(len(b) <= limit, "size_limit")
        return b
    finally:
        os.close(fd)


def _json(data):
    from .safeio import _parse_json
    _fail(data is not None, "metadata_missing")
    value = _parse_json(data)
    _fail(isinstance(value, dict), "metadata_object")
    return value


def _encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _pin(data):
    return None if data is None else sha(data)


def _blocked(path, held):
    return any(path == h or path.startswith(h + "/") or h.startswith(path + "/") for h in held)


def _validate(req):
    _fail(isinstance(req, dict) and set(req) == {
        "schema", "operation", "task", "session_id", "turn_id", "actor",
        "authority", "reviewer", "expected", "held_paths", "files", "create_directories"
    }, "request_fields")
    _fail(req["schema"] == SCHEMA, "schema")
    for k in ("operation", "task"):
        _fail(isinstance(req[k], str) and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", req[k]), "identifier")
    for k in ("session_id", "turn_id", "actor", "authority", "reviewer"):
        _fail(isinstance(req[k], str) and bool(req[k].strip()) and len(req[k]) <= 2000, "identity")
    _fail(isinstance(req["expected"], dict) and set(req["expected"]) == {"project", "task", "events", "binding"}, "expected")
    for value in req["expected"].values():
        _hash(value)
    _fail(isinstance(req["held_paths"], list) and len(req["held_paths"]) <= 128, "held_paths")
    held = [_rel(p) for p in req["held_paths"]]
    _fail(isinstance(req["files"], list) and 1 <= len(req["files"]) <= 16, "file_count")
    targets, sources = [], []
    for row in req["files"]:
        _fail(isinstance(row, dict) and set(row) == {"source", "target", "before", "after"}, "file_fields")
        for k in ("source", "target"):
            path = _rel(row[k])
            _fail(path.split("/")[0] not in {".agentos", ".git"}, "control_path")
            _fail(not _blocked(path, held), "held_overlap")
        _hash(row["before"], True)
        _hash(row["after"])
        targets.append(row["target"])
        sources.append(row["source"])
    _fail(len(set(targets)) == len(targets) and not set(targets) & set(sources), "overlap")
    _fail(not any(a != b and (a.startswith(b + "/") or b.startswith(a + "/")) for a in targets for b in targets), "overlap")
    dirs = req["create_directories"]
    _fail(isinstance(dirs, list) and len(dirs) <= 32 and len(set(dirs)) == len(dirs), "directories")
    for d in dirs:
        _rel(d)
        _fail(not _blocked(d, held) and any(t.startswith(d + "/") for t in targets), "directory_scope")


def require_clear(root):
    path = within(root, ".agentos/scoped-transaction.json")
    if path.exists():
        raise GateError("scoped_reconciliation_required")


def _row(path, before, after, mode=0o600):
    return {"path": path, "before": None if before is None else base64.b64encode(before).decode(),
            "after": base64.b64encode(after).decode(), "mode": mode}


def _unpack(row, key):
    return None if row[key] is None else base64.b64decode(row[key], validate=True)


def apply(root: Path, home: Path, req: dict, *, plan=False):
    """Apply or reconcile one exact request. Same operation replay never re-admits."""
    from . import project as p, task_metadata as tm
    from .turns import turn_path
    from .refusal_recovery import require_clear as refusal_clear
    from .interrupted_continuation import require_clear as continuation_clear

    _validate(req)  # validate negative boundaries before source reads
    root = root.absolute()
    _fail(root == root.resolve() and root.is_dir(), "canonical_root_required")
    home = home.absolute()
    _fail(home == home.resolve(), "canonical_home_required")
    task_rel = f".agentos/tasks/{req['task']}/task.json"
    events_rel = f".agentos/tasks/{req['task']}/events.jsonl"
    receipt_rel = f".agentos/tasks/{req['task']}/scoped/{req['operation']}.json"
    journal_rel = ".agentos/scoped-transaction.json"
    binding_rel = turn_path(home, req["session_id"]).relative_to(home).as_posix()
    for path in (".agentos/project.json", task_rel, events_rel, receipt_rel, journal_rel):
        _fail(not _blocked(path, req["held_paths"]), "metadata_held_overlap")
    task_limit = tm.limit(root)
    with lock(within(root, ".agentos/write.lock")), lock(within(home, "state/turns.lock")):
        refusal_clear(root)
        continuation_clear(root)
        _fail(not within(root, ".agentos/entry-transaction.json").exists(), "entry_recovery_required")
        project_bytes = _bytes(root, ".agentos/project.json", MAX_JSON)
        binding_bytes = _bytes(home, binding_rel, MAX_JSON)
        _fail(_pin(project_bytes) == req["expected"]["project"], "project_cas")
        _fail(_pin(binding_bytes) == req["expected"]["binding"], "binding_cas")
        project, binding = _json(project_bytes), _json(binding_bytes)
        _fail(project.get("active_task") == req["task"], "active_task")
        _fail(all(binding.get(k) == v for k, v in {
            "schema": "agentos.turn/v1", "root": str(root), "task_id": req["task"],
            "session_id": req["session_id"], "turn_id": req["turn_id"], "status": "ENTERED"
        }.items()), "binding_identity")
        journal_bytes = _bytes(root, journal_rel, MAX_JSON)
        receipt_bytes = _bytes(root, receipt_rel, MAX_JSON)
        old = _json(journal_bytes or receipt_bytes) if journal_bytes or receipt_bytes else None
        if old:
            _fail(old.get("request") == req and old.get("root") == str(root)
                  and old.get("home") == str(home), "operation_conflict")
            _fail(old.get("schema") == "agentos.scoped-transaction/v1", "journal_schema")
            rows = old.get("rows")
            _fail(isinstance(rows, list) and [x.get("path") for x in rows] ==
                  [x["target"] for x in req["files"]] + [task_rel, events_rel], "journal_paths")
            task_before = _unpack(rows[-2], "before")
            event_before = _unpack(rows[-1], "before")
            _fail(_pin(task_before) == req["expected"]["task"] and _pin(event_before) == req["expected"]["events"], "journal_preimage")
        else:
            task_before = _bytes(root, task_rel, task_limit)
            event_before = _bytes(root, events_rel, MAX_JSON)
            _fail(_pin(task_before) == req["expected"]["task"], "task_cas")
            _fail(_pin(event_before) == req["expected"]["events"], "events_cas")
        task = _json(task_before)
        _fail(task.get("id") == req["task"] and task.get("project_id") == project.get("id")
              and task.get("session_id") == req["session_id"] and task.get("turn_id") == req["turn_id"], "task_identity")
        _fail(task.get("status") in {"READY", "VERIFYING", "SCOPED_APPLIED"} and task.get("ready"), "prior_readiness_required")
        _fail(type(task.get("revision")) is int and 1 <= task["revision"] < 2147483647, "revision")
        # Existing document gate reads only explicitly registered paths. Validate
        # those against holds before invoking it, never call check/assess/snapshot.
        document_paths = [x["path"] for x in project["documents"].values()]
        _fail(not set(document_paths) & {x["target"] for x in req["files"]}, "registered_document_write_requires_separate_entry")
        for path in document_paths:
            _rel(path)
            _fail(not _blocked(path, req["held_paths"]), "document_held_overlap")
            _bytes(root, path, 512 * 1024)
        _fail(p.document_check(root, task)["status"] == "PASS", "documents_not_current")
        stamp = old["at"] if old else now()
        source_bytes = []
        target_before = []
        modes = []
        for index, item in enumerate(req["files"]):
            data = _bytes(root, item["source"])
            _fail(data is not None and sha(data) == item["after"], "source_pin")
            source_bytes.append(data)
            before = _unpack(old["rows"][index], "before") if old else _bytes(root, item["target"])
            _fail(_pin(before) == item["before"], "target_preimage")
            target_before.append(before)
            modes.append(old["rows"][index]["mode"] if old else
                         stat.S_IMODE(within(root, item["target"]).stat().st_mode) if before is not None else 0o644)
            _fail(modes[-1] in {0o600, 0o644}, "file_mode")
        directories = req["create_directories"]
        for target in [x["target"] for x in req["files"]]:
            for parent in reversed(PurePosixPath(target).parents):
                if str(parent) == ".":
                    continue
                pp = within(root, str(parent))
                if not pp.exists():
                    _fail(str(parent) in directories, "undeclared_parent")
                else:
                    _fail(pp.is_dir(), "parent_not_directory")
        scoped = {"operation": req["operation"], "at": stamp, "actor": req["actor"],
                  "authority": req["authority"], "reviewer": req["reviewer"],
                  "request_sha256": digest(req), "previous_revision": task["revision"],
                  "files": req["files"], "status": "SCOPED_APPLIED",
                  "global_readiness": "HISTORICAL_NOT_REVALIDATED", "business_acceptance": False}
        after_task = json.loads(json.dumps(task))
        after_task["revision"] += 1
        after_task["status"] = "SCOPED_APPLIED"
        after_task.setdefault("scoped_admissions", []).append(scoped)
        after_task["answers"]["write_paths"] = list(dict.fromkeys(task["answers"]["write_paths"] + [x["target"] for x in req["files"]]))
        tb = tm.encoded(after_task, task_limit)
        event = {"at": stamp, "event": "SCOPED_APPLIED", "details": scoped}
        eb = event_before + (json.dumps(event, ensure_ascii=False) + "\n").encode()
        _fail(len(eb) <= MAX_JSON, "events_limit")
        rows = [_row(x["target"], target_before[i], source_bytes[i], modes[i]) for i, x in enumerate(req["files"])]
        rows += [_row(task_rel, task_before, tb), _row(events_rel, event_before, eb)]
        record = {"schema": "agentos.scoped-transaction/v1", "root": str(root), "home": str(home),
                  "at": stamp, "request": req, "rows": rows, "receipt": scoped}
        encoded = _encode(record)
        _fail(len(encoded) <= MAX_JSON, "journal_limit")
        if old:
            _fail(old == record, "journal_integrity")
        if receipt_bytes:
            _fail(receipt_bytes == encoded, "receipt_conflict")
        # All preconditions/reconciliation checks finish before any product write.
        for row in rows:
            limit = task_limit if row["path"] == task_rel else MAX_JSON
            current = _bytes(root, row["path"], limit)
            allowed = [_unpack(row, "after")] if receipt_bytes and not journal_bytes else [_unpack(row, "before"), _unpack(row, "after")]
            _fail(current in allowed, "unknown_effect")
        if receipt_bytes and not journal_bytes:
            return {**scoped, "replayed": True, "receipt_path": receipt_rel}
        if plan:
            return {"status": "SCOPED_PLAN", "request_sha256": digest(req),
                    "reads": [".agentos/project.json", task_rel, events_rel] + document_paths +
                             [x[k] for x in req["files"] for k in ("source", "target")],
                    "user_reads": [binding_rel], "writes": [x["path"] for x in rows] + [journal_rel, receipt_rel],
                    "create_directories": directories, "temporary_files": "one same-directory .agentos-tmp-* per atomic write",
                    "external_authority_granted": False}
        if not journal_bytes:
            atomic_bytes(within(root, journal_rel), encoded)
        for directory in sorted(directories, key=lambda x: len(PurePosixPath(x).parts)):
            within(root, directory).mkdir(exist_ok=True, mode=0o755)
        for row in rows:
            current = _bytes(root, row["path"], task_limit if row["path"] == task_rel else MAX_JSON)
            before, after = _unpack(row, "before"), _unpack(row, "after")
            _fail(current in (before, after), "unknown_effect")
            if current != after:
                atomic_bytes(within(root, row["path"]), after, row["mode"])
            _fail(_bytes(root, row["path"], task_limit if row["path"] == task_rel else MAX_JSON) == after, "readback")
        atomic_bytes(within(root, receipt_rel), encoded)
        _fail(_bytes(root, receipt_rel, MAX_JSON) == encoded, "receipt_readback")
        within(root, journal_rel).unlink()
        return {**scoped, "replayed": False, "receipt_path": receipt_rel}


def command(argv, home):
    parser = argparse.ArgumentParser(prog="agentos project scoped-apply")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args(argv)
    return apply(args.root, home, read_json_input(args.request), plan=args.plan), 0
