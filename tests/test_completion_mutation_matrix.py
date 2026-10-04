"""Exhaustive public mutation matrix and deterministic generated interleavings.

Synthetic state setup uses the private publisher only to position test corners;
all observations/transitions under test use public APIs with valid payloads.
"""

from __future__ import annotations

import ast
import copy
import itertools
import json
import random
from pathlib import Path

import pytest
from test_completion import NOW, OWNER, event, plan_and_dispatch
from test_completion import completion as _fixture
from test_completion_acceptance import actual_ack, prepared_handoff, reviewed_results

from agent_os.completion import CompletionMixin
from agent_os.handoff_store import HandoffError, encoded, sha
from agent_os.safeio import filemap
from agent_os.work_coordination import Coordinator

completion = _fixture
ROOT = Path(__file__).resolve().parents[1]
LEGACY = (
    "receive",
    "recover_notice",
    "review",
    "checkpoint",
    "begin_action",
    "record_outcome",
    "verify_goal",
)
ADMIN = (
    "completion_heartbeat",
    "completion_update_route",
    "completion_route_error",
    "completion_change_contract",
)
EXECUTION = (
    "completion_begin_dispatch",
    "completion_receiver_admit",
    "completion_spawn_local",
    "completion_wait",
    "completion_review",
    "completion_prepare_handoff",
    "completion_handoff_sent",
    "completion_accept",
    "completion_goals_opt_in",
)
OTHERS = (
    "completion_plan",
    "completion_ack",
    "completion_record_result",
    "completion_reconcile",
    "completion_takeover",
    "completion_checkpoint",
    "completion_restore",
    "completion_event",
)
MUTATORS = ADMIN + EXECUTION + OTHERS + LEGACY
CORNERS = list(
    itertools.product(
        ("current", "stale"),
        ("live", "expired"),
        (False, True),
        (False, True),
        ("new", "duplicate", "conflicting"),
    )
)


def control_view(s):
    """Exclude only pure audit/observation fields; ledger is kept separate."""
    v = copy.deepcopy(s)
    v.pop("revision", None)
    for k in (
        "audit",
        "audit_archive_ref",
        "checked_at",
        "terminal_event_id_index",
        "late_ack_refs",
    ):
        v["completion"].pop(k, None)
    return v


def checkpoint_packet(co, workspace):
    src = workspace / "checkpoint-source"
    src.mkdir()
    for name in ("tracked.py", "untracked.txt", "dirty.patch"):
        (src / name).write_bytes((name + " actual synthetic checkpoint bytes").encode())
    inventory = filemap(src)
    target = {
        "target_ref": "owned-checkpoint-demo",
        "environment": "environment-demo",
        "source_commit": "a" * 40,
        "branch": "synthetic-demo",
        "process_inventory": [],
        "ownership_verified": True,
        "source_manifest": {
            "schema": "agentos.completion-source-checkpoint/v1",
            "tracked_paths": ["tracked.py"],
            "untracked_paths": ["untracked.txt"],
            "dirty_patch_path": "dirty.patch",
            "inventory_sha256": sha(encoded(inventory)),
        },
    }
    return src, list(inventory), target


