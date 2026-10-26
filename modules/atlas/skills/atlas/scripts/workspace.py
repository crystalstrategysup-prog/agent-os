#!/usr/bin/env python3
"""Fixed local Atlas workspace commands for explicitly registered projects.

This facade calls existing adapters in process. It never discovers host roots,
runs a shell, opens a browser, sends a message, or deploys a project.
"""
import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import atlas
import import_matrix
import navigator as nav

VERSION = "ATLAS-WORKSPACE-1.2.0"
require = nav.require


def local_path(value, *, directory):
    """Validate the lexical path before resolving, including every ancestor."""
    require(isinstance(value, str) and value and "\x00" not in value, "WORKSPACE_PATH")
    path = Path(value)
    require(path.is_absolute(), "WORKSPACE_ABSOLUTE_PATH_REQUIRED")
    require(not any(part in (".", "..") for part in value.split("/")), "WORKSPACE_PATH_TRAVERSAL")
    for entry in (path, *path.parents):
        require(not entry.is_symlink(), "WORKSPACE_SYMLINK")
    require(path.is_dir() if directory else path.is_file(), "WORKSPACE_DIRECTORY_REQUIRED" if directory else "WORKSPACE_FILE_REQUIRED")
    return path.resolve()


def load_registry(path):
    selected = Path(path).absolute()
    selected = local_path(str(selected), directory=False)
    raw = nav.read_selected(selected.parent, selected.name, 512 * 1024)
    value = nav.parse(raw)
    import_matrix.shape(value, ("schema", "projects"), label="workspace")
    require(value["schema"] == "atlas.workspace/v1", "WORKSPACE_SCHEMA")
    require(isinstance(value["projects"], list) and 0 < len(value["projects"]) <= 1000, "WORKSPACE_PROJECT_LIMIT")
    projects = {}
    roots = set()
    for item in value["projects"]:
        import_matrix.shape(item, ("key", "root", "binding"), label="workspace.project")
        nav.ident(item["key"])
        require(item["key"] not in projects, "WORKSPACE_DUPLICATE_KEY")
        root = local_path(item["root"], directory=True)
        require(root not in roots, "WORKSPACE_DUPLICATE_ROOT")
        atlas.path_text(item["binding"])
        require(item["binding"].startswith(".atlas/"), "WORKSPACE_BINDING_SCOPE")
        roots.add(root)
        projects[item["key"]] = {"key": item["key"], "root": str(root), "binding": item["binding"]}
    return projects


def registered_project(registry, key):
    require(key in registry, "WORKSPACE_UNKNOWN_PROJECT")
    project = registry[key]
    root = local_path(project["root"], directory=True)
    binding = import_matrix.binding_model(import_matrix.read(root, project["binding"], 512 * 1024))
    return project, root, binding


def view_receipt(root, binding):
    """Return only an index belonging to a hash-verified CURRENT release."""
    output = root / binding["output"]
    pointer, snapshot = atlas.current_output(output)
    if pointer is None:
        return {"view_path": None, "current": None}
    index = nav.safe(output, "releases/" + pointer["release"] + "/index.html")
    current_view = nav.current_view_status(
        output, expected_release=pointer["release"],
        expected_manifest_sha256=pointer["manifest_sha256"])
    selected = current_view["path"] if current_view["status"] == "CURRENT" else str(index)
    return {"view_path": selected, "current": pointer, "current_view": current_view}


def publish_view_receipt(root, binding):
    """Explicit write flows may repair the alias for an exact retained CURRENT."""
    output = root / binding["output"]
    pointer, _ = atlas.current_output(output)
    if pointer is None:
        return view_receipt(root, binding)
    current_view = nav.publish_current_view(
        output, expected_release=pointer["release"],
        expected_manifest_sha256=pointer["manifest_sha256"])
    return {"view_path": current_view["path"], "current": pointer,
            "current_view": current_view}


