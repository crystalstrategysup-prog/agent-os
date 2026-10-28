"""Finite, explicit re-attestation of immutable imported history. No publication.

The journal is trusted local owner state, like IMPORT_STATE; hashes are not a
signature against a hostile same-UID writer. Every admission is rooted in the
selected generation and verified retained pins, never in caller-supplied stats.
"""
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

import import_matrix as imp
import navigator as nav
import atlas

BASE = ".atlas/history-requalification"
MAX_PAGE_ROWS = 64
MAX_META = 8 * 1024 * 1024
require = nav.require


class Budget:
    def __init__(self, root):
        self.root = root
        self.used = 0
        self.guards = {}

    def read(self, root, path, limit=MAX_META):
        require(root == self.root, "REQUALIFICATION_ROOT")
        before = imp.source_stat(root, path)
        require(before["bytes"] <= limit, "REQUALIFICATION_FILE_LIMIT")
        require(self.used + before["bytes"] <= atlas.MAX_SELECTED,
                "REQUALIFICATION_READ_BUDGET")
        # Bound allocation even if a writer expands the file after stat.
        raw = imp.read(root, path, min(limit, atlas.MAX_SELECTED - self.used))
        self.used += len(raw)
        after = imp.source_stat(root, path)
        require(before == after and len(raw) == before["bytes"],
                "REQUALIFICATION_CHANGED_DURING_READ")
        if path in self.guards:
            require(self.guards[path] == after, "REQUALIFICATION_READ_RACE")
        self.guards[path] = after
        return raw

    def optional(self, path, limit=MAX_META):
        # Validate the entire path, including absent destinations' ancestors.
        imp.directory(self.root, str(Path(path).parent))
        p = self.root / imp.relative(path)
        require(not p.is_symlink(), "REQUALIFICATION_SYMLINK")
        return self.read(self.root, path, limit) if p.exists() else None


def _root(root):
    root = Path(root).absolute()
    require(root.is_dir() and all(not p.is_symlink() for p in (root, *root.parents)),
            "REQUALIFICATION_ROOT_SYMLINK")
    return root.resolve()


def _operation(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value),
            "REQUALIFICATION_OPERATION")
    return BASE + "/operations/" + value


def _rows(meta):
    rows = []
    used = set()
    for origin in meta.get("history_origins", []):
        require(origin.get("retained_file") and origin.get("matrix_at"),
                "REQUALIFICATION_RETAINED_PIN_REQUIRED")
        rows.append({"origin": origin, "retained": origin["retained_file"]})
        used.add(origin["retained_file"]["path"])
    # Also verify retained-only matrices. No old history is silently excluded.
    for item in meta["retained_matrices"]:
        if item["file"]["path"] not in used:
            rows.append({"origin": None, "retained": item["file"]})
            used.add(item["file"]["path"])
    require(len(rows) <= imp.MAX_METADATA_ROWS, "REQUALIFICATION_ROSTER_LIMIT")
    return rows