def operation(fixture, tmp, name, verifier=None):
    co, runner, contract, policy, caps, workspace = fixture
    verifier = verifier or (lambda *_: None)
    if name == "completion_heartbeat":
        return lambda a, r, t: co.completion_heartbeat(a, r, t)
    if name == "completion_update_route":
        return lambda a, r, t: co.completion_update_route(
            a,
            r,
            t,
            policy={
                **co.read()["completion"]["policy"],
                "revision": co.read()["completion"]["policy"]["revision"] + 1,
            },
        )
    if name == "completion_route_error":
        return lambda a, r, t: co.completion_route_error(
            a,
            r,
            t,
            operation="resume",
            target="local-demo",
            environment="environment-demo",
            error_code="TRANSIENT",
        )
    if name == "completion_change_contract":
        return lambda a, r, t: co.completion_change_contract(
            a, r, {**contract, "contract_hash": "f" * 64}, t, verifier
        )
    if name == "completion_wait":
        return lambda a, r, t: co.completion_wait(a, r, t, waiting_user=True)
    if name == "completion_plan":
        return lambda a, r, t: co.completion_plan(a, r, t)
    if name == "completion_event":
        return lambda a, r, t: co.completion_event(
            a, r, event(event_id="operation-event"), t
        )
    if name == "completion_goals_opt_in":
        c = co.read()
        c["completion"]["capabilities"]["goals"] = {**caps["resume"]}
        c["completion"]["policy"]["scope"].append(
            {**policy["scope"][0], "operation": "goals"}
        )
        co._save(c)
        return lambda a, r, t: co.completion_goals_opt_in(
            a,
            r,
            t,
            target="local-demo",
            receiver="receiver-demo-b",
            data_hash=policy["scope"][0]["data_hash"],
            verify_authority=lambda *_: True,
        )
    if name == "completion_begin_dispatch":
        p = co.completion_plan(OWNER, co.read()["revision"], NOW)
        return lambda a, r, t: co.completion_begin_dispatch(
            a, r, p["operation"]["operation_id"], t
        )
    if name in (
        "completion_receiver_admit",
        "completion_spawn_local",
        "completion_reconcile",
    ):
        identity = plan_and_dispatch(co)
        if name == "completion_receiver_admit":
            return lambda a, r, t: co.completion_receiver_admit(a, r, identity, t)
        if name == "completion_spawn_local":
            co.completion_receiver_admit(OWNER, co.read()["revision"], identity, NOW)
            return lambda a, r, t: co.completion_spawn_local(
                a, r, identity, t, runner.recipes["0"], None
            )
        store = co._completion_store()
        evidence = store.put(b"synthetic exact-operation receiver nonadmission")
        proof = {
            "schema": "agentos.completion-reconciliation/v1",
            **{
                k: identity[k]
                for k in ("operation_id", "nonce", "generation", "ownership_epoch")
            },
            "outcome": "CONFIRMED_NOT_ADMITTED",
            "evidence_hash": evidence["object_id"][7:],
            "checked_at": NOW,
            "provider": "synthetic-receiver",
            "authoritative": True,
            "dedup_valid_until": NOW + 100,
            "processing_horizon": NOW,
        }
        ref = store.put_json(proof)
        return lambda a, r, t: co.completion_reconcile(
            a, r, identity["operation_id"], t, lambda _: ref
        )
    if name == "completion_record_result":
        assert runner.run(co, OWNER, NOW)["status"] == "PASS"
        s = co.read()
        op = s["completion"]["operations"][0]
        identity = copy.deepcopy(op["identity"])
        ref = op["result_ref"]
        op.update(state="UNKNOWN", result_ref=None)
        s["completion"]["results"] = {}
        s["completion"]["actual_runtime"] = None
        co._save(s)
        return lambda a, r, t: co.completion_record_result(
            a, r, identity, ref, t, lambda *_: True
        )
    if name in ("completion_review", "completion_accept"):
        for _ in range(3):
            runner.run(co, OWNER, NOW)
        ref = reviewed_results(co, contract)
        if name == "completion_review":
            return lambda a, r, t: co.completion_review(a, r, ref, t, verifier)
    if name in (
        "completion_prepare_handoff",
        "completion_handoff_sent",
        "completion_ack",
        "completion_accept",
    ):
        root, envelope = prepared_handoff(fixture, tmp)
        if name == "completion_prepare_handoff":
            s = co.read()
            s["completion"]["handoff"] = None
            co._save(s)
            return lambda a, r, t: co.completion_prepare_handoff(
                a, r, envelope, root, t, verifier
            )
        if name == "completion_handoff_sent":
            return lambda a, r, t: co.completion_handoff_sent(a, r, t)
        co.completion_handoff_sent(OWNER, co.read()["revision"], NOW)
        ack, verify = actual_ack(co, root, envelope)
        ref = co._completion_store().put_json(ack)
        if name == "completion_ack":
            return lambda a, r, t: co.completion_ack(a, r, ref, t, verify)
        co.completion_ack(OWNER, co.read()["revision"], ref, NOW, verify)
        return lambda a, r, t: co.completion_accept(a, r, t, verifier)
    if name in ("completion_checkpoint", "completion_restore"):
        src, paths, target = checkpoint_packet(co, workspace)
        if name == "completion_checkpoint":
            return lambda a, r, t: co.completion_checkpoint(
                a, r, t, src, paths, lambda *_: target
            )
        cp = co.completion_checkpoint(
            OWNER, co.read()["revision"], NOW, src, paths, lambda *_: target
        )
        rehearsal = co.completion_rehearse_restore(
            cp["checkpoint_ref"], workspace / "rehearsal"
        )
        ref = co._completion_store().put_json(rehearsal)
        proof = {k: target[k] for k in ("target_ref", "source_commit", "environment")}
        proof.update(
            old_writer_quiescent=False,
            receiver_fence_verified=True,
            reconciled_operation_ids=[],
            current_authority=True,
            restored_artifact_hashes=rehearsal["artifact_hashes"],
        )
        return lambda a, r, t: co.completion_restore(
            a, r, t, cp["checkpoint_ref"], ref, lambda *_: proof
        )
    if name == "completion_takeover":
        c = co.read()["completion"]
        store = co._completion_store()
        proof = {
            "schema": "agentos.completion-takeover/v1",
            "mode": "EFFECT_FENCED",
            "task_id": contract["task_id"],
            "previous_owner": OWNER,
            "new_owner": "successor-demo",
            "generation": c["generation"],
            "previous_epoch": c["ownership_epoch"],
            "policy_revision": c["policy"]["revision"],
            "checked_at": NOW,
            "evidence_refs": [store.put(b"synthetic verified receiver fence")],
            "old_writer_quiescent": False,
            "reconciled_operation_ids": [],
            "receiver_fence_verified": True,
        }

        def takeover(a, r, t):
            p = {**proof, "checked_at": t}
            return co.completion_takeover(
                "successor-demo" if a == OWNER else a,
                r,
                t,
                store.put_json(p),
                verifier,
                {**policy, "actor": "successor-demo", "revision": 2},
            )

        return takeover

    class NoLibrary:
        def __getattr__(self, key):
            raise AssertionError("legacy callback reached " + key)

    library = NoLibrary()
    legacy = {
        "receive": lambda a, r, t: co.receive(
            a, "notice-demo", "work-demo-001", library, "principal-demo", {}, r
        ),
        "recover_notice": lambda a, r, t: co.recover_notice(
            a, "work-demo-001", library, "principal-demo", r
        ),
        "review": lambda a, r, t: co.review(
            a, "notice-demo", {}, library, "principal-demo", r
        ),
        "checkpoint": lambda a, r, t: co.checkpoint(a, "owned checkpoint", r),
        "begin_action": lambda a, r, t: co.begin_action(a, "action-demo", r),
        "record_outcome": lambda a, r, t: co.record_outcome(
            a, "action-demo", library, "principal-demo", {}, r
        ),
        "verify_goal": lambda a, r, t: co.verify_goal(
            a, library, "principal-demo", "handoff-demo", {}, "original goal", r
        ),
    }
    return legacy[name]


