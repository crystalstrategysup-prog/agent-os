"""Draft integration probes existing primitives; no new coordinator is adopted."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_continuation_dispatch import accepted, closed, move
from test_foundation import documents, start
from test_foundation import setup as foundation_setup
from test_indexed_handoff import P, accept, make

from agent_os import continuation as c
from agent_os import profile_adapter as profiles
from agent_os import project as p
from agent_os.handoff import Library, local_principal
from agent_os.handoff_lifecycle import TOPICS
from agent_os.handoff_store import HandoffError
from agent_os.safeio import GateError, atomic_json, filemap
from agent_os.work_coordination import Coordinator

setup = foundation_setup


def verified_result(setup, task):
    root, home, _ = setup
    assert p.verify_closeout(root, task)["status"] == "PASS"
    lib = Library(home / "results-library")
    binding = p.load_task(root, task)["closeout"]["handoff"]
    resolved = lib.resolve(binding["handoff_id"], local_principal())
    assert resolved["row"]["manifest_ref"] == binding["manifest_ref"]
    evidence = lib.read_evidence(
        binding["handoff_id"], "evidence:review", local_principal()
    )
    assert evidence["captured_bytes_verified"]
    payload = json.loads(evidence["bytes"])
    assert payload["task_id"] == task and payload["assessment"]["status"] == "PASS"
    return resolved


def test_completion_verified_acceptance_then_exact_next_action(setup):
    task = closed(setup)
    resolved = verified_result(setup, task)
    assert resolved["manifest"]["entity"]["state"] == "completed"
    item = c.reconcile(setup[1], setup[0], task)
    assert item["continuation"]["next_action"]["kind"] == "review"
    assert item["continuation"]["next_owner"] == "independent-reviewer"
    assert item["continuation"]["parent_owner"] == "parent"
    assert item["identity"]["source_sha256"] == p.source_snapshot(setup[0])["sha256"]
    assert c.read(setup[1], item["id"]) == item
    item = move(setup[1], item, "claim")
    item = move(setup[1], item, "begin-delivery")
    assert item["state"] == "DELIVERY_UNKNOWN" and not item["worker_started"]
    final = move(setup[1], item, "acknowledge", accepted(item))
    assert final["state"] == "ACKNOWLEDGED"
    assert not final["worker_started"]
    assert not c.status(setup[1])["project_completion_proven"]


def test_missed_final_notification_reconciles_selected_result_once(setup):
    task = closed(setup)  # No notification emitter runs in this fixture.
    verified_result(setup, task)
    item = c.reconcile(setup[1], setup[0], task)
    before = filemap(setup[1])
    assert c.reconcile(setup[1], setup[0], task) == item
    assert filemap(setup[1]) == before
    assert len(c.status(setup[1])["items"]) == 1


def test_partial_checkpoint_is_indexed_but_not_final_continuation(setup):
    task = start(setup)
    documents(setup, task)
    p.checkpoint(setup[0], task, "Partial synthetic result", "Continue scoped work")
    lib = Library(setup[1] / "results-library")
    manifest = lib.resolve("handoff:" + task, local_principal())["manifest"]
    assert manifest["entity"]["state"] == "active"
    assert manifest["facets"]["result_type"] == "checkpoint"
    with pytest.raises(GateError, match="registered_closeout_required"):
        c.reconcile(setup[1], setup[0], task)


def test_checkpoint_preserves_other_independent_project(setup, tmp_path):
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other = foundation_setup.__wrapped__(other_dir)
    first = start(setup)
    second = start(other)
    documents(setup, first)
    documents(other, second)
    before = filemap(other[0])
    before_home = filemap(other[1])
    p.checkpoint(
        setup[0], first, "Collect local checkpoint", "Architecture review pending"
    )
    assert filemap(other[0]) == before and filemap(other[1]) == before_home
    assert p.load_task(other[0], second)["status"] == "READY"


def test_generic_index_pins_contract_and_inherited_documents():
    root = Path(__file__).resolve().parents[1]
    src = root / "docs/COORDINATOR_KNOWLEDGE_INDEX.json"
    packaged = root / "src/agent_os/resources/docs/COORDINATOR_KNOWLEDGE_INDEX.json"
    assert src.read_bytes() == packaged.read_bytes()
    index = json.loads(src.read_text())
    assert index["status"] == "PUBLIC_RELEASE_CANDIDATE_NOT_ADOPTED"
    assert index["core_version"] == "0.7.1"
    assert index["knowledge_version"] == "1.2.0"
    assert index["role_id"] == "main-coordinator"
    for item in index["documents"]:
        assert Path(item["path"]).name == item["path"]
        for folder in [src.parent, packaged.parent]:
            data = (folder / item["path"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == item["sha256"]
    assert not index["live_adoption_proven"]


def test_private_profile_transports_index_pointer_without_loading_or_authority(setup):
    root, home, _ = setup
    private_index = {
        "status": "DRAFT_NOT_APPROVED",
        "foundation_index": "COORDINATOR_KNOWLEDGE_INDEX.json",
    }
    index = home / "knowledge/coordinator/INDEX.json"
    atomic_json(index, private_index)
    raw_hash = hashlib.sha256(index.read_bytes()).hexdigest()
    entries = []
    for key, value in [
        ("coordinator.role", "main-coordinator"),
        ("coordinator.knowledge_index", "knowledge/coordinator/INDEX.json"),
        ("coordinator.index_sha256", raw_hash),
    ]:
        entries.append(
            {
                "key": key,
                "kind": "fact",
                "value": value,
                "source": "synthetic draft fixture",
                "observed_at": "2026-10-02T00:00:00+00:00",
                "status": "DOCUMENTED",
            }
        )
    atomic_json(
        home / "profiles/main-coordinator/profile.json",
        {
            "schema": profiles.PROFILE_SCHEMA,
            "id": "main-coordinator",
            "version": "0.1.0-draft",
            "scope": "custom",
            "host_binding": None,
            "entries": entries,
        },
    )
    inventory = profiles.inventory(home)
    profiles.activate(home, "one", ["main-coordinator"], inventory["inventory_digest"])
    context = p.questionnaire(root, user_home=home)["selected_profile_context"]
    assert context["status"] == "ACTIVE" and not context["profile_authority"]
    values = {entry["key"]: entry["value"] for entry in context["entries"]}
    assert values["coordinator.knowledge_index"] == "knowledge/coordinator/INDEX.json"
    assert "foundation_index" not in values  # Adapter did not dereference the index.
    assert (
        hashlib.sha256(
            (home / values["coordinator.knowledge_index"]).read_bytes()
        ).hexdigest()
        == values["coordinator.index_sha256"]
    )
    profile = home / "profiles/main-coordinator/profile.json"
    profile.write_bytes(profile.read_bytes() + b"\n")
    assert profiles.context(home)["status"] == "STALE_SELECTION"


GOAL = "Deliver the original synthetic user result"


def actor_session(name, *, kind="session", parent=None):
    return {"session_id": name, "kind": kind, "parent_session_id": parent}


def work_item(name, n, *, depends=(), state="pending", paths=None):
    return {
        "work_id": name,
        "entity_id": f"work:{n}",
        "handoff_id": f"handoff:{n}",
        "role": "worker",
        "session": actor_session("session:" + name),
        "depends_on": list(depends),
        "write_set": [{"resource": "fixture-repository", "paths": paths or [name]}],
        "state": state,
        "required": True,
    }


@pytest.fixture
def registry(tmp_path):
    lib = Library.create(tmp_path / "results", P, topics=TOPICS)
    work = [
        work_item("first", 1, state="running"),
        work_item("second", 2, depends=["first"]),
    ]
    co = Coordinator.create(
        tmp_path / "owner",
        "fixture",
        P,
        GOAL,
        ["criterion:user-result"],
        work,
        coordinator_session=actor_session("session:coordinator"),
    )
    return co, lib


def receive_first(co, lib):
    ref, _ = accept(lib, 1)
    return co.receive(
        P, "notification:first", "first", lib, P, ref, co.read()["revision"]
    )


def checked_review(*, target="second", verdict="accepted"):
    return {
        "verdict": verdict,
        "original_goal": GOAL,
        "summary": "Checked captured result against original goal and remaining integration.",
        "reasons": "First child result does not itself establish the original user outcome.",
        "remaining": ["Integration and checked original user result remain."],
        "evidence_ids": ["evidence:review"],
        "next_actions": [
            {
                "target": target,
                "kind": "verify-goal" if target == "parent" else "next-stage",
                "summary": "Verify original user result"
                if target == "parent"
                else "Implement dependent next stage",
            }
        ],
        "waiting": None,
    }


def proof(lib, action, status, event="event:actual-fixture"):
    return lib.store.put_json(
        {
            "schema": "agentos.coordinator-action-receipt/v1",
            **{
                key: action[key]
                for key in ["action_id", "operation_id", "generation", "nonce"]
            },
            "provider": "synthetic-executor",
            "event_id": event,
            "observed_at": datetime.now(UTC).isoformat(),
            "status": status,
        }
    )


def test_report_review_remaining_next_assignment_and_parent_open(registry):
    co, lib = registry
    notice = receive_first(co, lib)
    assert co.status()["unreviewed_notices"] == [notice["notification_id"]]
    assert co.read()["work"]["first"]["state"] == "running"
    s = co.review(
        P, notice["notification_id"], checked_review(), lib, P, co.read()["revision"]
    )
    assert s["parent_state"] == "open" and s["work"]["first"]["state"] == "completed"
    assert s["work"]["second"]["state"] == "planned"
    assert s["actions"][0]["session"]["session_id"] == "session:second"
    assert s["decisions"][0]["review"]["remaining"]
    assert s["decisions"][0]["review"]["original_goal"] == GOAL
    assert co.status()["commands_executed"] == []


@pytest.mark.parametrize("damage", ["no_next", "no_remaining", "wrong_goal"])
def test_completed_child_cannot_orphan_unfinished_goal(registry, damage):
    co, lib = registry
    notice = receive_first(co, lib)
    r = checked_review()
    if damage == "no_next":
        r["next_actions"] = []
    elif damage == "no_remaining":
        r["remaining"] = []
    else:
        r["original_goal"] = "An easier replacement goal"
    before = filemap(co.root)
    with pytest.raises(
        HandoffError, match="ORPHANED_PARENT_WORK|ORIGINAL_GOAL_MISMATCH"
    ):
        co.review(P, notice["notification_id"], r, lib, P, co.read()["revision"])
    assert filemap(co.root) == before and co.read()["parent_state"] == "open"


def test_explicit_user_pause_is_recorded_but_not_completion(registry):
    co, lib = registry
    n = receive_first(co, lib)
    r = checked_review()
    r["next_actions"] = []
    r["waiting"] = {
        "kind": "user-pause",
        "reason": "Explicit current user pause recorded in reviewed fixture evidence.",
        "evidence_ids": ["evidence:review"],
    }
    s = co.review(P, n["notification_id"], r, lib, P, co.read()["revision"])
    assert (
        s["parent_state"] == "open"
        and s["decisions"][0]["review"]["waiting"]["kind"] == "user-pause"
    )


def test_blocker_cannot_suspend_ready_independent_work(registry):
    co, lib = registry
    n = receive_first(co, lib)
    r = checked_review()
    r["next_actions"] = []
    r["waiting"] = {
        "kind": "unavoidable-blocker",
        "reason": "Fixture blocks this slice only.",
        "evidence_ids": ["evidence:review"],
    }
    with pytest.raises(HandoffError, match="INDEPENDENT_WORK_MUST_CONTINUE"):
        co.review(P, n["notification_id"], r, lib, P, co.read()["revision"])
    assert co.read()["work"]["second"]["state"] == "pending"


def test_receive_review_and_assignment_recover_after_lost_responses(
    registry, monkeypatch
):
    co, lib = registry
    ref, _ = accept(lib, 1)

    def fault(point):
        raise ConnectionError("synthetic lost response " + point)

    monkeypatch.setattr(co, "_fault", fault)
    with pytest.raises(ConnectionError):
        co.receive(P, "notification:first", "first", lib, P, ref, 1)
    assert co.status()["unreviewed_notices"] == ["notification:first"]
    before = filemap(co.root)
    n = co.recover_notice(
        P, "first", lib, P, 1
    )  # Old expected revision is safe only for identical accepted receipt.
    assert filemap(co.root) == before and n["notification_id"] == "notification:first"
    with pytest.raises(ConnectionError):
        co.review(P, n["notification_id"], checked_review(), lib, P, 2)
    assert len(co.read()["decisions"]) == len(co.read()["actions"]) == 1
    before = filemap(co.root)
    co.review(P, n["notification_id"], checked_review(), lib, P, 2)
    assert filemap(co.root) == before and len(co.read()["actions"]) == 1


def test_partial_notice_recovery_keeps_owner_and_next_step(registry):
    co, lib = registry
    accept(lib, 1, state="active")
    n = co.recover_notice(P, "first", lib, P, 1)
    r = checked_review(target="first", verdict="partial")
    r["next_actions"][0]["kind"] = "continue"
    s = co.review(P, n["notification_id"], r, lib, P, 2)
    assert s["parent_state"] == "open" and s["work"]["first"]["state"] == "running"
    assert s["actions"][0]["target"] == "first"
    assert s["actions"][0]["session"] == s["work"]["first"]["session"]


def test_disconnect_before_action_requires_observation_before_retry(
    registry, monkeypatch, tmp_path
):
    co, lib = registry
    n = receive_first(co, lib)
    s = co.review(P, n["notification_id"], checked_review(), lib, P, 2)
    aid = s["actions"][0]["action_id"]

    def fault(point):
        raise ConnectionError("synthetic pre-command disconnect")

    monkeypatch.setattr(co, "_fault", fault)
    with pytest.raises(ConnectionError):
        co.begin_action(P, aid, s["revision"])
    a = co.read()["actions"][0]
    assert a["state"] == "unknown"
    effect = tmp_path / "synthetic-effect"
    assert not effect.exists()
    with pytest.raises(HandoffError, match="UNKNOWN_EFFECT_NO_RETRY"):
        co.begin_action(P, aid, co.read()["revision"])
    monkeypatch.setattr(co, "_fault", lambda _: None)
    co.record_outcome(
        P, aid, lib, P, proof(lib, a, "not-executed"), co.read()["revision"]
    )
    next_attempt = co.begin_action(P, aid, co.read()["revision"])
    assert (
        next_attempt["operation_id"] == a["operation_id"]
        and next_attempt["generation"] == a["generation"] + 1
    )
    assert next_attempt["nonce"] != a["nonce"]


def test_disconnect_after_effect_before_receipt_never_repeats_effect(
    registry, tmp_path
):
    co, lib = registry
    n = receive_first(co, lib)
    s = co.review(P, n["notification_id"], checked_review(), lib, P, 2)
    aid = s["actions"][0]["action_id"]
    a = co.begin_action(P, aid, s["revision"])
    effect = tmp_path / "synthetic-effect"
    effect.write_text("exactly one synthetic mutation")
    fresh = Coordinator(co.root.parents[2], "fixture")
    assert fresh.status()["unknown_effects"] == [aid]
    with pytest.raises(HandoffError, match="UNKNOWN_EFFECT_NO_RETRY"):
        fresh.begin_action(P, aid, fresh.read()["revision"])
    assert effect.read_text() == "exactly one synthetic mutation"
    receipt = proof(lib, a, "completed")
    fresh.record_outcome(P, aid, lib, P, receipt, fresh.read()["revision"])
    before = filemap(fresh.root)
    fresh.record_outcome(P, aid, lib, P, receipt, 1)
    assert (
        filemap(fresh.root) == before
        and fresh.read()["actions"][0]["state"] == "completed"
    )
    with pytest.raises(HandoffError):
        fresh.begin_action(P, aid, fresh.read()["revision"])


@pytest.mark.parametrize("status", ["running", "stopped", "unknown"])
def test_observed_session_status_does_not_prove_non_execution_or_success(
    registry, status
):
    co, lib = registry
    n = receive_first(co, lib)
    s = co.review(P, n["notification_id"], checked_review(), lib, P, 2)
    aid = s["actions"][0]["action_id"]
    a = co.begin_action(P, aid, s["revision"])
    co.record_outcome(P, aid, lib, P, proof(lib, a, status), co.read()["revision"])
    assert co.read()["actions"][0]["state"] == "unknown"
    with pytest.raises(HandoffError, match="UNKNOWN_EFFECT_NO_RETRY"):
        co.begin_action(P, aid, co.read()["revision"])


def test_checkpoint_keeps_independent_ownership_and_unknown_effects(registry):
    co, lib = registry
    n = receive_first(co, lib)
    s = co.review(P, n["notification_id"], checked_review(), lib, P, 2)
    a = co.begin_action(P, s["actions"][0]["action_id"], s["revision"])
    before = co.read()
    after = co.checkpoint(P, "Material plan review", before["revision"])
    assert after["work"] == before["work"] and after["actions"] == before["actions"]
    assert after["parent_state"] == "open" and co.status()["unknown_effects"] == [
        a["action_id"]
    ]


def test_registry_survives_fresh_process_and_hash_damage_refuses(registry):
    co, lib = registry
    n = receive_first(co, lib)
    co.review(P, n["notification_id"], checked_review(), lib, P, 2)
    script = "from pathlib import Path;import json,sys;from agent_os.work_coordination import Coordinator;print(json.dumps(Coordinator(Path(sys.argv[1]),'fixture').status()))"
    ran = subprocess.run(
        [sys.executable, "-B", "-c", script, str(co.root.parents[2])],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(ran.stdout) == co.status()
    head = json.loads((co.root / "HEAD.json").read_text())
    snapshot = co.root / "snapshots" / (head["snapshot_sha256"] + ".json")
    original = snapshot.read_bytes()
    snapshot.write_bytes(original + b"damaged")
    with pytest.raises(HandoffError, match="INTEGRITY_FAILED"):
        co.read()
    snapshot.write_bytes(original)
    assert co.status()["planned_actions"]


@pytest.mark.parametrize("damage", ["paths", "dependency", "capacity"])
def test_invalid_parallel_assignment_is_not_committed(registry, damage):
    co, lib = registry
    n = receive_first(co, lib)
    r = checked_review()
    # Independent fixture state is created through a separate explicit registry.
    work = [
        work_item("first", 1, state="running"),
        work_item("second", 2, depends=["first"]),
        work_item("other", 3, state="pending"),
    ]
    if damage == "paths":
        work[2]["state"] = "running"
        work[1]["write_set"] = copy.deepcopy(work[2]["write_set"])
    if damage == "dependency":
        work[1]["depends_on"] = ["other"]
    if damage == "capacity":
        r["next_actions"].append(
            {
                "target": "other",
                "kind": "next-stage",
                "summary": "Independent fixture assignment",
            }
        )
    other = Coordinator.create(
        co.root.parents[2],
        "conflicts",
        P,
        GOAL,
        ["criterion:user-result"],
        work,
        coordinator_session=actor_session("session:parent"),
        max_parallel=1 if damage == "capacity" else 4,
    )
    ref = lib.resolve("handoff:1", P)["row"]["manifest_ref"]
    other.receive(P, n["notification_id"], "first", lib, P, ref, 1)
    before = filemap(other.root)
    with pytest.raises(
        HandoffError, match="WRITE_SET_CONFLICT|DEPENDENCY_INCOMPLETE|CAPACITY_EXCEEDED"
    ):
        other.review(P, n["notification_id"], r, lib, P, 2)
    assert filemap(other.root) == before


def test_parent_requires_original_user_result_not_all_completed_children(registry):
    co, lib = registry
    n = receive_first(co, lib)
    co.review(P, n["notification_id"], checked_review(), lib, P, 2)
    ref, _ = accept(lib, 2)
    n = co.receive(P, "notification:second", "second", lib, P, ref, 3)
    s = co.review(P, n["notification_id"], checked_review(target="parent"), lib, P, 4)
    assert (
        all(w["state"] == "completed" for w in s["work"].values())
        and s["parent_state"] == "open"
    )
    with pytest.raises(HandoffError, match="ORIGINAL_GOAL_MISMATCH"):
        co.verify_goal(
            P, lib, P, "handoff:2", ref, "Child completion only", s["revision"]
        )
    m, assets = make(lib, 501)
    m["scope"]["objective"] = GOAL
    m["scope"]["criteria"] = [
        {
            "criterion_id": "criterion:user-result",
            "description": "Exact synthetic user-facing bytes verified.",
        }
    ]
    m["results"][0]["criterion_id"] = "criterion:user-result"
    final = lib.build_handoff(m, None, P, assets=assets)
    lib.publish_handoff(final, lib._authorize(P)["generation"], "goal:fixture", P)
    assert (
        lib.store.get(
            lib.resolve("handoff:501", P)["manifest"]["deliverables"][0]["ref"]
        )
        == assets["result:file"]
    )
    done = co.verify_goal(
        P,
        lib,
        P,
        "handoff:501",
        final,
        "Actual synthetic expected user-result bytes checked.",
        s["revision"],
    )
    assert (
        done["parent_state"] == "completed"
        and done["goal_acceptance"]["manifest_ref"] == final
    )


def test_actor_types_owner_cas_and_acl_are_explicit(registry):
    co, lib = registry
    n = receive_first(co, lib)
    with pytest.raises(HandoffError, match="OWNER_MISMATCH"):
        co.checkpoint("replacement-coordinator", "Do not take over", 2)
    with pytest.raises(HandoffError, match="REVISION_CONFLICT"):
        co.checkpoint(P, "Stale caller", 1)
    with pytest.raises(HandoffError):
        co.review(P, n["notification_id"], checked_review(), lib, "untrusted:reader", 2)
    assert (
        co.status()["declared_sessions"] == 2 and co.status()["declared_subagents"] == 0
    )
    assert co.status()["verified_live_sessions"] is None
    bad = [work_item("bad", 1)]
    bad[0]["session"] = actor_session("child", kind="subagent", parent="missing-parent")
    with pytest.raises(HandoffError, match="INVALID_SESSION"):
        Coordinator.create(
            co.root.parents[2],
            "bad-session",
            P,
            GOAL,
            ["criterion:user-result"],
            bad,
            coordinator_session=actor_session("session:parent"),
        )


def test_new_assignment_cannot_bypass_previous_unknown_effect(registry):
    co, lib = registry
    n = receive_first(co, lib)
    s = co.review(P, n["notification_id"], checked_review(), lib, P, 2)
    old = co.begin_action(P, s["actions"][0]["action_id"], s["revision"])
    ref, _ = accept(lib, 2, state="active")
    n = co.receive(
        P, "notification:partial-second", "second", lib, P, ref, co.read()["revision"]
    )
    r = checked_review(target="second", verdict="partial")
    r["next_actions"][0]["kind"] = "continue"
    s = co.review(P, n["notification_id"], r, lib, P, co.read()["revision"])
    new = s["actions"][-1]
    assert new["action_id"] != old["action_id"]
    with pytest.raises(HandoffError, match="UNKNOWN_EFFECT_NO_RETRY"):
        co.begin_action(P, new["action_id"], s["revision"])


def test_saved_receipt_wrong_generation_cannot_clear_unknown(registry):
    co, lib = registry
    n = receive_first(co, lib)
    s = co.review(P, n["notification_id"], checked_review(), lib, P, 2)
    a = co.begin_action(P, s["actions"][0]["action_id"], s["revision"])
    wrong = copy.deepcopy(a)
    wrong["generation"] += 1
    with pytest.raises(HandoffError, match="OUTCOME_BINDING_MISMATCH"):
        co.record_outcome(
            P,
            a["action_id"],
            lib,
            P,
            proof(lib, wrong, "completed"),
            co.read()["revision"],
        )
    assert co.status()["unknown_effects"] == [a["action_id"]]


def test_stale_assignment_after_child_acceptance_cannot_execute(registry):
    co, lib = registry
    n = receive_first(co, lib)
    s = co.review(P, n["notification_id"], checked_review(), lib, P, 2)
    obsolete = s["actions"][0]["action_id"]
    ref, _ = accept(lib, 2)
    n = co.receive(P, "notification:second", "second", lib, P, ref, s["revision"])
    s = co.review(
        P,
        n["notification_id"],
        checked_review(target="parent"),
        lib,
        P,
        co.read()["revision"],
    )
    with pytest.raises(HandoffError, match="WORK_ALREADY_COMPLETED"):
        co.begin_action(P, obsolete, s["revision"])


def finish_children(co, lib):
    n = receive_first(co, lib)
    co.review(P, n["notification_id"], checked_review(), lib, P, co.read()["revision"])
    ref, _ = accept(lib, 2)
    n = co.receive(
        P, "notification:second", "second", lib, P, ref, co.read()["revision"]
    )
    co.review(
        P,
        n["notification_id"],
        checked_review(target="parent"),
        lib,
        P,
        co.read()["revision"],
    )
    return ref


def revised_result(lib, previous, revision, *, state="active"):
    m, assets = make(lib, 2, state=state)
    m["entity"]["scope_revision"] = revision
    profile = "completion" if state == "completed" else "checkpoint"
    ref = lib.build_handoff(
        m, previous["object_id"], P, assets=assets, acceptance_profile=profile
    )
    lib.publish_handoff(
        ref,
        lib._authorize(P)["generation"],
        f"report:second:{revision}",
        P,
        acceptance_profile=profile,
    )
    return ref


def goal_result(lib):
    m, assets = make(lib, 501)
    m["scope"]["objective"] = GOAL
    m["scope"]["criteria"] = [
        {
            "criterion_id": "criterion:user-result",
            "description": "Synthetic exact user result",
        }
    ]
    m["results"][0]["criterion_id"] = "criterion:user-result"
    ref = lib.build_handoff(m, None, P, assets=assets)
    lib.publish_handoff(ref, lib._authorize(P)["generation"], "goal:latest-reports", P)
    return ref


@pytest.mark.parametrize("state", ["active", "completed"])
def test_superseding_unreviewed_report_cannot_close_parent(registry, state):
    co, lib = registry
    old = finish_children(co, lib)
    ref = revised_result(lib, old, 2, state=state)
    n = co.receive(
        P, "notification:second:new", "second", lib, P, ref, co.read()["revision"]
    )
    assert co.read()["work"]["second"]["state"] == "held"
    assert co.read()["work"]["second"]["accepted_notice_id"] is None
    final = goal_result(lib)
    before = filemap(co.root)
    with pytest.raises(
        HandoffError, match="PARENT_SCOPE_INCOMPLETE|PENDING_RESULT_REVIEW"
    ):
        co.verify_goal(
            P,
            lib,
            P,
            "handoff:501",
            final,
            "Verify current original goal",
            co.read()["revision"],
        )
    assert filemap(co.root) == before and co.status()["parent_state"] == "open"
    assert co.status()["unreviewed_notices"] == [n["notification_id"]]
    co.review(
        P,
        n["notification_id"],
        checked_review(
            target="parent", verdict="partial" if state == "active" else "accepted"
        ),
        lib,
        P,
        co.read()["revision"],
    )
    if state == "active":
        with pytest.raises(HandoffError, match="PARENT_SCOPE_INCOMPLETE"):
            co.verify_goal(
                P,
                lib,
                P,
                "handoff:501",
                final,
                "Verify current original goal",
                co.read()["revision"],
            )
    else:
        assert (
            co.verify_goal(
                P,
                lib,
                P,
                "handoff:501",
                final,
                "Verify current original goal",
                co.read()["revision"],
            )["parent_state"]
            == "completed"
        )


@pytest.mark.parametrize("boundary", ["review", "goal"])
@pytest.mark.parametrize("change", ["supersede", "retract"])
def test_library_change_without_notification_refuses_stale_acceptance(
    registry, boundary, change
):
    co, lib = registry
    if boundary == "goal":
        ref = finish_children(co, lib)
        final = goal_result(lib)
        hid = "handoff:2"
    else:
        n = receive_first(co, lib)
        ref = n["manifest_ref"]
        hid = "handoff:1"
    if change == "retract":
        lib.retract(hid, "Synthetic revoked result before semantic acceptance", P)
    elif boundary == "goal":
        revised_result(lib, ref, 2)
    else:
        m, assets = make(lib, 1, state="active")
        m["entity"]["scope_revision"] = 2
        new = lib.build_handoff(
            m, ref["object_id"], P, assets=assets, acceptance_profile="checkpoint"
        )
        lib.publish_handoff(
            new,
            lib._authorize(P)["generation"],
            "report:first:2",
            P,
            acceptance_profile="checkpoint",
        )
    before = filemap(co.root)
    with pytest.raises(HandoffError, match="STALE_RESULT|NOT_FOUND"):
        if boundary == "review":
            co.review(
                P, n["notification_id"], checked_review(), lib, P, co.read()["revision"]
            )
        else:
            co.verify_goal(
                P,
                lib,
                P,
                "handoff:501",
                final,
                "Reject stale accepted child",
                co.read()["revision"],
            )
    assert filemap(co.root) == before and co.status()["parent_state"] == "open"


def test_superseded_pending_notice_is_history_current_review_controls_closure(registry):
    co, lib = registry
    old = finish_children(co, lib)
    partial = revised_result(lib, old, 2)
    first = co.receive(
        P,
        "notification:second:partial",
        "second",
        lib,
        P,
        partial,
        co.read()["revision"],
    )
    latest = revised_result(lib, partial, 3, state="completed")
    current = co.receive(
        P, "notification:second:latest", "second", lib, P, latest, co.read()["revision"]
    )
    before = filemap(co.root)
    with pytest.raises(HandoffError, match="STALE_RESULT"):
        co.receive(
            P, "notification:late-old", "second", lib, P, partial, co.read()["revision"]
        )
    with pytest.raises(HandoffError, match="STALE_NOTIFICATION"):
        co.review(
            P,
            first["notification_id"],
            checked_review(target="parent", verdict="partial"),
            lib,
            P,
            co.read()["revision"],
        )
    assert filemap(co.root) == before
    r = checked_review(target="parent")
    co.review(P, current["notification_id"], r, lib, P, co.read()["revision"])
    before = filemap(co.root)
    assert co.receive(P, "notification:duplicate", "second", lib, P, latest, 0) == next(
        n
        for n in co.read()["notices"]
        if n["notification_id"] == current["notification_id"]
    )
    co.review(P, current["notification_id"], r, lib, P, 0)
    assert filemap(co.root) == before
    assert (
        co.read()["work"]["second"]["accepted_notice_id"] == current["notification_id"]
    )
    final = goal_result(lib)
    assert (
        co.verify_goal(
            P,
            lib,
            P,
            "handoff:501",
            final,
            "Verify resolved current scope",
            co.read()["revision"],
        )["parent_state"]
        == "completed"
    )
    before = filemap(co.root)
    for operation in [
        lambda: co.receive(
            P, "notification:closed", "second", lib, P, latest, co.read()["revision"]
        ),
        lambda: co.review(
            P, current["notification_id"], r, lib, P, co.read()["revision"]
        ),
        lambda: co.verify_goal(
            P, lib, P, "handoff:501", final, "Closed retry", co.read()["revision"]
        ),
    ]:
        with pytest.raises(HandoffError):
            operation()
    assert filemap(co.root) == before


def test_late_action_receipt_does_not_accept_superseding_report(registry):
    co, lib = registry
    n = receive_first(co, lib)
    s = co.review(
        P, n["notification_id"], checked_review(), lib, P, co.read()["revision"]
    )
    action = co.begin_action(P, s["actions"][0]["action_id"], co.read()["revision"])
    ref, _ = accept(lib, 2)
    co.receive(P, "notification:second", "second", lib, P, ref, co.read()["revision"])
    current = revised_result(lib, ref, 2)
    co.receive(
        P,
        "notification:second:partial",
        "second",
        lib,
        P,
        current,
        co.read()["revision"],
    )
    saved = proof(lib, action, "completed", event="event:old-completion")
    co.record_outcome(P, action["action_id"], lib, P, saved, co.read()["revision"])
    before = filemap(co.root)
    co.record_outcome(P, action["action_id"], lib, P, saved, 0)
    assert filemap(co.root) == before
    assert co.read()["work"]["second"]["accepted_notice_id"] is None
    final = goal_result(lib)
    with pytest.raises(
        HandoffError, match="PARENT_SCOPE_INCOMPLETE|PENDING_RESULT_REVIEW"
    ):
        co.verify_goal(
            P,
            lib,
            P,
            "handoff:501",
            final,
            "Old effect receipt is not new semantic acceptance",
            co.read()["revision"],
        )
    co.review(
        P,
        "notification:second:partial",
        checked_review(target="second", verdict="partial"),
        lib,
        P,
        co.read()["revision"],
    )
    assert (
        co.status()["parent_state"] == "open"
        and co.read()["work"]["second"]["state"] == "running"
    )


def test_reviewed_partial_remainder_requires_new_completed_review_before_goal(registry):
    co, lib = registry
    old = finish_children(co, lib)
    partial = revised_result(lib, old, 2)
    co.receive(
        P,
        "notification:second:partial",
        "second",
        lib,
        P,
        partial,
        co.read()["revision"],
    )
    co.review(
        P,
        "notification:second:partial",
        checked_review(target="second", verdict="partial"),
        lib,
        P,
        co.read()["revision"],
    )
    assert co.read()["work"]["second"]["accepted_notice_id"] is None
    current = revised_result(lib, partial, 3, state="completed")
    co.receive(
        P,
        "notification:second:resolved",
        "second",
        lib,
        P,
        current,
        co.read()["revision"],
    )
    final = goal_result(lib)
    with pytest.raises(
        HandoffError, match="PARENT_SCOPE_INCOMPLETE|PENDING_RESULT_REVIEW"
    ):
        co.verify_goal(
            P,
            lib,
            P,
            "handoff:501",
            final,
            "Review resolved remainder first",
            co.read()["revision"],
        )
    co.review(
        P,
        "notification:second:resolved",
        checked_review(target="parent"),
        lib,
        P,
        co.read()["revision"],
    )
    done = co.verify_goal(
        P,
        lib,
        P,
        "handoff:501",
        final,
        "Current child and original goal verified",
        co.read()["revision"],
    )
    assert done["parent_state"] == "completed"
    assert (
        done["work"]["second"]["accepted_notice_id"] == "notification:second:resolved"
    )


def test_legacy_completed_rows_without_acceptance_binding_fail_closed(registry):
    co, lib = registry
    finish_children(co, lib)
    legacy = co.read()
    for work in legacy["work"].values():
        work.pop("latest_notice_id")
        work.pop("accepted_notice_id")
    # Persist an old-shaped valid hash snapshot, not a damaged HEAD.
    co._save(legacy)
    final = goal_result(lib)
    before = filemap(co.root)
    with pytest.raises(HandoffError, match="CHILD_ACCEPTANCE_UNBOUND"):
        co.verify_goal(
            P,
            lib,
            P,
            "handoff:501",
            final,
            "Legacy flags are not current acceptance",
            co.read()["revision"],
        )
    assert filemap(co.root) == before and co.status()["parent_state"] == "open"
