"""Synthetic pre-resume evidence and once recovery; no real native workers."""
import contextlib
import copy
import json
import os
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from agent_os.safeio import atomic_json, digest, GateError
from agent_os.screen_adoption import adopt_screen
from agent_os.screen_pre_resume import reconcile_pre_resume, select_pre_resume, history_root
from agent_os.screen_reconciliation import reconcile_pending
from agent_os.session_launch import LaunchError
from test_screen_launch import screen_fixture
from test_screen_reconciliation import prepared, Review, RecoveredGuard, pin, SID

DESCRIBE = "11111111-2222-3333-4444-555555555555"
ATTEMPT = "22222222-3333-4444-5555-666666666666"


def case(f):
    old, adoption, pending_plan = prepared(f)
    adoption["pending_reconciliation"] = reconcile_pending(f["home"], pending_plan, reconciliation_guard=Review())
    failed_request = copy.deepcopy(f["request"])
    failed_request["transfer"] = {"source_session": SID, "source_workspace": str(f["home"] / "historical-source"),
                                  "source_snapshot_sha256": "a" * 64, "target": failed_request["workspace"]}
    request_sha = digest(failed_request)
    retained = json.loads((old / "startup.json").read_text())
    boot = {"request": failed_request, "adoption_retained_startup": retained,
            "codex_binary": str(f["codex_binary"]), "codex_home": f["environment"].get("CODEX_HOME")}
    identity = {"worker_id": "failed-provisional-worker", "name": "failed-worker", "screen_pid": 2**30+10,
                "request_sha256": request_sha, "bootstrap_sha256": digest(boot)}
    state = {**identity, "status": "READY", "session_id": None, "worker_pid": 2**30+11,
             "connection_id": "provisional-connection", "operation": "describe_adoption", "operation_id": DESCRIBE}
    message = {"id": DESCRIBE, "worker_id": identity["worker_id"], "connection_id": state["connection_id"],
               "operation": "describe_adoption", "payload": {"request": failed_request, "retained": retained, "attempt": ATTEMPT}}
    preflight = {"connection_id": state["connection_id"], "attempt_id": ATTEMPT, "model_metadata_source": "retained_startup_candidate_only"}
    response = {"id": DESCRIBE, "worker_id": identity["worker_id"], "connection_id": state["connection_id"],
                "request_sha256": digest(message), "result": preflight}
    worker = f["home"] / "state/screen-workers/failed-worker"
    records = {"identity.json": identity, "bootstrap.json": boot, "state.json": state,
               "request.json": message, "responses/"+DESCRIBE+".json": response}
    for n, value in records.items():
        atomic_json(worker/n, value)
    root = f["home"] / "state/screen-adoptions" / (SID+".json")
    failed = {"schema": "agentos.screen-adoption/v1", "status": "RECONCILIATION_REQUIRED", "session_id": SID,
              "request_sha256": request_sha, "adoption_sha256": digest(adoption),
              "resume_may_have_started": False, "work_accepted": False,
              "before_transport": {"attempt_id": ATTEMPT, "request_sha256": request_sha, "adoption_sha256": digest(adoption)}}
    atomic_json(root, failed)
    launch_path = f["home"] / "state/session-launch" / (digest(failed_request["launch_id"])+".json")
    launch = {"schema": "agentos.session-launch-receipt/v1", "attempt_id": ATTEMPT, "request_sha256": request_sha,
              "status": "UNKNOWN", "phase": "STOPPED", "provider_mutation_started": False, "work_accepted": False,
              "error": "transfer_reconciliation_not_bound", "trace": ["STOPPED"], "preflight": preflight}
    atomic_json(launch_path, launch)
    actor = {"session_id": "fixture-controller", "turn_id": "failed-attempt-turn", "task_id": "fixture-task"}
    claim = f["home"] / "state/dispatch" / (digest([actor["session_id"], actor["turn_id"]])+".json")
    proof = {"schema": "agentos.pre-resume-evidence/v1", "session_id": SID, "attempt_id": ATTEMPT,
             "request_sha256": request_sha, "worker_id": identity["worker_id"], "connection_id": state["connection_id"],
             "coverage": "COMPLETE", "claim_state": "ABSENT", "claim_path": str(claim), "dispatch_binding_sha256": digest(actor),
             "native_resume_count": 0, "native_probe_count": 0, "native_work_count": 0,
             "execution_code_pins": {n: "b"*64 for n in ["screen_launch.py", "codex_launch.py", "screen_adoption.py", "session_launch.py"]},
             "source_refs": [{"ref": "synthetic-qualified-execution-trace", "sha256": "c"*64}]}
    proof_path = f["home"] / "evidence/no-native.json"; atomic_json(proof_path, proof)
    replacement = copy.deepcopy(f["request"]); replacement["launch_id"] = "fresh-replacement-launch"
    plan = {"schema": "agentos.pre-resume-request/v1", "session_id": SID, "failed_adoption_sha256": pin(root),
            "failed_launch_sha256": pin(launch_path), "failed_adoption": adoption, "failed_worker_name": "failed-worker",
            "describe_operation_id": DESCRIBE, "worker_pins": {n: pin(worker/n) for n in records},
            "no_native_evidence": {"path": str(proof_path), "sha256": pin(proof_path)}, "dispatch_binding": actor,
            "replacement_name": f["name"], "replacement_request": replacement}
    return plan, adoption, root, launch_path, worker, claim


