"""Provider-neutral, explicit admission for new worker sessions.

This is a dispatch boundary, not a permission grant or an OS sandbox. The
provider and target guard are trusted integrations; self-written receipts alone
cannot establish live permissions, fencing or business authority.
"""

from __future__ import annotations

import copy
import json
import re
import time
import uuid
from pathlib import Path
from typing import Callable, Protocol

from .safeio import GateError, atomic_json, digest, lock, read_json, within


class LaunchError(GateError):
    def __init__(self, code: str, *, status: str = "MISMATCH", receipt: dict | None = None):
        self.code = code
        self.status = status
        self.receipt = receipt or {}
        super().__init__("session_launch:" + status + ":" + code)


class LaunchProvider(Protocol):
    def describe(self, request: dict, attempt: str) -> dict: ...
    def create(self, request: dict, attempt: str) -> dict: ...
    def probe(self, request: dict, startup: dict, attempt: str) -> dict: ...
    def dispatch(self, request: dict, startup: dict, envelope: str) -> dict: ...


def validate_request(request: dict) -> None:
    if not isinstance(request, dict) or request.get("schema") != "agentos.session-launch/v1":
        raise LaunchError("request_required", status="UNKNOWN")
    try:
        size = len(json.dumps(request, ensure_ascii=False))
    except (ValueError, TypeError, RecursionError) as exc:
        raise LaunchError("request_not_json_data") from exc
    if size > 64000:
        raise LaunchError("request_size_limit")
    for key in ("launch_id", "original_goal", "scope", "authority"):
        if not isinstance(request.get(key), str) or not request[key].strip():
            raise LaunchError("request_field_required:" + key, status="UNKNOWN")
    if len(request["launch_id"]) > 200 or len(request["original_goal"]) > 20000:
        raise LaunchError("request_field_size_limit")
    if not isinstance(request.get("context"), dict) or not isinstance(request.get("acceptance"), list) or not 1 <= len(request["acceptance"]) <= 64 or any(not isinstance(a, str) or not a.strip() for a in request["acceptance"]):
        raise LaunchError("retained_context_and_acceptance_required", status="UNKNOWN")
    if not isinstance(request.get("workspace"), str) or not Path(request["workspace"]).is_absolute():
        raise LaunchError("absolute_workspace_required")
    if not isinstance(request.get("autonomous_ordinary_work"), bool):
        raise LaunchError("ordinary_work_mode_required", status="UNKNOWN")
    caps = request.get("required_capabilities")
    if not isinstance(caps, list) or not 1 <= len(caps) <= 32 or any(not isinstance(c, str) or not c for c in caps) or len(caps) != len(set(caps)):
        raise LaunchError("required_capabilities_invalid")
    executor = request.get("executor")
    if not isinstance(executor, dict) or any(not isinstance(executor.get(k), str) or not executor[k].strip() for k in ("id", "provider", "owner_approved_ref")):
        raise LaunchError("owner_selected_executor_required", status="UNKNOWN")
    gates = request.get("target_gates")
    if not isinstance(gates, list) or len(gates) > 32 or any(not isinstance(g, str) or not g for g in gates):
        raise LaunchError("target_gate_inventory_required", status="UNKNOWN")
    if request.get("transfer") is not None:
        transfer = request["transfer"]
        if not isinstance(transfer, dict) or not transfer.get("source_session"):
            raise LaunchError("transfer_source_required", status="UNKNOWN")
        source_path = Path(str(transfer.get("source_workspace", "")))
        source = source_path.resolve()
        destination = Path(request["workspace"]).resolve()
        if not source_path.is_absolute() or source == destination or source in destination.parents or destination in source.parents:
            raise LaunchError("transfer_source_must_be_disjoint")
        if not isinstance(transfer.get("source_snapshot_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", transfer["source_snapshot_sha256"]) or not transfer.get("target"):
            raise LaunchError("transfer_snapshot_and_target_required", status="UNKNOWN")


def _observation(request: dict, observation: dict, attempt: str, *, startup: bool, clock: Callable[[], float]) -> None:
    if not isinstance(observation, dict):
        raise LaunchError("effective_metadata_missing", status="UNKNOWN")
    expected_source = "provider_startup" if startup else "provider_effective"
    if observation.get("source") != expected_source or observation.get("attempt_id") != attempt:
        raise LaunchError("copied_or_unbound_metadata", status="UNKNOWN")
    observed = observation.get("observed_at")
    if not isinstance(observed, (int, float)) or isinstance(observed, bool) or not 0 <= clock() - observed <= 60:
        raise LaunchError("stale_effective_metadata", status="UNKNOWN")
    for key in ("executor_id", "provider", "connection_id", "workspace", "sandbox", "approval_policy"):
        if observation.get(key) is None or observation.get(key) == "" or (isinstance(observation.get(key), str) and observation[key].lower() in {"unknown", "unavailable", "unset"}):
            raise LaunchError("effective_metadata_missing:" + key, status="UNKNOWN")
    if observation["executor_id"] != request["executor"]["id"] or observation["provider"] != request["executor"]["provider"]:
        raise LaunchError("executor_identity_mismatch")
    if observation["workspace"] != request["workspace"]:
        raise LaunchError("workspace_mismatch")
    if request["autonomous_ordinary_work"]:
        if observation.get("ordinary_commands") == "interactive":
            raise LaunchError("ordinary_commands_require_interactive_approval")
        if observation.get("ordinary_commands") not in {"noninteractive", "within_policy"}:
            raise LaunchError("ordinary_command_mode_unknown", status="UNKNOWN")
    capabilities = observation.get("capabilities", {})
    for capability in request["required_capabilities"]:
        state = capabilities.get(capability)
        if state is False:
            raise LaunchError("insufficient_capability:" + capability)
        if state is not True:
            raise LaunchError("capability_metadata_unknown:" + capability, status="UNKNOWN")
    if startup and not observation.get("session_id"):
        raise LaunchError("startup_session_missing", status="UNKNOWN")


def _targets(request: dict, guard: Callable[[dict, str], dict] | None, phase: str, attempt: str, clock: Callable[[], float]) -> None:
    if not request["target_gates"] and request.get("transfer") is None:
        return
    if guard is None:
        raise LaunchError("independent_target_readback_required", status="UNKNOWN")
    record = guard(copy.deepcopy(request), phase)
    if not isinstance(record, dict) or record.get("request_sha256") != digest(request) or record.get("phase") != phase:
        raise LaunchError("target_readback_not_bound", status="UNKNOWN")
    if record.get("source") != "target_readback" or record.get("attempt_id") != attempt:
        raise LaunchError("target_readback_not_current", status="UNKNOWN")
    observed = record.get("observed_at")
    if not isinstance(observed, (float, int)) or isinstance(observed, bool) or not 0 <= clock() - observed <= 60:
        raise LaunchError("target_readback_stale", status="UNKNOWN")
    for name in request["target_gates"]:
        gate = record.get("gates", {}).get(name, {})
        if gate.get("status") != "PASS" or not gate.get("evidence_ref"):
            raise LaunchError("target_gate_unsatisfied:" + name, status="BLOCKED")
    transfer = request.get("transfer")
    if transfer is not None:
        state = record.get("transfer", {})
        if state.get("source_session") != transfer["source_session"]:
            raise LaunchError("transfer_reconciliation_not_bound", status="UNKNOWN")
        if state.get("old_writer") not in {"stopped_and_reconciled", "fenced_and_reconciled"} or not state.get("fence_evidence_ref"):
            raise LaunchError("old_writer_reconciliation_required", status="BLOCKED")
        if state.get("source_workspace") != transfer["source_workspace"] or state.get("isolated_workspace") != request["workspace"] or not state.get("isolation_evidence_ref") or state.get("isolated_snapshot_sha256") != transfer["source_snapshot_sha256"]:
            raise LaunchError("source_isolation_not_verified", status="BLOCKED")
        if state.get("lease_holder") != request["launch_id"] or state.get("lease_status") != "held" or not state.get("lease_evidence_ref") or state.get("lease_target") != transfer["target"] or state.get("lease_scope_sha256") != digest([request["scope"], request["authority"]]):
            raise LaunchError("destination_lease_required", status="BLOCKED")


class LaunchJournal:
    """Crash-visible one-shot launch journal, separate from business authority."""

    def __init__(self, home: Path, launch_id: str):
        self.path = within(home, "state/session-launch/" + digest(launch_id) + ".json")
        self.lock_path = within(home, "state/session-launch.lock")

    def reserve(self, request: dict, attempt: str) -> None:
        with lock(self.lock_path):
            if self.path.exists():
                previous = read_json(self.path)
                if previous.get("request_sha256") != digest(request):
                    raise LaunchError("launch_id_reused_for_different_request")
                if previous.get("provider_mutation_started"):
                    raise LaunchError("previous_launch_requires_reconciliation", status="UNKNOWN", receipt=previous)
            atomic_json(self.path, {"schema": "agentos.session-launch-receipt/v1", "attempt_id": attempt,
                                    "request_sha256": digest(request), "phase": "RESERVED", "provider_mutation_started": False})

    def save(self, receipt: dict) -> None:
        with lock(self.lock_path):
            previous = read_json(self.path)
            if previous.get("attempt_id") != receipt["attempt_id"]:
                raise LaunchError("concurrent_launch_attempt", status="UNKNOWN")
            atomic_json(self.path, receipt)


def launch(request: dict, provider: LaunchProvider, *,
           target_guard: Callable[[dict, str], dict] | None = None,
           dispatch_claim: Callable[[], None], journal: LaunchJournal | None = None,
           clock: Callable[[], float] = time.time) -> dict:
    """Admit, create, probe and dispatch once; never change settings or retry.

    The target guard receives a private `_launch_attempt_id` in its request copy
    so a fresh response can bind itself to this call. It must hash the original
    request with that transport-only key removed. No third-party target gate is
    inferred from an empty gate list: that inventory belongs to the task contract.
    """
    validate_request(request)
    request = copy.deepcopy(request)
    attempt = str(uuid.uuid4())
    if journal:
        journal.reserve(request, attempt)
    receipt = {"schema": "agentos.session-launch-receipt/v1", "attempt_id": attempt,
               "request_sha256": digest(request), "goal_sha256": digest(request["original_goal"]),
               "authority_sha256": digest(request["authority"]), "provider_mutation_started": False,
               "phase": "PREFLIGHT", "work_accepted": False, "trace": []}

    def phase(value: str) -> None:
        receipt["phase"] = value
        receipt["trace"].append(value)
        if journal:
            journal.save(receipt)

    guard = None
    if target_guard:
        def guard(bound_request: dict, guard_phase: str) -> dict:
            bound_request["_launch_attempt_id"] = attempt
            return target_guard(bound_request, guard_phase)

    try:
        description = provider.describe(copy.deepcopy(request), attempt)
        _observation(request, description, attempt, startup=False, clock=clock)
        receipt["preflight"] = description
        _targets(request, guard, "before_create", attempt, clock)
        phase("ADMITTED_FOR_STARTUP_ONLY")
        receipt["provider_mutation_started"] = True
        phase("CREATING")
        startup = provider.create(copy.deepcopy(request), attempt)
        receipt["session_id"] = startup.get("session_id") if isinstance(startup, dict) else None
        _observation(request, startup, attempt, startup=True, clock=clock)
        for key in ("connection_id", "sandbox", "approval_policy"):
            if startup[key] != description[key]:
                raise LaunchError("startup_changed:" + key)
        receipt["startup"] = startup
        phase("STARTUP_READBACK_VERIFIED")
        probe = provider.probe(copy.deepcopy(request), startup, attempt)
        receipt["probe"] = probe
        if not isinstance(probe, dict) or probe.get("source") != "provider_tool_evidence" or probe.get("attempt_id") != attempt or probe.get("session_id") != startup["session_id"] or not probe.get("turn_id"):
            raise LaunchError("probe_evidence_missing", status="UNKNOWN")
        if probe.get("status") != "PASS" or set(probe.get("capabilities", [])) != set(request["required_capabilities"]):
            raise LaunchError("harmless_probe_failed", status="BLOCKED")
        proofs = probe.get("proofs", [])
        if not isinstance(proofs, list) or {p.get("capability") for p in proofs if isinstance(p, dict) and p.get("status") == "PASS" and p.get("evidence_ref")} != set(request["required_capabilities"]):
            raise LaunchError("probe_tool_proofs_missing", status="UNKNOWN")
        phase("RUNNABLE")
        _targets(request, guard, "before_dispatch", attempt, clock)
        dispatch_claim()
        phase("DISPATCHING")
        # Transfer context remains data under the original explicit task scope.
        envelope = request["original_goal"] + "\n\nRetained task contract (no additional authority):\n" + json.dumps(
            {key: request.get(key) for key in ("scope", "acceptance", "context", "authority", "target_gates", "transfer")},
            ensure_ascii=False, sort_keys=True)
        work = provider.dispatch(copy.deepcopy(request), startup, envelope)
        receipt["work"] = work
        phase("DISPATCH_OBSERVED")
        return receipt
    except LaunchError as exc:
        if exc.receipt and exc.receipt is not receipt:
            # Provider adapters expose normalized failure metadata here, such
            # as an actual thread created before startup binding was refused.
            # Keep it for reconciliation instead of losing the thread identity.
            receipt["provider_failure"] = copy.deepcopy(exc.receipt)
        receipt["status"], receipt["error"] = exc.status, exc.code
        phase("STOPPED")
        exc.receipt = receipt
        raise
    except GateError as exc:
        receipt["status"], receipt["error"] = "BLOCKED", str(exc)
        phase("STOPPED")
        raise LaunchError("independent_dispatch_gate_refused", status="BLOCKED", receipt=receipt) from exc
    except (OSError, TimeoutError, ValueError) as exc:
        receipt["status"] = "UNKNOWN" if receipt["provider_mutation_started"] else "UNAVAILABLE"
        receipt["error"] = type(exc).__name__
        phase("OUTCOME_REQUIRES_RECONCILIATION" if receipt["provider_mutation_started"] else "STOPPED")
        raise LaunchError("provider_io_unresolved", status=receipt["status"], receipt=receipt) from exc
