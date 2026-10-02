import json

import pytest

from agent_os import persona, profile_adapter
from agent_os.safeio import GateError


def test_private_settings_active_only_after_existing_hash_selection(tmp_path):
    home = tmp_path / "owner"
    assert persona.settings(home)["status"] == "DEFAULTS"
    configured = persona.configure(
        home,
        {"display_name": "ExampleAgent", "tone": "conversational"},
        expected_sha256=None,
        source="Explicit synthetic owner instruction",
    )
    assert configured["status"] == "CONFIGURED_REQUIRES_SELECTION"
    assert persona.settings(home)["status"] == "DEFAULTS"
    inventory = profile_adapter.inventory(home, ["persona"])
    profile_adapter.activate(home, "one", ["persona"], inventory["inventory_digest"])
    context = persona.settings(home)
    assert (
        context["status"] == "ACTIVE"
        and context["settings"]["tone"] == "conversational"
    )
    assert (
        context["settings"]["display_name"] == "ExampleAgent"
        and not context["profile_authority"]
    )
    original = (home / "profiles/persona/profile.json").read_bytes()
    persona.configure(
        home,
        {"tone": "warm"},
        expected_sha256=configured["sha256"],
        source="New explicit synthetic owner instruction",
    )
    assert persona.settings(home)["status"] == "STALE_SELECTION"
    assert (
        home / "backups/persona" / (configured["sha256"] + ".json")
    ).read_bytes() == original
    result = persona.response_plan(
        home,
        {
            "addressed": True,
            "user_speaking": False,
            "other_conversation": False,
            "utterance_complete": True,
        },
    )
    assert result["status"] == "BLOCKED" and result["action"] == "silent"
    inventory = profile_adapter.inventory(home, ["persona"])
    profile_adapter.activate(home, "one", ["persona"], inventory["inventory_digest"])
    assert persona.settings(home)["settings"]["display_name"] == "ExampleAgent"


@pytest.mark.parametrize(
    "settings",
    [
        {"human_biography": "A childhood somewhere"},
        {"identity": "human"},
        {"interrupt_others": True},
        {"listen_first": False},
        {"tone": "unknown"},
        {"display_name": "bad\nname"},
    ],
)
def test_unknown_biography_and_boundary_changes_refused(settings):
    with pytest.raises(GateError):
        persona.validate(settings)


@pytest.mark.parametrize(
    "signals,expected",
    [
        (
            {
                "addressed": True,
                "user_speaking": True,
                "other_conversation": False,
                "utterance_complete": False,
            },
            "listen",
        ),
        (
            {
                "addressed": False,
                "user_speaking": False,
                "other_conversation": True,
                "utterance_complete": True,
            },
            "silent",
        ),
        (
            {
                "addressed": False,
                "user_speaking": False,
                "other_conversation": False,
                "utterance_complete": True,
            },
            "silent",
        ),
        (
            {
                "addressed": True,
                "user_speaking": False,
                "other_conversation": True,
                "utterance_complete": True,
            },
            "respond",
        ),
    ],
)
def test_addressed_listening_gate_is_actual_plan_not_live_voice_claim(
    tmp_path, signals, expected
):
    result = persona.response_plan(tmp_path / "owner", signals)
    assert result["action"] == expected and result["live_behavior_proven"] is False
    assert result["preferences"]["identity"] == "transparent_ai"
    assert "display_name" not in result["preferences"]


def test_profile_conflict_and_configuration_cas_remain_required(tmp_path):
    home = tmp_path / "owner"
    value = persona.configure(
        home,
        {"tone": "warm"},
        expected_sha256=None,
        source="Synthetic current owner instruction",
    )
    with pytest.raises(GateError, match="generation_conflict"):
        persona.configure(
            home,
            {"tone": "plain"},
            expected_sha256=None,
            source="Synthetic current owner instruction",
        )
    profile = json.loads((home / "profiles/persona/profile.json").read_text())
    profile["id"] = "other"
    for entry in profile["entries"]:
        if entry["key"] == "persona.tone":
            entry["value"] = json.dumps("plain")
    path = home / "profiles/other/profile.json"
    path.parent.mkdir()
    path.write_text(json.dumps(profile))
    inventory = profile_adapter.inventory(home, ["persona", "other"])
    with pytest.raises(GateError, match="conflict_decisions_required"):
        profile_adapter.activate(
            home, "all", ["persona", "other"], inventory["inventory_digest"]
        )
    assert value["live_behavior_proven"] is False


def test_explicit_current_dialogue_is_allowed_but_others_conversation_is_not(tmp_path):
    home = tmp_path / "owner"
    persona.configure(
        home,
        {"addressing": "addressed_or_dialogue"},
        expected_sha256=None,
        source="Synthetic explicit owner instruction",
    )
    inventory = profile_adapter.inventory(home, ["persona"])
    profile_adapter.activate(home, "one", ["persona"], inventory["inventory_digest"])
    event = {
        "addressed": False,
        "user_speaking": False,
        "utterance_complete": True,
        "other_conversation": False,
        "dialogue_continuation": True,
    }
    assert persona.response_plan(home, event)["action"] == "respond"
    assert (
        persona.response_plan(home, {**event, "other_conversation": True})["action"]
        == "silent"
    )
    assert (
        persona.response_plan(home, {**event, "user_speaking": True})["action"]
        == "listen"
    )