class OwnerReview:
    def __init__(self, override=None, mutate=None):
        self.override, self.mutate = override or {}, mutate
    @contextlib.contextmanager
    def __call__(self, plan):
        def check(q):
            if self.mutate:
                self.mutate(plan)
            import time
            return {**q, "observed_at": time.time(), "owner_exclusion_token": "held-controller", "owner_exclusion_held": True,
                    "old_and_provisional_lineage_absent": True, "execution_identity_and_trace_verified": True,
                    "no_native_resume_probe_work_verified": True, "claim_absence_verified": True,
                    "transport_effects_reviewed": True, "same_canonical_owner_continuation_verified": True,
                    "historical_transfer_preserved_not_accepted": True, "reviewer": "fixture-root", "evidence_ref": "synthetic-current-review",
                    **self.override}
        yield check


class RecoveryGuard(RecoveredGuard):
    @contextlib.contextmanager
    def __call__(self, request, adoption):
        with super().__call__(request, adoption) as check:
            yield lambda q: {**check(q), "pre_resume_binding_sha256": digest(q["pre_resume_binding"]),
                             "pre_resume_no_native_effects_verified": True, "same_canonical_owner_continuation_verified": True,
                             "historical_transfer_preserved_not_accepted": True}


def test_reviewed_pre_resume_recovery_retains_failed_history_once(screen_fixture):
    f = screen_fixture
    plan, adoption, root, launch, worker, _ = case(f)
    originals = {p: p.read_bytes() for p in [root, launch, *worker.rglob("*.json")]}
    ref = reconcile_pre_resume(f["home"], plan, owning_guard=OwnerReview())
    current = dict(adoption, pre_resume_recovery=ref)
    selection = select_pre_resume(f["home"], f["name"], plan["replacement_request"], current)
    claims = []
    result = adopt_screen(**dict(f, request=plan["replacement_request"]), adoption=current,
                          adoption_guard=RecoveryGuard(adoption["pending_reconciliation"]), dispatch_claim=lambda: claims.append(True))
    assert result["session_id"] == SID and result["work"]["status"] == "completed" and claims == [True]
    assert all(p.read_bytes() == raw for p, raw in originals.items())
    assert json.loads(root.read_text())["status"] == "RECONCILIATION_REQUIRED"
    node = json.loads(selection.journal.read_text()); assert node["status"] == "DISPATCH_OBSERVED"
    history, pins = history_root(f["home"], {"session_id": SID, "pre_resume_history": ref})
    assert history == selection.journal and pins
    with pytest.raises(LaunchError, match="pre_resume_attempt_already_reserved"):
        select_pre_resume(f["home"], f["name"], plan["replacement_request"], current)


