from pathlib import Path
import importlib.util
import json

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("public_current", ROOT / "tools/verify_public.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def test_current_and_future_matching_versions_are_not_pinned_to_rc2():
    for version in ["0.8.0rc2033", "0.8.0rc2041+agentas3", "0.8.0rc2042", "0.9.0"]:
        assert validator.version_matches('[project]\nversion = "' + version + '"\n', version)


def test_mismatched_or_absent_version_is_rejected():
    assert not validator.version_matches('[project]\nversion = "0.9.0"', "0.8.0rc2033")
    assert not validator.version_matches('[project]\nname = "example"', "0.8.0rc2033")
    assert not validator.version_matches('not valid toml', "0.8.0rc2042")
    assert not validator.version_matches('[project]\nversion = "arbitrary"', "arbitrary")


def test_atlas_is_allowed_only_at_declared_mirror_locations():
    text = "---\nname: atlas\ndescription: Canonical Atlas module\n---\n"
    assert validator.skill_name(Path("src/agent_os/resources/skills/atlas/SKILL.md"), text) == "atlas"
    assert validator.skill_name(Path("modules/atlas/skills/atlas/SKILL.md"), text) == "atlas"
    assert validator.skill_name(Path("unregistered/SKILL.md"), text) is None


def test_unknown_or_malformed_skill_is_rejected():
    assert validator.skill_name(Path("x/SKILL.md"), "---\nname: arbitrary\ndescription: bad\n---\n") is None
    assert validator.skill_name(Path("x/SKILL.md"), "not a skill") is None
    text = "---\nname: agentos-project-entry\ndescription: Canonical skill\n---\n"
    assert validator.skill_name(Path("src/agent_os/resources/skills/agentos-project-entry/SKILL.md"), text) == "agentos-project-entry"
    assert validator.skill_name(Path("src/agent_os/resources/skills/agentos-other/SKILL.md"), text) is None
    assert validator.skill_name(Path("src/agent_os/resources/skills/agentos-project-entry/nested/SKILL.md"), text) is None


def release_contracts(root, version):
    for directory in ("schemas", "src/agent_os/resources/contracts"):
        target = root / directory
        target.mkdir(parents=True)
        (target / "mcp-tools-v1.json").write_text(json.dumps({"serverInfo": {"version": version}}))
        (target / "cli-contract-v1.json").write_text(json.dumps({"distribution_version": version, "release": version}))


def test_matching_release_contract_versions_and_mirrors(tmp_path):
    release_contracts(tmp_path, "0.9.0")
    assert validator.release_contract_errors(tmp_path, "0.9.0") == []


@pytest.mark.parametrize("directory", ["schemas", "src/agent_os/resources/contracts"])
@pytest.mark.parametrize("name,field", [("mcp-tools-v1.json", "serverInfo"),
                                       ("cli-contract-v1.json", "distribution_version"),
                                       ("cli-contract-v1.json", "release")])
def test_stale_authoritative_or_packaged_release_version_refused(tmp_path, directory, name, field):
    release_contracts(tmp_path, "0.9.0")
    path = tmp_path / directory / name
    value = json.loads(path.read_text())
    value[field] = {"version": "0.8.0"} if field == "serverInfo" else "0.8.0"
    path.write_text(json.dumps(value))
    errors = validator.release_contract_errors(tmp_path, "0.9.0")
    assert "release_contract_version_mismatch:" + directory + "/" + name in errors
    assert "release_contract_mirror_mismatch:" + name in errors


@pytest.mark.parametrize("replacement", [None, "[]", "{}", "not-json"])
def test_missing_or_invalid_release_contract_refused(tmp_path, replacement):
    release_contracts(tmp_path, "0.9.0")
    path = tmp_path / "schemas/mcp-tools-v1.json"
    if replacement is None:
        path.unlink()
    else:
        path.write_text(replacement)
    assert any(e.startswith("release_contract_invalid:") for e in validator.release_contract_errors(tmp_path, "0.9.0"))


def test_release_contract_mirror_drift_refused_even_with_matching_versions(tmp_path):
    release_contracts(tmp_path, "0.9.0")
    path = tmp_path / "src/agent_os/resources/contracts/mcp-tools-v1.json"
    value = json.loads(path.read_text()); value["unexpected"] = True
    path.write_text(json.dumps(value))
    assert validator.release_contract_errors(tmp_path, "0.9.0") == ["release_contract_mirror_mismatch:mcp-tools-v1.json"]
