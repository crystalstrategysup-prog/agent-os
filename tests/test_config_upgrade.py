from __future__ import annotations

import json

from agent_os.config import AgentOSPaths, load_config


def test_v1_config_is_upgraded_in_memory_without_losing_values(tmp_path):
    paths = AgentOSPaths.discover(tmp_path / "home")
    paths.initialize()
    paths.config.write_text(
        json.dumps(
            {
                "schema": "agent-os.community-config/v1",
                "name": "Existing",
                "telegram_business": {"enabled": True},
                "mcp": {"transport": "stdio", "allow_arbitrary_shell": False},
            }
        ),
        encoding="utf-8",
    )
    loaded = load_config(paths)
    assert loaded["schema"] == "agent-os.community-config/v4"
    assert loaded["name"] == "Existing"
    assert loaded["telegram_session_hub"]["enabled"] is False
    assert loaded["model_routing"]["profiles"]["coordinator"]["model"] == "gpt-5.6-sol"


def test_v2_nested_values_are_preserved_when_v3_defaults_are_added(tmp_path):
    paths = AgentOSPaths.discover(tmp_path / "home")
    paths.initialize()
    paths.config.write_text(
        json.dumps({
            "schema": "agent-os.community-config/v2",
            "codex": {"executable": "/custom/codex"},
        }),
        encoding="utf-8",
    )
    loaded = load_config(paths)
    assert loaded["schema"] == "agent-os.community-config/v4"
    assert loaded["codex"]["executable"] == "/custom/codex"
    assert loaded["codex"]["turn_timeout_seconds"] == 1800


def test_v3_partial_config_is_completed_without_overwriting_values(tmp_path):
    paths = AgentOSPaths.discover(tmp_path / "home")
    paths.initialize()
    paths.config.write_text(
        json.dumps({
            "schema": "agent-os.community-config/v3",
            "model_routing": {"delegate_by_default": True},
        }),
        encoding="utf-8",
    )
    loaded = load_config(paths)
    assert loaded["schema"] == "agent-os.community-config/v4"
    assert loaded["model_routing"]["delegate_by_default"] is True
    assert loaded["model_routing"]["profiles"]["worker"]["model"] == "gpt-5.6-terra"
    assert loaded["update_advisory"]["interval_seconds"] == 172800
    assert loaded["update_advisory"]["automatic_install"] is False
