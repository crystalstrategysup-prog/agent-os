"""Receiver bytes, independent review, ownership and checkpoint regressions."""

from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest
from test_completion import NOW, OWNER, REVIEWER, event
from test_completion import completion as _completion_fixture

from agent_os.completion import DEPENDENCIES
from agent_os.handoff import verify_completion_inventory
from agent_os.handoff_store import HandoffError, encoded, sha
from agent_os.safeio import filemap

completion = _completion_fixture


def prepared_handoff(
    fixture, tmp_path, *, transition="KEEP_OWNER", receiver="receiver-demo-b"
):
    co, _, contract, *_ = fixture
    root = tmp_path / "transfer"
    root.mkdir()
    data = b"actual approved result bytes\n"
    (root / "result.txt").write_bytes(data)
    manifest = {
        "schema_version": "1.0.0",
        "task_id": contract["task_id"],
        "generation": co.read()["completion"]["generation"],
        "source_commit": contract["source_commit"],
        "contract_hash": contract["contract_hash"],
        "artifacts": [
            {"path": "result.txt", "size_bytes": len(data), "sha256": sha(data)}
        ],
        "integrity": "HASH_VERIFIED",
        "signature_ref": None,
    }
    envelope = {
        "schema": "agentos.completion-handoff/v1",
        "handoff_id": "handoff-demo-delivery",
        "operation_id": "operation-demo-transfer",
        "task_id": contract["task_id"],
        "generation": manifest["generation"],
        "from_ref": OWNER,
        "to_ref": receiver,
        "source_commit": contract["source_commit"],
        "contract_hash": contract["contract_hash"],
        "manifest": manifest,
        "manifest_hash": sha(encoded(manifest)),
        "remaining_requirements": [],
        "next_step": "Review captured results",
        "policy_scope_ref": "approved-demo-scope",
        "expiry": NOW + 100,
        "ownership_transition": transition,
        "sender_receipt": None,
        "authentication_mechanism": "selected-fixture-adapter",
        "target_environment": "receiver-demo-env",
    }
    co.completion_prepare_handoff(
        OWNER, co.read()["revision"], envelope, root, NOW, lambda *_: None
    )
    return root, envelope


def actual_ack(co, root, e):
    inventory = verify_completion_inventory(root, e["manifest"])
    ack = {
        "schema_version": "1.0.0",
        "purpose": "EXECUTION_HANDOFF",
        **{k: e[k] for k in ("handoff_id", "operation_id", "task_id", "generation")},
        "receiver_ref": e["to_ref"],
        "verified_commit": e["source_commit"],
        "commit_status": "VERIFIED",
        "verified_contract_hash": e["contract_hash"],
        "verified_manifest_hash": inventory["manifest_hash"],
        "received_artifact_hashes": inventory["artifact_hashes"],
        "accepted_scope": [e["policy_scope_ref"]],
        "next_step": e["next_step"],
        "actual_environment": e["target_environment"],
        "received_at": datetime.fromtimestamp(NOW, UTC).isoformat(),
        "status": "ACKED",
        "verification_method": "Independent actual-byte inventory and current checkout readback",
        "can_mutate": e["ownership_transition"] == "TRANSFER_OWNER",
    }

    def verifier(value):
        checked = verify_completion_inventory(root, e["manifest"])
        assert value["receiver_ref"] == e["to_ref"]
        return {
            "manifest_hash": checked["manifest_hash"],
            "artifact_hashes": checked["artifact_hashes"],
            "source_commit": e["source_commit"],
            "contract_hash": e["contract_hash"],
            "receiver_ref": e["to_ref"],
            "environment": e["target_environment"],
        }

    return ack, verifier


