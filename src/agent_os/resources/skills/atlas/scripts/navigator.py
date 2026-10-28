"""DN-01.2: explicit local documents -> immutable offline navigator. No network."""
import argparse
import copy
import hashlib
import html
import json
import math
import os
import re
import stat
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath

VERSION = "DN-01.4"
MAX_DOCUMENTS = 1000
MAX_FILE = 2 * 1024 * 1024
# Owner-local finite capacity successor: full bodies, per-file and output guards
# remain unchanged. This engineering envelope is not a security scan waiver.
MAX_TOTAL = 16 * 1024 * 1024
MAX_INPUT = 8 * 1024 * 1024
MAX_HTML = 48 * 1024 * 1024
MAX_SNAPSHOT = 32 * 1024 * 1024
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,99}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


class Invalid(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Invalid(code)


def canonical(value):
    json_safe(value)
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise Invalid("INVALID_JSON_VALUE") from exc


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def json_safe(value):
    """Reject values JSON can parse but which cannot be published as strict UTF-8."""
    try:
        if isinstance(value, str):
            value.encode("utf-8", errors="strict")
        elif isinstance(value, dict):
            for key, item in value.items():
                require(isinstance(key, str), "JSON_OBJECT_KEY")
                json_safe(key); json_safe(item)
        elif isinstance(value, list):
            for item in value: json_safe(item)
        elif isinstance(value, float):
            require(math.isfinite(value), "NONFINITE_JSON")
        else:
            require(value is None or type(value) in (int, bool), "INVALID_JSON_VALUE")
    except UnicodeError as exc:
        raise Invalid("INVALID_UTF8_JSON") from exc
    except RecursionError as exc:
        raise Invalid("INVALID_JSON_DEPTH") from exc


def parse(data):
    try:
        require(isinstance(data, (str, bytes, bytearray)), "INVALID_UTF8_JSON")
        if isinstance(data, (bytes, bytearray)): data = data.decode("utf-8", errors="strict")
        value = json.loads(data, object_pairs_hook=unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(Invalid("NONFINITE_JSON")))
        json_safe(value)
        return value
    except Invalid:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise Invalid("INVALID_UTF8_JSON") from exc


def shape(value, fields, where):
    require(isinstance(value, dict) and set(value) == set(fields.split()), "SHAPE:" + where)


def text(value, where):
    require(isinstance(value, str) and 0 < len(value) <= 20000 and "\x00" not in value, "TEXT:" + where)


def ident(value):
    require(isinstance(value, str) and ID.fullmatch(value), "INVALID_ID")


def stamp(value):
    try:
        text(value, "timestamp")
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.utcoffset() is not None, "TIMESTAMP_TIMEZONE")
        return result
    except ValueError as exc:
        raise Invalid("INVALID_TIMESTAMP") from exc


def array(value, where, limit=1000):
    require(isinstance(value, list) and len(value) <= limit, "ARRAY:" + where)
    return value


def refs(value, allowed, where, limit=1000):
    array(value, where, limit)
    require(all(isinstance(x, str) and x in allowed for x in value), "DANGLING:" + where)
    require(len(value) == len(set(value)), "DUPLICATE_REF:" + where)


def structural(value, schema, definitions, where="input"):
    """Validate only the fixed schema's supported structural keywords; semantic refs below."""
    if "$ref" in schema:
        return structural(value, definitions[schema["$ref"].split("/")[-1]], definitions, where)
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try: structural(value, option, definitions, where); return
            except Invalid: pass
        raise Invalid("SCHEMA_TYPE:" + where)
    if "enum" in schema: require(value in schema["enum"], "SCHEMA_ENUM:" + where)
    if "const" in schema: require(value == schema["const"], "SCHEMA_CONST:" + where)
    kind = schema.get("type")
    if kind == "object":
        require(isinstance(value, dict), "SCHEMA_OBJECT:" + where)
        props = schema["properties"]
        require(set(schema["required"]) <= set(value) and not (set(value) - set(props)), "SCHEMA_FIELDS:" + where)
        for key, item in value.items(): structural(item, props[key], definitions, where + "." + key)
    elif kind == "array":
        require(isinstance(value, list) and schema.get("minItems", 0) <= len(value) <= schema["maxItems"], "SCHEMA_ARRAY:" + where)
        for item in value: structural(item, schema["items"], definitions, where + "[]")
    elif kind == "string":
        require(isinstance(value, str), "SCHEMA_STRING:" + where)
        require(schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 20000), "SCHEMA_LENGTH:" + where)
        if "pattern" in schema: require(re.fullmatch(schema["pattern"], value), "SCHEMA_PATTERN:" + where)
    elif kind == "integer":
        require(type(value) is int and schema["minimum"] <= value <= schema["maximum"], "SCHEMA_INTEGER:" + where)
    elif kind == "boolean": require(type(value) is bool, "SCHEMA_BOOLEAN:" + where)
    elif kind == "null": require(value is None, "SCHEMA_NULL:" + where)


