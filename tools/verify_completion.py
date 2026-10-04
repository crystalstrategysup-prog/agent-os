#!/usr/bin/env python3
"""Local CI chain: docs/schema/traceability only, never a product PASS."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def verify():
    trace = json.loads((ROOT / "docs/completion/TRACEABILITY.json").read_bytes())
    errors = []
    requirements, scenarios = trace["requirements"], trace["scenarios"]
    if set(requirements) != {f"R{i:02}" for i in range(1, 39)}:
        errors.append("requirement_coverage")
    if set(scenarios) != {f"T{i:02}" for i in range(1, 35)}:
        errors.append("scenario_coverage")
    for rid, row in requirements.items():
        if not row["test_ids"] or any(
            t not in scenarios or rid not in scenarios[t]["requirement_ids"]
            for t in row["test_ids"]
        ):
            errors.append("requirement_links:" + rid)
    for tid, row in scenarios.items():
        if not row["recipes"] or row["status"] != "NOT_RUN":
            errors.append("recipe_is_not_runtime_receipt:" + tid)
        for recipe in row["recipes"]:
            relative, function = recipe.split("::")
            path = ROOT / relative
            if (
                Path(relative).is_absolute()
                or ".." in Path(relative).parts
                or path.is_symlink()
                or not path.is_file()
            ):
                errors.append("missing_or_unsafe_recipe:" + tid)
                continue
            names = {
                n.name
                for n in ast.walk(ast.parse(path.read_bytes()))
                if isinstance(n, ast.FunctionDef)
            }
            if function not in names:
                errors.append("missing_recipe_function:" + tid)
    source = ROOT / "schemas/completion-v1.schema.json"
    packaged = ROOT / "src/agent_os/resources/schemas/completion-v1.schema.json"
    if source.read_bytes() != packaged.read_bytes():
        errors.append("schema_mirror")
    Draft202012Validator.check_schema(json.loads(source.read_bytes()))
    for name in ["COMPLETION.md", "COORDINATOR_KNOWLEDGE_INDEX.json"]:
        if (ROOT / "docs" / name).read_bytes() != (
            ROOT / "src/agent_os/resources/docs" / name
        ).read_bytes():
            errors.append("doc_mirror:" + name)
    return {
        "status": "FAIL" if errors else "PASS",
        "scope": "documentation_and_traceability_only",
        "requirements": len(requirements),
        "scenarios": len(scenarios),
        "product_tests_executed": False,
        "errors": errors,
    }


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