@pytest.mark.parametrize("kind", ["resume_flag", "provider_flag", "foreign_phase", "other_error", "different_status", "mutation_trace", "resume_mailbox", "native_count", "probe_count", "partial_trace", "missing_trace"])
def test_markers_or_unqualified_no_native_cases_refuse(screen_fixture, kind):
    f = screen_fixture
    plan, _, root, launch, worker, _ = case(f)
    if kind == "resume_flag":
        v=json.loads(root.read_text());v["resume_may_have_started"]=True;atomic_json(root,v);plan["failed_adoption_sha256"]=pin(root)
    elif kind in {"provider_flag","foreign_phase","other_error","different_status","mutation_trace"}:
        v=json.loads(launch.read_text());v.update({"provider_flag":{"provider_mutation_started":True},"foreign_phase":{"phase":"CREATING"},"other_error":{"error":"uncertain_provider_error"},"different_status":{"status":"UNAVAILABLE"},"mutation_trace":{"trace":["CREATING","STOPPED"]}}[kind]);atomic_json(launch,v);plan["failed_launch_sha256"]=pin(launch)
    elif kind == "resume_mailbox":
        p=worker/"state.json";v=json.loads(p.read_text());v["operation"]="resume";atomic_json(p,v);plan["worker_pins"]["state.json"]=pin(p)
    else:
        p=Path(plan["no_native_evidence"]["path"]);v=json.loads(p.read_text())
        v.update({"native_count":{"native_resume_count":1},"probe_count":{"native_probe_count":1},"partial_trace":{"coverage":"PARTIAL"},"missing_trace":{"source_refs":[]}}[kind]);atomic_json(p,v);plan["no_native_evidence"]["sha256"]=pin(p)
    with pytest.raises(LaunchError):
        reconcile_pre_resume(f["home"], plan, owning_guard=OwnerReview())


@pytest.mark.parametrize("kind", ["claim", "startup", "extra_response", "active_provisional", "provisional_lock"])
def test_actual_claim_or_provisional_effect_and_liveness_refuse(screen_fixture, kind):
    f = screen_fixture
    plan, _, _, _, worker, claim = case(f)
    if kind == "claim": atomic_json(claim,{"state":"CLAIMED_NOT_PROOF_OF_EXECUTION"})
    elif kind == "startup": atomic_json(worker/"startup.json",{"session_id":SID})
    elif kind == "extra_response": atomic_json(worker/"responses/foreign.json",{})
    elif kind == "provisional_lock": (worker/"worker.lock").mkdir()
    else:
        p=worker/"state.json";v=json.loads(p.read_text());v["worker_pid"]=os.getpid();atomic_json(p,v);plan["worker_pins"]["state.json"]=pin(p)
    with pytest.raises(LaunchError): reconcile_pre_resume(f["home"],plan,owning_guard=OwnerReview())


@pytest.mark.parametrize("override", [{"no_native_resume_probe_work_verified":False},{"claim_absence_verified":False},
                                       {"same_canonical_owner_continuation_verified":False},{"historical_transfer_preserved_not_accepted":False},
                                       {"execution_identity_and_trace_verified":False},{"plan_sha256":"a"*64}])
def test_fresh_bound_owning_review_required(screen_fixture, override):
    f=screen_fixture;plan,*_=case(f)
    with pytest.raises(LaunchError,match="pre_resume_owning_review_not_bound"):
        reconcile_pre_resume(f["home"],plan,owning_guard=OwnerReview(override))


@pytest.mark.parametrize("kind", ["same_launch", "widened_scope", "changed_model", "new_authority"])
def test_no_semantic_or_settings_transfer_bypass(screen_fixture, kind):
    f=screen_fixture;plan,*_=case(f)
    if kind=="same_launch": plan["replacement_request"]["launch_id"]=f["request"]["launch_id"]
    elif kind=="widened_scope": plan["replacement_request"]["scope"]="different scope"
    elif kind=="changed_model": plan["replacement_request"]["executor"]["approved_version"]="different"
    else: plan["replacement_request"]["authority"]="different authority"
    with pytest.raises(LaunchError): reconcile_pre_resume(f["home"],plan,owning_guard=OwnerReview())


def test_pinned_launch_changed_during_guard_refuses(screen_fixture):
    f=screen_fixture;plan,_,_,launch,*_=case(f)
    def mutate(_): atomic_json(launch,{"changed":True})
    with pytest.raises(LaunchError): reconcile_pre_resume(f["home"],plan,owning_guard=OwnerReview(mutate=mutate))


