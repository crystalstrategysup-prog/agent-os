"""External profile adapter behavior on disposable user homes."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from agent_os import profile_adapter, project
from agent_os.safeio import GateError, atomic_json


def profile(
    home: Path,
    profile_id: str,
    *,
    value: str = "ru",
    key: str = "owner.language",
    scope: str = "owner",
    binding: str | None = None,
) -> Path:
    path = home / "profiles" / profile_id / "profile.json"
    atomic_json(
        path,
        {
            "schema": profile_adapter.PROFILE_SCHEMA,
            "id": profile_id,
            "version": "1.0.0",
            "scope": scope,
            "host_binding": binding,
            "entries": [
                {
                    "key": key,
                    "kind": "preference",
                    "value": value,
                    "source": "owner interview",
                    "observed_at": "2026-09-25T00:00:00Z",
                    "status": "OWNER_CONFIRMED",
                }
            ],
        },
    )
    return path


def test_zero_profiles_keeps_core_usable(tmp_path):
    home = tmp_path / "user"
    assert profile_adapter.inventory(home)["available_ids"] == []
    assert profile_adapter.context(home)["status"] == "NONE"
    assert profile_adapter.activate(home, "none", [], None)["status"] == "SELECTED"
    assert profile_adapter.context(home)["entries"] == []
    assert profile_adapter.context(home)["profile_authority"] is False
    assert (
        project.questionnaire(tmp_path, user_home=home)["selected_profile_context"][
            "status"
        ]
        == "NONE"
    )


def test_one_exact_profile_prefills_project_interview(tmp_path):
    home = tmp_path / "user"
    profile(home, "owner")
    inv = profile_adapter.inventory(home, ["owner"])
    assert inv["status"] == "PASS"
    profile_adapter.activate(home, "one", ["owner"], inv["inventory_digest"])
    context = profile_adapter.context(home)
    assert context["status"] == "ACTIVE"
    assert context["entries"][0]["value"] == "ru"
    assert context["entries"][0]["profile_id"] == "owner"
    assert context["profile_authority"] is False
    assert (
        project.questionnaire(tmp_path, user_home=home)["selected_profile_context"][
            "entries"
        ][0]["key"]
        == "owner.language"
    )


def test_all_requires_inventory_and_explicit_conflict_choice(tmp_path):
    home = tmp_path / "user"
    profile(home, "owner", value="ru")
    profile(home, "work", value="en")
    inv = profile_adapter.inventory(home, ["owner", "work"])
    assert inv["status"] == "CONFLICTS"
    with pytest.raises(GateError, match="profile_conflict_decisions_required"):
        profile_adapter.activate(
            home, "all", ["owner", "work"], inv["inventory_digest"]
        )
    assert profile_adapter.context(home)["status"] == "NONE"
    result = profile_adapter.activate(
        home,
        "all",
        ["owner", "work"],
        inv["inventory_digest"],
        {"owner.language": "work"},
    )
    assert result["conflict_count"] == 1
    selected = profile_adapter.context(home)
    assert selected["selected_ids"] == ["owner", "work"]
    assert selected["entries"][0]["value"] == "en"


def test_all_requires_exact_owner_order_and_digest(tmp_path):
    home = tmp_path / "user"
    profile(home, "owner", key="owner.language")
    profile(home, "mac", key="host.kind", value="mac")
    inv = profile_adapter.inventory(home, ["mac", "owner"])
    with pytest.raises(GateError, match="ordered_full_inventory"):
        profile_adapter.activate(home, "all", ["owner"], inv["inventory_digest"])
    with pytest.raises(GateError, match="inventory_digest_mismatch"):
        profile_adapter.activate(home, "all", ["owner", "mac"], inv["inventory_digest"])
    profile_adapter.activate(home, "all", ["mac", "owner"], inv["inventory_digest"])
    assert profile_adapter.context(home)["selected_ids"] == ["mac", "owner"]


def test_deleted_or_changed_profile_invalidates_selection(tmp_path):
    home = tmp_path / "user"
    path = profile(home, "owner")
    inv = profile_adapter.inventory(home, ["owner"])
    profile_adapter.activate(home, "one", ["owner"], inv["inventory_digest"])
    body = json.loads(path.read_text())
    body["entries"][0]["value"] = "de"
    atomic_json(path, body)
    assert profile_adapter.context(home)["status"] == "STALE_SELECTION"
    assert profile_adapter.context(home)["entries"] == []
    path.unlink()
    assert profile_adapter.context(home)["status"] == "STALE_SELECTION"
    profile_adapter.activate(home, "none", [], None)
    assert profile_adapter.context(home)["status"] == "NONE"


def test_host_binding_and_symlink_refused(tmp_path):
    home = tmp_path / "user"
    profile(home, "mac", scope="host", binding="some-other-host")
    inv = profile_adapter.inventory(home, ["mac"])
    if socket.gethostname() != "some-other-host":
        assert inv["status"] == "BINDING_MISMATCH"
        assert inv["binding_mismatches"] == ["mac"]
        with pytest.raises(GateError, match="profile_host_binding_mismatch"):
            profile_adapter.activate(home, "one", ["mac"], inv["inventory_digest"])
    (home / "profiles" / "mac" / "profile.json").unlink()
    (home / "profiles" / "mac" / "profile.json").symlink_to(tmp_path / "outside")
    with pytest.raises(GateError, match="symlink_path_refused"):
        profile_adapter.inventory(home)


def test_secret_like_profile_value_refused(tmp_path):
    home = tmp_path / "user"
    profile(home, "owner", value="sk-" + "x" * 32)
    with pytest.raises(GateError, match="profile_secret_like_value_refused"):
        profile_adapter.inventory(home)


def test_tampered_selection_cannot_silently_choose_conflict(tmp_path):
    home = tmp_path / "user"
    profile(home, "owner", value="ru")
    profile(home, "work", value="en")
    inv = profile_adapter.inventory(home, ["owner", "work"])
    profile_adapter.activate(
        home,
        "all",
        ["owner", "work"],
        inv["inventory_digest"],
        {"owner.language": "owner"},
    )
    path = home / "state/profile-selection.json"
    body = json.loads(path.read_text())
    body["decisions"]["owner.language"] = "unknown"
    atomic_json(path, body)
    assert profile_adapter.context(home)["status"] == "STALE_SELECTION"


def test_all_selection_stales_when_new_profile_appears(tmp_path):
    home = tmp_path / "user"
    profile(home, "owner")
    inv = profile_adapter.inventory(home)
    profile_adapter.activate(home, "all", ["owner"], inv["inventory_digest"])
    profile(home, "mac", key="host.role", value="workstation")
    assert profile_adapter.context(home)["status"] == "STALE_SELECTION"


def test_none_selection_ignores_invalid_profile_store(tmp_path):
    home = tmp_path / "user"
    (home / "profiles" / "INVALID").mkdir(parents=True)
    profile_adapter.activate(home, "none", [], None)
    assert profile_adapter.context(home)["status"] == "NONE"


def test_interview_prefills_live_device_and_asks_unknowns(tmp_path):
    home = tmp_path / "user"
    profile(home, "owner", value="ru")
    inv = profile_adapter.inventory(home)
    profile_adapter.activate(home, "one", ["owner"], inv["inventory_digest"])
    result = profile_adapter.interview(home)
    assert result["device_observations"]["status"] == "LIVE_OBSERVED"
    assert result["device_observations"]["hostname"]
    assert result["selected_profile_context"]["status"] == "ACTIVE"
    assert "owner.language" not in {q["key"] for q in result["unanswered_questions"]}
    assert "owner.display_name" in {q["key"] for q in result["unanswered_questions"]}


def test_malformed_profile_types_and_decisions_fail_closed(tmp_path):
    home = tmp_path / "user"
    path = profile(home, "owner")
    body = json.loads(path.read_text())
    body["scope"] = []
    atomic_json(path, body)
    with pytest.raises(GateError, match="invalid_profile_scope"):
        profile_adapter.inventory(home)
    body["scope"] = "owner"
    body["entries"][0]["kind"] = []
    atomic_json(path, body)
    with pytest.raises(GateError, match="invalid_profile_entry_type"):
        profile_adapter.inventory(home)
    body["entries"][0]["kind"] = "preference"
    atomic_json(path, body)
    inv = profile_adapter.inventory(home)
    with pytest.raises(GateError, match="invalid_profile_conflict_decisions"):
        profile_adapter.activate(home, "one", ["owner"], inv["inventory_digest"], [])


def test_public_cli_inventory_and_interview(tmp_path):
    home = tmp_path / "user"
    profile(home, "owner")
    for action in ("inventory", "interview"):
        run = subprocess.run(
            [sys.executable, "-m", "agent_os", "--home", str(home), "profiles", action],
            text=True,
            capture_output=True,
            check=True,
        )
        result = json.loads(run.stdout)
        assert result["schema"] == f"agentos.profile-{action}/v1"


def test_packaged_profile_schema_accepts_runtime_fixture(tmp_path):
    home = tmp_path / "user"
    path = profile(home, "owner")
    schema = json.loads(
        (
            Path(profile_adapter.__file__).parent
            / "resources/schemas/profile.schema.json"
        ).read_text()
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(json.loads(path.read_text()))


def test_documented_personal_field_is_still_asked_for_confirmation(tmp_path):
    home = tmp_path / "user"
    path = profile(home, "owner")
    body = json.loads(path.read_text())
    body["entries"][0]["status"] = "DOCUMENTED"
    atomic_json(path, body)
    inv = profile_adapter.inventory(home)
    profile_adapter.activate(home, "one", ["owner"], inv["inventory_digest"])
    interview = profile_adapter.interview(home)
    assert "owner.language" in {q["key"] for q in interview["unanswered_questions"]}
