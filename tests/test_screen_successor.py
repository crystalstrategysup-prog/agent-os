"""Finite successor/legacy fixtures; no real native sessions or effects replay."""
import contextlib
import copy
import hashlib
import json
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_os.safeio import atomic_json, digest, GateError
from agent_os.screen_adoption import adopt_screen
from agent_os.screen_reconciliation import reconcile_pending
from agent_os.screen_successor import select_successor
from agent_os.session_launch import LaunchError
from test_screen_launch import screen_fixture
from test_screen_reconciliation import prepared, Review, RecoveredGuard, pin, SID, OP

PREVIOUS_OP = "87654321-4321-4321-4321-cba987654321"


def case(f):
    old, adoption, plan = prepared(f)
    identity = json.loads((old / "identity.json").read_text())
    identity["name"] = "old"
    atomic_json(old / "identity.json", identity)
    state = json.loads((old / "state.json").read_text())
    state.update(name="old", screen_pid=identity["screen_pid"], socket=str(identity["screen_pid"]) + ".old",
                 request_sha256=identity["request_sha256"], bootstrap_sha256=identity["bootstrap_sha256"])
    atomic_json(old / "state.json", state)
    for n in ("identity.json", "state.json"):
        plan["old_pins"][n] = adoption["old_pins"][n] = pin(old / n)
    ref = reconcile_pending(f["home"], plan, reconciliation_guard=Review())
    adoption["pending_reconciliation"] = ref
    previous_screen = dict(state, status="READY", operation_id=PREVIOUS_OP)
    row = {"schema": "agentos.screen-adoption/v1", "session_id": SID, "status": "DISPATCH_OBSERVED",
           "request_sha256": identity["request_sha256"], "adoption_sha256": "b" * 64,
           "result": {"phase": "DISPATCH_OBSERVED", "session_id": SID,
                      "request_sha256": identity["request_sha256"], "adoption_sha256": "b" * 64,
                      "screen": previous_screen, "startup": json.loads((old / "startup.json").read_text()),
                      "work": {"session_id": SID, "status": "completed", "turn_id": "previous-completed-turn",
                               "delivery": "accepted", "proof_source": "same_connection_provider_events"}}}
    journal = f["home"] / "state/screen-adoptions" / (SID + ".json")
    atomic_json(journal, row)
    adoption["successor"] = {"predecessor_sha256": pin(journal)}
    return old, adoption, journal


class SuccessorGuard(RecoveredGuard):
    def __init__(self, ref, mutate=None, **overrides):
        super().__init__(ref)
        self.mutate, self.overrides = mutate, overrides

    @contextlib.contextmanager
    def __call__(self, request, adoption):
        with super().__call__(request, adoption) as check:
            def observe(query):
                if self.mutate:
                    self.mutate(query)
                return {**check(query), "successor_binding_sha256": digest(query["successor_binding"]),
                        "predecessor_and_later_operation_reviewed": True, **self.overrides}
            yield observe


def test_reviewed_successor_keeps_originals_and_once(screen_fixture):
    f = screen_fixture
    old, adoption, root = case(f)
    originals = {p: p.read_bytes() for p in old.rglob("*") if p.is_file()}
    before = root.read_bytes()
    selection = select_successor(f["home"], f["name"], adoption)
    claims = []
    result = adopt_screen(**f, adoption=adoption, adoption_guard=SuccessorGuard(adoption["pending_reconciliation"]),
                          dispatch_claim=lambda: claims.append(True))
    assert result["session_id"] == SID and result["work"]["status"] == "completed"
    assert claims == [True] and root.read_bytes() == before
    assert all(p.read_bytes() == raw for p, raw in originals.items())
    child = json.loads(selection.journal.read_text())
    assert child["status"] == "DISPATCH_OBSERVED"
    assert child["successor"]["predecessor_sha256"] == hashlib.sha256(before).hexdigest()
    assert child["successor"]["later_operation_id"] == OP
    with pytest.raises(LaunchError, match="successor_predecessor_already_consumed"):
        adopt_screen(**dict(f, name="another-name"), adoption=adoption,
                     adoption_guard=SuccessorGuard(adoption["pending_reconciliation"]), dispatch_claim=lambda: pytest.fail("replay"))


@pytest.mark.parametrize("status", ["RESERVED", "RESUMING", "UNKNOWN", "RECONCILIATION_REQUIRED"])
def test_unknown_or_inflight_predecessor_refuses(screen_fixture, status):
    f = screen_fixture
    _, adoption, root = case(f)
    row = json.loads(root.read_text()); row["status"] = status; atomic_json(root, row)
    adoption["successor"]["predecessor_sha256"] = pin(root)
    with pytest.raises(LaunchError, match="successor_predecessor_not_successful"):
        select_successor(f["home"], f["name"], adoption)


@pytest.mark.parametrize("field,value", [("status", "failed"), ("delivery", "delivery_not_proven"),
                                         ("proof_source", "caller_assertion"), ("session_id", "foreign")])
def test_terminal_status_is_not_whole_predecessor_success(screen_fixture, field, value):
    f = screen_fixture
    _, adoption, root = case(f)
    row = json.loads(root.read_text()); row["result"]["work"][field] = value; atomic_json(root, row)
    adoption["successor"]["predecessor_sha256"] = pin(root)
    with pytest.raises(LaunchError, match="successor_predecessor_evidence_incomplete"):
        select_successor(f["home"], f["name"], adoption)


