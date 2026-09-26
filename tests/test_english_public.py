"""The distributed public surface uses one reviewed source language."""

from __future__ import annotations

import json
import re
from pathlib import Path

from agent_os.doc_catalog import DOCS

ROOT = Path(__file__).resolve().parents[1]
CYRILLIC = re.compile(r"[\u0400-\u04ff]")


def test_public_source_has_no_cyrillic_copy() -> None:
    excluded = {".git", ".venv", ".agentos", "__pycache__", ".pytest_cache", "dist", "build"}
    suffixes = {".md", ".py", ".json", ".toml", ".txt", ".yml", ".yaml", ".sh"}
    paths = [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not set(path.relative_to(ROOT).parts) & excluded
        and not any(part.endswith(".egg-info") for part in path.relative_to(ROOT).parts)
        and path.suffix in suffixes
    ]
    offenders = [str(path.relative_to(ROOT)) for path in paths if CYRILLIC.search(path.read_text())]
    assert offenders == []


def test_document_source_package_and_catalog_agree() -> None:
    source = ROOT / "docs"
    packaged = ROOT / "src/agent_os/resources/docs"
    source_names = {path.name for path in source.glob("*.md")}
    packaged_names = {path.name for path in packaged.glob("*.md")}
    assert packaged_names - source_names == {"PROJECT_BASELINE.md"}
    assert "README.ru.md" not in source_names
    for name in source_names:
        assert (source / name).read_bytes() == (packaged / name).read_bytes()

    catalog = json.loads((ROOT / "src/agent_os/resources/catalog.json").read_text())
    assert set(catalog["documents"]) == set(DOCS)
    for name, (title, headings) in DOCS.items():
        assert catalog["documents"][name]["title"] == title
        assert catalog["documents"][name]["headings"] == list(headings)
        template = (ROOT / "src/agent_os/resources/templates" / f"{name}.md").read_text()
        assert template.startswith(f"# {title}\n")
        assert re.findall(r"^## (.+)$", template, flags=re.MULTILINE) == list(headings)
