"""Optional, bounded user profiles outside the public AgentOS package.

The adapter transports owner-owned context. It never grants tool authority.
"""

from __future__ import annotations

import argparse
import getpass
import platform
import re
import socket
from datetime import datetime
from pathlib import Path
from typing import Any

from .overlay import validate_roots
from .safeio import (
    GateError,
    atomic_json,
    digest,
    identifier,
    now,
    read_json,
    sha,
    within,
)

PROFILE_SCHEMA = "agentos.profile/v1"
SELECTION_SCHEMA = "agentos.profile-selection/v1"
SCOPES = {"owner", "host", "project", "custom"}
KINDS = {"fact", "preference", "instruction"}
STATUSES = {"OWNER_CONFIRMED", "LIVE_OBSERVED", "DOCUMENTED", "INFERRED"}
PROFILE_LIMIT = 32
ENTRY_LIMIT = 64
FILE_LIMIT = 64 * 1024
CONTEXT_LIMIT = 32 * 1024
KEY = re.compile(r"[a-z][a-z0-9_.-]{0,99}\Z")
SECRET = re.compile(
    r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|"
    r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"\d{8,10}:[A-Za-z0-9_-]{30,})\b"
)


def _text(value: Any, name: str, limit: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(ord(char) < 32 and char not in "\n\t" for char in value)
    ):
        raise GateError("invalid_profile_" + name)
    if SECRET.search(value):
        raise GateError("profile_secret_like_value_refused")
    return value


def _profile_id(value: Any) -> str:
    value = identifier(value)
    if value.lower() != value:
        raise GateError("profile_id_must_be_lowercase")
    return value


def _paths(home: Path, profile_id: str) -> Path:
    validate_roots(home)
    return within(home, f"profiles/{_profile_id(profile_id)}/profile.json")


def _load(home: Path, profile_id: str) -> tuple[dict, str]:
    path = _paths(home, profile_id)
    if not path.is_file() or path.stat().st_size > FILE_LIMIT:
        raise GateError("profile_missing_or_oversized")
    if path.stat().st_nlink != 1:
        raise GateError("profile_hardlink_refused")
    raw = path.read_bytes()
    profile = read_json(path)
    if not isinstance(profile, dict) or set(profile) != {
        "schema",
        "id",
        "version",
        "scope",
        "host_binding",
        "entries",
    }:
        raise GateError("invalid_profile_shape")
    if profile["schema"] != PROFILE_SCHEMA or profile["id"] != profile_id:
        raise GateError("profile_identity_mismatch")
    _text(profile["version"], "version", 80)
    if not isinstance(profile["scope"], str) or profile["scope"] not in SCOPES:
        raise GateError("invalid_profile_scope")
    binding = profile["host_binding"]
    if binding is not None:
        _text(binding, "host_binding", 200)
    if profile["scope"] == "host" and binding is None:
        raise GateError("host_profile_binding_required")
    entries = profile["entries"]
    if not isinstance(entries, list) or len(entries) > ENTRY_LIMIT:
        raise GateError("invalid_profile_entries")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "key",
            "kind",
            "value",
            "source",
            "observed_at",
            "status",
        }:
            raise GateError("invalid_profile_entry_shape")
        key = entry["key"]
        if not isinstance(key, str) or not KEY.fullmatch(key) or key in seen:
            raise GateError("invalid_or_duplicate_profile_key")
        seen.add(key)
        if (
            not isinstance(entry["kind"], str)
            or entry["kind"] not in KINDS
            or not isinstance(entry["status"], str)
            or entry["status"] not in STATUSES
        ):
            raise GateError("invalid_profile_entry_type")
        _text(entry["value"], "value", 2000)
        _text(entry["source"], "source", 300)
        timestamp = _text(entry["observed_at"], "observed_at", 64)
        try:
            parsed = datetime.fromisoformat(timestamp)
            if parsed.tzinfo is None:
                raise ValueError("missing timezone")
        except ValueError as exc:
            raise GateError("invalid_profile_observed_at") from exc
    return profile, sha(raw)


def _available(home: Path) -> list[str]:
    validate_roots(home)
    root = within(home, "profiles")
    if not root.exists():
        return []
    if not root.is_dir():
        raise GateError("profiles_root_not_directory")
    names = sorted(path.name for path in root.iterdir())
    if len(names) > PROFILE_LIMIT:
        raise GateError("profile_count_limit")
    for name in names:
        _profile_id(name)
        if not (root / name).is_dir() or (root / name).is_symlink():
            raise GateError("invalid_profile_directory")
    return names