@pytest.mark.parametrize("name", MUTATORS)
@pytest.mark.parametrize("owner,lease,cancelled,revoked,replay", CORNERS)
def test_all_public_mutation_guard_matrix(
    completion, tmp_path, name, owner, lease, cancelled, revoked, replay
):
    co, *_ = completion
    invoke = operation(completion, tmp_path, name)
    seed = event(event_id="matrix-seed")
    co.completion_event(OWNER, co.read()["revision"], seed, NOW)
    s = co.read()
    c = s["completion"]
    if cancelled:
        c["state"] = "CANCELLED"
        c["blocker"] = "OWNER_CANCELLED"
        c["cancel_fence"] += 1
        s["parent_state"] = "cancelled"
    c["policy"]["revoked"] = revoked
    if lease == "expired":
        c["lease_expires_at"] = NOW
    co._save(s)
    actor = OWNER if owner == "current" else "stale-owner-demo"
    before = co.read()
    if replay != "new":
        delivered = seed if replay == "duplicate" else {**seed, "causal_sequence": 2}
        try:
            co.completion_event(actor, 0, delivered, NOW)
        except HandoffError as e:
            assert owner == "stale" or replay == "conflicting", e.code
        else:
            assert owner == "current" and replay == "duplicate"
        assert co.read() == before
    blocked = (
        owner == "stale"
        or lease == "expired"
        or (
            cancelled
            and name
            not in (
                "completion_checkpoint",
                "completion_restore",
                "completion_event",
                "completion_ack",
                "completion_record_result",
                "completion_reconcile",
                "completion_plan",
            )
        )
        or (revoked and name in EXECUTION + ("completion_update_route",))
        or name in LEGACY
    )
    if name == "completion_takeover":
        blocked = owner == "stale" or cancelled  # authenticated successor exception
    if name == "completion_plan" and cancelled and owner == "current":
        blocked = False  # terminal read
    try:
        result = invoke(actor, co.read()["revision"], NOW)
        if hasattr(result, "communicate"):
            result.communicate(timeout=5)
            assert result.returncode == 0
    except HandoffError as e:
        assert blocked, (name, owner, lease, cancelled, revoked, e.code)
        assert co.read() == before
    else:
        assert not blocked, (name, owner, lease, cancelled, revoked)
        after = co.read()
        if name == "completion_plan" and (cancelled or revoked):
            assert (
                after["completion"]["operations"] == before["completion"]["operations"]
            )
        if name in ("completion_record_result", "completion_ack") and (
            cancelled or revoked
        ):
            assert (
                after["completion"]["remaining_budget"]
                == before["completion"]["remaining_budget"]
            )
            assert after["completion"]["results"] == before["completion"]["results"]
            assert (
                after["completion"]["actual_runtime"]
                == before["completion"]["actual_runtime"]
            )
            assert after.get("goal_acceptance") == before.get("goal_acceptance")
        if name == "completion_reconcile":
            assert co._completion_ledger_view(after) == co._completion_ledger_view(
                before
            )
        if cancelled:
            assert (
                after["completion"]["state"] == "CANCELLED"
                and after["parent_state"] == "cancelled"
            )


