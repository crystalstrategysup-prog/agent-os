"""Explicit native markdown-source relocation; no authority or implicit fallback.

Logical pins stay immutable. Physical storage changes only through one bounded,
source-CAS operation. This cooperates with Atlas writers, not hostile same-UID IO.
"""
from __future__ import annotations

import base64
import copy
import json
import os
import re
import shutil
import stat
import tempfile
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import navigator as nav

SCHEMA = "atlas.source-relocation/v1"
PENDING = ".atlas/SOURCE_RELOCATION_PENDING.json"
BASE = ".atlas/source-relocations"
MAX_PLAN = 16 * 1024 * 1024
MAX_ROWS = 256
OP = re.compile(r"[0-9a-f]{32}\Z")
RECONCILE_SCHEMA = "atlas.source-relocation-reconcile/v1"


def require(ok, code):
    nav.require(ok, "SOURCE_RELOCATION_" + code)


def relative(value):
    from atlas import path_text
    return path_text(value)


def _root(value):
    path = Path(value).absolute()
    require(path.is_dir() and not path.is_symlink(), "INVALID_ROOT")
    return path.resolve()


def pin(path, raw):
    return {"path": path, "sha256": nav.digest(raw), "bytes": len(raw)}


def area(op):
    require(isinstance(op, str) and OP.fullmatch(op), "OPERATION_ID")
    return BASE + "/" + op


def retained_path(op, sha):
    require(isinstance(sha, str) and nav.SHA.fullmatch(sha), "SHA")
    return area(op) + "/retained/" + sha + ".md"


class _Token:
    def __init__(self, root, op, request_sha):
        self.root = Path(root).resolve()
        self.operation_id = op
        self.request_sha256 = request_sha


def require_clear(root, token=None):
    root = Path(root).resolve()
    path = root / PENDING
    require(not path.is_symlink(), "PENDING_SYMLINK")
    if not path.exists():
        return
    value = nav.parse(nav.read_selected(root, PENDING, 16384))
    nav.shape(value, "schema operation_id request_sha256 plan_sha256", "source.pending")
    require(value["schema"] == SCHEMA, "PENDING_SCHEMA")
    require(isinstance(token, _Token) and token.root == root
            and token.operation_id == value["operation_id"]
            and token.request_sha256 == value["request_sha256"], "PENDING_RECONCILE_REQUIRED")


def request_shape(r, root=None, *, fresh=False):
    nav.shape(r, "schema operation_id root project_path output project_id writer authority_ref at valid_until expected entries", "source.request")
    require(r["schema"] == SCHEMA, "REQUEST_SCHEMA")
    area(r["operation_id"])
    require(isinstance(r["root"], str) and Path(r["root"]).is_absolute()
            and str(Path(r["root"]).resolve()) == r["root"], "ROOT")
    if root is not None:
        require(str(Path(root).resolve()) == r["root"], "ROOT_BINDING")
    for key in ("project_path", "output"):
        relative(r[key])
    nav.ident(r["project_id"])
    for key in ("writer", "authority_ref"):
        nav.text(r[key], key)
    start, end = nav.stamp(r["at"]), nav.stamp(r["valid_until"])
    require(0 < (end-start).total_seconds() <= 900, "AUTHORITY_WINDOW")
    if fresh:
        require(start <= datetime.now(timezone.utc) <= end, "EXPIRED")
    nav.shape(r["expected"], "release manifest_sha256 project_sha256 source_sha256", "source.expected")
    nav.ident(r["expected"]["release"])
    for key in ("manifest_sha256", "project_sha256", "source_sha256"):
        require(isinstance(r["expected"][key], str) and nav.SHA.fullmatch(r["expected"][key]), "SHA")
    require(isinstance(r["entries"], list) and 0 < len(r["entries"]) <= 8, "ENTRY_LIMIT")
    seen = set()
    for entry in r["entries"]:
        nav.shape(entry, "path before replacement_document replacement", "source.entry")
        relative(entry["path"])
        require(Path(entry["path"]).suffix == ".md" and entry["path"] not in seen
                and not entry["path"].startswith(".atlas/"), "ENTRY_PATH")
        seen.add(entry["path"])
        nav.shape(entry["before"], "sha256 bytes", "source.before")
        nav.shape(entry["replacement"], "path sha256 bytes", "source.replacement")
        relative(entry["replacement"]["path"])
        require(entry["replacement"]["path"] != entry["path"]
                and Path(entry["replacement"]["path"]).suffix == ".md", "REPLACEMENT_PATH")
        nav.ident(entry["replacement_document"])
        for value in (entry["before"], entry["replacement"]):
            require(isinstance(value["sha256"], str) and nav.SHA.fullmatch(value["sha256"]), "SHA")
            require(type(value["bytes"]) is int and 0 <= value["bytes"] <= nav.MAX_FILE, "BYTES")
    require(len(nav.canonical(r)) <= 65536, "REQUEST_LIMIT")


def _authorization(root, request, plan_sha, action, renewal=None, *, fresh=True):
    """A fresh explicit same-operation attestation; never renew old authority implicitly."""
    request_shape(request, root if fresh else None, fresh=fresh and renewal is None)
    if renewal is None:
        return None
    nav.shape(renewal, "schema operation_id root project_id writer authority_ref authorization_ref plan_sha256 action at valid_until expected", "source.reconcile_authority")
    require(renewal["schema"] == RECONCILE_SCHEMA and renewal["action"] == action
            and renewal["plan_sha256"] == plan_sha, "RECONCILE_AUTHORITY_SCOPE")
    require(all(renewal[k] == request[k] for k in ("operation_id", "root", "project_id", "writer", "authority_ref")), "RECONCILE_AUTHORITY_IDENTITY")
    nav.text(renewal["authorization_ref"], "source.reconcile_authority.authorization_ref")
    start, end = nav.stamp(renewal["at"]), nav.stamp(renewal["valid_until"])
    require(0 < (end - start).total_seconds() <= 900, "RECONCILE_AUTHORITY_WINDOW")
    nav.shape(renewal["expected"], "release manifest_sha256", "source.reconcile_authority.expected")
    nav.ident(renewal["expected"]["release"])
    require(isinstance(renewal["expected"]["manifest_sha256"], str)
            and nav.SHA.fullmatch(renewal["expected"]["manifest_sha256"]), "RECONCILE_AUTHORITY_PIN")
    if fresh:
        import atlas
        require(start <= datetime.now(timezone.utc) <= end, "RECONCILE_AUTHORITY_EXPIRED")
        pointer, _ = atlas.current_output(root / request["output"])
        require(pointer is not None and all(pointer[k] == v for k, v in renewal["expected"].items()), "RECONCILE_AUTHORITY_HEAD")
    return nav.digest(nav.canonical(renewal))