def reviewed_results(co, contract):
    store = co._completion_store()
    state = co.read()["completion"]
    refs = {k: v["receipt_ref"] for k, v in state["results"].items()}
    # Synthetic independent review reads each real bounded command output.
    captured = []
    for reference in refs.values():
        receipt = store.json(reference)
        assert receipt["status"] == "PASS" and receipt["exit_code"] == 0
        captured.extend(store.get(ref).decode() for ref in receipt["evidence_refs"])
    evidence = store.put_json({"reviewed_outputs": captured})
    review = {
        "schema": "agentos.completion-review/v1",
        "reviewer": REVIEWER,
        "generation": state["generation"],
        **{k: contract[k] for k in DEPENDENCIES},
        "result_refs": refs,
        "blocking_findings": [],
        "semantic_acceptance": True,
        "docs_consistent": True,
        "checked_at": NOW,
        "evidence_refs": [evidence],
    }
    reference = store.put_json(review)
    co.completion_review(
        OWNER,
        co.read()["revision"],
        reference,
        NOW,
        lambda value: value == review or (_ for _ in ()).throw(AssertionError()),
    )
    return reference


def test_end_to_end_three_real_steps_independent_review_receiver_bytes_acceptance(
    completion, tmp_path
):
    co, runner, contract, *_ = completion
    for _ in range(3):
        assert runner.run(co, OWNER, NOW)["status"] == "PASS"
    reviewed_results(co, contract)
    root, e = prepared_handoff(completion, tmp_path)
    ack, verifier = actual_ack(co, root, e)
    ref = co._completion_store().put_json(ack)
    with pytest.raises(HandoffError, match="HANDOFF_TRANSPORT_NOT_RECORDED"):
        co.completion_ack(OWNER, co.read()["revision"], ref, NOW, verifier)
    co.completion_handoff_sent(OWNER, co.read()["revision"], NOW)
    assert co.completion_status(NOW)["delivery_status"] == "NOT_DELIVERED"
    co.completion_ack(OWNER, co.read()["revision"], ref, NOW, verifier)
    co.completion_accept(OWNER, co.read()["revision"], NOW, lambda c: verifier(ack))
    assert co.completion_status(NOW)["project_state"] == "ACCEPTED"
    assert co.read()["parent_state"] == "completed"
    co.completion_event(OWNER, co.read()["revision"], event(seq=100), NOW + 1)
    assert co.completion_status(NOW + 1)["project_state"] == "ACCEPTED"
    assert runner.run(co, OWNER, NOW + 1)["operation"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("verified_commit", "f" * 40),
        ("verified_manifest_hash", "f" * 64),
        ("generation", 9),
        ("next_step", "a different next step"),
        ("actual_environment", "wrong-environment"),
        ("received_at", "2099-01-01T00:00:00+00:00"),
    ],
)
def test_stale_wrong_and_future_ack_never_delivers(completion, tmp_path, field, value):
    co, *_ = completion
    root, e = prepared_handoff(completion, tmp_path)
    ack, verifier = actual_ack(co, root, e)
    co.completion_handoff_sent(OWNER, co.read()["revision"], NOW)
    ref = co._completion_store().put_json({**ack, field: value})
    with pytest.raises(HandoffError):
        co.completion_ack(OWNER, co.read()["revision"], ref, NOW, verifier)
    assert co.completion_status(NOW)["delivery_status"] == "NOT_DELIVERED"


def test_cancel_before_late_ack_is_audit_only(completion, tmp_path):
    co, *_ = completion
    root, e = prepared_handoff(completion, tmp_path)
    ack, verifier = actual_ack(co, root, e)
    co.completion_handoff_sent(OWNER, co.read()["revision"], NOW)
    co.completion_event(
        OWNER,
        co.read()["revision"],
        event(
            "USER_CANCELLED",
            payload={"reason": "cancelled", "source_ref": "owner-demo-cancel"},
        ),
        NOW,
    )
    result = co.completion_ack(
        OWNER,
        co.read()["revision"],
        co._completion_store().put_json(ack),
        NOW,
        verifier,
    )
    assert result == {"status": "AUDIT_ONLY", "delivery_status": "NOT_DELIVERED"}
    assert co.completion_status(NOW)["project_state"] == "CANCELLED"


