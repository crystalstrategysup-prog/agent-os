"""Owned disposable processes and deterministic receiver/store fault boundaries."""

from __future__ import annotations

import copy
import sys

import pytest
from test_completion import NOW, OWNER, event, plan_and_dispatch
from test_completion import completion as _completion_fixture
from test_completion_acceptance import checkpoint_source

from agent_os.completion import DEPENDENCIES
from agent_os.continuation_adapter import (
    LocalCompletionRunner,
    resolve_completion_capability,
)
from agent_os.handoff_store import HandoffError, encoded, sha
from agent_os.work_coordination import Coordinator

completion = _completion_fixture


def proof(
    co, identity, outcome="CONFIRMED_NOT_ADMITTED", *, authoritative=True, at=NOW
):
    evidence = co._completion_store().put(b"exact receiver durable admission query")
    return co._completion_store().put_json(
        {
            "schema": "agentos.completion-reconciliation/v1",
            **{
                k: identity[k]
                for k in ("operation_id", "nonce", "generation", "ownership_epoch")
            },
            "outcome": outcome,
            "evidence_hash": evidence["object_id"][7:],
            "checked_at": at,
            "provider": "receiver-demo-local",
            "authoritative": authoritative,
            "dedup_valid_until": 299,
            "processing_horizon": NOW,
        }
    )


@pytest.mark.parametrize(
    "point,unknown",
    [
        ("before_completion_intent_commit", False),
        ("after_completion_intent_commit", True),
        ("after_completion_receiver_admission", True),
        ("after_completion_local_effect", True),
        ("after_completion_result_commit", False),
    ],
)
def test_process_crash_boundaries_reopen_without_duplicate_effect(
    completion, point, unknown
):
    co, runner, *_ = completion

    def fail(where):
        if where == point:
            raise RuntimeError("owned deterministic crash")

    co._fault = fail
    with pytest.raises(RuntimeError):
        runner.run(co, OWNER, NOW)
    reopened = Coordinator(co.root.parents[2], "stream-demo")
    assert bool(reopened.completion_status(NOW)["unknown_operations"]) is unknown
    if unknown:
        count = len(reopened.read()["completion"]["operations"])
        assert runner.run(reopened, OWNER, NOW)["operation"] is None
        assert len(reopened.read()["completion"]["operations"]) == count
    if point == "after_completion_result_commit":
        assert len(reopened.completion_status(NOW)["remaining"]) == 2
        assert len(reopened.read()["completion"]["operations"]) == 1


def test_authoritative_non_admission_retry_keeps_key_and_is_bounded(completion):
    co, *_ = completion
    now = NOW
    original_key = None
    for attempt in range(1, 4):
        planned = co.completion_plan(OWNER, co.read()["revision"], now)
        identity = co.completion_begin_dispatch(
            OWNER, co.read()["revision"], planned["operation"]["operation_id"], now
        )
        original_key = original_key or identity["idempotency_key"]
        assert (
            identity["idempotency_key"] == original_key
            and identity["attempt"] == attempt
        )
        co.completion_reconcile(
            OWNER,
            co.read()["revision"],
            identity["operation_id"],
            now,
            lambda _, identity=identity, now=now: proof(co, identity, at=now),
        )
        op = co.read()["completion"]["operations"][0]
        if attempt < 3:
            assert (
                co.completion_plan(OWNER, co.read()["revision"], now)["status"]
                == "BACKOFF"
            )
            now = op["retry_at"]
    assert co.completion_status(now)["blocker"] == "RETRY_LIMIT"
    assert co.completion_plan(OWNER, co.read()["revision"], now)["operation"] is None
    assert len(co.read()["completion"]["operations"]) == 1


@pytest.mark.parametrize("outcome", ["COMPLETED", "ADMITTED", "RUNNING", "UNKNOWN"])
def test_independent_effect_reconciliation_never_replays_or_accepts_business_result(
    completion, outcome
):
    co, runner, *_ = completion
    identity = plan_and_dispatch(co)
    co.completion_reconcile(
        OWNER,
        co.read()["revision"],
        identity["operation_id"],
        NOW,
        lambda _: proof(co, identity, outcome),
    )
    assert not co.completion_status(NOW)["project_completion_proven"]
    if outcome != "COMPLETED":
        assert runner.run(co, OWNER, NOW)["operation"] is None
    else:
        assert co.completion_status(NOW)["blocker"] == "FAILED_RECIPE_REQUIRES_REPLAN"