def safe(root, relative, *, directory=False):
    require(isinstance(relative, str) and relative and "\\" not in relative and "\x00" not in relative, "UNSAFE_PATH")
    p = PurePosixPath(relative)
    require(not p.is_absolute() and all(s not in ("", ".", "..") for s in relative.split("/")), "UNSAFE_PATH")
    current = root
    for part in p.parts:
        current = current / part
        require(not current.is_symlink(), "SYMLINK_PATH")
    require(current.is_dir() if directory else current.is_file(), "MISSING_SELECTED_PATH")
    require(current.resolve().is_relative_to(root), "PATH_ESCAPE")
    return current


def read_selected(root, relative, limit=MAX_FILE):
    p = safe(root, relative)
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "NOT_REGULAR_FILE")
        data = stream.read(limit + 1)
    require(len(data) <= limit, "FILE_LIMIT")
    return data


def load(root, manifest, *, _source_context=None, _source_operation=None):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "INVALID_ROOT")
    root = root.resolve()
    from source_relocation import Context
    source_context = _source_context or Context(root, _source_operation)
    require(isinstance(source_context, Context) and source_context.root == root, "SOURCE_CONTEXT_IDENTITY")
    # A 1000-card API catalogue can exceed 512 KiB while all selected documents
    # remain bounded. Keep a separate explicit input-model budget; selected file
    # budgets below and the published snapshot/HTML budgets still apply.
    raw = read_selected(root, manifest, MAX_INPUT)
    model = parse(raw)
    schema = parse((Path(__file__).resolve().parent / "navigator.schema.json").read_bytes())
    structural(model, schema, schema["$defs"])
    shape(model, "schema project release documents modules contracts relations matrix bindings history", "input")
    require(model["schema"] == "docs-navigator.input/v1", "INPUT_SCHEMA")
    shape(model["project"], "id title" + (" scope_note" if "scope_note" in model["project"] else ""), "project")
    ident(model["project"]["id"]); text(model["project"]["title"], "project.title")
    if "scope_note" in model["project"]: text(model["project"]["scope_note"], "project.scope_note")
    shape(model["release"], "id created_at previous", "release")
    ident(model["release"]["id"])
    created = stamp(model["release"]["created_at"])
    previous = model["release"]["previous"]
    require(previous is None or isinstance(previous, str) and SHA.fullmatch(previous), "PREVIOUS_SHA")
    documents = array(model["documents"], "documents", MAX_DOCUMENTS)
    require(documents, "NO_DOCUMENTS")
    ids = set(); total = 0; loaded = []
    for doc in documents:
        shape(doc, "id title path kind version lifecycle sha256 bytes source_ref readback_at evidence_state execution" + (" storage" if "storage" in doc else ""), "document")
        ident(doc["id"]); require(doc["id"] not in ids, "DUPLICATE_ID"); ids.add(doc["id"])
        for key in ("title", "version", "source_ref"): text(doc[key], "doc." + key)
        require(doc["lifecycle"] in ("current", "archived"), "LIFECYCLE")
        require(doc["evidence_state"] in ("FACT", "DESIGN", "UNKNOWN"), "EVIDENCE_STATE")
        require(doc["execution"] in ("NOT_RUN", "STATIC_CHECKED", "VERIFIED"), "EXECUTION_STATE")
        require(isinstance(doc["sha256"], str) and SHA.fullmatch(doc["sha256"]), "INVALID_SHA")
        require(type(doc["bytes"]) is int and 0 <= doc["bytes"] <= MAX_FILE, "DECLARED_BYTES")
        ext = PurePosixPath(doc["path"]).suffix.lower()
        require(ext in (".json", ".md", ".txt", ".yaml", ".yml"), "DOCUMENT_EXTENSION")
        require(doc["kind"] in ("json", "schema", "markdown", "text", "yaml"), "DOCUMENT_KIND")
        require(doc["kind"] not in ("json", "schema") or ext == ".json", "KIND_EXTENSION")
        require(stamp(doc["readback_at"]) <= created, "READBACK_AFTER_RELEASE")
        raw_doc = source_context.read(doc, document=True)[0] if "storage" in doc else read_selected(root, doc["path"])
        require(len(raw_doc) == doc["bytes"] and digest(raw_doc) == doc["sha256"], "DOCUMENT_HASH:" + doc["id"])
        total += len(raw_doc); require(total <= MAX_TOTAL, "TOTAL_LIMIT")
        try: content = raw_doc.decode("utf-8")
        except UnicodeError as exc: raise Invalid("DOCUMENT_UTF8") from exc
        require("\x00" not in content, "DOCUMENT_NUL")
        if doc["kind"] in ("json", "schema"): parse(raw_doc)
        loaded.append({**doc, "content": content})
    doc_ids = {d["id"] for d in documents}
    modules = array(model["modules"], "modules", 200)
    contracts = array(model["contracts"], "contracts", 1000)
    for item in modules + contracts:
        require(isinstance(item, dict), "ENTITY_OBJECT"); ident(item.get("id"))
        require(item["id"] not in ids, "DUPLICATE_ID"); ids.add(item["id"])
    module_ids = {m["id"] for m in modules}; contract_ids = {c["id"] for c in contracts}
    for m in modules:
        shape(m, "id title purpose state_owner dependencies docs", "module")
        for key in ("title", "purpose", "state_owner"): text(m[key], "module." + key)
        refs(m["docs"], doc_ids, "module.docs"); refs(m["dependencies"], module_ids, "module.dependencies")
        require(m["docs"], "MISSING_MODULE_PROVENANCE")
    current_keys = set()
    for c in contracts:
        shape(c, "id contract_key title version lifecycle module state_owner input output parameters errors auth dependencies usage docs evidence_state execution", "contract")
        ident(c["contract_key"])
        for key in ("title", "version", "state_owner", "input", "output", "auth", "usage"): text(c[key], "contract." + key)
        require(c["module"] in module_ids, "DANGLING:contract.module")
        require(c["lifecycle"] in ("current", "archived"), "LIFECYCLE")
        require(c["evidence_state"] in ("FACT", "DESIGN", "UNKNOWN"), "EVIDENCE_STATE")
        require(c["execution"] in ("NOT_RUN", "STATIC_CHECKED", "VERIFIED"), "EXECUTION_STATE")
        if c["lifecycle"] == "current":
            require(c["contract_key"] not in current_keys, "MULTIPLE_CURRENT_CONTRACT"); current_keys.add(c["contract_key"])
        refs(c["docs"], doc_ids, "contract.docs"); refs(c["dependencies"], contract_ids, "contract.dependencies")
        require(c["docs"], "MISSING_CONTRACT_PROVENANCE")
        for p in array(c["parameters"], "parameters", 200):
            shape(p, "name type required description", "parameter")
            for key in ("name", "type", "description"): text(p[key], "parameter." + key)
            require(type(p["required"]) is bool or p["required"] == "UNKNOWN", "PARAMETER_REQUIRED")
        for e in array(c["errors"], "errors", 200):
            shape(e, "code meaning", "error"); text(e["code"], "error.code"); text(e["meaning"], "error.meaning")
    seen_edges = set()
    for edge in array(model["relations"], "relations", 2000):
        shape(edge, "from to type evidence_docs", "relation")
        require(edge["from"] in ids and edge["to"] in ids, "DANGLING:relation")
        require(edge["type"] in ("uses", "implements", "emits", "consumes", "depends_on", "describes"), "RELATION_TYPE")
        refs(edge["evidence_docs"], doc_ids, "relation.evidence_docs")
        require(edge["evidence_docs"], "MISSING_RELATION_PROVENANCE")
        key = (edge["from"], edge["to"], edge["type"])
        require(key not in seen_edges, "DUPLICATE_EDGE"); seen_edges.add(key)
    shape(model["matrix"], "doc", "matrix")
    matrix = None
    if model["matrix"]["doc"] is not None:
        require(model["matrix"]["doc"] in doc_ids, "DANGLING:matrix.doc")
        selected = next(d for d in loaded if d["id"] == model["matrix"]["doc"])
        require(selected["kind"] == "json", "MATRIX_KIND")
        matrix = parse(selected["content"])
        shape(matrix, "schema dataset_id steps events", "matrix snapshot")
        require(matrix["schema"] == "docs-navigator.matrix-refs/v1", "MATRIX_SCHEMA"); ident(matrix["dataset_id"])
        step_ids = set(); event_ids = set()
        for step in array(matrix["steps"], "matrix.steps"):
            shape(step, "id title", "matrix.step"); ident(step["id"]); text(step["title"], "step.title")
            require(step["id"] not in step_ids, "DUPLICATE_MATRIX_STEP"); step_ids.add(step["id"])
        previous_event = None
        for event in array(matrix["events"], "matrix.events"):
            shape(event, "id at title step_ids", "matrix.event"); ident(event["id"]); text(event["title"], "event.title")
            require(event["id"] not in event_ids, "DUPLICATE_MATRIX_EVENT"); event_ids.add(event["id"])
            event_at = stamp(event["at"])
            require(event_at <= created and (previous_event is None or previous_event <= event_at), "MATRIX_EVENT_TIME_ORDER")
            require(event_at <= stamp(selected["readback_at"]), "MATRIX_EVENT_AFTER_READBACK")
            previous_event = event_at
            refs(event["step_ids"], step_ids, "matrix.event.steps")
    else: step_ids = set(); event_ids = set()
    bound = set()
    for binding in array(model["bindings"], "bindings"):
        shape(binding, "entity_id step_ids event_ids", "binding")
        require(binding["entity_id"] in ids, "DANGLING:binding.entity")
        require(binding["entity_id"] not in bound, "DUPLICATE_BINDING"); bound.add(binding["entity_id"])
        refs(binding["step_ids"], step_ids, "binding.steps"); refs(binding["event_ids"], event_ids, "binding.events")
    history_ids = set(); last = None
    for event in array(model["history"], "history", 2000):
        shape(event, "id at kind summary entity_ids", "history")
        ident(event["id"]); require(event["id"] not in history_ids, "DUPLICATE_HISTORY"); history_ids.add(event["id"])
        when = stamp(event["at"]); require(when <= created and (last is None or when >= last), "HISTORY_TIME_ORDER"); last = when
        text(event["kind"], "history.kind"); text(event["summary"], "history.summary"); refs(event["entity_ids"], ids, "history.entities")
    return {"template_version": VERSION, "input_sha256": digest(raw), "input": model, "documents": loaded, "matrix_snapshot": matrix, "retained_source_pins": [{"path":p,"sha256":digest(b),"bytes":len(b)} for p,b in sorted(source_context.source_pins.items())]}


