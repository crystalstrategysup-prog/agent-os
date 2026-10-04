"""Pure provider binding contract. No I/O, authentication, send or receipt grant."""

from __future__ import annotations

from . import continuation as c
from .safeio import GateError, nonempty

OPERATIONS = {
    "read",
    "send",
    "start",
    "resume",
    "artifact_transfer",
    "native_handoff",
    "goals",
}
OPERATION_ALIASES = {"message_send": "send", "task_create": "start"}
OPERATION_ERRORS = {
    "AUTH_REQUIRED",
    "POLICY_DENIED",
    "TARGET_NOT_FOUND_FOR_OPERATION",
    "OFFLINE",
    "UNSUPPORTED",
    "TRANSIENT",
    "RATE_LIMITED",
    "STALE_TARGET",
    "UNKNOWN_OUTCOME",
}


def canonical_operation(operation: str) -> str:
    operation = OPERATION_ALIASES.get(operation, operation)
    if operation not in OPERATIONS:
        raise GateError("unsupported_completion_operation")
    return operation


def resolve_completion_capability(
    snapshot: dict, operation: str, target: str, scope: str, checked_at: int
) -> dict:
    """Operation-local evidence only; never infer send from read or choose fallback."""
    operation = canonical_operation(operation)
    row = snapshot.get(operation)
    if not isinstance(row, dict):
        return {"operation": operation, "status": "UNKNOWN", "reason": "UNSUPPORTED"}
    if row.get("status") not in {"SUPPORTED", "UNSUPPORTED", "UNKNOWN", "DENIED"}:
        raise GateError("invalid_completion_capability_status")
    if row["status"] != "SUPPORTED":
        return {
            "operation": operation,
            "status": row["status"],
            "reason": row.get("error_code")
            if row.get("error_code") in OPERATION_ERRORS
            else "POLICY_DENIED"
            if row["status"] == "DENIED"
            else "UNSUPPORTED",
        }
    for key in (
        "adapter_version",
        "runtime_version",
        "source",
        "target_class",
        "scope",
        "evidence_hash",
    ):
        nonempty(row.get(key), "capability_" + key, 4000)
    if (
        type(row.get("checked_at")) is not int
        or type(row.get("expires_at")) is not int
        or not 0 <= row["checked_at"] <= checked_at < row["expires_at"]
        or row["expires_at"] - row["checked_at"] > 300
    ):
        return {"operation": operation, "status": "UNKNOWN", "reason": "STALE_TARGET"}
    if row["target_class"] != target or row["scope"] != scope:
        return {"operation": operation, "status": "UNKNOWN", "reason": "STALE_TARGET"}
    return {"operation": operation, "status": "SUPPORTED", "reason": None}


def validate_completion_freshness(
    identity: dict, capability_hash: str, policy_scope_hash: str, checked_at: int
) -> None:
    """v1 relational admission checks; supplied labels never grant authority."""
    keys = (
        "capability_checked_at",
        "capability_expires_at",
        "policy_expires_at",
        "checked_at",
    )
    if any(type(identity.get(k)) is not int or identity[k] < 0 for k in keys):
        raise GateError("completion_freshness_required")
    if (
        identity["checked_at"] != checked_at
        or not identity["capability_checked_at"]
        <= checked_at
        < identity["capability_expires_at"]
        or identity["capability_expires_at"] - identity["capability_checked_at"] > 300
        or checked_at >= identity["policy_expires_at"]
    ):
        raise GateError("completion_capability_or_policy_expired")
    if (
        identity.get("capability_snapshot_hash") != capability_hash
        or identity.get("policy_scope_hash") != policy_scope_hash
    ):
        raise GateError("completion_capability_or_policy_scope_changed")


