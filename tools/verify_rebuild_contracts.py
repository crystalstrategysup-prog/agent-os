#!/usr/bin/env python3
"""Check maintained packaging contracts without changing project/user state."""
from __future__ import annotations

import ast
import hashlib
import json
import tomllib
from pathlib import Path

from sync_atlas import synchronize
from sync_resources import synchronize as synchronize_documents

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "src/agent_os/resources"

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    failures = []
    checked = 0
    def check(ok, label):
        nonlocal checked
        checked += 1
        if not ok:
            failures.append(label)
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    init = ast.parse((ROOT / "src/agent_os/__init__.py").read_text())
    declared = [ast.literal_eval(n.value) for n in init.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets)]
    check(declared == [version], "package-version")
    cli = json.loads((ROOT / "schemas/cli-contract-v1.json").read_bytes())
    check(cli["distribution_version"] == version and cli["release"] == version, "cli-version")
    for name in ("cli-contract-v1.json", "scoped-install-v1.json", "project-diagnostics-v1.json"):
        check((ROOT / "schemas" / name).read_bytes() == (RES / "contracts" / name).read_bytes(), "schema-mirror:" + name)
    entries = [x for x in cli["commands"] if x["name"] == "project diagnose"]
    check(len(entries) == 1 and entries[0].get("advisory") is True
          and entries[0]["write_surfaces"] == [] and entries[0]["effect"] == "read_only",
          "diagnostic-advisory-contract")
    try:
        documents = synchronize_documents(ROOT)
    except (ValueError, OSError) as exc:
        check(False, "document-sync:" + str(exc))
    else:
        for name in documents["documents"]:
            check(name not in documents["changed"], "document-mirror:" + name)
        check(not documents["orphaned"], "document-mirror-orphans:" + ",".join(documents["orphaned"]))
    name = "COORDINATOR_KNOWLEDGE_INDEX.json"
    index = json.loads((ROOT / "docs" / name).read_bytes())
    check((ROOT / "docs" / name).read_bytes() == (RES / "docs" / name).read_bytes(), "coordinator-index-mirror")
    for row in index["documents"]:
        check(digest(ROOT / "docs" / row["path"]) == row["sha256"], "coordinator-pin:" + row["id"])
    check((ROOT / "docs/ATLAS_SOURCE.json").read_bytes() ==
          (RES / "docs/ATLAS_SOURCE.json").read_bytes(), "atlas-source-manifest-mirror")
    try:
        atlas = synchronize(ROOT, apply=False)
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
        check(False, "atlas-source-sync:" + str(exc))
    else:
        check(atlas["status"] == "PASS", "atlas-source-sync")
    modules = json.loads((RES / "contracts/agentos-modules-v1.json").read_bytes())
    check(modules["modules"]["agentos"]["version"] == version, "module-version")
    for module, spec in modules["modules"].items():
        for row in spec["pins"]:
            check(digest(RES / row["path"]) == row["sha256"], "module-pin:" + module + ":" + row["path"])
    print(json.dumps({"status": "FAIL" if failures else "PASS", "version": version,
                      "checks": checked, "failures": failures, "effect": "READ_ONLY"}))
    return bool(failures)

if __name__ == "__main__":
    raise SystemExit(main())
