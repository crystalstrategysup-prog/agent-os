#!/usr/bin/env python3
"""Bounded WM-UI owning-matrix projection adapter. No network, shell or source writes."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from datetime import datetime, timezone

import atlas
import navigator as nav

VERSION = "ATLAS-WM-IMPORT-1.3.0"
PROJECT = ".atlas/project.json"
STATE = ".atlas/IMPORT_STATE.json"
PENDING = ".atlas/IMPORT_PENDING.json"
DOC_PENDING = ".atlas/DOC_SYNC_PENDING.json"
LOCK = ".atlas/IMPORT.lock"
GAP_ID = "ATLAS-IMPORT-GAPS"
DOMAINS = ("goals", "modules", "contracts", "documents", "source", "works")
EVENT_ARRAYS = ("events", "actor_events", "actor_updates", "activity_events")
HISTORY_PAGE_ROWS = 2000
MAX_SOURCE_ENTRIES = 100000
MAX_METADATA_ROWS = 100000
MAX_METADATA_PAGE_BYTES = 8 * 1024 * 1024
HISTORY_SECTIONS = ("history_origins", "retained_matrices")
require = nav.require


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def shape(value, required, optional=(), label="binding"):
    require(isinstance(value, dict), "OBJECT_REQUIRED:" + label)
    require(set(required) <= set(value) <= set(required) | set(optional), "FIELDS:" + label)


def relative(value):
    atlas.path_text(value)
    return value


def directory(root, rel, create=False):
    relative(rel)
    p = root
    for part in PurePosixPath(rel).parts:
        p = p / part
        require(not p.is_symlink(), "IMPORT_SYMLINK:" + rel)
        if p.exists():
            require(p.is_dir(), "IMPORT_DIRECTORY:" + rel)
        elif create:
            p.mkdir()
    return p


def read(root, path, limit=8 * 1024 * 1024):
    return nav.read_selected(root, relative(path), limit)


def optional_read(root, path, limit=512 * 1024):
    p = root / relative(path)
    require(not p.is_symlink(), "IMPORT_SYMLINK:" + path)
    return read(root, path, limit) if p.exists() else None


def pin(path, raw):
    return {"path": path, "sha256": sha(raw), "bytes": len(raw)}


def atomic(root, rel, raw):
    p = root / relative(rel)
    directory(root, str(PurePosixPath(rel).parent), create=True)
    require(not p.is_symlink(), "IMPORT_SYMLINK:" + rel)
    fd, temp = tempfile.mkstemp(prefix=".atlas-write-", dir=p.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, p)
        nav.sync_directory(p.parent)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def pointer_value(value, pointer):
    require(isinstance(pointer, str), "MATRIX_POINTER_TYPE")
    if pointer == "":
        return value
    require(pointer.startswith("/"), "MATRIX_POINTER")
    for token in pointer.split("/")[1:]:
        require(all(token[i:i+2] in ("~0", "~1") for i, c in enumerate(token) if c == "~"), "MATRIX_POINTER_ESCAPE")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            require(token in value, "MATRIX_POINTER_MISSING")
            value = value[token]
        elif isinstance(value, list):
            require(token.isdigit() and (token == "0" or not token.startswith("0")), "MATRIX_POINTER_INDEX")
            index = int(token)
            require(index < len(value), "MATRIX_POINTER_MISSING")
            value = value[index]
        else:
            raise nav.Invalid("MATRIX_POINTER_MISSING")
    return value


def binding_model(raw):
    b = nav.parse(raw)
    shape(b, ("schema", "project", "matrix", "history", "documents", "output"), ("semantic_catalog", "ce_evidence"))
    require(b["schema"] == "atlas.upstream-binding/v1", "UPSTREAM_BINDING_SCHEMA")
    shape(b["project"], ("id", "title", "objective", "writer", "authority_ref", "scope_note"), label="project")
    nav.ident(b["project"]["id"])
    for k, v in b["project"].items():
        nav.text(v, "project." + k)
    require(b["project"]["writer"] != "UNKNOWN", "IMPORT_WRITER_REQUIRED")
    shape(b["matrix"], ("path", "allowed_schema"), ("pointer",), "matrix")
    relative(b["matrix"]["path"])
    nav.text(b["matrix"]["allowed_schema"], "matrix.allowed_schema")
    require(isinstance(b["matrix"].get("pointer", ""), str), "MATRIX_POINTER_TYPE")
    shape(b["history"], ("paths", "directories", "coverage_note"), ("pointer",), "history")
    nav.text(b["history"]["coverage_note"], "history.coverage_note")
    require(isinstance(b["history"].get("pointer", ""), str), "HISTORY_POINTER_TYPE")
    for name in ("paths", "directories"):
        require(isinstance(b["history"][name], list) and len(b["history"][name]) <= 2000, "HISTORY_PATH_LIMIT")
        for path in b["history"][name]:
            relative(path)
        require(len(set(b["history"][name])) == len(b["history"][name]), "DUPLICATE_HISTORY_PATH")
    require(isinstance(b["documents"], list) and len(b["documents"]) < 198, "DOCUMENT_LIMIT")
    ids = set()
    for d in b["documents"]:
        shape(d, ("id", "path", "title", "role", "domain"), label="document")
        nav.ident(d["id"])
        require(d["id"] not in ids and d["id"] != "ATLAS-UPSTREAM", "DOCUMENT_ID")
        ids.add(d["id"])
        relative(d["path"])
        for k in ("title", "role"):
            nav.text(d[k], "document." + k)
        require(d["domain"] in DOMAINS, "DOCUMENT_DOMAIN")
    if "ce_evidence" in b:
        rows=b["ce_evidence"]
        require(type(rows) is list and 1 <= len(rows) <= 32, "CE_EVIDENCE_BOUND")
        seen=set()
        for item in rows:
            shape(item,("contract_key","source_path","source_sha256","fe_source_root",
                "registry_root","chunks_root","source_entry","fixture_sha256",
                "runner_sha256","expected_manifest_sha256","verifier_sha256",
                "api_module_sha256","recording_gate_sha256"),label="ce_evidence")
            nav.ident(item["contract_key"])
            require(item["contract_key"] not in seen,"CE_EVIDENCE_DUPLICATE")
            seen.add(item["contract_key"])
            relative(item["source_path"])
            for key in ("source_sha256","fixture_sha256","runner_sha256","expected_manifest_sha256","verifier_sha256","api_module_sha256","recording_gate_sha256"):
                require(type(item[key]) is str and nav.SHA.fullmatch(item[key]),"CE_EVIDENCE_PIN")
            for key in ("fe_source_root","registry_root","chunks_root","source_entry"):
                nav.text(item[key],"ce_evidence."+key)
    if "semantic_catalog" in b:
        c = b["semantic_catalog"]
        shape(c, ("path", "sha256", "bytes"), label="semantic_catalog")
        relative(c["path"])
        require(isinstance(c["sha256"], str) and nav.SHA.fullmatch(c["sha256"]), "SEMANTIC_CATALOG_SHA")
        require(type(c["bytes"]) is int and 0 < c["bytes"] <= 8 * 1024 * 1024, "SEMANTIC_CATALOG_BYTES")
        require(not c["path"].startswith(".atlas/"), "UPSTREAM_MUST_BE_OUTSIDE_PROJECTION")
    relative(b["output"])
    require(b["output"].startswith(".atlas/") and not b["output"].startswith(".atlas/imports"), "IMPORT_OUTPUT_SCOPE")
    for p in [b["matrix"]["path"], *b["history"]["paths"], *b["history"]["directories"], *[d["path"] for d in b["documents"]]]:
        require(not p.startswith(".atlas/"), "UPSTREAM_MUST_BE_OUTSIDE_PROJECTION")
    return b


def history_paths(root, b, *, capacity=None):
    paths = set(b["history"]["paths"])
    scanned = len(b["history"]["paths"])
    for rel in b["history"]["directories"]:
        p = directory(root, rel)
        require(p.is_dir(), "HISTORY_DIRECTORY_MISSING:" + rel)
        with os.scandir(p) as entries:
            for child in entries:
                scanned += 1
                require(scanned <= MAX_SOURCE_ENTRIES, "IMPORT_SOURCE_ENTRY_CAPACITY_EXCEEDED")
                if child.name.endswith(".json"):
                    require(child.is_file(follow_symlinks=False) and not child.is_symlink(), "HISTORY_FILE_REQUIRED")
                    paths.add(str(PurePosixPath(rel) / child.name))
    require(len(paths) <= MAX_SOURCE_ENTRIES, "IMPORT_SOURCE_ENTRY_CAPACITY_EXCEEDED")
    if capacity is not None:
        capacity["source_entries"] = {"used": scanned, "limit": MAX_SOURCE_ENTRIES,
                                      "remaining": MAX_SOURCE_ENTRIES - scanned}
        capacity["selected_history_paths"] = len(paths)
    return sorted(paths)


def sequence_sha256(rows):
    """Hash a deterministic row sequence without serializing the full list."""
    digest = hashlib.sha256()
    digest.update(b"[")
    for index, row in enumerate(rows):
        if index:
            digest.update(b",")
        digest.update(nav.canonical(row)[:-1])
    digest.update(b"]\n")
    return digest.hexdigest()


def history_pin(value, label, *, page=False):
    shape(value, ("path", "sha256", "bytes", "count") if page else ("path", "sha256", "bytes"), label=label)
    relative(value["path"])
    require(value["path"].startswith(".atlas/imports/"), "IMPORT_HISTORY_PIN_SCOPE")
    require(isinstance(value["sha256"], str) and nav.SHA.fullmatch(value["sha256"]), "IMPORT_HISTORY_PIN_SHA")
    require(type(value["bytes"]) is int and 0 < value["bytes"] <= MAX_METADATA_PAGE_BYTES, "IMPORT_HISTORY_PIN_BYTES")
    if page:
        require(type(value["count"]) is int and 0 < value["count"] <= HISTORY_PAGE_ROWS, "IMPORT_HISTORY_PAGE_COUNT")


def validate_history_metadata(sections):
    """Validate hydrated records without reopening retained matrix payloads."""
    for key in HISTORY_SECTIONS:
        require(isinstance(sections.get(key, []), list), "IMPORT_HISTORY_METADATA_ARRAY")
    rows = sum(len(sections.get(key, [])) for key in HISTORY_SECTIONS)
    require(rows <= MAX_METADATA_ROWS, "IMPORT_HISTORY_METADATA_CAPACITY_EXCEEDED")
    retained = {}
    last_at = None
    for item in sections.get("retained_matrices", []):
        shape(item, ("id", "at", "source_ref", "kind", "file"), label="retained_matrix")
        history_pin(item["file"], "retained_matrix.file")
        digest = item["file"]["sha256"]
        require(item["id"] == "M-" + digest and item["kind"] == "FULL_MATRIX", "IMPORT_RETAINED_MATRIX_ID")
        nav.text(item["source_ref"], "retained_matrix.source_ref")
        moment = nav.stamp(item["at"])
        require(last_at is None or moment >= last_at, "IMPORT_RETAINED_MATRIX_ORDER")
        require(digest not in retained, "IMPORT_RETAINED_MATRIX_DUPLICATE")
        retained[digest] = item["file"]
        last_at = moment
    seen = set()
    for item in sections.get("history_origins", []):
        shape(item, ("path", "pointer", "enclosing_sha256", "enclosing_bytes", "selected_sha256", "selected_bytes", "representation"),
              ("matrix_at", "stat_guard", "verified_at", "verification", "retained_file"), "history_origin")
        relative(item["path"])
        require(not item["path"].startswith(".atlas/") and item["path"] not in seen, "IMPORT_HISTORY_ORIGIN_PATH")
        seen.add(item["path"])
        require(isinstance(item["pointer"], str), "IMPORT_HISTORY_ORIGIN_POINTER")
        require(item["representation"] in ("EXACT_FILE_BYTES", "CANONICAL_SELECTED_SUBTREE"), "IMPORT_HISTORY_REPRESENTATION")
        for key in ("enclosing", "selected"):
            require(isinstance(item[key + "_sha256"], str) and nav.SHA.fullmatch(item[key + "_sha256"]), "IMPORT_HISTORY_ORIGIN_SHA")
            require(type(item[key + "_bytes"]) is int and 0 < item[key + "_bytes"] <= 8 * 1024 * 1024, "IMPORT_HISTORY_ORIGIN_BYTES")
        for key in ("matrix_at", "verified_at"):
            if key in item:
                nav.stamp(item[key])
        if "verification" in item:
            require(item["verification"] == "VERIFIED_AT_IMPORT", "IMPORT_HISTORY_VERIFICATION")
        if "stat_guard" in item:
            shape(item["stat_guard"], ("device", "inode", "bytes", "mtime_ns", "ctime_ns"), label="history_origin.stat_guard")
            require(all(type(v) is int for v in item["stat_guard"].values()), "IMPORT_HISTORY_STAT_INTEGER")
            require(all(item["stat_guard"][k] >= 0 for k in ("device", "inode", "bytes")), "IMPORT_HISTORY_STAT_INTEGER")
        if "retained_file" in item:
            history_pin(item["retained_file"], "history_origin.retained_file")
            require(item["retained_file"]["sha256"] == item["selected_sha256"] and item["retained_file"]["bytes"] == item["selected_bytes"], "IMPORT_HISTORY_ORIGIN_PIN")
            if "retained_matrices" in sections:
                require(retained.get(item["selected_sha256"]) == item["retained_file"], "IMPORT_HISTORY_ORIGIN_NOT_RETAINED")
    return rows


def hydrate_history_metadata(root, meta, reader=None):
    """Accept legacy inline metadata; verify new page pins using metadata reads only."""
    reader = reader or read
    index = meta.get("history_metadata")
    if index is None:
        validate_history_metadata(meta)
        return dict(meta)
    require(not any(key in meta for key in HISTORY_SECTIONS), "IMPORT_HISTORY_INLINE_AND_PAGES")
    shape(index, ("schema", "row_count", *HISTORY_SECTIONS), label="history_metadata")
    require(index["schema"] == "atlas.import-history-index/v1", "IMPORT_HISTORY_INDEX_SCHEMA")
    require(type(index["row_count"]) is int and 0 <= index["row_count"] <= MAX_METADATA_ROWS, "IMPORT_HISTORY_METADATA_CAPACITY_EXCEEDED")
    sections = {}
    # Validate every count before reading any page. Limits apply to total hydrated
    # metadata rows, separately from the source directory scan budget.
    for key in HISTORY_SECTIONS:
        section = index[key]
        shape(section, ("count", "sha256", "pages"), label="history_metadata." + key)
        require(type(section["count"]) is int and 0 <= section["count"] <= MAX_METADATA_ROWS, "IMPORT_HISTORY_SECTION_COUNT")
        require(isinstance(section["sha256"], str) and nav.SHA.fullmatch(section["sha256"]), "IMPORT_HISTORY_SECTION_SHA")
        require(isinstance(section["pages"], list) and len(section["pages"]) == (section["count"] + HISTORY_PAGE_ROWS - 1) // HISTORY_PAGE_ROWS, "IMPORT_HISTORY_SECTION_PAGES")
    require(sum(index[key]["count"] for key in HISTORY_SECTIONS) == index["row_count"], "IMPORT_HISTORY_ROW_COUNT")
    for key in HISTORY_SECTIONS:
        section = index[key]
        values = []
        for number, page in enumerate(section["pages"]):
            history_pin(page, "history_metadata.page", page=True)
            parts = PurePosixPath(page["path"]).parts
            require(len(parts) == 5 and nav.SHA.fullmatch(parts[2]) and parts[3] == "metadata" and parts[4] == key + "-" + page["sha256"] + ".json", "IMPORT_HISTORY_PAGE_PATH")
            expected_count = min(HISTORY_PAGE_ROWS, section["count"] - number * HISTORY_PAGE_ROWS)
            require(page["count"] == expected_count, "IMPORT_HISTORY_PAGE_COUNT")
            raw = reader(root, page["path"], MAX_METADATA_PAGE_BYTES)
            require(pin(page["path"], raw) == {k: page[k] for k in ("path", "sha256", "bytes")}, "IMPORT_HISTORY_PAGE_HASH")
            payload = nav.parse(raw)
            shape(payload, ("schema", "section", "entries"), label="history_page")
            require(payload["schema"] == "atlas.import-history-page/v1" and payload["section"] == key, "IMPORT_HISTORY_PAGE_SCHEMA")
            require(isinstance(payload["entries"], list) and len(payload["entries"]) == page["count"], "IMPORT_HISTORY_PAGE_COUNT")
            values.extend(payload["entries"])
        require(sequence_sha256(values) == section["sha256"], "IMPORT_HISTORY_SECTION_HASH")
        sections[key] = values
    validate_history_metadata(sections)
    return {**meta, **sections}


def stage_history_metadata(put, old_meta, sections):
    rows = validate_history_metadata(sections)
    index = {"schema": "atlas.import-history-index/v1", "row_count": rows}
    prior_index = (old_meta or {}).get("history_metadata", {})
    for key in HISTORY_SECTIONS:
        values = sections[key]
        prior = {page["sha256"]: page for page in prior_index.get(key, {}).get("pages", [])}
        pages = []
        for start in range(0, len(values), HISTORY_PAGE_ROWS):
            entries = values[start:start + HISTORY_PAGE_ROWS]
            raw = nav.canonical({"schema": "atlas.import-history-page/v1", "section": key, "entries": entries})
            require(len(raw) <= MAX_METADATA_PAGE_BYTES, "IMPORT_HISTORY_METADATA_PAGE_BYTES_LIMIT")
            digest = sha(raw)
            pages.append(prior[digest] if digest in prior else {**put("metadata/" + key + "-" + digest + ".json", raw), "count": len(entries)})
        index[key] = {"count": len(values), "sha256": sequence_sha256(values), "pages": pages}
    return index


def import_capacity(bundle, old_meta):
    """Check remaining capacity before writing a generation or publication pointer."""
    retained = {row["file"]["sha256"] for row in (old_meta or {}).get("retained_matrices", [])}
    incoming = {h["origin"]["selected_sha256"] for h in bundle["histories"]}
    incoming.add(bundle["origin"]["selected_sha256"])
    new_count = len(incoming - retained)
    retained_count = len(retained | incoming)
    rows = len(bundle["histories"]) + retained_count
    require(rows <= MAX_METADATA_ROWS, "IMPORT_HISTORY_METADATA_CAPACITY_EXCEEDED")
    require(new_count <= HISTORY_PAGE_ROWS, "IMPORT_NEW_MATRIX_PAGE_CAPACITY_EXCEEDED")
    return {**bundle["capacity"],
            "metadata_rows": {"used": rows, "limit": MAX_METADATA_ROWS, "remaining": MAX_METADATA_ROWS - rows},
            "retained_matrices": retained_count,
            "new_matrix_page": {"used": new_count, "limit": HISTORY_PAGE_ROWS, "remaining": HISTORY_PAGE_ROWS - new_count},
            "new_input_bytes": {"used": sum(map(len, bundle["sources"].values())), "limit": atlas.MAX_SELECTED,
                                "remaining": atlas.MAX_SELECTED - sum(map(len, bundle["sources"].values()))},
            "metadata_page_rows": HISTORY_PAGE_ROWS,
            "scope": "Bounded scan and metadata hydration. Old raw matrices remain immutable; no history is deleted at capacity."}


def selected_matrix(raw, path, pointer):
    model = pointer_value(nav.parse(raw), pointer)
    require(isinstance(model, dict), "SOURCE_MATRIX_OBJECT")
    selected = nav.canonical(model) if pointer else raw
    origin = {"path": path, "pointer": pointer, "enclosing_sha256": sha(raw), "enclosing_bytes": len(raw),
              "selected_sha256": sha(selected), "selected_bytes": len(selected),
              "representation": "CANONICAL_SELECTED_SUBTREE" if pointer else "EXACT_FILE_BYTES"}
    return model, selected, origin


def source_stat(root, path):
    current = root
    for part in PurePosixPath(relative(path)).parts:
        current = current / part
        require(not current.is_symlink(), "IMPORT_SYMLINK:" + path)
    require(current.is_file(), "SOURCE_FILE_REQUIRED:" + path)
    st = current.stat()
    return {"device": st.st_dev, "inode": st.st_ino, "bytes": st.st_size,
            "mtime_ns": st.st_mtime_ns, "ctime_ns": st.st_ctime_ns}


def verified_ce_evidence(root, binding):
    """Opt-in owning contract validation using the EXISTING FE/CE registry code.

    No FE/CE module copied into Atlas. Physical source bytes are checked from
    the selected Atlas project; caller SHA/manifest alone are insufficient.
    """
    import subprocess
    import sys
    results={}
    child_code="""import hashlib,importlib.abc,importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