@pytest.mark.parametrize("kind", ["foreign_hash", "foreign_worker", "same_operation", "same_turn", "same_destination"])
def test_stale_foreign_and_non_later_selection_refuses(screen_fixture, kind):
    f = screen_fixture
    _, adoption, root = case(f)
    row = json.loads(root.read_text())
    if kind == "foreign_hash":
        adoption["successor"]["predecessor_sha256"] = "a" * 64
    elif kind == "foreign_worker":
        row["result"]["screen"]["worker_id"] = "another-worker"
    elif kind == "same_operation":
        row["result"]["screen"]["operation_id"] = OP
    elif kind == "same_turn":
        row["result"]["work"]["turn_id"] = "selected-terminal-turn"
    else:
        f["name"] = "old"
    if kind != "foreign_hash":
        atomic_json(root, row); adoption["successor"]["predecessor_sha256"] = pin(root)
    with pytest.raises(LaunchError):
        select_successor(f["home"], f["name"], adoption)


def test_legacy_existing_journal_does_not_implicitly_opt_in(screen_fixture):
    f = screen_fixture
    _, adoption, root = case(f)
    del adoption["successor"]
    before = root.read_bytes()
    with pytest.raises(LaunchError, match="adoption_sid_requires_reconciliation"):
        adopt_screen(**f, adoption=adoption, adoption_guard=RecoveredGuard(adoption["pending_reconciliation"]),
                     dispatch_claim=lambda: pytest.fail("work"))
    assert root.read_bytes() == before


@pytest.mark.parametrize("overrides", [{"predecessor_and_later_operation_reviewed": False},
                                       {"successor_binding_sha256": "a" * 64}])
def test_fresh_successor_review_required_and_failed_edge_preserved(screen_fixture, overrides):
    f = screen_fixture
    _, adoption, root = case(f)
    selection = select_successor(f["home"], f["name"], adoption)
    before = root.read_bytes()
    with pytest.raises(LaunchError, match="successor_live_review_not_bound"):
        adopt_screen(**f, adoption=adoption, adoption_guard=SuccessorGuard(adoption["pending_reconciliation"], **overrides),
                     dispatch_claim=lambda: pytest.fail("work"))
    assert json.loads(selection.journal.read_text())["status"] == "RECONCILIATION_REQUIRED"
    assert root.read_bytes() == before
    with pytest.raises(LaunchError, match="successor_predecessor_already_consumed"):
        select_successor(f["home"], "different-name", adoption)


def test_predecessor_changed_during_guard_refuses(screen_fixture):
    f = screen_fixture
    _, adoption, root = case(f)
    def mutate(_):
        row = json.loads(root.read_text()); row["raced"] = True; atomic_json(root, row)
    with pytest.raises(LaunchError, match="successor_predecessor_changed"):
        adopt_screen(**f, adoption=adoption, adoption_guard=SuccessorGuard(adoption["pending_reconciliation"], mutate=mutate),
                     dispatch_claim=lambda: pytest.fail("work"))
    assert not (f["home"] / "state/screen-workers" / f["name"]).exists()


def test_old_inflight_lock_refuses_before_successor_transport(screen_fixture):
    f = screen_fixture
    old, adoption, _ = case(f)
    (old / "worker.lock").mkdir()
    with pytest.raises(LaunchError, match="adoption_old_lock_requires_reconciliation"):
        adopt_screen(**f, adoption=adoption, adoption_guard=SuccessorGuard(adoption["pending_reconciliation"]),
                     dispatch_claim=lambda: pytest.fail("work"))


def test_successful_chain_leaf_can_be_selected_but_ancestor_is_stale(screen_fixture):
    f = screen_fixture
    _, adoption, root = case(f)
    leaf = json.loads(root.read_text())
    ancestor = copy.deepcopy(leaf)
    ancestor["result"]["screen"]["name"] = "ancestor-worker"
    ancestor["result"]["work"]["turn_id"] = "ancestor-turn"
    atomic_json(root, ancestor)
    ancestor_hash = pin(root)
    leaf.update(schema="agentos.screen-adoption-successor/v1",
                successor={"predecessor_sha256": ancestor_hash, "destination_name": "old"})
    path = f["home"] / "state/screen-adoption-successors" / SID / (ancestor_hash + ".json")
    atomic_json(path, leaf)
    adoption["successor"]["predecessor_sha256"] = pin(path)
    selection = select_successor(f["home"], f["name"], adoption)
    assert len(selection.pins) == 2
    adoption["successor"]["predecessor_sha256"] = ancestor_hash
    with pytest.raises(LaunchError, match="successor_predecessor_already_consumed"):
        select_successor(f["home"], f["name"], adoption)


def test_concurrent_successors_share_existing_sid_lock(screen_fixture):
    f = screen_fixture
    _, adoption, _ = case(f)
    entered, release = threading.Event(), threading.Event()
    def wait(_):
        entered.set(); assert release.wait(5)
    guard = SuccessorGuard(adoption["pending_reconciliation"], mutate=wait, predecessor_and_later_operation_reviewed=False)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(adopt_screen, **f, adoption=adoption, adoption_guard=guard, dispatch_claim=lambda: None)
        assert entered.wait(5)
        try:
            with pytest.raises(GateError, match="busy_or_stale_lock"):
                adopt_screen(**dict(f, name="competitor"), adoption=adoption,
                             adoption_guard=SuccessorGuard(adoption["pending_reconciliation"]), dispatch_claim=lambda: None)
        finally:
            release.set()
        with pytest.raises(LaunchError, match="successor_live_review_not_bound"):
            future.result()