def _context(root, binding_path, budget, preloaded=None):
    binding_raw = budget.read(root, binding_path, 512 * 1024)
    b = imp.binding_model(binding_raw)
    state_raw = budget.read(root, imp.STATE, 2 * 1024 * 1024)
    state = nav.parse(state_raw)
    require(state.get("schema") == "atlas.import-state/v1", "REQUALIFICATION_STATE_SCHEMA")
    fingerprint = state.get("fingerprint")
    require(isinstance(fingerprint, str) and nav.SHA.fullmatch(fingerprint), "REQUALIFICATION_GENERATION")
    require(state.get("generation") == ".atlas/imports/" + fingerprint,
            "REQUALIFICATION_GENERATION")
    require(state.get("binding_sha256") == imp.sha(binding_raw), "REQUALIFICATION_BINDING_DRIFT")
    meta_path = state["generation"] + "/IMPORT.json"
    meta_raw = budget.read(root, meta_path)
    require(imp.sha(meta_raw) == state.get("generation_meta_sha256"), "REQUALIFICATION_METADATA_PIN_REQUIRED")
    meta = imp.hydrate_history_metadata(root, nav.parse(meta_raw), reader=budget.read)
    require(meta.get("generation") == state["generation"] and meta.get("fingerprint") == fingerprint,
            "REQUALIFICATION_GENERATION")
    if "retained_matrices" not in meta:
        raise nav.Invalid("REQUALIFICATION_PAGED_OR_RETAINED_METADATA_REQUIRED")
    projection = budget.read(root, imp.PROJECT, 512 * 1024)
    require(imp.sha(projection) == state.get("project_sha256"), "REQUALIFICATION_PROJECTION_DRIFT")
    retained_binding = budget.read(root, meta["binding_file"]["path"], 512 * 1024)
    require(imp.pin(meta["binding_file"]["path"], retained_binding) == meta["binding_file"],
            "REQUALIFICATION_RETAINED_BINDING")
    require(retained_binding == binding_raw, "REQUALIFICATION_BINDING_DRIFT")
    paths = imp.history_paths(root, b)
    rows = _rows(meta)
    origins = meta.get("history_origins", [])
    # Explicit requalification freezes the complete roster, including new paths.
    # It cannot attest a partially appended source history set.
    require({o["path"] for o in origins} <= set(paths), "REQUALIFICATION_ROSTER_DRIFT")
    requested = {b["matrix"]["path"], *[d["path"] for d in b["documents"]]}
    if b.get("semantic_catalog"):
        requested.add(b["semantic_catalog"]["path"])
    source_pins = []
    for path in sorted(requested):
        if preloaded is None:
            raw = budget.read(root, path)
        else:
            require(path in preloaded, "REQUALIFICATION_SOURCE_MISSING")
            raw = preloaded[path]
        source_pins.append(imp.pin(path, raw))
    physical = []
    for row in rows:
        physical.append({"source": imp.source_stat(root, row["origin"]["path"]) if row["origin"] else None,
                         "retained": imp.source_stat(root, row["retained"]["path"])})
    extras = {}
    for path in (".atlas/WRITER.json", ".atlas/CHECKPOINT_PENDING.json", imp.PENDING, imp.DOC_PENDING):
        raw = budget.optional(path, 2 * 1024 * 1024)
        extras[path] = imp.pin(path, raw) if raw is not None else None
    require(extras[imp.PENDING] is None and extras[imp.DOC_PENDING] is None,
            "REQUALIFICATION_IMPORT_OR_DOC_PENDING")
    root_stat = root.stat()
    context = {"root": str(root), "root_device": root_stat.st_dev, "root_inode": root_stat.st_ino,
               "binding": imp.pin(binding_path, binding_raw), "state": imp.pin(imp.STATE, state_raw),
               "metadata": imp.pin(meta_path, meta_raw), "projection": imp.pin(imp.PROJECT, projection),
               "history_paths": paths, "roster_sha256": imp.sequence_sha256(rows),
               "physical": physical, "sources": source_pins, "extras": extras}
    return context, rows, b


def _unchanged(root, context, rows, b, budget):
    st = root.stat()
    require((st.st_dev, st.st_ino) == (context["root_device"], context["root_inode"]),
            "REQUALIFICATION_ROOT_CHANGED")
    require(imp.history_paths(root, b) == context["history_paths"], "REQUALIFICATION_ROSTER_DRIFT")
    for row, physical in zip(rows, context["physical"]):
        require(imp.source_stat(root, row["retained"]["path"]) == physical["retained"],
                "REQUALIFICATION_RETAINED_DRIFT")
        if row["origin"]:
            require(imp.source_stat(root, row["origin"]["path"]) == physical["source"],
                    "REQUALIFICATION_SOURCE_DRIFT")
    for path, guard in budget.guards.items():
        require(imp.source_stat(root, path) == guard, "REQUALIFICATION_CONTEXT_DRIFT")
    for path, pin in context["extras"].items():
        if pin is None:
            require(budget.optional(path, 2 * 1024 * 1024) is None, "REQUALIFICATION_PENDING_DRIFT")


