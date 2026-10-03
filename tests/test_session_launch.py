"""Deterministic provider-neutral contract tests; no provider or host calls."""
from __future__ import annotations

import copy

import pytest

from agent_os.safeio import GateError, digest, read_json
from agent_os.session_launch import LaunchError, LaunchJournal, launch, validate_request


def request(tmp_path):
    return {"schema": "agentos.session-launch/v1", "launch_id": "fixture-launch",
            "original_goal": "Compare fixture prices per kilogram.", "scope": "isolated fixture files",
            "authority": "owner fixture preparation only", "workspace": str(tmp_path),
            "acceptance": ["Prices retain the accepted comparison unit."],
            "context": {"accepted_answers": {"comparison_unit": "kg"}, "docs": ["fixture-contract#sha256"], "results": []},
            "autonomous_ordinary_work": True, "required_capabilities": ["filesystem_read"],
            "executor": {"id": "fixture-local", "provider": "fixture", "owner_approved_ref": "fixture-owner-choice"},
            "target_gates": []}


class Provider:
    def __init__(self):
        self.trace = []
        self.before = {}
        self.after = {}
        self.proof = {}
        self.envelope = None

    def metadata(self, req, attempt, source):
        return {"source": source, "attempt_id": attempt, "observed_at": 100,
                "executor_id": req["executor"]["id"], "provider": req["executor"]["provider"],
                "connection_id": "fixture-current-connection", "workspace": req["workspace"],
                "sandbox": "fixture-write-sandbox", "approval_policy": "fixture-noninteractive",
                "ordinary_commands": "noninteractive", "capabilities": {c: True for c in req["required_capabilities"]}}

    def describe(self, req, attempt):
        self.trace.append("describe")
        return self.metadata(req, attempt, "provider_effective") | self.before

    def create(self, req, attempt):
        self.trace.append("create")
        return self.metadata(req, attempt, "provider_startup") | {"session_id": "fixture-new-session"} | self.after

    def probe(self, req, startup, attempt):
        self.trace.append("probe")
        return {"source": "provider_tool_evidence", "attempt_id": attempt, "session_id": startup["session_id"],
                "turn_id": "fixture-probe-turn", "status": "PASS", "capabilities": req["required_capabilities"],
                "proofs": [{"capability": c, "status": "PASS", "evidence_ref": "fixture-tool-item"} for c in req["required_capabilities"]]} | self.proof

    def dispatch(self, req, startup, envelope):
        self.trace.append("dispatch")
        self.envelope = envelope
        return {"status": "completed", "semantic_acceptance": "NOT_EVALUATED"}


def run(req, provider, **kwargs):
    return launch(req, provider, dispatch_claim=lambda: provider.trace.append("claim"), clock=lambda: 100, **kwargs)


def test_compatible_order_retained_goal_context_and_unaccepted_work(tmp_path):
    req, provider = request(tmp_path), Provider()
    receipt = run(req, provider)
    assert provider.trace == ["describe", "create", "probe", "claim", "dispatch"]
    assert receipt["trace"] == ["ADMITTED_FOR_STARTUP_ONLY", "CREATING", "STARTUP_READBACK_VERIFIED", "RUNNABLE", "DISPATCHING", "DISPATCH_OBSERVED"]
    assert provider.envelope.startswith(req["original_goal"])
    assert all(text in provider.envelope for text in ("comparison_unit", '"kg"', req["authority"], req["acceptance"][0]))
    assert receipt["work_accepted"] is False


@pytest.mark.parametrize("change,code,status", [
    ({"ordinary_commands": "interactive"}, "ordinary_commands_require_interactive_approval", "MISMATCH"),
    ({"approval_policy": None}, "effective_metadata_missing:approval_policy", "UNKNOWN"),
    ({"approval_policy": "UNKNOWN"}, "effective_metadata_missing:approval_policy", "UNKNOWN"),
    ({"source": "copied_config"}, "copied_or_unbound_metadata", "UNKNOWN"),
    ({"observed_at": 1}, "stale_effective_metadata", "UNKNOWN"),
    ({"attempt_id": "old-attempt"}, "copied_or_unbound_metadata", "UNKNOWN"),
    ({"capabilities": {"filesystem_read": False}}, "insufficient_capability:filesystem_read", "MISMATCH"),
    ({"capabilities": {}}, "capability_metadata_unknown:filesystem_read", "UNKNOWN"),
])
def test_known_mismatch_and_unknown_metadata_stop_before_create(tmp_path, change, code, status):
    provider = Provider()
    provider.before = change
    with pytest.raises(LaunchError) as caught:
        run(request(tmp_path), provider)
    assert caught.value.code == code and caught.value.status == status
    assert provider.trace == ["describe"]
    assert caught.value.receipt["provider_mutation_started"] is False


def test_local_or_durable_label_cannot_supply_missing_policy(tmp_path):
    for label in ("local", "durable", "cloud"):
        req, provider = request(tmp_path), Provider()
        req["executor"]["kind"] = label
        provider.before = {"approval_policy": None}
        with pytest.raises(LaunchError, match="UNKNOWN"):
            run(req, provider)
        assert provider.trace == ["describe"]


@pytest.mark.parametrize("change,code", [
    ({"sandbox": "different"}, "startup_changed:sandbox"),
    ({"connection_id": "another"}, "startup_changed:connection_id"),
    ({"approval_policy": None}, "effective_metadata_missing:approval_policy"),
])
def test_effective_startup_mismatch_blocks_probe_and_task(tmp_path, change, code):
    provider = Provider()
    provider.after = change
    with pytest.raises(LaunchError) as caught:
        run(request(tmp_path), provider)
    assert caught.value.code == code
    assert provider.trace == ["describe", "create"]