def matrix_freshness(root, binding, snapshot):
    """Compare only the selected owning matrix; do not claim all docs are fresh."""
    presentation = snapshot.get("atlas", {}).get("presentation", {})
    if not isinstance(presentation, dict):
        presentation = {}
    expected = presentation.get("source_matrix_sha256")
    base = {"scope": "SELECTED_OWNING_MATRIX_ONLY", "documents": "NOT_COMPARED",
            "expected_sha256": expected, "observed_sha256": None,
            "source_revision": "UNKNOWN", "writes": "NONE"}
    if presentation.get("source_matrix_status") != "PINNED" or not isinstance(expected, str) or not nav.SHA.fullmatch(expected):
        return {**base, "status": "UNKNOWN", "code": "SOURCE_MATRIX_PIN_UNAVAILABLE"}
    path = binding["matrix"]["path"]
    try:
        before = import_matrix.source_stat(root, path)
        raw = import_matrix.read(root, path)
        matrix, selected, _ = import_matrix.selected_matrix(raw, path, binding["matrix"].get("pointer", ""))
        after = import_matrix.source_stat(root, path)
        if before != after:
            return {**base, "status": "UNKNOWN", "code": "SOURCE_CHANGED_DURING_READ"}
        observed = nav.digest(selected)
        revision = matrix.get("revision")
        return {**base, "status": "MATCHED" if observed == expected else "CHANGED",
                "observed_sha256": observed,
                "source_revision": revision if type(revision) is int and revision >= 0 else "UNKNOWN"}
    except (nav.Invalid, OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
        return {**base, "status": "UNKNOWN",
                "code": str(exc) if isinstance(exc, nav.Invalid) else type(exc).__name__}


def coverage_summary(value):
    """Keep coverage qualifications without returning potentially large gap rows."""
    domains = value.get("domains", [])
    return {"status": value.get("status", "UNKNOWN"),
            "domain_count": len(domains), "domains_complete": len(domains) <= 32,
            "domains": [{"id": row.get("id"), "status": row.get("status", "UNKNOWN"),
                         "inventory_count": row.get("inventory_count"),
                         "documented_count": row.get("documented_count"),
                         "missing_count": len(row.get("missing_ids", [])),
                         "exclusion_count": len(row.get("exclusions", []))}
                        for row in domains[:32]],
            "issue_count": len(value.get("issues", [])),
            "qualification": "Coverage of the inventory declared in this immutable snapshot only."}


def source_revision(snapshot, presentation):
    """A source revision is available only through an exact declared document pin."""
    status = presentation.get("source_matrix_status")
    if status != "PINNED":
        return "UNKNOWN", status if status in ("UNAVAILABLE", "AMBIGUOUS") else "NOT_DECLARED"
    doc_id = presentation.get("source_matrix_doc_id")
    digest = presentation.get("source_matrix_sha256")
    if not isinstance(doc_id, str) or not isinstance(digest, str) or not nav.SHA.fullmatch(digest):
        return "UNKNOWN", "PIN_UNAVAILABLE"
    matches = [row for row in snapshot.get("documents", []) if row.get("id") == doc_id]
    if len(matches) != 1:
        return "UNKNOWN", "DOCUMENT_UNAVAILABLE_OR_AMBIGUOUS"
    document = matches[0]
    content = document.get("content")
    if not isinstance(content, str) or document.get("sha256") != digest or nav.digest(content.encode("utf-8")) != digest:
        return "UNKNOWN", "PIN_MISMATCH"
    try:
        matrix = nav.parse(content.encode("utf-8"))
    except nav.Invalid:
        return "UNKNOWN", "SOURCE_JSON_UNAVAILABLE"
    revision = matrix.get("revision") if isinstance(matrix, dict) else None
    if type(revision) is not int or revision < 0:
        return "UNKNOWN", "REVISION_UNAVAILABLE"
    return revision, "MATCHED_PINNED_DOCUMENT"


def project_views(root, binding):
    """Read verified CURRENT and compare its matrix. Do not refresh or write."""
    output = root / binding["output"]
    pointer, snapshot = atlas.current_output(output)
    base = {"schema": "atlas.workspace.views/v1", "current": pointer,
            "freshness": {"current_basis": "POINTER_OBSERVED_ONCE",
                          "owning_sources": "NOT_COMPARED",
                          "qualification": "The view is the verified retained release; this read does not establish freshness against active owning sources."},
            "presentation": {"status": "NOT_REQUESTED", "browser": "NOT_REQUESTED"},
            "product_execution": "NOT_RUN"}
    if pointer is None:
        return {**base, "status": "NO_CURRENT_VIEW", "view_path": None,
                "release": None, "as_of": None, "source_revision": "UNKNOWN",
                "source_revision_status": "NO_CURRENT_VIEW", "coverage": {"status": "UNKNOWN"},
                "artifacts": {}, "sections": {},
                "next_action": "The current writer must publish its saved source delta through the declared finish route before a view can be returned."}
    model = snapshot["atlas"]
    require(model["project"]["id"] == binding["project"]["id"], "WORKSPACE_VIEW_PROJECT_MISMATCH")
    prefix = "releases/" + pointer["release"] + "/"
    raw_manifest = nav.read_selected(output, prefix + "MANIFEST.json", 512 * 1024)
    require(nav.digest(raw_manifest) == pointer["manifest_sha256"], "OUTPUT_MANIFEST_HASH")
    manifest = nav.parse(raw_manifest)
    artifacts = {}
    for key, name in (("html", "index.html"), ("json", "snapshot.json")):
        path = nav.safe(output, prefix + name)
        artifacts[key] = {"path": str(path), "url": path.as_uri(), **manifest["files"][name]}
    presentation = model.get("presentation", {})
    if not isinstance(presentation, dict) or presentation.get("schema") != "atlas.presentation/v1":
        presentation = {}
    declared = presentation.get("sections", [])
    if not isinstance(declared, list) or not all(isinstance(item, str) for item in declared):
        declared = []
    current_view = nav.current_view_status(
        output, expected_release=pointer["release"],
        expected_manifest_sha256=pointer["manifest_sha256"])
    # A modified stable alias cannot be trusted. A missing alias is different:
    # the retained release has already passed immutable hash verification and
    # remains readable, while the writer is offered an explicit repair route.
    require(current_view["status"] != "STALE", "OUTPUT_FILE_HASH")
    # Preserve the published current alias for clients following the current
    # view; a missing alias falls back to the verified immutable release.
    selected_path = current_view["path"] if current_view["status"] == "CURRENT" else artifacts["html"]["path"]
    # Keep the stable alias as the backwards-compatible public link. A
    # separate immutable_url anchors the exact verified release so a reader
    # can select either latest-following or evidence-pinned navigation.
    selected_url = Path(selected_path).as_uri()
    immutable_url = Path(artifacts["html"]["path"]).as_uri()
    sections = {name: {"section": name, "anchor_supported": name in declared,
                       "url": selected_url + ("#" + name if name in declared else ""),
                       "immutable_url": immutable_url + ("#" + name if name in declared else ""),
                       "fallback": None if name in declared else "Open the base artifact and select the section manually; this release declares no matching anchor."}
                for name in ("contracts", "roadmap")}
    revision, revision_status = source_revision(snapshot, presentation)
    result = {**base, "status": "ARTIFACTS_READY", "release": pointer["release"],
              "as_of": model["as_of"], "source_sha256": model["source_sha256"],
              "source_revision": revision, "source_revision_status": revision_status,
              "renderer": presentation.get("renderer", "UNKNOWN"),
              "coverage": coverage_summary(model.get("coverage", {})),
              "counts": {"works": len(model.get("works", [])),
                         "documents": len(snapshot.get("documents", [])),
                         "contracts": len(snapshot["input"].get("contracts", [])),
                         "modules": len(snapshot["input"].get("modules", [])),
                         "matrix_history_total": model.get("matrix_history_total", "UNKNOWN")},
              "artifacts": artifacts, "view_path": selected_path,
              "current_view": current_view, "sections": sections}
    result["freshness"]["matrix"] = matrix_freshness(root, binding, snapshot)
    result["freshness"]["qualification"] = (
        "The selected owning matrix is compared without writing. Other source documents are not compared. "
        "The stable current page follows later saved publications when reloaded; immutable artifacts remain historical.")
    if result["freshness"]["matrix"]["status"] == "CHANGED":
        result["next_action"] = "The current writer must publish the saved source delta with finish; this read did not refresh it."
    elif current_view["status"] == "CURRENT_CHANGED":
        result["next_action"] = "CURRENT changed during this read. Read views again to select its verified release; the returned immutable artifacts remain valid."
    elif current_view["status"] in ("MISSING", "STALE"):
        result["next_action"] = "The current writer may repair the stable view with finish. This read returned the verified immutable release and wrote nothing."
    require(len(json.dumps(result, ensure_ascii=False).encode("utf-8")) + 1 <= 30 * 1024,
            "WORKSPACE_VIEWS_OUTPUT_LIMIT")
    return result


def prepare_work_record(root, binding, binding_path, args):
    """Bind typed parameters to one immutable checkpoint request, without shell.

    The engine still validates ownership, the profile and every source pin under
    its writer lock. This small facade saves repeated manual hashing and keeps
    the original timestamp and preimages when the same request is retried.
    """
    require(isinstance(args.operation, str) and re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", args.operation), "CHECKPOINT_OPERATION_ID")
    profile = nav.parse(import_matrix.read(root, ".atlas/WRITER.json", 256 * 1024))
    require(isinstance(profile, dict) and profile.get("schema") == "atlas.matrix-writer/v1",
            "CHECKPOINT_WRITER_PROFILE_REQUIRED")
    require(profile.get("binding") == binding_path and
            profile.get("project_id") == binding["project"]["id"] and
            profile.get("writer") == binding["project"]["writer"] and
            profile.get("matrix") == {"path": binding["matrix"]["path"],
                                      "pointer": binding["matrix"].get("pointer", ""),
                                      "allowed_schema": binding["matrix"]["allowed_schema"]},
            "CHECKPOINT_WRITER_BINDING_CHANGED")
    status = args.status
    if args.phase in ("start", "dispatch"):
        require(status in (None, "doing"), "CHECKPOINT_START_STATUS")
        status = "doing"
    else:
        require(status is not None, "WORKSPACE_WORK_STATUS_REQUIRED")
    evidence_paths = list(args.evidence)
    document_pairs = [list(pair) for pair in args.document_edit]
    require(len(evidence_paths) <= 32 and len(document_pairs) <= 16, "CHECKPOINT_INPUT_LIMIT")
    for path in evidence_paths + [path for pair in document_pairs for path in pair]:
        import_matrix.relative(path)
    require(len(set(evidence_paths)) == len(evidence_paths), "CHECKPOINT_DUPLICATE_EVIDENCE")
    require(len({pair[0] for pair in document_pairs}) == len(document_pairs), "CHECKPOINT_DUPLICATE_DOCUMENT")
    identity = {"operation_id": args.operation, "project_id": profile["project_id"],
                "writer": profile["writer"], "work_id": args.work, "phase": args.phase,
                "executor_id": args.executor, "status": status,
                "note": args.note, "next_action": args.next_action}
    record_path = ".atlas/checkpoint-records/" + args.operation + ".json"

    def same_request(raw):
        value = nav.parse(raw)
        require(isinstance(value, dict) and value.get("schema") == "atlas.checkpoint/v1",
                "CHECKPOINT_PREPARED_RECORD_SCHEMA")
        require(isinstance(value.get("evidence"), list) and
                all(isinstance(item, dict) for item in value["evidence"]) and
                isinstance(value.get("document_edits"), list) and
                all(isinstance(item, dict) and isinstance(item.get("after"), dict)
                    for item in value["document_edits"]), "CHECKPOINT_PREPARED_RECORD_SHAPE")
        require(all(value.get(key) == item for key, item in identity.items()) and
                [item.get("path") for item in value.get("evidence", [])] == evidence_paths and
                [[item.get("path"), item.get("after", {}).get("path")]
                 for item in value.get("document_edits", [])] == document_pairs and
                "activity" not in value, "CHECKPOINT_OPERATION_PARAMETERS_CHANGED")
        return record_path

    existing = import_matrix.optional_read(root, record_path, 256 * 1024)
    if existing is not None:
        return same_request(existing)
    require(isinstance(args.note, str) and 0 < len(args.note) <= 16384 and
            isinstance(args.next_action, str) and 0 < len(args.next_action) <= 4096,
            "CHECKPOINT_NOTE_OR_NEXT_ACTION")
    source_path = binding["matrix"]["path"]
    before = import_matrix.source_stat(root, source_path)
    source_raw = import_matrix.read(root, source_path)
    matrix, _, _ = import_matrix.selected_matrix(source_raw, source_path,
                                                 binding["matrix"].get("pointer", ""))
    require(before == import_matrix.source_stat(root, source_path), "SOURCE_CHANGED_DURING_PREPARE")

    def pin(raw):
        return {"sha256": nav.digest(raw), "bytes": len(raw)}

    def selected_pin(path):
        return {"path": path, **pin(import_matrix.read(root, path, 2 * 1024 * 1024))}

    record = {"schema": "atlas.checkpoint/v1", **identity,
              "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "expected_source": {**pin(source_raw), "revision": matrix.get("revision")},
              "evidence": [selected_pin(path) for path in evidence_paths],
              "document_edits": [{"path": destination,
                                  "before": pin(import_matrix.read(root, destination, 2 * 1024 * 1024)),
                                  "after": selected_pin(prepared)}
                                 for destination, prepared in document_pairs]}
    raw = nav.canonical(record)
    require(len(raw) <= 256 * 1024, "CHECKPOINT_RECORD_LIMIT")
    directory = import_matrix.directory(root, ".atlas/checkpoint-records", create=True)
    destination = directory / (args.operation + ".json")
    fd, temporary = tempfile.mkstemp(prefix=".prepare-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Exclusive atomic publication: a concurrent preparation may win, but
        # cannot be replaced by this one. Compare its semantic parameters below.
        import_matrix.directory(root, ".atlas/checkpoint-records")
        try:
            os.link(temporary, destination, follow_symlinks=False)
            nav.sync_directory(directory)
        except FileExistsError:
            pass
    finally:
        os.unlink(temporary)
    return same_request(import_matrix.read(root, record_path, 256 * 1024))


def run(args):
    registry = load_registry(args.registry)
    if args.command == "list":
        return {"schema": "atlas.workspace.list/v1", "projects": list(registry.values())}
    project, root, binding = registered_project(registry, args.project)
    context = {"project_key": project["key"]}
    if args.command in ("history-requalify", "history-requalification-status"):
        import history_requalification
        # No viewer/publication read or repair: certificate status is separate.
        return {**history_requalification.requalify(root, args.operation, project["binding"], args.cursor,
                    read_only=args.command == "history-requalification-status"), **context}
    if args.command == "views":
        return {**project_views(root, binding), **context}
    if args.command in ("refresh", "start", "finish"):
        refreshed = import_matrix.refresh(root, binding_path=project["binding"])
        if args.command == "start":
            snapshot = atlas.load_project(root, import_matrix.PROJECT)
            result = {"status": "CONTEXT_LOADED", "refresh": refreshed,
                      "packet": atlas.packet(snapshot, args.work),
                      "summary": snapshot["atlas"]["summary"], "coverage": snapshot["atlas"]["coverage"],
                      "work_recording": "NOT_REQUESTED",
                      "next_action": "When work starts or is dispatched, the current writer must save its lifecycle checkpoint immediately."}
        else:
            result = refreshed
    elif args.command == "packet":
        snapshot = atlas.load_project(root, import_matrix.PROJECT)
        result = {"status": "CONTEXT_LOADED", "packet": atlas.packet(snapshot, args.work)}
    elif args.command == "audit":
        snapshot = atlas.load_project(root, import_matrix.PROJECT)
        model = snapshot["atlas"]
        result = {"status": "PROJECT_CONTROL_REVIEW", "source_sha256": model["source_sha256"],
                  "as_of": model["as_of"], "coverage": model["coverage"], "summary": model["summary"],
                  "issues": model["issues"], "next_actions": atlas.next_actions(snapshot),
                  "product_execution": "NOT_RUN"}
    elif args.command == "history":
        result = atlas.history(root / binding["output"], limit=args.limit, cursor=args.cursor)
    elif args.command == "reconcile":
        result = import_matrix.reconcile(root, binding_path=project["binding"])
    elif args.command == "docs":
        import sync_docs
        source = local_path(str(Path(args.source_root).absolute()), directory=True)
        result = sync_docs.update(root, source, binding_path=project["binding"])
    elif args.command == "docs-reconcile":
        import sync_docs
        result = sync_docs.reconcile(root, binding_path=project["binding"], finish_pending=args.finish_pending)
    elif args.command == "checkpoint":
        import checkpoint
        result = checkpoint.checkpoint(root, args.record, binding_path=project["binding"])
    elif args.command == "work":
        import checkpoint
        record_path = prepare_work_record(root, binding, project["binding"], args)
        result = checkpoint.checkpoint(root, record_path, binding_path=project["binding"])
        result = {**result, "prepared_record": record_path}
    elif args.command == "checkpoint-reconcile":
        import checkpoint
        result = checkpoint.reconcile(root, args.operation, binding_path=project["binding"],
                                      finish_pending=args.finish_pending,
                                      inspect_note_restore=args.inspect_protected_note_restore,
                                      restore_note=args.restore_protected_note,
                                      inspect_text_restore=args.inspect_protected_text_restore,
                                      restore_texts=args.restore_protected_texts)
    else:
        raise nav.Invalid("WORKSPACE_COMMAND")
    explicit_write = args.command in ("refresh", "start", "finish", "docs", "checkpoint", "work") or (
        args.command in ("docs-reconcile", "checkpoint-reconcile") and args.finish_pending)
    # A partial source transaction must be reconciled before repairing or publishing
    # a view. Its existing verified release is still available as historical data.
    complete = result.get("status") in ("IMPORTED_PARTIAL", "NO_CHANGE", "CONTEXT_LOADED",
                                        "DOCUMENT_SNAPSHOT_UPDATED", "CHECKPOINT_PUBLISHED")
    receipt = publish_view_receipt(root, binding) if explicit_write and complete else view_receipt(root, binding)
    return {**result, **context, **receipt}


def parser():
    result = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
        epilog="The AgentOS facade also supports optional atlas profile --help (no registry or project writes).")
    result.add_argument("--registry", required=True, help="Explicit local atlas.workspace/v1 registry JSON")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("list", allow_abbrev=False, help="List registered project keys without refreshing")
    for name in ("refresh", "start", "finish", "packet", "audit", "history", "reconcile", "docs", "docs-reconcile", "work", "checkpoint", "checkpoint-reconcile", "views", "history-requalify", "history-requalification-status"):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument("project", help="An exact key from the registry")
        if name in ("history-requalify", "history-requalification-status"):
            command.add_argument("--operation", required=True, help="Stable finite history requalification operation; never a checkpoint replay")
            command.add_argument("--cursor", type=int, default=0, help="Last observed cursor; duplicate last page requests do not replay")
        if name in ("start", "packet"):
            command.add_argument("--work", required=True, help="Exact work ID for the context packet")
        if name == "history":
            command.add_argument("--limit", type=int, default=50, help="Retained release page size, 1–100")
            command.add_argument("--cursor", help="Opaque next_cursor from the preceding history page")
        if name == "docs":
            command.add_argument("--source-root", required=True, help="Explicit local directory of replacement owning documents")
        if name == "docs-reconcile":
            command.add_argument("--finish-pending", action="store_true", help="Finish the existing document update operation only")
        if name == "checkpoint":
            command.add_argument("--record", required=True, help="Prepared project-relative atlas.checkpoint/v1 record for the current owning writer")
        if name == "work":
            command.add_argument("--operation", required=True, help="Stable identity for this real work fact; reuse it after interruption")
            command.add_argument("--work", required=True, help="Exact existing source work ID")
            command.add_argument("--phase", required=True, choices=("start", "dispatch", "progress", "complete"))
            command.add_argument("--executor", required=True, help="Exact existing executor ID")
            command.add_argument("--status", choices=("doing", "waiting", "blocked", "partial", "done"),
                                 help="Start/dispatch imply doing; progress/complete require an explicit status")
            command.add_argument("--note", required=True, help="The new observed work fact")
            command.add_argument("--next-action", required=True, help="The owned next action or remaining work")
            command.add_argument("--evidence", action="append", default=[], help="Existing project-relative evidence file; repeat as needed")
            command.add_argument("--document-edit", action="append", nargs=2, default=[], metavar=("DOCUMENT", "PREPARED_FILE"),
                                 help="Existing allowed document and separate prepared replacement; repeat as needed")
        if name == "checkpoint-reconcile":
            command.add_argument("--operation", required=True, help="Exact checkpoint operation ID; never create a replacement identity after interruption")
            command.add_argument("--finish-pending", action="store_true", help="Finish only the exact retained checkpoint after all destinations match their before/after pins")
            command.add_argument("--inspect-protected-note-restore", action="store_true",
                                 help="READ ONLY: verify prior published project.scope_note against the exact pending operation")
            command.add_argument("--restore-protected-note", action="store_true",
                                 help="WITH --finish-pending: restore only the prior protected project.scope_note and publish the original pending operation")
            command.add_argument("--inspect-protected-text-restore", action="store_true",
                                 help="Read-only exact predecessor objective/scope_note restoration review")
            command.add_argument("--restore-protected-texts", action="store_true",
                                 help="Restore exact predecessor objective/scope_note with --finish-pending")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = run(args)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (nav.Invalid, OSError, UnicodeError, KeyError, TypeError, ValueError, ImportError) as exc:
        print(json.dumps({"status": "REFUSED", "code": str(exc) if isinstance(exc, nav.Invalid) else type(exc).__name__}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
