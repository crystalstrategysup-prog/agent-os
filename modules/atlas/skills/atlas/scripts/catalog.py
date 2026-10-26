#!/usr/bin/env python3
"""Compile explicit API documentation into Atlas cards; never infer runtime proof."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import navigator as nav

VERSION = "ATLAS-CATALOG-1.0.0"
METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


def identity(prefix, value):
    return prefix + "-" + hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:24]


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def field(value, pointer, fallback="UNKNOWN: not declared in selected source"):
    if value is None or value == [] or value == {} or value == "":
        return fallback
    text = value if isinstance(value, str) else compact(value)
    if len(text) <= 18000:
        return text
    return "Exact value at " + pointer + "; canonical value sha256=" + hashlib.sha256(compact(value).encode()).hexdigest() + ". Open the retained source to read the complete value."


def empty_catalog():
    return {"schema": "atlas.semantic-catalog/v1", "modules": [], "contracts": [], "relations": [], "work_bindings": [], "work_context": [], "patch_bindings": []}


def module(catalog, title, doc, purpose=None, owner=None):
    mid = identity("MOD", title)
    if not any(m["id"] == mid for m in catalog["modules"]):
        catalog["modules"].append({"id": mid, "title": str(title), "purpose": purpose or "Documentation group explicitly declared by the selected source: " + str(title),
                                   "state_owner": owner or "UNKNOWN: the documentation group alone does not establish a state writer", "dependencies": [], "docs": [doc]})
    return mid


def card(key, title, mid, doc, source, pointer, version):
    return {"id": identity("CTR", key), "contract_key": identity("API", key), "title": str(title), "version": str(version), "lifecycle": "current", "module": mid,
            "state_owner": "UNKNOWN: qualify from the owning source before a write", "input": "UNKNOWN: not declared", "output": "UNKNOWN: not declared", "parameters": [], "errors": [],
            "auth": "UNKNOWN: not declared", "dependencies": [], "usage": "Source declaration only. Exact source: " + pointer + ". Record sha256=" + hashlib.sha256(compact(source).encode()).hexdigest() + ". No endpoint, worker or product operation was run.",
            "docs": [doc], "evidence_state": "FACT", "execution": "NOT_RUN"}


def local_ref(document, value):
    if not isinstance(value, dict) or "$ref" not in value:
        return value
    ref = value["$ref"]
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return value
    found = document
    try:
        for token in ref[2:].split("/"):
            found = found[token.replace("~1", "/").replace("~0", "~")]
    except (KeyError, TypeError):
        return value
    return found if isinstance(found, dict) and "$ref" not in found else value


def from_openapi(document, doc, source_path):
    nav.require(isinstance(document, dict) and isinstance(document.get("paths"), dict) and "openapi" in document, "OPENAPI_SOURCE_REQUIRED")
    catalog = empty_catalog()
    for route, paths in sorted(document["paths"].items()):
        if not isinstance(paths, dict):
            continue
        for method in METHODS:
            operation = paths.get(method)
            if not isinstance(operation, dict):
                continue
            pointer = source_path + "#/paths/" + route.replace("~", "~0").replace("/", "~1") + "/" + method
            tags = operation.get("tags") or ["Untagged API"]
            mid = module(catalog, str(tags[0]), doc)
            c = card(method.upper() + " " + route, method.upper() + " " + route + " · " + str(operation.get("summary") or operation.get("operationId") or "operation"), mid, doc, operation, pointer, document.get("info", {}).get("version", "UNKNOWN"))
            parameters = {}
            for item in [*paths.get("parameters", []), *operation.get("parameters", [])]:
                item = local_ref(document, item)
                if isinstance(item, dict):
                    parameters[(item.get("name", "UNKNOWN"), item.get("in", "UNKNOWN"))] = item
            for (name, where), p in parameters.items():
                required = "UNKNOWN" if "$ref" in p else p.get("required", False)
                c["parameters"].append({"name": str(name), "type": field(p.get("schema") or p.get("content"), pointer + "/parameters", "UNKNOWN: unresolved parameter schema"),
                                         "required": required if type(required) is bool else "UNKNOWN", "description": "location=" + str(where) + "; " + field(p.get("description"), pointer + "/parameters", "No description declared")})
            body = local_ref(document, operation.get("requestBody", {}))
            if body:
                c["parameters"].append({"name": "requestBody", "type": field(body.get("content"), pointer + "/requestBody/content"), "required": body.get("required", False) if type(body.get("required", False)) is bool else "UNKNOWN", "description": field(body.get("description"), pointer + "/requestBody", "OpenAPI request body declaration; referenced schemas remain in the retained document")})
            c["input"] = field({"method": method.upper(), "path": route, "parameters": list(parameters.values()), "requestBody": body}, pointer)
            c["output"] = field(operation.get("responses"), pointer + "/responses")
            for code, response in operation.get("responses", {}).items():
                if code == "default" or (str(code).isdigit() and int(code) >= 400):
                    c["errors"].append({"code": str(code), "meaning": field(local_ref(document, response), pointer + "/responses/" + str(code))})
            if "security" in operation or "security" in document:
                c["auth"] = "Declared OpenAPI security; runtime enforcement not tested: " + field(operation.get("security", document.get("security")), pointer + "/security", "Explicit empty security declaration")
            catalog["contracts"].append(c)
            catalog["relations"].append({"from": doc, "to": c["id"], "type": "describes", "evidence_docs": [doc]})
    return catalog


def known_values(value):
    if not isinstance(value, list):
        return value
    # Preserve each source qualification. UNKNOWN is meaningful, not a missing key.
    return [{k: v for k, v in x.items() if k in ("state", "value", "reason")} if isinstance(x, dict) else x for x in value]


def from_records(document, doc, source_path):
    nav.require(isinstance(document, dict) and isinstance(document.get("contracts"), list), "RECORD_CATALOG_SOURCE_REQUIRED")
    catalog = empty_catalog()
    for i, record in enumerate(document["contracts"]):
        nav.require(isinstance(record, dict) and isinstance(record.get("id"), str), "CONTRACT_RECORD_ID")
        pointer = source_path + "#/contracts/" + str(i)
        mid = module(catalog, str(record.get("component") or "Unclassified source group"), doc)
        c = card(record["id"], record.get("title", record["id"]), mid, doc, record, pointer, document.get("revision", "SOURCE"))
        c["state_owner"] = field(known_values(record.get("state_ownership")), pointer + "/state_ownership")
        c["input"] = field({"entrypoints": known_values(record.get("entrypoints")), "parameters": known_values(record.get("parameters"))}, pointer)
        c["output"] = field(known_values(record.get("results")), pointer + "/results")
        c["auth"] = field(record.get("authorization"), pointer + "/authorization")
        c["usage"] += " Source verification=" + field(record.get("verification"), pointer) + "; source execution claim=" + field(record.get("execution_status"), pointer) + "; effects=" + field(known_values(record.get("effects")), pointer + "/effects")
        c["usage"] = field(c["usage"], pointer)
        for part in record.get("parameters", []):
            value = part.get("value", {}) if isinstance(part, dict) and part.get("state") == "known" else {}
            if not isinstance(value, dict):
                continue
            for p in value.get("individual_parameters", []):
                if not isinstance(p, dict):
                    continue
                required = p.get("required_by_signature", "UNKNOWN")
                c["parameters"].append({"name": str(p.get("name", "UNKNOWN")), "type": field(p.get("annotation"), pointer, "UNKNOWN: no annotation"), "required": required if type(required) is bool else "UNKNOWN", "description": field(p, pointer + "/parameters")})
        errors = known_values(record.get("errors"))
        if errors:
            c["errors"].append({"code": "SOURCE_DECLARATION", "meaning": field(errors, pointer + "/errors")})
        catalog["contracts"].append(c)
        catalog["relations"].append({"from": doc, "to": c["id"], "type": "describes", "evidence_docs": [doc]})
    return catalog


def from_operations(document, doc, source_path):
    nav.require(isinstance(document, dict) and isinstance(document.get("operations"), list), "OPERATION_REGISTRY_SOURCE_REQUIRED")
    catalog = empty_catalog()
    for category in ("operations", "additional_entries", "workers"):
        for i, record in enumerate(document.get(category, [])):
            nav.require(isinstance(record, dict), "OPERATION_RECORD_OBJECT")
            pointer = source_path + "#/" + category + "/" + str(i)
            key = record.get("id") or record.get("module") or pointer
            group = record.get("state_owner") or record.get("owner") or record.get("module") or "Unclassified source entries"
            mid = module(catalog, str(group), doc, owner=field(record.get("state_owner") or record.get("owner"), pointer))
            c = card(category + ":" + str(key), str(key), mid, doc, record, pointer, record.get("contract_version", document.get("version", "SOURCE")))
            c["state_owner"] = field(record.get("state_owner") or record.get("owner"), pointer)
            c["input"] = field({"entry": record.get("entry"), "inputs": record.get("inputs"), "source": record.get("source")}, pointer)
            c["output"] = field(record.get("output_expressions") or record.get("effects"), pointer)
            c["auth"] = field(record.get("preconditions"), pointer)
            raw_inputs = record.get("inputs", [])
            for p in raw_inputs if isinstance(raw_inputs, list) else []:
                if not isinstance(p, dict):
                    continue
                required = p.get("required", "UNKNOWN")
                c["parameters"].append({"name": str(p.get("name", "UNKNOWN")), "type": field(p.get("type_expression"), pointer), "required": required if type(required) is bool else "UNKNOWN", "description": field({"origin": p.get("origin"), "default_expression": p.get("default_expression")}, pointer)})
            if record.get("errors_ref"):
                c["errors"].append({"code": "SOURCE_REFERENCE", "meaning": field(record["errors_ref"], pointer)})
            c["usage"] = field(c["usage"] + " Source proof and boundaries=" + compact({k: record[k] for k in ("proof", "scope_status", "status", "rule", "unknowns", "consumers", "exception") if k in record}), pointer)
            catalog["contracts"].append(c)
            catalog["relations"].append({"from": doc, "to": c["id"], "type": "describes", "evidence_docs": [doc]})
    return catalog


BUILDERS = {"openapi": from_openapi, "record-catalog": from_records, "operation-registry": from_operations}


def compile_catalog(root, spec):
    nav.require(isinstance(spec, dict) and set(spec) == {"schema", "format", "path", "document_id"}, "CATALOG_SOURCE_FIELDS")
    nav.require(spec["schema"] == "atlas.catalog-source/v1" and spec["format"] in BUILDERS, "CATALOG_SOURCE_FORMAT")
    nav.ident(spec["document_id"])
    raw = nav.read_selected(Path(root).resolve(), spec["path"], 8 * 1024 * 1024)
    result = BUILDERS[spec["format"]](nav.parse(raw), spec["document_id"], spec["path"])
    nav.require(len(result["contracts"]) <= 1000 and len(result["modules"]) <= 200, "CATALOG_ENTITY_LIMIT")
    nav.require(len({c["contract_key"] for c in result["contracts"]}) == len(result["contracts"]), "DUPLICATE_SOURCE_CONTRACT")
    return result, {"path": spec["path"], "sha256": nav.digest(raw), "bytes": len(raw)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--source", required=True, help="Explicit root-relative atlas.catalog-source/v1 JSON")
    args = p.parse_args()
    try:
        spec = nav.parse(nav.read_selected(Path(args.root).resolve(), args.source))
        result, _ = compile_catalog(args.root, spec)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
        return 0
    except (nav.Invalid, OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"status": "REFUSED", "code": str(exc) if isinstance(exc, nav.Invalid) else type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