def test_inventory_covers_every_public_method():
    inventory = json.loads(
        (ROOT / "docs/completion/MUTATION_SURFACES.json").read_bytes()
    )
    expected = set(MUTATORS) | {
        "create",
        "activate_completion",
        "completion_verify_checkpoint",
        "completion_rehearse_restore",
    }
    assert {r["operation"] for r in inventory["entry_points"]} == expected
    public = {
        name
        for cls in (CompletionMixin, Coordinator)
        for name, value in cls.__dict__.items()
        if callable(value) and not name.startswith("_")
    }
    assert public - expected == {
        "read",
        "status",
        "completion_status",
        "completion_public_status",
    }
    for module in ("completion.py", "work_coordination.py"):
        tree = ast.parse((ROOT / "src/agent_os" / module).read_text())
        for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            for node in cls.body:
                if (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not node.name.startswith("_")
                    and node.name not in expected
                ):
                    assert node.name in {
                        "read",
                        "status",
                        "completion_status",
                        "completion_public_status",
                    }


@pytest.mark.parametrize("name", ADMIN + EXECUTION + ("completion_change_contract",))
def test_accepted_control_and_effects_are_immutable(completion, tmp_path, name):
    co, *_ = completion
    invoke = operation(completion, tmp_path, name)
    s = co.read()
    s["completion"]["state"] = "ACCEPTED"
    s["completion"]["delivery"] = "ACKED"
    s["parent_state"] = "completed"
    co._save(s)
    before = co.read()
    with pytest.raises(HandoffError, match="TERMINAL_TASK"):
        invoke(OWNER, before["revision"], NOW)
    assert co.read() == before


@pytest.mark.parametrize("seed", range(16))
def test_generated_terminal_event_interleavings_preserve_execution(completion, seed):
    co, *_ = completion
    rng = random.Random(seed)
    co.completion_event(
        OWNER,
        co.read()["revision"],
        event(
            "USER_CANCELLED",
            event_id="initial-cancel",
            payload={"reason": "cancel", "source_ref": "owner-demo"},
        ),
        NOW,
    )
    baseline = control_view(co.read())
    seen = {}
    for i in range(80):
        key = "generated-" + str(rng.randrange(20))
        message = event(event_id=key, seq=1)
        actor = OWNER if rng.randrange(4) else "stale-owner-demo"
        if key in seen and rng.randrange(3) == 0:
            message = {**message, "causal_sequence": 2}
        before = co.read()
        try:
            co.completion_event(actor, co.read()["revision"], message, NOW)
        except HandoffError as e:
            assert actor != OWNER or (key in seen and message != seen[key]), e.code
            assert co.read() == before
        else:
            if key in seen:
                assert co.read() == before
            seen[key] = message
        assert control_view(co.read()) == baseline
        assert len(co.read()["completion"].get("terminal_event_id_index", {})) <= 256
        assert len(co.read()["completion"]["audit"]) <= 512


def new_legacy(completion, home):
    source = completion[0].read()
    work = []
    for row in source["work"].values():
        work.append(
            {
                k: copy.deepcopy(row[k])
                for k in (
                    "work_id",
                    "entity_id",
                    "handoff_id",
                    "role",
                    "session",
                    "depends_on",
                    "write_set",
                    "state",
                    "required",
                )
            }
        )
    return Coordinator.create(
        home,
        "stream-demo",
        OWNER,
        source["goal"],
        source["criteria"],
        work,
        coordinator_session=source["coordinator_session"],
    )