def test_reconciliation_missing_bytes_or_wrong_nonce_cannot_authorize_retry(completion):
    co, *_ = completion
    ident = plan_and_dispatch(co)
    store = co._completion_store()
    value = store.json(proof(co, ident))
    for changed in (
        {**value, "evidence_hash": "f" * 64},
        {**value, "nonce": "wrong"},
        {**value, "checked_at": NOW - 1},
    ):
        with pytest.raises(HandoffError):
            co.completion_reconcile(
                OWNER,
                co.read()["revision"],
                ident["operation_id"],
                NOW,
                lambda _, changed=changed: store.put_json(changed),
            )
    assert co.completion_status(NOW)["unknown_operations"]


def test_one_preapproved_strategy_change_keeps_failed_receipt_and_succeeds(completion):
    co, runner, contract, policy, *_ = completion
    bad = {**runner.recipes["0"], "argv": [sys.executable, "-c", "raise SystemExit(1)"]}
    alternate = runner.recipes["0"]
    contract = copy.deepcopy(contract)
    contract["criteria"][0]["data_hash"] = sha(encoded(bad))
    contract["criteria"][0]["alternatives"] = [
        {"recipe_id": "fix", "data_hash": sha(encoded(alternate))}
    ]
    contract["contract_hash"] = "f" * 64
    co.completion_change_contract(
        OWNER, co.read()["revision"], contract, NOW, lambda *_: None
    )
    policy = copy.deepcopy(policy)
    policy["revision"] = 2
    policy["scope"].append(
        {**policy["scope"][0], "data_hash": contract["criteria"][0]["data_hash"]}
    )
    co.completion_update_route(OWNER, co.read()["revision"], NOW, policy=policy)
    runner = LocalCompletionRunner(
        {**runner.recipes, "0": bad, "fix": alternate},
        verify_authority=lambda *_: None,
        read_dependencies=lambda: {k: contract[k] for k in DEPENDENCIES},
        read_clock=lambda: NOW,
    )
    report = runner.run_bounded(co, OWNER, clock=lambda: NOW, max_steps=5)
    assert [r["status"] for r in report["runs"]] == ["FAIL", "PASS", "PASS", "PASS"]
    assert report["status"]["project_state"] == "VERIFYING"
    assert (
        co._completion_store().json(report["runs"][0]["receipt_ref"])["exit_code"] == 1
    )


def test_waiting_user_health_flood_is_coalesced_and_cancel_wins(completion):
    co, runner, *_ = completion
    co.completion_wait(OWNER, co.read()["revision"], NOW, waiting_user=True)
    for i in range(1, 280):
        co.completion_event(
            OWNER, co.read()["revision"], event(seq=i, event_id=f"event-demo-{i}"), NOW
        )
    before = co.read()
    result = runner.run_bounded(co, OWNER, clock=lambda: NOW)
    assert not result["runs"] and co.read()["completion"]["operations"] == []
    assert len(before["completion"]["events"]) <= 256
    assert before["completion"]["event_archive_ref"]
    co.completion_event(
        OWNER,
        co.read()["revision"],
        event(
            "USER_CANCELLED",
            seq=1,
            event_id="cancel-demo",
            payload={"reason": "cancel dominates sequence", "source_ref": "owner-demo"},
        ),
        NOW,
    )
    assert co.completion_status(NOW)["project_state"] == "CANCELLED"


@pytest.mark.parametrize("goal", ["UNSUPPORTED", "DENIED", "UNKNOWN"])
def test_optional_goals_never_auto_enable_and_no_goals_supervisor_runs(
    completion, goal
):
    co, runner, _, _, caps, _ = completion
    caps = {**caps, "goals": {"status": goal}}
    co.completion_update_route(OWNER, co.read()["revision"], NOW, capabilities=caps)
    decision = resolve_completion_capability(
        caps, "goals", "local-demo", "task-demo-001", NOW
    )
    assert decision["status"] == goal
    report = runner.run_bounded(co, OWNER, clock=lambda: NOW)
    assert len(report["runs"]) == 3 and report["status"]["project_state"] == "VERIFYING"
    assert all(
        o["operation"] == "resume" for o in co.read()["completion"]["operations"]
    )


