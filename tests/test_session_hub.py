from __future__ import annotations

import json

import pytest

from agent_os.config import default_config
from agent_os.session_hub import (
    CodexRunner,
    ScreenSession,
    _codex_descendant_session,
    _thread_id_from_jsonl,
    discover_sessions,
    validate_workspace,
)

SESSION_ID = "01a0a2b6-522a-7501-9a78-c093c781141e"


def test_discovers_only_bounded_session_metadata(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    path = root / f"rollout-2026-09-16-{SESSION_ID}.jsonl"
    path.write_text(
        json.dumps(
            {
                "type": "session_meta",
                "payload": {"id": SESSION_ID, "cwd": str(tmp_path / "work")},
            }
        )
        + "\n"
        + json.dumps({"type": "response_item", "payload": {"role": "user", "secret": "x"}})
        + "\n",
        encoding="utf-8",
    )
    config = default_config()
    config["codex"]["session_roots"] = [str(root)]
    sessions = discover_sessions(config)
    assert [item.session_id for item in sessions] == [SESSION_ID]
    assert sessions[0].workspace == str(tmp_path / "work")
    assert not hasattr(sessions[0], "transcript")


def test_workspace_is_restricted_to_configured_roots(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    child = allowed / "child"
    child.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    config = default_config()
    config["codex"]["allowed_workspaces"] = [str(allowed)]
    config["codex"]["default_workspace"] = str(allowed)
    assert validate_workspace(config, child) == child.resolve()
    with pytest.raises(ValueError, match="workspace_not_allowed"):
        validate_workspace(config, outside)


def test_process_tree_maps_screen_to_codex_uuid():
    rows = [
        (100, 1, "SCREEN -S work"),
        (101, 100, "bash"),
        (102, 101, f"codex resume {SESSION_ID}"),
    ]
    assert _codex_descendant_session(100, rows) == SESSION_ID


def test_thread_started_is_parsed_from_codex_jsonl():
    output = json.dumps({"type": "thread.started", "thread_id": SESSION_ID})
    assert _thread_id_from_jsonl(output) == SESSION_ID


def test_runner_preserves_thread_id_before_bounding_output(monkeypatch):
    class Completed:
        returncode = 0
        stdout = (
            json.dumps({"type": "thread.started", "thread_id": SESSION_ID})
            + "\n"
            + ("x" * 20_000)
        )
        stderr = ""

    monkeypatch.setattr("agent_os.session_hub.subprocess.run", lambda *args, **kwargs: Completed())
    result = CodexRunner(default_config()).create_session("hello")
    assert result.session_id == SESSION_ID
    assert len(result.output) == 8_000


def test_runner_rejects_non_uuid_without_launching():
    with pytest.raises(ValueError, match="session_id_invalid"):
        CodexRunner(default_config()).continue_session("latest; rm -rf x", "hello")


def test_screen_record_is_metadata_only():
    screen = ScreenSession("100.work", "work", "Detached", 100, SESSION_ID)
    assert screen.as_dict()["codex_session_id"] == SESSION_ID
