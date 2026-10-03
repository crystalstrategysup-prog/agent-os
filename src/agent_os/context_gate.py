"""Explicit bounded context materialization; never a hook or authority grant.

Receipts compare current bytes with caller-supplied event references. They do
not authenticate provider events or prove that an agent followed instructions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import profile_adapter
from .safeio import GateError, _parse_json, digest, identifier, read_json_input, sha, within

PURPOSES = {
    "question", "search", "audit", "discovery", "project-change",
    "project-report", "project-snapshot", "continuation",
}
READS = {"question", "search", "audit", "discovery"}
LIMIT = 64 * 1024


def _text(value, name, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise GateError("context_invalid_" + name)
    if profile_adapter.SECRET.search(value):
        raise GateError("context_secret_like_value_refused")
    return value


def _keys(values):
    if (not isinstance(values, list) or len(values) > 32
            or any(not isinstance(k, str) or not profile_adapter.KEY.fullmatch(k) for k in values)
            or len(set(values)) != len(values)):
        raise GateError("context_invalid_keys")
    return values


def _goal(value, required):
    if value is None and not required:
        return None
    fields = {"original", "scope", "acceptance", "known_answers", "authority_ref", "source_ref"}
    if not isinstance(value, dict) or set(value) != fields:
        raise GateError("context_goal_contract_required")
    for key in ["original", "scope", "authority_ref", "source_ref"]:
        _text(value[key], key)
    acceptance = value["acceptance"]
    if not isinstance(acceptance, list) or not 1 <= len(acceptance) <= 32:
        raise GateError("context_semantic_acceptance_required")
    for criterion in acceptance:
        _text(criterion, "criterion")
    answers = value["known_answers"]
    if not isinstance(answers, dict) or len(answers) > 64:
        raise GateError("context_invalid_known_answers")
    for key, answer in answers.items():
        _text(key, "answer_key", 200)
        _text(answer, "answer")
    return value


def _bytes(home, relative):
    path = within(home, relative, allow_missing=False)
    if path.stat().st_nlink != 1:
        raise GateError("context_hardlink_refused")
    with path.open("rb") as stream:
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise GateError("context_size_limit")
    text = data.decode("utf-8")
    if profile_adapter.SECRET.search(text):
        raise GateError("context_secret_like_value_refused")
    return data


def build(home: Path, request: dict) -> dict:
    """Return actual relevant text and its source binding, without writing files."""
    fields = {"schema", "session_id", "turn_id", "purpose", "profile_keys", "index_keys", "goal"}
    if (not isinstance(request, dict) or set(request) - fields
            or request.get("schema") != "agentos.context-request/v1"):
        raise GateError("context_invalid_request")
    session = identifier(request.get("session_id"))
    turn = identifier(request.get("turn_id"))
    purpose = request.get("purpose")
    if not isinstance(purpose, str) or purpose not in PURPOSES:
        raise GateError("context_invalid_purpose")
    keys = _keys(request.get("profile_keys", []))
    index_keys = _keys(request.get("index_keys", []))
    if len(index_keys) > 8:
        raise GateError("context_index_limit")
    goal = _goal(request.get("goal"), purpose in {"project-change", "continuation"})
    if purpose in READS and not keys and not index_keys:
        return {"schema": "agentos.context-capsule/v1", "status": "FAST_PATH",
                "purpose": purpose, "home_read": False, "intake_required": False,
                "authority_granted": False, "behavior_compliance": "NOT_PROVEN"}

    depends_on_profiles = bool(keys or index_keys)
    selected = (profile_adapter.context(home) if depends_on_profiles
                else {"status": "NOT_REQUESTED", "entries": []})
    if (keys or index_keys) and selected["status"] != "ACTIVE":
        raise GateError("selected_profile_context_unavailable:" + selected["status"])
    if selected["status"] not in {"ACTIVE", "NONE", "NOT_REQUESTED"}:
        raise GateError("selected_profile_context_unavailable:" + selected["status"])
    entries = {entry["key"]: entry for entry in selected["entries"]}
    needed = set(keys) | set(index_keys) | {key + "_sha256" for key in index_keys}
    if needed - entries.keys():
        raise GateError("context_selected_key_missing")
    documents, sources = [], {}
    budget = 0

    def read(relative, expected):
        nonlocal budget
        if not isinstance(expected, str) or len(expected) != 64:
            raise GateError("context_invalid_expected_hash")
        raw = _bytes(home, relative)
        if sha(raw) != expected:
            raise GateError("context_dependency_hash_mismatch:" + relative)
        if relative not in sources:
            budget += len(raw)
        if budget > LIMIT:
            raise GateError("context_size_limit")
        sources[relative] = expected
        return raw

    for key in index_keys:
        relative = entries[key]["value"]
        raw = read(relative, entries[key + "_sha256"]["value"])
        index = _parse_json(raw)
        if not isinstance(index, dict) or index.get("grants_authority") is not False:
            raise GateError("context_non_authoritative_index_required")
        applicable = index.get("applies_to")
        if applicable is not None:
            if (not isinstance(applicable, list)
                    or any(not isinstance(v, str) for v in applicable)
                    or purpose not in applicable):
                raise GateError("context_rule_not_applicable")
        rows = index.get("documents")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 16:
            raise GateError("context_invalid_index_documents")
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get("path"), str)
                    or type(row.get("required")) is not bool):
                raise GateError("context_invalid_index_document")
            if not row["required"]:
                continue
            # Validate relative member before joining so absolute or traversal
            # paths cannot discard/escape the index directory.
            parent = within(home, relative).parent
            doc = within(parent, row["path"], allow_missing=False)
            doc_relative = doc.relative_to(home.resolve()).as_posix()
            content = read(doc_relative, row.get("sha256"))
            documents.append({"index_key": key, "path": doc_relative,
                              "sha256": sha(content), "content": content.decode("utf-8")})
    # Detect cooperative concurrent updates while collecting several files.
    if depends_on_profiles and profile_adapter.context(home) != selected:
        raise GateError("context_selection_changed_during_read")
    if any(sha(_bytes(home, path)) != expected for path, expected in sources.items()):
        raise GateError("context_dependency_changed_during_read")
    body = {
        "schema": "agentos.context-capsule/v1", "status": "MATERIALIZED",
        "session_id": session, "turn_id": turn, "purpose": purpose,
        "request_sha256": digest(request),
        "profile_selection": {"status": selected["status"],
                              "selection_checked": depends_on_profiles,
                              "selection_digest": selected.get("selection_digest"),
                              "profile_hashes": selected.get("profile_hashes", {})},
        "entries": [entries[key] for key in sorted(needed)],
        "documents": documents, "dependency_hashes": sources, "goal": goal,
        "authority_granted": False, "native_hooks": "DISABLED",
        "behavior_compliance": "NOT_PROVEN",
    }
    if len(json.dumps(body, ensure_ascii=False).encode()) > LIMIT:
        raise GateError("context_size_limit")
    return {**body, "capsule_sha256": digest(body)}


def verify(home: Path, request: dict, receipt: dict) -> dict:
    """Check a byte binding; a supplied reference is not authenticated evidence."""
    current = build(home, request)
    if current["status"] == "FAST_PATH":
        return current
    fields = {"session_id", "turn_id", "capsule_sha256", "event_kind", "event_ref"}
    if (not isinstance(receipt, dict) or set(receipt) != fields
            or receipt.get("event_kind") != "tool_result"):
        raise GateError("context_observed_tool_result_reference_required")
    _text(receipt["event_ref"], "event_ref", 1000)
    for key in ["session_id", "turn_id", "capsule_sha256"]:
        if receipt.get(key) != current[key]:
            raise GateError("context_receipt_binding_mismatch:" + key)
    return {"schema": "agentos.context-binding-check/v1", "status": "CURRENT_BINDING_MATCH",
            "capsule_sha256": current["capsule_sha256"],
            "event_ref": receipt["event_ref"], "event_authenticity": "NOT_VERIFIED",
            "behavior_compliance": "NOT_PROVEN", "authority_granted": False}


def command(argv: list[str], home: Path | None = None) -> tuple[dict, int]:
    parser = argparse.ArgumentParser(prog="agentos context")
    parser.add_argument("action", choices=["build", "verify"])
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    request = read_json_input(args.request)
    if request.get("profile_keys") or request.get("index_keys"):
        from .config import AgentOSPaths

        home = AgentOSPaths.discover(home).home
    else:
        # A goal-only or direct-read request has no home dependency, including
        # optional CLI use with an otherwise unsuitable overlay directory.
        home = home or Path(".")
    if args.action == "verify":
        if args.receipt is None:
            raise GateError("context_receipt_required")
        return verify(home, request, read_json_input(args.receipt)), 0
    if args.receipt is not None:
        raise GateError("context_build_does_not_accept_receipt")
    return build(home, request), 0