def test_ack_transfer_changes_owner_only_with_verified_fence_and_new_policy(
    completion, tmp_path
):
    co, _, _, policy, *_ = completion
    new_owner = "owner-demo-new"
    root, e = prepared_handoff(
        completion, tmp_path, transition="TRANSFER_OWNER", receiver=new_owner
    )
    ack, verifier = actual_ack(co, root, e)
    co.completion_handoff_sent(OWNER, co.read()["revision"], NOW)
    co.completion_ack(
        OWNER,
        co.read()["revision"],
        co._completion_store().put_json(ack),
        NOW,
        verifier,
    )
    assert co.read()["owner"] == OWNER
    assert co.completion_status(NOW)["delivery_status"] == "NOT_DELIVERED"
    assert co.completion_plan(OWNER, co.read()["revision"], NOW)["operation"] is None
    with pytest.raises(HandoffError, match="DISPATCH_HELD"):
        co.completion_begin_dispatch(OWNER, co.read()["revision"], "anything", NOW)
    s = co.read()["completion"]
    proof = {
        "schema": "agentos.completion-takeover/v1",
        "mode": "EFFECT_FENCED",
        "task_id": s["contract"]["task_id"],
        "previous_owner": OWNER,
        "new_owner": new_owner,
        "generation": s["generation"],
        "previous_epoch": s["ownership_epoch"],
        "policy_revision": policy["revision"],
        "checked_at": NOW,
        "evidence_refs": [co._completion_store().put(b"actual fixture fence readback")],
        "old_writer_quiescent": False,
        "reconciled_operation_ids": [],
        "receiver_fence_verified": True,
    }
    co.completion_takeover(
        new_owner,
        co.read()["revision"],
        NOW,
        co._completion_store().put_json(proof),
        lambda value: value == proof or (_ for _ in ()).throw(AssertionError()),
        {**policy, "actor": new_owner, "revision": 2},
    )
    assert (
        co.read()["owner"] == new_owner
        and co.read()["completion"]["ownership_epoch"] == 2
    )
    with pytest.raises(HandoffError):
        co.completion_takeover(
            new_owner,
            co.read()["revision"],
            NOW,
            co._completion_store().put_json(proof),
            lambda _: None,
            {**policy, "actor": new_owner, "revision": 3},
        )


@pytest.mark.parametrize(
    "name",
    ["/absolute", "../escape", "C:/drive", "\\UNC\\file", "nul\x00file", "a/../b"],
)
def test_transfer_rejects_unsafe_paths(completion, tmp_path, name):
    _, e = prepared_handoff(completion, tmp_path)
    invalid = copy.deepcopy(e["manifest"])
    invalid["artifacts"][0]["path"] = name
    with pytest.raises((HandoffError, ValueError)):
        verify_completion_inventory(tmp_path / "transfer", invalid)


def checkpoint_source(fixture):
    _co, _, contract, _, _, workspace = fixture
    (workspace / "source.py").write_text('print("original source")\n')
    (workspace / "notes.txt").write_text("actual untracked unfinished work\n")
    (workspace / "dirty.patch").write_text("synthetic tracked patch bytes\n")
    inventory = filemap(workspace)
    target = {
        "target_ref": "canary-demo",
        "environment": contract["environment_fingerprint"],
        "source_commit": contract["source_commit"],
        "branch": "branch-demo",
        "process_inventory": [],
        "ownership_verified": True,
        "source_manifest": {
            "schema": "agentos.completion-source-checkpoint/v1",
            "tracked_paths": ["source.py"],
            "untracked_paths": ["notes.txt"],
            "dirty_patch_path": "dirty.patch",
            "inventory_sha256": sha(encoded(inventory)),
        },
    }
    return workspace, list(inventory), target


