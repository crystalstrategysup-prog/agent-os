"""Independent P1/P2 adversarial regressions: synthetic local metadata only."""
from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

import pytest
from test_continuation_dispatch import accepted, closed, move, queued, rejected
from test_foundation import setup as foundation_setup

from agent_os import continuation as c
from agent_os import project as p
from agent_os.safeio import GateError, atomic_json, filemap, read_json

setup = foundation_setup


def unknown(setup):
    home = setup[1]
    return move(home, move(home, queued(setup), "claim"), "begin-delivery")


def retry(setup):
    first = unknown(setup)
    rejection = rejected(first, "rejected-first-send")
    second = move(setup[1], move(setup[1], first, "not-sent", rejection), "begin-delivery")
    return first, rejection, second


def refuses_unchanged(setup, item, action, receipt, match=None):
    before = filemap(setup[1])
    with pytest.raises(GateError, match=match):
        move(setup[1], item, action, receipt)
    assert filemap(setup[1]) == before
    assert c.read(setup[1], item["id"]) == item


@pytest.mark.parametrize("action", ["not-sent", "acknowledge"])
def test_old_generation_response_with_current_revision_cannot_reopen_unknown2(setup, action):
    first, rejection, second = retry(setup)
    receipt = rejection if action == "not-sent" else accepted(first)
    refuses_unchanged(setup, second, action, receipt, "identity_mismatch")
    refuses_unchanged(setup, second, "begin-delivery", None, "invalid_continuation_transition")
    assert second["attempt_id"] == first["attempt_id"]
    assert second["delivery_generation"] == 2
    assert second["delivery_nonce"] != first["delivery_nonce"]


def test_consumed_rejection_retagged_for_new_generation_is_still_replay(setup):
    _, receipt, second = retry(setup)
    receipt.update(delivery_generation=second["delivery_generation"],
                   delivery_nonce=second["delivery_nonce"], checked_at=datetime.now(UTC).isoformat())
    refuses_unchanged(setup, second, "not-sent", receipt, "already_consumed")


def test_new_rejection_permits_retry_but_preserves_operation_and_all_consumed_evidence(setup):
    first, _, second = retry(setup)
    third = move(setup[1], move(setup[1], second, "not-sent", rejected(second, "second-rejection")), "begin-delivery")
    assert third["attempt_id"] == first["attempt_id"]
    assert third["delivery_generation"] == 3
    assert len({first["delivery_nonce"], second["delivery_nonce"], third["delivery_nonce"]}) == 3
    assert len(third["receipt_history"]) == len(set(third["consumed_receipt_ids"])) == 2
    assert third["receipt"] is None and third["state"] == "DELIVERY_UNKNOWN"


def test_duplicate_rejection_does_not_consume_or_change_claimed_item(setup):
    item = unknown(setup)
    receipt = rejected(item)
    claimed = move(setup[1], item, "not-sent", receipt)
    refuses_unchanged(setup, claimed, "not-sent", receipt, "invalid_continuation_transition")


@pytest.mark.parametrize("response", ["duplicate-ack", "late-rejection", "old-revision-ack"])
def test_duplicate_and_reordered_responses_preserve_known_ack(setup, response):
    item = unknown(setup)
    receipt = accepted(item)
    acked = move(setup[1], item, "acknowledge", receipt)
    before = filemap(setup[1])
    action = "not-sent" if response == "late-rejection" else "acknowledge"
    stale_or_current = item if response == "old-revision-ack" else acked
    with pytest.raises(GateError):
        move(setup[1], stale_or_current, action, rejected(item) if action == "not-sent" else receipt)
    assert filemap(setup[1]) == before
    assert c.reconcile(setup[1], setup[0], item["identity"]["task_id"]) == acked


@pytest.mark.parametrize("field,value", [
    ("delivery_generation", True), ("delivery_generation", 0), ("delivery_generation", 2),
    ("delivery_nonce", "wrong-nonce"), ("schema", "agentos.continuation-delivery-receipt/v1"),
])
def test_unbound_receipt_cannot_record_outcome(setup, field, value):
    item = unknown(setup)
    receipt = accepted(item)
    receipt[field] = value
    refuses_unchanged(setup, item, "acknowledge", receipt)


def test_old_receipt_structure_is_not_upgraded_or_accepted(setup):
    item = unknown(setup)
    receipt = rejected(item)
    for key in ["schema", "delivery_generation", "delivery_nonce"]:
        receipt.pop(key)
    refuses_unchanged(setup, item, "not-sent", receipt, "invalid_continuation_delivery_receipt")