def check_history(previous, current):
    a = previous["input"]; b = current["input"]
    require(a["project"]["id"] == b["project"]["id"], "PROJECT_CHANGED")
    require(stamp(a["release"]["created_at"]) <= stamp(b["release"]["created_at"]), "RELEASE_TIME_ORDER")
    require(b["history"][:len(a["history"])] == a["history"], "HISTORY_REWRITE")
    old_matrix = previous["matrix_snapshot"]; new_matrix = current["matrix_snapshot"]
    if old_matrix:
        require(new_matrix and old_matrix["dataset_id"] == new_matrix["dataset_id"], "MATRIX_HISTORY_REMOVED")
        for category in ("steps", "events"):
            require(new_matrix[category][:len(old_matrix[category])] == old_matrix[category], "MATRIX_HISTORY_REWRITE")
    for category in ("documents", "contracts"):
        after = {x["id"]: x for x in b[category]}
        for old in a[category]:
            require(old["id"] in after, "HISTORY_MEMBER_REMOVED")
            newer = copy.deepcopy(after[old["id"]]); older = copy.deepcopy(old)
            require(older["lifecycle"] != "archived" or newer["lifecycle"] == "archived", "ARCHIVE_REACTIVATED")
            older.pop("lifecycle"); newer.pop("lifecycle")
            if "storage" in older or "storage" in newer:
                require(category == "documents", "CONTRACT_STORAGE_NOT_SUPPORTED")
                require("storage" not in older or older["storage"] == newer.get("storage"), "HISTORICAL_STORAGE_REWRITE")
                require(after[old["id"]]["lifecycle"] == "archived", "STORAGE_CURRENT_DOCUMENT")
                older.pop("storage", None); newer.pop("storage", None)
            require(older == newer, "HISTORICAL_MEMBER_REWRITE")
    require(len(b["history"]) > len(a["history"]), "NEW_HISTORY_EVENT_REQUIRED")