def test_expiry_is_rechecked_at_actual_spawn_not_original_plan_time(completion):
    co, runner, *_ = completion
    now = [NOW]
    runner.read_clock = lambda: now[0]

    def delayed(where):
        if where == "before_completion_local_effect":
            now[0] += 60

    co._fault = delayed
    with pytest.raises(HandoffError, match="OWNERSHIP_LEASE_EXPIRED"):
        runner.run(co, OWNER, NOW)
    assert not co.read()["completion"]["operations"][0].get("process")


def test_interrupted_checkpoint_has_no_verified_receipt_and_stays_paused(completion):
    co, _, _, _, _, workspace = completion
    workspace, paths, target = checkpoint_source(completion)
    co._fault = lambda point: (_ for _ in ()).throw(
        RuntimeError("checkpoint interrupted")
    )
    with pytest.raises(RuntimeError):
        co.completion_checkpoint(
            OWNER, co.read()["revision"], NOW, workspace, paths, lambda *_: target
        )
    reopened = Coordinator(co.root.parents[2], "stream-demo")
    assert reopened.read()["completion"]["paused"]
    assert (
        reopened.completion_plan(OWNER, reopened.read()["revision"], NOW)["operation"]
        is None
    )


@pytest.mark.parametrize(
    "kind,value", [("steps", 0), ("tokens", 0), ("cost_units", 0), ("deadline", NOW)]
)
def test_each_budget_dimension_stops_without_erasing_progress(completion, kind, value):
    co, runner, *_ = completion
    runner.run(co, OWNER, NOW)
    s = co.read()
    s["completion"]["remaining_budget"][kind] = value
    co._save(s)
    result = runner.run_bounded(co, OWNER, clock=lambda: NOW)
    assert not result["runs"] and result["status"]["project_state"] == "BLOCKED_BUDGET"
    assert len(result["status"]["remaining"]) == 2


def test_source_change_invalidates_results_and_preserves_original_receipt(completion):
    co, runner, contract, *_ = completion
    result = runner.run(co, OWNER, NOW)
    changed = copy.deepcopy(contract)
    changed["build_hash"] = "f" * 64
    co.completion_change_contract(
        OWNER, co.read()["revision"], changed, NOW, lambda *_: None
    )
    assert len(co.completion_status(NOW)["remaining"]) == 3
    assert co.read()["work"]["work-demo-001"]["state"] == "pending"
    assert co._completion_store().get(result["receipt_ref"])
    before = len(co.read()["completion"]["operations"])
    stopped = runner.run(co, OWNER, NOW)
    assert stopped["operation"] is None
    assert stopped["reason"] == "FAILED_RECIPE_REQUIRES_REPLAN"
    assert len(co.read()["completion"]["operations"]) == before


def test_duplicate_and_out_of_order_events_do_not_regress_generation(completion):
    co, runner, *_ = completion
    fresh = event(seq=10)
    co.completion_event(OWNER, co.read()["revision"], fresh, NOW)
    before = co.read()["revision"]
    for _ in range(3):
        co.completion_event(OWNER, 0, fresh, NOW)
    assert co.read()["revision"] == before
    co.completion_event(
        OWNER, co.read()["revision"], event(seq=1, event_id="old-demo"), NOW
    )
    assert not co.read()["completion"]["events"][-1]["actionable"]
    assert (
        len(runner.run_bounded(co, OWNER, clock=lambda: NOW, max_steps=1)["runs"]) == 1
    )


def takeover(co, policy, owner="new-owner-demo"):
    c = co.read()["completion"]
    p = {
        "schema": "agentos.completion-takeover/v1",
        "mode": "EFFECT_FENCED",
        "task_id": c["contract"]["task_id"],
        "previous_owner": OWNER,
        "new_owner": owner,
        "generation": c["generation"],
        "previous_epoch": c["ownership_epoch"],
        "policy_revision": c["policy"]["revision"],
        "checked_at": NOW,
        "evidence_refs": [
            co._completion_store().put(b"exact current fixture receiver fence")
        ],
        "old_writer_quiescent": False,
        "reconciled_operation_ids": [],
        "receiver_fence_verified": True,
    }
    co.completion_takeover(
        owner,
        co.read()["revision"],
        NOW,
        co._completion_store().put_json(p),
        lambda _: None,
        {**policy, "actor": owner, "revision": 2},
    )
    return owner


