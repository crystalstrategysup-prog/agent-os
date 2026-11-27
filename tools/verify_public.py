#!/usr/bin/env python3
"""Bounded public-tree validation; heuristic privacy check is not a security audit."""

import ast
import hashlib
import json
import os
import re
import stat
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_os import __version__
from agent_os.doc_catalog import DOCS
from agent_os.engineering_guidance import MAX_DOCUMENT_BYTES, _section
from agent_os.handoff_store import HandoffError, scan_secrets

EXTENSION_SKILLS = {
    "src/agent_os/resources/skills/atlas/SKILL.md": "atlas",
    "src/agent_os/resources/skills/function-extractor/SKILL.md": "function-extractor",
    "modules/atlas/skills/atlas/SKILL.md": "atlas",
}
FROZEN_WORK_MANIFEST = ".release/work-laws-v1.json"
FROZEN_WORK_MANIFEST_SHA256 = "86b7d47d03520c659a3203b249694ac76069410d18df270f2b6db4cad2c67637"
FROZEN_WORK_DOCUMENTS = (
    ("laws", "docs/PROCESS.md", "src/agent_os/resources/docs/PROCESS.md", "solution-integrity"),
    ("orientation", "docs/WORK_ENVIRONMENT.md", "src/agent_os/resources/docs/WORK_ENVIRONMENT.md", None),
)


def _frozen_read(root: Path, relative: str, limit: int) -> bytes:
    """Read a fixed bounded regular file, refusing symlinks in its path."""
    path = root
    if path.is_symlink():
        raise ValueError("frozen_root_symlink")
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("frozen_path_symlink")
    if not path.is_file():
        raise ValueError("frozen_regular_file_required")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("frozen_regular_file_required")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("frozen_byte_bound")
    return raw


def frozen_work_laws_errors(root: Path) -> list[str]:
    """Check reviewed bytes, not owner authorization, meaning or agent behavior.

    The retained revision and this anchor change only by an explicit owner
    decision about the laws/orientation. Never regenerate them to clear a check.
    An editor able to replace the guard can replace its trust anchor as well.
    """
    try:
        raw = _frozen_read(root, FROZEN_WORK_MANIFEST, 4096)
        if hashlib.sha256(raw).hexdigest() != FROZEN_WORK_MANIFEST_SHA256:
            return ["frozen_work_manifest_changed:" + FROZEN_WORK_MANIFEST]
        manifest = json.loads(raw.decode("utf-8"))
        if (not isinstance(manifest, dict)
                or set(manifest) != {"schema", "revision", "change_policy", "historical_revisions",
                                     "proof_limit", "laws", "orientation"}
                or manifest["schema"] != "agentos.frozen-work-laws/v1"
                or type(manifest["revision"]) is not int or manifest["revision"] != 1
                or manifest["change_policy"] != "EXPLICIT_OWNER_DECISION_ABOUT_THIS_REVISION_REQUIRED"
                or manifest["historical_revisions"] != "RETAIN_IMMUTABLE"
                or not isinstance(manifest["proof_limit"], str) or not manifest["proof_limit"]):
            raise ValueError("frozen_manifest_schema")
        for name, source, resource, section in FROZEN_WORK_DOCUMENTS:
            pin = manifest[name]
            if (not isinstance(pin, dict)
                    or set(pin) != ({"source", "resource", "sha256", "bytes"} | ({"section"} if section else set()))
                    or pin["source"] != source or pin["resource"] != resource
                    or (section is not None and pin["section"] != section)
                    or type(pin["bytes"]) is not int or not 0 < pin["bytes"] <= MAX_DOCUMENT_BYTES
                    or not isinstance(pin["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])):
                raise ValueError("frozen_manifest_pin")
    except (OSError, ValueError, KeyError, TypeError):
        return ["frozen_work_manifest_invalid:" + FROZEN_WORK_MANIFEST]
    errors = []
    for name, source, resource, section in FROZEN_WORK_DOCUMENTS:
        for relative in (source, resource):
            try:
                raw = _frozen_read(root, relative, MAX_DOCUMENT_BYTES)
                text = raw.decode("utf-8")
                if section is not None:
                    content, _ = _section(text, section)
                    raw = content.encode("utf-8")
                pin = manifest[name]
                if len(raw) != pin["bytes"] or hashlib.sha256(raw).hexdigest() != pin["sha256"]:
                    errors.append("frozen_work_content_changed:" + relative)
            except (OSError, ValueError):
                errors.append("frozen_work_content_invalid:" + relative)
    return errors


def version_matches(project_text: str, runtime_version: str) -> bool:
    """Compare current identities without pinning validation to one release."""
    try:
        declared = tomllib.loads(project_text).get("project", {}).get("version")
    except (tomllib.TOMLDecodeError, AttributeError):
        return False
    return isinstance(runtime_version, str) and declared == runtime_version and bool(
        re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:rc[0-9]+)?(?:\+[a-z0-9]+(?:[.-][a-z0-9]+)*)?", runtime_version)
    )


def release_contract_errors(root: Path, runtime_version: str) -> list[str]:
    """Check authoritative AND packaged versions before claiming compatibility.

    This source check supplements actual wheel installer/MCP startup probes;
    an unrelated module import cannot prove the MCP version guard passed.
    """
    errors = []
    for name in ("mcp-tools-v1.json", "cli-contract-v1.json"):
        bodies = []
        for directory in ("schemas", "src/agent_os/resources/contracts"):
            path = root / directory / name
            try:
                raw = path.read_bytes()
                value = json.loads(raw)
                versions = ([value["serverInfo"]["version"]] if name.startswith("mcp-") else
                            [value["distribution_version"], value["release"]])
                if any(version != runtime_version for version in versions):
                    errors.append("release_contract_version_mismatch:" + directory + "/" + name)
                bodies.append(raw)
            except (OSError, ValueError, KeyError, TypeError):
                errors.append("release_contract_invalid:" + directory + "/" + name)
        if len(bodies) == 2 and bodies[0] != bodies[1]:
            errors.append("release_contract_mirror_mismatch:" + name)
    return errors


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
    errors = frozen_work_laws_errors(ROOT)
    frozen_rejected = ({FROZEN_WORK_MANIFEST} | {
        path for _, source, resource, _ in FROZEN_WORK_DOCUMENTS for path in (source, resource)
    }) if errors else set()
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
        # A refused frozen revision must not be reopened by this unbounded scan.
        # Preserve its controlled refusal and continue scanning all other files.
        if rel.as_posix() in frozen_rejected:
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
    errors.extend(release_contract_errors(ROOT, __version__))
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