def render(snapshot):
    base = Path(__file__).resolve().parent
    js = (base / "viewer.js").read_text(encoding="utf-8"); css = (base / "viewer.css").read_text(encoding="utf-8")
    data = canonical(snapshot).decode().replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    import base64
    script_hash = base64.b64encode(hashlib.sha256(js.encode()).digest()).decode()
    title = html.escape(snapshot["input"]["project"]["title"])
    suffix = "Матрица работ и контракты проекта" if snapshot.get("atlas") else "Документы и контракты"
    language = "ru"
    return (f'<!doctype html><html lang="{language}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'sha256-{script_hash}\'; base-uri \'none\'; form-action \'none\'">'
            f'<title>{title} · {suffix}</title><style>{css}</style><body>'
            '<header><div class="eyebrow">ДОКУМЕНТЫ · КОНТРАКТЫ · СВЯЗИ</div><h1 id="title"></h1><p id="release"></p><p id="scope" class="note"></p></header>'
            '<section class="toolbar" aria-label="Фильтры"><label>Поиск<input id="search" type="search" placeholder="Текст, ID, параметр…"></label>'
            '<label>Версии<select id="lifecycle"><option value="current">Текущие</option><option value="archived">Архив</option><option value="all">Все версии</option></select></label>'
            '<button id="reset">Сбросить фильтры</button><button id="download">Скачать индекс JSON</button></section>'
            '<nav id="tabs" aria-label="Разделы"></nav><div class="workspace"><aside><h2>Модули</h2><div id="modules"></div><p class="note">Выбранные файлы закреплены SHA. Эти записи не подтверждают работу системы или приёмку.</p></aside>'
            '<main tabindex="-1"><p id="summary" role="status" aria-live="polite"></p><div id="list"></div></main><section id="detail" tabindex="-1" aria-label="Выбранный объект"></section></div>'
            '<noscript>Для поиска и навигации включите JavaScript в разрешённом окружении. Полный машиночитаемый snapshot.json сохранён в неизменяемом выпуске и доступен для отдельной выгрузки.</noscript>'
            f'<script type="application/json" id="navigator-data">{data}</script><script>{js}</script></body></html>').encode()