def test_old_epoch_execution_result_is_audit_only_after_takeover(completion):
    co, runner, _, policy, *_ = completion
    co._fault = lambda where: (
        (_ for _ in ()).throw(RuntimeError("lost response"))
        if where == "after_completion_local_effect"
        else None
    )
    with pytest.raises(RuntimeError):
        runner.run(co, OWNER, NOW)
    store = co._completion_store()
    identity = co.read()["completion"]["operations"][0]["identity"]
    # Find the adapter's durable real execution receipt, without inventing PASS.
    from agent_os.handoff_store import bounded, parse

    receipts = []
    for path in store.root.glob("objects/sha256/*/*"):
        try:
            value = parse(bounded(path))
        except HandoffError:
            continue
        if (
            isinstance(value, dict)
            and value.get("schema") == "agentos.completion-execution/v1"
        ):
            receipts.append(store.reference(bounded(path)))
    assert len(receipts) == 1
    owner = takeover(co, policy)
    before_budget = copy.deepcopy(co.read()["completion"]["remaining_budget"])
    before_runtime = co.read()["completion"]["actual_runtime"]
    co.completion_record_result(
        owner,
        co.read()["revision"],
        identity,
        receipts[0],
        NOW,
        lambda value, binding: value == store.json(receipts[0]) and binding == identity,
    )
    assert len(co.completion_status(NOW)["remaining"]) == 3
    assert co.read()["completion"]["remaining_budget"] == before_budget
    assert co.read()["completion"]["actual_runtime"] == before_runtime
    assert any(
        a["kind"] == "LATE_RESULT_AUDIT_ONLY" for a in co.read()["completion"]["audit"]
    )


def test_takeover_non_admission_rebinds_retry_to_new_epoch(completion):
    co, _, _, policy, *_ = completion
    identity = plan_and_dispatch(co)
    owner = takeover(co, policy)
    co.completion_reconcile(
        owner,
        co.read()["revision"],
        identity["operation_id"],
        NOW,
        lambda _: proof(co, identity),
    )
    now = co.read()["completion"]["operations"][0]["retry_at"]
    p = co.completion_plan(owner, co.read()["revision"], now)
    new = co.completion_begin_dispatch(
        owner, co.read()["revision"], p["operation"]["operation_id"], now
    )
    assert new["idempotency_key"] == identity["idempotency_key"]
    assert new["ownership_epoch"] == 2 and new["nonce"] != identity["nonce"]
    assert (
        co.completion_receiver_admit(owner, co.read()["revision"], new, now)["status"]
        == "NEW_ADMISSION"
    )
    with pytest.raises(HandoffError):
        co.completion_receiver_admit(OWNER, co.read()["revision"], identity, now)


def test_archived_event_id_is_still_deduplicated_and_conflicts_rejected(completion):
    co, *_ = completion
    first = event(event_id="archived-demo")
    co.completion_event(OWNER, co.read()["revision"], first, NOW)
    for i in range(2, 280):
        co.completion_event(
            OWNER, co.read()["revision"], event(seq=i, event_id=f"flood-demo-{i}"), NOW
        )
    before = co.read()
    co.completion_event(OWNER, 0, first, NOW)
    assert co.read() == before
    with pytest.raises(HandoffError, match="EVENT_ID_CONFLICT"):
        co.completion_event(
            OWNER, co.read()["revision"], {**first, "causal_sequence": 300}, NOW
        )


def _race_writer(home, revision, queue, barrier):
    co = Coordinator(home, "stream-demo")
    barrier.wait(timeout=10)
    try:
        result = co.completion_plan(OWNER, revision, NOW)
        queue.put(result["status"])
    except HandoffError as error:
        queue.put(str(error))