@pytest.mark.parametrize(
    "name",
    (
        "create",
        "activate_completion",
        "completion_verify_checkpoint",
        "completion_rehearse_restore",
    ),
)
@pytest.mark.parametrize("owner,lease,cancelled,revoked,replay", CORNERS)
def test_creation_activation_and_passive_matrix(
    completion, tmp_path, name, owner, lease, cancelled, revoked, replay
):
    co, _, contract, policy, _, workspace = completion
    if name in ("completion_verify_checkpoint", "completion_rehearse_restore"):
        src, paths, target = checkpoint_packet(co, workspace)
        ref = co.completion_checkpoint(
            OWNER, co.read()["revision"], NOW, src, paths, lambda *_: target
        )["checkpoint_ref"]
    s = co.read()
    c = s["completion"]
    c["policy"]["revoked"] = revoked
    if cancelled:
        c["state"] = "CANCELLED"
        s["parent_state"] = "cancelled"
        c["cancel_fence"] += 1
    if lease == "expired":
        c["lease_expires_at"] = NOW
    co._save(s)
    before = co.read()
    actor = OWNER if owner == "current" else "stale-owner-demo"
    if name == "activate_completion":
        fresh = new_legacy(completion, tmp_path / "legacy-home")
        old = fresh.read()
        if cancelled:
            old["parent_state"] = "cancelled"
            fresh._save(old)
        candidate = {
            **policy,
            "revoked": revoked,
            "expires_at": NOW if lease == "expired" else policy["expires_at"],
        }
        if owner == "stale" or cancelled:
            with pytest.raises(HandoffError):
                fresh.activate_completion(
                    actor, old["revision"], contract, candidate, NOW
                )
            assert fresh.read() == old
        else:
            # No ownership lease exists before activation. Staging a closed
            # policy never gives permission to execute it.
            fresh.activate_completion(actor, old["revision"], contract, candidate, NOW)
            frozen = fresh.read()
            with pytest.raises(HandoffError):
                fresh.activate_completion(
                    actor, old["revision"], contract, candidate, NOW
                )
            assert fresh.read() == frozen
    elif name == "create":
        fresh = new_legacy(completion, tmp_path / "new-home")
        old = fresh.read()
        with pytest.raises(HandoffError, match="DESTINATION_EXISTS"):
            new_legacy(completion, tmp_path / "new-home")
        assert fresh.read() == old
    elif name == "completion_verify_checkpoint":
        assert (
            co.completion_verify_checkpoint(ref)[0]["schema"]
            == "agentos.completion-checkpoint/v1"
        )
        if replay != "new":
            assert co.completion_verify_checkpoint(ref)[1]["completion"]["paused"]
        if replay == "conflicting":
            bad = {**ref, "size_bytes": ref["size_bytes"] + 1}
            with pytest.raises(HandoffError):
                co.completion_verify_checkpoint(bad)
    else:
        destination = tmp_path / "passive-rehearsal"
        co.completion_rehearse_restore(ref, destination)
        recovered = Coordinator(destination / ".agentos-recovery", "stream-demo").read()
        assert recovered["completion"]["paused"] and recovered["owner"] == OWNER
        if replay != "new":
            with pytest.raises(HandoffError, match="RESTORE_DESTINATION_EXISTS"):
                co.completion_rehearse_restore(ref, destination)
    assert co.read() == before


@pytest.mark.parametrize("name", MUTATORS)
@pytest.mark.parametrize(
    "owner,lease,cancelled,revoked",
    list(
        itertools.product(
            ("current", "stale"), ("live", "expired"), (False, True), (False, True)
        )
    ),
)
def test_same_operation_duplicate_uses_original_revision(
    completion, tmp_path, name, owner, lease, cancelled, revoked
):
    co, *_ = completion
    invoke = operation(completion, tmp_path, name)
    revision = co.read()["revision"]
    if name in LEGACY:
        with pytest.raises(HandoffError):
            invoke(OWNER, revision, NOW)
    else:
        result = invoke(OWNER, revision, NOW)
        if hasattr(result, "communicate"):
            result.communicate(timeout=5)
            assert result.returncode == 0
    s = co.read()
    c = s["completion"]
    if cancelled:
        c["state"] = "CANCELLED"
        c["cancel_fence"] += 1
        s["parent_state"] = "cancelled"
    if revoked:
        c["policy"]["revoked"] = True
    if lease == "expired":
        c["lease_expires_at"] = NOW
    co._save(s)
    after = co.read()
    actor = OWNER if owner == "current" else "stale-owner-demo"
    # These APIs have immutable evidence/event identities. Other commands
    # have no replay ID: reusing their consumed CAS revision must fail.
    if owner == "current" and (
        name
        in (
            "completion_event",
            "completion_ack",
            "completion_record_result",
            "completion_reconcile",
        )
        or (name == "completion_plan" and cancelled)
    ):
        invoke(actor, revision, NOW)
        assert co.read() == after
    else:
        with pytest.raises(HandoffError):
            invoke(actor, revision, NOW)
        assert co.read() == after