def verify_release(out, release_id, expected=None):
    out = Path(out).absolute()
    for parent in (out, *out.parents): require(not parent.is_symlink(), "OUTPUT_SYMLINK")
    require(out.is_dir(), "OUTPUT_ROOT_DIRECTORY")
    out = out.resolve()
    ident(release_id)
    require(expected is None or isinstance(expected, str) and SHA.fullmatch(expected), "OUTPUT_EXPECTED_SHA")
    release_dir = safe(out, f"releases/{release_id}", directory=True)
    expected_names = {"index.html", "snapshot.json", "MANIFEST.json"}
    with os.scandir(release_dir) as entries:
        found = set()
        for entry in entries:
            require(entry.name in expected_names and not entry.is_symlink() and entry.is_file(follow_symlinks=False), "OUTPUT_EXTRA_OR_LINKED_MEMBER")
            found.add(entry.name)
    require(found == expected_names, "OUTPUT_MISSING_MEMBER")
    raw = read_selected(out, f"releases/{release_id}/MANIFEST.json", 512 * 1024)
    require(expected is None or digest(raw) == expected, "OUTPUT_MANIFEST_HASH")
    m = parse(raw)
    shape(m, "schema release template_version input_sha256 files", "output manifest")
    require(m["schema"] == "docs-navigator.output/v1" and m["release"] == release_id, "OUTPUT_MANIFEST_SCHEMA")
    text(m["template_version"], "output.template_version")
    require(isinstance(m["input_sha256"], str) and SHA.fullmatch(m["input_sha256"]), "OUTPUT_INPUT_SHA")
    shape(m["files"], "index.html snapshot.json", "output files")
    contents = {}
    for name, pin in m["files"].items():
        shape(pin, "sha256 bytes", "output pin")
        limit = MAX_HTML if name == "index.html" else MAX_SNAPSHOT
        require(isinstance(pin["sha256"], str) and SHA.fullmatch(pin["sha256"]), "OUTPUT_PIN_SHA")
        require(type(pin["bytes"]) is int and 0 <= pin["bytes"] <= limit, "OUTPUT_PIN_BYTES")
        data = read_selected(out, f"releases/{release_id}/{name}", limit)
        require(len(data) == pin["bytes"] and digest(data) == pin["sha256"], "OUTPUT_FILE_HASH")
        contents[name] = data
    snapshot = parse(contents["snapshot.json"])
    snapshot_header(snapshot)
    require(snapshot["input"]["release"]["id"] == release_id and snapshot["input_sha256"] == m["input_sha256"], "OUTPUT_RELEASE_BINDING")
    require(snapshot["template_version"] == m["template_version"], "OUTPUT_TEMPLATE_BINDING")
    return digest(raw), snapshot


def snapshot_header(snapshot):
    """Validate shared publishing fields without closing extension namespaces."""
    require(isinstance(snapshot, dict) and {"template_version", "input_sha256", "input"} <= set(snapshot), "SNAPSHOT_HEADER")
    text(snapshot["template_version"], "snapshot.template_version")
    require(isinstance(snapshot["input_sha256"], str) and SHA.fullmatch(snapshot["input_sha256"]), "SNAPSHOT_INPUT_SHA")
    model = snapshot["input"]
    require(isinstance(model, dict) and {"project", "release"} <= set(model), "SNAPSHOT_INPUT")
    require(isinstance(model["project"], dict) and "id" in model["project"], "SNAPSHOT_PROJECT")
    ident(model["project"]["id"])
    shape(model["release"], "id created_at previous", "snapshot.release")
    ident(model["release"]["id"]); stamp(model["release"]["created_at"])
    previous = model["release"]["previous"]
    require(previous is None or isinstance(previous, str) and SHA.fullmatch(previous), "PREVIOUS_SHA")


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _current_view_root(output):
    out = Path(output).absolute()
    for parent in (out, *out.parents): require(not parent.is_symlink(), "OUTPUT_SYMLINK")
    require(not out.exists() or out.is_dir(), "OUTPUT_ROOT_DIRECTORY")
    return out.resolve()


