"""Selected pending recovery fixtures; synthetic accessors, no real sessions."""
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_os.safeio import atomic_json, digest, GateError
from agent_os.screen_adoption import adopt_screen, _old_readback
from agent_os.screen_reconciliation import reconcile_pending, verify_pending_reconciliation
from agent_os.session_launch import LaunchError
from test_screen_adoption import Guard, configure_adoption, old_registry, SID
from test_screen_launch import screen_fixture

OP = "12345678-1234-1234-1234-123456789abc"
TURN = "selected-terminal-turn"


def pin(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepared(f):
    configure_adoption(f)
    old, adoption = old_registry(f)
    original = json.loads((old / "bootstrap.json").read_text())
    startup = json.loads((old / "startup.json").read_text())
    identity = json.loads((old / "identity.json").read_text())
    identity.update(request_sha256=digest(original['request']), bootstrap_sha256=digest(original))
    state = json.loads((old / "state.json").read_text())
    state.update(status="FAILED", connection_id=startup["connection_id"],
                 operation="dispatch", operation_id=OP)
    message = {"id": OP, "operation": "dispatch", "worker_id": identity["worker_id"],
               "connection_id": state["connection_id"], "payload": {
                   "request": original["request"], "startup": startup, "envelope": "exact original task"}}
    records = {"identity.json": identity, "state.json": state, "request.json": message,
               "pending.json": {"operation_id": OP, "operation": "dispatch", "status": "PENDING",
                                "request_sha256": digest(message)},
               "responses/" + OP + ".json": {"id": OP, "worker_id": identity["worker_id"],
                   "connection_id": state["connection_id"], "request_sha256": digest(message),
                   "status": "UNKNOWN", "error": "bounded_turn_evidence_exceeded"}}
    for name, value in records.items():
        atomic_json(old / name, value)
    names = set(records) | set(adoption["old_pins"])
    adoption["old_pins"] = {n: pin(old / n) for n in names}
    common = {"session_id": SID, "turn_id": TURN, "operation_id": OP,
              "envelope_sha256": digest(message["payload"]["envelope"])}
    evidence = {}
    values = {"terminal": {"status": "completed", "source_verified": True},
              "commands": {"coverage": "COMPLETE", "commands": [
                  {"id": "cmd-1", "command_sha256": "a" * 64, "exit_code": 0}]},
              "effects": {"coverage": "COMPLETE", "commands": [
                  {"id": "cmd-1", "disposition": "OBSERVED", "scope": "own selected source writes",
                   "evidence_refs": ["synthetic-own-result-proof"]}]}}
    for kind, value in values.items():
        path = f["home"] / "evidence" / (kind + ".json")
        atomic_json(path, {**common, **value, "schema": "agentos.screen-" + kind + "-evidence/v1"})
        evidence[kind] = {"path": str(path), "sha256": pin(path)}
    plan = {"schema": "agentos.screen-reconciliation-request/v1", "old_name": "old",
            "session_id": SID, "operation_id": OP, "turn_id": TURN,
            "old_pins": copy.deepcopy(adoption["old_pins"]), "evidence": evidence}
    return old, adoption, plan


class Review:
    def __init__(self, mutate=None, override=None):
        self.mutate, self.override = mutate, override or {}
        self.calls = 0

    @contextlib.contextmanager
    def __call__(self, plan):
        def check(query):
            self.calls += 1
            if self.mutate:
                self.mutate(plan)
            return {**query, "observed_at": time.time(), "owner_exclusion_held": True,
                    "owner_exclusion_token": "synthetic-held-owner", "source_writer_state": "FREE",
                    "old_owned_lineage_absent": True, "native_evidence_verified": True,
                    "command_effects_reviewed": True, "reviewed_plan_sha256": query["plan_sha256"],
                    "reviewer": "independent-fixture-reviewer", **self.override}
        yield check


class RecoveredGuard(Guard):
    def __init__(self, ref, **overrides):
        super().__init__()
        self.ref, self.overrides = ref, overrides

    @contextlib.contextmanager
    def __call__(self, request, adoption):
        with super().__call__(request, adoption) as check:
            yield lambda query: {**check(query), "terminal_turn_id": TURN,
                                 "pending_reconciliation_sha256": self.ref["receipt_sha256"],
                                 **self.overrides}


def old_bytes(old):
    return {str(p.relative_to(old)): p.read_bytes() for p in old.rglob("*") if p.is_file()}


def test_reconciliation_guarded_same_sid_and_no_original_replay(screen_fixture):
    f = screen_fixture
    old, adoption, plan = prepared(f)
    before = old_bytes(old)
    with pytest.raises(LaunchError, match="adoption_pending_requires_reconciliation"):
        _old_readback(f["home"], adoption)
    ref = reconcile_pending(f["home"], plan, reconciliation_guard=Review())
    adoption["pending_reconciliation"] = ref
    receipt = verify_pending_reconciliation(f["home"], adoption)
    assert receipt["original_status"] == "UNKNOWN" and receipt["business_accepted"] is False
    assert receipt["replay_authorized"] is False
    claims = []
    result = adopt_screen(**f, adoption=adoption, adoption_guard=RecoveredGuard(ref),
                          dispatch_claim=lambda: claims.append(True))
    assert result["startup"]["session_id"] == SID
    assert len(claims) == 1
    assert old_bytes(old) == before  # includes original pending/FAILED/error/old request
    with pytest.raises(LaunchError, match="adoption_sid_requires_reconciliation"):
        adopt_screen(**f, adoption=adoption, adoption_guard=RecoveredGuard(ref), dispatch_claim=lambda: None)
    with pytest.raises(LaunchError, match="reconciliation_already_recorded"):
        reconcile_pending(f["home"], plan, reconciliation_guard=Review())


@pytest.mark.parametrize("kind,field,value", [
    ("terminal", "turn_id", "foreign"), ("terminal", "session_id", "foreign"),
    ("terminal", "operation_id", "foreign"), ("terminal", "envelope_sha256", "b" * 64),
    ("terminal", "status", "running"), ("terminal", "source_verified", False),
    ("commands", "coverage", "PARTIAL"), ("effects", "commands", []),
    ("effects", "commands", [{"id": [], "disposition": "OBSERVED", "scope": "scope", "evidence_refs": ["ref"]}]),
    ("effects", "commands", [{"id": "cmd-1", "disposition": [], "scope": "scope", "evidence_refs": ["ref"]}]),
    ("effects", "coverage", "UNKNOWN")])
def test_wrong_or_incomplete_native_evidence_refused(screen_fixture, kind, field, value):
    f = screen_fixture
    old, _, plan = prepared(f)
    ref = plan["evidence"][kind]
    path = Path(ref["path"])
    data = json.loads(path.read_text()); data[field] = value; atomic_json(path, data)
    ref["sha256"] = pin(path)
    before = old_bytes(old)
    review = Review()
    with pytest.raises(LaunchError):
        reconcile_pending(f["home"], plan, reconciliation_guard=review)
    assert review.calls == 0 and old_bytes(old) == before


@pytest.mark.parametrize("override", [
    {"owner_exclusion_held": False}, {"source_writer_state": "BUSY"},
    {"old_owned_lineage_absent": False}, {"native_evidence_verified": False},
    {"command_effects_reviewed": False}, {"reviewed_plan_sha256": "b" * 64},
    {"observed_at": 0}, {"terminal_turn_id": "foreign"}])
def test_unqualified_owner_review_refuses(screen_fixture, override):
    f = screen_fixture
    old, _, plan = prepared(f)
    before = old_bytes(old)
    with pytest.raises(LaunchError, match="reconciliation_live_evidence_review_required"):
        reconcile_pending(f["home"], plan, reconciliation_guard=Review(override=override))
    assert old_bytes(old) == before


@pytest.mark.parametrize("name", ["pending.json", "request.json", "state.json"])
def test_original_changed_during_review_cannot_publish(screen_fixture, name):
    f = screen_fixture
    old, _, plan = prepared(f)
    def mutate(_):
        path = old / name
        data = json.loads(path.read_text()); data["raced"] = True; atomic_json(path, data)
    with pytest.raises(LaunchError, match="reconciliation_evidence_changed"):
        reconcile_pending(f["home"], plan, reconciliation_guard=Review(mutate=mutate))
    assert not list((f["home"] / "state/screen-reconciliations").rglob("*.json"))


def test_changed_effect_evidence_and_mutated_plan_refuse(screen_fixture):
    f = screen_fixture
    _, _, plan = prepared(f)
    def mutate(value):
        value["turn_id"] = "changed"
    with pytest.raises(LaunchError, match="reconciliation_plan_changed"):
        reconcile_pending(f["home"], plan, reconciliation_guard=Review(mutate=mutate))
    def mutate_effects(value):
        Path(value["evidence"]["effects"]["path"]).write_text('{}')
    with pytest.raises(LaunchError, match="reconciliation_evidence_changed"):
        reconcile_pending(f["home"], plan, reconciliation_guard=Review(mutate=mutate_effects))


def test_receipt_and_live_binding_are_required(screen_fixture):
    f = screen_fixture
    old, adoption, plan = prepared(f)
    ref = reconcile_pending(f["home"], plan, reconciliation_guard=Review())
    adoption["pending_reconciliation"] = dict(ref, receipt_sha256="b" * 64)
    with pytest.raises(LaunchError, match="reconciliation_evidence_changed"):
        _old_readback(f["home"], adoption)
    adoption["pending_reconciliation"] = ref
    with pytest.raises(LaunchError, match="adoption_live_reconciliation_not_bound"):
        adopt_screen(**f, adoption=adoption, adoption_guard=RecoveredGuard(ref,
            pending_reconciliation_sha256="b" * 64), dispatch_claim=lambda: pytest.fail("work"))
    assert (old / "pending.json").exists()


def test_stale_receipt_refuses_without_relabeling_pending(screen_fixture):
    f = screen_fixture
    old, adoption, plan = prepared(f)
    adoption["pending_reconciliation"] = reconcile_pending(f["home"], plan, reconciliation_guard=Review())
    path = old / "pending.json"
    data = json.loads(path.read_text()); data["operation_id"] = "changed"; atomic_json(path, data)
    with pytest.raises(LaunchError):
        verify_pending_reconciliation(f["home"], adoption)
    assert json.loads(path.read_text())["status"] == "PENDING"


@pytest.mark.parametrize("changes", [
    {"operation": "__MISSING__"}, {"operation_id": "__MISSING__"},
    {"operation": None}, {"operation_id": None},
    {"operation": []}, {"operation_id": []},
    {"operation": {}}, {"operation_id": {}},
    {"operation": ""}, {"operation_id": ""},
    {"operation": "describe"}, {"operation_id": "malformed"},
    {"operation_id": "87654321-4321-4321-4321-cba987654321"},
    {"operation": "describe", "operation_id": "87654321-4321-4321-4321-cba987654321"},
])
def test_state_operation_must_bind_selected_dispatch(screen_fixture, changes):
    f = screen_fixture
    old, _, plan = prepared(f)
    path = old / "state.json"
    state = json.loads(path.read_text())
    for field, value in changes.items():
        if value == "__MISSING__":
            state.pop(field)
        else:
            state[field] = value
    atomic_json(path, state)
    plan["old_pins"]["state.json"] = pin(path)
    before = old_bytes(old)
    review = Review()
    with pytest.raises(LaunchError, match="reconciliation_state_operation_not_bound") as failure:
        reconcile_pending(f["home"], plan, reconciliation_guard=review)
    assert failure.value.status == "UNKNOWN"
    assert review.calls == 0 and old_bytes(old) == before
    assert not (f["home"] / "state/screen-reconciliations").exists()


def test_live_old_pid_refuses_before_owner_review(screen_fixture):
    f = screen_fixture
    old, _, plan = prepared(f)
    path = old / "state.json"
    data = json.loads(path.read_text()); data["worker_pid"] = os.getpid(); atomic_json(path, data)
    plan["old_pins"]["state.json"] = pin(path)
    with pytest.raises(LaunchError, match="reconciliation_old_writer_present"):
        reconcile_pending(f["home"], plan, reconciliation_guard=Review())


def test_oversized_plan_refused_before_any_receipt(screen_fixture):
    f = screen_fixture
    _, _, plan = prepared(f)
    plan["unbounded"] = "x" * (128 * 1024)
    with pytest.raises(LaunchError, match="reconciliation_plan_limit"):
        reconcile_pending(f["home"], plan, reconciliation_guard=Review())
    assert not (f["home"] / "state/screen-reconciliations").exists()


def test_concurrent_publication_has_one_owner(screen_fixture):
    f = screen_fixture
    _, _, plan = prepared(f)
    entered, release = threading.Event(), threading.Event()
    def wait(_):
        entered.set()
        assert release.wait(5)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(reconcile_pending, f["home"], plan, reconciliation_guard=Review(mutate=wait))
        assert entered.wait(5)
        try:
            with pytest.raises(GateError, match="busy_or_stale_lock"):
                reconcile_pending(f["home"], plan, reconciliation_guard=Review())
        finally:
            release.set()
        assert future.result()["operation_id"] == OP
