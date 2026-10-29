"""Explicit reviewed pre-resume disposition; never a failed-UNKNOWN reset."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time

from .safeio import create_only_bytes, digest, lock, within
from .screen_launch import LIMIT, worker_root
from .screen_reconciliation import HASH, SID, _ref, _absent, verify_pending_reconciliation
from .screen_successor import _journal
from .session_launch import LaunchError, validate_request

REVIEW_FLAGS = ("owner_exclusion_held", "old_and_provisional_lineage_absent", "execution_identity_and_trace_verified",
                "no_native_resume_probe_work_verified", "claim_absence_verified", "transport_effects_reviewed",
                "same_canonical_owner_continuation_verified", "historical_transfer_preserved_not_accepted")


def _query(plan):
    return {"phase": "review_pre_resume", "session_id": plan["session_id"], "plan_sha256": digest(plan),
            "replacement_request_sha256": digest(plan["replacement_request"]),
            "failed_adoption_sha256": plan["failed_adoption_sha256"],
            "no_native_evidence_sha256": plan["no_native_evidence"]["sha256"]}


def _review_bound(review, query, *, fresh):
    return (isinstance(review, dict) and all(review.get(k) == v for k, v in query.items()) and
            type(review.get("observed_at")) in (int, float) and math.isfinite(review["observed_at"]) and
            (not fresh or 0 <= time.time() - review["observed_at"] <= 60) and
            all(isinstance(review.get(k), str) and 1 <= len(review[k]) <= 2000 for k in
                ("owner_exclusion_token", "reviewer", "evidence_ref")) and
            all(review.get(k) is True for k in REVIEW_FLAGS))


def _fail(code: str) -> None:
    raise LaunchError("pre_resume_" + code, status="UNKNOWN")


def _paths(home: Path, sid: str, failed: str) -> tuple[Path, Path]:
    prefix = "state/screen-adoption-pre-resume/" + sid + "/" + failed
    return within(home, prefix + ".receipt.json"), within(home, prefix + ".attempt.json")


def _claim(home: Path, actor: dict) -> Path:
    if (not isinstance(actor, dict) or set(actor) != {"session_id", "turn_id", "task_id"} or
            any(not isinstance(x, str) or not 1 <= len(x) <= 200 for x in actor.values())):
        _fail("dispatch_binding_required")
    return within(home, "state/dispatch/" + digest([actor["session_id"], actor["turn_id"]]) + ".json")


def _snapshot(home: Path, plan: dict, *, claim_absent: bool, quiescent: bool) -> list[tuple[Path, str]]:
    if (not isinstance(plan, dict) or plan.get("schema") != "agentos.pre-resume-request/v1" or
            not isinstance(plan.get("session_id"), str) or not SID.fullmatch(plan["session_id"]) or
            not isinstance(plan.get("failed_adoption_sha256"), str) or not HASH.fullmatch(plan["failed_adoption_sha256"]) or
            not isinstance(plan.get("describe_operation_id"), str) or not SID.fullmatch(plan["describe_operation_id"])):
        _fail("plan_identity_invalid")
    sid, op = plan["session_id"], plan["describe_operation_id"]
    pins = []
    def read(path, expected):
        value = _ref(path, expected)
        pins.append((path, expected))
        return value
    failed = read(within(home, "state/screen-adoptions/" + sid + ".json"), plan["failed_adoption_sha256"])
    provisional = worker_root(home, plan.get("failed_worker_name", ""))
    proposed = worker_root(home, plan.get("replacement_name", ""))
    if proposed == provisional:
        _fail("fresh_destination_required")
    required = {"identity.json", "bootstrap.json", "state.json", "request.json", "responses/" + op + ".json"}
    worker_pins = plan.get("worker_pins")
    if not isinstance(worker_pins, dict) or set(worker_pins) != required:
        _fail("exact_describe_only_pins_required")
    records = {n: read(within(provisional, n), h) for n, h in worker_pins.items()}
    identity, boot, state, message, response = (records[n] for n in
        ("identity.json", "bootstrap.json", "state.json", "request.json", "responses/" + op + ".json"))
    request, replacement = boot.get("request"), plan.get("replacement_request")
    if not isinstance(request, dict) or not isinstance(request.get("transfer"), dict):
        _fail("selected_transfer_failure_required")
    validate_request(request)
    validate_request(replacement)
    expected = dict(request)
    expected.pop("transfer")
    expected["launch_id"] = replacement["launch_id"]
    if replacement["launch_id"] == request["launch_id"] or replacement != expected:
        _fail("replacement_scope_or_launch_changed")
    launch_path = within(home, "state/session-launch/" + digest(request["launch_id"]) + ".json")
    launch = read(launch_path, plan.get("failed_launch_sha256"))
    old_adoption = plan.get("failed_adoption")
    if (not isinstance(old_adoption, dict) or old_adoption.get("session_id") != sid or
            "successor" in old_adoption or "pre_resume_recovery" in old_adoption or "pre_resume_history" in old_adoption or
            digest(old_adoption) != failed.get("adoption_sha256")):
        _fail("original_adoption_not_bound")
    if plan["replacement_name"] == old_adoption.get("old_name"):
        _fail("fresh_destination_required")
    verify_pending_reconciliation(home, old_adoption)
    request_sha = digest(request)
    if (failed.get("schema") != "agentos.screen-adoption/v1" or failed.get("session_id") != sid or
            failed.get("status") != "RECONCILIATION_REQUIRED" or failed.get("resume_may_have_started") is not False or
            failed.get("work_accepted") is not False or failed.get("request_sha256") != request_sha or
            any(k in failed for k in ("before_resume", "before_dispatch", "result")) or
            launch.get("schema") != "agentos.session-launch-receipt/v1" or launch.get("phase") != "STOPPED" or
            launch.get("status") != "UNKNOWN" or launch.get("trace") != ["STOPPED"] or
            launch.get("error") != "transfer_reconciliation_not_bound" or
            launch.get("provider_mutation_started") is not False or launch.get("work_accepted") is not False or
            launch.get("request_sha256") != request_sha or launch.get("session_id") is not None or
            any(k in launch for k in ("startup", "probe", "work"))):
        _fail("not_proven_pre_resume")
    before = failed.get("before_transport", {})
    if (not isinstance(before, dict) or before.get("attempt_id") != launch.get("attempt_id") or before.get("request_sha256") != request_sha or
            before.get("adoption_sha256") != digest(old_adoption)):
        _fail("attempt_not_bound")
    payload = message.get("payload", {})
    if (not isinstance(payload, dict) or message.get("operation") != "describe_adoption" or message.get("id") != op or
            state.get("operation") != "describe_adoption" or state.get("operation_id") != op or
            state.get("status") != "READY" or "session_id" not in state or state["session_id"] is not None or
            payload.get("attempt") != launch.get("attempt_id") or payload.get("request") != request or
            payload.get("retained") != boot.get("adoption_retained_startup") or
            not isinstance(payload.get("retained"), dict) or payload["retained"].get("session_id") != sid or
            identity.get("bootstrap_sha256") != digest(boot) or state.get("bootstrap_sha256") != digest(boot) or
            identity.get("request_sha256") != request_sha or state.get("request_sha256") != request_sha or
            identity.get("name") != plan["failed_worker_name"] or state.get("name") != plan["failed_worker_name"] or
            state.get("screen_pid") != identity.get("screen_pid") or
            not isinstance(identity.get("worker_id"), str) or not identity["worker_id"] or
            any(x.get("worker_id") != identity["worker_id"] for x in (state, message, response)) or
            not isinstance(state.get("connection_id"), str) or not state["connection_id"] or
            any(x.get("connection_id") != state["connection_id"] for x in (message, response)) or
            response.get("id") != op or response.get("request_sha256") != digest(message) or response.get("error") or
            not isinstance(response.get("result"), dict) or response["result"] != launch.get("preflight")):
        _fail("describe_evidence_not_bound")
    if any((provisional / n).exists() or (provisional / n).is_symlink() for n in
           ("startup.json", "rejected-startup.json", "pending.json", "launch.json")):
        _fail("unexpected_provisional_effect")
    responses = within(provisional, "responses")
    # This narrow case has exactly one successful mailbox description. No
    # directory-wide historical reconstruction or inferred missing response.
    if {p.name for p in responses.iterdir()} != {op + ".json"}:
        _fail("mailbox_coverage_unknown")
    proof_ref = plan.get("no_native_evidence")
    if not isinstance(proof_ref, dict) or not isinstance(proof_ref.get("path"), str):
        _fail("independent_no_native_evidence_required")
    proof = read(Path(proof_ref["path"]), proof_ref.get("sha256"))
    actor = plan.get("dispatch_binding")
    claim = _claim(home, actor)
    code_pins = proof.get("execution_code_pins")
    if (proof.get("schema") != "agentos.pre-resume-evidence/v1" or proof.get("session_id") != sid or
            proof.get("attempt_id") != launch.get("attempt_id") or proof.get("request_sha256") != request_sha or
            proof.get("worker_id") != identity["worker_id"] or proof.get("connection_id") != state["connection_id"] or
            proof.get("coverage") != "COMPLETE" or proof.get("claim_state") != "ABSENT" or
            proof.get("claim_path") != str(claim) or proof.get("dispatch_binding_sha256") != digest(actor) or
            any(type(proof.get(k)) is not int or proof[k] != 0 for k in
                ("native_resume_count", "native_probe_count", "native_work_count")) or
            not isinstance(code_pins, dict) or not {"screen_launch.py", "codex_launch.py", "screen_adoption.py", "session_launch.py"} <= code_pins.keys() or
            any(not isinstance(h, str) or not HASH.fullmatch(h) for h in code_pins.values()) or
            not isinstance(proof.get("source_refs"), list) or not proof["source_refs"] or
            any(not isinstance(x, dict) or set(x) != {"ref", "sha256"} or
                not isinstance(x["ref"], str) or not 1 <= len(x["ref"]) <= 512 or
                not isinstance(x["sha256"], str) or not HASH.fullmatch(x["sha256"]) for x in proof["source_refs"])):
        _fail("no_native_or_claim_proof_incomplete")
    if claim_absent and (claim.exists() or claim.is_symlink()):
        _fail("old_claim_present")
    if quiescent:
        from .screen_adoption import _old_readback
        _old_readback(home, old_adoption)
        _absent({"old": provisional, "records": records})
    return pins


def reconcile_pre_resume(home: Path, plan: dict, *, owning_guard) -> dict:
    """Publish a reviewed no-native disposition, never stop a worker or retry.

    The actual trusted accessor must prove loaded execution identity, complete
    native trace, claim boundary, transport effects and current owning authority.
    Flags/null markers alone do not qualify. Both old lineages must be quiescent.
    """
    raw = json.dumps(plan, allow_nan=False).encode()
    if len(raw) > LIMIT:
        _fail("plan_limit")
    plan = json.loads(raw)
    selected_sha = digest(plan)
    _snapshot(home, plan, claim_absent=True, quiescent=True)
    sid = plan["session_id"]
    destination, attempt = _paths(home, sid, plan["failed_adoption_sha256"])
    if not callable(owning_guard):
        _fail("owning_guard_required")
    with lock(within(home, "state/screen-adoptions/" + sid + ".lock")):
        if destination.exists() or destination.is_symlink() or attempt.exists() or attempt.is_symlink():
            _fail("already_reviewed_or_attempted")
        with owning_guard(plan) as check:
            query = _query(plan)
            if not callable(check):
                _fail("owning_guard_required")
            review = check(dict(query))
            if digest(plan) != selected_sha or not _review_bound(review, query, fresh=True):
                _fail("owning_review_not_bound")
            _snapshot(home, plan, claim_absent=True, quiescent=True)
            receipt = {"schema": "agentos.pre-resume-reconciliation/v1", "status": "REVIEWED_PRE_RESUME_NO_NATIVE_WORK",
                       "plan": plan, "plan_sha256": selected_sha, "review": review,
                       "old_journals_preserved": True, "old_transfer_accepted": False, "replay_authorized": False}
            data = (json.dumps(receipt, sort_keys=True) + "\n").encode()
            if len(data) > LIMIT:
                _fail("receipt_limit")
            create_only_bytes(destination, data)
    return {"failed_adoption_sha256": plan["failed_adoption_sha256"], "receipt_sha256": hashlib.sha256(data).hexdigest()}


def _verified(home: Path, sid: str, ref: dict, *, current: bool) -> tuple[dict, list[tuple[Path, str]], Path]:
    if (not isinstance(sid, str) or not SID.fullmatch(sid) or not isinstance(ref, dict) or
            set(ref) != {"failed_adoption_sha256", "receipt_sha256"} or
            any(not isinstance(v, str) or not HASH.fullmatch(v) for v in ref.values())):
        _fail("reference_invalid")
    path, attempt = _paths(home, sid, ref["failed_adoption_sha256"])
    receipt = _ref(path, ref["receipt_sha256"])
    plan, review = receipt.get("plan"), receipt.get("review")
    if (receipt.get("schema") != "agentos.pre-resume-reconciliation/v1" or receipt.get("status") != "REVIEWED_PRE_RESUME_NO_NATIVE_WORK" or
            not isinstance(plan, dict) or plan.get("session_id") != sid or plan.get("failed_adoption_sha256") != ref["failed_adoption_sha256"] or
            digest(plan) != receipt.get("plan_sha256") or not isinstance(review, dict) or review.get("plan_sha256") != digest(plan) or
            receipt.get("old_journals_preserved") is not True or receipt.get("old_transfer_accepted") is not False or
            receipt.get("replay_authorized") is not False):
        _fail("receipt_not_bound")
    pins = _snapshot(home, plan, claim_absent=current, quiescent=current)
    if not _review_bound(review, _query(plan), fresh=False):
        _fail("receipt_review_not_bound")
    return receipt, [*pins, (path, ref["receipt_sha256"])], attempt


class PreResumeSelection:
    def __init__(self, home, plan, request, journal, binding, pins):
        self.home, self.plan = home, plan
        self.request = request
        self.journal, self.binding, self.pins = journal, binding, pins

    def verify(self):
        if digest(self.request) != self.binding["replacement_request_sha256"]:
            _fail("replacement_request_changed")
        _snapshot(self.home, self.plan, claim_absent=False, quiescent=True)
        for path, expected in self.pins:
            if _journal(path)[1] != expected:
                _fail("reviewed_source_changed")


def select_pre_resume(home: Path, name: str, request: dict, adoption: dict) -> PreResumeSelection:
    ref = adoption.get("pre_resume_recovery")
    receipt, pins, attempt = _verified(home, adoption["session_id"], ref, current=True)
    plan = receipt["plan"]
    original = {k: v for k, v in adoption.items() if k != "pre_resume_recovery"}
    if original != plan["failed_adoption"] or name != plan["replacement_name"] or request != plan["replacement_request"]:
        _fail("replacement_not_reviewed")
    if attempt.exists() or attempt.is_symlink():
        _fail("attempt_already_reserved")
    binding = {"failed_adoption_sha256": ref["failed_adoption_sha256"], "receipt_sha256": ref["receipt_sha256"],
               "replacement_request_sha256": digest(request), "destination_name": name}
    return PreResumeSelection(home, plan, request, attempt, binding, pins)


def history_root(home: Path, adoption: dict) -> tuple[Path, list[tuple[Path, str]]]:
    """Only an explicitly reviewed pre-resume history may precede success.

    No historical claim absence is asserted as current after a legitimate new
    dispatch claim. The ordinary current successor guard/claim gates still run.
    """
    receipt, pins, attempt = _verified(home, adoption["session_id"], adoption["pre_resume_history"], current=False)
    node, _ = _journal(attempt)
    expected = {"failed_adoption_sha256": receipt["plan"]["failed_adoption_sha256"],
                "receipt_sha256": adoption["pre_resume_history"]["receipt_sha256"],
                "replacement_request_sha256": digest(receipt["plan"]["replacement_request"]),
                "destination_name": receipt["plan"]["replacement_name"]}
    if node.get("pre_resume") != expected or node.get("request_sha256") != expected["replacement_request_sha256"]:
        _fail("historical_attempt_not_bound")
    return attempt, pins
