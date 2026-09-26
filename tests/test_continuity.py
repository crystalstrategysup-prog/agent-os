"""The public continuity guide must be packaged without a personal passport."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = files("agent_os").joinpath("resources")


def test_guide_and_template_are_shipped_as_generic_resources() -> None:
    source = (ROOT / "docs/WORK_CONTINUITY.md").read_bytes()
    packaged = RESOURCES.joinpath("docs/WORK_CONTINUITY.md").read_bytes()
    assert packaged == source

    guide = packaged.decode()
    template = RESOURCES.joinpath("templates/work-continuity-passport.md").read_text()
    assert "external overlay" in guide
    assert "restore a sample" in guide
    assert "server sync" in guide
    for heading in (
        "## Project index",
        "## Current handoffs",
        "## Data and recovery map",
        "## Passport-copy proof",
        "## Maintenance log and outstanding checks",
    ):
        assert heading in template
    for private_marker in ("/" + "Users/", "@gmail.com", "api_hash", "session_string"):
        assert private_marker not in guide
        assert private_marker not in template


def test_knowledge_and_handoff_routes_point_to_same_guide() -> None:
    for skill in ("agentos-knowledge-maintenance", "agentos-project-handoff"):
        content = RESOURCES.joinpath(f"skills/{skill}/SKILL.md").read_text()
        assert "resources/docs/WORK_CONTINUITY.md" in content
