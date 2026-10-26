#!/usr/bin/env python3
"""Opt-in owning-matrix checkpoints; local files only, no executor operations.

CHECKPOINT.lock is a cooperative flock for all participating source writers.
IMPORT.lock prevents a projection of a partially installed source transaction.
Neither lock is an OS compare-and-swap against a writer ignoring the protocol.
Before/after images are retained. Recovery never repeats an external action.
"""
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import tempfile

import import_matrix as adapter
import navigator as nav

PROFILE = ".atlas/WRITER.json"
LOCK = ".atlas/CHECKPOINT.lock"
PENDING = ".atlas/CHECKPOINT_PENDING.json"
OPERATIONS = ".atlas/checkpoints"
MAX_RECORD = 256 * 1024
MAX_SOURCE = 8 * 1024 * 1024
MAX_DOCUMENT = 2 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
PHASES = {"start": {"doing"}, "dispatch": {"doing"},
          "progress": {"doing", "waiting", "blocked", "partial"},
          "complete": {"done", "partial"}}
ACTIVITY_SOURCES = {"supported_native_route", "supported_native_wait", "collaboration", "supported_command"}
require = nav.require


def _text(value, limit=400):
    require(isinstance(value, str) and value.strip() and len(value) <= limit
            and "\x00" not in value, "CHECKPOINT_TEXT")
    return value


def _operation(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value),
            "CHECKPOINT_OPERATION_ID")
    return value


def _uint(value, limit):
    require(type(value) is int and 0 <= value <= limit, "CHECKPOINT_UNSIGNED_INTEGER")