@pytest.mark.parametrize(
    "name", ("completion_ack", "completion_record_result", "completion_reconcile")
)
@pytest.mark.parametrize(
    "owner,lease,cancelled,revoked",
    list(
        itertools.product(
            ("current", "stale"), ("live", "expired"), (False, True), (False, True)
        )
    ),
)
def test_evidence_duplicate_and_conflict_matrix(
    completion, tmp_path, name, owner, lease, cancelled, revoked
):
    co, *_ = completion
    invoke = operation(completion, tmp_path, name)
    # Admit the exact evidence once while current. Replays are reads, not
    # new writes or lease renewal, including after terminal/revoked/expiry.
    invoke(OWNER, co.read()["revision"], NOW)
    s = co.read()
    c = s["completion"]
    if cancelled:
        c["state"] = "CANCELLED"
        s["parent_state"] = "cancelled"
        c["cancel_fence"] += 1
    if revoked:
        c["policy"]["revoked"] = True
    if lease == "expired":
        c["lease_expires_at"] = NOW
    co._save(s)
    before = co.read()
    actor = OWNER if owner == "current" else "stale-owner-demo"
    if owner == "current":
        invoke(actor, 0, NOW + 1)
    else:
        with pytest.raises(HandoffError):
            invoke(actor, 0, NOW + 1)
    assert co.read() == before
    store = co._completion_store()
    if name == "completion_ack":
        ref = c["handoff"]["ack_ref"]
        value = store.json(ref)
        bad = store.put_json({**value, "next_step": "conflicting next step"})
        conflict = lambda: co.completion_ack(actor, 0, bad, NOW + 1, lambda _: None)
    elif name == "completion_record_result":
        op = c["operations"][0]
        value = store.json(op["result_ref"])
        bad = store.put_json({**value, "tokens": value["tokens"] + 1})
        conflict = lambda: co.completion_record_result(
            actor, 0, op["identity"], bad, NOW + 1, lambda *_: True
        )
    else:
        op = c["operations"][0]
        value = store.json(op["reconciliation_ref"])
        bad = store.put_json({**value, "provider": "conflicting-provider"})
        conflict = lambda: co.completion_reconcile(
            actor, 0, op["operation_id"], NOW + 1, lambda _: bad
        )
    with pytest.raises(HandoffError):
        conflict()
    assert co.read() == before


def test_revoked_policy_cannot_be_resurrected_by_route(completion):
    co, runner, _, policy, caps, _ = completion
    co.completion_update_route(
        OWNER,
        co.read()["revision"],
        NOW,
        policy={**policy, "revision": 2, "revoked": True},
    )
    before = co.read()
    for kwargs in ({"policy": {**policy, "revision": 3}}, {"capabilities": caps}):
        with pytest.raises(HandoffError, match="POLICY_REAUTHORIZATION_REQUIRED"):
            co.completion_update_route(OWNER, before["revision"], NOW, **kwargs)
        assert co.read() == before
    assert runner.run(co, OWNER, NOW)["operation"] is None
    assert not co.read()["completion"]["operations"]


@pytest.mark.parametrize("result", (False, 0, 1, "", {}, []))
@pytest.mark.parametrize(
    "name",
    (
        "completion_change_contract",
        "completion_review",
        "completion_prepare_handoff",
        "completion_accept",
        "completion_takeover",
    ),
)
def test_contract_authority_explicit_rejection(completion, tmp_path, result, name):
    co, *_ = completion
    invoke = operation(completion, tmp_path, name, verifier=lambda *_: result)
    before = co.read()
    with pytest.raises(HandoffError):
        invoke(OWNER, before["revision"], NOW)
    assert co.read() == before


@pytest.mark.parametrize("field", ("work", "budget", "runtime", "acceptance", "policy"))
def test_audit_transaction_cannot_publish_execution_mutation(completion, field):
    co, *_ = completion
    before = co.read()
    with (
        pytest.raises(HandoffError, match="AUDIT_EXECUTION_MUTATION"),
        co._completion_transaction(OWNER, before["revision"], NOW, mode="audit") as (
            s,
            c,
        ),
    ):
        if field == "work":
            s["work"]["work-demo-001"]["state"] = "running"
        elif field == "budget":
            c["remaining_budget"]["steps"] -= 1
        elif field == "runtime":
            c["actual_runtime"] = {"model": "invented"}
        elif field == "acceptance":
            s["goal_acceptance"] = {"accepted": True}
        else:
            c["policy"]["revoked"] = True
    assert co.read() == before