def inventory(home: Path, ids: list[str] | None = None) -> dict:
    available = _available(home)
    selected = available if ids is None else ids
    if len(selected) != len(set(selected)) or any(i not in available for i in selected):
        raise GateError("profile_selection_unknown_or_duplicate")
    profiles = []
    buckets: dict[str, list[dict]] = {}
    for profile_id in selected:
        value, content_hash = _load(home, profile_id)
        profiles.append(
            {
                "id": profile_id,
                "sha256": content_hash,
                "version": value["version"],
                "scope": value["scope"],
                "host_binding": value["host_binding"],
                "entry_count": len(value["entries"]),
            }
        )
        for entry in value["entries"]:
            buckets.setdefault(entry["key"], []).append(
                {
                    "profile_id": profile_id,
                    "kind": entry["kind"],
                    "value_sha256": sha(entry["value"].encode()),
                }
            )
    conflicts = {
        key: rows
        for key, rows in sorted(buckets.items())
        if len({(r["kind"], r["value_sha256"]) for r in rows}) > 1
    }
    binding_mismatches = [
        p["id"]
        for p in profiles
        if p["host_binding"] is not None and p["host_binding"] != socket.gethostname()
    ]
    subject = {
        "profiles": profiles,
        "conflicts": conflicts,
        "binding_mismatches": binding_mismatches,
    }
    return {
        "schema": "agentos.profile-inventory/v1",
        "status": (
            "BINDING_MISMATCH"
            if binding_mismatches
            else "CONFLICTS"
            if conflicts
            else "PASS"
        ),
        "available_ids": available,
        "selected_ids": selected,
        **subject,
        "inventory_digest": digest(subject),
    }


def activate(
    home: Path,
    mode: str,
    ids: list[str],
    inventory_digest: str | None,
    decisions: dict[str, str] | None = None,
) -> dict:
    validate_roots(home)
    if mode not in {"none", "one", "all"}:
        raise GateError("invalid_profile_mode")
    if mode == "none":
        if ids or decisions:
            raise GateError("none_mode_has_profiles")
        selected = []
    elif mode == "one":
        if len(ids) != 1:
            raise GateError("one_mode_requires_exact_id")
        selected = ids
    else:
        if not ids or set(ids) != set(_available(home)) or len(ids) != len(set(ids)):
            raise GateError("all_mode_requires_ordered_full_inventory")
        selected = ids
    current = (
        inventory(home, selected)
        if mode != "none"
        else {
            "profiles": [],
            "conflicts": {},
            "binding_mismatches": [],
            "inventory_digest": digest(
                {"profiles": [], "conflicts": {}, "binding_mismatches": []}
            ),
        }
    )
    if mode != "none" and current["inventory_digest"] != inventory_digest:
        raise GateError("inventory_digest_mismatch")
    if current["binding_mismatches"]:
        raise GateError("profile_host_binding_mismatch")
    if decisions is None:
        decisions = {}
    if not isinstance(decisions, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in decisions.items()
    ):
        raise GateError("invalid_profile_conflict_decisions")
    if set(decisions) != set(current["conflicts"]):
        raise GateError("profile_conflict_decisions_required")
    for key, choice in decisions.items():
        if choice not in {row["profile_id"] for row in current["conflicts"][key]}:
            raise GateError("invalid_profile_conflict_choice")
    selection = {
        "schema": SELECTION_SCHEMA,
        "mode": mode,
        "ids": selected,
        "profile_hashes": {p["id"]: p["sha256"] for p in current["profiles"]},
        "inventory_digest": current["inventory_digest"],
        "decisions": decisions,
        "selected_at": now(),
    }
    path = within(home, "state/profile-selection.json")
    atomic_json(path, selection)
    return {
        "status": "SELECTED",
        "mode": mode,
        "ids": selected,
        "conflict_count": len(decisions),
        "selection_digest": digest(selection),
    }