def _current_view_pointer(out):
    require(not (out / "CURRENT.json").is_symlink(), "OUTPUT_SYMLINK")
    if not (out / "CURRENT.json").exists(): return None
    pointer = parse(read_selected(out, "CURRENT.json", 16384))
    shape(pointer, "schema release manifest_sha256", "pointer")
    require(pointer["schema"] == "docs-navigator.current/v1", "POINTER_SCHEMA")
    ident(pointer["release"])
    require(isinstance(pointer["manifest_sha256"], str) and SHA.fullmatch(pointer["manifest_sha256"]), "POINTER_SHA")
    return pointer


def _current_view_alias(out):
    require(not (out / "index.html").is_symlink(), "CURRENT_VIEW_SYMLINK")
    return read_selected(out, "index.html", MAX_HTML) if (out / "index.html").exists() else None


def _current_view_state(out, expected_release, expected_manifest_sha256):
    require((expected_release is None) == (expected_manifest_sha256 is None), "CURRENT_VIEW_EXPECTED_PIN")
    if expected_release is not None:
        ident(expected_release)
        require(isinstance(expected_manifest_sha256, str) and SHA.fullmatch(expected_manifest_sha256), "CURRENT_VIEW_EXPECTED_PIN")
    pointer = _current_view_pointer(out)
    receipt = {"schema": "atlas.current-view/v1", "status": "NO_CURRENT", "path": str(out / "index.html"),
               "immutable_path": None, "release": None, "manifest_sha256": None, "sha256": None, "bytes": None,
               "observed_sha256": None, "observed_bytes": None,
               "expected_release": expected_release, "expected_manifest_sha256": expected_manifest_sha256}
    if pointer is None:
        if expected_release is not None: receipt["status"] = "CURRENT_CHANGED"
        return receipt, None, None, None
    _, snapshot = verify_release(out, pointer["release"], pointer["manifest_sha256"])
    prefix = "releases/" + pointer["release"] + "/"
    manifest_raw = read_selected(out, prefix + "MANIFEST.json", 512 * 1024)
    require(digest(manifest_raw) == pointer["manifest_sha256"], "OUTPUT_MANIFEST_HASH")
    manifest = parse(manifest_raw)
    payload = read_selected(out, prefix + "index.html", MAX_HTML)
    pin = manifest["files"]["index.html"]
    require(len(payload) == pin["bytes"] and digest(payload) == pin["sha256"], "OUTPUT_FILE_HASH")
    alias = _current_view_alias(out)
    receipt.update({"immutable_path": str(out / prefix / "index.html"), "release": pointer["release"],
                    "manifest_sha256": pointer["manifest_sha256"], "sha256": pin["sha256"], "bytes": pin["bytes"],
                    "observed_sha256": digest(alias) if alias is not None else None,
                    "observed_bytes": len(alias) if alias is not None else None,
                    "status": "MISSING" if alias is None else "CURRENT" if alias == payload else "STALE"})
    if expected_release is not None and (pointer["release"] != expected_release or pointer["manifest_sha256"] != expected_manifest_sha256):
        receipt["status"] = "CURRENT_CHANGED"
    return receipt, payload, alias, snapshot


def current_view_status(output, *, expected_release=None, expected_manifest_sha256=None):
    """Read one verified CURRENT and compare its stable HTML, without repairing it.

    CURRENT_CHANGED distinguishes a different captured pointer from a stale copy.
    A CURRENT receipt is anchored to this read; it makes no claim about later writes
    or newer owning-source data that has not been published.
    """
    return _current_view_state(_current_view_root(output), expected_release, expected_manifest_sha256)[0]


def _current_view_owned(out, alias, project_id, known_release=None):
    """Only a byte-exact retained release may be replaced at the managed entry."""
    if alias is None: return
    if known_release is not None:
        _, retained = verify_release(out, known_release)
        require(retained["input"]["project"]["id"] == project_id, "CURRENT_VIEW_PROJECT_MISMATCH")
        if alias == read_selected(out, "releases/" + known_release + "/index.html", MAX_HTML): return known_release
    matches = list(re.finditer(rb'<script type="application/json" id="navigator-data">([^<]*)</script>', alias))
    require(len(matches) == 1, "CURRENT_VIEW_UNMANAGED_INDEX")
    try:
        embedded = parse(matches[0].group(1)); snapshot_header(embedded)
        release = embedded["input"]["release"]["id"]
        require(embedded["input"]["project"]["id"] == project_id, "CURRENT_VIEW_PROJECT_MISMATCH")
        _, retained = verify_release(out, release)
        require(retained["input"]["project"]["id"] == project_id, "CURRENT_VIEW_PROJECT_MISMATCH")
        known = read_selected(out, "releases/" + release + "/index.html", MAX_HTML)
        require(alias == known, "CURRENT_VIEW_UNMANAGED_INDEX")
        return release
    except (Invalid, KeyError, TypeError) as exc:
        raise Invalid("CURRENT_VIEW_UNMANAGED_INDEX") from exc