def _pin_shape(value, *, path=True, limit=MAX_SOURCE):
    adapter.shape(value, ("path", "sha256", "bytes") if path else ("sha256", "bytes"), label="checkpoint.pin")
    if path:
        adapter.relative(value["path"])
    require(isinstance(value["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]), "CHECKPOINT_SHA256")
    _uint(value["bytes"], limit)


def _root(value):
    root = Path(value).absolute()
    require(root.is_dir(), "CHECKPOINT_ROOT")
    require(all(not p.is_symlink() for p in (root, *root.parents)), "CHECKPOINT_ROOT_SYMLINK")
    return root


def _state(root, rel, limit=MAX_SOURCE):
    adapter.relative(rel)
    path = root / rel
    require(not path.is_symlink(), "CHECKPOINT_SYMLINK:" + rel)
    raw = adapter.read(root, rel, limit)
    metadata = path.lstat()
    require(stat.S_ISREG(metadata.st_mode), "CHECKPOINT_REGULAR_FILE:" + rel)
    return raw, stat.S_IMODE(metadata.st_mode)


def _matches(raw, pin):
    return len(raw) == pin["bytes"] and adapter.sha(raw) == pin["sha256"]


def _pinned(root, pin, limit=MAX_SOURCE):
    _pin_shape(pin, limit=limit)
    raw = adapter.read(root, pin["path"], limit)
    require(_matches(raw, pin), "CHECKPOINT_PIN:" + pin["path"])
    return raw


def _new(root, rel, raw, mode=0o600):
    parent = str(Path(rel).parent)
    adapter.directory(root, parent, create=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(root / rel, flags, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    nav.sync_directory(root / parent)


def _replace(root, rel, raw, before, mode):
    """Replace only the exact observed bytes and mode, preserving that mode."""
    require(_state(root, rel) == (before, mode), "CHECKPOINT_SOURCE_CAS:" + rel)
    parent = root / str(Path(rel).parent)
    fd, temporary = tempfile.mkstemp(prefix=".checkpoint-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(_state(root, rel) == (before, mode), "CHECKPOINT_SOURCE_CAS:" + rel)
        os.replace(temporary, root / rel)
        nav.sync_directory(parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _lock(root):
    adapter.directory(root, ".atlas")
    require(not (root / LOCK).is_symlink(), "CHECKPOINT_LOCK_SYMLINK")
    fd = os.open(root / LOCK, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), "CHECKPOINT_LOCK_REGULAR_FILE")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise nav.Invalid("CHECKPOINT_WRITER_BUSY") from exc
        own = os.fstat(fd)
        live = (root / LOCK).lstat()
        require((own.st_dev, own.st_ino) == (live.st_dev, live.st_ino), "CHECKPOINT_LOCK_CHANGED")
        yield
    finally:
        os.close(fd)


def _profile(root, binding_path):
    raw = adapter.read(root, PROFILE, 256 * 1024)
    value = nav.parse(raw)
    adapter.shape(value, ("schema", "binding", "project_id", "writer", "matrix", "lock_path", "document_paths", "history"), label="checkpoint.profile")
    require(value["schema"] == "atlas.matrix-writer/v1" and value["lock_path"] == LOCK,
            "CHECKPOINT_PROFILE_SCHEMA_OR_LOCK")
    require(value["binding"] == binding_path, "CHECKPOINT_BINDING_MISMATCH")
    binding_raw = adapter.read(root, binding_path, 512 * 1024)
    binding = adapter.binding_model(binding_raw)
    require(value["project_id"] == binding["project"]["id"] and value["writer"] == binding["project"]["writer"],
            "CHECKPOINT_CURRENT_WRITER_MISMATCH")
    adapter.shape(value["matrix"], ("path", "pointer", "allowed_schema"), label="checkpoint.matrix")
    expected = {**binding["matrix"], "pointer": binding["matrix"].get("pointer", "")}
    require(value["matrix"] == expected, "CHECKPOINT_SOURCE_BINDING_MISMATCH")
    adapter.shape(value["history"], ("mode", "previous_payload_hash"), label="checkpoint.history")
    mode = "selected-canonical" if expected["pointer"] else "source-bytes"
    require(value["history"] == {"mode": "retained-operation-snapshots", "previous_payload_hash": mode},
            "CHECKPOINT_HISTORY_MODE")
    paths = value["document_paths"]
    require(isinstance(paths, list) and len(paths) <= 1000 and all(isinstance(p, str) for p in paths)
            and len(set(paths)) == len(paths), "CHECKPOINT_DOCUMENT_PATHS")
    bound = {d["path"] for d in binding["documents"]}
    for path in paths:
        adapter.relative(path)
        require(path in bound and not path.startswith(".atlas/") and path != expected["path"]
                and path != binding.get("semantic_catalog", {}).get("path"), "CHECKPOINT_DOCUMENT_NOT_BOUND:" + path)
        require(path not in binding["history"]["paths"] and not any(path == directory or path.startswith(directory + "/")
                    for directory in binding["history"]["directories"]), "CHECKPOINT_HISTORY_IS_NOT_DOCUMENT_DESTINATION:" + path)
    return value, raw, binding, binding_raw


def _record(raw):
    require(len(raw) <= MAX_RECORD, "CHECKPOINT_RECORD_LIMIT")
    value = nav.parse(raw)
    adapter.shape(value, ("schema", "operation_id", "project_id", "writer", "work_id", "phase", "at", "expected_source",
                          "executor_id", "status", "note", "next_action", "evidence", "document_edits"), ("activity",), label="checkpoint.record")
    require(value["schema"] == "atlas.checkpoint/v1", "CHECKPOINT_RECORD_SCHEMA")
    _operation(value["operation_id"])
    for key in ("project_id", "writer", "work_id", "executor_id"):
        _text(value[key])
        require(value[key] != "UNKNOWN", "CHECKPOINT_ACTOR_UNKNOWN")
    require(isinstance(value["phase"], str) and value["phase"] in PHASES and isinstance(value["status"], str)
            and value["status"] in PHASES[value["phase"]], "CHECKPOINT_PHASE_STATUS")
    nav.stamp(value["at"])
    _text(value["note"], 16384)
    _text(value["next_action"], 4096)
    source = value["expected_source"]
    adapter.shape(source, ("sha256", "bytes", "revision"), label="checkpoint.expected_source")
    _pin_shape({k: source[k] for k in ("sha256", "bytes")}, path=False)
    _uint(source["revision"], 2**53 - 1)
    require(isinstance(value["evidence"], list) and len(value["evidence"]) <= 32, "CHECKPOINT_EVIDENCE_LIMIT")
    for evidence in value["evidence"]:
        _pin_shape(evidence)
    require(value["phase"] != "complete" or value["evidence"], "CHECKPOINT_RESULT_EVIDENCE_REQUIRED")
    edits = value["document_edits"]
    require(isinstance(edits, list) and len(edits) <= 16, "CHECKPOINT_DOCUMENT_EDIT_LIMIT")
    for edit in edits:
        adapter.shape(edit, ("path", "before", "after"), label="checkpoint.edit")
        adapter.relative(edit["path"])
        _pin_shape(edit["before"], path=False, limit=MAX_DOCUMENT)
        _pin_shape(edit["after"], limit=MAX_DOCUMENT)
    if "activity" in value:
        activity = value["activity"]
        adapter.shape(activity, ("observed_at", "valid_until", "source", "ref", "receipt"), label="checkpoint.activity")
        require(value["phase"] in ("start", "progress") and value["status"] == "doing", "CHECKPOINT_ACTIVITY_NOT_DISPATCH")
        observed, until = nav.stamp(activity["observed_at"]), nav.stamp(activity["valid_until"])
        require(observed <= nav.stamp(value["at"]) and 0 < (until - observed).total_seconds() <= 3600,
                "CHECKPOINT_ACTIVITY_WINDOW")
        require(isinstance(activity["source"], str) and activity["source"] in ACTIVITY_SOURCES, "CHECKPOINT_ACTIVITY_SOURCE")
        _text(activity["ref"], 2048)
        require(not any(ord(c) < 32 for c in activity["ref"]), "CHECKPOINT_ACTIVITY_REF")
        _pin_shape(activity["receipt"])
    return value


def _span(text, pointer):
    """Find the selected JSON value without re-encoding its enclosing object."""
    decoder = json.JSONDecoder()
    tokens = [] if not pointer else [t.replace("~1", "/").replace("~0", "~") for t in pointer.split("/")[1:]]
    require(len(tokens) <= 64, "CHECKPOINT_POINTER_DEPTH")

    def whitespace(index):
        while index < len(text) and text[index] in " \t\r\n":
            index += 1
        return index

    def walk(index, remaining):
        index = whitespace(index)
        if not remaining:
            return index, decoder.raw_decode(text, index)[1]
        token, tail = remaining[0], remaining[1:]
        kind = text[index]
        require(kind in "{[", "CHECKPOINT_POINTER_CONTAINER")
        index = whitespace(index + 1)
        position = 0
        while text[index] not in "}]":
            if kind == "{":
                key, index = decoder.raw_decode(text, index)
                index = whitespace(index)
                require(text[index] == ":", "CHECKPOINT_JSON_SEPARATOR")
                index = whitespace(index + 1)
                match = key == token
            else:
                match = str(position) == token
            if match:
                return walk(index, tail)
            index = whitespace(decoder.raw_decode(text, index)[1])
            position += 1
            if text[index] == ",":
                index = whitespace(index + 1)
            else:
                break
        raise nav.Invalid("CHECKPOINT_POINTER_MISSING")
    return walk(0, tokens)


def _transition(before, profile, record, record_sha256, documents):
    """Derive the one permitted postimage; also used to distrust retained plans."""
    matrix = adapter.pointer_value(nav.parse(before), profile["matrix"]["pointer"])
    earlier = [e for e in matrix["events"] if e["step_id"] == record["work_id"]]
    fact = {k: record[k] for k in ("phase", "work_id", "executor_id", "status", "note", "next_action", "evidence")}
    fact_sha = adapter.sha(nav.canonical(fact))
    unchanged = record["phase"] == "progress" and earlier and earlier[-1].get("checkpoint", {}).get("fact_sha256") == fact_sha
    unchanged = bool(unchanged and "activity" not in record and all(old == new for _, old, new, _ in documents))
    result = copy.deepcopy(matrix)
    eid = "CP-" + adapter.sha(record["operation_id"].encode())[:32]
    if not unchanged:
        require(all(e["id"] != eid for e in matrix["events"]), "CHECKPOINT_EVENT_ID_CONFLICT")
        result["events"].append({"id": eid, "step_id": record["work_id"], "at": record["at"], "status": record["status"],
            "note": record["note"], "next_action": record["next_action"], "executor_ids": [record["executor_id"]],
            "coordinator_id": record["writer"], "history_ids": list(dict.fromkeys([record["executor_id"], record["writer"]])),
            "evidence": copy.deepcopy(record["evidence"]), "accepted": False,
            "checkpoint": {"operation_id": record["operation_id"], "phase": record["phase"], "record_sha256": record_sha256, "fact_sha256": fact_sha}})
        if "activity" in record:
            observation = record["activity"]
            result.setdefault("activity_events", []).append({"id": eid + "-ACTIVITY", "actor_id": record["executor_id"],
                "step_id": record["work_id"], "at": observation["observed_at"], "state": "active", "valid_until": observation["valid_until"],
                "evidence": [{"source": observation["source"], "ref": observation["ref"], "actor_id": record["executor_id"],
                              "step_id": record["work_id"], "receipt": copy.deepcopy(observation["receipt"])}]})
        result["revision"] += 1
        result["updated_at"] = record["at"]
        if "previous_payload_sha256" in matrix:
            prior = before if profile["history"]["previous_payload_hash"] == "source-bytes" else nav.canonical(matrix)
            result["previous_payload_sha256"] = adapter.sha(prior)
    adapter.verify_append(matrix, result)
    text = before.decode("utf-8")
    start, end = _span(text, profile["matrix"]["pointer"])
    raw = before if unchanged else (text[:start] + nav.canonical(result).decode("utf-8").rstrip("\n") + text[end:]).encode("utf-8")
    require(len(raw) <= MAX_SOURCE, "CHECKPOINT_SOURCE_LIMIT")
    require(len(nav.canonical(result) if profile["matrix"]["pointer"] else raw) <= nav.MAX_FILE,
            "CHECKPOINT_SELECTED_MATRIX_CAPACITY")
    require(adapter.pointer_value(nav.parse(raw), profile["matrix"]["pointer"]) == result, "CHECKPOINT_SELECTED_READBACK")
    return result, raw, unchanged


def _prepare(root, raw, profile, profile_raw, binding, binding_raw, now):
    record = _record(raw)
    require(record["project_id"] == profile["project_id"] and record["writer"] == profile["writer"], "CHECKPOINT_RECORD_OWNER_MISMATCH")
    require(nav.stamp(record["at"]) <= nav.stamp(now), "CHECKPOINT_FUTURE_FACT")
    source_path = profile["matrix"]["path"]
    before, source_mode = _state(root, source_path)
    require(_matches(before, record["expected_source"]), "CHECKPOINT_SOURCE_PREIMAGE")
    envelope = nav.parse(before)
    matrix = adapter.pointer_value(envelope, profile["matrix"]["pointer"])
    adapter.validate_matrix(matrix, binding["matrix"]["allowed_schema"], now)
    _uint(matrix.get("revision"), 2**53 - 1)
    require(matrix["revision"] == record["expected_source"]["revision"], "CHECKPOINT_REVISION_PREIMAGE")
    require(nav.stamp(matrix["updated_at"]) <= nav.stamp(record["at"]), "CHECKPOINT_FACT_BEFORE_SOURCE")
    actors = {a["id"] for a in matrix["actors"] if isinstance(a, dict) and isinstance(a.get("id"), str)}
    require(record["writer"] in actors and record["executor_id"] in actors, "CHECKPOINT_UNDECLARED_ACTOR")
    ids = {step["id"] for step in matrix["steps"]}
    require(record["work_id"] in ids and not any(step["parent_id"] == record["work_id"] for step in matrix["steps"]),
            "CHECKPOINT_EXISTING_LEAF_REQUIRED")
    earlier = [event for event in matrix["events"] if event["step_id"] == record["work_id"]]
    require(all(nav.stamp(e["at"]) <= nav.stamp(record["at"]) for e in earlier), "CHECKPOINT_EVENT_TIME_ORDER")
    dests = [e["path"] for e in record["document_edits"]]
    require(len(set(dests)) == len(dests) and all(p in profile["document_paths"] for p in dests), "CHECKPOINT_DOCUMENT_SCOPE")
    require(all(e["after"]["path"] not in {*dests, source_path} for e in record["document_edits"]), "CHECKPOINT_PREPARED_PATH_OVERLAP")
    documents = []
    for edit in record["document_edits"]:
        old, mode = _state(root, edit["path"], MAX_DOCUMENT)
        require(_matches(old, edit["before"]), "CHECKPOINT_DOCUMENT_PREIMAGE:" + edit["path"])
        documents.append((edit["path"], old, _pinned(root, edit["after"], MAX_DOCUMENT), mode))
    if documents and "semantic_catalog" in binding:
        catalogue = nav.parse(_pinned(root, binding["semantic_catalog"]))
        doc_paths = {d["id"]: d["path"] for d in binding["documents"]}
        changed = {path: adapter.sha(new) for path, old, new, _ in documents if old != new}
        for patch in catalogue.get("patch_bindings", []):
            target = doc_paths.get(patch.get("target_doc_id"))
            require(target not in changed or changed[target] == patch.get("base_sha256"),
                    "CHECKPOINT_PATCH_BASE_CHANGE_REQUIRES_CATALOG_RECONCILE")
    proofs = [(p, _pinned(root, p)) for p in record["evidence"]]
    if "activity" in record:
        proofs.append((record["activity"]["receipt"], _pinned(root, record["activity"]["receipt"])))
        # This validates a local record of a native observation, not the remote fact itself.
        claim = nav.parse(proofs[-1][1])
        require(isinstance(claim, dict) and claim.get("actor_id") == record["executor_id"]
                and claim.get("step_id") == record["work_id"] and claim.get("state") == "active"
                and claim.get("at") == record["activity"]["observed_at"]
                and claim.get("valid_until") == record["activity"]["valid_until"]
                and claim.get("scope") == "ACTIVITY" and claim.get("result") == "PASS"
                and claim.get("source") == record["activity"]["source"] and claim.get("ref") == record["activity"]["ref"],
                "CHECKPOINT_ACTIVITY_RECEIPT_BINDING")
    after_matrix, after, unchanged = _transition(before, profile, record, adapter.sha(raw), documents)
    adapter.validate_matrix(after_matrix, binding["matrix"]["allowed_schema"], now)
    files = documents + [(source_path, before, after, source_mode)]
    require(sum(len(a) + len(b) for _, a, b, _ in files) + sum(len(p) for _, p in proofs) + len(raw) <= MAX_TOTAL,
            "CHECKPOINT_TRANSACTION_LIMIT")
    return record, files, proofs, {"schema": "atlas.checkpoint-plan/v1", "operation_id": record["operation_id"], "phase": record["phase"],
        "record_sha256": adapter.sha(raw), "profile_pin": adapter.pin(PROFILE, profile_raw),
        "binding_pin": adapter.pin(profile["binding"], binding_raw), "unchanged": unchanged,
        "source_before": {**adapter.pin(source_path, before), "revision": matrix["revision"]},
        "source_after": {**adapter.pin(source_path, after), "revision": after_matrix["revision"]}, "files": [], "proofs": []}


def _store(root, record_raw, files, proofs, plan):
    base = OPERATIONS + "/" + plan["operation_id"]
    require(not (root / base).exists() and not (root / base).is_symlink(), "CHECKPOINT_OPERATION_ALREADY_STAGED")
    adapter.directory(root, OPERATIONS, create=True)
    (root / base).mkdir(mode=0o700)
    _new(root, base + "/record.json", record_raw)
    for index, (path, before, after, mode) in enumerate(files):
        first, last = base + f"/file-{index:02d}.before", base + f"/file-{index:02d}.after"
        _new(root, first, before)
        _new(root, last, after)
        plan["files"].append({"path": path, "mode": mode, "before": adapter.pin(first, before), "after": adapter.pin(last, after)})
    for index, (origin, raw) in enumerate(proofs):
        path = base + f"/proof-{index:02d}"
        _new(root, path, raw)
        plan["proofs"].append({"origin": origin, "retained": adapter.pin(path, raw)})
    _new(root, base + "/PLAN.json", nav.canonical(plan))
    return plan


def _load(root, operation_id):
    base = OPERATIONS + "/" + _operation(operation_id)
    raw = adapter.read(root, base + "/PLAN.json", MAX_RECORD)
    plan = nav.parse(raw)
    adapter.shape(plan, ("schema", "operation_id", "phase", "record_sha256", "profile_pin", "binding_pin", "unchanged",
                         "source_before", "source_after", "files", "proofs"), label="checkpoint.retained_plan")
    require(plan.get("schema") == "atlas.checkpoint-plan/v1"
            and plan.get("operation_id") == operation_id, "CHECKPOINT_PLAN_SCHEMA")
    record_raw = adapter.read(root, base + "/record.json", MAX_RECORD)
    require(adapter.sha(record_raw) == plan["record_sha256"], "CHECKPOINT_RETAINED_RECORD_HASH")
    record = _record(record_raw)
    require(record["operation_id"] == operation_id and record["phase"] == plan["phase"] and type(plan["unchanged"]) is bool,
            "CHECKPOINT_RETAINED_OPERATION")
    _pin_shape(plan["profile_pin"], limit=256 * 1024)
    _pin_shape(plan["binding_pin"], limit=512 * 1024)
    require(isinstance(plan["files"], list) and 1 <= len(plan["files"]) <= 17
            and isinstance(plan["proofs"], list) and len(plan["proofs"]) <= 33,
            "CHECKPOINT_RETAINED_LIMIT")
    total = len(record_raw)
    for index, row in enumerate(plan["files"]):
        adapter.shape(row, ("path", "mode", "before", "after"), label="checkpoint.retained_file")
        adapter.relative(row["path"])
        _uint(row["mode"], 0o7777)
        for side in ("before", "after"):
            require(row[side]["path"] == base + f"/file-{index:02d}." + side, "CHECKPOINT_RETAINED_PATH")
            total += len(_pinned(root, row[side]))
    for index, proof in enumerate(plan["proofs"]):
        adapter.shape(proof, ("origin", "retained"), label="checkpoint.retained_proof")
        _pin_shape(proof["origin"])
        require(proof["retained"]["path"] == base + f"/proof-{index:02d}", "CHECKPOINT_RETAINED_PROOF_PATH")
        proof_raw = _pinned(root, proof["retained"])
        require(_matches(proof_raw, proof["origin"]), "CHECKPOINT_RETAINED_PROOF_BINDING")
        total += len(proof_raw)
    require(total <= MAX_TOTAL, "CHECKPOINT_RETAINED_LIMIT")
    return plan, raw, record


def _observed(root, plan):
    result = []
    for row in plan["files"]:
        try:
            raw, mode = _state(root, row["path"])
            value = "AFTER" if _matches(raw, row["after"]) and mode == row["mode"] else (
                "BEFORE" if _matches(raw, row["before"]) and mode == row["mode"] else "CONFLICT")
        except (nav.Invalid, OSError):
            value = "CONFLICT"
        result.append({"path": row["path"], "state": value})
    return result


def _pending_result(root, plan, error=None):
    observed = _observed(root, plan)
    changed = [i for i, r in enumerate(plan["files"]) if r["before"]["sha256"] != r["after"]["sha256"]]
    effect = "UNKNOWN" if any(r["state"] == "CONFLICT" for r in observed) else "NONE" if not changed or all(observed[i]["state"] == "BEFORE" for i in changed) else (
        "COMMITTED" if all(observed[i]["state"] == "AFTER" for i in changed) else "PARTIAL")
    return {"status": "CHECKPOINT_PENDING", "operation_id": plan["operation_id"], "phase": plan["phase"],
            "source_effect": effect, "pending": True, "record_sha256": plan["record_sha256"], "receipt": None,
            "projection": None, "replayed": False, "source_before": plan["source_before"], "source_after": plan["source_after"],
            "observed": observed, "error": error, "note": "Exact retained operation only; no external action is performed or replayed."}


def _completed(root, plan):
    path = OPERATIONS + "/" + plan["operation_id"] + "/RESULT.json"
    raw = adapter.optional_read(root, path, MAX_RECORD)
    if raw is None:
        return None
    value = nav.parse(raw)
    require(isinstance(value, dict) and value.get("record_sha256") == plan["record_sha256"] and value.get("operation_id") == plan["operation_id"]
            and value.get("source_before") == plan["source_before"] and value.get("source_after") == plan["source_after"]
            and value.get("phase") == plan["phase"] and value.get("pending") is False
            and value.get("status") in ("CHECKPOINT_PUBLISHED", "NO_CHANGE"), "CHECKPOINT_RESULT_BINDING")
    pending_raw = adapter.optional_read(root, PENDING)
    pending = nav.parse(pending_raw) if pending_raw else None
    require(pending is None or isinstance(pending, dict), "CHECKPOINT_PENDING_SCHEMA")
    own_pending = pending is not None and pending.get("operation_id") == plan["operation_id"]
    return {**value, "receipt": adapter.pin(path, raw), "replayed": True, "pending": own_pending,
            **({"status": "CHECKPOINT_PENDING", "recorded_status": value["status"], "error": "CHECKPOINT_FINALIZATION_PENDING"} if own_pending else {})}


def _valid_restoration_manifest(manifest):
    if manifest.get("schema") == "atlas.protected-project-note-recovery/v2":
        return manifest.get("only_restored_field") == "project.scope_note"
    return (manifest.get("schema") == "atlas.protected-project-text-recovery/v3"
            and manifest.get("allowed_restored_fields") == ["project.objective", "project.scope_note"]
            and isinstance(manifest.get("restored_fields"), list)
            and bool(manifest["restored_fields"])
            and manifest["restored_fields"] == [f for f in manifest["allowed_restored_fields"]
                                               if f in manifest["restored_fields"]])


def _guard(root, plan, profile_raw, binding_raw, *, recovery=None):
    require(_matches(profile_raw, plan["profile_pin"]), "CHECKPOINT_AUTHORITY_CHANGED")
    if recovery is None:
        require(_matches(binding_raw, plan["binding_pin"]), "CHECKPOINT_AUTHORITY_CHANGED")
    else:
        # Historical plan remains pinned. The new exact prior-authority proof
        # qualifies the corrected v2 note or fixed v3 two-text set as an additional binding state.
        require(_matches(recovery["before"], plan["binding_pin"])
                and binding_raw == recovery["after"]
                and recovery["manifest"]["operation_id"] == plan["operation_id"]
                and _valid_restoration_manifest(recovery["manifest"]),
                "CHECKPOINT_PROTECTED_NOTE_RECOVERY_MISMATCH")
    profile = nav.parse(profile_raw)
    record = _record(adapter.read(root, OPERATIONS + "/" + plan["operation_id"] + "/record.json", MAX_RECORD))
    require(plan["profile_pin"]["path"] == PROFILE and plan["binding_pin"]["path"] == profile["binding"], "CHECKPOINT_RETAINED_AUTHORITY_PATH")
    paths = [e["path"] for e in record["document_edits"]] + [profile["matrix"]["path"]]
    require([r["path"] for r in plan["files"]] == paths and all(p in profile["document_paths"] for p in paths[:-1]),
            "CHECKPOINT_RETAINED_DESTINATION_SCOPE")
    for edit, row in zip(record["document_edits"], plan["files"]):
        require(all(row["before"][key] == edit["before"][key] and row["after"][key] == edit["after"][key]
                    for key in ("sha256", "bytes")), "CHECKPOINT_RETAINED_DOCUMENT_BINDING")
    source = plan["files"][-1]
    require(all(source["before"][key] == record["expected_source"][key] for key in ("sha256", "bytes")),
            "CHECKPOINT_RETAINED_SOURCE_BINDING")
    documents = [(r["path"], _pinned(root, r["before"]), _pinned(root, r["after"]), r["mode"]) for r in plan["files"][:-1]]
    source_before, source_after = _pinned(root, source["before"]), _pinned(root, source["after"])
    _, expected_after, unchanged = _transition(source_before, profile, record, plan["record_sha256"], documents)
    require(source_after == expected_after and plan["unchanged"] is unchanged, "CHECKPOINT_RETAINED_TRANSITION_MISMATCH")
    require(plan["source_before"] == {**adapter.pin(profile["matrix"]["path"], source_before), "revision": record["expected_source"]["revision"]}
            and plan["source_after"] == {**adapter.pin(profile["matrix"]["path"], source_after),
                                        "revision": record["expected_source"]["revision"] + (0 if unchanged else 1)},
            "CHECKPOINT_RETAINED_SOURCE_SUMMARY")
    require(all(r["state"] != "CONFLICT" for r in _observed(root, plan)), "CHECKPOINT_SOURCE_CONFLICT")


def _own_import_lock(root, token):
    current = adapter.optional_read(root, adapter.LOCK)
    if current is None:
        _new(root, adapter.LOCK, token)
    else:
        require(current == token, "CHECKPOINT_FOREIGN_IMPORT_LOCK")


def _unlink_ours(root, path, raw):
    require(adapter.optional_read(root, path) == raw, "CHECKPOINT_OWNED_TOKEN_CHANGED:" + path)
    (root / path).unlink()
    nav.sync_directory(root / ".atlas")


def _prior_published_binding(root, current_binding):
    """Capture before any effect: old state, archived authority and exact prior release."""
    state_raw = adapter.read(root, adapter.STATE, 2 * 1024 * 1024)
    state = nav.parse(state_raw)
    require(state.get("schema") == "atlas.import-state/v1", "NOTE_RESTORE_STATE_SCHEMA")
    meta_raw = adapter.read(root, state["generation"] + "/IMPORT.json", 2 * 1024 * 1024)
    require(adapter.sha(meta_raw) == state["generation_meta_sha256"], "NOTE_RESTORE_RETAINED_IMPORT_HASH")
    metadata = nav.parse(meta_raw)
    pin = metadata["binding_file"]
    require(pin["path"].startswith(".atlas/imports/"), "NOTE_RESTORE_RETAINED_AUTHORITY_SOURCE")
    old_raw = _pinned(root, pin, 512 * 1024)
    require(adapter.sha(old_raw) == state["binding_sha256"], "NOTE_RESTORE_RETAINED_AUTHORITY_HASH")
    pointer, _ = adapter.atlas.current_output(root / current_binding["output"])
    require(pointer is not None and pointer["manifest_sha256"] == state["output_manifest_sha256"],
            "NOTE_RESTORE_PRIOR_OUTPUT_MISMATCH")
    project_raw = adapter.read(root, adapter.PROJECT, 8 * 1024 * 1024)
    require(adapter.sha(project_raw) == state["project_sha256"], "NOTE_RESTORE_PRIOR_PROJECT_MISMATCH")
    return old_raw, state_raw, pointer["release"]


def _recorded_note_prior(root, frozen_state_raw, frozen_authority_raw, prior_release, prior_manifest_sha):
    """Validate original authority against archived generation + immutable prior release.

    This never recomputes the predecessor from the *current* import state,
    which changes upon publication. Cached bytes are pinned by the staged manifest.
    """
    state = nav.parse(frozen_state_raw)
    require(state.get("schema") == "atlas.import-state/v1", "NOTE_RESTORE_PRIOR_STATE_SCHEMA")
    meta_raw = adapter.read(root, state["generation"] + "/IMPORT.json", 2 * 1024 * 1024)
    require(adapter.sha(meta_raw) == state["generation_meta_sha256"], "NOTE_RESTORE_PRIOR_IMPORT_CHANGED")
    metadata = nav.parse(meta_raw)
    pin = metadata["binding_file"]
    require(pin["path"].startswith(".atlas/imports/")
            and _pinned(root, pin, 512 * 1024) == frozen_authority_raw
            and adapter.sha(frozen_authority_raw) == state["binding_sha256"],
            "NOTE_RESTORE_FROZEN_AUTHORITY_MISMATCH")
    old_project = adapter.read(root, state["generation"] + "/project.json", 8 * 1024 * 1024)
    require(adapter.sha(old_project) == state["project_sha256"]
            and metadata["project_sha256"] == state["project_sha256"], "NOTE_RESTORE_PRIOR_PROJECT_CHANGED")
    archive_sha, _ = nav.verify_release(root / adapter.binding_model(frozen_authority_raw)["output"],
                                       prior_release, prior_manifest_sha)
    require(archive_sha == state["output_manifest_sha256"], "NOTE_RESTORE_PRIOR_RELEASE_CHANGED")
    return state


def _note_published_state(root, prior_state_raw, prior_release, after, plan):
    """Recognize one already-published immediate successor, never invoke refresh again."""
    state_raw = adapter.read(root, adapter.STATE, 2 * 1024 * 1024)
    if state_raw == prior_state_raw:
        state = nav.parse(state_raw)
        binding = adapter.binding_model(after)
        pointer, _ = adapter.atlas.current_output(root / binding["output"])
        require(pointer and pointer["manifest_sha256"] == state["output_manifest_sha256"],
                "NOTE_RESTORE_PRE_PUBLICATION_OUTPUT_CHANGED")
        require(adapter.sha(adapter.read(root, adapter.PROJECT, 8 * 1024 * 1024)) ==
                state["project_sha256"], "NOTE_RESTORE_PRE_PUBLICATION_PROJECT_CHANGED")
        return None
    old = nav.parse(prior_state_raw)
    current = nav.parse(state_raw)
    require(current.get("schema") == "atlas.import-state/v1"
            and current["generation"] != old["generation"]
            and current["binding_sha256"] == adapter.sha(after),
            "NOTE_RESTORE_UNEXPECTED_PUBLISHED_STATE")
    meta_raw = adapter.read(root, current["generation"] + "/IMPORT.json", 2 * 1024 * 1024)
    require(adapter.sha(meta_raw) == current["generation_meta_sha256"],
            "NOTE_RESTORE_PUBLISHED_META_CHANGED")
    meta = nav.parse(meta_raw)
    require(meta["project_sha256"] == current["project_sha256"]
            and meta["before_project_sha256"] == old["project_sha256"]
            and _pinned(root, meta["binding_file"], 512 * 1024) == after
            and meta["matrix_origin"]["path"] == plan["source_after"]["path"]
            and meta["matrix_origin"]["enclosing_sha256"] == plan["source_after"]["sha256"],
            "NOTE_RESTORE_PUBLISHED_LINEAGE_CHANGED")
    source_raw = adapter.read(root, plan["source_after"]["path"], MAX_SOURCE)
    require(_matches(source_raw, plan["source_after"]), "NOTE_RESTORE_PUBLISHED_SOURCE_CHANGED")
    retained_matrix = _pinned(root, meta["matrix"], MAX_SOURCE)
    source_definition = adapter.pointer_value(nav.parse(source_raw),
                                              adapter.binding_model(after)["matrix"].get("pointer", ""))
    require(nav.parse(retained_matrix) == source_definition, "NOTE_RESTORE_PUBLISHED_MATRIX_CHANGED")
    project_raw = adapter.read(root, adapter.PROJECT, 8 * 1024 * 1024)
    require(adapter.sha(project_raw) == current["project_sha256"],
            "NOTE_RESTORE_PUBLISHED_PROJECT_CHANGED")
    binding = adapter.binding_model(after)
    pointer, snapshot = adapter.atlas.current_output(root / binding["output"])
    require(pointer and pointer["manifest_sha256"] == current["output_manifest_sha256"],
            "NOTE_RESTORE_PUBLISHED_OUTPUT_CHANGED")
    archive = snapshot["atlas"].get("projection_archive") or {}
    require(archive.get("previous_release") == prior_release
            and archive.get("previous_manifest_sha256") == old["output_manifest_sha256"],
            "NOTE_RESTORE_PUBLISHED_PREDECESSOR_CHANGED")
    return {"state":current, "pointer":pointer}


def _stage_exact_note(root, path, data):
    """Resume a partially written set only when every existing member matches."""
    existing = adapter.optional_read(root, path, MAX_RECORD if path.endswith(".json") else MAX_SOURCE)
    if existing is None:
        _new(root, path, data)
    else:
        require(existing == data, "NOTE_RESTORE_STAGED_FRAGMENT_CONFLICT:" + path)


def _protected_note_candidate(previous_raw, candidate_raw, *, text_mode=False):
    """Default v2 note, or explicit v3 fixed two texts, from the immutable prior authority."""
    prior = adapter.binding_model(previous_raw)
    present = adapter.binding_model(candidate_raw)
    fields = ("objective", "scope_note") if text_mode else ("scope_note",)
    require(any(prior["project"][f] != present["project"][f] for f in fields),
            "TEXT_RESTORE_NO_DIFFERENCE" if text_mode else "NOTE_RESTORE_ONLY_FOR_CHANGED_SCOPE_NOTE")
    restored = copy.deepcopy(present)
    for field in fields:
        restored["project"][field] = prior["project"][field]
    require(restored["project"] == prior["project"], "NOTE_RESTORE_OTHER_PROJECT_AUTHORITY_CHANGED")
    require(restored["output"] == prior["output"], "NOTE_RESTORE_OUTPUT_CHANGED")
    adapter.verify_binding_append(prior, restored)
    result = nav.canonical(restored)
    require(result != candidate_raw, "NOTE_RESTORE_NO_DIFFERENCE")
    return result


def _note_restore_evidence(root, plan, plan_raw, binding_path, *, stage=False, text_mode=False):
    """Verify or resume one exact, durable authority-only correction.

    The old published authority and IMPORT_STATE are captured *before* any
    effect and then independently checked against immutable archived generation
    and release. Current IMPORT_STATE may advance only to the immediate proven
    successor; its changed bytes never redefine the old authority.
    """
    profile, profile_raw, current, current_raw = _profile(root, binding_path)
    require(plan["binding_pin"]["path"] == binding_path and profile["binding"] == binding_path,
            "NOTE_RESTORE_BINDING_PATH")
    pending = nav.canonical({"schema":"atlas.checkpoint-pending/v1",
                             "operation_id":plan["operation_id"],"plan_sha256":adapter.sha(plan_raw)})
    require(adapter.optional_read(root, PENDING) == pending, "NOTE_RESTORE_EXACT_PENDING")
    require(adapter.optional_read(root, adapter.PENDING) is None
            and adapter.optional_read(root, adapter.DOC_PENDING) is None,
            "NOTE_RESTORE_OTHER_IMPORT_PENDING")
    require(all(item["state"] == "AFTER" for item in _observed(root, plan)),
            "NOTE_RESTORE_SOURCE_MUST_ALREADY_BE_COMMITTED")
    require(profile["project_id"] == current["project"]["id"]
            and profile["writer"] == current["project"]["writer"]
            and _matches(profile_raw, plan["profile_pin"]),
            "NOTE_RESTORE_WRITER_OR_PROFILE_CHANGED")
    base = OPERATIONS + "/" + plan["operation_id"]
    other_prefix = "/PROJECT_NOTE" if text_mode else "/PROJECT_TEXTS"
    require(all(adapter.optional_read(root, base + other_prefix + suffix, MAX_SOURCE) is None
                for suffix in (".before", ".after", ".prior-authority", ".prior-state", "_RECOVERY.json")),
            "TEXT_RESTORE_OTHER_MODE_PREPARATION_EXISTS")
    before_path = base + ("/PROJECT_TEXTS" if text_mode else "/PROJECT_NOTE") + ".before"
    after_path = base + ("/PROJECT_TEXTS" if text_mode else "/PROJECT_NOTE") + ".after"
    prior_authority_path = base + ("/PROJECT_TEXTS" if text_mode else "/PROJECT_NOTE") + ".prior-authority"
    prior_state_path = base + ("/PROJECT_TEXTS" if text_mode else "/PROJECT_NOTE") + ".prior-state"
    manifest_path = base + ("/PROJECT_TEXTS" if text_mode else "/PROJECT_NOTE") + "_RECOVERY.json"
    manifest_raw = adapter.optional_read(root, manifest_path, MAX_RECORD)
    if manifest_raw is None:
        # All interruption windows before the manifest precede the actual
        # binding rewrite. Existing partial staged bytes must match exactly.
        require(_matches(current_raw, plan["binding_pin"]), "NOTE_RESTORE_ORIGINAL_BINDING_MISMATCH")
        prior_authority_raw, prior_state_raw, prior_release = _prior_published_binding(root, current)
        before = current_raw
        after = _protected_note_candidate(prior_authority_raw, before, text_mode=text_mode)
    else:
        prior_manifest = nav.parse(manifest_raw)
        adapter.shape(prior_manifest,
                      ("schema", "operation_id", "plan_sha256", "previous_authority_sha256",
                       "previous_import_state", "previous_authority", "previous_release",
                       "previous_output_manifest_sha256", "previous_project_sha256",
                       "previous_import_meta_sha256", "before", "after", "profile_sha256",
                       "source_after_sha256", "project_id", "writer", "output") +
                      (("allowed_restored_fields", "restored_fields") if text_mode else ("only_restored_field",)),
                      label="checkpoint.note_recovery")
        require(prior_manifest["schema"] == ("atlas.protected-project-text-recovery/v3" if text_mode else "atlas.protected-project-note-recovery/v2")
                and prior_manifest["operation_id"] == plan["operation_id"],
                "NOTE_RESTORE_MANIFEST_SCHEMA")
        prior_state_raw = _pinned(root, prior_manifest["previous_import_state"], MAX_RECORD)
        prior_authority_raw = _pinned(root, prior_manifest["previous_authority"], 512 * 1024)
        before = _pinned(root, prior_manifest["before"], 512 * 1024)
        after = _pinned(root, prior_manifest["after"], 512 * 1024)
        prior_release = prior_manifest["previous_release"]
    old_state = _recorded_note_prior(root, prior_state_raw, prior_authority_raw, prior_release,
                                     nav.parse(prior_state_raw)["output_manifest_sha256"])
    require(_matches(before, plan["binding_pin"]), "NOTE_RESTORE_RETAINED_ORIGINAL_MISMATCH")
    require(after == _protected_note_candidate(prior_authority_raw, before, text_mode=text_mode),
            "NOTE_RESTORE_RETAINED_CORRECTION_MISMATCH")
    prior = adapter.binding_model(prior_authority_raw)
    require(prior["project"]["id"] == profile["project_id"]
            and prior["project"]["writer"] == profile["writer"]
            and prior["output"] == current["output"],
            "NOTE_RESTORE_PREVIOUS_AUTHORITY_DIFFERENT")
    manifest = {
        "schema":"atlas.protected-project-text-recovery/v3" if text_mode else "atlas.protected-project-note-recovery/v2",
        "operation_id":plan["operation_id"],
        "plan_sha256":adapter.sha(plan_raw),
        "previous_authority_sha256":adapter.sha(prior_authority_raw),
        "previous_import_state":adapter.pin(prior_state_path,prior_state_raw),
        "previous_authority":adapter.pin(prior_authority_path,prior_authority_raw),
        "previous_release":prior_release,
        "previous_output_manifest_sha256":old_state["output_manifest_sha256"],
        "previous_project_sha256":old_state["project_sha256"],
        "previous_import_meta_sha256":old_state["generation_meta_sha256"],
        "before":adapter.pin(before_path,before),
        "after":adapter.pin(after_path,after),
        "profile_sha256":plan["profile_pin"]["sha256"],
        "source_after_sha256":plan["source_after"]["sha256"],
        "project_id":prior["project"]["id"],
        "writer":prior["project"]["writer"],
        "output":prior["output"],
        **({"allowed_restored_fields":["project.objective", "project.scope_note"],
            "restored_fields":["project." + f for f in ("objective", "scope_note")
                               if prior["project"][f] != adapter.binding_model(before)["project"][f]]}
           if text_mode else {"only_restored_field":"project.scope_note"}),
    }
    require(current_raw in (before,after),"NOTE_RESTORE_CURRENT_BINDING_CONFLICT")
    published = _note_published_state(root,prior_state_raw,prior_release,after,plan)
    require(published is None or current_raw == after,
            "NOTE_RESTORE_PUBLISHED_BINDING_ROLLBACK")
    if manifest_raw is not None:
        require(manifest_raw == nav.canonical(manifest), "NOTE_RESTORE_MANIFEST_CONFLICT")
    else:
        # Zero, one, or several pre-manifest fragments can survive a crash.
        # Verify each existing member before writing ANY missing member.
        files = ((prior_state_path,prior_state_raw),(prior_authority_path,prior_authority_raw),
                 (before_path,before),(after_path,after))
        for rel, data in files:
            existing = adapter.optional_read(root,rel,512 * 1024)
            require(existing is None or existing == data, "NOTE_RESTORE_STAGED_FRAGMENT_CONFLICT:" + rel)
        if stage:
            require(published is None and current_raw == before,
                    "NOTE_RESTORE_STAGING_MUST_PRECEDE_EFFECT")
            for rel,data in files:
                _stage_exact_note(root,rel,data)
            _stage_exact_note(root,manifest_path,nav.canonical(manifest))
    return {"before":before,"after":after,"manifest":manifest,"pending":pending,
            "published":published,"state":"PUBLISHED" if published else
            ("RESTORED" if current_raw == after else "ORIGINAL")}


def _apply_note_restore(root, plan, plan_raw, binding_path, *, text_mode=False):
    """One guarded local authority-metadata restoration, no matrix replay."""
    qualified = _note_restore_evidence(root, plan, plan_raw, binding_path, stage=False, text_mode=text_mode)
    profile, profile_raw, _, binding_raw = _profile(root, binding_path)
    _guard(root, plan, profile_raw, qualified["before"])
    qualified = _note_restore_evidence(root, plan, plan_raw, binding_path, stage=True, text_mode=text_mode)
    if qualified["state"] == "ORIGINAL":
        current, mode = _state(root, binding_path, 512 * 1024)
        require(current == qualified["before"], "NOTE_RESTORE_CAS_ORIGINAL_CHANGED")
        _replace(root, binding_path, qualified["after"], qualified["before"], mode)
    require(adapter.read(root, binding_path, 512 * 1024) == qualified["after"],
            "NOTE_RESTORE_AFTER_READBACK")
    return qualified


def _finish(root, plan, plan_raw, binding_path, now, *, recovery=None):
    token = nav.canonical({"schema": "atlas.checkpoint-source-lock/v1", "operation_id": plan["operation_id"], "plan_sha256": adapter.sha(plan_raw)})
    pending = nav.canonical({"schema": "atlas.checkpoint-pending/v1", "operation_id": plan["operation_id"], "plan_sha256": adapter.sha(plan_raw)})
    try:
        profile, profile_raw, binding, binding_raw = _profile(root, binding_path)
        _guard(root, plan, profile_raw, binding_raw, recovery=recovery)
        prior_pending = adapter.optional_read(root, PENDING)
        require(prior_pending in (None, pending), "CHECKPOINT_OTHER_OPERATION_PENDING")
        require(adapter.optional_read(root, adapter.PENDING) is None, "IMPORT_PENDING_RECONCILE_REQUIRED")
        require(adapter.optional_read(root, adapter.DOC_PENDING) is None, "DOCUMENT_SYNC_PENDING_RECONCILE_REQUIRED")
        _own_import_lock(root, token)
        if prior_pending is None:
            _new(root, PENDING, pending)
        for row in plan["files"]:
            before, after = _pinned(root, row["before"]), _pinned(root, row["after"])
            current, mode = _state(root, row["path"])
            require(mode == row["mode"] and current in (before, after), "CHECKPOINT_SOURCE_CAS:" + row["path"])
            if current != after:
                _replace(root, row["path"], after, before, mode)
        require(all(x["state"] == "AFTER" for x in _observed(root, plan)), "CHECKPOINT_SOURCE_READBACK")
        require(adapter.read(root, PROFILE, 256 * 1024) == profile_raw
                and adapter.read(root, binding_path, 512 * 1024) == binding_raw, "CHECKPOINT_AUTHORITY_CHANGED")
        # No source transaction remains partially installed at this point. The
        # ordinary importer acquires its own lock, while the source flock stays held.
        _unlink_ours(root, adapter.LOCK, token)
        if recovery is not None and recovery["published"] is not None:
            # An earlier attempt already changed the CURRENT immutable release.
            # Do not repeat a publication. Verify the retained immediate
            # successor and finalize only the original missing RESULT/pending.
            frozen = _pinned(root, recovery["manifest"]["previous_import_state"], MAX_RECORD)
            saved = _note_published_state(root, frozen, recovery["manifest"]["previous_release"],
                                          recovery["after"], plan)
            require(saved is not None, "NOTE_RESTORE_EXPECTED_PUBLISHED_SUCCESSOR")
            state, existing_pointer = saved["state"], saved["pointer"]
            projected = {"status":"EXISTING_PUBLISHED_RELEASE_VERIFIED",
                         "fingerprint":state["fingerprint"],"generation":state["generation"],
                         "cycle":{"status":"EXISTING_PUBLISHED",
                                  "release":existing_pointer["release"],
                                  "manifest_sha256":existing_pointer["manifest_sha256"],
                                  "view_path":str(root / binding["output"] / "index.html"),
                                  "changed_paths":[],
                                  "note":"Existing immutable release only; no second refresh, source effect or publication."}}
        else:
            projected = adapter.refresh(root, binding_path=binding_path, at=now)
        require(all(x["state"] == "AFTER" for x in _observed(root, plan)), "CHECKPOINT_SOURCE_CHANGED_AFTER_PROJECTION")
        pointer, snapshot = adapter.atlas.current_output(root / binding["output"])
        require(pointer is not None and pointer["manifest_sha256"] == projected["cycle"]["manifest_sha256"], "CHECKPOINT_CURRENT_READBACK")
        state = nav.parse(adapter.read(root, adapter.STATE, 2 * 1024 * 1024))
        metadata = nav.parse(adapter.read(root, state["generation"] + "/IMPORT.json"))
        retained = _pinned(root, metadata["matrix"])
        actual_matrix = adapter.pointer_value(nav.parse(adapter.read(root, profile["matrix"]["path"])), profile["matrix"]["pointer"])
        require(nav.parse(retained) == actual_matrix, "CHECKPOINT_PROJECTED_SOURCE_MISMATCH")
        record = _record(adapter.read(root, OPERATIONS + "/" + plan["operation_id"] + "/record.json", MAX_RECORD))
        result = {"status": "NO_CHANGE" if plan["unchanged"] else "CHECKPOINT_PUBLISHED", "operation_id": plan["operation_id"],
                  "phase": plan["phase"], "source_effect": "NONE" if plan["unchanged"] else "COMMITTED", "pending": False,
                  "work_id": record["work_id"], "executor_id": record["executor_id"], "next_action": record["next_action"],
                  "event_id": None if plan["unchanged"] else "CP-" + adapter.sha(record["operation_id"].encode())[:32],
                  "record_sha256": plan["record_sha256"], "projection": projected, "replayed": False,
                  "source_before": plan["source_before"], "source_after": plan["source_after"],
                  "activity": "RECORDED_OBSERVATION" if "activity" in record else "NOT_RECORDED",
                  "document_changes": sum(r["before"]["sha256"] != r["after"]["sha256"] for r in plan["files"][:-1]),
                  "note": "Source claim published; no product acceptance or independently verified native activity is inferred."}
        result_path = OPERATIONS + "/" + plan["operation_id"] + "/RESULT.json"
        result_raw = nav.canonical(result)
        require(len(result_raw) <= MAX_RECORD, "CHECKPOINT_RECEIPT_LIMIT")
        _new(root, result_path, result_raw)
        _unlink_ours(root, PENDING, pending)
        return {**result, "receipt": adapter.pin(result_path, result_raw)}
    except (nav.Invalid, OSError, ValueError, KeyError, TypeError) as exc:
        return _pending_result(root, plan, str(exc))


def checkpoint(root, record_path, *, binding_path=".atlas/UPSTREAM.json", at=None):
    """Commit one declared source fact and project it; never dispatch an executor."""
    root = _root(root)
    now = at or datetime.now(timezone.utc).isoformat()
    nav.stamp(now)
    raw = adapter.read(root, record_path, MAX_RECORD)
    record = _record(raw)
    profile, profile_raw, binding, binding_raw = _profile(root, binding_path)
    require(record["project_id"] == profile["project_id"] and record["writer"] == profile["writer"], "CHECKPOINT_RECORD_OWNER_MISMATCH")
    operation_id = record["operation_id"]
    with _lock(root):
        base = OPERATIONS + "/" + operation_id
        if (root / base).exists() or (root / base).is_symlink():
            plan, plan_raw, _ = _load(root, operation_id)
            require(plan["record_sha256"] == adapter.sha(raw), "CHECKPOINT_OPERATION_PAYLOAD_CONFLICT")
            done = _completed(root, plan)
            if done is not None:
                return done
            return _pending_result(root, plan, "CHECKPOINT_RECONCILE_REQUIRED")
        require(adapter.optional_read(root, PENDING) is None, "CHECKPOINT_OTHER_OPERATION_PENDING")
        require(adapter.optional_read(root, adapter.PENDING) is None, "IMPORT_PENDING_RECONCILE_REQUIRED")
        require(adapter.optional_read(root, adapter.DOC_PENDING) is None, "DOCUMENT_SYNC_PENDING_RECONCILE_REQUIRED")
        require(adapter.optional_read(root, adapter.LOCK) is None, "CHECKPOINT_FOREIGN_IMPORT_LOCK")
        profile, profile_raw, binding, binding_raw = _profile(root, binding_path)
        record, files, proofs, plan = _prepare(root, raw, profile, profile_raw, binding, binding_raw, now)
        _store(root, raw, files, proofs, plan)
        return _finish(root, plan, nav.canonical(plan), binding_path, now)


def reconcile(root, operation_id, *, binding_path=".atlas/UPSTREAM.json",
              finish_pending=False, inspect_note_restore=False, restore_note=False,
              inspect_text_restore=False, restore_texts=False, at=None):
    """Read one exact retained operation; optional guarded restore of only old protected scope_note.

    Inspect is read-only. Restore requires explicit finish_pending and the same operation ID.
    No new source event/phase is generated. Non-owner/root platform authority is not expanded.
    """
    require(sum(bool(x) for x in (inspect_note_restore, restore_note, inspect_text_restore, restore_texts)) <= 1,
            "NOTE_RESTORE_MODE_CONFLICT")
    text_mode = bool(inspect_text_restore or restore_texts)
    inspect_restore = bool(inspect_note_restore or inspect_text_restore)
    restore = bool(restore_note or restore_texts)
    require(not restore or finish_pending, "NOTE_RESTORE_FINISH_REQUIRED")
    require(not inspect_restore or not finish_pending, "NOTE_RESTORE_INSPECT_READ_ONLY")
    root = _root(root)
    now = at or datetime.now(timezone.utc).isoformat()
    nav.stamp(now)
    _profile(root, binding_path)
    plan, plan_raw, record = _load(root, operation_id)
    done = _completed(root, plan)
    # Preserve the historical read-only contract: a retained RESULT with its
    # own pending marker is honestly CHECKPOINT_FINALIZATION_PENDING.
    # Only explicit restore inspection/finish may proceed into guarded recovery.
    if done is not None and (not done["pending"] or (not finish_pending and not inspect_restore)):
        return done
    if inspect_restore:
        require(done is None, "NOTE_RESTORE_ALREADY_RECORDED")
        qualified = _note_restore_evidence(root, plan, plan_raw, binding_path, stage=False, text_mode=text_mode)
        return {"schema":"atlas.protected-project-text-recovery-review/v3" if text_mode else "atlas.protected-project-note-recovery-review/v1",
                "status":"READY_FOR_OWNER_GUARDED_TEXT_RESTORE" if text_mode else "READY_FOR_OWNER_GUARDED_NOTE_RESTORE",
                "operation_id":operation_id, "source_effect":"COMMITTED",
                "project_id":qualified["manifest"]["project_id"],
                "writer":qualified["manifest"]["writer"],
                "output":qualified["manifest"]["output"],
                "before":qualified["manifest"]["before"],
                "after":qualified["manifest"]["after"],
                "prior_authority_sha256":qualified["manifest"]["previous_authority_sha256"],
                "retained_plan_sha256":qualified["manifest"]["plan_sha256"],
                "current_state":qualified["state"],
                "writes":"NONE", "grants_authority":False,
                "next_owner":"original matrix writer"}
    if not finish_pending:
        return _pending_result(root, plan)
    with _lock(root):
        plan, plan_raw, record = _load(root, operation_id)
        done = _completed(root, plan)
        if done is not None:
            if done["pending"]:
                profile, profile_raw, binding, binding_raw = _profile(root, binding_path)
                qualified = _note_restore_evidence(root, plan, plan_raw, binding_path, text_mode=text_mode) if restore else None
                _guard(root, plan, profile_raw, binding_raw, recovery=qualified)
                require(all(r["state"] == "AFTER" for r in _observed(root, plan)),
                        "CHECKPOINT_FINALIZATION_SOURCE_CHANGED")
                pending = nav.canonical({"schema": "atlas.checkpoint-pending/v1",
                                         "operation_id": operation_id, "plan_sha256": adapter.sha(plan_raw)})
                _unlink_ours(root, PENDING, pending)
                return _completed(root, plan)
            return done
        qualified = _apply_note_restore(root, plan, plan_raw, binding_path, text_mode=text_mode) if restore else None
        return _finish(root, plan, plan_raw, binding_path, now, recovery=qualified)
