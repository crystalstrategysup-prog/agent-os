"""Published setup knowledge stays bounded, internally consistent and read-only."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from agent_os import cli
from agent_os.setup_scenarios import RESOURCE_ROOT, load_index, show

ROOT = Path(__file__).resolve().parents[1]
PRIMARY_SOURCE_PREFIXES = (
    "https://core.telegram.org/",
    "https://man.openbsd.org/",
    "https://learn.microsoft.com/",
    "https://support.apple.com/",
    "https://www.rfc-editor.org/",
)


def test_public_catalog_matches_versioned_schemas_and_package_copies() -> None:
    index_schema = json.loads((ROOT / "schemas/setup-index-v1.schema.json").read_text())
    scenario_schema = json.loads(
        (ROOT / "schemas/setup-scenario-v1.schema.json").read_text()
    )
    assert (ROOT / "src/agent_os/resources/schemas/setup-index-v1.schema.json").read_bytes() == (
        ROOT / "schemas/setup-index-v1.schema.json"
    ).read_bytes()
    assert (
        ROOT / "src/agent_os/resources/schemas/setup-scenario-v1.schema.json"
    ).read_bytes() == (ROOT / "schemas/setup-scenario-v1.schema.json").read_bytes()

    index = load_index()
    jsonschema.validate(index, index_schema, format_checker=jsonschema.FormatChecker())
    ids = [entry["id"] for entry in index["scenarios"]]
    assert len(ids) == len(set(ids))
    assert sorted(path.name for path in RESOURCE_ROOT.glob("*.json")) == sorted(
        ["index.json", *(f"{identifier}.json" for identifier in ids)]
    )
    for entry in index["scenarios"]:
        scenario = show(entry["id"])
        jsonschema.validate(
            scenario, scenario_schema, format_checker=jsonschema.FormatChecker()
        )
        assert scenario["title"] == entry["title"]
        assert scenario["implementation_status"] == entry["implementation_status"]
        assert scenario["implementation_status"] == "guide_only"
        assert scenario["evidence"]["level"] == "documented"
        assert all(
            source.startswith(PRIMARY_SOURCE_PREFIXES)
            for source in scenario["evidence"]["sources"]
        )

    tunnel = show("ssh-vnc-tunnel")
    assert tunnel["flows"][0]["id"] == "known-route"
    assert len(tunnel["flows"][0]["steps"]) <= 2
    assert {flow["id"] for flow in tunnel["flows"]} == {
        "known-route",
        "new-ssh-route",
        "desktop-over-ssh",
    }


def test_setup_cli_requires_no_user_home_or_update_check(monkeypatch, capsys) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("setup discovery must not touch user configuration or network")

    monkeypatch.setattr("agent_os.config.AgentOSPaths.discover", forbidden)
    monkeypatch.setattr("agent_os.cli.update_advisory_check", forbidden)
    assert cli.main(["setup", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert {row["id"] for row in listed["scenarios"]} == {
        "telegram-mtproto",
        "telegram-business",
        "ssh-vnc-tunnel",
    }
    assert cli.main(["setup", "show", "ssh-vnc-tunnel"]) == 0
    selected = json.loads(capsys.readouterr().out)
    assert selected["id"] == "ssh-vnc-tunnel"


def test_setup_cli_rejects_unknown_or_unsafe_id(capsys) -> None:
    assert cli.main(["setup", "show", "unpublished-scenario"]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "unknown_setup_scenario"
    assert cli.main(["setup", "show", "../config.json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "invalid_setup_scenario_id"