@pytest.mark.parametrize("change", [{"source": "agent_ack"}, {"status": "FAIL"}, {"proofs": []}, {"session_id": "other"}])
def test_ack_failure_or_unbound_probe_never_dispatches(tmp_path, change):
    provider = Provider()
    provider.proof = change
    with pytest.raises(LaunchError):
        run(request(tmp_path), provider)
    assert provider.trace == ["describe", "create", "probe"]


def guard_for(req, *, deny_phase=None, changes=None):
    def guard(bound, phase):
        attempt = bound.pop("_launch_attempt_id")
        assert bound == req
        state = {"source": "target_readback", "attempt_id": attempt, "observed_at": 100,
                 "request_sha256": digest(bound), "phase": phase,
                 "gates": {g: {"status": "DENY" if phase == deny_phase else "PASS", "evidence_ref": "fixture-target-receipt"} for g in req["target_gates"]}}
        if req.get("transfer"):
            transfer = req["transfer"]
            state["transfer"] = {"source_session": transfer["source_session"], "source_workspace": transfer["source_workspace"],
                                 "old_writer": "fenced_and_reconciled", "fence_evidence_ref": "fixture-fence",
                                 "isolated_workspace": req["workspace"], "isolated_snapshot_sha256": transfer["source_snapshot_sha256"],
                                 "isolation_evidence_ref": "fixture-isolation", "lease_holder": req["launch_id"],
                                 "lease_target": transfer["target"], "lease_scope_sha256": digest([req["scope"], req["authority"]]),
                                 "lease_status": "held", "lease_evidence_ref": "fixture-lease"} | (changes or {})
        return state
    return guard


@pytest.mark.parametrize("gate", ["security", "financial", "authentication", "destructive", "database", "production"])
def test_independent_target_gate_rechecked_after_probe(tmp_path, gate):
    req, provider = request(tmp_path), Provider()
    req["target_gates"] = [gate]
    with pytest.raises(LaunchError, match="target_gate_unsatisfied:" + gate):
        run(req, provider, target_guard=guard_for(req, deny_phase="before_dispatch"))
    assert provider.trace == ["describe", "create", "probe"]


def transfer_request(tmp_path):
    req = request(tmp_path / "destination")
    req["transfer"] = {"source_session": "fixture-old", "source_workspace": str(tmp_path / "source"),
                       "source_snapshot_sha256": "a" * 64, "target": "fixture-protected-target"}
    return req


def test_transfer_preserves_goal_fencing_isolation_and_lease(tmp_path):
    req, provider = transfer_request(tmp_path), Provider()
    run(req, provider, target_guard=guard_for(req))
    assert '"source_session": "fixture-old"' in provider.envelope
    assert req["original_goal"] in provider.envelope
    assert provider.trace[-1] == "dispatch"


@pytest.mark.parametrize("changes,code", [
    ({"old_writer": "inProgress"}, "old_writer_reconciliation_required"),
    ({"fence_evidence_ref": None}, "old_writer_reconciliation_required"),
    ({"isolated_snapshot_sha256": "b" * 64}, "source_isolation_not_verified"),
    ({"isolated_workspace": "/elsewhere"}, "source_isolation_not_verified"),
    ({"lease_status": "closed"}, "destination_lease_required"),
    ({"lease_holder": "old-writer"}, "destination_lease_required"),
    ({"lease_target": "wrong-target"}, "destination_lease_required"),
])
def test_transfer_negative_conditions_stop_before_create(tmp_path, changes, code):
    req, provider = transfer_request(tmp_path), Provider()
    with pytest.raises(LaunchError, match=code):
        run(req, provider, target_guard=guard_for(req, changes=changes))
    assert provider.trace == ["describe"]


def test_transfer_symlink_alias_and_traversal_are_not_isolation(tmp_path):
    req = transfer_request(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    (tmp_path / "alias").symlink_to(source, target_is_directory=True)
    for destination in (str(tmp_path / "alias"), str(source / "child" / "..")):
        req["workspace"] = destination
        with pytest.raises(LaunchError, match="source_must_be_disjoint"):
            validate_request(req)


def test_journal_rejects_retry_after_unknown_create_outcome(tmp_path):
    req, provider = request(tmp_path), Provider()
    journal = LaunchJournal(tmp_path / "agentos", req["launch_id"])
    def timeout(*args):
        provider.trace.append("create")
        raise TimeoutError("fixture-timeout-after-provider-receipt")
    provider.create = timeout
    with pytest.raises(LaunchError, match="provider_io_unresolved"):
        run(req, provider, journal=journal)
    persisted = read_json(journal.path)
    assert persisted["phase"] == "OUTCOME_REQUIRES_RECONCILIATION"
    with pytest.raises(LaunchError, match="previous_launch_requires_reconciliation"):
        run(req, provider, journal=journal)
    assert provider.trace == ["describe", "create"]


def test_gate_claim_failure_never_dispatches_and_is_persisted(tmp_path):
    req, provider = request(tmp_path), Provider()
    def denied():
        raise GateError("existing_gate_denied")
    with pytest.raises(LaunchError, match="independent_dispatch_gate_refused"):
        launch(req, provider, dispatch_claim=denied, clock=lambda: 100)
    assert provider.trace == ["describe", "create", "probe"]


@pytest.mark.parametrize("change", [{"acceptance": [{}]}, {"original_goal": ""}, {"context": {"x": "x" * 65000}}])
def test_invalid_or_unbounded_task_contract_never_reaches_provider(tmp_path, change):
    req, provider = request(tmp_path) | change, Provider()
    with pytest.raises(LaunchError):
        run(req, provider)
    assert provider.trace == []