def test_two_real_process_writers_have_one_cas_winner(completion):
    import multiprocessing

    co, *_ = completion
    ctx = multiprocessing.get_context("spawn")
    queue, barrier = ctx.Queue(), ctx.Barrier(2)
    processes = [
        ctx.Process(
            target=_race_writer,
            args=(co.root.parents[2], co.read()["revision"], queue, barrier),
        )
        for _ in range(2)
    ]
    try:
        for process in processes:
            process.start()
        results = [queue.get(timeout=15) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        assert results.count("PREPARED") == 1
        assert results.count("GENERATION_CONFLICT") == 1
        assert len(co.read()["completion"]["operations"]) == 1
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        queue.close()


def test_new_epoch_fences_paused_old_sender_at_spawn(completion):
    co, runner, _, policy, *_ = completion

    def paused(where):
        if where == "before_completion_local_effect":
            takeover(co, policy)

    co._fault = paused
    with pytest.raises(HandoffError, match="OWNER_MISMATCH|EFFECT_FENCED|NOT_OWNER"):
        runner.run(co, OWNER, NOW)
    assert not co.read()["completion"]["operations"][0].get("process")
    assert co.read()["owner"] == "new-owner-demo"


def test_clock_skew_and_unsafe_quiescence_cannot_reinitialize(completion):
    co, *_ = completion
    with pytest.raises(HandoffError, match="CLOCK_REVERSED"):
        co.completion_plan(OWNER, co.read()["revision"], NOW - 1)
    identity = plan_and_dispatch(co)
    co.completion_receiver_admit(OWNER, co.read()["revision"], identity, NOW)
    c = co.read()["completion"]
    p = {
        "schema": "agentos.completion-takeover/v1",
        "mode": "QUIESCENCE_REQUIRED",
        "task_id": c["contract"]["task_id"],
        "previous_owner": OWNER,
        "new_owner": "new-owner-demo",
        "generation": 1,
        "previous_epoch": 1,
        "policy_revision": 1,
        "checked_at": NOW,
        "evidence_refs": [
            co._completion_store().put(b"unverified old writer still active")
        ],
        "old_writer_quiescent": False,
        "reconciled_operation_ids": [],
        "receiver_fence_verified": False,
    }
    with pytest.raises(HandoffError, match="BLOCKED_UNSAFE_TAKEOVER"):
        co.completion_takeover(
            "new-owner-demo",
            co.read()["revision"],
            NOW,
            co._completion_store().put_json(p),
            lambda _: None,
            {**c["policy"], "actor": "new-owner-demo", "revision": 2},
        )
    assert co.read()["owner"] == OWNER


def test_public_status_is_stale_honest_and_contains_no_private_identity(completion):
    co, *_ = completion
    status = co.completion_public_status(NOW + 100)
    assert status["status_freshness"] == "STALE"
    assert status["age_seconds"] == 100 and status["actual_model"] == "UNKNOWN"
    assert status["blocker"] == "OWNERSHIP_LEASE_EXPIRED"
    assert OWNER not in repr(status) and "stream-demo" not in repr(status)
    assert not status["project_completion_proven"]


def test_error_is_scoped_to_operation_and_preserves_read_capability(completion):
    co, _, _, _, caps, _ = completion
    co.completion_update_route(
        OWNER,
        co.read()["revision"],
        NOW,
        capabilities={**caps, "read": copy.deepcopy(caps["resume"])},
    )
    co.completion_route_error(
        OWNER,
        co.read()["revision"],
        NOW,
        operation="resume",
        target="local-demo",
        environment="environment-demo",
        error_code="TARGET_NOT_FOUND_FOR_OPERATION",
    )
    c = co.read()["completion"]
    assert (
        resolve_completion_capability(
            c["capabilities"], "read", "local-demo", "task-demo-001", NOW
        )["status"]
        == "SUPPORTED"
    )
    denied = resolve_completion_capability(
        c["capabilities"], "resume", "local-demo", "task-demo-001", NOW
    )
    assert denied["reason"] == "TARGET_NOT_FOUND_FOR_OPERATION"
    with pytest.raises(HandoffError, match="ERROR_ROUTE_BINDING_MISMATCH"):
        co.completion_route_error(
            OWNER,
            co.read()["revision"],
            NOW,
            operation="read",
            target="wrong-demo",
            environment="environment-demo",
            error_code="OFFLINE",
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("target", "wrong-demo"),
        ("receiver", "wrong-demo"),
        ("data_hash", "f" * 64),
        ("environment_fingerprint", "different-environment"),
    ],
)
def test_changed_exact_policy_scope_prevents_effect(completion, field, value):
    co, runner, _, policy, *_ = completion
    policy = copy.deepcopy(policy)
    policy["revision"] = 2
    policy["scope"][0][field] = value
    co.completion_update_route(OWNER, co.read()["revision"], NOW, policy=policy)
    with pytest.raises(HandoffError, match="POLICY_DENIED"):
        runner.run(co, OWNER, NOW)
    assert co.read()["completion"]["operations"] == []