class LocalCompletionRunner:
    """Explicit registered argv adapter; no shell interpolation or model launch.

    The authority and dependency readers are authenticated selecting-adapter
    callbacks, never deserialized from an archive. This is not an OS sandbox.
    """

    def __init__(
        self, recipes, *, verify_authority, read_dependencies, read_clock=None
    ):
        from copy import deepcopy

        if not callable(verify_authority) or not callable(read_dependencies):
            raise GateError("completion_live_authority_and_source_readers_required")
        if not isinstance(recipes, dict) or not 0 < len(recipes) <= 64:
            raise GateError("invalid_registered_completion_recipes")
        self.recipes = deepcopy(recipes)
        self.verify_authority = verify_authority
        self.read_dependencies = read_dependencies
        import time

        self.read_clock = read_clock or (lambda: int(time.time()))
        if not callable(self.read_clock):
            raise GateError("completion_clock_reader_required")

    def run_bounded(self, coordinator, actor, *, clock, max_steps=3):
        """Explicit finite continuation; no timer, sleeping, scheduler or Goals.

        A waiting/unknown/terminal state returns without polling or a model call.
        Current authority, dependencies, lease, budget and receiver fence are
        rechecked by every selected step. Backoff is reported to the caller.
        """
        from .handoff_store import require

        require(
            callable(clock) and type(max_steps) is int and 1 <= max_steps <= 64,
            "INVALID_CONTINUATION_BOUND",
        )
        runs = []
        for _ in range(max_steps):
            result = self.run(coordinator, actor, clock())
            if "receipt_ref" not in result:
                return {
                    "schema": "agentos.completion-bounded-run/v1",
                    "runs": runs,
                    "stop": result,
                    "status": coordinator.completion_status(clock()),
                }
            runs.append(result)
        return {
            "schema": "agentos.completion-bounded-run/v1",
            "runs": runs,
            "stop": {"reason": "CALL_STEP_LIMIT"},
            "status": coordinator.completion_status(clock()),
        }

    def run(self, coordinator, actor, checked_at):
        import os
        import platform
        import time
        import uuid
        from copy import deepcopy
        from pathlib import Path

        from .completion import DEPENDENCIES
        from .handoff_store import encoded, require, sha
        from .project import _capture_check_process, _scrub

        checked_at = self.read_clock()
        s = coordinator.read()
        cstate = s["completion"]
        current_status = coordinator.completion_status(checked_at)
        if current_status["project_state"] != "READY":
            return {
                "status": current_status["project_state"],
                "operation": None,
                "reason": current_status["blocker"],
            }
        self.verify_authority("plan", deepcopy(cstate["contract"]))
        actual = self.read_dependencies()
        require(
            actual == {k: cstate["contract"][k] for k in DEPENDENCIES},
            "CURRENT_SOURCE_MISMATCH",
        )
        plan = coordinator.completion_plan(actor, s["revision"], checked_at)
        if plan["operation"] is None:
            return plan
        op = plan["operation"]
        require(
            op["operation"] in {"start", "resume"},
            "LOCAL_COMPLETION_OPERATION_UNSUPPORTED",
        )
        recipe = self.recipes.get(op["recipe_id"])
        require(
            isinstance(recipe, dict)
            and set(recipe) == {"argv", "workspace", "timeout", "artifact_paths"},
            "REGISTERED_RECIPE_REQUIRED",
        )
        require(sha(encoded(recipe)) == op["data_hash"], "REGISTERED_RECIPE_CHANGED")
        argv = recipe["argv"]
        require(
            isinstance(argv, list)
            and 0 < len(argv) <= 128
            and all(isinstance(v, str) and v and "\x00" not in v for v in argv),
            "INVALID_RECIPE_ARGV",
        )
        workspace = Path(recipe["workspace"])
        require(
            workspace.is_dir() and not workspace.is_symlink(),
            "INVALID_RECIPE_WORKSPACE",
        )
        require(
            type(recipe["timeout"]) is int and 1 <= recipe["timeout"] <= 300,
            "INVALID_RECIPE_TIMEOUT",
        )
        names = recipe["artifact_paths"]
        require(
            isinstance(names, list)
            and len(names) <= 63
            and len(set(names)) == len(names)
            and all(isinstance(n, str) and n for n in names),
            "INVALID_RECIPE_ARTIFACTS",
        )
        from .safeio import within

        for name in names:
            within(workspace, name)
        self.verify_authority("dispatch", deepcopy(op))
        identity = coordinator.completion_begin_dispatch(
            actor, coordinator.read()["revision"], op["operation_id"], self.read_clock()
        )
        # Last current source/authority check belongs to the selecting adapter.
        self.verify_authority("receiver-admit", deepcopy(identity))
        require(self.read_dependencies() == actual, "CURRENT_SOURCE_MISMATCH")
        admission = coordinator.completion_receiver_admit(
            actor, coordinator.read()["revision"], identity, self.read_clock()
        )
        require(admission["status"] == "NEW_ADMISSION", "ALREADY_ADMITTED_RECONCILE")
        coordinator._fault("before_completion_local_effect")
        started = int(time.time())
        process = coordinator.completion_spawn_local(
            actor,
            coordinator.read()["revision"],
            identity,
            self.read_clock(),
            recipe,
            dict(os.environ),
        )
        try:
            exit_code, output = _capture_check_process(process, recipe["timeout"])
        except GateError as exc:
            exit_code, output = 125, "BOUNDED_RUNNER_BLOCKED:" + str(exc)
        finished = int(time.time())
        store = coordinator._completion_store()
        # Persist bounded, scrubbed real output. No source session transcripts.
        evidence = [store.put(_scrub(output).encode(), "text/plain")]
        from .safeio import within

        for name in recipe["artifact_paths"]:
            path = within(workspace, name, allow_missing=False)
            from .handoff_store import bounded

            evidence.append(store.put(bounded(path), "application/octet-stream"))
        require(self.read_dependencies() == actual, "SOURCE_CHANGED_DURING_EXECUTION")
        receipt = {
            "schema": "agentos.completion-execution/v1",
            **{
                k: identity[k]
                for k in (
                    "operation_id",
                    "nonce",
                    "generation",
                    "ownership_epoch",
                    *DEPENDENCIES,
                )
            },
            "criterion_id": op["criterion_id"],
            "run_id": uuid.uuid4().hex,
            "status": "PASS" if exit_code == 0 else "FAIL",
            "exit_code": exit_code,
            "recipe_id": op["recipe_id"],
            "runtime": "python-local-runner:" + platform.python_version(),
            "workspace": str(workspace.resolve()),
            "started_at": started,
            "finished_at": finished,
            "tokens": 0,
            "cost_units": 0,
            "evidence_refs": evidence,
        }
        receipt_ref = store.put_json(receipt)
        coordinator._fault("after_completion_local_effect")
        coordinator.completion_record_result(
            actor,
            coordinator.read()["revision"],
            identity,
            receipt_ref,
            self.read_clock(),
            lambda value, binding: value == receipt and binding == identity,
        )
        return {
            "status": receipt["status"],
            "operation_id": op["operation_id"],
            "run_id": receipt["run_id"],
            "receipt_ref": receipt_ref,
            "completion": coordinator.completion_status(self.read_clock()),
        }


