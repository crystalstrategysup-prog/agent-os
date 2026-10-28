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

EXTENSION_SKILLS = {
    "src/agent_os/resources/skills/atlas/SKILL.md": "atlas",
    "src/agent_os/resources/skills/function-extractor/SKILL.md": "function-extractor",
    "modules/atlas/skills/atlas/SKILL.md": "atlas",
}


def version_matches(project_text: str, runtime_version: str) -> bool:
    """Compare current identities without pinning validation to one release."""
    try:
        declared = tomllib.loads(project_text).get("project", {}).get("version")
    except (tomllib.TOMLDecodeError, AttributeError):
        return False
    return isinstance(runtime_version, str) and declared == runtime_version and bool(
        re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:rc[0-9]+)?(?:\+[a-z0-9]+(?:[.-][a-z0-9]+)*)?", runtime_version)
    )


def skill_name(path: Path, text: str) -> str | None:
    """Return only a canonical skill name at its declared public location."""
    expected = EXTENSION_SKILLS.get(path.as_posix())
    if expected is None:
        parts = path.parts
        if (len(parts) != 6 or parts[:4] != ("src", "agent_os", "resources", "skills")
                or parts[-1] != "SKILL.md" or not re.fullmatch(r"agentos-[a-z0-9][a-z0-9-]*", parts[-2])):
            return None
        expected = parts[-2]
    match = re.match(r"^---\nname: ([^\n]+)\ndescription: .+\n---\n", text)
    return expected if match and match.group(1) == expected else None


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
    extension_skills = EXTENSION_SKILLS
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
            if skill_name(rel, text) is None:
                errors.append("skill_frontmatter:" + str(rel))
    for doc_id in DOCS:
        if not (ROOT / f"src/agent_os/resources/templates/{doc_id}.md").is_file():
            errors.append("missing_template:" + doc_id)
    base_skills = list((ROOT / "src/agent_os/resources/skills").glob("agentos-*/SKILL.md"))
    if len(base_skills) != 9 or counts["skills"] != len(base_skills) + len(extension_skills) or not all((ROOT / name).is_file() for name in extension_skills):
        errors.append("unexpected_module_skill_inventory")
    if not version_matches((ROOT / "pyproject.toml").read_text(), __version__):
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
