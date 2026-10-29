"""Reviewed late harmless probe disposition; never transfers capability proof."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time

from .safeio import create_only_bytes, digest, lock, within
from .screen_launch import LIMIT, worker_root
from .screen_reconciliation import HASH, SID, _ref, _absent
from .screen_successor import _journal, _edge, _successful
from .screen_pre_resume import _claim
from .session_launch import LaunchError, validate_request

FLAGS = ("owner_exclusion_held", "both_owned_lineages_absent", "native_evidence_verified",
         "complete_probe_effects_and_cleanup_reviewed", "no_work_or_claim_verified",
         "same_sid_continuation_authorized", "current_target_security_verified")


def _fail(code):
    raise LaunchError("late_probe_" + code, status="UNKNOWN")


def _paths(home, sid, failed):
    prefix = "state/screen-adoption-late-probe/" + sid + "/" + failed
    return within(home, prefix + ".receipt.json"), within(home, prefix + ".attempt.json")


def _query(plan):
    return {"phase": "review_late_probe", "session_id": plan["session_id"], "plan_sha256": digest(plan),
            "failed_adoption_sha256": plan["failed_adoption_sha256"],
            "replacement_request_sha256": digest(plan["replacement_request"]),
            "probe_evidence_sha256": plan["probe_evidence"]["sha256"]}


def _review_bound(record, query, *, fresh):
    return (isinstance(record, dict) and all(record.get(k) == v for k, v in query.items()) and
            type(record.get("observed_at")) in (int, float) and math.isfinite(record["observed_at"]) and
            (not fresh or 0 <= time.time() - record["observed_at"] <= 60) and
            all(isinstance(record.get(k), str) and 1 <= len(record[k]) <= 2000 for k in
                ("owner_exclusion_token", "reviewer", "evidence_ref")) and
            all(record.get(k) is True for k in FLAGS))


def _tip(home, plan):
    """Resolve canonical successful ancestry; an input path never chooses a tip."""
    sid = plan["session_id"]
    path = within(home, "state/screen-adoptions/" + sid + ".json")
    original = plan["failed_adoption"]
    pins = []
    if "pre_resume_recovery" in original or "pre_resume_history" in original:
        from .screen_pre_resume import history_root
        ref = original.get("pre_resume_recovery", original.get("pre_resume_history"))
        path, pins = history_root(home, {"session_id": sid, "pre_resume_history": ref})
    if "late_probe_recovery" in original or "late_probe_history" in original:
        _fail("nested_recovery_not_supported")
    for _ in range(32):
        row, sha = _journal(path); pins.append((path, sha))
        child = _edge(home, sid, sha)
        if sha == plan["failed_adoption_sha256"]:
            if child.exists() or child.is_symlink():
                _fail("failed_tip_already_consumed")
            return row, pins
        _successful(row, sid)  # UNKNOWN predecessors never become traversable.
        if not child.exists():
            _fail("failed_tip_not_current")
        link, _ = _journal(child)
        if (link.get("schema") != "agentos.screen-adoption-successor/v1" or
                not isinstance(link.get("successor"), dict) or link["successor"].get("predecessor_sha256") != sha):
            _fail("ancestry_not_bound")
        path = child
    _fail("ancestry_limit")


def _snapshot(home, plan, *, current):
    if (not isinstance(plan, dict) or plan.get("schema") != "agentos.late-probe-request/v1" or
            not isinstance(plan.get("session_id"), str) or not SID.fullmatch(plan["session_id"]) or
            not isinstance(plan.get("operation_id"), str) or not SID.fullmatch(plan["operation_id"]) or
            not isinstance(plan.get("turn_id"), str) or not 1 <= len(plan["turn_id"]) <= 200 or
            not isinstance(plan.get("failed_adoption_sha256"), str) or not HASH.fullmatch(plan["failed_adoption_sha256"]) or
            not isinstance(plan.get("failed_adoption"), dict)):
        _fail("plan_identity_invalid")
    sid, op = plan["session_id"], plan["operation_id"]
    failed, pins = _tip(home, plan)
    original = plan["failed_adoption"]
    if original.get("session_id") != sid or failed.get("adoption_sha256") != digest(original):
        _fail("original_adoption_not_bound")
    old = worker_root(home, plan.get("failed_worker_name", ""))
    proposed = worker_root(home, plan.get("replacement_name", ""))
    if proposed == old or plan["replacement_name"] == original.get("old_name"):
        _fail("fresh_destination_required")
    required = {"identity.json", "bootstrap.json", "startup.json", "state.json", "pending.json", "request.json", "responses/" + op + ".json"}
    supplied = plan.get("worker_pins")
    if not isinstance(supplied, dict) or set(supplied) != required:
        _fail("exact_worker_pins_required")
    total = 0
    def read(path, sha):
        nonlocal total
        value = _ref(path, sha); pins.append((path, sha)); total += path.stat().st_size
        if total > 4 * LIMIT: _fail("input_limit")
        return value
    records = {n: read(within(old, n), h) for n, h in supplied.items()}
    identity, boot, startup, state, pending, message, response = (records[n] for n in
        ("identity.json", "bootstrap.json", "startup.json", "state.json", "pending.json", "request.json", "responses/" + op + ".json"))
    request, replacement = boot.get("request"), plan.get("replacement_request")
    validate_request(request); validate_request(replacement)
    contract = {k: request.get(k) for k in ("original_goal", "scope", "acceptance", "context", "authority")}
    expected = dict(request, launch_id=replacement["launch_id"], context=dict(request["context"], adopted_original_contract=contract))
    if "probe_budget_seconds" in replacement: expected["probe_budget_seconds"] = replacement["probe_budget_seconds"]
    if replacement["launch_id"] == request["launch_id"] or replacement != expected:
        _fail("replacement_scope_changed")
    launch = read(within(home, "state/session-launch/" + digest(request["launch_id"]) + ".json"), plan.get("failed_launch_sha256"))
    attempt = launch.get("attempt_id")
    payload = message.get("payload")
    if not isinstance(payload, dict): _fail("probe_mailbox_not_bound")
    if (identity.get("name") != plan["failed_worker_name"] or identity.get("bootstrap_sha256") != digest(boot) or
            identity.get("request_sha256") != digest(request) or state.get("bootstrap_sha256") != digest(boot) or
            state.get("request_sha256") != digest(request) or state.get("name") != identity["name"] or
            state.get("screen_pid") != identity.get("screen_pid") or
            not isinstance(identity.get("worker_id"), str) or not identity["worker_id"] or
            any(r.get("worker_id") != identity["worker_id"] for r in (state, message, response)) or
            not isinstance(state.get("connection_id"), str) or not state["connection_id"] or
            any(r.get("connection_id") != state["connection_id"] for r in (message, response, startup)) or
            state.get("status") != "FAILED" or state.get("session_id") != sid or startup.get("session_id") != sid or
            state.get("operation") != "probe" or state.get("operation_id") != op or
            message.get("operation") != "probe" or message.get("id") != op or
            pending.get("operation") != "probe" or pending.get("operation_id") != op or pending.get("status") != "PENDING" or
            pending.get("request_sha256") != digest(message) or response.get("id") != op or
            response.get("request_sha256") != digest(message) or response.get("status") != "UNKNOWN" or
            response.get("error") != "screen_provider_TimeoutError" or "result" in response or
            payload.get("request") != request or payload.get("startup") != startup or payload.get("attempt") != attempt or
            not isinstance(attempt, str) or not SID.fullmatch(attempt) or startup.get("attempt_id") != attempt):
        _fail("probe_mailbox_not_bound")
    trace = ["ADMITTED_FOR_STARTUP_ONLY", "CREATING", "STARTUP_READBACK_VERIFIED", "STOPPED"]
    if (failed.get("schema") not in {"agentos.screen-adoption/v1", "agentos.screen-adoption-successor/v1"} or
            launch.get("schema") != "agentos.session-launch-receipt/v1" or launch.get("phase") != "STOPPED" or
            launch.get("status") != "UNKNOWN" or launch.get("trace") != trace or
            launch.get("error") != response["error"] or launch.get("provider_mutation_started") is not True or
            launch.get("work_accepted") is not False or launch.get("request_sha256") != digest(request) or
            launch.get("session_id") != sid or launch.get("startup") != startup or
            any(k in launch for k in ("probe", "work")) or
            failed.get("status") != "RECONCILIATION_REQUIRED" or failed.get("session_id") != sid or
            failed.get("resume_may_have_started") is not True or failed.get("work_accepted") is not False or
            failed.get("request_sha256") != digest(request) or any(k in failed for k in ("before_dispatch", "result"))):
        _fail("not_pre_work_probe_timeout")
    before = failed.get("before_resume")
    if (not isinstance(before, dict) or before.get("attempt_id") != attempt or
            before.get("request_sha256") != digest(request) or before.get("adoption_sha256") != digest(original) or
            not isinstance(before.get("new_worker"), dict) or
            any(before["new_worker"].get(k) != state.get(k) for k in
                ("worker_id", "connection_id", "name", "screen_pid", "worker_pid", "bootstrap_sha256", "request_sha256"))):
        _fail("resume_lineage_not_bound")
    if failed.get("schema") == "agentos.screen-adoption-successor/v1":
        link = failed.get("successor")
        if not isinstance(link, dict) or link.get("destination_name") != identity["name"]:
            _fail("failed_destination_not_bound")
    ref = plan.get("probe_evidence")
    if not isinstance(ref, dict) or not isinstance(ref.get("path"), str): _fail("probe_evidence_required")
    proof = read(Path(ref["path"]), ref.get("sha256"))
    actor = plan.get("dispatch_binding"); claim = _claim(home, actor)
    if (proof.get("schema") != "agentos.late-probe-evidence/v1" or proof.get("session_id") != sid or
            proof.get("operation_id") != op or proof.get("turn_id") != plan["turn_id"] or proof.get("attempt_id") != attempt or
            proof.get("worker_id") != identity["worker_id"] or proof.get("connection_id") != state["connection_id"] or
            proof.get("request_sha256") != digest(request) or proof.get("native_status") != "completed" or
            proof.get("coverage") != "COMPLETE" or proof.get("cleanup_complete") is not True or
            type(proof.get("native_work_count")) is not int or proof["native_work_count"] != 0 or
            proof.get("claim_state") != "ABSENT" or proof.get("claim_path") != str(claim) or proof.get("dispatch_binding_sha256") != digest(actor)):
        _fail("probe_effects_incomplete")
    # Intentionally only the exact harmless filesystem read/write probes. No
    # network probe or arbitrary completed command can unlock this boundary.
    if set(request["required_capabilities"]) != {"filesystem_read", "filesystem_write"}:
        _fail("probe_capabilities_unsupported")
    from .codex_launch import _commands, _command_script
    commands = _commands(request, attempt)
    items = proof.get("commands")
    if not isinstance(items, list) or len(items) != 2: _fail("command_coverage_incomplete")
    seen, ids = set(), set()
    for item in items:
        if not isinstance(item, dict): _fail("command_not_bound")
        script = _command_script(item.get("command"))
        cap = next((c for c, (cmd, _) in commands.items() if script == cmd), None)
        if (cap is None or cap in seen or not isinstance(item.get("id"), str) or not item["id"] or item["id"] in ids or
                item.get("cwd") != request["workspace"] or item.get("status") != "completed" or
                type(item.get("exit_code")) is not int or item["exit_code"] != 0 or item.get("output_truncated") is not False or
                item.get("output") != commands[cap][1] + "\n"):
            _fail("command_not_bound")
        seen.add(cap); ids.add(item["id"])
    sources = proof.get("source_refs"); codes = proof.get("execution_code_pins")
    if (not isinstance(sources, list) or not 1 <= len(sources) <= 32 or
            any(not isinstance(x, dict) or set(x) != {"ref", "sha256"} or not isinstance(x["ref"], str) or
                not 1 <= len(x["ref"]) <= 512 or not isinstance(x["sha256"], str) or not HASH.fullmatch(x["sha256"]) for x in sources) or
            not isinstance(codes, dict) or not {"screen_launch.py", "codex_launch.py", "screen_adoption.py", "session_launch.py"} <= codes.keys() or
            any(not isinstance(x, str) or not HASH.fullmatch(x) for x in codes.values())):
        _fail("native_provenance_incomplete")
    if current:
        if claim.exists() or claim.is_symlink(): _fail("old_claim_present")
        from .screen_adoption import _old_readback
        _old_readback(home, original)  # independently reconciled original source
        _absent({"old": old, "records": records})
    return pins


def reconcile_late_probe(home: Path, plan: dict, *, owning_guard) -> dict:
    """Append immutable effects disposition, no capability PASS or native action."""
    try: raw = json.dumps(plan, allow_nan=False).encode()
    except (ValueError, TypeError): _fail("plan_invalid")
    if len(raw) > LIMIT: _fail("plan_limit")
    plan = json.loads(raw); sha = digest(plan)
    _snapshot(home, plan, current=True)
    destination, attempt = _paths(home, plan["session_id"], plan["failed_adoption_sha256"])
    if not callable(owning_guard): _fail("owning_guard_required")
    with lock(within(home, "state/screen-adoptions/" + plan["session_id"] + ".lock")):
        if any(p.exists() or p.is_symlink() for p in (destination, attempt)): _fail("already_reviewed_or_attempted")
        with owning_guard(plan) as check:
            query = _query(plan)
            if not callable(check): _fail("owning_guard_required")
            review = check(dict(query))
            if digest(plan) != sha or not _review_bound(review, query, fresh=True): _fail("owning_review_not_bound")
            _snapshot(home, plan, current=True)
            receipt = {"schema": "agentos.late-probe-reconciliation/v1", "status": "REVIEWED_LATE_PROBE_EFFECTS_ONLY",
                       "plan": plan, "plan_sha256": sha, "review": review,
                       "old_journals_preserved": True, "old_probe_accepted": False, "work_replay_authorized": False}
            data = (json.dumps(receipt, sort_keys=True) + "\n").encode()
            if len(data) > LIMIT: _fail("receipt_limit")
            create_only_bytes(destination, data)
    return {"failed_adoption_sha256": plan["failed_adoption_sha256"], "receipt_sha256": hashlib.sha256(data).hexdigest()}


def _verified(home, sid, ref, *, current):
    if (not isinstance(sid, str) or not SID.fullmatch(sid) or not isinstance(ref, dict) or
            set(ref) != {"failed_adoption_sha256", "receipt_sha256"} or
            any(not isinstance(x, str) or not HASH.fullmatch(x) for x in ref.values())): _fail("reference_invalid")
    path, attempt = _paths(home, sid, ref["failed_adoption_sha256"])
    row = _ref(path, ref["receipt_sha256"]); plan = row.get("plan")
    if (row.get("schema") != "agentos.late-probe-reconciliation/v1" or row.get("status") != "REVIEWED_LATE_PROBE_EFFECTS_ONLY" or
            not isinstance(plan, dict) or plan.get("session_id") != sid or plan.get("failed_adoption_sha256") != ref["failed_adoption_sha256"] or
            row.get("plan_sha256") != digest(plan) or row.get("old_journals_preserved") is not True or
            row.get("old_probe_accepted") is not False or row.get("work_replay_authorized") is not False): _fail("receipt_not_bound")
    pins = _snapshot(home, plan, current=current)
    if not _review_bound(row.get("review"), _query(plan), fresh=False): _fail("receipt_review_not_bound")
    return row, [*pins, (path, ref["receipt_sha256"])], attempt


class LateProbeSelection:
    def __init__(self, home, plan, request, journal, binding, pins):
        self.home, self.plan, self.request = home, plan, request
        self.journal, self.binding, self.pins = journal, binding, pins

    def verify(self):
        if digest(self.request) != self.binding["replacement_request_sha256"]: _fail("replacement_request_changed")
        _snapshot(self.home, self.plan, current=True)
        for path, sha in self.pins:
            if _journal(path)[1] != sha: _fail("reviewed_source_changed")


def verify_late_probe(home, adoption, *, current=True):
    row, pins, attempt = _verified(home, adoption["session_id"], adoption["late_probe_recovery"], current=current)
    plan = row["plan"]
    if adoption != {"session_id": plan["session_id"], "old_name": plan["failed_worker_name"],
                    "old_pins": plan["worker_pins"], "late_probe_recovery": adoption["late_probe_recovery"]}:
        _fail("adoption_not_reviewed")
    return row, pins, attempt


def select_late_probe(home, name, request, adoption):
    row, pins, attempt = verify_late_probe(home, adoption)
    plan = row["plan"]
    if name != plan["replacement_name"] or request != plan["replacement_request"]: _fail("replacement_not_reviewed")
    if attempt.exists() or attempt.is_symlink(): _fail("attempt_already_reserved")
    ref = adoption["late_probe_recovery"]
    binding = {**ref, "replacement_request_sha256": digest(request), "destination_name": name,
               "terminal_turn_id": plan["turn_id"], "operation_id": plan["operation_id"]}
    return LateProbeSelection(home, plan, request, attempt, binding, pins)


def history_root(home, adoption):
    row, pins, attempt = _verified(home, adoption["session_id"], adoption["late_probe_history"], current=False)
    node, _ = _journal(attempt); plan = row["plan"]
    binding = {**adoption["late_probe_history"], "replacement_request_sha256": digest(plan["replacement_request"]),
               "destination_name": plan["replacement_name"], "terminal_turn_id": plan["turn_id"], "operation_id": plan["operation_id"]}
    if node.get("late_probe") != binding or node.get("request_sha256") != binding["replacement_request_sha256"]:
        _fail("historical_attempt_not_bound")
    return attempt, pins
