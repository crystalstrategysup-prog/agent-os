"""Synthetic completion integration, real argv execution and durable snapshots."""

from __future__ import annotations

import copy
import sys

import pytest

from agent_os.completion import DEPENDENCIES
from agent_os.continuation_adapter import (
    LocalCompletionRunner,
    resolve_completion_capability,
)
from agent_os.handoff_store import HandoffError, encoded, sha
from agent_os.work_coordination import Coordinator

OWNER = "owner-demo-a"
REVIEWER = "reviewer-demo-b"
NOW = 100


def event(
    kind="TURN_FINISHED",
    *,
    generation=1,
    seq=1,
    event_id="event-demo-001",
    payload=None,
):
    return {
        "schema": "agentos.completion-event/v1",
        "event_id": event_id,
        "kind": kind,
        "generation": generation,
        "causal_sequence": seq,
        "observed_at": NOW,
        "payload": payload
        or {
            "turn_id": "turn-demo-001",
            "executor_ref": "executor-demo-a",
            "status": "COMPLETED",
        },
    }


@pytest.fixture
def completion(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session = {
        "session_id": "session-demo-a",
        "kind": "session",
        "parent_session_id": None,
    }
    work = [
        {
            "work_id": "work-demo-001",
            "entity_id": "entity-demo-001",
            "handoff_id": "handoff-demo-001",
            "role": "worker",
            "session": session,
            "depends_on": [],
            "write_set": [{"resource": "repository-demo", "paths": ["."]}],
            "state": "pending",
            "required": True,
        }
    ]
    ids = ["criterion-demo-001", "criterion-demo-002", "criterion-demo-003"]
    co = Coordinator.create(
        tmp_path / "home",
        "stream-demo",
        OWNER,
        "Deliver three verified results",
        ids,
        work,
        coordinator_session=session,
    )
    recipes = {
        str(i): {
            "argv": [sys.executable, "-c", f"print('verified criterion {i}')"],
            "workspace": str(workspace),
            "timeout": 5,
            "artifact_paths": [],
        }
        for i in range(3)
    }
    criteria = [
        {
            "criterion_id": name,
            "requirement_ids": ["R02"],
            "operation": "resume",
            "target": "local-demo",
            "receiver": "receiver-demo-b",
            "data_hash": sha(encoded(recipes[str(i)])),
            "recipe_id": str(i),
        }
        for i, name in enumerate(ids)
    ]
    contract = {
        "schema": "agentos.completion-contract/v1",
        "task_id": "task-demo-001",
        "goal": "Deliver three verified results",
        "acceptance_owner": REVIEWER,
        "source_commit": "a" * 40,
        "contract_hash": "b" * 64,
        "build_hash": "c" * 64,
        "configuration_hash": "d" * 64,
        "environment_fingerprint": "environment-demo",
        "criteria": criteria,
        "budget": {"steps": 6, "deadline": 1000, "tokens": 100, "cost_units": 100},
        "limits": {
            "max_attempts": 3,
            "max_no_progress": 2,
            "lease_seconds": 60,
            "ack_timeout": 120,
            "backoff": [5, 20, 60],
        },
    }
    policy = {
        "revision": 1,
        "actor": OWNER,
        "expires_at": 1000,
        "revoked": False,
        "scope": [
            {
                **{k: row[k] for k in ("operation", "target", "receiver", "data_hash")},
                "environment_fingerprint": "environment-demo",
            }
            for row in criteria
        ],
        "source_ref": "authorization-demo-local",
    }
    co.activate_completion(OWNER, 1, contract, policy, NOW)
    caps = {
        "resume": {
            "status": "SUPPORTED",
            "adapter_version": "local-completion/v1",
            "runtime_version": "python-local",
            "source": "fixture-harmless-probe",
            "target_class": "local-demo",
            "scope": "task-demo-001",
            "evidence_hash": "e" * 64,
            "checked_at": NOW,
            "expires_at": NOW + 200,
        }
    }
    co.completion_update_route(OWNER, co.read()["revision"], NOW, capabilities=caps)
    adapter = LocalCompletionRunner(
        recipes,
        verify_authority=lambda action, value: None,
        read_dependencies=lambda: {k: contract[k] for k in DEPENDENCIES},
        read_clock=lambda: NOW,
    )
    return co, adapter, contract, policy, caps, workspace


def plan_and_dispatch(co):
    p = co.completion_plan(OWNER, co.read()["revision"], NOW)
    return co.completion_begin_dispatch(
        OWNER, co.read()["revision"], p["operation"]["operation_id"], NOW
    )


def test_turn_completion_never_accepts_and_duplicate_is_a_read(completion):
    co, *_ = completion
    co.completion_event(OWNER, co.read()["revision"], event(), NOW)
    before = co.read()
    assert co.completion_status(NOW)["remaining"] == co.read()["criteria"]
    assert not co.completion_status(NOW)["project_completion_proven"]
    co.completion_event(OWNER, 0, event(), NOW)
    assert co.read() == before
    with pytest.raises(HandoffError, match="EVENT_ID_CONFLICT"):
        co.completion_event(OWNER, 0, event(seq=2), NOW)


def test_unknown_dispatch_survives_reopen_and_never_retries(completion):
    co, *_ = completion
    ident = plan_and_dispatch(co)
    reopened = Coordinator(co.root.parents[2], "stream-demo")
    assert reopened.completion_status(NOW)["project_state"] == "BLOCKED_UNKNOWN_OUTCOME"
    with pytest.raises(HandoffError, match="UNKNOWN_EFFECT_NO_RETRY"):
        reopened.completion_begin_dispatch(
            OWNER, reopened.read()["revision"], ident["operation_id"], NOW
        )
    assert (
        reopened.completion_plan(OWNER, reopened.read()["revision"], NOW)["operation"]
        is None
    )


def test_receiver_deduplicates_and_cancel_fences_old_sender(completion):
    co, *_ = completion
    ident = plan_and_dispatch(co)
    assert (
        co.completion_receiver_admit(OWNER, co.read()["revision"], ident, NOW)["status"]
        == "NEW_ADMISSION"
    )
    assert (
        co.completion_receiver_admit(OWNER, co.read()["revision"], ident, NOW)["status"]
        == "ALREADY_ADMITTED"
    )
    co.completion_event(
        OWNER,
        co.read()["revision"],
        event(
            "USER_CANCELLED",
            seq=1,
            payload={"reason": "owner cancelled", "source_ref": "owner-demo-cancel"},
        ),
        NOW,
    )
    with pytest.raises(HandoffError, match="EFFECT_FENCED|TERMINAL_TASK"):
        co.completion_receiver_admit(OWNER, co.read()["revision"], ident, NOW)
    assert co.completion_status(NOW)["project_state"] == "CANCELLED"
    assert co.completion_status(NOW)["unknown_operations"] == [ident["operation_id"]]


def test_policy_revoked_after_discovery_before_effect(completion):
    co, _, _, policy, *_ = completion
    ident = plan_and_dispatch(co)
    co.completion_update_route(
        OWNER,
        co.read()["revision"],
        NOW,
        policy={**policy, "revision": 2, "revoked": True},
    )
    with pytest.raises(HandoffError, match="POLICY_DENIED"):
        co.completion_receiver_admit(OWNER, co.read()["revision"], ident, NOW)
    assert not co.read()["completion"]["operations"][0]["admitted"]


def test_read_is_not_send_and_alias_does_not_grant_support(completion):
    _, _, _, _, caps, _ = completion
    snapshot = {"read": caps["resume"]}
    assert (
        resolve_completion_capability(
            snapshot, "read", "local-demo", "task-demo-001", NOW
        )["status"]
        == "SUPPORTED"
    )
    assert (
        resolve_completion_capability(
            snapshot, "message_send", "local-demo", "task-demo-001", NOW
        )["status"]
        == "UNKNOWN"
    )
    assert (
        resolve_completion_capability(
            snapshot, "native_handoff", "local-demo", "task-demo-001", NOW
        )["status"]
        == "UNKNOWN"
    )


def test_real_registered_three_steps_stop_at_independent_review(completion):
    co, runner, *_ = completion
    for remaining in (2, 1, 0):
        result = runner.run(co, OWNER, NOW)
        assert result["status"] == "PASS"
        assert len(co.completion_status(NOW)["remaining"]) == remaining
        assert co.read()["parent_state"] == "open"
        actual = co._completion_store().json(result["receipt_ref"])
        assert actual["exit_code"] == 0 and actual["run_id"]
        assert (
            co._completion_store()
            .get(actual["evidence_refs"][0])
            .startswith(b"verified criterion")
        )
    assert co.completion_status(NOW)["project_state"] == "VERIFYING"
    assert runner.run(co, OWNER, NOW)["operation"] is None
    with pytest.raises(HandoffError, match="ACCEPTANCE_INCOMPLETE"):
        co.completion_accept(OWNER, co.read()["revision"], NOW, lambda _: None)


def test_zero_budget_before_receiver_admission(completion):
    co, *_ = completion
    ident = plan_and_dispatch(co)
    s = co.read()
    s["completion"]["remaining_budget"]["steps"] = (
        0  # Deliberate valid-store fault injection.
    )
    co._save(s)
    with pytest.raises(HandoffError, match="BUDGET_EXHAUSTED"):
        co.completion_receiver_admit(OWNER, co.read()["revision"], ident, NOW)


def test_waiting_user_and_expired_lease_never_dispatch(completion):
    co, *_ = completion
    co.completion_wait(OWNER, co.read()["revision"], NOW, waiting_user=True)
    before = len(co.read()["completion"]["operations"])
    assert co.completion_plan(OWNER, co.read()["revision"], NOW)["operation"] is None
    assert len(co.read()["completion"]["operations"]) == before
    with pytest.raises(HandoffError, match="OWNERSHIP_LEASE_EXPIRED"):
        co.completion_plan(OWNER, co.read()["revision"], NOW + 60)


def test_reconcile_empty_query_and_non_authoritative_absence_keep_unknown(completion):
    co, *_ = completion
    ident = plan_and_dispatch(co)
    assert (
        co.completion_reconcile(
            OWNER, co.read()["revision"], ident["operation_id"], NOW, lambda _: None
        )["status"]
        == "UNKNOWN"
    )
    p = {
        "schema": "agentos.completion-reconciliation/v1",
        **{
            k: ident[k]
            for k in ("operation_id", "nonce", "generation", "ownership_epoch")
        },
        "outcome": "CONFIRMED_NOT_ADMITTED",
        "evidence_hash": co._completion_store().put(b"non-authoritative stale read")[
            "object_id"
        ][7:],
        "checked_at": NOW,
        "provider": "provider-demo",
        "authoritative": False,
        "dedup_valid_until": 500,
        "processing_horizon": 400,
    }
    ref = co._completion_store().put_json(p)
    with pytest.raises(HandoffError, match="UNKNOWN_EFFECT_NO_RETRY"):
        co.completion_reconcile(
            OWNER, co.read()["revision"], ident["operation_id"], NOW, lambda _: ref
        )
    assert co.completion_status(NOW)["unknown_operations"]


def test_durable_crash_after_intent_prevents_second_effect(completion):
    co, runner, *_ = completion

    def fault(point):
        if point == "after_completion_intent_commit":
            raise RuntimeError("simulated crash")

    co._fault = fault
    with pytest.raises(RuntimeError, match="simulated crash"):
        runner.run(co, OWNER, NOW)
    reopened = Coordinator(co.root.parents[2], "stream-demo")
    assert reopened.completion_status(NOW)["unknown_operations"]
    assert runner.run(reopened, OWNER, NOW)["operation"] is None


def test_legacy_completion_and_dispatch_cannot_bypass_new_gate(completion):
    co, *_ = completion
    with pytest.raises(HandoffError, match="VERSIONED_COMPLETION_DISPATCH_REQUIRED"):
        co.begin_action(OWNER, "anything", co.read()["revision"])


@pytest.mark.parametrize("change", ["cancel", "revoke"])
def test_cancel_or_revoke_at_actual_spawn_boundary_has_zero_effect(completion, change):
    co, runner, _, policy, _, workspace = completion

    def fault(point):
        if point == "before_completion_local_effect":
            if change == "cancel":
                co.completion_event(
                    OWNER,
                    co.read()["revision"],
                    event(
                        "USER_CANCELLED",
                        payload={
                            "reason": "cancel at boundary",
                            "source_ref": "owner-demo-cancel",
                        },
                    ),
                    NOW,
                )
            else:
                co.completion_update_route(
                    OWNER,
                    co.read()["revision"],
                    NOW,
                    policy={**policy, "revision": 2, "revoked": True},
                )

    co._fault = fault
    with pytest.raises(HandoffError, match="EFFECT_FENCED|POLICY_DENIED|TERMINAL_TASK"):
        runner.run(co, OWNER, NOW)
    op = co.read()["completion"]["operations"][0]
    assert op["state"] == "UNKNOWN" and not op.get("process")
    assert list(workspace.iterdir()) == []


def test_real_failed_recipe_stops_with_explicit_replan_blocker(completion):
    co, runner, contract, policy, _caps, _ = completion
    recipe = {
        **runner.recipes["0"],
        "argv": [sys.executable, "-c", "raise SystemExit(1)"],
    }
    updated = copy.deepcopy(contract)
    updated["criteria"][0]["data_hash"] = sha(encoded(recipe))
    updated["contract_hash"] = "f" * 64
    co.completion_change_contract(
        OWNER, co.read()["revision"], updated, NOW, lambda *_: None
    )
    new_policy = copy.deepcopy(policy)
    new_policy["revision"] += 1
    new_policy["scope"][0]["data_hash"] = updated["criteria"][0]["data_hash"]
    co.completion_update_route(OWNER, co.read()["revision"], NOW, policy=new_policy)
    runner = LocalCompletionRunner(
        {**runner.recipes, "0": recipe},
        verify_authority=lambda *_: None,
        read_dependencies=lambda: {k: updated[k] for k in DEPENDENCIES},
        read_clock=lambda: NOW,
    )
    assert runner.run(co, OWNER, NOW)["status"] == "FAIL"
    status = co.completion_status(NOW)
    assert status["project_state"] == "BLOCKED_NO_PROGRESS"
    assert status["blocker"] == "FAILED_RECIPE_REQUIRES_REPLAN"
    assert runner.run(co, OWNER, NOW)["operation"] is None


def test_separate_transfer_operations_do_not_claim_native_handoff(completion):
    co, _, _, _, caps, _ = completion
    snapshot = {
        "read": caps["resume"],
        "send": {"status": "DENIED", "error_code": "TARGET_NOT_FOUND_FOR_OPERATION"},
        "native_handoff": {"status": "UNSUPPORTED"},
        "start": caps["resume"],
        "artifact_transfer": caps["resume"],
    }
    assert (
        resolve_completion_capability(
            snapshot, "native_handoff", "local-demo", "task-demo-001", NOW
        )["status"]
        == "UNSUPPORTED"
    )
    assert (
        resolve_completion_capability(
            snapshot, "message_send", "local-demo", "task-demo-001", NOW
        )["reason"]
        == "TARGET_NOT_FOUND_FOR_OPERATION"
    )
    assert (
        resolve_completion_capability(
            snapshot, "task_create", "local-demo", "task-demo-001", NOW
        )["operation"]
        == "start"
    )
    assert (
        resolve_completion_capability(
            snapshot, "artifact_transfer", "local-demo", "task-demo-001", NOW
        )["operation"]
        == "artifact_transfer"
    )
    assert co.read()["completion"]["operations"] == []


def test_activation_predecessor_backup_is_actual_and_failure_keeps_old_head(
    completion, monkeypatch
):
    co, _, contract, policy, _, _ = completion
    store = co._completion_store()
    old = store.json(co.read()["completion"]["activation_backup_ref"])
    assert old["schema"] == "agentos.work-coordination/v1" and "completion" not in old
    co._save(old)
    before = (co.root / "HEAD.json").read_bytes()
    from agent_os.safeio import filemap

    inventory = filemap(co.root)
    dry = co.activate_completion(
        OWNER, old["revision"], contract, policy, NOW, dry_run=True
    )
    assert dry["status"] == "ACTIVATION_DRY_RUN"
    assert filemap(co.root) == inventory
    real_read = store.json
    monkeypatch.setattr(co, "_completion_store", lambda: store)
    monkeypatch.setattr(store, "json", lambda ref: {"corrupt_fixture": True})
    with pytest.raises(HandoffError, match="ACTIVATION_BACKUP_VERIFICATION_FAILED"):
        co.activate_completion(OWNER, old["revision"], contract, policy, NOW)
    assert (co.root / "HEAD.json").read_bytes() == before
    monkeypatch.setattr(store, "json", real_read)
    result = co.activate_completion(OWNER, old["revision"], contract, policy, NOW)
    assert store.json(result["activation_backup_ref"]) == old