def test_source_only_execution_claim_is_not_host_evidence(completion):
    co, runner, *_ = completion
    result = runner.run(co, OWNER, NOW)
    identity = co.read()["completion"]["operations"][0]["identity"]
    with pytest.raises(HandoffError, match="AUTHENTICATED_EXECUTION_VERIFIER_REQUIRED"):
        co.completion_record_result(
            OWNER, co.read()["revision"], identity, result["receipt_ref"], NOW
        )
    with pytest.raises(HandoffError, match="HOST_EVIDENCE_REQUIRED"):
        co.completion_record_result(
            OWNER,
            co.read()["revision"],
            identity,
            result["receipt_ref"],
            NOW,
            lambda *_: False,
        )


def test_checkpoint_source_change_after_pause_is_not_verified(completion):
    co, *_ = completion
    workspace, paths, target = checkpoint_source(completion)

    def change(where):
        if where == "after_completion_commit":
            (workspace / "notes.txt").write_text("changed after manifest")

    co._fault = change
    with pytest.raises(HandoffError, match="SOURCE_CHANGED_DURING_CHECKPOINT"):
        co.completion_checkpoint(
            OWNER, co.read()["revision"], NOW, workspace, paths, lambda *_: target
        )
    assert co.read()["completion"]["paused"]


def test_all_expired_owner_mutation_paths_are_fenced(completion, tmp_path):
    from test_completion_acceptance import actual_ack, prepared_handoff

    co, _, _, _, _, workspace = completion
    root, envelope = prepared_handoff(completion, tmp_path)
    ack, verifier = actual_ack(co, root, envelope)
    co.completion_handoff_sent(OWNER, co.read()["revision"], NOW)
    store = co._completion_store()
    ack_ref = store.put_json(ack)
    workspace, paths, target = checkpoint_source(completion)
    before = co.read()
    for call in [
        lambda: co.completion_event(OWNER, before["revision"], event(), NOW + 60),
        lambda: co.completion_ack(
            OWNER, before["revision"], ack_ref, NOW + 60, verifier
        ),
        lambda: co.completion_checkpoint(
            OWNER, before["revision"], NOW + 60, workspace, paths, lambda *_: target
        ),
    ]:
        with pytest.raises(HandoffError, match="OWNERSHIP_LEASE_EXPIRED"):
            call()
        assert co.read() == before


def test_cancel_index_has_one_reserved_slot_and_terminal_flood_is_bounded(completion):
    co, *_ = completion
    state = co.read()
    state["completion"]["event_id_index"] = {f"synthetic-{i}": "f" * 64 for i in range(4096)}
    co._save(state)
    co.completion_event(OWNER, co.read()["revision"], event("USER_CANCELLED", event_id="last-cancel", payload={"reason":"owner cancel","source_ref":"owner-demo"}), NOW)
    before = co.read()
    for i in range(256):
        co.completion_event(OWNER, co.read()["revision"], event("USER_CANCELLED", event_id=f"cancel-{i}", payload={"reason":"owner cancel","source_ref":"owner-demo"}), NOW)
    after = co.read()
    assert after["completion"]["cancel_fence"] == before["completion"]["cancel_fence"]
    assert len(after["completion"]["event_id_index"]) == 4097
    assert len(after["completion"]["terminal_event_id_index"]) == 256
    with pytest.raises(HandoffError, match="TERMINAL_EVENT_INDEX_LIMIT"):
        co.completion_event(OWNER, co.read()["revision"], event(event_id="terminal-overflow"), NOW)
    co.completion_event(OWNER, 0, event("USER_CANCELLED", event_id="cancel-0", payload={"reason":"owner cancel","source_ref":"owner-demo"}), NOW+100)
    assert co.read() == after
    with pytest.raises(HandoffError, match="EVENT_ID_CONFLICT"):
        co.completion_event(OWNER, 0, event("USER_CANCELLED", event_id="cancel-0", payload={"reason":"conflicting cancel","source_ref":"owner-demo"}), NOW)
    assert co.read() == after