def _immutable(root, path, raw):
    require(len(raw) <= MAX_META, "REQUALIFICATION_JOURNAL_LIMIT")
    directory = imp.directory(root, str(Path(path).parent), create=True)
    require(not (root / path).exists() and not (root / path).is_symlink(),
            "REQUALIFICATION_IMMUTABLE_EXISTS")
    fd, temp = tempfile.mkstemp(prefix=".rq-stage-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        # No overwrite even if a cooperating process raced the preflight.
        os.link(temp, root / path)
        nav.sync_directory(directory)
    finally:
        os.unlink(temp)
    return imp.pin(path, raw)


def _load_pin(root, pin, budget, path):
    imp.shape(pin, ("path", "bytes", "sha256"), label="requalification.pin")
    require(pin["path"] == path, "REQUALIFICATION_RECEIPT_PATH")
    raw = budget.read(root, path)
    require(imp.pin(path, raw) == pin, "REQUALIFICATION_RECEIPT_HASH")
    return nav.parse(raw)


def _progress(root, base, plan, budget, rows, context):
    head = nav.parse(budget.read(root, base + "/HEAD.json"))
    imp.shape(head, ("schema", "plan", "cursor", "pages"), label="requalification.head")
    require(head["schema"] == "atlas.history-requalification-head/v1", "REQUALIFICATION_HEAD_SCHEMA")
    require(head["plan"] == imp.pin(base + "/PLAN.json", nav.canonical(plan)), "REQUALIFICATION_PLAN_HASH")
    require(type(head["cursor"]) is int and 0 <= head["cursor"] <= len(rows), "REQUALIFICATION_CURSOR")
    require(isinstance(head["pages"], list) and len(head["pages"]) <= imp.MAX_METADATA_ROWS,
            "REQUALIFICATION_PAGE_LIMIT")
    cursor = 0
    last_start = None
    for page_pin in head["pages"]:
        path = base + "/page-" + str(cursor) + ".json"
        page = _load_pin(root, page_pin, budget, path)
        imp.shape(page, ("schema", "operation", "plan_sha256", "start", "end", "entries"), label="requalification.page")
        require(page["schema"] == "atlas.history-requalification-page/v1"
                and page["operation"] == plan["operation"] and page["plan_sha256"] == head["plan"]["sha256"],
                "REQUALIFICATION_PAGE_BINDING")
        require(type(page["start"]) is int and type(page["end"]) is int
                and page["start"] == cursor and cursor < page["end"] <= min(len(rows), cursor + MAX_PAGE_ROWS)
                and isinstance(page["entries"], list) and len(page["entries"]) == page["end"] - cursor,
                "REQUALIFICATION_PAGE_COVERAGE")
        for index, entry in enumerate(page["entries"], cursor):
            require(entry == _entry(index, rows[index], context["physical"][index]),
                    "REQUALIFICATION_PAGE_PROOF")
        last_start = cursor
        cursor = page["end"]
    require(cursor == head["cursor"], "REQUALIFICATION_CURSOR_COVERAGE")
    allowed = {"PLAN.json", "HEAD.json", "CERTIFICATE.json", *[Path(p["path"]).name for p in head["pages"]]}
    # A crash after an immutable page write but before HEAD is deliberately
    # UNKNOWN. No blind read/work replay or adoption of uncommitted artifacts.
    for entry in (root / base).iterdir():
        require(entry.name in allowed and not entry.is_symlink() and entry.is_file(),
                "REQUALIFICATION_UNKNOWN_PARTIAL_EFFECT")
    return head, last_start


def _entry(index, row, physical):
    origin = row["origin"]
    source = {"path": origin["path"], "sha256": origin["enclosing_sha256"], "bytes": origin["enclosing_bytes"]} if origin else None
    return {"index": index, "source": source, "selected_sha256": origin["selected_sha256"] if origin else None,
            "retained": row["retained"], "stat": physical}


def _certificate(plan_pin, head, context):
    return {"schema": "atlas.history-requalification-certificate/v1", "plan": plan_pin,
            "context_sha256": imp.sha(nav.canonical(context)), "row_count": len(context["physical"]),
            "pages": head["pages"], "status": "CERTIFICATE_COMPLETE"}


def _accepted_path(context):
    return BASE + "/by-generation/" + context["state"]["sha256"] + ".json"


@contextmanager
def _locks(root):
    import checkpoint
    with checkpoint._lock(root):
        try:
            fd = os.open(root / imp.LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        except FileExistsError as exc:
            raise nav.Invalid("REQUALIFICATION_IMPORT_BUSY_OR_UNKNOWN") from exc
        own = os.fstat(fd)
        os.close(fd)
        try:
            yield
        finally:
            live = (root / imp.LOCK).lstat()
            require(not (root / imp.LOCK).is_symlink() and (own.st_dev, own.st_ino) == (live.st_dev, live.st_ino),
                    "REQUALIFICATION_LOCK_CHANGED")
            (root / imp.LOCK).unlink()
            nav.sync_directory(root / ".atlas")


def _run(root, operation, binding_path, cursor, read_only):
    budget = Budget(root)
    context, rows, b = _context(root, binding_path, budget)
    base = _operation(operation)
    plan_raw = budget.optional(base + "/PLAN.json")
    if plan_raw is None:
        require(not (root / base).exists(), "REQUALIFICATION_UNKNOWN_PARTIAL_EFFECT")
        if read_only:
            _unchanged(root, context, rows, b, budget)
            return {"status": "NOT_STARTED", "operation_id": operation, "read_bytes": budget.used,
                    "read_limit": atlas.MAX_SELECTED, "publication": "NOT_RUN"}
        require(cursor == 0, "REQUALIFICATION_CURSOR")
        plan = {"schema": "atlas.history-requalification-plan/v1", "operation": operation, "context": context}
        _unchanged(root, context, rows, b, budget)
        plan_raw = nav.canonical(plan)
        plan_pin = _immutable(root, base + "/PLAN.json", plan_raw)
        head = {"schema": "atlas.history-requalification-head/v1", "plan": plan_pin, "cursor": 0, "pages": []}
        imp.atomic(root, base + "/HEAD.json", nav.canonical(head))
        last_start = None
    else:
        plan = nav.parse(plan_raw)
        imp.shape(plan, ("schema", "operation", "context"), label="requalification.plan")
        require(plan["schema"] == "atlas.history-requalification-plan/v1" and plan["operation"] == operation
                and plan["context"] == context, "REQUALIFICATION_STALE_OR_FOREIGN_PLAN")
        plan_pin = imp.pin(base + "/PLAN.json", plan_raw)
        require(plan_raw == nav.canonical(plan), "REQUALIFICATION_PLAN_ENCODING")
        head, last_start = _progress(root, base, plan, budget, rows, context)
    require(read_only or cursor in (head["cursor"], last_start), "REQUALIFICATION_CURSOR")
    completed = head["cursor"] == len(rows)
    status = "PENDING"
    if not read_only and not completed and cursor == head["cursor"]:
        start = head["cursor"]
        entries = []
        for index in range(start, min(len(rows), start + MAX_PAGE_ROWS)):
            row = rows[index]
            size = row["retained"]["bytes"] + (row["origin"]["enclosing_bytes"] if row["origin"] else 0)
            if budget.used + size > atlas.MAX_SELECTED:
                break
            origin = row["origin"]
            if origin:
                raw = budget.read(root, origin["path"])
                _, selected, observed = imp.selected_matrix(raw, origin["path"], origin["pointer"])
                require(all(observed[k] == origin[k] for k in observed), "REQUALIFICATION_SOURCE_HASH")
                require(imp.sha(selected) == row["retained"]["sha256"], "REQUALIFICATION_SELECTED_HASH")
            raw = budget.read(root, row["retained"]["path"])
            require(imp.pin(row["retained"]["path"], raw) == row["retained"], "REQUALIFICATION_RETAINED_HASH")
            entries.append(_entry(index, row, context["physical"][index]))
        require(entries, "REQUALIFICATION_NO_PAIR_FITS_BUDGET")
        _unchanged(root, context, rows, b, budget)
        end = start + len(entries)
        page = {"schema": "atlas.history-requalification-page/v1", "operation": operation,
                "plan_sha256": plan_pin["sha256"], "start": start, "end": end, "entries": entries}
        page_pin = _immutable(root, base + "/page-" + str(start) + ".json", nav.canonical(page))
        head = {**head, "cursor": end, "pages": [*head["pages"], page_pin]}
        require(len(nav.canonical(head)) <= MAX_META, "REQUALIFICATION_JOURNAL_LIMIT")
        imp.atomic(root, base + "/HEAD.json", nav.canonical(head))
        # This is our journal commit under both locks, not upstream drift.
        budget.guards.pop(base + "/HEAD.json", None)
        completed = end == len(rows)
        status = "PAGE_COMPLETE"
    elif not read_only and not completed:
        status = "PAGE_ALREADY_COMMITTED"
    _unchanged(root, context, rows, b, budget)
    if completed:
        cert = _certificate(plan_pin, head, context)
        cert_raw = nav.canonical(cert)
        path = base + "/CERTIFICATE.json"
        existing = budget.optional(path)
        if not read_only:
            if existing is None:
                cert_pin = _immutable(root, path, cert_raw)
            else:
                require(existing == cert_raw, "REQUALIFICATION_CERTIFICATE_MISMATCH")
                cert_pin = imp.pin(path, existing)
            pointer = {"schema": "atlas.history-requalification-pointer/v1", "operation": operation,
                       "certificate": cert_pin}
            accepted = budget.optional(_accepted_path(context))
            require(accepted is None or nav.parse(accepted) == pointer,
                    "REQUALIFICATION_FOREIGN_ACCEPTANCE")
            _unchanged(root, context, rows, b, budget)
            if accepted is None:
                imp.atomic(root, _accepted_path(context), nav.canonical(pointer))
            status = "CERTIFICATE_COMPLETE"
        else:
            require(existing is None or existing == cert_raw, "REQUALIFICATION_CERTIFICATE_MISMATCH")
            accepted = budget.optional(_accepted_path(context))
            expected = {"schema": "atlas.history-requalification-pointer/v1", "operation": operation,
                        "certificate": imp.pin(path, cert_raw)}
            require(accepted is None or nav.parse(accepted) == expected,
                    "REQUALIFICATION_FOREIGN_ACCEPTANCE")
            status = "CERTIFICATE_COMPLETE" if existing is not None and accepted is not None and nav.parse(accepted) == expected else "PENDING_CERTIFICATE_COMMIT"
    _unchanged(root, context, rows, b, budget)
    return {"status": status, "operation_id": operation, "cursor": head["cursor"], "row_count": len(rows),
            "read_bytes": budget.used, "read_limit": atlas.MAX_SELECTED, "publication": "NOT_RUN",
            "plan": plan_pin, "certificate": imp.pin(base + "/CERTIFICATE.json", nav.canonical(_certificate(plan_pin, head, context))) if status == "CERTIFICATE_COMPLETE" else None}


def requalify(root, operation, binding_path=".atlas/UPSTREAM.json", cursor=0, read_only=False):
    root = _root(root)
    _operation(operation)
    require(type(cursor) is int and 0 <= cursor <= imp.MAX_METADATA_ROWS, "REQUALIFICATION_CURSOR")
    require(type(read_only) is bool, "REQUALIFICATION_READ_ONLY_FLAG")
    if read_only:
        return _run(root, operation, binding_path, cursor, True)
    with _locks(root):
        return _run(root, operation, binding_path, cursor, False)


def qualified_guards(root, binding_path, preloaded):
    """No history payload reads: consume only a complete generation-bound proof."""
    budget = Budget(root)
    initial_bytes = sum(map(len, preloaded.values()))
    budget.used = initial_bytes
    require(budget.used <= atlas.MAX_SELECTED, "REQUALIFICATION_READ_BUDGET")
    # No certificate is a zero-cost legacy path apart from the bounded state read.
    state_raw = budget.optional(imp.STATE, 2 * 1024 * 1024)
    if state_raw is None:
        return {}, budget.used - initial_bytes
    path = BASE + "/by-generation/" + imp.sha(state_raw) + ".json"
    raw = budget.optional(path)
    if raw is None:
        return {}, budget.used - initial_bytes
    pointer = nav.parse(raw)
    imp.shape(pointer, ("schema", "operation", "certificate"), label="requalification.pointer")
    require(pointer["schema"] == "atlas.history-requalification-pointer/v1", "REQUALIFICATION_POINTER_SCHEMA")
    base = _operation(pointer["operation"])
    cert = _load_pin(root, pointer["certificate"], budget, base + "/CERTIFICATE.json")
    context, rows, b = _context(root, binding_path, budget, preloaded)
    plan = _load_pin(root, cert["plan"], budget, base + "/PLAN.json")
    require(plan == {"schema": "atlas.history-requalification-plan/v1", "operation": pointer["operation"], "context": context},
            "REQUALIFICATION_STALE_OR_FOREIGN_PLAN")
    head, _ = _progress(root, base, plan, budget, rows, context)
    require(head["cursor"] == len(rows) and cert == _certificate(head["plan"], head, context),
            "REQUALIFICATION_INCOMPLETE_CERTIFICATE")
    _unchanged(root, context, rows, b, budget)
    guards = dict(budget.guards)
    for row, physical in zip(rows, context["physical"]):
        guards[row["retained"]["path"]] = physical["retained"]
        if row["origin"]:
            guards[row["origin"]["path"]] = physical["source"]
    # Retain all proof dependencies through the importer's final prepublication
    # stat check, including retained-only payloads and immutable proof metadata.
    return guards, budget.used - initial_bytes