def binding(value: dict, item: dict) -> dict:
    keys = {
        "schema",
        "provider",
        "target_owner",
        "target_id",
        "workstream_id",
        "parent_owner",
    }
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or value.get("schema") != "agentos.continuation-adapter-binding/v1"
    ):
        raise GateError("invalid_continuation_adapter_binding")
    for key in keys:
        nonempty(value[key], key, 300)
    if (
        value["target_owner"] != item["continuation"]["next_owner"]
        or value["parent_owner"] != item["continuation"]["parent_owner"]
    ):
        raise GateError("adapter_owner_binding_mismatch")
    return dict(value)


def request(item: dict, mapping: dict) -> dict:
    mapping = binding(mapping, item)
    if item["schema"] != c.ITEM_SCHEMA or item["state"] != "DELIVERY_UNKNOWN":
        raise GateError("committed_v2_unknown_required")
    return {
        "schema": "agentos.continuation-provider-request/v1",
        "provider": mapping["provider"],
        "target_id": mapping["target_id"],
        "workstream_id": mapping["workstream_id"],
        "target_owner": mapping["target_owner"],
        "parent_owner": mapping["parent_owner"],
        "operation_key": item["attempt_id"],
        "delivery_generation": item["delivery_generation"],
        "delivery_nonce": item["delivery_nonce"],
        "delivery_started_at": item["delivery_started_at"],
        "ledger_id": item["id"],
        "ledger_revision": item["revision"],
        "target_authority_proven": False,
        "provider_invocation_performed": False,
    }


def check_receipt(item: dict, mapping: dict, receipt: dict, action: str) -> dict:
    """Pins namespace and checks structure; actual provider provenance is external."""
    mapping = binding(mapping, item)
    request(item, mapping)
    if action not in {"acknowledge", "not-sent"}:
        raise GateError("invalid_adapter_outcome")
    if not isinstance(receipt, dict) or receipt.get("provider") != mapping["provider"]:
        raise GateError("adapter_provider_namespace_mismatch")
    receipt_id = c._check_receipt(item, receipt, action)
    return {
        "schema": "agentos.continuation-adapter-check/v1",
        "status": "STRUCTURE_MATCHES",
        "receipt_id": receipt_id,
        "request": request(item, mapping),
        "external_provenance_proven": False,
        "delivery_acceptance_proven": False,
        "ledger_transition_performed": False,
        "next": "Authorized real adapter must verify durable provider origin, exact target/call correlation and authority before recording the receipt.",
    }
