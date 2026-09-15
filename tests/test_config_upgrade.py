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
    assert loaded["schema"] == "agent-os.community-config/v2"
    assert loaded["name"] == "Existing"
    assert loaded["telegram_session_hub"]["enabled"] is False
