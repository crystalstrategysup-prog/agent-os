#!/usr/bin/env python3
"""Bounded public-tree validation; heuristic privacy check is not a security audit."""

import ast
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_os import __version__
from agent_os.doc_catalog import DOCS
from agent_os.handoff_store import HandoffError, scan_secrets


def runtime_receipts_present(root: Path) -> bool:
    return (root / ".agentos").exists()


def version_matches(project_text: str, module_version: str) -> bool:
    try:
        declared = tomllib.loads(project_text)["project"]["version"]
    except (ValueError, KeyError, TypeError):
        return False
    return type(declared) is str and bool(declared) and declared == module_version


def skill_name(rel: Path, text: str):
    match = re.match(r"^---\nname: ([^\n]+)\ndescription: .+\n---\n", text)
    if not match:
        return None
    name = match.group(1)
    if name.startswith("agentos-"):
        return name
    if name == "atlas" and str(rel) in {"src/agent_os/resources/skills/atlas/SKILL.md", "modules/atlas/skills/atlas/SKILL.md"}:
        return name
    return None


def verify() -> dict:
    errors = []
    counts = {"python": 0, "json": 0, "skills": 0, "markdown": 0}
    foundation_skills = set()
    atlas_skills = 0
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
        "docs/HANDOFF_DISCOVERY.md",
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
        try:
            scan_secrets(path.read_bytes())
        except HandoffError:
            errors.append("secret_shape:" + str(rel))
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
                    errors.append("private_marker:" + str(rel))
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
            name = skill_name(rel, text)
            if name is None:
                errors.append("skill_frontmatter:" + str(rel))
            elif name == "atlas":
                atlas_skills += 1
            else:
                foundation_skills.add(name)
    for doc_id in DOCS:
        if not (ROOT / f"src/agent_os/resources/templates/{doc_id}.md").is_file():
            errors.append("missing_template:" + doc_id)
    if len(foundation_skills) != 9 or atlas_skills != 2 or counts["skills"] != 11:
        errors.append("foundation_or_atlas_skill_inventory_mismatch")
    version_text = (ROOT / "pyproject.toml").read_text()
    if not version_matches(version_text, __version__):
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