@pytest.mark.parametrize("case", ["malformed", "naive", "future", "before-start", "reverse", "equal", "after-check"])
def test_receipt_time_and_event_order_are_validated_before_mutation(setup, case):
    item = unknown(setup)
    receipt = accepted(item)
    if case == "malformed":
        receipt["checked_at"] = "not-a-timestamp"
    elif case == "naive":
        receipt["checked_at"] = "2026-10-01T00:00:00"
    elif case == "future":
        receipt["checked_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    elif case == "before-start":
        receipt["checked_at"] = (datetime.fromisoformat(item["delivery_started_at"]) - timedelta(seconds=1)).isoformat()
    elif case == "reverse":
        receipt["user_event_at"], receipt["later_activity_at"] = receipt["later_activity_at"], receipt["user_event_at"]
    elif case == "equal":
        receipt["later_activity_at"] = receipt["user_event_at"]
    else:
        receipt["later_activity_at"] = (datetime.fromisoformat(receipt["checked_at"]) + timedelta(seconds=1)).isoformat()
    refuses_unchanged(setup, item, "acknowledge", receipt)


def test_lost_begin_response_recovers_exact_generation_nonce_without_new_admission(setup, monkeypatch):
    home = setup[1]
    claimed = move(home, queued(setup), "claim")
    original = c.atomic_json

    def committed_response_lost(path, value):
        original(path, value)
        raise OSError("synthetic lost local response")

    monkeypatch.setattr(c, "atomic_json", committed_response_lost)
    with pytest.raises(OSError):
        move(home, claimed, "begin-delivery")
    monkeypatch.setattr(c, "atomic_json", original)
    item = c.read(home, claimed["id"])
    assert item["delivery_generation"] == 1 and len(item["delivery_nonce"]) == 32
    before = filemap(home)
    assert c.reconcile(home, setup[0], item["identity"]["task_id"]) == item
    assert filemap(home) == before
    refuses_unchanged(setup, item, "begin-delivery", None)


def age_checks(setup, item):
    task = p.load_task(setup[0], item["identity"]["task_id"])
    for rid in task["receipts"]:
        path = setup[0] / f".agentos/tasks/{task['id']}/evidence/{rid}.json"
        receipt = read_json(path)
        receipt["finished_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        atomic_json(path, receipt)


@pytest.mark.parametrize("stale", ["source", "aged-check"])
def test_existing_unknown_and_known_ack_recover_after_drift_without_stale_dispatch(setup, stale):
    item = unknown(setup)
    if stale == "source":
        (setup[0] / "code.py").write_text("unreviewed successor source\n")
    else:
        age_checks(setup, item)
    assert p.verify_closeout(setup[0], item["identity"]["task_id"])["status"] == "BLOCKED"
    before = filemap(setup[1])
    recovered = c.reconcile(setup[1], setup[0], item["identity"]["task_id"])
    assert recovered == item and filemap(setup[1]) == before
    assert c.status(setup[1])["dispatchable"] == []
    for action in ["claim", "begin-delivery"]:
        refuses_unchanged(setup, item, action, None, "stale")
    receipt = accepted(item)
    acked = move(setup[1], recovered, "acknowledge", receipt)
    before = filemap(setup[1])
    assert c.reconcile(setup[1], setup[0], item["identity"]["task_id"]) == acked
    assert filemap(setup[1]) == before
    assert acked["receipt"] == receipt


@pytest.mark.parametrize("stale", ["source", "aged-check"])
def test_recovery_does_not_admit_new_queue_item_from_stale_closeout(setup, stale):
    task = closed(setup)
    if stale == "source":
        (setup[0] / "code.py").write_text("new bytes\n")
    else:
        age_checks(setup, {"identity": {"task_id": task}})
    before = filemap(setup[1])
    with pytest.raises(GateError, match="stale"):
        c.reconcile(setup[1], setup[0], task)
    assert filemap(setup[1]) == before
    assert c.status(setup[1])["items"] == []


def test_reconcile_existing_stale_pending_is_read_only_but_dispatch_stays_blocked(setup):
    item = queued(setup)
    (setup[0] / "code.py").write_text("source drift\n")
    before = filemap(setup[1])
    assert c.reconcile(setup[1], setup[0], item["identity"]["task_id"]) == item
    assert filemap(setup[1]) == before and c.status(setup[1])["dispatchable"] == []
    refuses_unchanged(setup, item, "claim", None, "stale")


@pytest.mark.parametrize("state", ["DELIVERY_UNKNOWN", "ACKNOWLEDGED"])
def test_legacy_item_remains_readable_and_recoverable_without_guessed_delivery_binding(setup, state):
    item = unknown(setup)
    if state == "ACKNOWLEDGED":
        item = move(setup[1], item, "acknowledge", accepted(item))
    legacy = copy.deepcopy(item)
    legacy["schema"] = c.LEGACY_ITEM_SCHEMA
    for key in ["delivery_generation", "delivery_nonce", "delivery_started_at", "consumed_receipt_ids", "receipt_history"]:
        legacy.pop(key)
    if legacy["receipt"]:
        for key in ["schema", "delivery_generation", "delivery_nonce", "user_event_at", "later_activity_at"]:
            legacy["receipt"].pop(key)
    atomic_json(c._path(setup[1], legacy["id"]), legacy)
    (setup[0] / "code.py").write_text("subsequent source\n")
    before = filemap(setup[1])
    assert c.reconcile(setup[1], setup[0], item["identity"]["task_id"]) == legacy
    assert c.status(setup[1])["items"] == [legacy]
    refuses_unchanged(setup, legacy, "acknowledge", accepted(item), "legacy_delivery_binding")
    assert filemap(setup[1]) == before


@pytest.mark.parametrize("corruption", ["history-not-object", "consumed-not-string", "wrong-status", "future-generation"])
def test_malformed_history_fails_closed_with_controlled_error(setup, corruption):
    item = unknown(setup)
    item = move(setup[1], item, "not-sent", rejected(item))
    if corruption == "history-not-object":
        item["receipt_history"][0] = []
    elif corruption == "consumed-not-string":
        item["consumed_receipt_ids"][0] = []
    elif corruption == "wrong-status":
        item["receipt_history"][0]["status"] = "UNKNOWN"
    else:
        item["receipt_history"][0]["delivery_generation"] = 2
    atomic_json(c._path(setup[1], item["id"]), item)
    before = filemap(setup[1])
    with pytest.raises(GateError):
        c.read(setup[1], item["id"])
    assert filemap(setup[1]) == before


def test_cli_recovers_same_unknown_item_after_source_drift(setup):
    item = unknown(setup)
    (setup[0] / "code.py").write_text("successor bytes\n")
    before = filemap(setup[1])
    result, code = c.command(["reconcile", "--root", str(setup[0]), "--task", item["identity"]["task_id"]], setup[1])
    assert code == 0 and result == item and filemap(setup[1]) == before
    assert item["worker_started"] is False and item["external_authority_granted"] is False