def test_receipt_not_a_generic_failed_retry_and_wrong_replacement_refuses(screen_fixture):
    f=screen_fixture;plan,adoption,*_=case(f)
    ref=reconcile_pre_resume(f["home"],plan,owning_guard=OwnerReview())
    with pytest.raises(LaunchError,match="pre_resume_already_reviewed_or_attempted"):
        reconcile_pre_resume(f["home"],plan,owning_guard=OwnerReview())
    with pytest.raises(LaunchError,match="pre_resume_replacement_not_reviewed"):
        select_pre_resume(f["home"],"another-name",plan["replacement_request"],dict(adoption,pre_resume_recovery=ref))


def test_incomplete_consumer_review_is_not_accepted_by_plan_hash_alone(screen_fixture):
    f=screen_fixture;plan,adoption,*_=case(f)
    ref=reconcile_pre_resume(f["home"],plan,owning_guard=OwnerReview())
    path=f["home"]/'state/screen-adoption-pre-resume'/SID/(ref['failed_adoption_sha256']+'.receipt.json')
    receipt=json.loads(path.read_text());receipt['review']={'plan_sha256':digest(plan)};atomic_json(path,receipt)
    forged=dict(ref,receipt_sha256=pin(path))
    with pytest.raises(LaunchError,match='pre_resume_receipt_review_not_bound'):
        select_pre_resume(f["home"],f["name"],plan['replacement_request'],dict(adoption,pre_resume_recovery=forged))


def test_replacement_request_pin_survives_owning_callback(screen_fixture):
    f=screen_fixture;plan,adoption,*_=case(f)
    ref=reconcile_pre_resume(f["home"],plan,owning_guard=OwnerReview())
    request=copy.deepcopy(plan['replacement_request'])
    class MutatingGuard(RecoveryGuard):
        @contextlib.contextmanager
        def __call__(self, supplied, bound):
            supplied['scope']='unreviewed scope'
            with super().__call__(supplied,bound) as check: yield check
    with pytest.raises(LaunchError,match='pre_resume_replacement_request_changed'):
        adopt_screen(**dict(f,request=request),adoption=dict(adoption,pre_resume_recovery=ref),
                     adoption_guard=MutatingGuard(adoption['pending_reconciliation']),dispatch_claim=lambda:pytest.fail('work'))
    assert not (f['home']/'state/screen-workers'/f['name']).exists()


def test_create_only_foreign_attempt_is_preserved(screen_fixture, monkeypatch):
    import agent_os.screen_adoption as core
    f=screen_fixture;plan,adoption,*_=case(f)
    ref=reconcile_pre_resume(f['home'],plan,owning_guard=OwnerReview())
    current=dict(adoption,pre_resume_recovery=ref)
    selection=select_pre_resume(f['home'],f['name'],plan['replacement_request'],current)
    original=core.create_only_bytes
    def raced(path,data):
        atomic_json(path,{'status':'foreign-existing-attempt'})
        return original(path,data)
    monkeypatch.setattr(core,'create_only_bytes',raced)
    with pytest.raises(LaunchError,match='pre_resume_attempt_already_reserved'):
        adopt_screen(**dict(f,request=plan['replacement_request']),adoption=current,
                     adoption_guard=RecoveryGuard(adoption['pending_reconciliation']),dispatch_claim=lambda:pytest.fail('work'))
    assert json.loads(selection.journal.read_text())=={'status':'foreign-existing-attempt'}
    assert not (f['home']/'state/screen-workers'/f['name']).exists()


def test_publication_uses_existing_sid_lock(screen_fixture):
    f=screen_fixture;plan,*_=case(f)
    entered,release=threading.Event(),threading.Event()
    def wait(_): entered.set();assert release.wait(5)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(reconcile_pre_resume,f["home"],plan,owning_guard=OwnerReview(mutate=wait))
        assert entered.wait(5)
        try:
            with pytest.raises(GateError,match="busy_or_stale_lock"):
                reconcile_pre_resume(f["home"],plan,owning_guard=OwnerReview())
        finally: release.set()
        assert future.result()["failed_adoption_sha256"]==plan["failed_adoption_sha256"]
