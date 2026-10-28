"""Bounded local contract discovery. Attestations are inputs, never live authority.

No application import, network resolver, schema execution or expected-value learning.
The JSON Schema helper deliberately implements a small, explicitly closed subset.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from datetime import datetime

LEVELS = ("OFFICIAL", "APPROVED_INTERNAL", "OBSERVED", "UNSPECIFIED")
PROVENANCE_ORDER = {level: i for i, level in enumerate(LEVELS)}
RULE_KINDS = ("input_schema", "output_schema", "trace_match", "delivery_state", "no_retry", "semantic")
_KINDS = ("json_schema", "openapi", "python", "local_doc", "rules")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,179}\Z")
_ENTRY = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\Z", re.ASCII)
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_SECRET = re.compile(r"(?:\.env(?:\..*)?|(?:credentials?|secrets?|sessions?|backups?)(?:[._-].*)?|id_rsa(?:\..*)?|id_ed25519(?:\..*)?|auth\.json)", re.I)
_MAP_KEYS = {"schema", "version", "status", "route", "revision", "sources", "boundaries", "rules", "unresolved", "content_digest"}
_METADATA_KEYS = {"retrieved_at", "version", "primary_ref", "primary_sha256", "official_schema", "machine_adapter"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def content_digest(value):
    """Digest all fields except the self-referential content_digest field."""
    return hashlib.sha256(canonical({k: v for k, v in value.items() if k != "content_digest"})).hexdigest()


def _bounded(value, *, items=20000, depth=24, size=2_000_000):
    budget = [items]
    def visit(x, d):
        budget[0] -= 1
        if budget[0] < 0 or d > depth:
            raise ValueError("JSON_BOUND")
        if x is None or type(x) in (bool, int, str):
            if type(x) is str and len(x) > 524288:
                raise ValueError("JSON_BOUND")
        elif type(x) is float and math.isfinite(x):
            pass
        elif type(x) is list:
            for child in x:
                visit(child, d + 1)
        elif type(x) is dict and all(type(k) is str and len(k) <= 256 for k in x):
            for child in x.values():
                visit(child, d + 1)
        else:
            raise ValueError("JSON_TYPE")
    visit(value, 0)
    raw = canonical(value)
    if len(raw) > size:
        raise ValueError("JSON_BOUND")
    return json.loads(raw)


def _identifier(value):
    return type(value) is str and bool(_ID.fullmatch(value))


def _sha(value):
    return type(value) is str and bool(_SHA.fullmatch(value))


def _metadata(value, kind):
    default = {"retrieved_at": None, "version": None, "primary_ref": None, "primary_sha256": None,
               "official_schema": False, "machine_adapter": kind in ("python", "rules", "local_doc")}
    if value is None:
        return default
    if type(value) is not dict or set(value) != _METADATA_KEYS:
        raise ValueError("SOURCE_METADATA")
    for key in ("retrieved_at", "version", "primary_ref"):
        if value[key] is not None and (type(value[key]) is not str or not 1 <= len(value[key]) <= 1024):
            raise ValueError("SOURCE_METADATA")
    if value["retrieved_at"] is not None:
        if datetime.fromisoformat(value["retrieved_at"].replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("SOURCE_METADATA")
    if value["primary_sha256"] is not None and not _sha(value["primary_sha256"]):
        raise ValueError("SOURCE_METADATA")
    if type(value["official_schema"]) is not bool or type(value["machine_adapter"]) is not bool:
        raise ValueError("SOURCE_METADATA")
    if kind in ("python", "rules", "local_doc") and (value["official_schema"] or not value["machine_adapter"]):
        raise ValueError("SOURCE_METADATA")
    return value


def _relative(value):
    if type(value) is not str or len(value) > 512 or "\\" in value:
        raise ValueError("SOURCE_PATH")
    path = Path(value)
    if path.is_absolute() or not path.parts or path.as_posix() != value or any(p in (".", "..") or _SECRET.fullmatch(p) for p in path.parts):
        raise ValueError("SOURCE_PATH")
    return path


def _read_public(root, relative):
    """Walk directories by pinned no-follow FDs, including every root ancestor."""
    path = Path(root)
    if not path.is_absolute() or ".." in path.parts or path == Path("/"):
        raise ValueError("SOURCE_ROOT")
    rel = _relative(relative)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:] + rel.parts[:-1]:
            if _SECRET.fullmatch(component):
                raise ValueError("SOURCE_PATH")
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        leaf = os.open(rel.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(leaf)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 524288:
                raise ValueError("SOURCE_FILE")
            chunks = []
            remaining = 524289
            while remaining:
                chunk = os.read(leaf, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(leaf)
            named = os.stat(rel.parts[-1], dir_fd=fd, follow_symlinks=False)
            signature = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if len(raw) > 524288 or signature(before) != signature(after) or signature(after) != signature(named):
                raise ValueError("SOURCE_CHANGED")
            return raw
        finally:
            os.close(leaf)
    finally:
        os.close(fd)


_SCHEMA_KEYS = {"$schema", "$id", "$defs", "definitions", "$ref", "title", "description", "default", "examples", "type", "properties", "required", "additionalProperties", "items", "enum", "const", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties", "uniqueItems", "oneOf"}
_TYPES = {"null", "boolean", "integer", "number", "string", "array", "object"}


def _pointer(root, reference):
    if type(reference) is not str or not reference.startswith("#/") or len(reference) > 512:
        raise ValueError("UNSUPPORTED_REF")
    node = root
    for part in reference[2:].split("/"):
        if "~" in part and re.search(r"~(?![01])", part):
            raise ValueError("UNSUPPORTED_REF")
        key = part.replace("~1", "/").replace("~0", "~")
        if type(node) is not dict or key not in node:
            raise ValueError("UNRESOLVED_REF")
        node = node[key]
    return node


def _schema_check(schema, root=None, stack=(), depth=0, budget=None):
    budget = [20000] if budget is None else budget
    budget[0] -= 1
    if depth > 16 or budget[0] < 0:
        raise ValueError("SCHEMA_DEPTH")
    if type(schema) is bool:
        return
    if type(schema) is not dict or set(schema) - _SCHEMA_KEYS:
        raise ValueError("UNSUPPORTED_SCHEMA")
    if root is None:
        root = schema
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref in stack:
            raise ValueError("CYCLIC_REF")
        _schema_check(_pointer(root, ref), root, stack + (ref,), depth + 1, budget)
    if "type" in schema:
        types = schema["type"] if type(schema["type"]) is list else [schema["type"]]
        if not types or len(types) > 7 or any(type(t) is not str or t not in _TYPES for t in types) or len(types) != len(set(types)):
            raise ValueError("UNSUPPORTED_SCHEMA")
    if "oneOf" in schema:
        branches = schema["oneOf"]
        if type(branches) is not list or not 1 <= len(branches) <= 8:
            raise ValueError("UNSUPPORTED_SCHEMA")
        for branch in branches:
            _schema_check(branch, root, stack, depth + 1, budget)
    for key in ("$defs", "definitions", "properties"):
        if key in schema:
            if type(schema[key]) is not dict:
                raise ValueError("UNSUPPORTED_SCHEMA")
            for child in schema[key].values():
                _schema_check(child, root, stack, depth + 1, budget)
    for key in ("additionalProperties", "items"):
        if key in schema:
            _schema_check(schema[key], root, stack, depth + 1, budget)
    if "required" in schema and (type(schema["required"]) is not list or any(type(x) is not str for x in schema["required"]) or len(schema["required"]) != len(set(schema["required"]))):
        raise ValueError("UNSUPPORTED_SCHEMA")
    if "enum" in schema and (type(schema["enum"]) is not list or not schema["enum"]):
        raise ValueError("UNSUPPORTED_SCHEMA")
    for key in ("minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties"):
        if key in schema and (type(schema[key]) is not int or not 0 <= schema[key] <= 1000000):
            raise ValueError("UNSUPPORTED_SCHEMA")
    for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        if key in schema and (type(schema[key]) not in (int, float) or not math.isfinite(schema[key])):
            raise ValueError("UNSUPPORTED_SCHEMA")
    if "uniqueItems" in schema and type(schema["uniqueItems"]) is not bool:
        raise ValueError("UNSUPPORTED_SCHEMA")
    if "$schema" in schema and schema["$schema"] not in ("https://json-schema.org/draft/2020-12/schema", "http://json-schema.org/draft-07/schema#"):
        raise ValueError("UNSUPPORTED_SCHEMA_DIALECT")


def _matches(value, name):
    return {"null": value is None, "boolean": type(value) is bool,
            "integer": type(value) is int or type(value) is float and math.isfinite(value) and value.is_integer(),
            "number": type(value) in (int, float), "string": type(value) is str,
            "array": type(value) is list, "object": type(value) is dict}[name]


def _equality_value(value):
    # Inputs already passed the finite JSON/depth/item budgets. Normalize only
    # mathematical integer floats, recursively; booleans remain a distinct type.
    if type(value) is float and value.is_integer():
        return int(value)
    if type(value) is list:
        return [_equality_value(x) for x in value]
    if type(value) is dict:
        return {k: _equality_value(v) for k, v in value.items()}
    return value


def _schema_errors(value, schema, root, depth=0, budget=None):
    budget = [50000] if budget is None else budget
    budget[0] -= 1
    if depth > 24 or budget[0] < 0:
        raise ValueError("SCHEMA_DEPTH")
    if type(schema) is bool:
        return [] if schema else ["FALSE_SCHEMA"]
    errors = []
    if "$ref" in schema:
        errors += _schema_errors(value, _pointer(root, schema["$ref"]), root, depth + 1, budget)
    if "oneOf" in schema:
        matches = sum(not _schema_errors(value, branch, root, depth + 1, budget) for branch in schema["oneOf"])
        if matches != 1:
            errors.append("ONEOF_MATCH_COUNT")
    types = schema.get("type", list(_TYPES))
    types = types if type(types) is list else [types]
    if not any(_matches(value, name) for name in types):
        return errors + ["TYPE_MISMATCH"]
    encoded_value = canonical(_equality_value(value)) if "const" in schema or "enum" in schema else None
    if "const" in schema and encoded_value != canonical(_equality_value(schema["const"])):
        errors.append("CONST_MISMATCH")
    if "enum" in schema and not any(encoded_value == canonical(_equality_value(x)) for x in schema["enum"]):
        errors.append("ENUM_MISMATCH")
    if type(value) in (int, float):
        for key, invalid in (("minimum", lambda x: value < x), ("maximum", lambda x: value > x), ("exclusiveMinimum", lambda x: value <= x), ("exclusiveMaximum", lambda x: value >= x)):
            if key in schema and invalid(schema[key]):
                errors.append("NUMBER_BOUND")
    if type(value) is str and (len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1000000)):
        errors.append("STRING_BOUND")
    if type(value) is list:
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 1000000):
            errors.append("ARRAY_BOUND")
        if schema.get("uniqueItems") and len({canonical(_equality_value(x)) for x in value}) != len(value):
            errors.append("ARRAY_NOT_UNIQUE")
        for item in value:
            errors += _schema_errors(item, schema.get("items", True), root, depth + 1, budget)
    if type(value) is dict:
        if len(value) < schema.get("minProperties", 0) or len(value) > schema.get("maxProperties", 1000000):
            errors.append("OBJECT_BOUND")
        if any(k not in value for k in schema.get("required", [])):
            errors.append("REQUIRED_MISSING")
        props = schema.get("properties", {})
        for key, item in value.items():
            errors += _schema_errors(item, props.get(key, schema.get("additionalProperties", True)), root, depth + 1, budget)
    return errors


def validate_schema(value, schema):
    """Small pure validator. Unsupported/unsafe constructs always return UNKNOWN."""
    try:
        schema = _bounded(schema, items=5000, depth=20, size=262144)
        value = _bounded(value, items=10000, depth=24, size=524288)
        _schema_check(schema)
        errors = sorted(set(_schema_errors(value, schema, schema)))
        return {"status": "INVALID" if errors else "VALID", "errors": errors, "unsupported": []}
    except (ValueError, TypeError, RecursionError, OverflowError):
        return {"status": "UNKNOWN", "errors": [], "unsupported": ["UNSUPPORTED_OR_BOUNDED_SCHEMA"]}


def _route(route):
    if type(route) is not dict or set(route) != {"route_id", "entry", "graph_sha256", "source_pins"} or not _identifier(route["route_id"]) or type(route["entry"]) is not str or not _ENTRY.fullmatch(route["entry"]) or not _sha(route["graph_sha256"]):
        raise ValueError("ROUTE_SHAPE")
    if type(route["source_pins"]) is not list or len(route["source_pins"]) > 80:
        raise ValueError("ROUTE_PINS")
    seen = set()
    for pin in route["source_pins"]:
        if type(pin) is not dict or set(pin) != {"path", "sha256"} or not _sha(pin["sha256"]):
            raise ValueError("ROUTE_PINS")
        path = _relative(pin["path"]).as_posix()
        if path in seen:
            raise ValueError("ROUTE_PINS")
        seen.add(path)
    return {**route, "source_pins": sorted(route["source_pins"], key=lambda x: x["path"])}


def _expand_refs(schema, document, stack=(), depth=0, budget=None):
    budget = [20000] if budget is None else budget
    budget[0] -= 1
    if depth > 16 or budget[0] < 0:
        raise ValueError("SCHEMA_DEPTH")
    if type(schema) is list:
        return [_expand_refs(v, document, stack, depth + 1, budget) for v in schema]
    if type(schema) is not dict:
        return schema
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref in stack:
            raise ValueError("CYCLIC_REF")
        target = _pointer(document, ref)
        # Sibling constraints are not overwritten or silently ignored.
        if set(schema) != {"$ref"}:
            raise ValueError("UNSUPPORTED_REF_SIBLINGS")
        return _expand_refs(target, document, stack + (ref,), depth + 1, budget)
    return {k: _expand_refs(v, document, stack, depth + 1, budget) for k, v in schema.items()}


def _annotation(node):
    if node is None:
        return None
    if isinstance(node, ast.Constant) and node.value is None:
        return {"type": "null"}
    if isinstance(node, ast.Name):
        names = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "list": "array", "dict": "object"}
        return {"type": names[node.id]} if node.id in names else None
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        if node.value.id in ("list", "List"):
            item = _annotation(node.slice)
            return {"type": "array", "items": item} if item is not None else None
        if node.value.id in ("Optional",):
            child = _annotation(node.slice)
            if child is not None and type(child.get("type")) is str:
                return {**child, "type": [child["type"], "null"]}
    return None


def _adapt(source, raw, default_boundary):
    """Return explicit boundaries/rules/gaps; natural prose is never interpreted."""
    selector = source.get("selector", {})
    if type(selector) is not dict:
        raise ValueError("SELECTOR_SHAPE")
    kind = source["kind"]
    if kind == "python":
        if set(selector) - {"symbol", "boundary_id"}:
            raise ValueError("SELECTOR_SHAPE")
        symbol = selector.get("symbol", default_boundary.split(":", 1)[1])
        if type(symbol) is not str or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", symbol, re.ASCII):
            raise ValueError("SELECTOR_SHAPE")
        tree = ast.parse(raw.decode("utf-8"))
        body = tree.body
        for part in symbol.split("."):
            matches = [n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == part]
            if len(matches) != 1:
                return [], [], ["PYTHON_SYMBOL_UNRESOLVED"]
            node = matches[0]
            body = node.body
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return [], [], ["PYTHON_SYMBOL_UNRESOLVED"]
        boundary = selector.get("boundary_id", default_boundary)
        rows, gaps, properties, required = [], [], {}, []
        args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
        if node.args.vararg or node.args.kwarg:
            gaps.append("PYTHON_VARIADIC_UNSPECIFIED")
        defaults = {a.arg for a in (node.args.posonlyargs + node.args.args)[len(node.args.posonlyargs + node.args.args) - len(node.args.defaults):]} if node.args.defaults else set()
        defaults.update(a.arg for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults) if d is not None)
        for arg in args:
            if arg.arg in ("self", "cls"):
                continue
            annotation = _annotation(arg.annotation)
            if annotation is None:
                gaps.append("PYTHON_ANNOTATION_UNSPECIFIED")
            else:
                properties[arg.arg] = annotation
            if arg.arg not in defaults:
                required.append(arg.arg)
        if not gaps:
            rows.append({"boundary_id": boundary, "kind": "input_schema", "constraint": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}})
        result = _annotation(node.returns)
        if result is None:
            gaps.append("PYTHON_RETURN_UNSPECIFIED")
        else:
            rows.append({"boundary_id": boundary, "kind": "output_schema", "constraint": result})
        return [{"boundary_id": boundary, "symbol": symbol, "kind": "python"}], rows, gaps
    document = _bounded(json.loads(raw), items=20000, depth=24, size=524288) if kind != "local_doc" else None
    if kind == "local_doc":
        text = raw.decode("utf-8")
        blocks = re.findall(r"^```contract-rules\n(.*?)\n```[ \t]*$", text, re.M | re.S)
        if len(blocks) != 1:
            return [], [], ["DOC_RULES_UNSPECIFIED"]
        document = _bounded(json.loads(blocks[0]))
    if kind in ("rules", "local_doc"):
        if selector or type(document) is not dict or type(document.get("rules")) is not list:
            raise ValueError("RULE_DOCUMENT_SHAPE")
        if "schema" in document:
            if document["schema"] != "function-extractor.rule-declarations/v1" or set(document) - {"schema", "boundaries", "rules"}:
                raise ValueError("RULE_DOCUMENT_SHAPE")
            boundaries = document.get("boundaries")
            if boundaries is None:
                boundaries = [{"boundary_id": name, "symbol": name, "kind": "semantic"} for name in sorted({r["boundary_id"] for r in document["rules"]})]
        else:
            if set(document) != {"boundaries", "rules"}:
                raise ValueError("RULE_DOCUMENT_SHAPE")
            boundaries = document["boundaries"]
        if type(boundaries) is not list:
            raise ValueError("RULE_DOCUMENT_SHAPE")
        return boundaries, document["rules"], []
    boundary = selector.get("boundary_id", default_boundary)
    if kind == "json_schema":
        if set(selector) - {"boundary_id", "direction"} or selector.get("direction", "input_schema") not in ("input_schema", "output_schema"):
            raise ValueError("SELECTOR_SHAPE")
        return [{"boundary_id": boundary, "symbol": default_boundary, "kind": "schema"}], [{"boundary_id": boundary, "kind": selector.get("direction", "input_schema"), "constraint": document}], []
    if kind == "openapi":
        if set(selector) - {"path", "method", "response", "boundary_id"} or document.get("openapi") not in ("3.0.0", "3.0.1", "3.0.2", "3.0.3", "3.1.0", "3.1.1"):
            raise ValueError("OPENAPI_SHAPE")
        path, method = selector.get("path"), selector.get("method")
        if type(path) is not str or not path.startswith("/") or method not in ("get", "post", "put", "patch", "delete", "head", "options"):
            raise ValueError("SELECTOR_SHAPE")
        operation = document.get("paths", {}).get(path, {}).get(method)
        if type(operation) is not dict:
            return [], [], ["OPENAPI_OPERATION_UNRESOLVED"]
        rules, gaps = [], []
        for direction, container in (("input_schema", operation.get("requestBody", {})), ("output_schema", operation.get("responses", {}).get(selector.get("response", "200"), {}))):
            try:
                if "$ref" in container:
                    container = _expand_refs(container, document)
                schema = container["content"]["application/json"]["schema"]
                constraint = _expand_refs(schema, document)
                rules.append({"boundary_id": boundary, "kind": direction, "constraint": constraint})
            except (KeyError, TypeError, ValueError):
                gaps.append("OPENAPI_SCHEMA_UNRESOLVED")
        if operation.get("parameters") or document.get("paths", {}).get(path, {}).get("parameters"):
            gaps.append("OPENAPI_PARAMETERS_UNRESOLVED")
        return [{"boundary_id": boundary, "symbol": method.upper() + " " + path, "kind": "http"}], rules, gaps
    raise ValueError("SOURCE_KIND")


def _finalize(result):
    result["sources"].sort(key=lambda x: x["source_id"])
    result["boundaries"].sort(key=lambda x: x["boundary_id"])
    result["rules"].sort(key=lambda x: x["rule_id"])
    result["unresolved"] = sorted({canonical(x) for x in result["unresolved"]})
    result["unresolved"] = [json.loads(x) for x in result["unresolved"]]
    result["content_digest"] = content_digest(result)
    return result


def resolve_contracts(route, sources, revision):
    """Resolve explicit snapshots. Revision bindings attest pins, not live grants.

    Source self-labels are ignored. Only an explicit same-digest binding can
    classify a source above UNSPECIFIED. No source label establishes acceptance.
    """
    result = {"schema": "contract-map/v1", "version": 1, "status": "REFUSED", "route": None, "revision": "UNSPECIFIED", "sources": [], "boundaries": [], "rules": [], "unresolved": []}
    source_id = None
    def gap(code, boundary_id=None, rule_id=None):
        result["unresolved"].append({"code": code, "source_id": source_id, "boundary_id": boundary_id, "rule_id": rule_id})
    try:
        route, sources, revision = _bounded(route), _bounded(sources), _bounded(revision)
        result["route"] = _route(route)
        if type(revision) is not dict or set(revision) != {"id", "source_root", "authority_bindings"} or not _identifier(revision["id"]) or type(revision["source_root"]) is not str or type(revision["authority_bindings"]) is not list:
            raise ValueError("REVISION_SHAPE")
        result["revision"] = revision["id"]
        bindings = {}
        if len(revision["authority_bindings"]) > 16 or type(sources) is not list or not 1 <= len(sources) <= 16:
            raise ValueError("SOURCE_BOUND")
        for binding in revision["authority_bindings"]:
            if type(binding) is not dict or set(binding) != {"source_id", "sha256", "provenance", "authority_ref"} or not _identifier(binding["source_id"]) or not _sha(binding["sha256"]) or binding["provenance"] not in LEVELS or type(binding["authority_ref"]) is not str or not 1 <= len(binding["authority_ref"]) <= 1024 or binding["source_id"] in bindings:
                raise ValueError("AUTHORITY_BINDING")
            bindings[binding["source_id"]] = binding
        seen, total = set(), 0
        for source in sorted(sources, key=lambda s: s.get("source_id", "") if type(s) is dict else ""):
            if type(source) is not dict or set(source) - {"source_id", "kind", "path", "sha256", "selector", "provenance", "authority_ref", "metadata"} or not {"source_id", "kind", "path", "sha256"} <= set(source):
                raise ValueError("SOURCE_SHAPE")
            source_id = source["source_id"] if _identifier(source["source_id"]) else None
            if not _identifier(source_id) or source_id in seen or source["kind"] not in _KINDS or not _sha(source["sha256"]):
                raise ValueError("SOURCE_SHAPE")
            seen.add(source_id)
            raw = _read_public(revision["source_root"], source["path"])
            total += len(raw)
            if total > 4_000_000:
                raise ValueError("SOURCE_BOUND")
            if hashlib.sha256(raw).hexdigest() != source["sha256"]:
                raise ValueError("SOURCE_HASH")
            binding = bindings.get(source_id)
            if binding is not None and binding["sha256"] != source["sha256"]:
                raise ValueError("AUTHORITY_HASH")
            level, authority = (binding["provenance"], binding["authority_ref"]) if binding else ("UNSPECIFIED", None)
            metadata = _metadata(source.get("metadata"), source["kind"])
            if level == "OFFICIAL" and any(metadata[k] is None for k in ("primary_ref", "primary_sha256", "retrieved_at")):
                raise ValueError("OFFICIAL_PRIMARY_UNRESOLVED")
            if source["kind"] == "python":
                level, authority = "OBSERVED", "source-pin:" + source["sha256"]
            elif level == "UNSPECIFIED":
                authority = None
            if "provenance" in source and source["provenance"] not in LEVELS:
                raise ValueError("SOURCE_PROVENANCE")
            result["sources"].append({"source_id": source_id, "kind": source["kind"], "path": source["path"], "sha256": source["sha256"], "provenance": level, "authority_ref": authority, "metadata": metadata})
            if level == "UNSPECIFIED":
                gap("SOURCE_AUTHORITY_UNSPECIFIED")
            boundaries, rules, gaps = _adapt(source, raw, route["entry"])
            for code in gaps:
                gap(code)
            for boundary in boundaries:
                if type(boundary) is not dict or set(boundary) != {"boundary_id", "symbol", "kind"} or not _identifier(boundary["boundary_id"]) or type(boundary["symbol"]) is not str or not 1 <= len(boundary["symbol"]) <= 256 or boundary["kind"] not in ("python", "schema", "http", "semantic"):
                    raise ValueError("BOUNDARY_SHAPE")
                existing = next((x for x in result["boundaries"] if x["boundary_id"] == boundary["boundary_id"]), None)
                if existing is not None and existing != boundary:
                    raise ValueError("BOUNDARY_CONFLICT")
                if existing is None:
                    result["boundaries"].append(boundary)
            if len(result["boundaries"]) > 128 or len(result["rules"]) + len(rules) > 256:
                raise ValueError("RULE_BOUND")
            for rule in rules:
                if type(rule) is not dict or set(rule) - {"rule_id", "boundary_id", "kind", "constraint"} or not {"boundary_id", "kind", "constraint"} <= set(rule) or rule["kind"] not in RULE_KINDS or rule["boundary_id"] not in {x["boundary_id"] for x in result["boundaries"]} or type(rule["constraint"]) not in (dict, bool):
                    raise ValueError("RULE_SHAPE")
                row = {k: v for k, v in rule.items() if k != "rule_id"}
                row.update(source_id=source_id, provenance=level)
                row["rule_id"] = rule.get("rule_id", "rule:" + hashlib.sha256(canonical(row)).hexdigest()[:24])
                if not _identifier(row["rule_id"]):
                    raise ValueError("RULE_ID")
                row["conflicts"] = []
                if rule["kind"] in ("input_schema", "output_schema"):
                    try:
                        _schema_check(rule["constraint"])
                    except (ValueError, TypeError):
                        gap("SCHEMA_UNSUPPORTED", rule["boundary_id"], row["rule_id"])
                existing_rule = next((x for x in result["rules"] if x["rule_id"] == row["rule_id"]), None)
                if existing_rule is not None and existing_rule != row:
                    raise ValueError("RULE_ID_CONFLICT")
                if existing_rule is None:
                    result["rules"].append(row)
        if set(bindings) - seen:
            raise ValueError("AUTHORITY_SOURCE_UNRESOLVED")
        source_id = None
        for index, a in enumerate(result["rules"]):
            for b in result["rules"][index + 1:]:
                if (a["boundary_id"], a["kind"]) == (b["boundary_id"], b["kind"]) and canonical(a["constraint"]) != canonical(b["constraint"]):
                    a["conflicts"].append(b["rule_id"])
                    b["conflicts"].append(a["rule_id"])
                    gap("NORMATIVE_RULES_COMPETE" if a["provenance"] in LEVELS[:2] and b["provenance"] in LEVELS[:2] else "OBSERVED_OR_UNSPECIFIED_DIFFERENCE", a["boundary_id"])
        for rule in result["rules"]:
            rule["conflicts"].sort()
        if not result["rules"]:
            gap("NO_RULES_RESOLVED")
        result["status"] = "PARTIAL" if result["unresolved"] else "RESOLVED"
    except (ValueError, TypeError, KeyError, AttributeError, OSError, UnicodeError, SyntaxError, RecursionError, OverflowError, json.JSONDecodeError):
        # Fixed public category; never echo exception paths, contents or args.
        result["status"] = "REFUSED"
        gap("INVALID_OR_UNSAFE_CONTRACT_SOURCE")
    return _finalize(result)


def validate_contract_map(value):
    """Validate untrusted persisted IR, all references and its content digest."""
    try:
        value = _bounded(value)
        if type(value) is not dict or set(value) != _MAP_KEYS or value["schema"] != "contract-map/v1" or type(value["version"]) is not int or value["version"] != 1 or value["status"] not in ("RESOLVED", "PARTIAL", "REFUSED") or not _sha(value["content_digest"]) or content_digest(value) != value["content_digest"] or not _identifier(value["revision"]):
            raise ValueError("MAP_SHAPE")
        if value["route"] is None:
            if value["status"] != "REFUSED":
                raise ValueError("MAP_ROUTE")
        else:
            _route(value["route"])
        for key, cap in (("sources", 16), ("boundaries", 128), ("rules", 256), ("unresolved", 1024)):
            if type(value[key]) is not list or len(value[key]) > cap:
                raise ValueError("MAP_BOUND")
        sources, boundaries, rules = {}, {}, {}
        for source in value["sources"]:
            if type(source) is not dict or set(source) != {"source_id", "kind", "path", "sha256", "provenance", "authority_ref", "metadata"} or not _identifier(source["source_id"]) or source["source_id"] in sources or source["kind"] not in _KINDS or not _sha(source["sha256"]) or source["provenance"] not in LEVELS:
                raise ValueError("MAP_SOURCE")
            _relative(source["path"])
            _metadata(source["metadata"], source["kind"])
            if source["kind"] == "python" and source["provenance"] != "OBSERVED":
                raise ValueError("MAP_AUTHORITY")
            if source["provenance"] == "OFFICIAL" and any(source["metadata"][k] is None for k in ("primary_ref", "primary_sha256", "retrieved_at")):
                raise ValueError("MAP_AUTHORITY")
            if source["provenance"] == "UNSPECIFIED":
                if source["authority_ref"] is not None:
                    raise ValueError("MAP_AUTHORITY")
            elif type(source["authority_ref"]) is not str or not 1 <= len(source["authority_ref"]) <= 1024:
                raise ValueError("MAP_AUTHORITY")
            sources[source["source_id"]] = source
        for boundary in value["boundaries"]:
            if type(boundary) is not dict or set(boundary) != {"boundary_id", "symbol", "kind"} or not _identifier(boundary["boundary_id"]) or boundary["boundary_id"] in boundaries or type(boundary["symbol"]) is not str or not 1 <= len(boundary["symbol"]) <= 256 or boundary["kind"] not in ("python", "schema", "http", "semantic"):
                raise ValueError("MAP_BOUNDARY")
            boundaries[boundary["boundary_id"]] = boundary
        for rule in value["rules"]:
            if type(rule) is not dict or set(rule) != {"rule_id", "boundary_id", "kind", "source_id", "provenance", "constraint", "conflicts"} or not _identifier(rule["rule_id"]) or rule["rule_id"] in rules or rule["source_id"] not in sources or rule["boundary_id"] not in boundaries or rule["kind"] not in RULE_KINDS or rule["provenance"] != sources[rule["source_id"]]["provenance"] or type(rule["constraint"]) not in (dict, bool) or type(rule["conflicts"]) is not list or len(rule["conflicts"]) != len(set(rule["conflicts"])):
                raise ValueError("MAP_RULE")
            rules[rule["rule_id"]] = rule
        for rule in rules.values():
            expected_conflicts = {other["rule_id"] for other in rules.values()
                if other["rule_id"] != rule["rule_id"] and (other["boundary_id"], other["kind"]) == (rule["boundary_id"], rule["kind"])
                and canonical(other["constraint"]) != canonical(rule["constraint"])}
            if set(rule["conflicts"]) != expected_conflicts:
                raise ValueError("MAP_CONFLICT_REF")
            for other_id in rule["conflicts"]:
                if other_id not in rules or rule["rule_id"] not in rules[other_id]["conflicts"] or other_id == rule["rule_id"]:
                    raise ValueError("MAP_CONFLICT_REF")
        for gap in value["unresolved"]:
            if type(gap) is not dict or set(gap) != {"code", "source_id", "boundary_id", "rule_id"} or type(gap["code"]) is not str or not re.fullmatch(r"[A-Z][A-Z_]{1,63}", gap["code"]):
                raise ValueError("MAP_GAP")
            if gap["source_id"] is not None and gap["source_id"] not in sources and value["status"] != "REFUSED":
                raise ValueError("MAP_GAP_REF")
            if gap["boundary_id"] is not None and gap["boundary_id"] not in boundaries or gap["rule_id"] is not None and gap["rule_id"] not in rules:
                raise ValueError("MAP_GAP_REF")
        if value["status"] == "RESOLVED" and (value["unresolved"] or not rules) or value["status"] == "PARTIAL" and not value["unresolved"]:
            raise ValueError("MAP_STATUS")
        return {"status": "VALID", "errors": [], "unsupported": []}
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
        return {"status": "INVALID", "errors": ["INVALID_CONTRACT_MAP"], "unsupported": []}


def selected_rule_digest(contract_map, rule_ids):
    """Invalidate selected rules/provenance; unrelated rules do not change it.

    A changed selected snapshot digest invalidates conservatively, even if the
    selected rule text is identical. This is a cache identity, never approval.
    """
    if validate_contract_map(contract_map)["status"] != "VALID" or type(rule_ids) is not list or not 1 <= len(rule_ids) <= 256 or any(not _identifier(x) for x in rule_ids) or len(rule_ids) != len(set(rule_ids)):
        raise ValueError("INVALID_SELECTED_RULES")
    rules = {x["rule_id"]: x for x in contract_map["rules"]}
    if any(x not in rules for x in rule_ids):
        raise ValueError("INVALID_SELECTED_RULES")
    # Competing rules are related dependencies, even if they are not explicitly
    # selected by a scenario. Their changes must invalidate an old cached PASS.
    ids = set(rule_ids)
    while True:
        expanded = ids | {other for name in ids for other in rules[name]["conflicts"]}
        if expanded == ids:
            break
        ids = expanded
    selected = [rules[x] for x in sorted(ids)]
    sources = {x["source_id"]: x for x in contract_map["sources"]}
    pinned = [sources[x] for x in sorted({r["source_id"] for r in selected})]
    return hashlib.sha256(canonical({"route": contract_map["route"], "rules": selected, "sources": pinned})).hexdigest()
