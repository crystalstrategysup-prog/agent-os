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
from agent_os.handoff_store import HandoffError, scan_secrets


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
    # Exact plugin entrypoints are bundled as independent modules. Foundation
    # still requires its original nine canonical agentos-* skills; importing
    # third-party skills must neither rename them nor discard their locales.
    extension_skills = {
        "src/agent_os/resources/skills/atlas/SKILL.md": "atlas",
        "src/agent_os/resources/skills/function-extractor/SKILL.md": "function-extractor",
        "modules/atlas/skills/atlas/SKILL.md": "atlas",
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
            name = extension_skills.get(str(rel))
            if name is None:
                allowed = str(rel).startswith("src/agent_os/resources/skills/agentos-")
                expected_name = "agentos-[^\n]+" if allowed else None
            else:
                expected_name = re.escape(name)
            if expected_name is None or not re.match(
                r"^---\nname: " + expected_name + r"\ndescription: .+\n---\n", text
            ):
                errors.append("skill_frontmatter:" + str(rel))
    for doc_id in DOCS:
        if not (ROOT / f"src/agent_os/resources/templates/{doc_id}.md").is_file():
            errors.append("missing_template:" + doc_id)
    base_skills = list((ROOT / "src/agent_os/resources/skills").glob("agentos-*/SKILL.md"))
    if len(base_skills) != 9 or counts["skills"] != len(base_skills) + len(extension_skills) or not all((ROOT / name).is_file() for name in extension_skills):
        errors.append("unexpected_module_skill_inventory")
    import tomllib
    project_version = tomllib.loads((ROOT / "pyproject.toml").read_text()).get("project", {}).get("version")
    if project_version != __version__ or not re.fullmatch(r"0\.8\.0rc[0-9]+(?:\+[a-z0-9]+(?:[.-][a-z0-9]+)*)?", __version__):
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
