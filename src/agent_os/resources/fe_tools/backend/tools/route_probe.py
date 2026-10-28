"""Bounded static extraction and hash-pinned offline replay. No live-send mode."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def freeze_bundle(source_root, entry, output, *, adapter=None, include_modules=(), opaque_modules=(), include_entries=(), capture_mode="STRICT"):
    import importlib
    graph_module = importlib.import_module((__package__ or "tools") + ".route_probe_graph")
    if capture_mode not in {"STRICT", "PARTIAL_STATIC"}:
        raise ValueError("capture_mode")
    extract_route, _open_source = graph_module.extract_route, graph_module._open_source
    root = graph_module._safe_path(Path(source_root).absolute())
    output = graph_module._safe_path(Path(output).absolute())
    if output.exists() or output.is_relative_to(root):
        raise ValueError("bundle_output_exists_or_inside_source")
    graphs = [extract_route(root, entry, opaque_modules=tuple(opaque_modules))]
    if adapter:
        graphs.append(extract_route(root, adapter, opaque_modules=tuple(opaque_modules)))
    for selected_entry in include_entries:
        graphs.append(extract_route(root, selected_entry, opaque_modules=tuple(opaque_modules)))
    for module in include_modules:
        # Explicit module pinning does not execute it. Dependencies of the
        # actual selected functions remain in the normal graphs.
        if not all(p.isidentifier() for p in module.split(".")):
            raise ValueError("invalid_include_module")
    files = {}
    for graph in graphs:
        caps = graph.get("unresolved_caps", [])
        if caps and (capture_mode != "PARTIAL_STATIC" or any(row["kind"] != "max_depth" for row in caps)):
            raise ValueError("graph_expansion_cap")
        for row in graph["files"]:
            files[row["path"]] = row
    for module in include_modules:
        rel = module.replace(".", "/")
        path = root / (rel + ".py")
        if not path.is_file():
            path = root / rel / "__init__.py"
        files[str(path.relative_to(root))] = {}
    # Keep real package initializers, not a hidden package-import approximation.
    for rel in list(files):
        for parent in Path(rel).parents:
            if str(parent) != "." and (root / parent / "__init__.py").is_file():
                files.setdefault(str(parent / "__init__.py"), {})
    if len(files) > 160:
        raise ValueError("bundle_file_cap")
    pinned, contents = [], {}
    total = 0
    for rel in sorted(files):
        path = graph_module._safe_path(root / rel)
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("source_path_escape")
        fd = _open_source(path)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 2_000_000:
                raise ValueError("source_file_type_or_bound")
            data = stream.read(2_000_001)
            after = os.fstat(stream.fileno())
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")
        if any(getattr(before, key) != getattr(after, key) for key in fields):
            raise ValueError("source_changed_during_read")
        total += len(data)
        if len(data) > 2_000_000 or total > 16_000_000:
            raise ValueError("bundle_byte_cap")
        sha = hashlib.sha256(data).hexdigest()
        expected = files[rel].get("sha256")
        if expected and expected != sha:
            raise ValueError("source_changed_during_freeze")
        pinned.append({"path": rel, "sha256": sha, "bytes": len(data)})
        contents[rel] = data
    # Recheck output ancestors immediately before creating the isolated result.
    graph_module._safe_path(output)
    output.mkdir(parents=True, exist_ok=False)
    for row in pinned:
        dst = output / "source" / row["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(contents[row["path"]])
    graph = dict(graphs[0])
    graph["additional_entrypoints"] = [g["entry"] for g in graphs[1:]]
    for key in ("nodes", "edges", "branches", "unresolved", "unresolved_caps"):
        merged = {}
        for g in graphs:
            for row in g.get(key, []):
                merged[canonical(row)] = row
        graph[key] = [merged[key] for key in sorted(merged)]
    graph["files"] = pinned
    graph["complete"] = not bool(graph["unresolved_caps"])
    (output / "route_graph.json").write_bytes(canonical(graph) + b"\n")
    manifest = {"schema": "route-probe.bundle/v1", "entry": entry, "adapter": adapter,
                "opaque_modules": sorted(set(opaque_modules)), "files": pinned,
                "graph_sha256": hashlib.sha256((output / "route_graph.json").read_bytes()).hexdigest(),
                "coverage": "BOUNDED_STATIC_NOT_EXHAUSTIVE", "capture_mode": capture_mode,
                "live_send_supported": False}
    data = canonical(manifest) + b"\n"
    (output / "manifest.json").write_bytes(data)
    (output / "manifest.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    extract = sub.add_parser("extract")
    extract.add_argument("--source-root", type=Path, required=True)
    extract.add_argument("--entry", required=True)
    extract.add_argument("--adapter")
    extract.add_argument("--include-module", action="append", default=[])
    extract.add_argument("--include-entry", action="append", default=[])
    extract.add_argument("--opaque-module", action="append", default=[])
    extract.add_argument("--out", type=Path, required=True)
    replay = sub.add_parser("replay")
    replay.add_argument("--bundle", type=Path, required=True)
    replay.add_argument("--fixture", type=Path, required=True)
    replay.add_argument("--fixture-sha256")
    replay.add_argument("--timeout", type=float, default=10)
    replay.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "extract":
            value = freeze_bundle(args.source_root, args.entry, args.out, adapter=args.adapter,
                                  include_modules=args.include_module, opaque_modules=args.opaque_module,
                                  include_entries=args.include_entry)
            print(json.dumps({"status": "FROZEN", "files": len(value["files"]), "output": str(args.out)}))
            return 0
        import importlib
        replay_bundle = importlib.import_module((__package__ or "tools") + ".route_probe_replay").replay_bundle
        if args.out.exists() or args.fixture.stat().st_size > 65536:
            raise ValueError("output_exists_or_fixture_bound")
        fixture = json.loads(args.fixture.read_bytes())
        result = replay_bundle(args.bundle, fixture, timeout=args.timeout,
                               expected_fixture_sha256=args.fixture_sha256)
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / "trace.json").write_bytes(canonical(result) + b"\n")
        lines = ["# Isolated route replay", "", "Status: " + result["status"],
                 "", "Real selected source runs in a separate guarded process; explicit fixture crossings are simulated.",
                 "No production delivery or historical root cause is inferred.", ""]
        for span in result.get("spans", []):
            lines.append(f"- {span.get('phase')}: {span.get('event')} {span.get('symbol', '')} ({span.get('file', '')}:{span.get('line', '')})")
        (args.out / "ROUTE_REPORT.md").write_text("\n".join(lines) + "\n")
        print(json.dumps({"status": result["status"], "spans": len(result.get("spans", [])), "output": str(args.out)}))
        return 0 if result["status"] in {"RETURNED", "RAISED", "DENIED"} else 2
    except Exception as exc:
        # Never echo user fixture, exception text or request/error payload.
        print(json.dumps({"status": "REFUSED", "exception_class": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
