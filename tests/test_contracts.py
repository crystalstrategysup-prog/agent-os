"""Exercise the published contracts against real public entry points."""

from __future__ import annotations

import importlib.util
import json
import sys
import tomllib
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from agent_os import __version__, project
from agent_os.config import AgentOSPaths
from agent_os.mcp_server import MCP_CONTRACT, response

ROOT = Path(__file__).resolve().parents[1]


def test_release_and_mcp_versions_have_one_identity():
    package_version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
        "version"
    ]
    assert __version__ == "0.5.2"
    assert package_version == __version__.replace("-beta.", "b")
    initialized = response({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert initialized["result"]["serverInfo"] == MCP_CONTRACT["serverInfo"]
    assert initialized["result"]["serverInfo"]["version"] == __version__


def test_mcp_input_output_contracts_match_live_tools(tmp_path, monkeypatch):
    home = tmp_path / "user"
    AgentOSPaths.discover(home).initialize()
    monkeypatch.setenv("AGENTOS_USER_HOME", str(home))
    source = json.loads((ROOT / "schemas/mcp-tools-v1.json").read_text())
    installed = json.loads(
        (ROOT / "src/agent_os/resources/contracts/mcp-tools-v1.json").read_text()
    )
    assert source == installed == MCP_CONTRACT
    listed = response({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed["result"]["tools"] == source["tools"]
    samples = {
        "agentos_get_telegram_setup_plan": {},
        "agentos_normalize_task": {"objective": "Review a fixture"},
        "agentos_doctor": {},
        "agentos_get_project_entry_plan": {},
        "agentos_select_documents": {"types": ["platform"], "features": ["public"]},
        "agentos_get_foundation_status": {},
    }
    for tool in source["tools"]:
        name = tool["name"]
        Draft202012Validator.check_schema(tool["inputSchema"])
        Draft202012Validator.check_schema(tool["outputSchema"])
        Draft202012Validator(tool["inputSchema"]).validate(samples[name])
        called = response(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": name, "arguments": samples[name]},
            }
        )
        assert not called["result"].get("isError"), name
        Draft202012Validator(tool["outputSchema"]).validate(
            called["result"]["structuredContent"]
        )


def test_project_task_and_event_contracts_accept_actual_records(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    project.initialize(
        root,
        "Synthetic project",
        ["general"],
        [],
        {
            "purpose": "Validate the actual project record against its public schema.",
            "current_state": "An empty synthetic project directory.",
            "boundaries": "Temporary files only, no external side effects.",
            "constraints": "No network, credentials or private data.",
        },
    )
    answers = {
        key: "Synthetic fixture fact with no external authority."
        for key in project.QUESTIONS
    }
    answers.update(
        {
            "change_kind": "implementation",
            "write_paths": ["maths.py"],
            "acceptance": [
                {"id": "sum", "criterion": "The sum equals five.", "checks": ["sum"]}
            ],
            "checks": [{"id": "sum", "argv": [sys.executable, "-c", "assert 2+3==5"]}],
        }
    )
    entered = project.enter(
        root,
        answers,
        session_id="fixture-session",
        turn_id="fixture-turn",
        user_home=tmp_path / "user",
    )
    task_id = entered["task_id"]
    task = project.load_task(root, task_id)
    task_schema = json.loads((ROOT / "schemas/project-task-v1.schema.json").read_text())
    event_schema = json.loads(
        (ROOT / "schemas/project-event-v1.schema.json").read_text()
    )
    Draft202012Validator.check_schema(task_schema)
    Draft202012Validator.check_schema(event_schema)
    Draft202012Validator(task_schema).validate(task)
    Draft202012Validator(task_schema).validate({**task, "status": "VERIFYING"})
    with pytest.raises(ValidationError):
        Draft202012Validator(task_schema).validate({**task, "status": "COMPLETE"})
    event_path = root / ".agentos/tasks" / task_id / "events.jsonl"
    for line in event_path.read_text().splitlines():
        Draft202012Validator(event_schema).validate(json.loads(line))
    with pytest.raises(ValidationError):
        Draft202012Validator(event_schema).validate(
            {"at": task["entered_at"], "event": "WRITE", "details": {}}
        )
    assert task_schema == json.loads(
        (
            ROOT / "src/agent_os/resources/schemas/project-task-v1.schema.json"
        ).read_text()
    )
    assert event_schema == json.loads(
        (
            ROOT / "src/agent_os/resources/schemas/project-event-v1.schema.json"
        ).read_text()
    )


def test_cli_contract_is_packaged_and_release_tree_refuses_runtime_receipts(tmp_path):
    source = json.loads((ROOT / "schemas/cli-contract-v1.json").read_text())
    installed = json.loads(
        (ROOT / "src/agent_os/resources/contracts/cli-contract-v1.json").read_text()
    )
    assert source == installed
    assert source["release"] == __version__
    assert {
        "project enter",
        "project next-turn",
        "project close",
        "overlay import",
        "install.py rollback",
    } <= {row["name"] for row in source["commands"]}
    spec = importlib.util.spec_from_file_location(
        "agentos_public_verifier", ROOT / "tools/verify_public.py"
    )
    assert spec and spec.loader
    verify_public = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify_public)

    (tmp_path / ".agentos").mkdir()
    assert verify_public.runtime_receipts_present(tmp_path)
