"""Deterministic single-file transport for a verified source bundle."""
import base64
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile

from .loader import load_engine


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def pack_bundle(directory, destination):
    directory, destination = Path(directory), Path(destination)
    engine = load_engine("route_probe_replay")
    manifest, verified = engine._verify(directory, with_sources=True)
    contents = {path: base64.b64encode(data).decode() for path, data in verified.items()}
    graph_bytes = engine._read_public(directory / "route_graph.json", 8_000_000)
    if hashlib.sha256(graph_bytes).hexdigest() != manifest["graph_sha256"]:
        raise ValueError("graph_changed_during_pack")
    value = {"schema": "function-extractor.portable-bundle/v1", "tool_version": "0.3.0",
             "manifest": manifest, "graph": json.loads(graph_bytes),
             "sources_base64": contents, "launcher": "fe replay --bundle route_bundle.json --fixture fixture.json"}
    data = canonical(value) + b"\n"
    if len(data) > 32_000_000 or destination.exists():
        raise ValueError("portable_bound_or_exists")
    with destination.open("xb") as stream:
        stream.write(data)
    destination.chmod(0o600)
    return {"path": str(destination), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


@contextmanager
def materialize_bundle(path):
    path = Path(path)
    if path.is_dir():
        load_engine("route_probe_replay")._verify(path)
        yield path
        return
    raw = load_engine("route_probe_replay")._read_public(path, 32_000_000)
    value = json.loads(raw)
    if value.get("schema") != "function-extractor.portable-bundle/v1":
        raise ValueError("portable_schema")
    manifest = value["manifest"]
    rows = manifest["files"]
    if not 0 < len(rows) <= 160 or {r["path"] for r in rows} != set(value["sources_base64"]):
        raise ValueError("portable_files")
    with tempfile.TemporaryDirectory(prefix="fe-bundle-") as temp:
        root = Path(temp); total = 0
        for row in rows:
            rel = Path(row["path"])
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError("portable_path")
            data = base64.b64decode(value["sources_base64"][row["path"]], validate=True)
            total += len(data)
            if (len(data) > 2_000_000 or total > 16_000_000 or len(data) != row["bytes"]
                    or hashlib.sha256(data).hexdigest() != row["sha256"]):
                raise ValueError("portable_pin")
            dst = root / "source" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            with dst.open("xb") as stream:
                stream.write(data)
        data = canonical(manifest) + b"\n"
        (root / "manifest.json").write_bytes(data)
        (root / "manifest.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")
        (root / "route_graph.json").write_bytes(canonical(value["graph"]) + b"\n")
        load_engine("route_probe_replay")._verify(root)
        yield root
