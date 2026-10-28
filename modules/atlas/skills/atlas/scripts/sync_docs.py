#!/usr/bin/env python3
"""Refresh a declared documentation snapshot and its catalogue, then project once.

The source folder is explicit. This module has no network, shell or API execution.
It owns only the configured documentation COPY, its inventory/catalogue and binding.
Owning product files and matrices are never destinations.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile

import catalog
import import_matrix as adapter
import navigator as nav

CONFIG_PATH = ".atlas/DOCUMENT_SYNC.json"
PENDING = ".atlas/DOC_SYNC_PENDING.json"
MAX_SOURCE = 64 * 1024 * 1024
ALLOWED = {".md", ".json", ".yaml", ".yml", ".txt"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def retain_encoding(value, before):
    # A changed indentation or key order alone must not publish a new project state.
    return before if nav.parse(before) == value else nav.canonical(value)


def plain_root(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        adapter.require(not item.is_symlink(), "DOCUMENT_SYNC_SYMLINK:" + str(item))
    adapter.require(path.is_dir(), "DOCUMENT_SYNC_DIRECTORY_REQUIRED:" + str(path))
    return path


def config_model(root):
    config = nav.parse(adapter.read(root, CONFIG_PATH, 64 * 1024))
    adapter.shape(config, ("schema", "destination", "inventory", "catalog_spec", "semantic_catalog"), ("record_index",))
    adapter.require(config["schema"] == "atlas.document-sync/v1", "DOCUMENT_SYNC_CONFIG_SCHEMA")
    for key in ("destination", "inventory", "semantic_catalog", "catalog_spec"):
        adapter.relative(config[key])
    for key in ("destination", "inventory", "semantic_catalog"):
        adapter.require(config[key].startswith("work/atlas-sources/"), "DOCUMENT_SYNC_DESTINATION_SCOPE")
    adapter.require(config["catalog_spec"].startswith(".atlas/"), "DOCUMENT_SYNC_CATALOG_SPEC_SCOPE")
    if "record_index" in config:
        adapter.relative(config["record_index"])
    adapter.require(len({config["destination"], config["inventory"], config["semantic_catalog"]}) == 3,
                    "DOCUMENT_SYNC_PATHS_OVERLAP")
    return config


def members(root):
    result = []
    for path in sorted(root.rglob("*")):
        adapter.require(not path.is_symlink(), "DOCUMENT_SOURCE_SYMLINK")
        if path.is_dir():
            continue
        adapter.require(path.is_file(), "DOCUMENT_SOURCE_REGULAR_FILE_REQUIRED")
        rel = path.relative_to(root).as_posix()
        adapter.relative(rel)
        adapter.require(not any(p.startswith(".") for p in PurePosixPath(rel).parts)
                        and path.suffix.lower() in ALLOWED, "UNDECLARED_DOCUMENT_FILE_TYPE:" + rel)
        result.append(rel)
    adapter.require(len(result) <= 2000, "DOCUMENT_SOURCE_FILE_LIMIT")
    return result


def lock(root):
    adapter.require(adapter.optional_read(root, adapter.PENDING) is None, "IMPORT_PENDING_RECONCILE_REQUIRED")
    try:
        fd = os.open(root / adapter.LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError as exc:
        raise nav.Invalid("IMPORT_LOCK_RECONCILE_REQUIRED") from exc
    os.close(fd)


def heading(path, raw):
    if path.endswith(".md"):
        for line in raw.decode("utf-8").splitlines()[:30]:
            if line.startswith("# "):
                return line[2:].strip()[:400] or path
    return path


def plan_update(root, source_root, binding_path):
    adapter.require(adapter.relative(binding_path).startswith(".atlas/"), "DOCUMENT_SYNC_BINDING_SCOPE")
    config = config_model(root)
    before_binding = adapter.read(root, binding_path, 512 * 1024)
    binding = adapter.binding_model(before_binding)
    for path in [binding["matrix"]["path"], *binding["history"]["paths"], *binding["history"]["directories"]]:
        adapter.require(not path.startswith(config["destination"] + "/") and path not in
                        {config["destination"], config["inventory"], config["semantic_catalog"]}, "DOCUMENT_SYNC_OWNING_SOURCE_OVERLAP")
    inventory_raw = adapter.read(root, config["inventory"], 8 * 1024 * 1024)
    inventory = nav.parse(inventory_raw)
    adapter.require(inventory.get("schema") == "atlas.project-document-snapshot/v1"
                    and inventory.get("offline_index_only") is False, "FULL_DOCUMENT_SNAPSHOT_REQUIRED")
    adapter.require(config["inventory"] in {d["path"] for d in binding["documents"]}, "DOCUMENT_INVENTORY_NOT_BOUND")
    adapter.require(binding.get("semantic_catalog", {}).get("path") == config["semantic_catalog"], "DOCUMENT_CATALOG_NOT_BOUND")
    spec = nav.parse(adapter.read(root, config["catalog_spec"], 64 * 1024))
    old_sem_raw = adapter.read(root, config["semantic_catalog"], 8 * 1024 * 1024)
    adapter.require(adapter.pin(config["semantic_catalog"], old_sem_raw) == binding["semantic_catalog"], "SEMANTIC_CATALOG_PIN")
    old_sem = nav.parse(old_sem_raw)
    destination = adapter.directory(root, config["destination"])
    existing_generated, _ = catalog.compile_catalog(destination, spec)
    for key in ("modules", "contracts", "relations"):
        adapter.require(old_sem[key] == existing_generated[key], "MANUAL_CATALOG_EDITS_REQUIRE_RECONCILE:" + key)
    old_rows = {r["path"]: r for r in inventory["files"]}
    adapter.require(len(old_rows) == len(inventory["files"]), "DUPLICATE_DOCUMENT_INVENTORY")
    for name in old_rows:
        adapter.relative(name)
    chosen = members(source_root)
    adapter.require(set(old_rows) <= set(chosen), "DOCUMENT_REMOVAL_REQUIRES_EXPLICIT_RETIREMENT")
    for name in set(chosen) - set(old_rows):
        adapter.require(name.endswith(".md"), "UNREGISTERED_NON_MARKDOWN_DOCUMENT:" + name)
    adapter.require(set(members(destination)) == set(old_rows), "DOCUMENT_SNAPSHOT_MEMBERS_CHANGED")
    source = {}
    rows = []
    changes = {}
    total = 0
    def change(path, before, after):
        if before != after:
            changes[path] = {"before": before, "after": after}
    for name in chosen:
        raw = nav.read_selected(source_root, name, 8 * 1024 * 1024)
        total += len(raw)
        adapter.require(total <= MAX_SOURCE, "DOCUMENT_SOURCE_BYTES_LIMIT")
        source[name] = raw
        path = config["destination"] + "/" + name
        before = adapter.optional_read(root, path, 8 * 1024 * 1024)
        if name in old_rows:
            adapter.require(before is not None and adapter.pin(name, before) == {k: old_rows[name][k] for k in ("path", "sha256", "bytes")},
                            "DOCUMENT_SNAPSHOT_CHANGED_OUTSIDE_SYNC:" + name)
            selected = old_rows[name]["selected_in_view"]
        else:
            adapter.require(before is None, "DOCUMENT_NEW_PATH_ALREADY_EXISTS:" + name)
            selected = name.endswith(".md") and len(raw) <= 512 * 1024
            if selected:
                identifier = catalog.identity("DOC", name)
                adapter.require(identifier not in {d["id"] for d in binding["documents"]}, "DOCUMENT_ID_CONFLICT")
                binding["documents"].append({"id": identifier, "path": path, "title": heading(name, raw),
                    "role": "Pinned documentation snapshot; source authority=" + inventory["origin"], "domain": "documents"})
        if selected:
            adapter.require(len(raw) <= nav.MAX_FILE, "DOCUMENT_SELECTED_FILE_LIMIT:" + name)
            try:
                text = raw.decode("utf-8")
            except UnicodeError as exc:
                raise nav.Invalid("DOCUMENT_UTF8:" + name) from exc
            adapter.require("\x00" not in text, "DOCUMENT_NUL:" + name)
            if name.endswith(".json"):
                nav.parse(raw)
        rows.append({**adapter.pin(name, raw), "selected_in_view": selected})
        change(path, before, raw)
    selected = [r for r in rows if r["selected_in_view"]]
    adapter.require(len(selected) < 180 and sum(r["bytes"] for r in selected) <= 6 * 1024 * 1024,
                    "DOCUMENT_READING_SET_REQUIRES_REVIEW")
    new_generated, source_pin = catalog.compile_catalog(source_root, spec)
    adapter.require(adapter.pin(spec["path"], source[spec["path"]]) == source_pin, "DOCUMENT_SOURCE_CHANGED_DURING_SYNC")
    if "record_index" in config:
        index = nav.parse(source[config["record_index"]])
        records = nav.parse(source[spec["path"]])["contracts"]
        expected = {row["id"]: row for row in index["records"]}
        adapter.require(len(expected) == len(index["records"]) == len(records)
                        and set(expected) == {row["id"] for row in records}, "PUBLISHER_CATALOG_ID_MISMATCH")
        for row in records:
            adapter.require(expected[row["id"]]["record_canonical_sha256"] == sha((catalog.compact(row) + "\n").encode()),
                            "PUBLISHER_RECORD_HASH_MISMATCH:" + row["id"])
    # Preserve deliberately declared work/context/patch bindings. A removed linked
    # contract or changed patch base must be resolved explicitly by its writer.
    for key in ("modules", "contracts", "relations"):
        old_sem[key] = new_generated[key]
    sem_raw = retain_encoding(old_sem, old_sem_raw)
    binding["semantic_catalog"] = adapter.pin(config["semantic_catalog"], sem_raw)
    matrix, _, _ = adapter.selected_matrix(adapter.read(root, binding["matrix"]["path"]),
                                           binding["matrix"]["path"], binding["matrix"].get("pointer", ""))
    adapter.catalog_model(sem_raw, binding, {step["id"] for step in matrix["steps"]})
    inventory["files"] = rows
    inventory["catalog_source"] = source_pin
    next_inventory_raw = retain_encoding(inventory, inventory_raw)
    adapter.require(len(next_inventory_raw) <= nav.MAX_FILE, "DOCUMENT_INVENTORY_VIEW_LIMIT")
    change(config["inventory"], inventory_raw, next_inventory_raw)
    change(config["semantic_catalog"], old_sem_raw, sem_raw)
    change(binding_path, before_binding, retain_encoding(binding, before_binding))
    adapter.binding_model(nav.canonical(binding))
    bound_docs = {d["id"]: d for d in binding["documents"]}
    for patch in old_sem.get("patch_bindings", []):
        target = bound_docs[patch["target_doc_id"]]["path"]
        expected_bytes = changes[target]["after"] if target in changes else adapter.read(root, target)
        adapter.require(sha(expected_bytes) == patch["base_sha256"], "PATCH_BASE_REQUIRES_EXPLICIT_REBIND:" + patch["work_id"])
    adapter.require(members(source_root) == chosen, "DOCUMENT_SOURCE_MEMBERS_CHANGED_DURING_SYNC")
    for name, raw in source.items():
        adapter.require(nav.read_selected(source_root, name, 8 * 1024 * 1024) == raw, "DOCUMENT_SOURCE_CHANGED_DURING_SYNC:" + name)
    return config, changes, rows


def replace_one(root, item, after):
    path = item["path"]
    before = adapter.optional_read(root, path, 8 * 1024 * 1024)
    observed = sha(before) if before is not None else None
    adapter.require(observed == item["before_sha256"], "DOCUMENT_DESTINATION_CHANGED_RECONCILE:" + path)
    parent = adapter.directory(root, str(PurePosixPath(path).parent), create=True)
    fd, temp = tempfile.mkstemp(prefix=".atlas-doc-sync-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, item["mode"])
        adapter.require(adapter.optional_read(root, path, 8 * 1024 * 1024) == before, "DOCUMENT_DESTINATION_CHANGED_RECONCILE:" + path)
        os.replace(temp, root / path)
        nav.sync_directory(parent)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    adapter.require(adapter.read(root, path, 8 * 1024 * 1024) == after, "DOCUMENT_WRITE_READBACK_FAILED:" + path)


def pending_model(root):
    raw = adapter.optional_read(root, PENDING, 2 * 1024 * 1024)
    if raw is None:
        return None
    pending = nav.parse(raw)
    adapter.require(pending.get("schema") == "atlas.document-sync-pending/v1", "DOCUMENT_SYNC_PENDING_SCHEMA")
    adapter.require(adapter.relative(pending["binding"]).startswith(".atlas/"), "DOCUMENT_SYNC_BINDING_SCOPE")
    adapter.relative(pending["generation"])
    adapter.require(pending["generation"].startswith(".atlas/doc-sync/"), "DOCUMENT_SYNC_GENERATION_SCOPE")
    stage_manifest = adapter.read(root, pending["generation"] + "/PLAN.json", 2 * 1024 * 1024)
    adapter.require(sha(stage_manifest) == pending["plan_sha256"], "DOCUMENT_SYNC_PLAN_HASH")
    plan = nav.parse(stage_manifest)
    adapter.require(plan.get("schema") == "atlas.document-sync-plan/v1", "DOCUMENT_SYNC_PLAN_SCHEMA")
    adapter.require(plan["binding"] == pending["binding"], "DOCUMENT_SYNC_PENDING_BINDING")
    config = config_model(root)
    binding = adapter.binding_model(adapter.read(root, pending["binding"], 512 * 1024))
    for path in [binding["matrix"]["path"], *binding["history"]["paths"], *binding["history"]["directories"]]:
        adapter.require(not path.startswith(config["destination"] + "/") and path not in
                        {config["destination"], config["inventory"], config["semantic_catalog"]}, "DOCUMENT_SYNC_OWNING_SOURCE_OVERLAP")
    adapter.require(len(plan["changes"]) == len({item["path"] for item in plan["changes"]}) <= 2004, "DOCUMENT_SYNC_JOURNAL_PATH_LIMIT")
    for item in plan["changes"]:
        adapter.require(type(item["mode"]) is int and 0 <= item["mode"] <= 0o777, "DOCUMENT_SYNC_JOURNAL_MODE")
        path = adapter.relative(item["path"])
        adapter.require(path.startswith(config["destination"] + "/") or path in
                        {config["inventory"], config["semantic_catalog"], pending["binding"]}, "DOCUMENT_SYNC_RECOVERY_SCOPE")
        for key in ("before_file", "after_file"):
            if item[key] is not None:
                adapter.require(item[key]["path"].startswith(pending["generation"] + "/"), "DOCUMENT_SYNC_JOURNAL_FILE_SCOPE")
        after = adapter.read(root, item["after_file"]["path"], 8 * 1024 * 1024)
        adapter.require(adapter.pin(item["after_file"]["path"], after) == item["after_file"]
                        and sha(after) == item["after_sha256"], "DOCUMENT_SYNC_AFTER_HASH")
        if item["before_file"] is not None:
            before = adapter.read(root, item["before_file"]["path"], 8 * 1024 * 1024)
            adapter.require(adapter.pin(item["before_file"]["path"], before) == item["before_file"]
                            and sha(before) == item["before_sha256"], "DOCUMENT_SYNC_BEFORE_HASH")
    return pending, plan


def finish(root, pending, plan):
    for item in plan["changes"]:
        current = adapter.optional_read(root, item["path"], 8 * 1024 * 1024)
        digest = sha(current) if current is not None else None
        adapter.require(digest in (item["before_sha256"], item["after_sha256"]), "DOCUMENT_DESTINATION_CHANGED_RECONCILE:" + item["path"])
    for item in plan["changes"]:
        current = adapter.optional_read(root, item["path"], 8 * 1024 * 1024)
        if current is not None and sha(current) == item["after_sha256"]:
            continue
        replace_one(root, item, adapter.read(root, item["after_file"]["path"], 8 * 1024 * 1024))
    result = {"schema": "atlas.document-sync-receipt/v1", "status": "DOCUMENT_SNAPSHOT_UPDATED",
              "generation": pending["generation"], "plan_sha256": pending["plan_sha256"],
              "changed_paths": [r["path"] for r in plan["changes"]], "source_root": plan["source_root"],
              "matrix_writes": 0, "runtime_acceptance": "NOT_RUN"}
    adapter.atomic(root, pending["generation"] + "/RECEIPT.json", nav.canonical(result))
    (root / PENDING).unlink()
    nav.sync_directory(root / ".atlas")
    return result


def update(root, source_root, binding_path=".atlas/UPSTREAM.json"):
    root, source_root = plain_root(root), plain_root(source_root)
    adapter.require(adapter.optional_read(root, PENDING) is None, "DOCUMENT_SYNC_PENDING_RECONCILE_REQUIRED")
    lock(root)
    try:
        config, changes, rows = plan_update(root, source_root, binding_path)
        if not changes:
            result = {"status": "NO_CHANGE", "changed_paths": [], "matrix_writes": 0}
        else:
            state_raw = adapter.optional_read(root, adapter.STATE, 2 * 1024 * 1024)
            identity = {"binding": binding_path, "prior_import_state_sha256": sha(state_raw) if state_raw is not None else None,
                        "changes": [{"path": path, "before_sha256": sha(c["before"]) if c["before"] is not None else None,
                        "after_sha256": sha(c["after"])} for path, c in sorted(changes.items())]}
            generation = ".atlas/doc-sync/" + sha(nav.canonical(identity))
            adapter.require(not (root / generation).exists(), "DOCUMENT_SYNC_GENERATION_RECONCILE_REQUIRED")
            adapter.directory(root, generation, create=True)
            items = []
            for index, (path, change) in enumerate(sorted(changes.items(), key=lambda item: (item[0] == binding_path, item[0]))):
                before, after = change["before"], change["after"]
                before_file = None
                if before is not None:
                    name = generation + "/" + str(index) + ".before"
                    adapter.atomic(root, name, before)
                    before_file = adapter.pin(name, before)
                name = generation + "/" + str(index) + ".after"
                adapter.atomic(root, name, after)
                items.append({"path": path, "before_sha256": sha(before) if before is not None else None, "after_sha256": sha(after),
                              "before_file": before_file, "after_file": adapter.pin(name, after),
                              "mode": (root / path).stat().st_mode & 0o777 if before is not None else 0o600})
            plan = {"schema": "atlas.document-sync-plan/v1", "binding": binding_path, "source_root": str(source_root),
                    "source_inventory": rows, "changes": items, "observed_at": datetime.now(timezone.utc).isoformat()}
            plan_raw = nav.canonical(plan)
            adapter.require(len(plan_raw) <= 2 * 1024 * 1024, "DOCUMENT_SYNC_PLAN_LIMIT")
            adapter.atomic(root, generation + "/PLAN.json", plan_raw)
            pending = {"schema": "atlas.document-sync-pending/v1", "generation": generation, "plan_sha256": sha(plan_raw), "binding": binding_path}
            adapter.atomic(root, PENDING, nav.canonical(pending))
            result = finish(root, pending, plan)
    finally:
        (root / adapter.LOCK).unlink()
    result["projection"] = adapter.refresh(root, binding_path=binding_path)
    return result


def reconcile(root, binding_path=".atlas/UPSTREAM.json", finish_pending=False):
    root = plain_root(root)
    parsed = pending_model(root)
    if parsed is None:
        return {"status": "NO_DOCUMENT_SYNC_PENDING", "effect": "READ_ONLY"}
    pending, plan = parsed
    adapter.require(pending["binding"] == binding_path, "DOCUMENT_SYNC_BINDING_MISMATCH")
    if not finish_pending:
        files = []
        for item in plan["changes"]:
            raw = adapter.optional_read(root, item["path"], 8 * 1024 * 1024)
            digest = sha(raw) if raw is not None else None
            state = "AFTER" if digest == item["after_sha256"] else ("BEFORE" if digest == item["before_sha256"] else "CONFLICT")
            files.append({"path": item["path"], "state": state})
        return {"status": "DOCUMENT_SYNC_RECONCILE_REQUIRED", "generation": pending["generation"], "files": files,
                "lock_present": (root / adapter.LOCK).exists(), "effect": "READ_ONLY"}
    lock(root)
    try:
        parsed_again = pending_model(root)
        adapter.require(parsed_again == parsed, "DOCUMENT_SYNC_PENDING_CHANGED")
        result = finish(root, pending, plan)
    finally:
        (root / adapter.LOCK).unlink()
    result["projection"] = adapter.refresh(root, binding_path=binding_path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("update", "reconcile"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--binding", default=".atlas/UPSTREAM.json")
    parser.add_argument("--source-root")
    parser.add_argument("--finish-pending", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "update":
            adapter.require(args.source_root is not None and not args.finish_pending, "UPDATE_SOURCE_ROOT_REQUIRED")
            result = update(args.root, args.source_root, binding_path=args.binding)
        else:
            adapter.require(args.source_root is None, "RECONCILE_HAS_NO_NEW_SOURCE")
            result = reconcile(args.root, binding_path=args.binding, finish_pending=args.finish_pending)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (nav.Invalid, OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        print(json.dumps({"status": "REFUSED", "code": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