@pytest.mark.parametrize("change", ("owner", "revision", "cancel", "lease"))
def test_checkpoint_rechecks_after_capture(completion, monkeypatch, change):
    co, *_, workspace = completion
    src, paths, target = checkpoint_packet(co, workspace)
    store_type = type(co._completion_store())
    original = store_type.put
    mutated = False

    def race(store, data, *args, **kwargs):
        nonlocal mutated
        result = original(store, data, *args, **kwargs)
        if not mutated and data == (src / paths[0]).read_bytes():
            mutated = True
            s = co.read()
            c = s["completion"]
            if change == "owner":
                s["owner"] = "successor-demo"
            elif change == "lease":
                c["lease_expires_at"] = NOW
            elif change == "cancel":
                c["state"] = "CANCELLED"
                s["parent_state"] = "cancelled"
                c["cancel_fence"] += 1
                s["revision"] += 1
            else:
                s["revision"] += 1
            co._save(s)
        return result

    monkeypatch.setattr(store_type, "put", race)
    with pytest.raises(HandoffError):
        co.completion_checkpoint(
            OWNER, co.read()["revision"], NOW, src, paths, lambda *_: target
        )
    assert mutated and co.read()["completion"]["paused"]


@pytest.mark.parametrize("owner,lease,cancelled,revoked,replay", CORNERS)
def test_terminal_cancellation_matrix(
    completion, owner, lease, cancelled, revoked, replay
):
    co, *_ = completion
    cancel = event(
        "USER_CANCELLED",
        event_id="cancel-matrix",
        payload={"reason": "owner cancelled", "source_ref": "owner-demo"},
    )
    if replay != "new":
        co.completion_event(OWNER, co.read()["revision"], cancel, NOW)
    s = co.read()
    c = s["completion"]
    c["policy"]["revoked"] = revoked
    if cancelled:
        c["state"] = "CANCELLED"
        s["parent_state"] = "cancelled"
        c["cancel_fence"] += 1
    if lease == "expired":
        c["lease_expires_at"] = NOW
    co._save(s)
    before = co.read()
    actor = OWNER if owner == "current" else "stale-owner-demo"
    message = cancel if replay != "conflicting" else {**cancel, "causal_sequence": 2}
    blocked = (
        owner == "stale"
        or replay == "conflicting"
        or (lease == "expired" and replay == "new")
    )
    if blocked:
        with pytest.raises(HandoffError):
            co.completion_event(actor, before["revision"], message, NOW)
        assert co.read() == before
    else:
        co.completion_event(actor, before["revision"], message, NOW)
        after = co.read()
        if replay == "duplicate":
            assert after == before
        else:
            assert after["completion"]["state"] == "CANCELLED"
            assert (
                after["completion"]["remaining_budget"]
                == before["completion"]["remaining_budget"]
            )
            assert after["completion"]["cancel_fence"] == before["completion"][
                "cancel_fence"
            ] + (not cancelled)


@pytest.mark.parametrize(
    "field",
    (
        "generation",
        "ownership_epoch",
        "cancel_fence",
        "policy_revision",
        "policy_scope",
        "policy_expiry",
    ),
)
def test_late_result_dependency_matrix_keeps_current_runtime_budget_and_work(
    completion, tmp_path, field
):
    co, *_ = completion
    invoke = operation(completion, tmp_path, "completion_record_result")
    s = co.read()
    c = s["completion"]
    if field in ("generation", "ownership_epoch", "cancel_fence"):
        c[field] += 1
    elif field == "policy_revision":
        c["policy"]["revision"] += 1
    elif field == "policy_scope":
        c["policy"]["scope"] = []
    else:
        c["policy"]["expires_at"] = NOW
    co._save(s)
    before = co.read()
    invoke(OWNER, before["revision"], NOW)
    after = co.read()
    assert co._completion_ledger_view(after) == co._completion_ledger_view(before)
    assert after["completion"]["operations"][0]["state"] == "COMPLETED"
    assert after["work"] == before["work"]


