"""Real disposable profile/index/document bytes, not mocked context receipts."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from agent_os import context_gate as gate, integration, profile_adapter
from agent_os.safeio import GateError, atomic_json, sha


def goal():
    return {"original": "Compare offers using the agreed unit", "scope": "local comparison",
            "acceptance": ["All comparable prices use the agreed unit"],
            "known_answers": {"comparison_unit": "kilogram", "package_size": "not required"},
            "authority_ref": "current-owner-task", "source_ref": "accepted-task-answers"}


def request(**updates):
    return {"schema": "agentos.context-request/v1", "session_id": "session-a", "turn_id": "turn-1",
            "purpose": "project-report", "profile_keys": [], "index_keys": ["owner.format_index"],
            "goal": goal(), **updates}


@pytest.fixture
def store(tmp_path):
    home = tmp_path / "user"
    doc = home / "knowledge/presentation/FORMAT.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Selected format\nShow actual results and an owned remainder.\n")
    index = doc.parent / "INDEX.json"
    atomic_json(index, {"grants_authority": False, "applies_to": ["project-report", "project-snapshot"],
                        "documents": [{"path": "FORMAT.md", "required": True, "sha256": sha(doc.read_bytes())}]})
    entries = [{"key": key, "value": value, "kind": "preference", "source": "owner instruction",
                "observed_at": "2026-10-03T00:00:00Z", "status": "OWNER_CONFIRMED"}
               for key, value in [("owner.format_index", "knowledge/presentation/INDEX.json"),
                                  ("owner.format_index_sha256", sha(index.read_bytes()))]]
    profile = home / "profiles/owner/profile.json"
    atomic_json(profile, {"schema": "agentos.profile/v1", "id": "owner", "version": "1",
                          "scope": "owner", "host_binding": None, "entries": entries})
    select(home)
    return home, profile, index, doc


def select(home):
    inv = profile_adapter.inventory(home, ["owner"])
    profile_adapter.activate(home, "one", ["owner"], inv["inventory_digest"])


def repin(home, profile, index):
    value = json.loads(profile.read_text())
    value["entries"][1]["value"] = sha(index.read_bytes())
    atomic_json(profile, value)
    select(home)


def receipt(capsule, **updates):
    return {"session_id": capsule["session_id"], "turn_id": capsule["turn_id"],
            "capsule_sha256": capsule["capsule_sha256"], "event_kind": "tool_result",
            "event_ref": "synthetic-provider-result-1", **updates}


def test_materializes_actual_bytes_and_preserves_semantic_goal(store):
    home, _, _, doc = store
    result = gate.build(home, request())
    assert result["status"] == "MATERIALIZED"
    assert result["documents"][0]["content"] == doc.read_text()
    assert result["documents"][0]["sha256"] == sha(doc.read_bytes())
    assert result["goal"] == goal()
    assert result["profile_selection"]["profile_hashes"]["owner"]
    assert result["profile_selection"]["selection_digest"]
    assert result["authority_granted"] is False
    assert result["behavior_compliance"] == "NOT_PROVEN"


@pytest.mark.parametrize("purpose", sorted(gate.READS))
def test_ordinary_reads_do_not_inspect_home_or_enter_intake(tmp_path, monkeypatch, purpose):
    def fail(_):
        raise AssertionError("read-only request touched profiles")
    monkeypatch.setattr(profile_adapter, "context", fail)
    result = gate.build(tmp_path / "nonexistent", request(purpose=purpose, index_keys=[], goal=None))
    assert result["status"] == "FAST_PATH"
    assert result["home_read"] is result["intake_required"] is False


def test_inapplicable_rule_is_not_silently_loaded(store):
    with pytest.raises(GateError, match="not_applicable"):
        gate.build(store[0], request(purpose="question"))


@pytest.mark.parametrize("purpose", ["project-change", "continuation", "project-report"])
def test_goal_only_capsule_does_not_depend_on_unrelated_profiles(tmp_path, monkeypatch, purpose):
    def fail(_):
        raise AssertionError("unrelated profiles must not gate this capsule")
    monkeypatch.setattr(profile_adapter, "context", fail)
    result = gate.build(tmp_path, request(purpose=purpose, index_keys=[]))
    assert result["status"] == "MATERIALIZED"
    assert result["profile_selection"]["status"] == "NOT_REQUESTED"
    assert result["profile_selection"]["selection_checked"] is False
    assert result["goal"] == goal()


def test_optional_direct_read_cli_does_not_discover_overlay(tmp_path, monkeypatch):
    from agent_os.config import AgentOSPaths

    def fail(*args, **kwargs):
        raise AssertionError("unrelated home discovery")
    monkeypatch.setattr(AgentOSPaths, "discover", fail)
    path = tmp_path / "request.json"
    atomic_json(path, request(purpose="audit", index_keys=[], goal=None))
    result, code = gate.command(["build", "--request", str(path)])
    assert code == 0 and result["status"] == "FAST_PATH"


@pytest.mark.parametrize("member", [1, 2, 3])
def test_stale_profile_index_or_document_is_not_accepted(store, member):
    home = store[0]
    store[member].write_text(store[member].read_text() + "\n")
    with pytest.raises(GateError, match="unavailable|hash_mismatch"):
        gate.build(home, request())


@pytest.mark.parametrize("member", ["../outside.md", "/outside.md"])
def test_index_path_escape_is_refused_even_when_reselected(store, member):
    home, profile, index, _ = store
    value = json.loads(index.read_text())
    value["documents"][0]["path"] = member
    atomic_json(index, value)
    repin(home, profile, index)
    with pytest.raises(GateError, match="unsafe_relative_path"):
        gate.build(home, request())


def test_symlink_document_is_refused(store, tmp_path):
    home, _, _, doc = store
    other = tmp_path / "external.md"
    other.write_bytes(doc.read_bytes())
    doc.unlink()
    doc.symlink_to(other)
    with pytest.raises(GateError, match="symlink"):
        gate.build(home, request())


def test_oversize_bound_is_on_bytes_read_not_only_index(store):
    home, _, _, doc = store
    doc.write_bytes(b"x" * (gate.LIMIT + 1))
    with pytest.raises(GateError, match="size_limit"):
        gate.build(home, request())


def test_receipt_matches_binding_without_claiming_behavior(store):
    home = store[0]
    capsule = gate.build(home, request())
    result = gate.verify(home, request(), receipt(capsule))
    assert result["status"] == "CURRENT_BINDING_MATCH"
    assert result["event_authenticity"] == "NOT_VERIFIED"
    assert result["behavior_compliance"] == "NOT_PROVEN"


@pytest.mark.parametrize("change", [{"event_kind": "ACK"}, {"session_id": "other"},
                                     {"turn_id": "other"}, {"capsule_sha256": "0" * 64}])
def test_ack_or_cross_turn_receipt_cannot_pass(store, change):
    home = store[0]
    with pytest.raises(GateError, match="reference_required|binding_mismatch"):
        gate.verify(home, request(), receipt(gate.build(home, request()), **change))


def test_fresh_valid_reselection_does_not_accept_old_capsule_receipt(store):
    home, profile, index, doc = store
    old = receipt(gate.build(home, request()))
    doc.write_text("# Revised selected format\nDo not reuse obsolete text.\n")
    value = json.loads(index.read_text())
    value["documents"][0]["sha256"] = sha(doc.read_bytes())
    atomic_json(index, value)
    repin(home, profile, index)
    with pytest.raises(GateError, match="binding_mismatch"):
        gate.verify(home, request(), old)


def test_continuation_requires_original_goal_and_acceptance(store):
    home = store[0]
    with pytest.raises(GateError, match="goal_contract"):
        gate.build(home, request(purpose="continuation", index_keys=[], goal=None))
    result = gate.build(home, request(purpose="continuation", index_keys=[]))
    assert result["goal"]["known_answers"]["comparison_unit"] == "kilogram"
    assert result["authority_granted"] is False


def test_actual_cli_outputs_capsule_and_bootstrap_routes_to_it(store, tmp_path):
    home = store[0]
    args = tmp_path / "request.json"
    atomic_json(args, request())
    proc = subprocess.run([sys.executable, "-m", "agent_os", "--home", str(home),
                           "context", "build", "--request", str(args)],
                          capture_output=True, text=True, timeout=10, env=os.environ.copy())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["documents"][0]["content"] == store[3].read_text()
    codex = tmp_path / "codex"
    integration.install(codex, tmp_path / "skills", home, apply=True)
    installed = (codex / "AGENTS.md").read_text()
    assert "context build --request" in installed
    assert "SESSION_LAUNCH.md" in installed
    assert "A path/hash alone is not loaded context" in installed


def test_context_cli_is_discoverable_and_contract_has_no_write_authority():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = json.loads((root / "schemas/cli-contract-v1.json").read_text())
    packaged = json.loads((root / "src/agent_os/resources/contracts/cli-contract-v1.json").read_text())
    assert source == packaged
    for name in ["context build", "context verify"]:
        row = next(row for row in source["commands"] if row["name"] == name)
        assert row["effect"] == "read_only" and row["write_surfaces"] == []
    proc = subprocess.run([sys.executable, "-m", "agent_os", "--help"], capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0 and "context" in proc.stdout