def test_goals_policy_migration_preserves_deny_and_explicit_opt_in_scope(completion):
    co, _, _, policy, caps, _ = completion
    before = co.read()
    # Discovery/update may add a capability; it cannot add missing authority.
    caps = {**caps, "goals": copy.deepcopy(caps["resume"])}
    co.completion_update_route(OWNER, co.read()["revision"], NOW, capabilities=caps)
    assert co.read()["completion"]["policy"] == before["completion"]["policy"]
    assert "goals_opt_in" not in co.read()["completion"]
    request = {
        "target": "local-demo",
        "receiver": "receiver-demo-b",
        "data_hash": "f" * 64,
    }
    with pytest.raises(HandoffError, match="EXPLICIT_GOALS_OPT_IN_REQUIRED"):
        co.completion_goals_opt_in(OWNER, co.read()["revision"], NOW, **request)
    with pytest.raises(HandoffError, match="POLICY_DENIED"):
        co.completion_goals_opt_in(
            OWNER,
            co.read()["revision"],
            NOW,
            **request,
            verify_authority=lambda *_: True,
        )
    updated = copy.deepcopy(policy)
    updated["revision"] = 2
    updated["scope"].append(
        {"operation": "goals", **request, "environment_fingerprint": "environment-demo"}
    )
    co.completion_update_route(OWNER, co.read()["revision"], NOW, policy=updated)
    recorded = co.completion_goals_opt_in(
        OWNER,
        co.read()["revision"],
        NOW,
        **request,
        verify_authority=lambda operation, value: (
            operation == "goals-opt-in" and value == {"operation": "goals", **request}
        ),
    )
    assert recorded["status"] == "SCOPED_OPT_IN_RECORDED_NOT_ACTIVATED"
    assert recorded["policy_revision"] == 2 and recorded["task_id"] == "task-demo-001"
    assert co.read()["completion"]["operations"] == []
    assert co.read()["completion"]["policy"]["scope"][:-1] == policy["scope"]


def test_event_apply_crash_reopens_and_duplicate_never_reapplies(completion):
    co, *_ = completion
    notice = event()
    co._fault = lambda _: (_ for _ in ()).throw(
        RuntimeError("crash after event commit")
    )
    with pytest.raises(RuntimeError):
        co.completion_event(OWNER, co.read()["revision"], notice, NOW)
    reopened = Coordinator(co.root.parents[2], "stream-demo")
    before = reopened.read()
    reopened.completion_event(OWNER, 0, notice, NOW)
    assert reopened.read() == before


def test_restored_old_completed_effect_is_not_replayed_after_reconciliation(
    completion, tmp_path
):
    co, runner, *_ = completion
    original = co._fault

    def crash_after_effect(point):
        if point == "after_completion_local_effect":
            raise RuntimeError("owned effect response lost")

    co._fault = crash_after_effect
    with pytest.raises(RuntimeError):
        runner.run(co, OWNER, NOW)
    co._fault = original
    identity = co.read()["completion"]["operations"][0]["identity"]
    workspace, paths, target = checkpoint_source(completion)
    cp = co.completion_checkpoint(
        OWNER, co.read()["revision"], NOW, workspace, paths, lambda *_: target
    )
    rehearsal = co.completion_rehearse_restore(
        cp["checkpoint_ref"], tmp_path / "old-effect-restore"
    )
    target_proof = {
        k: target[k] for k in ("target_ref", "environment", "source_commit")
    }
    target_proof.update(
        old_writer_quiescent=True,
        receiver_fence_verified=True,
        reconciled_operation_ids=[],
        current_authority=True,
        restored_artifact_hashes=rehearsal["artifact_hashes"],
    )
    co.completion_restore(
        OWNER,
        co.read()["revision"],
        NOW,
        cp["checkpoint_ref"],
        co._completion_store().put_json(rehearsal),
        lambda *_: target_proof,
    )
    assert co.completion_status(NOW)["unknown_operations"]
    co.completion_reconcile(
        OWNER,
        co.read()["revision"],
        identity["operation_id"],
        NOW,
        lambda _: proof(co, identity, "COMPLETED"),
    )
    before = len(co.read()["completion"]["operations"])
    result = runner.run_bounded(co, OWNER, clock=lambda: NOW)
    assert not result["runs"]
    assert result["status"]["blocker"] == "FAILED_RECIPE_REQUIRES_REPLAN"
    assert len(co.read()["completion"]["operations"]) == before