@pytest.mark.parametrize("seed", range(16))
def test_generated_mixed_revoke_cancel_ledger_interleavings(completion, tmp_path, seed):
    co, *_ = completion
    invoke = operation(completion, tmp_path, "completion_record_result")
    rng = random.Random(seed)
    cancelled = False
    applied = False
    baseline_steps = co.read()["completion"]["remaining_budget"]["steps"]
    for i in range(100):
        s = co.read()
        actor = OWNER if rng.randrange(5) else "stale-owner-demo"
        kind = rng.choice(("event", "cancel", "revoke", "heartbeat", "result", "wait"))
        if kind == "revoke" and not cancelled:
            policy = {
                **s["completion"]["policy"],
                "revision": s["completion"]["policy"]["revision"] + 1,
                "revoked": True,
            }
            call = lambda actor=actor, s=s, policy=policy: co.completion_update_route(
                actor, s["revision"], NOW, policy=policy
            )
        elif kind == "result":
            call = lambda actor=actor, applied=applied, s=s: invoke(
                actor, 0 if applied else s["revision"], NOW
            )
        elif kind == "heartbeat":
            call = lambda actor=actor, s=s: co.completion_heartbeat(
                actor, s["revision"], NOW
            )
        elif kind == "wait":
            call = lambda actor=actor, s=s: co.completion_wait(
                actor, s["revision"], NOW, waiting_user=True
            )
        else:
            message = event(
                "USER_CANCELLED" if kind == "cancel" else "TURN_FINISHED",
                event_id="mixed-" + str(i),
                payload={"reason": "cancel", "source_ref": "owner-demo"}
                if kind == "cancel"
                else None,
            )
            call = lambda actor=actor, s=s, message=message: co.completion_event(
                actor, s["revision"], message, NOW
            )
        try:
            call()
        except HandoffError:
            assert co.read() == s
        after = co.read()
        if actor != OWNER:
            assert after == s
        if cancelled and kind not in ("result",):
            assert control_view(after) == control_view(s)
        if kind == "result" and actor == OWNER:
            if applied:
                assert after == s
            elif s["completion"]["policy"]["revoked"] or cancelled:
                assert co._completion_ledger_view(after) == co._completion_ledger_view(
                    s
                )
            applied = after["completion"]["operations"][0]["result_ref"] is not None
        if after["completion"]["state"] == "CANCELLED":
            cancelled = True
        if cancelled:
            assert after["parent_state"] == "cancelled"
        assert after["completion"]["remaining_budget"]["steps"] == baseline_steps
        assert len(after["completion"]["operations"]) == 1
        assert len(after["completion"]["audit"]) <= 512
        assert len(after["completion"].get("terminal_event_id_index", {})) <= 256


@pytest.mark.parametrize("name", ("completion_checkpoint", "completion_restore"))
def test_accepted_recovery_cannot_change_acceptance(completion, tmp_path, name):
    co, *_ = completion
    invoke = operation(completion, tmp_path, name)
    s = co.read()
    s["completion"]["state"] = "ACCEPTED"
    s["parent_state"] = "completed"
    co._save(s)
    before = co.read()
    with pytest.raises(HandoffError, match="TERMINAL_TASK"):
        invoke(OWNER, before["revision"], NOW)
    assert co.read() == before


def test_late_ack_retention_capacity_preserves_duplicates_and_execution(
    completion, tmp_path
):
    co, *_ = completion
    invoke = operation(completion, tmp_path, "completion_ack")
    s = co.read()
    c = s["completion"]
    c["state"] = "CANCELLED"
    s["parent_state"] = "cancelled"
    c["cancel_fence"] += 1
    co._save(s)
    before = control_view(co.read())
    invoke(OWNER, co.read()["revision"], NOW)
    assert control_view(co.read()) == before
    s = co.read()
    c = s["completion"]
    key = next(iter(c["late_ack_refs"]))
    ref = c["late_ack_refs"][key]
    c["late_ack_refs"].update({"retained-" + str(i): ref for i in range(255)})
    co._save(s)
    full = co.read()
    invoke(OWNER, 0, NOW + 1)
    assert co.read() == full
    value = co._completion_store().json(ref)
    conflict = co._completion_store().put_json({**value, "next_step": "conflict"})
    with pytest.raises(HandoffError, match="ACK_CONFLICT"):
        co.completion_ack(OWNER, 0, conflict, NOW + 1, lambda _: None)
    assert co.read() == full
    # A new exact current handoff cannot evict any retained identity.
    s = co.read()
    s["completion"]["late_ack_refs"].pop(key)
    s["completion"]["late_ack_refs"]["replacement"] = ref
    co._save(s)
    full = co.read()
    with pytest.raises(HandoffError, match="LATE_ACK_INDEX_LIMIT"):
        invoke(OWNER, full["revision"], NOW)
    assert co.read() == full