def context(home: Path) -> dict:
    validate_roots(home)
    path = within(home, "state/profile-selection.json")
    if not path.exists():
        return {
            "schema": "agentos.profile-context/v1",
            "status": "NONE",
            "selected_ids": [],
            "entries": [],
            "profile_authority": False,
        }
    try:
        selection = read_json(path)
        if (
            not isinstance(selection, dict)
            or selection.get("schema") != SELECTION_SCHEMA
        ):
            raise GateError("invalid_profile_selection")
        if set(selection) != {
            "schema",
            "mode",
            "ids",
            "profile_hashes",
            "inventory_digest",
            "decisions",
            "selected_at",
        }:
            raise GateError("invalid_profile_selection_shape")
        ids = selection["ids"]
        if (
            not isinstance(ids, list)
            or not ids
            and selection["mode"] != "none"
            or any(not isinstance(i, str) for i in ids)
            or selection["mode"] not in {"none", "one", "all"}
            or selection["mode"] == "one"
            and len(ids) != 1
            or not isinstance(selection["decisions"], dict)
            or not isinstance(selection["profile_hashes"], dict)
        ):
            raise GateError("invalid_profile_selection_values")
        if selection["mode"] == "none":
            if ids:
                raise GateError("invalid_none_selection")
            return {
                "schema": "agentos.profile-context/v1",
                "status": "NONE",
                "selected_ids": [],
                "entries": [],
                "profile_authority": False,
            }
        if selection["mode"] == "all" and set(ids) != set(_available(home)):
            raise GateError("all_profile_set_changed")
        current = inventory(home, ids)
        if (
            current["inventory_digest"] != selection["inventory_digest"]
            or {p["id"]: p["sha256"] for p in current["profiles"]}
            != selection["profile_hashes"]
        ):
            raise GateError("profile_changed_since_selection")
        decisions = selection["decisions"]
        if set(decisions) != set(current["conflicts"]):
            raise GateError("profile_conflict_decisions_stale")
        for key, choice in decisions.items():
            if choice not in {row["profile_id"] for row in current["conflicts"][key]}:
                raise GateError("profile_conflict_choice_stale")
        entries = {}
        for profile_id in ids:
            profile, content_hash = _load(home, profile_id)
            if content_hash != selection["profile_hashes"][profile_id]:
                raise GateError("profile_changed_during_context_read")
            binding = profile["host_binding"]
            if binding is not None and binding != socket.gethostname():
                raise GateError("profile_host_binding_mismatch")
            for entry in profile["entries"]:
                key = entry["key"]
                if key not in entries or decisions.get(key) == profile_id:
                    entries[key] = {**entry, "profile_id": profile_id}
        result = {
            "schema": "agentos.profile-context/v1",
            "status": "ACTIVE",
            "selected_ids": ids,
            "entries": list(entries.values()),
            "profile_authority": False,
        }
        if len(str(result).encode()) > CONTEXT_LIMIT:
            raise GateError("profile_context_size_limit")
        return result
    except GateError as exc:
        return {
            "schema": "agentos.profile-context/v1",
            "status": "STALE_SELECTION",
            "reason_code": str(exc).split(":", 1)[0],
            "selected_ids": [],
            "entries": [],
            "profile_authority": False,
        }
    except (KeyError, TypeError, ValueError, OSError):
        return {
            "schema": "agentos.profile-context/v1",
            "status": "STALE_SELECTION",
            "reason_code": "invalid_selection_or_io",
            "selected_ids": [],
            "entries": [],
            "profile_authority": False,
        }


def interview(home: Path) -> dict:
    """Prefill only bounded local facts and verified selected profile context."""
    selected = context(home)
    confirmed = {
        entry["key"]
        for entry in selected["entries"]
        if entry["status"] == "OWNER_CONFIRMED"
    }
    questions = [
        {"key": key, "question": question}
        for key, question in (
            ("owner.display_name", "How should the owner be addressed?"),
            ("owner.language", "Which language should this profile prefer?"),
            ("host.role", "What role does this device have for AgentOS?"),
        )
        if key not in confirmed
    ]
    return {
        "schema": "agentos.profile-interview/v1",
        "device_observations": {
            "hostname": platform.node(),
            "os": platform.system(),
            "architecture": platform.machine(),
            "runtime_user": getpass.getuser(),
            "status": "LIVE_OBSERVED",
            "observed_at": now(),
        },
        "selected_profile_context": selected,
        "unanswered_questions": questions,
        "rule": "Show observed facts for correction; do not infer personal identity from a home path.",
    }


def command(argv: list[str], home: Path) -> tuple[dict, int]:
    p = argparse.ArgumentParser(prog="agentos profiles")
    sub = p.add_subparsers(dest="action", required=True)
    inv = sub.add_parser("inventory")
    inv.add_argument("--id", action="append", default=[])
    select = sub.add_parser("select")
    select.add_argument("--mode", choices=("none", "one", "all"), required=True)
    select.add_argument("--id", action="append", default=[])
    select.add_argument("--inventory-digest")
    select.add_argument("--decisions", type=Path)
    sub.add_parser("context")
    sub.add_parser("interview")
    args = p.parse_args(argv)
    if args.action == "inventory":
        return inventory(home, args.id or None), 0
    if args.action == "context":
        return context(home), 0
    if args.action == "interview":
        return interview(home), 0
    choices = read_json(args.decisions) if args.decisions else None
    result = activate(home, args.mode, args.id, args.inventory_digest, choices)
    return result, 0
