#!/usr/bin/env python3
"""Bounded public-tree validation; heuristic privacy check is not a security audit."""

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_os import __version__
from agent_os.doc_catalog import DOCS


def runtime_receipts_present(root: Path) -> bool:
    return (root / ".agentos").exists()


def verify() -> dict:
    errors = []
    counts = {"python": 0, "json": 0, "skills": 0, "markdown": 0}
    if runtime_receipts_present(ROOT):
        errors.append("runtime_receipts_in_public_tree")
    forbidden = ["/Users/", "PRIVATE-DO-NOT-PUBLISH", "private-current-rc."]
    required = [
        "README.md",
        "AGENTS.md",
        "LICENSE",
        "docs/PROCESS.md",
        "docs/ARCHITECTURE.md",
        "docs/DATA.md",
        "docs/CONTRACTS.md",
        "docs/INSTALL_UPDATE.md",
        "docs/SECURITY_MODEL.md",
        "docs/QUALITY.md",
        "docs/ONBOARDING.md",
        "docs/WORK_CONTINUITY.md",
        "docs/RELEASE.md",
        "docs/DOCUMENTATION_CATALOG.md",
        "docs/agentos/DOSSIER.md",
        "docs/agentos/ROADMAP.md",
    ]
    for rel in required:
        if not (ROOT / rel).is_file():
            errors.append("missing:" + rel)
    ignored = {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".agentos",
    }
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if set(rel.parts) & ignored or any(x.endswith(".egg-info") for x in rel.parts):
            continue
        if path.is_symlink():
            errors.append("symlink:" + str(rel))
            continue
        if not path.is_file():
            continue
        if path.name in {".env", "auth.json"} or path.suffix in {".pem", ".key"}:
            errors.append("forbidden_file:" + str(rel))
        if path.suffix not in {
            ".py",
            ".json",
            ".md",
            ".toml",
            ".yml",
            ".yaml",
            ".txt",
            ".sh",
        }:
            continue
        text = path.read_text(encoding="utf-8")
        if path != Path(__file__).resolve():
            for token in forbidden:
                if token in text:
                    errors.append("private_marker:" + str(rel) + ":" + token)
        if path.suffix == ".py":
            ast.parse(text, filename=str(rel))
            counts["python"] += 1
        if path.suffix == ".json":
            json.loads(text)
            counts["json"] += 1
        if path.suffix == ".md":
            counts["markdown"] += 1
        if path.name == "SKILL.md":
            counts["skills"] += 1
            if not re.match(
                r"^---\nname: agentos-[^\n]+\ndescription: .+\n---\n", text
            ):
                errors.append("skill_frontmatter:" + str(rel))
    for doc_id in DOCS:
        if not (ROOT / f"src/agent_os/resources/templates/{doc_id}.md").is_file():
            errors.append("missing_template:" + doc_id)
    if counts["skills"] != 9:
        errors.append("expected_nine_skills")
    version_text = (ROOT / "pyproject.toml").read_text()
    if 'version = "0.5.1"' not in version_text or __version__ != "0.5.1":
        errors.append("version_mismatch")
    return {
        "status": "PASS" if not errors else "FAIL",
        "version": __version__,
        "counts": counts,
        "errors": errors,
        "privacy_scope": "Known-marker/filename heuristics; independent review still required.",
    }


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