def _publish_current_view_locked(out, expected_release, expected_manifest_sha256, known_view_release=None):
    receipt, payload, alias, snapshot = _current_view_state(out, expected_release, expected_manifest_sha256)
    require(receipt["status"] not in ("NO_CURRENT", "CURRENT_CHANGED"), "CURRENT_CHANGED")
    if receipt["status"] == "CURRENT": return {**receipt, "outcome": "NO_CHANGE"}
    _current_view_owned(out, alias, snapshot["input"]["project"]["id"], known_view_release)
    fd, name = tempfile.mkstemp(prefix=".current-view-", dir=out)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        current = _current_view_pointer(out)
        require(current is not None and current["release"] == expected_release and current["manifest_sha256"] == expected_manifest_sha256, "CURRENT_CHANGED")
        require(_current_view_alias(out) == alias, "CURRENT_VIEW_CONCURRENT_MODIFICATION")
        os.replace(name, out / "index.html")
        sync_directory(out)
    finally:
        if os.path.exists(name): os.unlink(name)
    final = current_view_status(out, expected_release=expected_release, expected_manifest_sha256=expected_manifest_sha256)
    require(final["status"] == "CURRENT", "CURRENT_VIEW_READBACK")
    return {**final, "outcome": "PUBLISHED" if alias is None else "REPAIRED"}


def publish_current_view(output, *, expected_release, expected_manifest_sha256):
    """Explicitly repair only the exact selected CURRENT through the publish lock.

    A matching view returns without touching files. Missing or stale managed views
    are copied atomically; unrelated files, links and changed pointers are refused.
    """
    require(expected_release is not None and expected_manifest_sha256 is not None, "CURRENT_VIEW_EXPECTED_PIN")
    out = _current_view_root(output)
    receipt, _, _, _ = _current_view_state(out, expected_release, expected_manifest_sha256)
    require(receipt["status"] not in ("NO_CURRENT", "CURRENT_CHANGED"), "CURRENT_CHANGED")
    if receipt["status"] == "CURRENT": return {**receipt, "outcome": "NO_CHANGE"}
    lock = out / ".writer.lock"
    try: fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc: raise Invalid("WRITER_LOCK_RECONCILE_REQUIRED") from exc
    try:
        os.close(fd)
        return _publish_current_view_locked(out, expected_release, expected_manifest_sha256)
    finally:
        lock.unlink()


def build(root, manifest, output):
    snapshot = load(root, manifest)
    return publish(snapshot, output)


