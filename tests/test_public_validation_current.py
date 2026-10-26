from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("public_current", ROOT / "tools/verify_public.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def test_current_and_future_matching_versions_are_not_pinned_to_rc2():
    for version in ["0.8.0rc2033", "0.9.0"]:
        assert validator.version_matches('[project]\nversion = "' + version + '"\n', version)


def test_mismatched_or_absent_version_is_rejected():
    assert not validator.version_matches('[project]\nversion = "0.9.0"', "0.8.0rc2033")
    assert not validator.version_matches('[project]\nname = "example"', "0.8.0rc2033")


def test_atlas_is_allowed_only_at_declared_mirror_locations():
    text = "---\nname: atlas\ndescription: Canonical Atlas module\n---\n"
    assert validator.skill_name(Path("src/agent_os/resources/skills/atlas/SKILL.md"), text) == "atlas"
    assert validator.skill_name(Path("modules/atlas/skills/atlas/SKILL.md"), text) == "atlas"
    assert validator.skill_name(Path("unregistered/SKILL.md"), text) is None


def test_unknown_or_malformed_skill_is_rejected():
    assert validator.skill_name(Path("x/SKILL.md"), "---\nname: arbitrary\ndescription: bad\n---\n") is None
    assert validator.skill_name(Path("x/SKILL.md"), "not a skill") is None