args=json.loads(sys.argv[2]); expected=json.loads(sys.argv[3])
executed={}
class VerifiedSourceLoader(importlib.abc.SourceLoader):
 def __init__(self,name,path):self.name,self.path=name,path
 def get_filename(self,fullname):return str(self.path)
 def get_data(self,path):return Path(path).read_bytes()
 def get_code(self,fullname):
  data=self.get_data(self.path)
  relative=self.path.relative_to(root).as_posix()
  digest=hashlib.sha256(data).hexdigest()
  if relative in expected and digest!=expected[relative]:raise ImportError('SOURCE_DIGEST_MISMATCH')
  executed[relative]=digest
  return compile(data,str(self.path),'exec',dont_inherit=True)
class VerifiedFinder(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname!='tools' and not fullname.startswith('tools.') :return None
  parts=fullname.split('.')
  location=root.joinpath(*parts)
  file=location/'__init__.py' if (location/'__init__.py').is_file() else location.with_suffix('.py')
  if location.is_dir() and not (location/'__init__.py').exists():
   spec=importlib.util.spec_from_loader(fullname,loader=None,is_package=True)
   spec.submodule_search_locations=[str(location)]
   return spec
  if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(root):raise ImportError('VERIFIER_MODULE_UNAVAILABLE')
  loader=VerifiedSourceLoader(fullname,file)
  return importlib.util.spec_from_loader(fullname,loader,is_package=file.name=='__init__.py')
sys.meta_path.insert(0,VerifiedFinder())
import tools.function_extractor.api
import tools.function_extractor.recording_gate
import tools.function_extractor.evidence_registry as module
assert Path(module.__file__).resolve()==(root/'tools/function_extractor/evidence_registry.py').resolve(), 'VERIFIER_MODULE_PATH'
result=module.load_chunk_evidence_v2(args['registry_root'],args['chunks_root'],
 source_entry=args['source_entry'],fixture_sha256=args['fixture_sha256'],
 runner_sha256=args['runner_sha256'],expected_manifest_sha256=args['expected_manifest_sha256'])
assert all(executed.get(k)==v for k,v in expected.items()),'VERIFIER_EXECUTED_ORIGIN'
print(json.dumps({'status':result.get('status'),'executed':executed}))"""
    for row in binding.get("ce_evidence",[]):
        source=read(root,row["source_path"])
        source_valid=sha(source)==row["source_sha256"]
        fe_root=Path(row["fe_source_root"]).absolute()
        pinned=(("tools/function_extractor/evidence_registry.py","verifier_sha256"),
                ("tools/function_extractor/api.py","api_module_sha256"),
                ("tools/function_extractor/recording_gate.py","recording_gate_sha256"))
        def check_pins():
            for relative,key in pinned:
                dep=fe_root/relative
                require(dep.is_file() and not dep.is_symlink() and sha(dep.read_bytes())==row[key],
                        "CE_VERIFIER_UNQUALIFIED" if key=="verifier_sha256" else "CE_TRANSITIVE_VERIFIER_UNQUALIFIED")
        check_pins()
        args={key:row[key] for key in ("registry_root","chunks_root","source_entry",
               "fixture_sha256","runner_sha256","expected_manifest_sha256")}
        try:
            child=subprocess.run([sys.executable,"-I","-B","-c",child_code,str(fe_root),
                                  json.dumps(args,sort_keys=True,separators=(",",":")),
                                  json.dumps({rel:row[key] for rel,key in pinned},sort_keys=True)],
                                  stdin=subprocess.DEVNULL,capture_output=True,text=True,
                                  timeout=8,check=False)
        except (OSError,subprocess.TimeoutExpired):
            require(False,"CE_VERIFIER_EXECUTION_UNKNOWN")
        check_pins()
        require(child.returncode==0 and len(child.stdout)<=4096 and len(child.stderr)<=4096,
                "CE_VERIFIER_EXECUTION_UNKNOWN")
        try:
            verdict=json.loads(child.stdout)
        except (ValueError,TypeError):
            require(False,"CE_VERIFIER_RESULT_UNKNOWN")
        require(type(verdict) is dict and set(verdict)=={"status","executed"} and
                type(verdict["executed"]) is dict and
                all(verdict["executed"].get(rel)==row[key] for rel,key in pinned) and
                verdict["status"] in ("HIT","MISS","REFUSED","UNKNOWN"),"CE_VERIFIER_RESULT_UNKNOWN")
        results[row["contract_key"]]="FACT" if source_valid and verdict.get("status")=="HIT" else "UNKNOWN"
    return results


def source_bundle(root, b, binding_raw, at, old_meta=None, binding_path=".atlas/UPSTREAM.json"):
    capacity = {}
    paths = history_paths(root, b, capacity=capacity)
    requested = {b["matrix"]["path"], *[d["path"] for d in b["documents"]]}
    if b.get("semantic_catalog"):
        requested.add(b["semantic_catalog"]["path"])
    sources = {}
    guards = {}
    input_bytes = 0
    def load_source(path):
        nonlocal input_bytes
        if path not in sources:
            before = source_stat(root, path)
            require(input_bytes + before["bytes"] <= atlas.MAX_SELECTED, "IMPORT_TOTAL_LIMIT_NEW_INPUTS_ARCHIVE_REQUIRED")
            raw = read(root, path)
            after = source_stat(root, path)
            require(before == after, "UPSTREAM_CHANGED_DURING_IMPORT")
            input_bytes += len(raw)
            require(input_bytes <= atlas.MAX_SELECTED, "IMPORT_TOTAL_LIMIT_NEW_INPUTS_ARCHIVE_REQUIRED")
            sources[path] = raw
            guards[path] = after
        return sources[path]
    for p in sorted(requested):
        load_source(p)
    require(sum(map(len, sources.values())) <= atlas.MAX_SELECTED, "IMPORT_TOTAL_LIMIT")
    matrix, selected, origin = selected_matrix(sources[b["matrix"]["path"]], b["matrix"]["path"], b["matrix"].get("pointer", ""))
    validate_matrix(matrix, b["matrix"]["allowed_schema"], at)
    cached = {o["path"]: o for o in old_meta.get("history_origins", [])} if old_meta else {}
    require(set(cached) <= set(paths), "SOURCE_HISTORY_REWRITE_OR_REMOVAL")
    qualified = {}
    if any(prior.get("stat_guard") != source_stat(root, p) for p, prior in cached.items()):
        import history_requalification
        qualified, proof_bytes = history_requalification.qualified_guards(root, binding_path, sources)
        input_bytes += proof_bytes
        require(input_bytes <= atlas.MAX_SELECTED, "IMPORT_TOTAL_LIMIT_NEW_INPUTS_ARCHIVE_REQUIRED")
        capacity["requalification_metadata_bytes"] = proof_bytes
        guards.update(qualified)
    histories = []
    for p in paths:
        prior = cached.get(p)
        observed = source_stat(root, p)
        guards[p] = observed
        if prior and (prior.get("stat_guard") == observed or qualified.get(p) == observed) and prior.get("retained_file") and prior.get("matrix_at"):
            orig = {**copy.deepcopy(prior), "stat_guard": observed, "verification": "VERIFIED_AT_IMPORT"}
            histories.append({"source_path": p, "raw": None, "origin": orig, "at": orig["matrix_at"], "file": orig["retained_file"]})
            continue
        m, raw, orig = selected_matrix(load_source(p), p, b["history"].get("pointer", ""))
        require(isinstance(m.get("updated_at"), str), "HISTORY_TIME_REQUIRED:" + p)
        require(nav.stamp(m["updated_at"]) <= nav.stamp(at), "HISTORY_FROM_FUTURE:" + p)
        if prior:
            require(orig["selected_sha256"] == prior["selected_sha256"], "SOURCE_HISTORY_REWRITE_OR_REMOVAL")
        orig.update({"matrix_at": m["updated_at"], "stat_guard": guards[p], "verified_at": at, "verification": "VERIFIED_AT_IMPORT"})
        histories.append({"source_path": p, "raw": raw, "origin": orig, "at": m["updated_at"]})
    require(sum(map(len, sources.values())) <= atlas.MAX_SELECTED, "IMPORT_TOTAL_LIMIT_NEW_INPUTS_ARCHIVE_REQUIRED")
    catalog = None
    if b.get("semantic_catalog"):
        c = b["semantic_catalog"]
        require(pin(c["path"], sources[c["path"]]) == c, "SEMANTIC_CATALOG_PIN")
        catalog = catalog_model(sources[c["path"]], b, {s["id"] for s in matrix["steps"]})
    evidence=verified_ce_evidence(root,b)
    if evidence:
        require(catalog is not None,"CE_CATALOG_REQUIRED")
        matched=set()
        for row in catalog["contracts"]:
            if row["contract_key"] in evidence:
                row["evidence_state"]=evidence[row["contract_key"]]
                matched.add(row["contract_key"])
        require(matched==set(evidence),"CE_CONTRACT_BINDING_MISSING")
    identity = {"binding_sha256": sha(binding_raw), "matrix_sha256": sha(selected),
                "histories": {"count": len(histories), "sha256": sequence_sha256({"path": h["source_path"], "sha256": h["origin"]["selected_sha256"]} for h in histories)},
                "documents": [{"path": d["path"], "sha256": sha(sources[d["path"]])} for d in b["documents"]],
                "ce_evidence_states": evidence, "adapter_version": VERSION, "toolchain_sha256": sha(nav.canonical({p.name: sha(p.read_bytes()) for p in sorted(Path(__file__).parent.iterdir()) if p.is_file() and p.suffix in (".py", ".json", ".js", ".css")}))}
    return {"matrix": matrix, "matrix_raw": selected, "origin": origin, "histories": histories,
            "sources": sources, "source_guards": guards, "ce_evidence_states": evidence, "catalog": catalog,
            "history_paths": paths, "capacity": capacity, "identity": identity, "fingerprint": sha(nav.canonical(identity)), "binding_raw": binding_raw}


def validate_matrix(m, schema, at):
    require(m.get("schema") == schema, "UPSTREAM_SCHEMA_MISMATCH")
    require(isinstance(m.get("updated_at"), str) and nav.stamp(m["updated_at"]) <= nav.stamp(at), "SOURCE_MATRIX_TIME")
    require(isinstance(m.get("steps"), list) and 0 < len(m["steps"]) < 1000, "SOURCE_STEPS_LIMIT")
    ids = set()
    for step in m["steps"]:
        require(isinstance(step, dict), "SOURCE_STEP_OBJECT")
        nav.ident(step.get("id"))
        require(step["id"] not in ids and step["id"] != GAP_ID, "SOURCE_STEP_ID")
        ids.add(step["id"])
        nav.text(step.get("title"), "source.step.title")
        require(len(step["title"]) <= 500, "SOURCE_STEP_TITLE_LIMIT")
    for step in m["steps"]:
        require(step.get("parent_id") is None or step["parent_id"] in ids, "SOURCE_PARENT")
    for category in EVENT_ARRAYS:
        values = m.get(category, [])
        require(isinstance(values, list) and len(values) <= 100000, "SOURCE_EVENT_LIMIT")
        seen = set()
        for e in values:
            require(isinstance(e, dict), "SOURCE_EVENT_OBJECT")
            nav.ident(e.get("id"))
            require(e["id"] not in seen, "SOURCE_EVENT_ID:" + category)
            seen.add(e["id"])
            require(nav.stamp(e.get("at")) <= nav.stamp(at), "SOURCE_EVENT_TIME")
            if category == "events":
                require(e.get("step_id") in ids, "SOURCE_EVENT_STEP")
    require(isinstance(m.get("actors", []), list), "SOURCE_ACTORS")


def verify_append(old, new):
    old_steps = {s["id"]: s for s in old["steps"]}
    new_steps = {s["id"]: s for s in new["steps"]}
    for sid, step in old_steps.items():
        require(sid in new_steps, "SOURCE_STEP_REMOVED:" + sid)
        # Order is presentation; definitions retain every other original field.
        a = {k: v for k, v in step.items() if k != "order"}
        b = {k: v for k, v in new_steps[sid].items() if k != "order"}
        require(a == b, "SOURCE_DEFINITION_REWRITE:" + sid)
    for category in EVENT_ARRAYS:
        before = old.get(category, [])
        require(new.get(category, [])[:len(before)] == before, "SOURCE_EVENT_REWRITE:" + category)


def verify_binding_append(old, new):
    require(old["project"] == new["project"] and old["output"] == new["output"], "UPSTREAM_AUTHORITY_MIGRATION_REQUIRED")
    for key in ("path", "allowed_schema", "pointer"):
        require(old["matrix"].get(key, "") == new["matrix"].get(key, ""), "UPSTREAM_MATRIX_MIGRATION_REQUIRED")
    require(old["history"]["directories"] == new["history"]["directories"] and old["history"].get("pointer", "") == new["history"].get("pointer", ""), "UPSTREAM_HISTORY_BINDING_MIGRATION_REQUIRED")
    require(new["history"]["paths"][:len(old["history"]["paths"])] == old["history"]["paths"], "UPSTREAM_HISTORY_BINDING_REWRITE")
    require(new["documents"][:len(old["documents"])] == old["documents"], "UPSTREAM_DOCUMENT_BINDING_REWRITE")
    if old.get("semantic_catalog"):
        require(new.get("semantic_catalog") and old["semantic_catalog"]["path"] == new["semantic_catalog"]["path"], "UPSTREAM_CATALOG_BINDING_REWRITE")


def catalog_model(raw, b, work_ids):
    c = nav.parse(raw)
    shape(c, ("schema", "modules", "contracts", "relations", "work_bindings"), ("work_context", "patch_bindings"), "semantic_catalog")
    require(c["schema"] == "atlas.semantic-catalog/v1", "SEMANTIC_CATALOG_SCHEMA")
    for key, limit in (("modules", 200), ("contracts", 1000), ("relations", 2000), ("work_bindings", 1000), ("work_context", 1000), ("patch_bindings", 2000)):
        nav.array(c.get(key, []), "catalog." + key, limit)
    doc_ids = {"ATLAS-UPSTREAM", *[d["id"] for d in b["documents"]]}
    module_ids = set()
    contract_ids = set()
    for key, ids in (("modules", module_ids), ("contracts", contract_ids)):
        for item in c[key]:
            require(isinstance(item, dict), "SEMANTIC_ENTITY_OBJECT")
            nav.ident(item.get("id"))
            require(item["id"] not in doc_ids | module_ids | contract_ids, "SEMANTIC_ENTITY_ID")
            ids.add(item["id"])
    all_ids = doc_ids | module_ids | contract_ids
    for m in c["modules"]:
        nav.shape(m, "id title purpose state_owner dependencies docs", "module")
        nav.refs(m["docs"], doc_ids, "catalog.module.docs")
        nav.refs(m["dependencies"], module_ids, "catalog.module.dependencies")
    for contract in c["contracts"]:
        nav.shape(contract, "id contract_key title version lifecycle module state_owner input output parameters errors auth dependencies usage docs evidence_state execution", "contract")
        nav.refs(contract["docs"], doc_ids, "catalog.contract.docs")
        nav.refs(contract["dependencies"], contract_ids, "catalog.contract.dependencies")
        require(contract["module"] in module_ids, "SEMANTIC_CONTRACT_MODULE")
    for edge in c["relations"]:
        nav.shape(edge, "from to type evidence_docs", "relation")
        require(edge["from"] in all_ids and edge["to"] in all_ids, "SEMANTIC_RELATION_ENTITY")
        nav.refs(edge["evidence_docs"], doc_ids, "catalog.relation.docs")
    for key in ("work_bindings", "work_context"):
        seen = set()
        for item in c.get(key, []):
            if key == "work_bindings":
                shape(item, ("work_id", "entity_ids"), label=key)
                nav.refs(item["entity_ids"], all_ids, "catalog.work.entities")
            else:
                shape(item, ("work_id",), ("outcome", "result_claim", "remaining", "next_action"), key)
                require(len(item) > 1, "EMPTY_WORK_CONTEXT")
                for name in ("outcome", "result_claim", "remaining"):
                    if name in item:
                        nav.text(item[name], "catalog." + name)
                        require(len(item[name]) <= 19000, "SEMANTIC_TEXT_LIMIT")
                if "next_action" in item:
                    shape(item["next_action"], ("actor", "action"), label="next_action")
                    nav.text(item["next_action"]["actor"], "next_action.actor")
                    nav.text(item["next_action"]["action"], "next_action.action")
            require(item["work_id"] in work_ids and item["work_id"] not in seen, "SEMANTIC_WORK_ID")
            seen.add(item["work_id"])
    seen = set()
    for patch in c.get("patch_bindings", []):
        shape(patch, ("work_id", "patch_doc_id", "target_doc_id", "base_sha256", "selectors", "source_state"), label="patch_binding")
        require(patch["work_id"] in work_ids, "SEMANTIC_PATCH_WORK")
        require(patch["patch_doc_id"] in doc_ids and patch["target_doc_id"] in doc_ids and patch["patch_doc_id"] != patch["target_doc_id"], "SEMANTIC_PATCH_DOC")
        require(isinstance(patch["base_sha256"], str) and nav.SHA.fullmatch(patch["base_sha256"]), "SEMANTIC_PATCH_SHA")
        nav.array(patch["selectors"], "patch.selectors", 200)
        require(patch["selectors"] and len(set(patch["selectors"])) == len(patch["selectors"]) and all(isinstance(s, str) and s.startswith("/") for s in patch["selectors"]), "SEMANTIC_PATCH_SELECTORS")
        nav.text(patch["source_state"], "patch.source_state")
        identity = (patch["work_id"], patch["patch_doc_id"], patch["target_doc_id"], tuple(patch["selectors"]))
        require(identity not in seen, "SEMANTIC_PATCH_DUPLICATE")
        seen.add(identity)
    return c


def semantic_projection(catalog, doc_ids):
    c = catalog or {"modules": [], "contracts": [], "relations": [], "work_bindings": []}
    modules = copy.deepcopy(c["modules"])
    for m in modules:
        m["docs"] = [doc_ids[d] for d in m["docs"]]
    contracts = copy.deepcopy(c["contracts"])
    by_id = {card["id"]: card for card in contracts}
    seeds = {}
    for card in contracts:
        card["docs"] = [doc_ids[d] for d in card["docs"]]
        seeds[card["id"]] = sha(nav.canonical(card))
    contract_ids = {}
    for logical in sorted(by_id):
        reached = set()
        pending = [logical]
        while pending:
            node = pending.pop()
            if node not in reached:
                reached.add(node)
                pending.extend(by_id[node]["dependencies"])
        version = sha(nav.canonical({node: seeds[node] for node in sorted(reached)}))
        contract_ids[logical] = "C-" + sha(logical.encode())[:12] + "-" + version[:24]
    for card in contracts:
        card["id"] = contract_ids[card["id"]]
        card["dependencies"] = [contract_ids[d] for d in card["dependencies"]]
    entity_ids = {**doc_ids, **{m["id"]: m["id"] for m in modules}, **contract_ids}
    relations = [{"from": entity_ids[r["from"]], "to": entity_ids[r["to"]], "type": r["type"],
                  "evidence_docs": [doc_ids[d] for d in r["evidence_docs"]]} for r in c["relations"]]
    # Only declared dependency edges expand a work packet; no keyword guessing.
    graph = {m["id"]: m["dependencies"] + m["docs"] for m in modules}
    graph.update({card["id"]: card["dependencies"] + card["docs"] + [card["module"]] for card in contracts})
    work_refs = {}
    for binding in c["work_bindings"]:
        refs = set()
        pending = [entity_ids[e] for e in binding["entity_ids"]]
        while pending:
            node = pending.pop()
            if node not in refs:
                refs.add(node)
                pending.extend(graph.get(node, []))
        work_refs[binding["work_id"]] = sorted(refs)
    return {"modules": modules, "contracts": contracts, "relations": relations, "entity_ids": entity_ids,
            "work_refs": work_refs, "work_context": {x["work_id"]: x for x in c.get("work_context", [])},
            "patch_bindings": c.get("patch_bindings", [])}


def legacy_claim(step, latest, context):
    if not latest and not context.get("result_claim"):
        return None
    claim = {k: latest[k] for k in ("id", "at", "status", "accepted", "note", "evidence") if k in latest}
    if "result_claim" in context:
        claim["catalogue_result_claim"] = context["result_claim"]
    text = "SOURCE_CLAIM: " + json.dumps(claim, ensure_ascii=False, separators=(",", ":"))
    if len(text) > 20000:
        text = "SOURCE_CLAIM: event=" + str(latest.get("id", "UNKNOWN")) + "; status=" + str(latest.get("status", "UNKNOWN")) + "; exact result, acceptance scope and evidence references remain in UPSTREAM-FRAGMENT (claim exceeds the bounded card view)."
    return text


def state_for(step, events, children, actors):
    latest = events[-1] if events else {}
    executors = latest.get("executor_ids", [])
    assigned = executors[0] if isinstance(executors, list) and len(executors) == 1 and executors[0] in actors else "UNKNOWN"
    status = latest.get("status", "UNKNOWN")
    if step["id"] in children:
        return "PLANNED", assigned, status
    mapped = {"planned": "PLANNED", "done": "REVIEW", "partial": "REVIEW", "blocked": "BLOCKED", "waiting": "PAUSED"}
    if status == "doing":
        return ("DOING" if assigned != "UNKNOWN" else "UNKNOWN"), assigned, status
    state = mapped.get(status, "UNKNOWN")
    if state == "REVIEW" and assigned == "UNKNOWN":
        state = "UNKNOWN"
    return state, assigned, status


def append_event(work, kind, summary, at, salt):
    work["events"].append({"id": "I-" + sha(nav.canonical([work["id"], len(work["events"]), kind, salt]))[:32],
                           "at": at, "actor": work["writer"], "kind": kind, "summary": summary, "evidence_ids": []})


def stage_generation(root, b, bundle, at, old_meta, old_project, old_snapshot, old_pointer=None):
    fingerprint = bundle["fingerprint"]
    gen = ".atlas/imports/" + fingerprint
    existing = optional_read(root, gen + "/IMPORT.json", 8 * 1024 * 1024)
    old_project_sha = sha(nav.canonical(old_project)) if old_project is not None else None
    if existing is not None:
        meta = nav.parse(existing)
        require(meta["fingerprint"] == fingerprint and meta["before_project_sha256"] == old_project_sha, "IMPORT_GENERATION_RECONCILE_REQUIRED")
        for p in meta["files"]:
            require(pin(p["path"], read(root, p["path"])) == p, "IMPORT_GENERATION_HASH")
        hydrate_history_metadata(root, meta)
        return meta, read(root, gen + "/project.json", 512 * 1024)
    files = {}
    def put(name, raw):
        rel = gen + "/" + name
        files[rel] = raw if isinstance(raw, bytes) else nav.canonical(raw)
        return pin(rel, files[rel])
    prior_matrix = old_meta.get("matrix") if old_meta else None
    current_pin = prior_matrix if prior_matrix and prior_matrix["sha256"] == sha(bundle["matrix_raw"]) else put("matrix.json", bundle["matrix_raw"])
    prior_binding = old_meta.get("binding_file") if old_meta else None
    binding_pin = prior_binding if prior_binding and prior_binding["sha256"] == sha(bundle["binding_raw"]) else put("UPSTREAM.json", bundle["binding_raw"])
    catalog_pin = None
    if bundle["catalog"]:
        catalog_raw = bundle["sources"][b["semantic_catalog"]["path"]]
        prior_catalog = old_meta.get("semantic_catalog") if old_meta else None
        catalog_pin = prior_catalog if prior_catalog and prior_catalog["sha256"] == sha(catalog_raw) else put("SEMANTIC_CATALOG.json", catalog_raw)
    old_dn = copy.deepcopy(old_snapshot["input"]) if old_snapshot else None
    old_docs = old_dn["documents"] if old_dn else []
    doc_lookup = {d["id"]: d for d in old_docs}
    current_docs = {}
    documents = []
    doc_defs = [{"id": "ATLAS-UPSTREAM", "path": b["matrix"]["path"], "title": "Owning matrix: selected source", "role": "owning matrix projection source", "domain": "works"}, *b["documents"]]
    for d in doc_defs:
        raw = bundle["matrix_raw"] if d["id"] == "ATLAS-UPSTREAM" else bundle["sources"][d["path"]]
        previous_id = old_meta.get("documents", {}).get(d["id"]) if old_meta else None
        previous = doc_lookup.get(previous_id)
        if previous and previous["sha256"] == sha(raw):
            current_docs[d["id"]] = previous_id
            documents.append(previous)
            continue
        ext = ".json" if d["id"] == "ATLAS-UPSTREAM" else PurePosixPath(d["path"]).suffix.lower()
        require(ext in (".json", ".md", ".txt", ".yaml", ".yml"), "DOCUMENT_EXTENSION")
        docid = "D-" + sha(d["id"].encode())[:12] + "-" + fingerprint[:20]
        p = current_pin if d["id"] == "ATLAS-UPSTREAM" else put("documents/" + docid + ext, raw)
        record = {"id": docid, "title": d["title"], **p, "kind": {".json": "json", ".md": "markdown", ".txt": "text", ".yaml": "yaml", ".yml": "yaml"}[ext],
                  "version": sha(raw), "lifecycle": "current", "source_ref": d["path"] + " [" + d["role"] + "]" + (" pointer=" + b["matrix"].get("pointer", "") if d["id"] == "ATLAS-UPSTREAM" else ""),
                  "readback_at": at, "evidence_state": "UNKNOWN", "execution": "NOT_RUN"}
        documents.append(record)
        current_docs[d["id"]] = docid
    semantic = semantic_projection(bundle["catalog"], current_docs)
    dn_history = [{"id": "IMPORT-" + fingerprint[:32], "at": at, "kind": "imported", "summary": "Owning source and declared semantic bindings projected. Prior scoped claims retained; no new runtime or acceptance inferred.", "entity_ids": list(current_docs.values())}]
    dn = {"schema": "docs-navigator.input/v1", "project": {"id": b["project"]["id"], "title": b["project"]["title"], "scope_note": b["project"]["scope_note"]},
          "release": {"id": "IMPORT-" + fingerprint[:32], "created_at": at, "previous": None}, "documents": documents,
          "modules": semantic["modules"], "contracts": semantic["contracts"],
          "relations": semantic["relations"], "matrix": {"doc": None}, "bindings": [], "history": dn_history}
    dn_pin = put("documents.json", dn)
    retained = copy.deepcopy(old_meta.get("retained_matrices", old_project.get("matrix_history", []))) if old_meta else []
    retained_by_sha = {x["file"]["sha256"]: x for x in retained}
    histories = []
    incoming = [*bundle["histories"], {"source_path": b["matrix"]["path"], "raw": bundle["matrix_raw"], "origin": bundle["origin"], "at": bundle["matrix"]["updated_at"]}]
    for h in sorted(incoming, key=lambda h: (nav.stamp(h["at"]), h["origin"]["selected_sha256"])):
        digest = h["origin"]["selected_sha256"]
        if digest in retained_by_sha:
            h["origin"]["retained_file"] = retained_by_sha[digest]["file"]
            continue
        require(not retained or nav.stamp(h["at"]) >= nav.stamp(retained[-1]["at"]), "LATE_HISTORY_REQUIRES_EXPLICIT_LINEAGE")
        require(h["raw"] is not None, "RETAINED_HISTORY_PIN_MISSING")
        filepin = current_pin if digest == current_pin["sha256"] else put("history/" + digest + ".json", h["raw"])
        entry = {"id": "M-" + digest, "at": h["at"], "source_ref": h["source_path"] + (" pointer=" + h["origin"]["pointer"] if h["origin"]["pointer"] else ""), "kind": "FULL_MATRIX", "file": filepin}
        histories.append(entry)
        retained.append(entry)
        retained_by_sha[digest] = entry
        h["origin"]["retained_file"] = filepin
    old_works = {w["id"]: atlas._raw_work(w) for w in old_snapshot["atlas"]["works"]} if old_snapshot else {}
    old_paths = old_snapshot["atlas"]["work_paths"] if old_snapshot else {}
    matrix = bundle["matrix"]
    children = {s.get("parent_id") for s in matrix["steps"] if s.get("parent_id") is not None}
    actors = {a.get("id") for a in matrix.get("actors", []) if isinstance(a, dict) and isinstance(a.get("id"), str)}
    work_paths = []
    changed = []
    gaps = []
    docs_by_id = {d["id"]: d for d in documents}
    for step in matrix["steps"]:
        wid = step["id"]
        events = [e for e in matrix["events"] if e["step_id"] == wid]
        context = semantic["work_context"].get(wid, {})
        patches = [p for p in semantic["patch_bindings"] if p["work_id"] == wid]
        fragment = {"schema": "atlas.upstream-fragment/v1", "step": step, "events": events,
                    "activity_events": [e for e in matrix.get("activity_events", []) if e.get("step_id") == wid]}
        if context:
            fragment["work_context"] = context
        if patches:
            fragment["patch_bindings"] = patches
        fragment_raw = nav.canonical(fragment)
        previous = old_works.get(wid)
        prior_art = previous["artifacts"][0] if previous and previous["artifacts"] else None
        fragment_pin = {k: prior_art[k] for k in ("path", "sha256", "bytes")} if prior_art and prior_art["sha256"] == sha(fragment_raw) else put("fragments/" + wid + ".json", fragment_raw)
        state, assigned, source_status = state_for(step, events, children, actors)
        if state == "UNKNOWN" and previous and any(e["kind"] in ("STARTED", "RESUMED", "REVIEWED", "BLOCKED", "PAUSED", "REOPEN") for e in previous["events"]):
            # The frozen core has no typed UNKNOWN transition. A qualification plan
            # removes any execution claim while retaining exact upstream UNKNOWN.
            state = "PLANNED"
        definition = step.get("source_definition")
        objective = definition if isinstance(definition, str) and definition else step["title"]
        require(len(objective) <= 20000, "SOURCE_OBJECTIVE_LIMIT:" + wid)
        latest = events[-1] if events else {}
        note = latest.get("note")
        reason = note if isinstance(note, str) and note else "Source reports blocked; exact cause remains to be qualified from the retained source."
        require(len(reason) <= 20000, "SOURCE_NOTE_LIMIT:" + wid)
        refs = semantic["work_refs"].get(wid, [])
        artifacts = [{"id": "UPSTREAM-FRAGMENT", **fragment_pin, "role": "reference", "entity_ids": refs}]
        target_artifacts = set()
        for patch in patches:
            target = docs_by_id[current_docs[patch["target_doc_id"]]]
            patch_doc = docs_by_id[current_docs[patch["patch_doc_id"]]]
            require(target["sha256"] == patch["base_sha256"], "SEMANTIC_PATCH_BASE_CHANGED:" + wid)
            target_id = "TARGET-" + sha(patch["target_doc_id"].encode())[:20]
            if target_id not in target_artifacts:
                artifacts.append({"id": target_id, **{k: target[k] for k in ("path", "sha256", "bytes")}, "role": "input", "entity_ids": [target["id"]]})
                target_artifacts.add(target_id)
            patch_id = "PATCH-" + sha(nav.canonical([patch["patch_doc_id"], patch["target_doc_id"], patch["selectors"]]))[:20]
            artifacts.append({"id": patch_id, **{k: patch_doc[k] for k in ("path", "sha256", "bytes")}, "role": "patch", "entity_ids": [patch_doc["id"]],
                              "patch": {"target_id": target_id, "base_sha256": patch["base_sha256"], "selectors": patch["selectors"], "state": "PROPOSED", "decision_evidence_ids": [], "result_artifact_id": None}})
        declared_outcome = definition.get("outcome", definition.get("expected", definition.get("acceptance"))) if isinstance(definition, dict) else definition
        default_outcome = "Source-declared work scope: " + (declared_outcome if isinstance(declared_outcome, str) and declared_outcome else step["title"])
        require(len(default_outcome) <= 20000, "SOURCE_OUTCOME_LIMIT:" + wid)
        completed_claim = source_status == "done" or latest.get("accepted") is True
        next_text = ("Preserve the owning result and its recorded acceptance scope. Reuse prior evidence; change or verify this work only for a changed dependency, a new requirement, or a concrete assigned gap."
                     if completed_claim else "Continue the owning plan from the retained source result and next step. Qualify only missing fields needed for the next assigned change; reuse still relevant scoped evidence.")
        work = {"schema": "atlas.work/v1", "id": wid, "parent_id": step.get("parent_id"), "title": step["title"], "objective": objective,
                "outcome": context.get("outcome", default_outcome),
                "criteria": [], "state": state, "writer": b["project"]["writer"], "assigned_to": assigned, "write_scope": [], "depends_on": [],
                "artifacts": artifacts,
                "evidence": [], "acceptance": [], "activity": None,
                "blocker": {"reason": reason, "unblock_condition": "UNKNOWN: owning writer must qualify the source blocker and exact continuation condition.", "next_owner": b["project"]["writer"]} if state == "BLOCKED" else None,
                "result": legacy_claim(step, latest, context),
                "remaining": context.get("remaining", "Source status=" + str(source_status) + "; its historical result and acceptance scope remain retained. No new Atlas acceptance or current activity is inferred. Missing metadata is qualified only when this work is next touched; import alone requires no rerun."),
                "next_action": context.get("next_action", {"actor": b["project"]["writer"], "action": next_text}),
                "events": copy.deepcopy(previous["events"]) if previous else []}
        if previous and {k: v for k, v in previous.items() if k != "events"} == {k: v for k, v in work.items() if k != "events"}:
            work_paths.append(old_paths[wid])
        else:
            if previous and (previous["writer"] != work["writer"] or previous["assigned_to"] != assigned):
                append_event(work, "HANDOFF", "Source projection assignment changed; no independent work authorization is granted.", at, fingerprint)
            append_event(work, "IMPORTED", "Retained exact source fragment; source status=" + str(source_status) + ". No acceptance/activity inferred.", at, fingerprint)
            kind = {"PLANNED": "REOPEN", "DOING": "STARTED", "REVIEW": "REVIEWED", "BLOCKED": "BLOCKED", "PAUSED": "PAUSED"}.get(state)
            if kind and (state != "PLANNED" or previous and previous["state"] != "PLANNED"):
                append_event(work, kind, "Projection state from the owning source; this records source interpretation, not fresh runtime activity.", at, fingerprint)
            work_paths.append(put("work/" + wid + ".json", work)["path"])
            changed.append(wid)
        gaps.append({"work_id": wid, "missing": ["native_acceptance_criteria", "write_scope", "dependencies"] + ([] if refs else ["semantic_binding"]),
                     "qualification_policy": "ON_NEXT_TOUCHED_WORK", "source_status": source_status, "assigned_to": assigned})
    gap_raw = nav.canonical({"schema": "atlas.import-gaps/v1", "works": gaps, "coverage": "PARTIAL", "history_note": b["history"]["coverage_note"],
                             "semantic_counts": {"modules": len(semantic["modules"]), "contracts": len(semantic["contracts"]), "relations": len(semantic["relations"]), "bound_works": len(semantic["work_refs"])},
                             "note": "All listed source steps and scoped result claims retained. Metadata gaps are not a reopening or mandatory rerun list. Qualify only the next relevant missing binding; completeness remains limited to declared inventory."})
    prior_gap = old_works.get(GAP_ID)
    prior_gap_art = prior_gap["artifacts"][0] if prior_gap else None
    gap_pin = {k: prior_gap_art[k] for k in ("path", "sha256", "bytes")} if prior_gap_art and prior_gap_art["sha256"] == sha(gap_raw) else put("GAPS.json", gap_raw)
    gap_artifacts = [{"id": "IMPORT-GAPS", **gap_pin, "role": "reference", "entity_ids": []}]
    if catalog_pin:
        gap_artifacts.append({"id": "SEMANTIC-CATALOG", **catalog_pin, "role": "reference", "entity_ids": []})
    gap = {"schema": "atlas.work/v1", "id": GAP_ID, "parent_id": None, "title": "Register the next required missing binding", "objective": b["project"]["objective"],
           "outcome": "Exact project inventory, outcome/criteria and write scopes are linked by the existing writer; every unresolved gap remains explicit.",
           "criteria": [], "state": "PLANNED", "writer": b["project"]["writer"], "assigned_to": b["project"]["writer"], "write_scope": [], "depends_on": [],
           "artifacts": gap_artifacts, "evidence": [], "acceptance": [], "activity": None, "blocker": None, "result": None,
           "remaining": "The register describes missing native metadata; preserved source results and prior scoped acceptance remain available. It does not reopen completed work.",
           "next_action": {"actor": b["project"]["writer"], "action": "Register the next missing binding needed by an assigned change. Add the exact module/contract/document once; reuse earlier scoped evidence and do not requalify unchanged historical works."},
           "events": copy.deepcopy(prior_gap["events"]) if prior_gap else []}
    if prior_gap and {k: v for k, v in prior_gap.items() if k != "events"} == {k: v for k, v in gap.items() if k != "events"}:
        work_paths.append(old_paths[GAP_ID])
    else:
        append_event(gap, "IMPORTED", "Exact unresolved source qualification gaps retained.", at, fingerprint)
        work_paths.append(put("work/" + GAP_ID + ".json", gap)["path"])
        changed.append(GAP_ID)
    items = {d: [] for d in DOMAINS}
    items["works"] = [s["id"] for s in matrix["steps"]] + [GAP_ID]
    items["documents"] = list(current_docs)
    for d in b["documents"]:
        if d["domain"] not in ("works", "documents"):
            items[d["domain"]].append(d["id"])
    items["modules"].extend(m["id"] for m in semantic["modules"])
    items["contracts"].extend(c["id"] for c in (bundle["catalog"] or {}).get("contracts", []))
    inventory = {"schema": "atlas.inventory/v1", "id": "IMPORTED-INVENTORY", "scope_note": b["project"]["scope_note"], "source_ref": b["matrix"]["path"], "observed_at": at,
                 "domains": [{"id": d, "title": d, "exhaustive": False, "items": list(dict.fromkeys(items[d])), "exclusions": []} for d in DOMAINS]}
    bindings = [{"domain_id": "works", "item_id": wid, "entity_ids": semantic["work_refs"].get(wid, []), "work_ids": [wid]} for wid in items["works"]]
    bindings += [{"domain_id": d, "item_id": item, "entity_ids": [semantic["entity_ids"][item]], "work_ids": []} for d in DOMAINS if d != "works" for item in dict.fromkeys(items[d])]
    project = {"schema": "atlas.project/v1", **b["project"], "mode": "projection", "source_ref": b["matrix"]["path"] + " pointer=" + b["matrix"].get("pointer", ""),
               "documents": dn_pin, "work_files": work_paths, "coverage": {"inventory": put("inventory.json", inventory), "bindings": bindings}, "matrix_history": histories}
    if old_snapshot:
        require(old_pointer is not None, "PROJECTION_ARCHIVE_PARENT_REQUIRED")
        project["projection_archive"] = {"schema": "atlas.projection-archive/v1", "output": b["output"], "previous_release": old_snapshot["input"]["release"]["id"],
                                         "previous_manifest_sha256": old_pointer["manifest_sha256"], "matrix_history_total": len(retained)}
    project_raw = nav.canonical(project)
    require(len(project_raw) <= 512 * 1024, "IMPORT_PROJECT_MANIFEST_CAPACITY_EXCEEDED")
    put("project.json", project_raw)
    # Existing origin order is stable even when a new source filename sorts
    # earlier. Full immutable metadata pages can therefore be reused exactly.
    origins = {h["source_path"]: h["origin"] for h in bundle["histories"]}
    ordered_origins = [origins.pop(item["path"]) for item in (old_meta or {}).get("history_origins", [])]
    ordered_origins.extend(origins.values())
    history_metadata = stage_history_metadata(put, old_meta, {"history_origins": ordered_origins, "retained_matrices": retained})
    meta = {"schema": "atlas.import-generation/v1", "version": VERSION, "fingerprint": fingerprint, "at": at, "identity": bundle["identity"],
            "before_project_sha256": old_project_sha, "project_sha256": sha(project_raw), "generation": gen, "matrix": current_pin, "binding_file": binding_pin,
            "matrix_origin": bundle["origin"], "history_metadata": history_metadata,
            "semantic_catalog": catalog_pin, "semantic_entity_ids": semantic["entity_ids"],
            "documents": current_docs, "changed_work_ids": changed, "source_step_count": len(matrix["steps"]), "source_event_count": len(matrix["events"]),
            "files": [pin(p, raw) for p, raw in sorted(files.items())]}
    meta_raw = nav.canonical(meta)
    require(len(meta_raw) <= 8 * 1024 * 1024, "IMPORT_GENERATION_METADATA_CAPACITY_EXCEEDED")
    put("IMPORT.json", meta_raw)
    directory(root, ".atlas/imports", create=True)
    stage = Path(tempfile.mkdtemp(prefix=".import-stage-", dir=root / ".atlas"))
    for rel, raw in files.items():
        target = stage / str(PurePosixPath(rel).relative_to(gen))
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    require(not (root / gen).exists(), "IMPORT_GENERATION_RACE")
    os.rename(stage, root / gen)
    nav.sync_directory(root / ".atlas/imports")
    return meta, project_raw


def reconcile(root, binding_path=".atlas/UPSTREAM.json"):
    root = Path(root).resolve()
    b = binding_model(read(root, binding_path, 512 * 1024))
    state_raw = optional_read(root, STATE, 2 * 1024 * 1024)
    pending_raw = optional_read(root, PENDING)
    doc_pending_raw = optional_read(root, DOC_PENDING)
    pointer, snapshot = atlas.current_output(root / b["output"])
    project_raw = optional_read(root, PROJECT)
    return {"status": "RECONCILE_REQUIRED" if pending_raw is not None or doc_pending_raw is not None or (root / LOCK).exists() else "READ_ONLY",
            "state": nav.parse(state_raw) if state_raw else None, "pending": nav.parse(pending_raw) if pending_raw else None,
            "doc_sync_pending": nav.parse(doc_pending_raw) if doc_pending_raw else None,
            "project_sha256": sha(project_raw) if project_raw else None, "output_current": pointer,
            "lock_present": (root / LOCK).exists(), "source_sha256": snapshot["atlas"]["source_sha256"] if snapshot else None,
            "note": "Read-only. Preserve original generation/operation identity. No lock removal, retry, repair, writer reassignment or orphan activation."}


def refresh(root, binding_path=".atlas/UPSTREAM.json", at=None):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "INVALID_ROOT")
    root = root.resolve()
    at = at or datetime.now(timezone.utc).isoformat()
    nav.stamp(at)
    binding_raw = read(root, binding_path, 512 * 1024)
    b = binding_model(binding_raw)
    require(optional_read(root, PENDING) is None, "IMPORT_PENDING_RECONCILE_REQUIRED")
    require(optional_read(root, DOC_PENDING) is None, "DOCUMENT_SYNC_PENDING_RECONCILE_REQUIRED")
    directory(root, ".atlas", create=True)
    try:
        fd = os.open(root / LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise nav.Invalid("IMPORT_LOCK_RECONCILE_REQUIRED") from exc
    os.close(fd)
    try:
        # Recheck under the common writer lock: another cooperating writer may
        # have left pending state after our first read and before acquisition.
        require(optional_read(root, PENDING) is None, "IMPORT_PENDING_RECONCILE_REQUIRED")
        require(optional_read(root, DOC_PENDING) is None, "DOCUMENT_SYNC_PENDING_RECONCILE_REQUIRED")
        state_raw = optional_read(root, STATE, 2 * 1024 * 1024)
        state = nav.parse(state_raw) if state_raw else None
        before_raw = optional_read(root, PROJECT)
        require(state is not None or before_raw is None, "EXISTING_ATLAS_NOT_ADAPTER_OWNED")
        if state:
            require(before_raw is not None and sha(before_raw) == state["project_sha256"], "PROJECTION_CHANGED_OUTSIDE_ADAPTER")
            previous_meta_raw = read(root, state["generation"] + "/IMPORT.json", 8 * 1024 * 1024)
            if "generation_meta_sha256" in state:
                require(sha(previous_meta_raw) == state["generation_meta_sha256"], "RETAINED_IMPORT_METADATA_HASH")
            previous_meta = hydrate_history_metadata(root, nav.parse(previous_meta_raw))
            if "retained_matrices" not in previous_meta:
                previous_meta["retained_matrices"] = nav.parse(before_raw).get("matrix_history", [])
                validate_history_metadata(previous_meta)
            previous_binding_raw = read(root, previous_meta["binding_file"]["path"], 512 * 1024)
            require(sha(previous_binding_raw) == state["binding_sha256"], "RETAINED_BINDING_HASH")
            verify_binding_append(binding_model(previous_binding_raw), b)
        else:
            previous_meta = None
        bundle = source_bundle(root, b, binding_raw, at, previous_meta, binding_path=binding_path)
        capacity = import_capacity(bundle, previous_meta)
        pointer, previous = atlas.current_output(root / b["output"])
        if state:
            require(pointer and pointer["manifest_sha256"] == state["output_manifest_sha256"], "IMPORT_OUTPUT_CHANGED_RECONCILE_REQUIRED")
            old_meta = previous_meta
            old_matrix_raw = read(root, old_meta["matrix"]["path"])
            require(pin(old_meta["matrix"]["path"], old_matrix_raw) == old_meta["matrix"], "RETAINED_MATRIX_HASH")
            old_matrix = nav.parse(old_matrix_raw)
            verify_append(old_matrix, bundle["matrix"])
            old_histories = {x["path"]: x["selected_sha256"] for x in old_meta["history_origins"]}
            new_histories = {h["origin"]["path"]: h["origin"]["selected_sha256"] for h in bundle["histories"]}
            require(all(new_histories.get(p) == digest for p, digest in old_histories.items()), "SOURCE_HISTORY_REWRITE_OR_REMOVAL")
            if state["fingerprint"] == bundle["fingerprint"]:
                checked = atlas.load_project(root, PROJECT, at=at)
                require(checked["atlas"]["source_sha256"] == previous["atlas"]["source_sha256"] and checked["atlas"]["toolchain_sha256"] == previous["atlas"]["toolchain_sha256"], "NO_CHANGE_SUBJECT_MISMATCH")
                current = {"status": "NO_CHANGE", "release": pointer["release"], "manifest_sha256": pointer["manifest_sha256"], "summary": checked["atlas"]["summary"], "coverage": checked["atlas"]["coverage"]}
                return {"status": "NO_CHANGE", "fingerprint": bundle["fingerprint"], "source_origin_observed_now": bundle["origin"], "changed_work_ids": [], "capacity": capacity, "cycle": current}
        else:
            require(pointer is None, "EXISTING_OUTPUT_NOT_ADAPTER_OWNED")
            old_meta = None
        old_project = nav.parse(before_raw) if before_raw else None
        meta, project_raw = stage_generation(root, b, bundle, at, old_meta, old_project, previous, pointer)
        candidate = atlas.load_project(root, meta["generation"] + "/project.json", at=meta["at"])
        if previous:
            atlas.check_history(previous, candidate)
        require(read(root, binding_path, 512 * 1024) == binding_raw and history_paths(root, b) == bundle["history_paths"], "UPSTREAM_CHANGED_DURING_IMPORT")
        require(all(read(root, p) == raw for p, raw in bundle["sources"].items()), "UPSTREAM_CHANGED_DURING_IMPORT")
        require(all(source_stat(root, p) == guard for p, guard in bundle["source_guards"].items()), "UPSTREAM_CHANGED_DURING_IMPORT")
        require(optional_read(root, PROJECT) == before_raw, "PROJECT_CAS_FAILED")
        current_pointer, _ = atlas.current_output(root / b["output"])
        require(current_pointer == pointer, "IMPORT_OUTPUT_CAS_FAILED")
        # Revalidate source bytes and CE registry at the commit boundary.
        # This is a cooperative source guard, not a same-UID hard fence.
        require(verified_ce_evidence(root,b)==bundle["ce_evidence_states"],
                "CE_EVIDENCE_CHANGED_BEFORE_COMMIT")
        pending = {"schema": "atlas.import-pending/v1", "fingerprint": bundle["fingerprint"], "generation": meta["generation"],
                   "before_project_sha256": sha(before_raw) if before_raw else None, "after_project_sha256": sha(project_raw),
                   "before_output_manifest_sha256": pointer["manifest_sha256"] if pointer else None}
        # IMPORT.lock serializes cooperating projection writers. The comparisons
        # above plus os.replace are not an OS compare-and-swap against an external
        # writer that ignores the lock; PROJECT belongs exclusively to this adapter.
        atomic(root, PENDING, nav.canonical(pending))
        atomic(root, PROJECT, project_raw)
        try:
            built = atlas.cycle(root, PROJECT, root / b["output"], at=meta["at"], previous=pointer["manifest_sha256"] if pointer else None)
        except (nav.Invalid, OSError):
            # Roll back only if exact output readback confirms no publication effect.
            observed, _ = atlas.current_output(root / b["output"])
            if observed == pointer and optional_read(root, PROJECT) == project_raw:
                if before_raw is None:
                    (root / PROJECT).unlink()
                else:
                    atomic(root, PROJECT, before_raw)
                (root / PENDING).unlink()
            raise
        next_state = {"schema": "atlas.import-state/v1", "fingerprint": bundle["fingerprint"], "generation": meta["generation"],
                      "binding_sha256": sha(binding_raw), "project_sha256": sha(project_raw), "output_manifest_sha256": built["manifest_sha256"],
                      "generation_meta_sha256": sha(nav.canonical(meta))}
        atomic(root, STATE, nav.canonical(next_state))
        (root / PENDING).unlink()
        nav.sync_directory(root / ".atlas")
        return {"status": "IMPORTED_PARTIAL", "fingerprint": bundle["fingerprint"], "generation": meta["generation"],
                "source_step_count": meta["source_step_count"], "source_event_count": meta["source_event_count"],
                "changed_work_ids": meta["changed_work_ids"], "matrix_history_count": meta["history_metadata"]["retained_matrices"]["count"],
                "matrix_history_page_count": len(candidate["atlas"]["matrix_history"]),
                "capacity": capacity,
                "semantic_counts": {k: len(candidate["input"][k]) for k in ("documents", "modules", "contracts", "relations")},
                "source_origin": bundle["origin"], "cycle": built,
                "note": "Owning inputs retained; no product acceptance or current activity inferred. Existing matrix/docs were not modified."}
    finally:
        (root / LOCK).unlink()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("refresh", "reconcile", "history-requalify", "history-requalification-status"))
    p.add_argument("--root", required=True)
    p.add_argument("--binding", default=".atlas/UPSTREAM.json")
    p.add_argument("--at")
    p.add_argument("--operation")
    p.add_argument("--cursor", type=int, default=0)
    args = p.parse_args()
    try:
        if args.command.startswith("history-requalif"):
            import history_requalification
            result = history_requalification.requalify(args.root, args.operation, args.binding, args.cursor,
                                                       read_only=args.command == "history-requalification-status")
        else:
            result = refresh(args.root, args.binding, args.at) if args.command == "refresh" else reconcile(args.root, args.binding)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (nav.Invalid, OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "REFUSED", "code": str(exc) if isinstance(exc, nav.Invalid) else type(exc).__name__}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