class _PublishLease:
    """Live in-memory ownership of the existing output .writer.lock inode."""
    def __init__(self, output):
        self.out = Path(output).absolute()
        self.fd = None

    def acquire(self):
        for parent in (self.out, *self.out.parents): require(not parent.is_symlink(), "OUTPUT_SYMLINK")
        self.out.mkdir(parents=True, exist_ok=True); self.out = self.out.resolve()
        try: self.fd = os.open(self.out / ".writer.lock", os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError as exc: raise Invalid("WRITER_LOCK_RECONCILE_REQUIRED") from exc
        self.identity = os.fstat(self.fd)
        return self

    def check(self, output=None):
        require(self.fd is not None and (output is None or self.out == Path(output).resolve()), "WRITER_LEASE_IDENTITY")
        path = self.out / ".writer.lock"
        require(not path.is_symlink() and path.is_file(), "WRITER_LOCK_CHANGED")
        own, current = os.fstat(self.fd), path.stat()
        require(stat.S_ISREG(own.st_mode) and (own.st_dev,own.st_ino) == (current.st_dev,current.st_ino)
                == (self.identity.st_dev,self.identity.st_ino), "WRITER_LOCK_CHANGED")

    def tag(self, value):
        self.check(); raw=canonical(value); os.lseek(self.fd,0,os.SEEK_SET); os.ftruncate(self.fd,0)
        require(os.write(self.fd,raw)==len(raw), "WRITER_LOCK_TAG"); os.fsync(self.fd)

    def release(self):
        if self.fd is None: return
        try:
            self.check(); (self.out / ".writer.lock").unlink(); sync_directory(self.out)
        finally:
            os.close(self.fd); self.fd=None


def publish(snapshot, output, *, render_fn=render, history_fn=check_history, version=VERSION, _lease=None, _source_guard=None, _source_orphan=None):
    """Publish a validated snapshot; callers may extend rendering and history semantics.

    The caller owns semantic validation of extension namespaces before publishing.
    This function enforces common immutable output, lineage and JSON integrity.
    """
    json_safe(snapshot); snapshot_header(snapshot)
    text(version, "publish.version")
    require(snapshot["template_version"] == version, "PUBLISH_TEMPLATE_BINDING")
    out = Path(output).absolute()
    for parent in (out, *out.parents): require(not parent.is_symlink(), "OUTPUT_SYMLINK")
    out.mkdir(parents=True, exist_ok=True); out = out.resolve()
    owned_lease = _lease is None
    lease = _PublishLease(out).acquire() if owned_lease else _lease
    require(isinstance(lease, _PublishLease), "WRITER_LEASE_IDENTITY")
    lease.check(out)
    try:
        if _source_guard is not None: _source_guard()
        require(not (out / "CURRENT.json").is_symlink(), "OUTPUT_SYMLINK")
        pointer_exists = (out / "CURRENT.json").exists()
        current = parse(read_selected(out, "CURRENT.json", 16384)) if pointer_exists else None
        if pointer_exists:
            shape(current, "schema release manifest_sha256", "pointer")
            require(current["schema"] == "docs-navigator.current/v1", "POINTER_SCHEMA")
            require(isinstance(current["manifest_sha256"], str) and SHA.fullmatch(current["manifest_sha256"]), "POINTER_SHA")
            current_sha, previous = verify_release(out, current["release"], current["manifest_sha256"])
        else: current_sha = None; previous = None
        releases = out / "releases"; require(not releases.is_symlink(), "OUTPUT_SYMLINK")
        if releases.exists():
            require(releases.is_dir(), "OUTPUT_RELEASES_DIRECTORY")
            if not pointer_exists:
                require(not any(releases.iterdir()), "ORPHAN_RECONCILE_ONLY")
        release = snapshot["input"]["release"]["id"]
        # Refuse an unrelated stable entry before committing a new release/pointer.
        known_view_release = _current_view_owned(out, _current_view_alias(out), snapshot["input"]["project"]["id"], current["release"] if current else None)
        payload = {"index.html": render_fn(snapshot), "snapshot.json": canonical(snapshot)}
        require(isinstance(payload["index.html"], bytes), "RENDER_BYTES_REQUIRED")
        require(len(payload["index.html"]) <= MAX_HTML and len(payload["snapshot.json"]) <= MAX_SNAPSHOT, "OUTPUT_LIMIT")
        m = {"schema": "docs-navigator.output/v1", "release": release, "template_version": version,
             "input_sha256": snapshot["input_sha256"], "files": {n: {"sha256": digest(b), "bytes": len(b)} for n, b in payload.items()}}
        raw_manifest = canonical(m); manifest_sha = digest(raw_manifest)
        releases.mkdir(exist_ok=True)
        target = releases / release
        existing_target = target.exists() or target.is_symlink()
        if existing_target:
            found_sha, _ = verify_release(out, release)
            require(found_sha == manifest_sha, "RELEASE_COLLISION")
            if pointer_exists and current["release"] == release and current_sha == manifest_sha:
                view = _publish_current_view_locked(out, release, manifest_sha, known_view_release)
                return {"status": "RECONCILED_IDENTICAL", "release": release, "manifest_sha256": manifest_sha,
                        "view_path": view["path"], "current_view": view}
            from source_relocation import _OrphanProof
            require(isinstance(_source_orphan, _OrphanProof), "ORPHAN_RECONCILE_ONLY")
            _source_orphan.check(out, snapshot, release, manifest_sha, current_sha)
        require(snapshot["input"]["release"]["previous"] == current_sha, "EXPECTED_PREVIOUS_MISMATCH")
        if previous is not None: history_fn(previous, snapshot)
        if not existing_target:
            stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=out))
            for name, data in {**payload, "MANIFEST.json": raw_manifest}.items():
                with (stage / name).open("xb") as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
            sync_directory(stage)
            os.rename(stage, target)
            sync_directory(releases)
        verify_release(out, release, manifest_sha)
        pointer = canonical({"schema": "docs-navigator.current/v1", "release": release, "manifest_sha256": manifest_sha})
        pointer_fd, pointer_name = tempfile.mkstemp(prefix=".pointer-", dir=out)
        with os.fdopen(pointer_fd, "wb") as stream: stream.write(pointer); stream.flush(); os.fsync(stream.fileno())
        lease.check(out)
        if _source_guard is not None: _source_guard()
        os.replace(pointer_name, out / "CURRENT.json")
        sync_directory(out)
        view = _publish_current_view_locked(out, release, manifest_sha, known_view_release)
        return {"status": "BUILT_LOCAL", "release": release, "manifest_sha256": manifest_sha,
                "view_path": view["path"], "current_view": view}
    finally:
        if owned_lease: lease.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True); parser.add_argument("--manifest", required=True); parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try: print(json.dumps(build(args.root, args.manifest, args.output), ensure_ascii=False))
    except (Invalid, OSError) as exc:
        print(json.dumps({"status": "REFUSED", "code": str(exc) if isinstance(exc, Invalid) else type(exc).__name__})); raise SystemExit(1)
