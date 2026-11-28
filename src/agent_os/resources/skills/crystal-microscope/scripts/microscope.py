#!/usr/bin/env python3
"""Validate or view an explicit Crystal Microscope document; never collect profiles.

Only the standard library is used. Structural validity does not establish that
an observation, source claim or causal explanation is true.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import stat
import sys
from typing import Any

SCHEMA = "crystal-microscope/v1"
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_HTML_BYTES = 16 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_PARENT_DEPTH = 128
LIMITS = {"nodes": 5000, "edges": 20000, "runs": 5000,
          "evidence": 20000, "metrics": 20000}
STATUSES = {"declared", "source", "runtime", "experiment", "hypothesis", "unknown"}
EDGE_KINDS = {"call", "message", "data", "ownership", "wait", "state", "recovery", "correlation"}
TIME_BASES = {"inclusive", "exclusive", "not_applicable", "unknown"}


class DocumentError(ValueError):
    """An input cannot be safely represented by this bounded format."""


def _read_file(path: Path, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise DocumentError("Input must be a regular file")
        if info.st_size > limit:
            raise DocumentError(f"Input exceeds {limit} bytes")
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise DocumentError(f"Input exceeds {limit} bytes")
    return content


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DocumentError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _nonfinite(token: str) -> Any:
    raise DocumentError(f"Non-finite JSON number: {token}")


def parse_document(raw: bytes) -> dict[str, Any]:
    """Parse without dropping extension fields; the caller retains raw bytes."""
    if len(raw) > MAX_INPUT_BYTES:
        raise DocumentError(f"JSON exceeds {MAX_INPUT_BYTES} bytes")
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                              parse_constant=_nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise DocumentError(f"Invalid bounded UTF-8 JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise DocumentError("The JSON root must be an object")
    stack = [(document, 0)]
    while stack:
        value, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            raise DocumentError(f"JSON nesting exceeds {MAX_JSON_DEPTH}")
        if isinstance(value, float) and not math.isfinite(value):
            raise DocumentError("Non-finite number, including in extension fields")
        if isinstance(value, dict):
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)
    return document


def validate(document: dict[str, Any]) -> list[str]:
    """Check structure, references and declared measurement provenance, not truth."""
    errors: list[str] = []

    def error(path: str, note: str) -> None:
        if len(errors) < 100:
            errors.append(f"{path}: {note}")

    def text(value: Any, path: str) -> bool:
        valid = isinstance(value, str) and bool(value.strip())
        if not valid:
            error(path, "expected nonempty text")
        return valid

    def strings(value: Any, path: str) -> bool:
        if not isinstance(value, list):
            error(path, "expected an array of strings")
            return False
        for i, item in enumerate(value):
            text(item, f"{path}[{i}]")
        return True

    def enum(value: Any, allowed: set[str], path: str) -> None:
        if not isinstance(value, str) or value not in allowed:
            error(path, "expected one of " + ", ".join(sorted(allowed)))

    if document.get("schema") != SCHEMA:
        error("schema", f"expected {SCHEMA}")
    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        error("metadata", "expected object")
    else:
        for field in ("revision", "environment", "question", "scope"):
            text(metadata.get(field), f"metadata.{field}")
        strings(metadata.get("unknowns"), "metadata.unknowns")

    tables: dict[str, dict[str, dict[str, Any]]] = {}
    for name, limit in LIMITS.items():
        value = document.get(name)
        table: dict[str, dict[str, Any]] = {}
        tables[name] = table
        if not isinstance(value, list):
            error(name, "expected array (use [] if no records)")
            continue
        if len(value) > limit:
            error(name, f"exceeds {limit} records")
            continue
        for i, item in enumerate(value):
            path = f"{name}[{i}]"
            if not isinstance(item, dict):
                error(path, "expected object")
                continue
            key = item.get("id")
            if not text(key, path + ".id"):
                continue
            if len(key) > 128:
                error(path + ".id", "exceeds 128 characters")
                continue
            if key in table:
                error(path + ".id", "duplicate ID")
            else:
                table[key] = item
    if not tables["nodes"]:
        error("nodes", "at least one node is required")

    def ref(value: Any, table: str, path: str, nullable: bool = False) -> None:
        if nullable and value is None:
            return
        if not isinstance(value, str) or value not in tables[table]:
            error(path, f"unknown {table} ID")

    def evidence_refs(item: dict[str, Any], path: str) -> None:
        values = item.get("evidence")
        if not isinstance(values, list):
            error(path + ".evidence", "expected array of evidence IDs")
            return
        for i, value in enumerate(values):
            ref(value, "evidence", f"{path}.evidence[{i}]")
        status = item.get("status")
        if isinstance(status, str) and status in {"runtime", "experiment"} and not values:
            error(path + ".evidence", "runtime/experiment claims need a declared evidence reference")
        kinds = {tables["evidence"][value].get("kind") for value in values
                 if isinstance(value, str) and value in tables["evidence"]
                 and isinstance(tables["evidence"][value].get("kind"), str)}
        if item.get("status") == "runtime" and not kinds.intersection({"runtime", "experiment"}):
            error(path + ".evidence", "runtime claims need runtime or experiment evidence; source alone is insufficient")
        if item.get("status") == "experiment" and "experiment" not in kinds:
            error(path + ".evidence", "experiment claims need experiment evidence")

    for key, item in tables["runs"].items():
        for field in ("scenario", "environment", "revision"):
            text(item.get(field), f"runs.{key}.{field}")
    for key, item in tables["evidence"].items():
        path = f"evidence.{key}"
        enum(item.get("kind"), STATUSES, path + ".kind")
        for field in ("locator", "summary"):
            text(item.get(field), path + "." + field)
        if "run" not in item:
            error(path + ".run", "required; use null for non-run evidence")
        ref(item.get("run"), "runs", path + ".run", nullable=True)
        kind = item.get("kind")
        if isinstance(kind, str) and kind in {"runtime", "experiment"} and item.get("run") is None:
            error(path + ".run", "runtime/experiment evidence needs a run")
        strings(item.get("limits"), path + ".limits")
        if item.get("kind") == "unknown":
            text(item.get("unknown_reason"), path + ".unknown_reason")

    for key, item in tables["nodes"].items():
        path = f"nodes.{key}"
        for field in ("kind", "title"):
            text(item.get(field), path + "." + field)
        enum(item.get("status"), STATUSES, path + ".status")
        if "parent" not in item:
            error(path + ".parent", "required; use null for a root")
        ref(item.get("parent"), "nodes", path + ".parent", nullable=True)
        if not isinstance(item.get("contract"), dict):
            error(path + ".contract", "expected object; describe missing knowledge explicitly")
        if "source" not in item or (item["source"] is not None and not isinstance(item["source"], dict)):
            error(path + ".source", "expected object or null")
        if item.get("status") == "source" and not item.get("source"):
            error(path + ".source", "a source claim needs a source anchor")
        if item.get("status") == "unknown":
            text(item.get("unknown_reason"), path + ".unknown_reason")
        evidence_refs(item, path)

    # Only the containment parent relation must be a tree/forest. A wait graph
    # may deliberately contain a cycle describing a suspected deadlock.
    for start in tables["nodes"]:
        seen: set[str] = set()
        key: Any = start
        while isinstance(key, str) and key in tables["nodes"]:
            if key in seen:
                error(f"nodes.{start}.parent", "parent cycle")
                break
            seen.add(key)
            if len(seen) > MAX_PARENT_DEPTH:
                error(f"nodes.{start}.parent", f"hierarchy exceeds {MAX_PARENT_DEPTH}")
                break
            key = tables["nodes"][key].get("parent")

    for key, item in tables["edges"].items():
        path = f"edges.{key}"
        enum(item.get("kind"), EDGE_KINDS, path + ".kind")
        enum(item.get("status"), STATUSES, path + ".status")
        ref(item.get("from"), "nodes", path + ".from")
        ref(item.get("to"), "nodes", path + ".to")
        if item.get("status") == "unknown":
            text(item.get("unknown_reason"), path + ".unknown_reason")
        evidence_refs(item, path)

    for key, item in tables["metrics"].items():
        path = f"metrics.{key}"
        ref(item.get("node"), "nodes", path + ".node")
        text(item.get("name"), path + ".name")
        text(item.get("unit"), path + ".unit")
        enum(item.get("status"), STATUSES, path + ".status")
        # Supplied references remain claims even when no measurement exists.
        # Check them before the null/invalid-value branches can return early.
        if "run" in item:
            ref(item["run"], "runs", path + ".run")
        if "evidence" in item:
            evidence_refs(item, path)
        if "value" not in item:
            error(path + ".value", "required; use null with unknown_reason if unknown")
            continue
        value = item["value"]
        if value is None:
            text(item.get("unknown_reason"), path + ".unknown_reason")
            if item.get("status") != "unknown":
                error(path + ".status", "null measurements require unknown status")
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and not math.isfinite(value)):
            error(path + ".value", "expected finite JSON number or null, not boolean")
            continue
        if isinstance(value, int) and abs(value) > 9007199254740991:
            error(path + ".value", "integer exceeds exact browser numeric range; use a justified scaled unit")
        if item.get("status") == "unknown":
            error(path + ".status", "unknown measurements use null, not a numeric placeholder")
        if "run" not in item:
            ref(None, "runs", path + ".run")
        for field in ("scenario", "method", "clock", "overlap", "overhead"):
            text(item.get(field), path + "." + field)
        enum(item.get("time_basis"), TIME_BASES, path + ".time_basis")
        strings(item.get("limits"), path + ".limits")
        if "evidence" not in item:
            evidence_refs(item, path)
        if not item.get("evidence"):
            error(path + ".evidence", "numeric values need a declared evidence reference, including estimates")
        sample = item.get("sample")
        if not isinstance(sample, dict):
            error(path + ".sample", "expected count/selection/aggregation or na_reason")
        elif "na_reason" in sample:
            text(sample["na_reason"], path + ".sample.na_reason")
            if "count" in sample:
                error(path + ".sample", "use either sample count or na_reason, not both")
        else:
            count = sample.get("count")
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                error(path + ".sample.count", "expected positive integer")
            for field in ("selection", "aggregation"):
                text(sample.get(field), path + ".sample." + field)
    return errors


STYLE = """
:root{color-scheme:light dark;font-family:system-ui,sans-serif;line-height:1.45}
body{margin:0;background:#101621;color:#e8edf5}header{padding:18px 24px;background:#172235}
h1{margin:0;font-size:24px}h2{font-size:21px}h3{font-size:16px;color:#a9c9ef}
button,input{font:inherit;border-radius:7px;border:1px solid #516780;padding:8px;background:#22344e;color:inherit}
button{cursor:pointer}button:hover{background:#344e72}input{box-sizing:border-box;width:100%}
.layout{display:grid;grid-template-columns:minmax(220px,28%) 1fr;min-height:75vh}
aside{padding:16px;border-right:1px solid #34445b}main{padding:18px 24px;min-width:0}
#node-list{display:grid;gap:6px;margin-top:12px}.node{text-align:left;overflow-wrap:anywhere}
.notice{padding:12px;border:1px solid #b78a3c;background:#322a1d;border-radius:8px}
.muted{color:#a8b7ca}.badge{display:inline-block;padding:2px 7px;border:1px solid #56708e;border-radius:5px;margin-left:8px}
.unknown{color:#ffd88d}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#172235;padding:12px;border-radius:7px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin:9px 0}details{margin:10px 0}summary{cursor:pointer}
a{color:#a9c9ef}.small{font-size:13px}#export{float:right}#count{margin-top:8px}
@media(max-width:700px){.layout{grid-template-columns:1fr}aside{border-right:0;border-bottom:1px solid #34445b}#node-list{max-height:240px;overflow:auto}main{padding:16px}}
"""

SCRIPT = """
'use strict';
const encoded = document.getElementById('microscope-data').textContent.trim();
const bytes = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
const original = new TextDecoder('utf-8', {fatal:true}).decode(bytes);
const data = JSON.parse(original);
const nodes = new Map(data.nodes.map(n => [n.id,n]));
const evidence = new Map(data.evidence.map(e => [e.id,e]));
const children = new Map(), links = new Map(), metrics = new Map();
for (const n of data.nodes) { const a=children.get(n.parent)||[]; a.push(n); children.set(n.parent,a); }
for (const e of data.edges) { for(const id of new Set([e.from,e.to])){const a=links.get(id)||[];a.push(e);links.set(id,a);} }
for (const m of data.metrics) { const a=metrics.get(m.node)||[];a.push(m);metrics.set(m.node,a); }
const main = document.getElementById('detail'), list = document.getElementById('node-list');
const showJSON = value => JSON.stringify(value,null,2);
function el(tag,text,cls){const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x;}
function section(title){const s=el('section');s.append(el('h3',title));main.append(s);return s;}
function details(target,title,value){const d=el('details');d.append(el('summary',title),el('pre',showJSON(value)));target.append(d);}
function nav(target,id,label){const b=el('button',label||nodes.get(id).title);b.type='button';b.addEventListener('click',()=>select(id));target.append(b);}
function refs(target,ids){for(const id of ids||[]){const e=evidence.get(id);if(e)details(target,'Evidence '+id+' · '+e.kind,e);}}
function select(id){
 const n=nodes.get(id);if(!n)return;main.replaceChildren();
 const crumb=el('div',undefined,'row');let p=n.parent;const chain=[];
 while(p!==null&&nodes.has(p)){chain.unshift(p);p=nodes.get(p).parent;}
 for(const c of chain)nav(crumb,c);main.append(crumb);
 const title=el('h2',n.title);title.append(el('span',n.status.toUpperCase(),'badge'+(n.status==='unknown'?' unknown':'')));main.append(title);
 main.append(el('p',n.id+' · '+n.kind,'muted'));
 if(n.unknown_reason)main.append(el('p','UNKNOWN: '+n.unknown_reason,'notice unknown'));
 const c=section('Contract');c.append(el('pre',showJSON(n.contract)));
 const src=section('Source and evidence');
 if(n.source===null)src.append(el('p','Source: UNKNOWN / not supplied','unknown'));else details(src,'Source anchor',n.source);
 refs(src,n.evidence);
 const child=children.get(id)||[];if(child.length){const s=section('Zoom into children');const row=el('div',undefined,'row');for(const x of child)nav(row,x.id,x.title+' · '+x.status);s.append(row);}
 const es=links.get(id)||[];if(es.length){const s=section('Typed relations');for(const e of es){const row=el('div',undefined,'row');row.append(el('span',e.kind+' · '+e.status+' · '+(e.from===id?'→':'←')));const other=e.from===id?e.to:e.from;nav(row,other);s.append(row);details(s,'Relation '+e.id,e);refs(s,e.evidence);}}
 const ms=metrics.get(id)||[];if(ms.length){const s=section('Measurements — declared provenance, not verified truth');for(const m of ms){const v=m.value===null?'UNKNOWN: '+m.unknown_reason:String(m.value)+' '+m.unit;const d=el('details');d.open=true;d.append(el('summary',m.name+' = '+v+' · '+m.status),el('pre',showJSON(m)));s.append(d);refs(s,m.evidence);}}
 details(main,'Complete node record, including extension fields',n);
}
let shown=200;
function refresh(){const q=document.getElementById('search').value.toLocaleLowerCase();const matches=data.nodes.filter(n=>showJSON(n).toLocaleLowerCase().includes(q));list.replaceChildren();for(const n of matches.slice(0,shown)){const b=el('button',n.title+' · '+n.kind+' · '+n.status,'node');b.type='button';b.addEventListener('click',()=>select(n.id));list.append(b);}document.getElementById('count').textContent=matches.length+' matched nodes; '+Math.min(shown,matches.length)+' shown';document.getElementById('more').hidden=shown>=matches.length;}
document.getElementById('search').addEventListener('input',()=>{shown=200;refresh();});
document.getElementById('more').addEventListener('click',()=>{shown+=200;refresh();});
document.getElementById('overview').addEventListener('click',()=>{main.replaceChildren();main.append(el('h2','Snapshot and limits'));details(main,'Metadata',data.metadata);const u=section('UNKNOWN');if(data.metadata.unknowns.length){for(const x of data.metadata.unknowns)u.append(el('p',x,'unknown'));}else u.append(el('p','No unknowns declared; this is not a completeness claim.','muted'));const r=section('Runs');for(const x of data.runs)details(r,x.id+' · '+x.scenario,x);const root=section('Root nodes');for(const x of children.get(null)||[])nav(root,x.id);});
document.getElementById('export').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([bytes],{type:'application/json'}));const a=el('a');a.href=url;a.download='crystal-microscope.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);});
document.getElementById('question').textContent=data.metadata.question;
document.getElementById('basis').textContent=data.metadata.revision+' · '+data.metadata.environment;
refresh();document.getElementById('overview').click();
"""


def render_html(raw: bytes) -> bytes:
    document = parse_document(raw)
    errors = validate(document)
    if errors:
        raise DocumentError("Invalid document: " + "; ".join(errors))
    payload = base64.b64encode(raw).decode("ascii")
    script_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    style_hash = base64.b64encode(hashlib.sha256(STYLE.encode()).digest()).decode()
    csp = ("default-src 'none'; connect-src 'none'; img-src 'none'; object-src 'none'; "
           "base-uri 'none'; form-action 'none'; "
           f"script-src 'sha256-{script_hash}'; style-src 'sha256-{style_hash}'")
    html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<title>Crystal Microscope</title><style>{STYLE}</style></head><body>
<header><button id="export" type="button">Export original JSON</button><h1>Crystal Microscope</h1>
<p id="question"></p><p id="basis" class="muted"></p>
<p class="notice small">Offline view of supplied data. Structural validation is not verification of facts, causality, coverage or production readiness. No profiler or host connection runs here. Export preserves the original UTF-8 JSON bytes, including extension fields and zero values. Detail formatting uses browser JSON numbers.</p></header>
<div class="layout"><aside><button id="overview" type="button">Snapshot / UNKNOWN / runs</button>
<p><label for="search">Search nodes and their fields</label><input id="search" type="search" placeholder="Function, contract, status…"></p>
<div id="count" class="muted small"></div><div id="node-list"></div><button id="more" type="button">Show more</button></aside>
<main id="detail"></main></div>
<script type="application/octet-stream" id="microscope-data">{payload}</script>
<script>{SCRIPT}</script></body></html>'''
    return html.encode("utf-8")


class _PayloadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.inside = False
        self.blocks: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        if tag == "script" and fields.get("id") == "microscope-data":
            if fields.get("type") != "application/octet-stream":
                raise DocumentError("Unexpected payload type")
            self.blocks.append([])
            self.inside = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.inside = False

    def handle_data(self, data: str) -> None:
        if self.inside:
            self.blocks[-1].append(data)


def extract_payload(html: bytes) -> bytes:
    """Extract data without executing HTML. This does not certify arbitrary HTML."""
    if len(html) > MAX_HTML_BYTES:
        raise DocumentError(f"HTML exceeds {MAX_HTML_BYTES} bytes")
    parser = _PayloadParser()
    try:
        parser.feed(html.decode("utf-8"))
        parser.close()
        if len(parser.blocks) != 1:
            raise DocumentError("Expected exactly one microscope payload")
        raw = base64.b64decode("".join(parser.blocks[0]).strip(), validate=True)
    except (UnicodeError, ValueError) as exc:
        raise DocumentError(f"Invalid embedded payload: {exc}") from exc
    errors = validate(parse_document(raw))
    if errors:
        raise DocumentError("Invalid embedded document: " + "; ".join(errors))
    return raw


def write_new(path: Path, data: bytes) -> None:
    """O_EXCL also refuses existing symlinks; never replace a prior artifact."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "render", "extract"):
        action = actions.add_parser(name)
        action.add_argument("input", type=Path)
        if name != "validate":
            action.add_argument("--output", required=True, type=Path,
                                help="New file only; existing output is never overwritten")
    args = parser.parse_args(argv)
    try:
        if args.command == "extract":
            raw = extract_payload(_read_file(args.input, MAX_HTML_BYTES))
            write_new(args.output, raw)
            result = {"operation": "extract", "output": str(args.output),
                      "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                      "claims_verified": False}
        else:
            raw = _read_file(args.input, MAX_INPUT_BYTES)
            document = parse_document(raw)
            errors = validate(document)
            result = {"schema": SCHEMA, "structural_valid": not errors,
                      "claims_verified": False, "errors": errors,
                      "counts": {key: len(document.get(key, [])) if isinstance(document.get(key), list) else None for key in LIMITS},
                      "input_sha256": hashlib.sha256(raw).hexdigest()}
            if errors:
                print(json.dumps(result, ensure_ascii=True))
                return 2
            if args.command == "render":
                html = render_html(raw)
                if extract_payload(html) != raw:
                    raise DocumentError("Internal payload roundtrip mismatch")
                write_new(args.output, html)
                result.update(operation="render", output=str(args.output), bytes=len(html),
                              export_roundtrip="byte_identical")
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (OSError, ValueError, RecursionError, OverflowError) as exc:
        print(json.dumps({"structural_valid": False, "claims_verified": False,
                          "error": str(exc)}, ensure_ascii=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
