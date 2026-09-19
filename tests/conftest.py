from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def no_implicit_update_network(monkeypatch):
    def current(*args, **kwargs):
        return {
            "schema": "agent-os.community-update-advisory/v1",
            "status": "CURRENT",
            "check_performed": False,
            "cache_reused": True,
            "current_version": "0.4.0",
            "latest_version": "0.4.0",
            "latest_tag_url": "https://github.com/crystalstrategysup-prog/agent-os/tree/v0.4.0",
            "automatic_install": False,
        }

    monkeypatch.setattr("agent_os.cli.update_advisory_check", current)
