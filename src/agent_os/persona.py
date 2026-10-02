"""Bounded owner preferences and a trusted-interaction response gate.

The caller supplies interaction signals from its authenticated runtime adapter.
The gate supplies a plan; actual microphone/output behavior needs adapter proof.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from . import profile_adapter as profiles
from .handoff_store import scan_secrets
from .overlay import validate_roots
from .safeio import (
    GateError,
    atomic_bytes,
    atomic_json,
    lock,
    now,
    read_json,
    sha,
    within,
)

SCHEMA = "agentos.persona-settings/v1"
DEFAULTS = {
    "tone": "plain",
    "formality": "relaxed",
    "verbosity": "concise",
    "addressing": "addressed_only",
    "listen_first": True,
    "interrupt_others": False,
    "identity": "transparent_ai",
}
OPTIONS = {
    "tone": {"plain", "conversational", "warm"},
    "formality": {"relaxed", "neutral", "formal"},
    "verbosity": {"concise", "normal", "detailed"},
    "addressing": {"addressed_only", "addressed_or_dialogue"},
    "identity": {"transparent_ai"},
}


def validate(settings):
    if not isinstance(settings, dict) or set(settings) - (
        set(DEFAULTS) | {"display_name"}
    ):
        raise GateError("unknown_or_invalid_persona_setting")
    value = {**DEFAULTS, **settings}
    for key, options in OPTIONS.items():
        if not isinstance(value[key], str) or value[key] not in options:
            raise GateError("invalid_persona_" + key)
    if value["listen_first"] is not True or value["interrupt_others"] is not False:
        raise GateError("persona_interaction_boundary_required")
    if "display_name" in value:
        name = value["display_name"]
        if not isinstance(name, str) or not re.fullmatch(r"[\w .-]{1,40}", name):
            raise GateError("invalid_persona_display_name")
    scan_secrets(json.dumps(value).encode())
    return value


def configure(home, settings, *, expected_sha256, source):
    validate_roots(home)
    validate(settings)
    requested = dict(settings)
    if not isinstance(source, str) or not source.strip() or len(source) > 300:
        raise GateError("persona_current_source_required")
    scan_secrets(source.encode())
    path = within(home, "profiles/persona/profile.json")
    with lock(within(home, "state/persona-write.lock")):
        old = path.read_bytes() if path.exists() else None
        current_hash = sha(old) if old is not None else None
        if current_hash != expected_sha256:
            raise GateError("persona_profile_generation_conflict")
        prior = profiles._load(home, "persona")[0] if old is not None else None
        if prior and (prior["scope"] != "owner" or prior["host_binding"] is not None):
            raise GateError("persona_existing_scope_mismatch")
        previous = (
            {
                entry["key"][8:]: json.loads(entry["value"])
                for entry in prior["entries"]
                if entry["key"].startswith("persona.")
            }
            if prior
            else {}
        )
        settings = validate({**previous, **requested})
        entries = (
            [
                entry
                for entry in prior["entries"]
                if not entry["key"].startswith("persona.")
            ]
            if prior
            else []
        )
        entries += [
            {
                "key": "persona." + key,
                "kind": "preference",
                "value": json.dumps(value, ensure_ascii=False),
                "source": source,
                "observed_at": now(),
                "status": "OWNER_CONFIRMED",
            }
            for key, value in sorted(settings.items())
        ]
        value = {
            "schema": profiles.PROFILE_SCHEMA,
            "id": "persona",
            "version": "1",
            "scope": "owner",
            "host_binding": None,
            "entries": entries,
        }
        if (
            len(entries) > profiles.ENTRY_LIMIT
            or len(json.dumps(value).encode()) > profiles.FILE_LIMIT
        ):
            raise GateError("persona_profile_size_limit")
        if old is not None:
            backup = within(home, "backups/persona/" + current_hash + ".json")
            if not backup.exists():
                atomic_bytes(backup, old)
        atomic_json(path, value)
        _, written_hash = profiles._load(home, "persona")
    return {
        "status": "CONFIGURED_REQUIRES_SELECTION",
        "profile_id": "persona",
        "sha256": written_hash,
        "profile_authority": False,
        "live_behavior_proven": False,
        "selection": "Use existing profiles inventory/select with exact hashes and explicit conflict decisions.",
    }


def settings(home):
    context = profiles.context(home)
    if context["status"] == "STALE_SELECTION":
        return {
            "schema": SCHEMA,
            "status": "STALE_SELECTION",
            "settings": {},
            "profile_authority": False,
        }
    configured = {}
    for entry in context["entries"]:
        if entry["key"].startswith("persona."):
            if entry["kind"] != "preference" or entry["status"] != "OWNER_CONFIRMED":
                raise GateError("persona_owner_confirmation_required")
            try:
                configured[entry["key"][8:]] = json.loads(entry["value"])
            except ValueError as exc:
                raise GateError("invalid_persona_preference") from exc
    return {
        "schema": SCHEMA,
        "status": "ACTIVE" if configured else "DEFAULTS",
        "settings": validate(configured),
        "profile_authority": False,
        "live_behavior_proven": False,
        "selected_ids": context["selected_ids"],
    }


def response_plan(home, interaction):
    keys = {"addressed", "user_speaking", "other_conversation", "utterance_complete"}
    if (
        not isinstance(interaction, dict)
        or set(interaction) not in (keys, keys | {"dialogue_continuation"})
        or any(type(value) is not bool for value in interaction.values())
    ):
        raise GateError("trusted_interaction_signals_required")
    preferences = settings(home)
    if preferences["status"] == "STALE_SELECTION":
        return {
            "status": "BLOCKED",
            "action": "silent",
            "reason": "STALE_SELECTION",
            "live_behavior_proven": False,
        }
    if interaction["user_speaking"] or not interaction["utterance_complete"]:
        action, reason = "listen", "wait_for_completed_utterance"
    elif not (
        interaction["addressed"]
        or (
            preferences["settings"]["addressing"] == "addressed_or_dialogue"
            and interaction.get("dialogue_continuation", False)
            and not interaction["other_conversation"]
        )
    ):
        action, reason = "silent", "not_addressed"
    else:
        action, reason = "respond", "addressed_and_finished"
    return {
        "status": "PLANNED",
        "action": action,
        "reason": reason,
        "preferences": preferences["settings"],
        "historical_permissions_grant_authority": False,
        "live_behavior_proven": False,
    }


def command(argv, home):
    parser = argparse.ArgumentParser(prog="agentos persona")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("context")
    plan = sub.add_parser("plan")
    plan.add_argument("--input", type=Path, required=True)
    config = sub.add_parser("configure")
    config.add_argument("--settings", type=Path, required=True)
    config.add_argument("--expected-sha256")
    config.add_argument("--source", required=True)
    args = parser.parse_args(argv)
    if args.action == "context":
        return settings(home), 0
    if args.action == "plan":
        result = response_plan(home, read_json(args.input))
        return result, 2 if result["status"] == "BLOCKED" else 0
    return configure(
        home,
        read_json(args.settings),
        expected_sha256=args.expected_sha256,
        source=args.source,
    ), 0
