from __future__ import annotations

import json
import stat

import pytest

from agent_os.config import AgentOSPaths, load_config
from agent_os.doctor import run
from agent_os.mcp_server import response
from agent_os.onboarding import public_plan
from agent_os.tasks import normalize_task


def test_init_creates_private_tree(tmp_path):
    paths = AgentOSPaths.discover(tmp_path / "agent-os")
    paths.initialize()
    assert load_config(paths)["schema"] == "agent-os.community-config/v4"
    assert stat.S_IMODE(paths.secrets.stat().st_mode) == 0o700
    assert run(paths)["status"] == "PASS"


def test_telegram_plan_is_telegram_only_and_secret_free():
    plan = public_plan()
    assert plan["website_required"] is False
    assert [step["id"] for step in plan["steps"]][:3] == [
        "telegram_account",
        "owner_approval",
        "string_session",
    ]
    serialized = json.dumps(plan)
    assert "STRING_SESSION" in serialized
    assert "api_hash=" not in serialized.lower()


def test_task_is_deterministic_and_bounded():
    first = normalize_task(" Check   status ")
    second = normalize_task("Check status")
    assert first == second
    with pytest.raises(ValueError):
        normalize_task("run", risk="root")


def test_mcp_lists_and_calls_safe_tools():
    listed = response({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert len(listed["result"]["tools"]) == 3
    called = response(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "agentos_normalize_task", "arguments": {"objective": "Hello"}},
        }
    )
    assert called["result"]["structuredContent"]["risk"] == "R0"