def _state(root, rel):
    relative(rel)
    path = root / rel
    current = root
    for part in Path(rel).parts:
        current = current / part
        require(not current.is_symlink(), "SYMLINK")
    if not path.exists():
        return None, None
    raw = nav.read_selected(root, rel, MAX_PLAN)
    mode = stat.S_IMODE(path.stat().st_mode)
    return raw, mode


def _parents(root, rel):
    current = root
    for part in Path(rel).parent.parts:
        current = current / part
        require(not current.is_symlink(), "SYMLINK")
        current.mkdir(exist_ok=True, mode=0o700)
        require(current.is_dir() and current.resolve().is_relative_to(root), "PATH_ESCAPE")


def _create(root, rel, raw, mode=0o600):
    _parents(root, rel)
    fd, temporary = tempfile.mkstemp(prefix=".source-relocation-create-", dir=(root / rel).parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        # Atomic no-replace publication: no partial request/plan/retained file.
        os.link(temporary, root / rel, follow_symlinks=False)
        nav.sync_directory((root / rel).parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _replace(root, row, *, reverse=False):
    before, after = _images(row)
    if reverse:
        before, after = after, before
    observed, mode = _state(root, row["path"])
    if observed == after and (after is None or mode == row["mode"]):
        return
    require(observed == before and (before is None or mode == row["mode"]), "CAS:" + row["path"])
    if after is None:
        # Retained objects/journals are never removed by rollback.
        require(row["kind"] == "retained", "ROLLBACK_DELETE")
        return
    if before is None:
        _create(root, row["path"], after, row["mode"])
        return
    fd, temporary = tempfile.mkstemp(prefix=".source-relocation-", dir=(root / row["path"]).parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), row["mode"])
            stream.write(after); stream.flush(); os.fsync(stream.fileno())
        require(_state(root, row["path"]) == (before, row["mode"]), "CAS:" + row["path"])
        os.replace(temporary, root / row["path"])
        nav.sync_directory((root / row["path"]).parent)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def _row(root, path, after, kind="metadata"):
    before, mode = _state(root, path)
    return {"path": path, "kind": kind, "mode": mode if mode is not None else 0o600,
            "before": None if before is None else base64.b64encode(before).decode(),
            "after": base64.b64encode(after).decode(),
            "before_sha256": None if before is None else nav.digest(before),
            "after_sha256": nav.digest(after)}


def _images(row):
    nav.shape(row, "path kind mode before after before_sha256 after_sha256", "source.row")
    relative(row["path"])
    require(row["kind"] in ("retained", "metadata", "entry")
            and type(row["mode"]) is int and 0 <= row["mode"] <= 0o777, "ROW")
    try:
        before = None if row["before"] is None else base64.b64decode(row["before"], validate=True)
        after = base64.b64decode(row["after"], validate=True)
    except (ValueError, TypeError) as exc:
        raise nav.Invalid("SOURCE_RELOCATION_ROW_ENCODING") from exc
    require((None if before is None else nav.digest(before)) == row["before_sha256"]
            and nav.digest(after) == row["after_sha256"], "ROW_HASH")
    require(len(after) <= nav.MAX_INPUT and (before is None or len(before) <= nav.MAX_INPUT), "ROW_LIMIT")
    return before, after


def _anchor(root, r):
    sha, snapshot = nav.verify_release(root / r["output"], r["expected"]["release"])
    require(sha == r["expected"]["manifest_sha256"] and "atlas" in snapshot
            and snapshot["atlas"]["project"]["id"] == r["project_id"]
            and snapshot["atlas"]["source_sha256"] == r["expected"]["source_sha256"], "ANCHOR")
    return snapshot


class Context:
    """One request/anchor read per operation per load; no implicit pin fallback."""
    def __init__(self, root, token=None):
        self.root = Path(root).resolve(); self.token = token
        require_clear(self.root, token)
        self.cache = {}; self.source_pins = {}

    def read(self, record, *, document=False, work_id=None):
        descriptor = record["storage"]
        nav.shape(descriptor, "path operation_id request_sha256", "source.storage")
        op, request_sha = descriptor["operation_id"], descriptor["request_sha256"]
        require(descriptor["path"] == retained_path(op, record["sha256"]), "STORAGE_PATH")
        key = (op, request_sha)
        if key not in self.cache:
            rel = area(op) + "/request.json"
            raw = nav.read_selected(self.root, rel, 65536)
            require(nav.digest(raw) == request_sha, "REQUEST_PIN")
            r = nav.parse(raw); request_shape(r)
            require(r["operation_id"] == op, "REQUEST_IDENTITY")
            snapshot = _anchor(self.root, r)
            staged = isinstance(self.token, _Token) and self.token.operation_id == op and self.token.request_sha256 == request_sha
            if not staged:
                receipt = nav.parse(nav.read_selected(self.root, area(op) + "/receipt.json", 65536))
                require(receipt.get("schema") == SCHEMA and receipt.get("status") == "COMMITTED"
                        and receipt.get("request_sha256") == request_sha, "NOT_COMMITTED")
                plan_raw = nav.read_selected(self.root, area(op) + "/plan.json", MAX_PLAN)
                require(nav.digest(plan_raw) == receipt.get("plan_sha256"), "PLAN_PIN")
                saved_plan = nav.parse(plan_raw)
                require(saved_plan["request"] == r, "REQUEST_PIN")
                _receipt(receipt, saved_plan)
                _validate_rows(saved_plan, snapshot)
                renewal_sha = receipt.get("reconcile_authority_sha256")
                if renewal_sha is not None:
                    renewal_raw = nav.read_selected(self.root, area(op) + "/authorities/" + renewal_sha + ".json", 65536)
                    require(nav.digest(renewal_raw) == renewal_sha, "RECEIPT_AUTHORITY_PIN")
                    _authorization(self.root, r, receipt["plan_sha256"], "resume", nav.parse(renewal_raw), fresh=False)
                result_sha, _ = nav.verify_release(self.root / r["output"], receipt["release"])
                require(result_sha == receipt["manifest_sha256"], "RESULT_RELEASE")
            self.cache[key] = r, snapshot
            self.source_pins[rel] = raw
        r, snapshot = self.cache[key]
        entries = [e for e in r["entries"] if e["path"] == record["path"]
                   and e["before"] == {"sha256": record["sha256"], "bytes": record["bytes"]}]
        require(len(entries) == 1, "STORAGE_SUBJECT")
        if document:
            require(record["lifecycle"] == "archived", "STORAGE_CURRENT_DOCUMENT")
            old = next((d for d in snapshot["input"]["documents"] if d["id"] == record["id"]), None)
            omitted = {"storage", "lifecycle"}
        else:
            work = next((w for w in snapshot["atlas"]["works"] if w["id"] == work_id), None)
            require(work is not None, "STORAGE_WORK")
            old = next((a for a in work["artifacts"] if a["id"] == record["id"]), None)
            omitted = {"storage"}
        require(old is not None and "storage" not in old
                and {k:v for k,v in old.items() if k not in omitted}
                == {k:v for k,v in record.items() if k not in omitted}, "STORAGE_IDENTITY")
        raw = nav.read_selected(self.root, descriptor["path"], nav.MAX_FILE)
        require(len(raw) == record["bytes"] and nav.digest(raw) == record["sha256"], "STORAGE_HASH")
        self.source_pins[descriptor["path"]] = raw
        return raw, descriptor["path"]


def _compose(root, r, snapshot):
    import atlas
    project = nav.parse(nav.read_selected(root, r["project_path"], 512*1024))
    require(project["mode"] == "native" and project["id"] == r["project_id"], "NATIVE_PROJECT")
    require(project["writer"] == r["writer"] and project["authority_ref"] == r["authority_ref"], "WRITER_AUTHORITY")
    require(nav.digest(nav.read_selected(root, r["project_path"], 512*1024)) == r["expected"]["project_sha256"], "PROJECT_CAS")
    docs_path = project["documents"]["path"]
    model = nav.parse(nav.read_selected(root, docs_path, nav.MAX_INPUT))
    docs = {d["id"]:d for d in model["documents"]}
    works = {rel: nav.parse(nav.read_selected(root, rel)) for rel in project["work_files"]}
    rows = []; retained = {}; touched = set(); changed_works = set()
    request_sha = nav.digest(nav.canonical(r))
    for ordinal, entry in enumerate(r["entries"]):
        old_raw, mode = _state(root, entry["path"])
        require(old_raw is not None and pin(entry["path"], old_raw) == {"path":entry["path"], **entry["before"]}, "ENTRY_CAS")
        replacement = nav.read_selected(root, entry["replacement"]["path"])
        require(pin(entry["replacement"]["path"], replacement) == entry["replacement"], "REPLACEMENT_PIN")
        require(replacement != old_raw, "NO_CHANGE")
        current = docs.get(entry["replacement_document"])
        require(current is not None and current["lifecycle"] == "current" and current["kind"] == "markdown"
                and all(current[k] == entry["replacement"][k] for k in ("path","sha256","bytes"))
                and "storage" not in current, "CURRENT_REPLACEMENT")
        path = retained_path(r["operation_id"], entry["before"]["sha256"])
        storage = {"path":path,"operation_id":r["operation_id"],"request_sha256":request_sha}
        require(_state(root, path)[0] is None, "RETAINED_EXISTS")
        retained[path] = old_raw
        count = 0
        for document in model["documents"]:
            if document["path"] != entry["path"] or "storage" in document:
                continue
            require(document["kind"] == "markdown" and document["sha256"] == entry["before"]["sha256"]
                    and document["bytes"] == len(old_raw), "DOCUMENT_CLOSURE")
            document["lifecycle"] = "archived"; document["storage"] = storage.copy()
            touched.add(document["id"]); count += 1
        require(count > 0, "NO_PINNED_DOCUMENT")
        for rel, work in works.items():
            for ev in work["evidence"]:
                require(ev["receipt"]["path"] != entry["path"], "UNSUPPORTED_RECEIPT_CONSUMER")
            for artifact in work["artifacts"]:
                if artifact["path"] != entry["path"] or "storage" in artifact:
                    continue
                require(work["writer"] == r["writer"], "WORK_WRITER")
                require(artifact["sha256"] == entry["before"]["sha256"] and artifact["bytes"] == len(old_raw), "ARTIFACT_CLOSURE")
                artifact["storage"] = storage.copy(); changed_works.add(rel)
        alias = copy.deepcopy(current)
        alias.update(id="ENTRY-"+r["operation_id"]+"-"+str(ordinal),path=entry["path"],readback_at=r["at"],
                     source_ref="atlas.source-entry-copy/v1:"+current["id"])
        require(alias["id"] not in docs, "ALIAS_COLLISION")
        model["documents"].append(alias); touched.add(alias["id"]); docs[alias["id"]] = alias
        rows.append(_row(root, entry["path"], replacement, "entry"))
    for path, raw in sorted(retained.items()):
        rows.insert(0, _row(root, path, raw, "retained"))
    for rel in sorted(changed_works):
        work = works[rel]
        work["events"].append({"id":"SRC-"+r["operation_id"],"at":r["at"],"actor":r["writer"],
                               "kind":"RESULT","summary":"Preserve exact historical source bytes; logical pins, acceptance and activity unchanged.","evidence_ids":[]})
        rows.append(_row(root, rel, nav.canonical(work)))
    old_input_sha = nav.digest(nav.read_selected(root, docs_path, nav.MAX_INPUT))
    model["release"] = {"id":"DN-SRC-"+r["operation_id"],"created_at":r["at"],"previous":old_input_sha}
    model["history"].append({"id":"SRC-"+r["operation_id"],"at":r["at"],"kind":"SOURCE_RELOCATED",
                             "summary":"Retained exact historical source bytes and updated explicit current entry aliases.","entity_ids":sorted(touched)})
    docs_raw = nav.canonical(model)
    rows.append(_row(root, docs_path, docs_raw))
    project["documents"] = pin(docs_path, docs_raw)
    rows.append(_row(root, r["project_path"], nav.canonical(project)))
    require(len(rows) <= MAX_ROWS and len({row["path"] for row in rows}) == len(rows), "ROW_CLOSURE")
    return rows


def _preview_copy(root, destination, rel, budget):
    raw = nav.read_selected(root, rel, nav.MAX_HTML)
    existing, _ = _state(destination, rel)
    if existing is not None:
        require(existing == raw, "PREVIEW_DEPENDENCY_CONFLICT")
        return
    # Reuse the existing source/snapshot/HTML envelopes as one finite preview
    # budget. No entire history scan or persistent snapshot copy is introduced.
    import atlas
    budget[0] += len(raw)
    require(budget[0] <= atlas.MAX_SELECTED + nav.MAX_SNAPSHOT + nav.MAX_HTML, "PREVIEW_TOTAL_LIMIT")
    _create(destination, rel, raw)


def _copy_anchor(root, destination, r, *, pointer=True, budget=None):
    budget = budget if budget is not None else [0]
    for name in ("MANIFEST.json", "snapshot.json", "index.html"):
        rel = r["output"]+"/releases/"+r["expected"]["release"]+"/"+name
        _preview_copy(root, destination, rel, budget)
    if pointer:
        _preview_copy(root, destination, r["output"] + "/CURRENT.json", budget)


def _copy_dependencies(root, destination, snapshot, budget):
    records = list(snapshot["input"]["documents"])
    records.extend(a for work in snapshot["atlas"]["works"] for a in work["artifacts"])
    operations = {}
    for record in records:
        if "storage" in record:
            storage = record["storage"]
            op = storage["operation_id"]
            require(op not in operations or operations[op] == storage["request_sha256"], "PREVIEW_DEPENDENCY_IDENTITY")
            operations[op] = storage["request_sha256"]
    require(len(operations) <= MAX_ROWS, "PREVIEW_DEPENDENCY_LIMIT")
    for op, expected in sorted(operations.items()):
        base = area(op)
        raw = nav.read_selected(root, base + "/request.json", 65536)
        require(nav.digest(raw) == expected, "PREVIEW_DEPENDENCY_PIN")
        r = nav.parse(raw); request_shape(r)
        require(r["operation_id"] == op, "PREVIEW_DEPENDENCY_IDENTITY")
        for name in ("request.json", "plan.json", "receipt.json"):
            _preview_copy(root, destination, base + "/" + name, budget)
        receipt = nav.parse(nav.read_selected(root, base + "/receipt.json", 65536))
        require(receipt.get("status") == "COMMITTED", "PREVIEW_DEPENDENCY_NOT_COMMITTED")
        renewal = receipt.get("reconcile_authority_sha256")
        if renewal is not None:
            require(isinstance(renewal, str) and nav.SHA.fullmatch(renewal), "RECEIPT_AUTHORITY_PIN")
            _preview_copy(root, destination, base + "/authorities/" + renewal + ".json", budget)
        _copy_anchor(root, destination, r, pointer=False, budget=budget)
        for name in ("MANIFEST.json", "snapshot.json", "index.html"):
            _preview_copy(root, destination, r["output"] + "/releases/" + receipt["release"] + "/" + name, budget)


def plan(root, r, *, _renewal=None, _plan_sha=None, _action="resume"):
    import atlas
    root = _root(root); _authorization(root,r,_plan_sha,_action,_renewal); require_clear(root)
    require(_state(root,area(r["operation_id"])+"/plan.json")[0] is None, "EXISTING_OPERATION_RECONCILE")
    pointer, previous = atlas.current_output(root/r["output"])
    require(pointer and pointer["release"] == r["expected"]["release"]
            and pointer["manifest_sha256"] == r["expected"]["manifest_sha256"], "CURRENT_CAS")
    snapshot = atlas.load_project(root,r["project_path"],at=r["at"])
    require(snapshot["atlas"]["source_sha256"] == r["expected"]["source_sha256"], "SOURCE_CAS")
    require(previous["atlas"]["source_sha256"] == r["expected"]["source_sha256"], "SOURCE_NOT_PUBLISHED")
    rows = _compose(root,r,snapshot)
    value = {"schema":SCHEMA,"request":r,"request_sha256":nav.digest(nav.canonical(r)),"rows":rows,"preview":None,"guard_pins":None,"toolchain_sha256":None}
    require(len(nav.canonical(value)) <= MAX_PLAN, "PLAN_LIMIT")
    # No input/project mutation: selected bodies and one immutable anchor only.
    with tempfile.TemporaryDirectory(prefix="atlas-source-relocation-preview-") as temporary:
        staged = Path(temporary).resolve()
        for item in snapshot["atlas"]["source_pins"]:
            raw = nav.read_selected(root,item["path"],8*1024*1024)
            require(pin(item["path"],raw) == item, "SOURCE_CHANGED_DURING_PLAN")
            _create(staged,item["path"],raw,stat.S_IMODE((root/item["path"]).stat().st_mode))
        budget = [sum(item["bytes"] for item in snapshot["atlas"]["source_pins"])]
        _copy_anchor(root,staged,r,budget=budget)
        _copy_dependencies(root,staged,snapshot,budget)
        _create(staged,area(r["operation_id"])+"/request.json",nav.canonical(r))
        for row in rows:
            _replace(staged,row)
        pending={"schema":SCHEMA,"operation_id":r["operation_id"],"request_sha256":value["request_sha256"],"plan_sha256":"0"*64}
        _create(staged,PENDING,nav.canonical(pending))
        token=_Token(staged,r["operation_id"],value["request_sha256"])
        result=atlas.cycle(staged,r["project_path"],staged/r["output"],release="ATLAS-SRC-"+r["operation_id"],at=r["at"],previous=r["expected"]["manifest_sha256"],_source_operation=token)
        _, final=atlas.current_output(staged/r["output"])
        value["preview"]={"release":result["release"],"manifest_sha256":result["manifest_sha256"],"source_sha256":final["atlas"]["source_sha256"],"snapshot_sha256":nav.digest(nav.canonical(final))}
        value["guard_pins"] = final["atlas"]["source_pins"]
        value["toolchain_sha256"] = final["atlas"]["toolchain_sha256"]
    for row in rows:
        before,_=_images(row)
        require(_state(root,row["path"])[0] == before,"SOURCE_CHANGED_DURING_PLAN")
    require(len(nav.canonical(value)) <= MAX_PLAN,"PLAN_LIMIT")
    _validate_rows(value, snapshot)
    return value


def _load_plan(root, op, expected_sha):
    raw=nav.read_selected(root,area(op)+"/plan.json",MAX_PLAN)
    require(nav.digest(raw)==expected_sha,"PLAN_PIN")
    value=nav.parse(raw)
    nav.shape(value,"schema request request_sha256 rows preview guard_pins toolchain_sha256","source.plan")
    require(value["schema"]==SCHEMA and value["request"]["operation_id"]==op,"PLAN_IDENTITY")
    request_shape(value["request"],root)
    require(nav.digest(nav.canonical(value["request"]))==value["request_sha256"],"REQUEST_PIN")
    require(nav.read_selected(root,area(op)+"/request.json",65536)==nav.canonical(value["request"]),"REQUEST_PIN")
    require(isinstance(value["rows"],list) and 0<len(value["rows"])<=MAX_ROWS,"ROW_LIMIT")
    seen=set()
    anchor=_anchor(root,value["request"])
    allowed={p["path"] for p in anchor["atlas"]["source_pins"]}
    for row in value["rows"]:
        _images(row);require(row["path"] not in seen,"DUPLICATE_ROW");seen.add(row["path"])
        require(row["path"] in allowed or row["kind"]=="retained" and row["path"]==retained_path(op,row["after_sha256"]),"ROW_SCOPE")
    _validate_rows(value, anchor)
    return value


def _validate_rows(value, anchor):
    """Re-derive the sole permitted transition, never trust arbitrary row writes."""
    r = value["request"]
    rows = {row["path"]: row for row in value["rows"]}
    pins = {item["path"]: item for item in anchor["atlas"]["source_pins"]}
    require(r["project_path"] in rows, "PLAN_PROJECT_ROW")
    before, _ = _images(rows[r["project_path"]])
    require(before is not None and nav.digest(before) == r["expected"]["project_sha256"], "PLAN_PROJECT_PIN")
    project = nav.parse(before)
    require(project == anchor["atlas"]["project"], "PLAN_PROJECT_IDENTITY")
    require(project["writer"] == r["writer"] and project["authority_ref"] == r["authority_ref"], "WRITER_AUTHORITY")
    images = {}
    for row in value["rows"]:
        before, _ = _images(row)
        if before is not None:
            require(row["path"] in pins and pin(row["path"], before) == pins[row["path"]], "PLAN_BEFORE_PIN")
            images[row["path"]] = (before, row["mode"])
        else:
            require(row["kind"] == "retained", "PLAN_NEW_SOURCE_ROW")
    works = anchor["atlas"]["works"]
    require(len(works) == len(project["work_files"]), "PLAN_WORK_CLOSURE")
    work_paths = anchor["atlas"]["work_paths"]
    require(set(work_paths.values()) == set(project["work_files"]), "PLAN_WORK_CLOSURE")
    for work in works:
        require(work["id"] in work_paths, "PLAN_WORK_CLOSURE")
        path = work_paths[work["id"]]
        original = {k: v for k, v in work.items() if k != "derived"}
        if path in images:
            require(nav.parse(images[path][0]) == original, "PLAN_WORK_IDENTITY")
        else:
            images[path] = (nav.canonical(original), 0o600)
    for entry in r["entries"]:
        require(entry["path"] in rows and rows[entry["path"]]["kind"] == "entry", "PLAN_ENTRY_ROW")
        before, after = _images(rows[entry["path"]])
        require(before is not None and pin(entry["path"], before) == {"path": entry["path"], **entry["before"]}
                and pin(entry["replacement"]["path"], after) == entry["replacement"], "PLAN_ENTRY_PIN")
        replacement_path = entry["replacement"]["path"]
        require(replacement_path not in images or images[replacement_path][0] == after, "PLAN_IMAGE_CONFLICT")
        images[replacement_path] = (after, 0o600)
    with tempfile.TemporaryDirectory(prefix="atlas-relocation-row-proof-") as directory:
        staged = Path(directory).resolve()
        for path, (raw, mode) in images.items():
            _create(staged, path, raw, mode)
        derived = _compose(staged, r, anchor)
        require(nav.canonical(derived) == nav.canonical(value["rows"]), "PLAN_TRANSITION")
    preview = value["preview"]
    nav.shape(preview, "release manifest_sha256 source_sha256 snapshot_sha256", "source.preview")
    require(preview["release"] == "ATLAS-SRC-" + r["operation_id"], "PREVIEW_IDENTITY")
    require(all(isinstance(preview[k], str) and nav.SHA.fullmatch(preview[k])
                for k in ("manifest_sha256", "source_sha256", "snapshot_sha256")), "PREVIEW_PIN")
    guards = {item["path"]: item for item in anchor["atlas"]["source_pins"]}
    after_project = None
    for row in value["rows"]:
        _, after = _images(row)
        guards[row["path"]] = pin(row["path"], after)
        if row["path"] == r["project_path"]:
            after_project = nav.parse(after)
    request_path = area(r["operation_id"]) + "/request.json"
    guards[request_path] = pin(request_path, nav.canonical(r))
    guard_pins = [item for _, item in sorted(guards.items())]
    require(value["guard_pins"] == guard_pins, "PLAN_GUARD_CLOSURE")
    require(preview["source_sha256"] == nav.digest(nav.canonical({"project": after_project, "source_pins": guard_pins})), "PLAN_SOURCE_DIGEST")
    require(isinstance(value["toolchain_sha256"], str) and nav.SHA.fullmatch(value["toolchain_sha256"]), "PLAN_TOOLCHAIN_PIN")


def _check_pins(root, pins):
    for item in pins:
        raw = nav.read_selected(root, item["path"], nav.MAX_INPUT)
        require(pin(item["path"], raw) == item, "SELECTED_SOURCE_CHANGED:" + item["path"])


def _receipt(value, plan):
    common = "schema status operation_id request_sha256 plan_sha256"
    require(isinstance(value, dict) and value.get("status") in ("COMMITTED", "ROLLED_BACK_UNPUBLISHED"), "RECEIPT_SCHEMA")
    extra = " release manifest_sha256 source_sha256 snapshot_sha256 semantic_acceptance activity_renewed authority_granted" if value["status"] == "COMMITTED" else " retained_objects_kept"
    if "reconcile_authority_sha256" in value:
        extra += " reconcile_authority_sha256"
        require(isinstance(value["reconcile_authority_sha256"], str)
                and nav.SHA.fullmatch(value["reconcile_authority_sha256"]), "RECEIPT_AUTHORITY_PIN")
    nav.shape(value, common + extra, "source.receipt")
    require(value["schema"] == SCHEMA and value["operation_id"] == plan["request"]["operation_id"]
            and value["request_sha256"] == plan["request_sha256"]
            and value["plan_sha256"] == nav.digest(nav.canonical(plan)), "RECEIPT_IDENTITY")
    if value["status"] == "COMMITTED":
        require(all(value[k] == v for k, v in plan["preview"].items())
                and all(value[k] is False for k in ("semantic_acceptance", "activity_renewed", "authority_granted")), "RECEIPT_RESULT")
    else:
        require(value["retained_objects_kept"] is True, "RECEIPT_RESULT")
    return value


def _states(root, value):
    rows=[]
    for row in value["rows"]:
        before,after=_images(row);raw,mode=_state(root,row["path"])
        state="BEFORE" if raw==before and (raw is None or mode==row["mode"]) else "AFTER" if raw==after and mode==row["mode"] else "CONFLICT"
        rows.append({"path":row["path"],"state":state})
    return rows


def status(root, op, expected_sha):
    root=_root(root)
    require(isinstance(expected_sha, str) and nav.SHA.fullmatch(expected_sha), "PLAN_PIN")
    if _state(root, area(op) + "/plan.json")[0] is None:
        raw = nav.read_selected(root, area(op) + "/request.json", 65536)
        r = nav.parse(raw); request_shape(r, root)
        require(r["operation_id"] == op, "REQUEST_IDENTITY")
        return {"schema": SCHEMA, "status": "PREPARATION_INCOMPLETE", "operation_id": op, "phase": "PREPARATION_INCOMPLETE",
                "request_sha256": nav.digest(raw), "requested_plan_sha256": expected_sha,
                "pending": (root/PENDING).exists(), "effects": "NONE_READ_ONLY"}
    value=_load_plan(root,op,expected_sha)
    receipt_path=area(op)+"/receipt.json";raw,_=_state(root,receipt_path)
    return {"schema":SCHEMA,"status":"OBSERVED","operation_id":op,"plan_sha256":expected_sha,"pending":(root/PENDING).exists(),
            "receipt":None if raw is None else _receipt(nav.parse(raw), value),"files":_states(root,value),"effects":"NONE_READ_ONLY"}


class _OrphanProof:
    """A live exact-operation proof; no JSON flag relaxes general publication."""
    def __init__(self, root, value, plan_sha, lease, renewal=None):
        self.root, self.value, self.plan_sha, self.lease = root, value, plan_sha, lease
        self.renewal = renewal

    def check(self, output, snapshot, release, manifest_sha, previous_sha):
        r = self.value["request"]
        self.lease.check(output)
        require(Path(output).resolve() == self.root / r["output"], "ORPHAN_OUTPUT")
        _authorization(self.root, r, self.plan_sha, "resume", self.renewal)
        verified = _load_plan(self.root, r["operation_id"], self.plan_sha)
        require(verified == self.value, "ORPHAN_PLAN")
        require_clear(self.root, _Token(self.root, r["operation_id"], self.value["request_sha256"]))
        require(all(x["state"] == "AFTER" for x in _states(self.root, self.value)), "ORPHAN_SOURCE")
        preview = self.value["preview"]
        require(previous_sha == r["expected"]["manifest_sha256"]
                and release == preview["release"] and manifest_sha == preview["manifest_sha256"]
                and snapshot["atlas"]["toolchain_sha256"] == self.value["toolchain_sha256"]
                and nav.digest(nav.canonical(snapshot)) == preview["snapshot_sha256"], "ORPHAN_PREVIEW")


def _continuation_sources(root, value):
    """Check exact source/code/head before reserving or changing recovery state."""
    import atlas
    r = value["request"]
    require(atlas.toolchain_digest() == value["toolchain_sha256"], "TOOLCHAIN_CHANGED")
    observed=_states(root,value);require(all(x["state"]!="CONFLICT" for x in observed),"CONFLICT")
    affected = {row["path"] for row in value["rows"]}
    anchor = _anchor(root, r)
    _check_pins(root, [p for p in anchor["atlas"]["source_pins"] if p["path"] not in affected])
    pointer,_=atlas.current_output(root/r["output"])
    preview=value["preview"]
    before_head=pointer["manifest_sha256"]==r["expected"]["manifest_sha256"]
    after_head=pointer["manifest_sha256"]==preview["manifest_sha256"] and pointer["release"]==preview["release"]
    require(before_head or after_head,"CURRENT_CAS")
    return observed, before_head, after_head


def _pending_identity(root, value, plan_sha):
    raw = nav.read_selected(root, PENDING, 16384)
    expected = {"schema": SCHEMA, "operation_id": value["request"]["operation_id"],
                "request_sha256": value["request_sha256"], "plan_sha256": plan_sha}
    require(nav.parse(raw) == expected, "PENDING_IDENTITY")
    return raw


def _terminal_receipt(root, value, raw, *, rollback=False):
    """Validate a durable result for cleanup, never reconstruct or replay it."""
    import atlas
    result = _receipt(nav.parse(raw), value)
    r = value["request"]
    renewal_sha = result.get("reconcile_authority_sha256")
    if renewal_sha is not None:
        authority_raw = nav.read_selected(root, area(r["operation_id"]) + "/authorities/" + renewal_sha + ".json", 65536)
        require(nav.digest(authority_raw) == renewal_sha, "RECEIPT_AUTHORITY_PIN")
        _authorization(root, r, result["plan_sha256"],
                       "resume" if result["status"] == "COMMITTED" else "rollback",
                       nav.parse(authority_raw), fresh=False)
    observed, before_head, after_head = _continuation_sources(root, value)
    if result["status"] == "COMMITTED":
        require(not rollback, "PUBLISHED_ROLLBACK_REQUIRES_SUCCESSOR")
        require(after_head and all(item["state"] == "AFTER" for item in observed), "TERMINAL_COMMITTED_STATE")
        _check_pins(root, value["guard_pins"])
        _, snapshot = atlas.current_output(root / r["output"])
        require(snapshot["atlas"]["source_sha256"] == result["source_sha256"]
                and nav.digest(nav.canonical(snapshot)) == result["snapshot_sha256"], "RESULT_READBACK")
    else:
        require(before_head and all(item["state"] == "BEFORE" or row["kind"] == "retained"
                                    for item, row in zip(observed, value["rows"])), "TERMINAL_ROLLBACK_STATE")
        _check_pins(root, _anchor(root, r)["atlas"]["source_pins"])
    return result


def _clear_pending(root, value, plan_sha, lease):
    raw = _pending_identity(root, value, plan_sha)
    lease.check(root / value["request"]["output"])
    require(_state(root, PENDING)[0] == raw, "PENDING_CHANGED")
    (root / PENDING).unlink()
    nav.sync_directory((root / PENDING).parent)


def _finish(root,value,plan_sha,lease,*,rollback=False,reconciling=False,renewal=None):
    import atlas
    r=value["request"];op=r["operation_id"]
    action = "rollback" if rollback else "resume"
    renewal_sha = _authorization(root, r, plan_sha, action, renewal)
    token=_Token(root,op,value["request_sha256"])
    require_clear(root,token)
    observed, before_head, after_head = _continuation_sources(root, value)
    preview = value["preview"]
    existing, _ = _state(root, area(op) + "/receipt.json")
    if existing is not None:
        # Fresh cleanup permission is retained separately by reconcile. The
        # durable result, including its original authority pin, is immutable.
        result = _terminal_receipt(root, value, existing, rollback=rollback)
        require(_state(root, area(op) + "/receipt.json")[0] == existing, "RECEIPT_CONFLICT")
        _clear_pending(root, value, plan_sha, lease)
        return {**result, "replayed": False}
    if rollback:
        require(before_head,"PUBLISHED_ROLLBACK_REQUIRES_SUCCESSOR")
        for row in reversed(value["rows"]):
            _authorization(root, r, plan_sha, action, renewal)
            _replace(root,row,reverse=True)
        result={"schema":SCHEMA,"status":"ROLLED_BACK_UNPUBLISHED","operation_id":op,"request_sha256":value["request_sha256"],"plan_sha256":plan_sha,"retained_objects_kept":True}
    else:
        if after_head:
            require(all(x["state"]=="AFTER" for x in observed),"COMMITTED_SOURCE_CHANGED")
        else:
            for row in value["rows"]:
                _authorization(root, r, plan_sha, action, renewal);_replace(root,row)
            require(all(x["state"]=="AFTER" for x in _states(root,value)),"READBACK")
            def guard():
                _authorization(root, r, plan_sha, action, renewal)
                require(all(x["state"]=="AFTER" for x in _states(root,value)),"SOURCE_CHANGED_BEFORE_PUBLISH")
                require(atlas.toolchain_digest() == value["toolchain_sha256"], "TOOLCHAIN_CHANGED")
                _check_pins(root, value["guard_pins"])
            proof = _OrphanProof(root, value, plan_sha, lease, renewal) if reconciling else None
            published=atlas.cycle(root,r["project_path"],root/r["output"],release=preview["release"],at=r["at"],previous=r["expected"]["manifest_sha256"],_source_operation=token,_writer_lease=lease,_source_guard=guard,_source_orphan=proof)
            require(published["manifest_sha256"]==preview["manifest_sha256"],"PREVIEW_RESULT_MISMATCH")
        _,snapshot=atlas.current_output(root/r["output"])
        require(snapshot["atlas"]["source_sha256"]==preview["source_sha256"] and nav.digest(nav.canonical(snapshot))==preview["snapshot_sha256"],"RESULT_READBACK")
        result={"schema":SCHEMA,"status":"COMMITTED","operation_id":op,"request_sha256":value["request_sha256"],"plan_sha256":plan_sha,**preview,"semantic_acceptance":False,"activity_renewed":False,"authority_granted":False}
    if renewal_sha is not None:
        result["reconcile_authority_sha256"] = renewal_sha
    rel=area(op)+"/receipt.json";existing,_=_state(root,rel)
    if existing is None:_create(root,rel,nav.canonical(result))
    else:require(existing==nav.canonical(result),"RECEIPT_CONFLICT")
    _clear_pending(root, value, plan_sha, lease)
    return result


def apply(root,r,expected_plan_sha):
    root=_root(root);request_shape(r,root,fresh=True)
    require(not(root/area(r["operation_id"])).exists(),"EXISTING_OPERATION_RECONCILE")
    value=plan(root,r);raw=nav.canonical(value)
    require(nav.digest(raw)==expected_plan_sha,"EXPECTED_PLAN_CHANGED")
    lease=nav._PublishLease(root/r["output"]);lease.acquire()
    try:
        # Recheck every preimage and head under the actual existing publisher lock.
        import atlas
        pointer,_=atlas.current_output(root/r["output"])
        require(pointer["manifest_sha256"]==r["expected"]["manifest_sha256"],"CURRENT_CAS")
        require(all(x["state"]=="BEFORE" for x in _states(root,value)),"SOURCE_CAS")
        require(atlas.toolchain_digest() == value["toolchain_sha256"], "TOOLCHAIN_CHANGED")
        _check_pins(root, _anchor(root, r)["atlas"]["source_pins"])
        lease.tag({"schema":SCHEMA,"operation_id":r["operation_id"],"plan_sha256":expected_plan_sha,"pid":os.getpid()})
        _create(root,area(r["operation_id"])+"/request.json",nav.canonical(r))
        _create(root,area(r["operation_id"])+"/plan.json",raw)
        pending={"schema":SCHEMA,"operation_id":r["operation_id"],"request_sha256":value["request_sha256"],"plan_sha256":expected_plan_sha}
        _create(root,PENDING,nav.canonical(pending))
        return _finish(root,value,expected_plan_sha,lease)
    finally:lease.release()


def reconcile(root,op,expected_plan_sha,*,rollback=False,stale_lock_sha256=None,preparation_request=None,renewal=None):
    import atlas
    root=_root(root)
    require(isinstance(expected_plan_sha, str) and nav.SHA.fullmatch(expected_plan_sha), "PLAN_PIN")
    if _state(root, area(op) + "/plan.json")[0] is None:
        require(not (root/PENDING).exists() and _state(root, area(op) + "/receipt.json")[0] is None,
                "MISSING_RESERVED_PLAN")
        stored, _ = _state(root, area(op) + "/request.json")
        require(stored is not None or preparation_request is not None, "PREPARATION_REQUEST_REQUIRED")
        r = nav.parse(stored) if stored is not None else preparation_request
        _authorization(root, r, expected_plan_sha, "rollback" if rollback else "resume", renewal)
        require(r["operation_id"] == op and (preparation_request is None or preparation_request == r), "REQUEST_IDENTITY")
        directory = root / area(op)
        if directory.exists():
            nav.safe(root, area(op), directory=True)
            require(set(p.name for p in directory.iterdir()) <= {"request.json"}, "PREPARATION_FOREIGN_CONTENT")
        value = None
    else:
        value=_load_plan(root,op,expected_plan_sha);r=value["request"]
    receipt,_=_state(root,area(op)+"/receipt.json")
    if receipt is not None and not(root/PENDING).exists():
        result=_receipt(nav.parse(receipt), value)
        require(result.get("plan_sha256")==expected_plan_sha,"RECEIPT_CONFLICT")
        require(not rollback or result.get("status") != "COMMITTED", "PUBLISHED_ROLLBACK_REQUIRES_SUCCESSOR")
        # Historical committed operations are never replayed or made current again.
        if result["status"]=="COMMITTED":
            sha,_=nav.verify_release(root/r["output"],result["release"])
            require(sha==result["manifest_sha256"],"RESULT_RELEASE")
        return {**result,"replayed":False}
    if (root / PENDING).exists():
        _pending_identity(root, value, expected_plan_sha)
    if receipt is not None:
        _terminal_receipt(root, value, receipt, rollback=rollback)
    renewal_sha = _authorization(root, r, expected_plan_sha, "rollback" if rollback else "resume", renewal)
    if value is not None:
        _continuation_sources(root, value)
    lock_rel=r["output"]+"/.writer.lock"
    lock_raw,_=_state(root,lock_rel)
    if lock_raw is not None:
        require(stale_lock_sha256 is not None and nav.digest(lock_raw)==stale_lock_sha256,"STALE_LOCK_EXACT_QUALIFICATION_REQUIRED")
        tag=nav.parse(lock_raw);nav.shape(tag,"schema operation_id plan_sha256 pid","source.lock")
        require(tag["schema"]==SCHEMA and tag["operation_id"]==op and tag["plan_sha256"]==expected_plan_sha
                and type(tag["pid"])is int and tag["pid"]>0,"STALE_LOCK_IDENTITY")
        try:os.kill(tag["pid"],0)
        except ProcessLookupError:pass
        except OSError as exc:raise nav.Invalid("SOURCE_RELOCATION_LOCK_OWNER_UNKNOWN") from exc
        else:require(False,"LOCK_OWNER_ACTIVE")
        before=(root/lock_rel).lstat()
        require(_state(root,lock_rel)[0]==lock_raw and (root/lock_rel).lstat()==before,"STALE_LOCK_CHANGED")
        (root/lock_rel).unlink();nav.sync_directory((root/lock_rel).parent)
    lease=nav._PublishLease(root/r["output"]);lease.acquire()
    try:
        lease.tag({"schema":SCHEMA,"operation_id":op,"plan_sha256":expected_plan_sha,"pid":os.getpid()})
        if value is None:
            # Preparation had no source effects. Rebuild from the original exact
            # request only while its head/source/authority still match.
            value = plan(root, r, _renewal=renewal, _plan_sha=expected_plan_sha,
                         _action="rollback" if rollback else "resume")
            require(nav.digest(nav.canonical(value)) == expected_plan_sha, "EXPECTED_PLAN_CHANGED")
            stored, _ = _state(root, area(op) + "/request.json")
            if stored is None:
                _create(root, area(op) + "/request.json", nav.canonical(r))
            else:
                require(stored == nav.canonical(r), "REQUEST_PIN")
            _create(root, area(op) + "/plan.json", nav.canonical(value))
            value = _load_plan(root, op, expected_plan_sha)
        _continuation_sources(root, value)
        require(_state(root, area(op) + "/receipt.json")[0] == receipt, "RECEIPT_CONFLICT")
        if receipt is not None:
            _terminal_receipt(root, value, receipt, rollback=rollback)
        if renewal_sha is not None:
            rel = area(op) + "/authorities/" + renewal_sha + ".json"
            raw, _ = _state(root, rel)
            if raw is None:
                _create(root, rel, nav.canonical(renewal))
            else:
                require(raw == nav.canonical(renewal), "RECONCILE_AUTHORITY_PIN")
        if not(root/PENDING).exists():
            pointer,_=atlas.current_output(root/r["output"])
            require(pointer["manifest_sha256"]==r["expected"]["manifest_sha256"]
                    and all(x["state"]=="BEFORE" for x in _states(root,value)),"UNRESERVED_STATE_CHANGED")
            _create(root,PENDING,nav.canonical({"schema":SCHEMA,"operation_id":op,"request_sha256":value["request_sha256"],"plan_sha256":expected_plan_sha}))
        else:
            pending=nav.parse(nav.read_selected(root,PENDING,16384))
            require(pending=={"schema":SCHEMA,"operation_id":op,"request_sha256":value["request_sha256"],"plan_sha256":expected_plan_sha},"PENDING_IDENTITY")
        lease.tag({"schema":SCHEMA,"operation_id":op,"plan_sha256":expected_plan_sha,"pid":os.getpid()})
        return _finish(root,value,expected_plan_sha,lease,rollback=rollback,reconciling=True,renewal=renewal)
    finally:lease.release()


def summary(value):
    """Bounded public plan metadata; never print before/after source bodies."""
    result = {"schema": SCHEMA, "status": "PLANNED", "operation_id": value["request"]["operation_id"],
              "plan_sha256": nav.digest(nav.canonical(value)), "request_sha256": value["request_sha256"],
              "preview": value["preview"], "toolchain_sha256": value["toolchain_sha256"], "rows": [
                  {k: row[k] for k in ("path", "kind", "before_sha256", "after_sha256")}
                  for row in value["rows"]], "effects": "NONE_READ_ONLY"}
    require(len(nav.canonical(result)) <= 24 * 1024, "SUMMARY_LIMIT")
    return result


def _input(path):
    if path == "-":
        raw = sys.stdin.buffer.read(65537)
        require(len(raw) <= 65536, "REQUEST_LIMIT")
    else:
        selected = Path(path).absolute()
        for part in (selected, *selected.parents):
            require(not part.is_symlink(), "REQUEST_SYMLINK")
        raw = nav.read_selected(selected.parent.resolve(), selected.name, 65536)
    return nav.parse(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="atlas source-relocate", allow_abbrev=False)
    parser.add_argument("action", choices=("plan", "apply", "status", "reconcile"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--request")
    parser.add_argument("--operation")
    parser.add_argument("--expected-plan")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--stale-lock-sha256")
    parser.add_argument("--authorization")
    args = parser.parse_args(argv)
    try:
        if args.action in ("plan", "apply"):
            require(args.request is not None and args.operation is None
                    and not args.rollback and args.stale_lock_sha256 is None and args.authorization is None, "CLI_ARGUMENTS")
            request = _input(args.request)
            if args.action == "plan":
                require(args.expected_plan is None, "CLI_ARGUMENTS")
                result = summary(plan(args.root, request))
            else:
                require(args.expected_plan is not None, "CLI_ARGUMENTS")
                result = apply(args.root, request, args.expected_plan)
        else:
            require(args.operation is not None and args.expected_plan is not None, "CLI_ARGUMENTS")
            if args.action == "status":
                require(args.request is None and not args.rollback and args.stale_lock_sha256 is None and args.authorization is None, "CLI_ARGUMENTS")
                result = status(args.root, args.operation, args.expected_plan)
            else:
                result = reconcile(args.root, args.operation, args.expected_plan,
                    rollback=args.rollback, stale_lock_sha256=args.stale_lock_sha256,
                    preparation_request=_input(args.request) if args.request is not None else None,
                    renewal=_input(args.authorization) if args.authorization is not None else None)
        require(len(nav.canonical(result)) <= 24 * 1024, "SUMMARY_LIMIT")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (nav.Invalid, OSError, ValueError, KeyError, TypeError) as exc:
        # No input body or arbitrary OS path/exception text in the public error.
        code = str(exc) if isinstance(exc, nav.Invalid) else type(exc).__name__
        print(json.dumps({"status": "REFUSED", "code": code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
