"""Static boundary labels, never runtime permissions or inferred observations."""
from __future__ import annotations

import hashlib
import json


def classify_boundary(edge: dict) -> dict:
    target = edge.get("target") or edge.get("expression") or ""
    lower = target.lower()
    if any(word in lower for word in ("requests", "httpx", "socket", "urlopen", "aiohttp")):
        kind = "network"
    elif any(word in lower for word in ("sqlalchemy", "sqlite", "psycopg", "database", "transaction")):
        kind = "database"
    elif any(word in lower for word in ("subprocess", "os.system", "os.exec", "os.fork")):
        kind = "process"
    elif any(word in lower for word in ("kafka", "rabbit", "celery", "broker", "publish")):
        kind = "broker"
    elif any(word in lower for word in ("builtins.open", "pathlib", "os.open", "write_text", "write_bytes")):
        kind = "filesystem"
    elif edge.get("reason") == "opaque_module":
        kind = "opaque_import"
    elif edge.get("resolution") == "dynamic":
        kind = "dynamic_call"
    else:
        kind = "external_dependency"
    identity = {key: edge.get(key) for key in ("source", "target", "file", "line", "expression", "kind")}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"id": digest, "kind": kind, "source": edge.get("source"), "target": edge.get("target"),
            "file": edge.get("file"), "line": edge.get("line"), "resolution": edge.get("resolution"),
            "evidence": "STATIC_NOT_EXECUTED", "admission": "REQUIRES_EXPLICIT_FIXTURE_OR_DENIAL"}