def test_checkpoint_captures_untracked_patch_and_preserves_cancel_on_restore(
    completion, tmp_path
):
    co, *_ = completion
    workspace, paths, target = checkpoint_source(completion)
    checkpoint = co.completion_checkpoint(
        OWNER, co.read()["revision"], NOW, workspace, paths, lambda *_: target
    )
    dest = tmp_path / "restored"
    rehearsal = co.completion_rehearse_restore(checkpoint["checkpoint_ref"], dest)
    assert (dest / "notes.txt").read_bytes() == (workspace / "notes.txt").read_bytes()
    from agent_os.work_coordination import Coordinator

    recovered = Coordinator(dest / ".agentos-recovery", co.root.name)
    assert recovered.completion_verify_checkpoint(checkpoint["checkpoint_ref"])[0]
    co.completion_event(
        OWNER,
        co.read()["revision"],
        event(
            "USER_CANCELLED",
            payload={
                "reason": "cancel during backup",
                "source_ref": "owner-demo-cancel",
            },
        ),
        NOW,
    )
    proof = {k: target[k] for k in ("target_ref", "environment", "source_commit")}
    proof.update(
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
        checkpoint["checkpoint_ref"],
        co._completion_store().put_json(rehearsal),
        lambda *_: proof,
    )
    assert co.completion_status(NOW)["project_state"] == "CANCELLED"
    assert co.read()["completion"]["generation"] == 2


@pytest.mark.parametrize("paths_mode", ["empty", "omit_untracked"])
def test_checkpoint_rejects_empty_and_missing_actual_untracked(completion, paths_mode):
    co, *_ = completion
    workspace, paths, target = checkpoint_source(completion)
    bad = [] if paths_mode == "empty" else [n for n in paths if n != "notes.txt"]
    with pytest.raises(
        HandoffError, match="INVALID_CHECKPOINT_PATHS|INCOMPLETE_WORKSPACE_CHECKPOINT"
    ):
        co.completion_checkpoint(
            OWNER, co.read()["revision"], NOW, workspace, bad, lambda *_: target
        )


def test_unsupported_downgrade_is_no_write(completion):
    co, *_ = completion
    before = co.read()
    with pytest.raises(HandoffError, match="UNSUPPORTED_COMPLETION_DOWNGRADE"):
        co.completion_restore(
            OWNER,
            co.read()["revision"],
            NOW,
            {},
            {},
            lambda *_: None,
            target_schema="agentos.work-coordination/v1",
        )
    assert co.read() == before


@pytest.mark.parametrize("mutation", ["missing", "changed"])
def test_receiver_missing_or_changed_actual_bytes_cannot_ack(
    completion, tmp_path, mutation
):
    co, *_ = completion
    root, e = prepared_handoff(completion, tmp_path)
    ack, verifier = actual_ack(co, root, e)
    co.completion_handoff_sent(OWNER, co.read()["revision"], NOW)
    if mutation == "missing":
        (root / "result.txt").unlink()
    else:
        (root / "result.txt").write_bytes(b"substituted actual bytes")
    with pytest.raises((HandoffError, ValueError)):
        co.completion_ack(
            OWNER,
            co.read()["revision"],
            co._completion_store().put_json(ack),
            NOW,
            verifier,
        )
    assert co.completion_status(NOW)["delivery_status"] == "NOT_DELIVERED"


def test_receiver_read_only_cannot_accept_transfer_ownership(completion, tmp_path):
    co, *_ = completion
    root, e = prepared_handoff(
        completion, tmp_path, transition="TRANSFER_OWNER", receiver="owner-demo-new"
    )
    ack, verifier = actual_ack(co, root, e)
    co.completion_handoff_sent(OWNER, co.read()["revision"], NOW)
    with pytest.raises(HandoffError, match="RECEIVER_MUTATION_CAPABILITY_REQUIRED"):
        co.completion_ack(
            OWNER,
            co.read()["revision"],
            co._completion_store().put_json({**ack, "can_mutate": False}),
            NOW,
            verifier,
        )
    assert co.read()["owner"] == OWNER
