"""Explicit completion extension of Coordinator's existing snapshot/HEAD store.

No background worker, network, model call, authentication or authority source.
The selected adapter owns those boundaries; an unknown effect remains owned.
"""

from __future__ import annotations

import copy
import re
import uuid
from contextlib import contextmanager

from .continuation_adapter import (
    canonical_operation,
    resolve_completion_capability,
    validate_completion_freshness,
)
from .handoff_store import Store, encoded, publisher_lock, require, sha, valid_id

SCHEMA = "agentos.completion/v1"
TERMINAL = {"ACCEPTED", "CANCELLED", "FAILED_FINAL"}
STATES = {
    "DRAFT",
    "READY",
    "RUNNING",
    "VERIFYING",
    "WAITING_USER",
    "WAITING_EXECUTOR",
    "BLOCKED_POLICY",
    "BLOCKED_BUDGET",
    "BLOCKED_NO_PROGRESS",
    "BLOCKED_UNKNOWN_OUTCOME",
    "BLOCKED_UNSAFE_TAKEOVER",
} | TERMINAL
DEPENDENCIES = (
    "source_commit",
    "contract_hash",
    "build_hash",
    "configuration_hash",
    "environment_fingerprint",
)
EVENT_PAYLOADS = {
    "TASK_CREATED": {"contract_hash"},
    "CONTRACT_CHANGED": {"contract_hash", "source_commit"},
    "TURN_FINISHED": {"turn_id", "executor_ref", "status"},
    "TEST_FINISHED": {"operation_id", "run_id", "outcome"},
    "EXECUTOR_DISCONNECTED": {"executor_ref"},
    "EXECUTOR_RECONNECTED": {"executor_ref"},
    "APPROVAL_CHANGED": {"policy_revision", "policy_scope_hash"},
    "BUDGET_CHANGED": {"budget_hash"},
    "HANDOFF_ACK": {"handoff_id", "operation_id", "ack_hash"},
    "USER_CANCELLED": {"reason", "source_ref"},
    "CHECKPOINT_VERIFIED": {"checkpoint_hash"},
    "COORDINATOR_RESTARTED": {"previous_epoch"},
    "RECONCILIATION_FINISHED": {"operation_id", "receipt_hash"},
}


def clock(value):
    require(type(value) is int and value >= 0, "INVALID_CLOCK")
    return value


def hash_value(value):
    require(
        isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value), "INVALID_HASH"
    )
    return value


def contract_shape(value, state):
    require(
        isinstance(value, dict)
        and value.get("schema") == "agentos.completion-contract/v1",
        "INVALID_COMPLETION_CONTRACT",
    )
    require(
        set(value)
        == {
            "schema",
            "task_id",
            "goal",
            "acceptance_owner",
            "criteria",
            *DEPENDENCIES,
            "budget",
            "limits",
        },
        "INVALID_COMPLETION_CONTRACT",
    )
    require(value["goal"] == state["goal"], "ORIGINAL_GOAL_MISMATCH")
    for key in ("task_id", "acceptance_owner"):
        valid_id(value[key])
    require(value["acceptance_owner"] != state["owner"], "INDEPENDENT_REVIEW_REQUIRED")
    require(
        isinstance(value["source_commit"], str)
        and re.fullmatch("[0-9a-f]{40,64}", value["source_commit"]),
        "INVALID_SOURCE_COMMIT",
    )
    for key in DEPENDENCIES[1:-1]:
        hash_value(value[key])
    valid_id(value["environment_fingerprint"])
    rows = value["criteria"]
    require(isinstance(rows, list) and 0 < len(rows) <= 64, "INVALID_CRITERIA")
    require([r["criterion_id"] for r in rows] == state["criteria"], "CRITERIA_MISMATCH")
    for row in rows:
        require(
            set(row) - {"alternatives", "work_id"}
            == {
                "criterion_id",
                "requirement_ids",
                "operation",
                "target",
                "receiver",
                "data_hash",
                "recipe_id",
            },
            "INVALID_CRITERION",
        )
        for key in ("criterion_id", "target", "receiver", "recipe_id"):
            valid_id(row[key])
        canonical_operation(row["operation"])
        hash_value(row["data_hash"])
        alternatives = row.get("alternatives", [])
        require(
            isinstance(alternatives, list) and len(alternatives) <= 1,
            "INVALID_STRATEGIES",
        )
        for alternative in alternatives:
            require(
                set(alternative) == {"recipe_id", "data_hash"}
                and alternative["recipe_id"] != row["recipe_id"],
                "INVALID_STRATEGIES",
            )
            valid_id(alternative["recipe_id"])
            hash_value(alternative["data_hash"])
        require(
            isinstance(row["requirement_ids"], list)
            and row["requirement_ids"]
            and all(
                isinstance(r, str) and re.fullmatch("R[0-9]{2}", r)
                for r in row["requirement_ids"]
            ),
            "INVALID_REQUIREMENT_MAPPING",
        )
    budget = value["budget"]
    require(
        set(budget) == {"steps", "deadline", "tokens", "cost_units"}, "INVALID_BUDGET"
    )
    require(all(type(v) is int and v >= 0 for v in budget.values()), "INVALID_BUDGET")
    limits = value["limits"]
    require(
        set(limits)
        == {
            "max_attempts",
            "max_no_progress",
            "lease_seconds",
            "ack_timeout",
            "backoff",
        },
        "INVALID_LIMITS",
    )
    require(
        type(limits["max_attempts"]) is int
        and 1 <= limits["max_attempts"] <= 3
        and type(limits["max_no_progress"]) is int
        and 1 <= limits["max_no_progress"] <= 2
        and type(limits["lease_seconds"]) is int
        and 1 <= limits["lease_seconds"] <= 60
        and type(limits["ack_timeout"]) is int
        and 1 <= limits["ack_timeout"] <= 120
        and isinstance(limits["backoff"], list)
        and limits["backoff"] == [5, 20, 60],
        "INVALID_LIMITS",
    )
    result = copy.deepcopy(value)
    required_work = [k for k, work in state["work"].items() if work["required"]]
    for row in result["criteria"]:
        if "work_id" not in row:
            require(len(required_work) == 1, "EXPLICIT_CRITERION_WORK_MAPPING_REQUIRED")
            row["work_id"] = required_work[0]
        require(row["work_id"] in state["work"], "INVALID_CRITERION_WORK_MAPPING")
    require(
        set(required_work) <= {r["work_id"] for r in result["criteria"]},
        "REQUIRED_WORK_UNCOVERED",
    )
    return result


def policy_shape(value):
    require(
        isinstance(value, dict)
        and set(value)
        == {"revision", "actor", "expires_at", "revoked", "scope", "source_ref"},
        "INVALID_POLICY",
    )
    require(
        type(value["revision"]) is int
        and value["revision"] >= 1
        and type(value["revoked"]) is bool
        and isinstance(value["scope"], list)
        and 0 < len(value["scope"]) <= 64,
        "INVALID_POLICY",
    )
    clock(value["expires_at"])
    valid_id(value["actor"])
    valid_id(value["source_ref"])
    for scope in value["scope"]:
        require(
            set(scope)
            == {
                "operation",
                "target",
                "receiver",
                "data_hash",
                "environment_fingerprint",
            },
            "INVALID_POLICY_SCOPE",
        )
        canonical_operation(scope["operation"])
        hash_value(scope["data_hash"])
        for key in ("target", "receiver", "environment_fingerprint"):
            valid_id(scope[key])
    return copy.deepcopy(value)


def policy_check(c, actor, row, checked_at):
    p = c["policy"]
    require(
        not p["revoked"] and p["actor"] == actor and checked_at < p["expires_at"],
        "POLICY_DENIED",
    )
    expected = {k: row[k] for k in ("target", "receiver", "data_hash")}
    expected.update(
        operation=canonical_operation(row["operation"]),
        environment_fingerprint=c["contract"]["environment_fingerprint"],
    )
    require(
        expected
        in [
            {**s, "operation": canonical_operation(s["operation"])} for s in p["scope"]
        ],
        "POLICY_DENIED",
    )


def current_result(c, criterion):
    receipt = c["results"].get(criterion)
    return bool(
        receipt
        and receipt["status"] == "PASS"
        and receipt["generation"] == c["generation"]
        and all(receipt[k] == c["contract"][k] for k in DEPENDENCIES)
    )


def budget_available(c, checked_at):
    b = c["remaining_budget"]
    return checked_at < b["deadline"] and all(
        b[k] > 0 for k in ("steps", "tokens", "cost_units")
    )


def attempted_recipes(c, row):
    """Never replay an already completed identical effect after reinitialization.

    An old receipt may be insufficient for current semantic acceptance while
    its effect remains real. Use an explicitly approved alternative verification
    recipe or changed exact scope; a new generation alone is not permission.
    """
    recipes = [row] + row.get("alternatives", [])
    return {
        op["recipe_id"]
        for op in c["operations"]
        if op["criterion_id"] == row["criterion_id"]
        and op["state"] in {"COMPLETED", "RECONCILED"}
        and (
            op["generation"] == c["generation"]
            or (
                (op.get("identity") or {}).get("environment_fingerprint")
                == c["contract"]["environment_fingerprint"]
                and any(
                    op["recipe_id"] == recipe["recipe_id"]
                    and all(
                        op[k] == recipe.get(k, row[k])
                        for k in ("operation", "target", "receiver", "data_hash")
                    )
                    for recipe in recipes
                )
            )
        )
    }


def projection(c, checked_at):
    if c["state"] in TERMINAL:
        return c["state"], c["blocker"]
    if any(op["state"] == "UNKNOWN" for op in c["operations"]):
        return "BLOCKED_UNKNOWN_OUTCOME", "RECONCILE_EXACT_OPERATION"
    if c["paused"]:
        return "WAITING_EXECUTOR", "DISPATCH_PAUSED_FOR_CHECKPOINT"
    if checked_at >= c["lease_expires_at"]:
        return "WAITING_EXECUTOR", "OWNERSHIP_LEASE_EXPIRED"
    if c.get("route_blocker") == "POLICY_DENIED":
        return "BLOCKED_POLICY", "POLICY_DENIED"
    if c["waiting_user"]:
        return "WAITING_USER", "OWNER_DECISION_REQUIRED"
    if not c["executor_online"]:
        return "WAITING_EXECUTOR", "EXECUTOR_OFFLINE"
    if c["policy"]["revoked"] or checked_at >= c["policy"]["expires_at"]:
        return "BLOCKED_POLICY", "POLICY_DENIED"
    if all(current_result(c, row["criterion_id"]) for row in c["contract"]["criteria"]):
        return "VERIFYING", "INDEPENDENT_REVIEW_AND_DELIVERY_REQUIRED"
    budget = c["remaining_budget"]
    if checked_at >= budget["deadline"] or any(
        budget[k] <= 0 for k in ("steps", "tokens", "cost_units")
    ):
        return "BLOCKED_BUDGET", "BUDGET_EXHAUSTED"
    if c["no_progress"] >= c["contract"]["limits"]["max_no_progress"]:
        return "BLOCKED_NO_PROGRESS", "SEMANTIC_PROGRESS_REQUIRED"
    for row in c["contract"]["criteria"]:
        if current_result(c, row["criterion_id"]):
            continue
        attempted = attempted_recipes(c, row)
        candidates = {row["recipe_id"]} | {
            v["recipe_id"] for v in row.get("alternatives", [])
        }
        if candidates <= attempted:
            return "BLOCKED_NO_PROGRESS", "FAILED_RECIPE_REQUIRES_REPLAN"
        if any(
            o["criterion_id"] == row["criterion_id"]
            and o["state"] == "NOT_ADMITTED"
            and o["attempt"] >= c["contract"]["limits"]["max_attempts"]
            for o in c["operations"]
        ):
            return "BLOCKED_NO_PROGRESS", "RETRY_LIMIT"
    if any(op["state"] == "PREPARED" for op in c["operations"]):
        return "RUNNING", None
    return "READY", None


class CompletionMixin:
    """Uses only Coordinator.read/_save/_cas and its existing publisher lock."""

    def _completion_store(self):
        return Store(self.root, "completion-evidence")

    @contextmanager
    def _completion_transaction(
        self, actor, expected_revision, checked_at, *, lease=True
    ):
        clock(checked_at)
        with publisher_lock(self.root / "publisher.lock"):
            s = self.read()
            self._owner(s, actor)
            self._cas(s, expected_revision)
            c = s.get("completion")
            require(
                isinstance(c, dict) and c.get("schema") == SCHEMA,
                "COMPLETION_NOT_ACTIVATED",
            )
            require(checked_at >= c["checked_at"], "CLOCK_REVERSED")
            if lease:
                require(checked_at < c["lease_expires_at"], "OWNERSHIP_LEASE_EXPIRED")
            yield s, c
            require(c["state"] in STATES, "INVALID_PROJECT_STATE")
            require(
                len(c["events"]) <= 1024
                and len(c["operations"]) <= 1024
                and len(c["audit"]) <= 1024,
                "SIZE_LIMIT",
            )
            c["checked_at"] = checked_at
            c["state"], c["blocker"] = projection(c, checked_at)
            c["audit"].append(
                {
                    "kind": "STATE_COMMIT",
                    "revision": s["revision"] + 1,
                    "generation": c["generation"],
                    "ownership_epoch": c["ownership_epoch"],
                    "project_state": c["state"],
                    "at": checked_at,
                }
            )
            if len(c["audit"]) > 512:
                prior = c.get("audit_archive_ref")
                c["audit_archive_ref"] = self._completion_store().put_json(
                    {"previous": prior, "records": c["audit"][:256]}
                )
                c["audit"] = c["audit"][256:]
            s["parent_state"] = (
                "completed"
                if c["state"] == "ACCEPTED"
                else "cancelled"
                if c["state"] == "CANCELLED"
                else "open"
            )
            s["revision"] += 1
            self._save(s)
            self._fault("after_completion_commit")

    def activate_completion(
        self, actor, expected_revision, contract, policy, checked_at, *, dry_run=False
    ):
        clock(checked_at)
        with publisher_lock(self.root / "publisher.lock"):
            s = self.read()
            self._owner(s, actor)
            self._cas(s, expected_revision)
            require(
                s["parent_state"] == "open" and "completion" not in s,
                "COMPLETION_ACTIVATION_REFUSED",
            )
            require(
                not any(a["state"] in {"planned", "unknown"} for a in s["actions"]),
                "LEGACY_COMMAND_RECONCILIATION_REQUIRED",
            )
            contract = contract_shape(contract, s)
            policy = policy_shape(policy)
            require(policy["actor"] == actor, "POLICY_ACTOR_MISMATCH")
            if dry_run:
                return {
                    "status": "ACTIVATION_DRY_RUN",
                    "from_schema": s["schema"],
                    "to_schema": SCHEMA,
                }
            # Capture and reread the actual predecessor before promoting HEAD.
            # Failure leaves the existing v1 HEAD untouched; this backup is state,
            # not a substitute for a reinitialization's full source checkpoint.
            backup_store = self._completion_store()
            activation_backup_ref = backup_store.put_json(s)
            require(
                backup_store.json(activation_backup_ref) == s,
                "ACTIVATION_BACKUP_VERIFICATION_FAILED",
            )
            s["completion"] = c = {
                "schema": SCHEMA,
                "activation_backup_ref": activation_backup_ref,
                "generation": 1,
                "ownership_epoch": 1,
                "cancel_fence": 0,
                "state": "DRAFT",
                "blocker": None,
                "contract": contract,
                "policy": policy,
                "capabilities": {},
                "events": [],
                "event_id_index": {},
                "last_sequence": 0,
                "operations": [],
                "results": {},
                "review": None,
                "handoff": None,
                "delivery": "NOT_DELIVERED",
                "audit": [],
                "paused": False,
                "waiting_user": False,
                "executor_online": True,
                "remaining_budget": copy.deepcopy(contract["budget"]),
                "no_progress": 0,
                "progress_fingerprint": sha(encoded([])),
                "checked_at": checked_at,
                "lease_expires_at": checked_at + contract["limits"]["lease_seconds"],
                "models": {"requested": None, "assigned": None, "actual": "UNKNOWN"},
                "actual_runtime": None,
            }
            # Older Coordinator code refuses this HEAD before any mutable call.
            # An unknown optional field on v1 alone would not fence old writers.
            s["schema"] = "agentos.work-coordination/v2"
            c["state"], c["blocker"] = projection(c, checked_at)
            s["revision"] += 1
            self._save(s)
            return copy.deepcopy(c)

    def completion_heartbeat(self, actor, expected_revision, checked_at):
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            c["lease_expires_at"] = (
                checked_at + c["contract"]["limits"]["lease_seconds"]
            )
        return self.completion_status(checked_at)

    def completion_update_route(
        self, actor, expected_revision, checked_at, *, capabilities=None, policy=None
    ):
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            if capabilities is not None:
                require(
                    isinstance(capabilities, dict) and len(capabilities) <= 7,
                    "INVALID_CAPABILITIES",
                )
                for operation, row in capabilities.items():
                    canonical_operation(operation)
                    require(
                        operation == canonical_operation(operation),
                        "CAPABILITY_ALIAS_NOT_CANONICAL",
                    )
                    require(isinstance(row, dict), "INVALID_CAPABILITIES")
                c["capabilities"] = copy.deepcopy(capabilities)
                c["route_blocker"] = None
                c["executor_online"] = True
            if policy is not None:
                policy = policy_shape(policy)
                require(
                    policy["revision"] > c["policy"]["revision"],
                    "POLICY_REVISION_CONFLICT",
                )
                require(policy["actor"] == actor, "POLICY_ACTOR_MISMATCH")
                c["policy"] = policy
                c["review"] = None
                c["handoff"] = None
                c["delivery"] = "NOT_DELIVERED"
        return self.completion_status(checked_at)

    def completion_route_error(
        self,
        actor,
        expected_revision,
        checked_at,
        *,
        operation,
        target,
        environment,
        error_code,
    ):
        """Record one authenticated adapter error, without platform-wide inference."""
        from .continuation_adapter import OPERATION_ERRORS

        operation = canonical_operation(operation)
        require(error_code in OPERATION_ERRORS, "INVALID_OPERATION_ERROR")
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            require(
                environment == c["contract"]["environment_fingerprint"]
                and any(
                    canonical_operation(r["operation"]) == operation
                    and r["target"] == target
                    for r in c["contract"]["criteria"]
                ),
                "ERROR_ROUTE_BINDING_MISMATCH",
            )
            row = c["capabilities"].get(operation)
            require(
                row and row.get("target_class") == target,
                "ERROR_ROUTE_BINDING_MISMATCH",
            )
            row["status"] = (
                "DENIED"
                if error_code in {"AUTH_REQUIRED", "POLICY_DENIED"}
                else "UNSUPPORTED"
                if error_code == "UNSUPPORTED"
                else "UNKNOWN"
            )
            row["error_code"] = error_code
            row["checked_at"] = checked_at
            c["audit"].append(
                {
                    "kind": "OPERATION_LOCAL_ERROR",
                    "operation": operation,
                    "target": target,
                    "environment": environment,
                    "error_code": error_code,
                    "at": checked_at,
                }
            )
        return self.completion_status(checked_at)

    def completion_goals_opt_in(
        self,
        actor,
        expected_revision,
        checked_at,
        *,
        target,
        receiver,
        data_hash,
        verify_authority=None,
    ):
        """Record scoped consent only; never activate a Goal or change client policy."""
        require(callable(verify_authority), "EXPLICIT_GOALS_OPT_IN_REQUIRED")
        request = {
            "operation": "goals",
            "target": target,
            "receiver": receiver,
            "data_hash": data_hash,
        }
        require(
            verify_authority("goals-opt-in", copy.deepcopy(request)) is True,
            "EXPLICIT_GOALS_OPT_IN_REQUIRED",
        )
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            decision = resolve_completion_capability(
                c["capabilities"], "goals", target, c["contract"]["task_id"], checked_at
            )
            require(
                decision["status"] == "SUPPORTED", decision["reason"] or "UNSUPPORTED"
            )
            policy_check(c, actor, request, checked_at)
            c["goals_opt_in"] = {
                "status": "SCOPED_OPT_IN_RECORDED_NOT_ACTIVATED",
                "task_id": c["contract"]["task_id"],
                "generation": c["generation"],
                **request,
                "policy_revision": c["policy"]["revision"],
                "checked_at": checked_at,
                "policy_scope_hash": sha(encoded(c["policy"]["scope"])),
                "capability_hash": sha(encoded(c["capabilities"]["goals"])),
            }
            c["audit"].append(
                {
                    "kind": "GOALS_SCOPED_OPT_IN",
                    "at": checked_at,
                    "policy_revision": c["policy"]["revision"],
                }
            )
        return copy.deepcopy(self.read()["completion"]["goals_opt_in"])

    def completion_event(self, actor, expected_revision, event, checked_at):
        require(
            isinstance(event, dict)
            and set(event)
            == {
                "schema",
                "event_id",
                "kind",
                "generation",
                "causal_sequence",
                "observed_at",
                "payload",
            }
            and event["schema"] == "agentos.completion-event/v1",
            "INVALID_EVENT",
        )
        valid_id(event["event_id"])
        require(
            event["kind"] in EVENT_PAYLOADS
            and isinstance(event["payload"], dict)
            and set(event["payload"]) == EVENT_PAYLOADS[event["kind"]],
            "INVALID_EVENT_PAYLOAD",
        )
        for key, value in event["payload"].items():
            if key.endswith("_hash"):
                hash_value(value)
            elif key in {"policy_revision", "previous_epoch"}:
                require(type(value) is int and value > 0, "INVALID_EVENT_PAYLOAD")
            elif key == "source_commit":
                require(
                    isinstance(value, str) and re.fullmatch("[0-9a-f]{40,64}", value),
                    "INVALID_EVENT_PAYLOAD",
                )
            else:
                require(
                    isinstance(value, str) and 0 < len(value.strip()) <= 4000,
                    "INVALID_EVENT_PAYLOAD",
                )
        if event["kind"] == "TURN_FINISHED":
            require(
                event["payload"]["status"] in {"COMPLETED", "FAILED", "CANCELLED"},
                "INVALID_EVENT_PAYLOAD",
            )
        if event["kind"] == "TEST_FINISHED":
            require(
                event["payload"]["outcome"] in {"PASS", "FAIL", "BLOCKED"},
                "INVALID_EVENT_PAYLOAD",
            )
        require(
            type(event["generation"]) is int
            and event["generation"] >= 1
            and type(event["causal_sequence"]) is int
            and event["causal_sequence"] >= 1
            and clock(event["observed_at"]) <= checked_at,
            "INVALID_EVENT_ORDER",
        )
        # A byte-identical duplicate is a read, even if its caller CAS is old.
        s = self.read()
        self._owner(s, actor)
        digest = sha(encoded(event))
        consumed = s.get("completion", {}).get("event_id_index", {})
        if event["event_id"] in consumed:
            require(consumed[event["event_id"]] == digest, "EVENT_ID_CONFLICT")
            return self.completion_status(checked_at)
        for old in s.get("completion", {}).get("events", []):
            if old["event_id"] == event["event_id"]:
                require(old["event"] == event, "EVENT_ID_CONFLICT")
                return self.completion_status(checked_at)
        if s["completion"]["state"] in TERMINAL:
            return self.completion_status(checked_at)
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            actionable = (
                event["generation"] == c["generation"]
                and c["state"] not in TERMINAL
                and (
                    event["causal_sequence"] > c["last_sequence"]
                    or event["kind"] == "USER_CANCELLED"
                )
            )
            require(
                len(c["event_id_index"]) < 4096
                or (event["kind"] == "USER_CANCELLED" and actionable),
                "EVENT_INDEX_LIMIT",
            )
            c["event_id_index"][event["event_id"]] = digest
            c["events"].append(
                {
                    "event_id": event["event_id"],
                    "event": copy.deepcopy(event),
                    "actionable": actionable,
                }
            )
            if len(c["events"]) > 256:
                c["event_archive_ref"] = self._completion_store().put_json(
                    {
                        "previous": c.get("event_archive_ref"),
                        "records": c["events"][:128],
                    }
                )
                c["events"] = c["events"][128:]
            if actionable:
                c["last_sequence"] = max(c["last_sequence"], event["causal_sequence"])
                kind = event["kind"]
                if kind == "USER_CANCELLED":
                    c["state"], c["blocker"] = "CANCELLED", "OWNER_CANCELLED"
                    c["cancel_fence"] += 1
                    for op in c["operations"]:
                        if op["state"] == "PREPARED":
                            op["state"] = "CANCELLED"
                elif kind == "EXECUTOR_DISCONNECTED":
                    c["executor_online"] = False
                elif kind == "EXECUTOR_RECONNECTED":
                    c["executor_online"] = True
                elif kind == "CONTRACT_CHANGED":
                    if any(
                        event["payload"][k] != c["contract"][k]
                        for k in ("contract_hash", "source_commit")
                    ):
                        c["waiting_user"] = True
                        c["review"] = None
                        c["delivery"] = "NOT_DELIVERED"
                # Completion/ACK/budget notices never substitute verified receipts.
        return self.completion_status(checked_at)

    def completion_plan(self, actor, expected_revision, checked_at):
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            state, blocker = projection(c, checked_at)
            if state != "READY":
                return {"status": state, "operation": None, "reason": blocker}
            row = copy.deepcopy(
                next(
                    r
                    for r in c["contract"]["criteria"]
                    if not current_result(c, r["criterion_id"])
                )
            )
            attempted = attempted_recipes(c, row)
            if row["recipe_id"] in attempted:
                alternative = next(
                    (
                        a
                        for a in row.get("alternatives", [])
                        if a["recipe_id"] not in attempted
                    ),
                    None,
                )
                require(alternative is not None, "SEMANTIC_PROGRESS_REQUIRED")
                row.update(alternative)
            row.pop("alternatives", None)
            decision = resolve_completion_capability(
                c["capabilities"],
                row["operation"],
                row["target"],
                c["contract"]["task_id"],
                checked_at,
            )
            if decision["status"] != "SUPPORTED":
                c["route_blocker"] = decision["reason"]
                c["executor_online"] = decision["status"] == "DENIED"
                c["audit"].append({"kind": "ROUTE_HELD", **decision, "at": checked_at})
                return {
                    "status": "BLOCKED_POLICY"
                    if decision["status"] == "DENIED"
                    else "WAITING_EXECUTOR",
                    "operation": None,
                    "reason": decision["reason"],
                }
            policy_check(c, actor, row, checked_at)
            key = sha(
                encoded(
                    {
                        "task_id": c["contract"]["task_id"],
                        "generation": c["generation"],
                        "criterion": row["criterion_id"],
                        "recipe": row["recipe_id"],
                        "contract_hash": c["contract"]["contract_hash"],
                    }
                )
            )
            previous = next(
                (o for o in c["operations"] if o["idempotency_key"] == key), None
            )
            if previous is not None:
                require(previous["state"] == "NOT_ADMITTED", "OPERATION_ALREADY_OWNED")
                require(
                    previous["attempt"] < c["contract"]["limits"]["max_attempts"],
                    "RETRY_LIMIT",
                )
                if checked_at < previous["retry_at"]:
                    return {
                        "status": "BACKOFF",
                        "operation": None,
                        "reason": "RETRY_NOT_DUE",
                    }
                require(
                    checked_at < previous["dedup_valid_until"], "DEDUP_HORIZON_EXPIRED"
                )
                previous.update(
                    state="PREPARED",
                    ownership_epoch=c["ownership_epoch"],
                    cancel_fence=c["cancel_fence"],
                )
                op = previous
            else:
                op = {
                    **copy.deepcopy(row),
                    "operation": canonical_operation(row["operation"]),
                    "operation_id": "operation:" + key,
                    "idempotency_key": key,
                    "generation": c["generation"],
                    "ownership_epoch": c["ownership_epoch"],
                    "cancel_fence": c["cancel_fence"],
                    "state": "PREPARED",
                    "attempt": 0,
                    "nonce": None,
                    "admitted": False,
                    "identity": None,
                    "result_ref": None,
                }
                c["operations"].append(op)
            self._fault("before_completion_intent_commit")
            answer = {
                "status": "PREPARED",
                "operation": copy.deepcopy(op),
                "reason": None,
            }
        return answer

    def completion_begin_dispatch(
        self, actor, expected_revision, operation_id, checked_at
    ):
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            require(
                c["state"] not in TERMINAL
                and not c["paused"]
                and not c["waiting_user"],
                "DISPATCH_HELD",
            )
            op = next(
                (o for o in c["operations"] if o["operation_id"] == operation_id), None
            )
            require(op and op["state"] == "PREPARED", "UNKNOWN_EFFECT_NO_RETRY")
            require(
                not any(o["state"] == "UNKNOWN" for o in c["operations"]),
                "UNKNOWN_EFFECT_NO_RETRY",
            )
            policy_check(c, actor, op, checked_at)
            d = resolve_completion_capability(
                c["capabilities"],
                op["operation"],
                op["target"],
                c["contract"]["task_id"],
                checked_at,
            )
            require(d["status"] == "SUPPORTED", d["reason"] or "UNSUPPORTED")
            require(
                budget_available(c, checked_at)
                and c["no_progress"] < c["contract"]["limits"]["max_no_progress"],
                "CONTINUATION_LIMIT",
            )
            cap = c["capabilities"][op["operation"]]
            op["attempt"] += 1
            require(
                op["attempt"] <= c["contract"]["limits"]["max_attempts"], "RETRY_LIMIT"
            )
            identity = {
                "schema": "agentos.completion-admission/v1",
                "task_id": c["contract"]["task_id"],
                **{
                    k: op[k]
                    for k in (
                        "operation_id",
                        "idempotency_key",
                        "generation",
                        "ownership_epoch",
                        "cancel_fence",
                        "attempt",
                        "operation",
                        "target",
                        "receiver",
                        "data_hash",
                    )
                },
                **{k: c["contract"][k] for k in DEPENDENCIES},
                "nonce": uuid.uuid4().hex,
                "policy_revision": c["policy"]["revision"],
                "capability_snapshot_hash": sha(encoded(cap)),
                "capability_checked_at": cap["checked_at"],
                "capability_expires_at": cap["expires_at"],
                "policy_scope_hash": sha(encoded(c["policy"]["scope"])),
                "policy_expires_at": c["policy"]["expires_at"],
                "checked_at": checked_at,
            }
            op.update(
                state="UNKNOWN",
                nonce=identity["nonce"],
                identity=identity,
                admitted=False,
            )
            c["audit"].append(
                {
                    "kind": "DISPATCH_INTENT",
                    "operation_id": operation_id,
                    "nonce": identity["nonce"],
                    "at": checked_at,
                }
            )
        self._fault("after_completion_intent_commit")
        return copy.deepcopy(identity)

    def completion_receiver_admit(self, actor, expected_revision, identity, checked_at):
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            require(
                c["state"] not in TERMINAL
                and not c["paused"]
                and not c["waiting_user"],
                "EFFECT_FENCED",
            )
            require(
                identity["generation"] == c["generation"]
                and identity["ownership_epoch"] == c["ownership_epoch"]
                and identity["cancel_fence"] == c["cancel_fence"],
                "EFFECT_FENCED",
            )
            op = next(
                (
                    o
                    for o in c["operations"]
                    if o["operation_id"] == identity["operation_id"]
                ),
                None,
            )
            require(
                op and op["identity"] == identity and op["state"] == "UNKNOWN",
                "EFFECT_FENCED",
            )
            policy_check(c, actor, op, checked_at)
            cap = c["capabilities"].get(op["operation"])
            require(cap is not None, "UNSUPPORTED")
            validate_completion_freshness(
                {**identity, "checked_at": checked_at},
                sha(encoded(cap)),
                sha(encoded(c["policy"]["scope"])),
                checked_at,
            )
            require(
                identity["policy_revision"] == c["policy"]["revision"], "POLICY_DENIED"
            )
            if op["admitted"]:
                return {
                    "status": "ALREADY_ADMITTED",
                    "identity": copy.deepcopy(identity),
                }
            require(budget_available(c, checked_at), "BUDGET_EXHAUSTED")
            op["admitted"] = True
            c["remaining_budget"]["steps"] -= 1
            c["audit"].append(
                {
                    "kind": "RECEIVER_ADMITTED",
                    "operation_id": op["operation_id"],
                    "nonce": identity["nonce"],
                    "at": checked_at,
                }
            )
        self._fault("after_completion_receiver_admission")
        return {"status": "NEW_ADMISSION", "identity": copy.deepcopy(identity)}

    def completion_wait(self, actor, expected_revision, checked_at, *, waiting_user):
        require(type(waiting_user) is bool, "INVALID_WAIT_STATE")
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            require(c["state"] not in TERMINAL, "TERMINAL_TASK")
            c["waiting_user"] = waiting_user
        return self.completion_status(checked_at)

    def completion_spawn_local(
        self, actor, expected_revision, identity, checked_at, recipe, env
    ):
        """Minimal local receiver critical section: fence check and owned Popen.

        UNKNOWN intent and admission are already durable. Waiting/output/target
        I/O run outside this fence. A cancel/revoke/takeover before this boundary
        cannot start a process; later cancellation cannot erase an admitted effect.
        """
        import subprocess
        from pathlib import Path

        from .project import _stop_check_group

        process = None
        try:
            with self._completion_transaction(actor, expected_revision, checked_at) as (
                s,
                c,
            ):
                require(
                    c["state"] not in TERMINAL
                    and not c["paused"]
                    and not c["waiting_user"],
                    "EFFECT_FENCED",
                )
                require(
                    identity["generation"] == c["generation"]
                    and identity["ownership_epoch"] == c["ownership_epoch"]
                    and identity["cancel_fence"] == c["cancel_fence"],
                    "EFFECT_FENCED",
                )
                op = next(
                    (
                        o
                        for o in c["operations"]
                        if o["operation_id"] == identity["operation_id"]
                    ),
                    None,
                )
                require(
                    op
                    and op["identity"] == identity
                    and op["admitted"]
                    and op["state"] == "UNKNOWN"
                    and not op.get("process"),
                    "EFFECT_FENCED",
                )
                policy_check(c, actor, op, checked_at)
                require(
                    identity["policy_revision"] == c["policy"]["revision"],
                    "POLICY_DENIED",
                )
                cap = c["capabilities"].get(op["operation"])
                require(cap is not None, "UNSUPPORTED")
                validate_completion_freshness(
                    {**identity, "checked_at": checked_at},
                    sha(encoded(cap)),
                    sha(encoded(c["policy"]["scope"])),
                    checked_at,
                )
                require(
                    sha(encoded(recipe)) == op["data_hash"], "REGISTERED_RECIPE_CHANGED"
                )
                process = subprocess.Popen(
                    recipe["argv"],
                    cwd=Path(recipe["workspace"]),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                s["work"][op["work_id"]]["state"] = "running"
                op["process"] = {
                    "pid": process.pid,
                    "argv_hash": sha(encoded(recipe["argv"])),
                    "workspace": str(Path(recipe["workspace"]).resolve()),
                    "nonce": identity["nonce"],
                }
            return process
        except BaseException:
            if process is not None:
                _stop_check_group(process.pid, process)
                if process.stdout is not None:
                    process.stdout.close()
            raise

    def completion_review(
        self, actor, expected_revision, review_ref, checked_at, verify_reviewer
    ):
        require(callable(verify_reviewer), "AUTHENTICATED_REVIEWER_REQUIRED")
        store = self._completion_store()
        review = store.json(review_ref)
        # Actual reviewer authentication/semantic observation is adapter-owned.
        verify_reviewer(copy.deepcopy(review))
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            s,
            c,
        ):
            require(
                c["state"] not in TERMINAL
                and all(
                    current_result(c, r["criterion_id"])
                    for r in c["contract"]["criteria"]
                ),
                "CURRENT_CRITERIA_INCOMPLETE",
            )
            require(
                set(review)
                == {
                    "schema",
                    "reviewer",
                    "generation",
                    *DEPENDENCIES,
                    "result_refs",
                    "blocking_findings",
                    "semantic_acceptance",
                    "docs_consistent",
                    "checked_at",
                    "evidence_refs",
                }
                and review["schema"] == "agentos.completion-review/v1",
                "INVALID_REVIEW",
            )
            require(
                review["reviewer"] == c["contract"]["acceptance_owner"]
                and review["reviewer"] != actor,
                "INDEPENDENT_REVIEW_REQUIRED",
            )
            require(
                review["generation"] == c["generation"]
                and all(review[k] == c["contract"][k] for k in DEPENDENCIES),
                "STALE_REVIEW",
            )
            require(
                review["result_refs"]
                == {
                    k: v["receipt_ref"]
                    for k, v in c["results"].items()
                    if current_result(c, k)
                },
                "STALE_REVIEW",
            )
            require(
                review["blocking_findings"] == []
                and review["semantic_acceptance"] is True
                and review["docs_consistent"] is True,
                "REVIEW_NOT_ACCEPTED",
            )
            require(
                clock(review["checked_at"]) <= checked_at and review["evidence_refs"],
                "INVALID_REVIEW",
            )
            for result in c["results"].values():
                receipt = store.json(result["receipt_ref"])
                for ref in receipt["evidence_refs"]:
                    store.get(ref)
            for ref in review["evidence_refs"]:
                store.get(ref)
            c["review"] = copy.deepcopy(review_ref)
            for work_id, work in s["work"].items():
                criteria = [
                    r["criterion_id"]
                    for r in c["contract"]["criteria"]
                    if r["work_id"] == work_id
                ]
                if criteria and all(
                    current_result(c, criterion) for criterion in criteria
                ):
                    work["state"] = "completed"
                    work["completion_review_ref"] = copy.deepcopy(review_ref)
        return self.completion_status(checked_at)

    def completion_prepare_handoff(
        self,
        actor,
        expected_revision,
        envelope,
        artifact_root,
        checked_at,
        verify_authority,
    ):
        from .handoff import verify_completion_inventory

        require(callable(verify_authority), "CURRENT_HANDOFF_AUTHORITY_REQUIRED")
        verify_authority("artifact_transfer", copy.deepcopy(envelope))
        require(
            isinstance(envelope, dict)
            and set(envelope)
            == {
                "schema",
                "handoff_id",
                "operation_id",
                "task_id",
                "generation",
                "from_ref",
                "to_ref",
                "contract_hash",
                "source_commit",
                "manifest",
                "manifest_hash",
                "remaining_requirements",
                "next_step",
                "policy_scope_ref",
                "expiry",
                "ownership_transition",
                "sender_receipt",
                "authentication_mechanism",
                "target_environment",
            },
            "INVALID_HANDOFF_ENVELOPE",
        )
        require(
            envelope["schema"] == "agentos.completion-handoff/v1",
            "INVALID_HANDOFF_ENVELOPE",
        )
        actual = verify_completion_inventory(artifact_root, envelope["manifest"])
        require(
            envelope["manifest_hash"] == actual["manifest_hash"],
            "HANDOFF_MANIFEST_MISMATCH",
        )
        for key in (
            "handoff_id",
            "operation_id",
            "from_ref",
            "to_ref",
            "policy_scope_ref",
            "authentication_mechanism",
            "target_environment",
        ):
            valid_id(envelope[key])
        require(
            isinstance(envelope["next_step"], str)
            and 0 < len(envelope["next_step"]) <= 4000,
            "NEXT_STEP_REQUIRED",
        )
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            require(
                c["state"] not in TERMINAL
                and clock(envelope["expiry"]) > checked_at
                and envelope["expiry"] - checked_at
                <= c["contract"]["limits"]["ack_timeout"],
                "HANDOFF_EXPIRED",
            )
            require(
                envelope["task_id"] == c["contract"]["task_id"]
                and envelope["generation"] == c["generation"]
                and envelope["from_ref"] == actor
                and all(
                    envelope[k] == c["contract"][k]
                    for k in ("source_commit", "contract_hash")
                ),
                "HANDOFF_BINDING_MISMATCH",
            )
            require(
                all(
                    envelope["manifest"][k] == envelope[k]
                    for k in ("task_id", "generation", "source_commit", "contract_hash")
                ),
                "HANDOFF_BINDING_MISMATCH",
            )
            require(
                envelope["ownership_transition"] in {"KEEP_OWNER", "TRANSFER_OWNER"},
                "INVALID_OWNERSHIP_TRANSITION",
            )
            require(c["handoff"] is None, "HANDOFF_ALREADY_OWNED")
            # Persist transport uncertainty; a sender receipt does not verify reception.
            c["handoff"] = {
                "envelope": copy.deepcopy(envelope),
                "verified_inventory": actual,
                "state": "PREPARED",
                "ack_ref": None,
                "prepared_at": checked_at,
            }
            c["delivery"] = "NOT_DELIVERED"
        return self.completion_status(checked_at)

    def completion_handoff_sent(self, actor, expected_revision, checked_at):
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            require(
                c["handoff"]
                and c["handoff"]["state"] == "PREPARED"
                and c["state"] not in TERMINAL,
                "HANDOFF_NOT_PREPARED",
            )
            c["handoff"]["state"] = "SENT_UNCONFIRMED"
        return self.completion_status(checked_at)

    def completion_ack(
        self, actor, expected_revision, ack_ref, checked_at, verify_receiver
    ):
        require(callable(verify_receiver), "AUTHENTICATED_RECEIVER_VERIFIER_REQUIRED")
        store = self._completion_store()
        ack = store.json(ack_ref)
        from datetime import datetime

        required_ack = {
            "schema_version",
            "purpose",
            "handoff_id",
            "operation_id",
            "task_id",
            "generation",
            "receiver_ref",
            "actual_environment",
            "received_at",
            "status",
            "verification_method",
        }
        allowed_ack = required_ack | {
            "verified_commit",
            "verified_contract_hash",
            "verified_manifest_hash",
            "received_artifact_hashes",
            "accepted_scope",
            "next_step",
            "can_mutate",
            "commit_status",
            "reason_code",
        }
        require(
            isinstance(ack, dict)
            and required_ack <= set(ack) <= allowed_ack
            and ack["schema_version"] == "1.0.0",
            "INVALID_RECEIVER_ACK",
        )
        try:
            received = datetime.fromisoformat(ack["received_at"])
            require(received.tzinfo is not None, "ACK_TIME_REQUIRED")
            received_at = int(received.timestamp())
        except (ValueError, TypeError, OverflowError) as exc:
            from .handoff_store import HandoffError

            raise HandoffError("ACK_TIME_REQUIRED") from exc
        prior = self.read()
        self._owner(prior, actor)
        prior_handoff = prior["completion"]["handoff"]
        if (
            prior_handoff
            and prior_handoff["ack_ref"] == ack_ref
            and prior_handoff["state"] in {"ACKED", "ACK_VERIFIED_PENDING_TRANSFER"}
        ):
            return self.completion_status(checked_at)
        # The actual receiver reads target bytes/checkout/dependencies via its route.
        receiver_evidence = verify_receiver(copy.deepcopy(ack))
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            h = c["handoff"]
            require(h is not None, "HANDOFF_NOT_PREPARED")
            e = h["envelope"]
            require(
                h["prepared_at"] <= received_at <= checked_at,
                "ACK_TIME_OUTSIDE_HANDOFF",
            )
            if c["state"] == "CANCELLED":
                c["audit"].append({"kind": "LATE_ACK_AFTER_CANCEL", "ack_ref": ack_ref})
                return {"status": "AUDIT_ONLY", "delivery_status": "NOT_DELIVERED"}
            require(c["state"] not in TERMINAL, "TERMINAL_TASK")
            require(h["state"] == "SENT_UNCONFIRMED", "HANDOFF_TRANSPORT_NOT_RECORDED")
            require(ack.get("status") in {"ACKED", "REJECTED"}, "INVALID_RECEIVER_ACK")
            require(
                all(
                    ack.get(k) == e[k]
                    for k in ("handoff_id", "operation_id", "task_id", "generation")
                )
                and ack.get("receiver_ref") == e["to_ref"],
                "ACK_BINDING_MISMATCH",
            )
            if ack["status"] == "REJECTED":
                require(ack.get("reason_code"), "REJECTION_REASON_REQUIRED")
                h.update(state="REJECTED", ack_ref=copy.deepcopy(ack_ref))
                c["delivery"] = "NOT_DELIVERED"
                c["audit"].append(
                    {"kind": "REJECTED_HANDOFF", "reason": ack["reason_code"]}
                )
                return {"status": "REJECTED", "delivery_status": "NOT_DELIVERED"}
            require(
                checked_at < e["expiry"]
                and checked_at < c["policy"]["expires_at"]
                and not c["policy"]["revoked"],
                "ACK_SCOPE_EXPIRED",
            )
            require(
                ack.get("purpose") == "EXECUTION_HANDOFF"
                and ack.get("commit_status") == "VERIFIED"
                and ack.get("verified_commit") == e["source_commit"]
                and ack.get("verified_contract_hash") == e["contract_hash"]
                and ack.get("verified_manifest_hash") == e["manifest_hash"]
                and ack.get("received_artifact_hashes")
                == h["verified_inventory"]["artifact_hashes"]
                and ack.get("next_step") == e["next_step"]
                and ack.get("actual_environment") == e["target_environment"]
                and ack.get("accepted_scope") == [e["policy_scope_ref"]],
                "ACK_BYTES_OR_SCOPE_MISMATCH",
            )
            require(
                receiver_evidence
                == {
                    "manifest_hash": e["manifest_hash"],
                    "artifact_hashes": h["verified_inventory"]["artifact_hashes"],
                    "source_commit": e["source_commit"],
                    "contract_hash": e["contract_hash"],
                    "receiver_ref": e["to_ref"],
                    "environment": e["target_environment"],
                },
                "ACTUAL_RECEIVER_EVIDENCE_REQUIRED",
            )
            require(type(ack.get("can_mutate")) is bool, "INVALID_RECEIVER_ACK")
            if e["ownership_transition"] == "TRANSFER_OWNER":
                require(
                    ack["can_mutate"] is True, "RECEIVER_MUTATION_CAPABILITY_REQUIRED"
                )
            if e["ownership_transition"] == "TRANSFER_OWNER":
                # Receipt verification fences the source immediately. Delivery is
                # not accepted until ACK+ownership are applied in takeover's commit.
                h.update(
                    state="ACK_VERIFIED_PENDING_TRANSFER",
                    ack_ref=copy.deepcopy(ack_ref),
                )
                c["paused"] = True
                c["delivery"] = "NOT_DELIVERED"
            else:
                h.update(state="ACKED", ack_ref=copy.deepcopy(ack_ref))
                c["delivery"] = "ACKED"
        return self.completion_status(checked_at)

    def completion_accept(
        self, actor, expected_revision, checked_at, verify_acceptance=None
    ):
        store = self._completion_store()
        require(callable(verify_acceptance), "CURRENT_ACCEPTANCE_VERIFIER_REQUIRED")
        verify_acceptance(copy.deepcopy(self.read()["completion"]))
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            s,
            c,
        ):
            require(
                projection(c, checked_at)[0] == "VERIFYING"
                and not c["paused"]
                and c["review"]
                and c["delivery"] == "ACKED"
                and c["handoff"]["ack_ref"],
                "ACCEPTANCE_INCOMPLETE",
            )
            require(
                checked_at < c["handoff"]["envelope"]["expiry"], "ACK_SCOPE_EXPIRED"
            )
            require(
                not any(o["state"] in {"UNKNOWN", "PREPARED"} for o in c["operations"]),
                "UNKNOWN_EFFECT_NO_RETRY",
            )
            require(
                all(
                    w["state"] == "completed"
                    and w.get("completion_review_ref") == c["review"]
                    for w in s["work"].values()
                    if w["required"]
                ),
                "PARENT_SCOPE_INCOMPLETE",
            )
            review = store.json(c["review"])
            require(
                review["generation"] == c["generation"]
                and all(review[k] == c["contract"][k] for k in DEPENDENCIES),
                "STALE_REVIEW",
            )
            for result in c["results"].values():
                receipt = store.json(result["receipt_ref"])
                for ref in receipt["evidence_refs"]:
                    store.get(ref)
            store.get(c["handoff"]["ack_ref"])
            c.update(state="ACCEPTED", blocker=None)
            s["goal_acceptance"] = {
                "schema": "agentos.completion-acceptance/v1",
                "review_ref": c["review"],
                "receiver_ack_ref": c["handoff"]["ack_ref"],
                "original_goal": s["goal"],
                "generation": c["generation"],
                "checked_at": checked_at,
            }
        return self.completion_status(checked_at)

    def completion_change_contract(
        self, actor, expected_revision, contract, checked_at, verify_authority
    ):
        require(callable(verify_authority), "CURRENT_CONTRACT_AUTHORITY_REQUIRED")
        verify_authority("contract-change", copy.deepcopy(contract))
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            s,
            c,
        ):
            require(c["state"] not in TERMINAL, "TERMINAL_TASK")
            for work in s["work"].values():
                work.pop("completion_review_ref", None)
                if work["required"]:
                    work["state"] = "pending"
            replacement = contract_shape(contract, s)
            require(
                replacement["task_id"] == c["contract"]["task_id"],
                "TASK_IDENTITY_MISMATCH",
            )
            c["audit"].append(
                {
                    "kind": "CONTRACT_INVALIDATED",
                    "previous": copy.deepcopy(c["contract"]),
                    "results": copy.deepcopy(c["results"]),
                    "review": c["review"],
                    "handoff": c["handoff"],
                }
            )
            c["contract"] = replacement
            c["generation"] += 1
            c["cancel_fence"] += 1
            c["results"], c["review"], c["handoff"] = {}, None, None
            c["delivery"] = "NOT_DELIVERED"
            c["waiting_user"] = False
            c["no_progress"] = 0
            c["progress_fingerprint"] = sha(encoded([]))
            for op in c["operations"]:
                if op["state"] == "PREPARED":
                    op["state"] = "SUPERSEDED"
            # Unresolved old effects remain in the same ledger and still block work.
        return self.completion_status(checked_at)

    def completion_takeover(
        self, new_actor, expected_revision, checked_at, proof_ref, verify_target, policy
    ):
        require(callable(verify_target), "CURRENT_TARGET_VERIFIER_REQUIRED")
        valid_id(new_actor)
        store = self._completion_store()
        proof = store.json(proof_ref)
        verify_target(
            copy.deepcopy(proof)
        )  # Authenticate target and current scope outside lock.
        clock(checked_at)
        with publisher_lock(self.root / "publisher.lock"):
            s = self.read()
            self._cas(s, expected_revision)
            c = s["completion"]
            require(
                c["state"] not in TERMINAL and checked_at >= c["checked_at"],
                "TAKEOVER_REFUSED",
            )
            require(
                set(proof)
                == {
                    "schema",
                    "mode",
                    "task_id",
                    "previous_owner",
                    "new_owner",
                    "generation",
                    "previous_epoch",
                    "policy_revision",
                    "checked_at",
                    "evidence_refs",
                    "old_writer_quiescent",
                    "reconciled_operation_ids",
                    "receiver_fence_verified",
                }
                and proof["schema"] == "agentos.completion-takeover/v1",
                "INVALID_TAKEOVER_PROOF",
            )
            require(
                proof["task_id"] == c["contract"]["task_id"]
                and proof["previous_owner"] == s["owner"]
                and proof["new_owner"] == new_actor
                and proof["generation"] == c["generation"]
                and proof["previous_epoch"] == c["ownership_epoch"]
                and proof["policy_revision"] == c["policy"]["revision"]
                and proof["checked_at"] == checked_at
                and proof["evidence_refs"],
                "STALE_TAKEOVER_PROOF",
            )
            for ref in proof["evidence_refs"]:
                store.get(ref)
            unknown = [
                o["operation_id"] for o in c["operations"] if o["state"] == "UNKNOWN"
            ]
            if proof["mode"] == "EFFECT_FENCED":
                require(
                    proof["receiver_fence_verified"] is True, "BLOCKED_UNSAFE_TAKEOVER"
                )
            elif proof["mode"] == "QUIESCENCE_REQUIRED":
                require(
                    proof["old_writer_quiescent"] is True
                    and not unknown
                    and set(proof["reconciled_operation_ids"])
                    >= {
                        o["operation_id"]
                        for o in c["operations"]
                        if o["identity"] is not None
                    },
                    "BLOCKED_UNSAFE_TAKEOVER",
                )
            else:
                require(False, "BLOCKED_UNSAFE_TAKEOVER")
            policy = policy_shape(policy)
            require(
                policy["actor"] == new_actor
                and policy["revision"] > c["policy"]["revision"]
                and not policy["revoked"]
                and checked_at < policy["expires_at"],
                "POLICY_DENIED",
            )
            if (
                c["handoff"]
                and c["handoff"]["envelope"]["ownership_transition"] == "TRANSFER_OWNER"
            ):
                require(
                    c["handoff"]["state"] == "ACK_VERIFIED_PENDING_TRANSFER"
                    and c["handoff"]["ack_ref"]
                    and c["handoff"]["envelope"]["to_ref"] == new_actor
                    and checked_at < c["handoff"]["envelope"]["expiry"],
                    "VERIFIED_ACK_REQUIRED",
                )
            require(
                new_actor != c["contract"]["acceptance_owner"],
                "INDEPENDENT_REVIEW_REQUIRED",
            )
            s["owner"] = new_actor
            c["policy"] = policy
            c["ownership_epoch"] += 1
            c["cancel_fence"] += 1
            c["lease_expires_at"] = (
                checked_at + c["contract"]["limits"]["lease_seconds"]
            )
            c["checked_at"] = checked_at
            c["review"] = None
            if (
                c["handoff"]
                and c["handoff"]["state"] == "ACK_VERIFIED_PENDING_TRANSFER"
            ):
                c["handoff"]["state"] = "ACKED"
                c["delivery"] = "ACKED"
                c["paused"] = False
            else:
                c["handoff"], c["delivery"] = None, "NOT_DELIVERED"
            for op in c["operations"]:
                if op["state"] == "PREPARED":
                    op["state"] = "SUPERSEDED"
            c["audit"].append(
                {"kind": "VERIFIED_TAKEOVER", "proof_ref": proof_ref, "at": checked_at}
            )
            c["state"], c["blocker"] = projection(c, checked_at)
            s["revision"] += 1
            self._save(s)
        return self.completion_status(checked_at)

    def completion_checkpoint(
        self, actor, expected_revision, checked_at, workspace, paths, verify_target
    ):
        from pathlib import Path

        from .handoff_store import bounded
        from .safeio import filemap, within

        require(callable(verify_target), "EXACT_CHECKPOINT_TARGET_REQUIRED")
        target = verify_target("checkpoint", str(Path(workspace).resolve()))
        require(
            isinstance(target, dict)
            and set(target)
            == {
                "target_ref",
                "environment",
                "source_commit",
                "branch",
                "process_inventory",
                "ownership_verified",
                "source_manifest",
            },
            "INVALID_CHECKPOINT_TARGET",
        )
        require(target["ownership_verified"] is True, "CHECKPOINT_OWNERSHIP_UNKNOWN")
        require(
            isinstance(paths, list)
            and 0 < len(paths) <= 256
            and len(set(paths)) == len(paths),
            "INVALID_CHECKPOINT_PATHS",
        )
        root = Path(workspace)
        require(root.is_dir() and not root.is_symlink(), "INVALID_CHECKPOINT_WORKSPACE")
        source = target["source_manifest"]
        require(
            isinstance(source, dict)
            and set(source)
            == {
                "schema",
                "tracked_paths",
                "untracked_paths",
                "dirty_patch_path",
                "inventory_sha256",
            }
            and source["schema"] == "agentos.completion-source-checkpoint/v1",
            "SOURCE_CHECKPOINT_REQUIRED",
        )
        tracked, untracked = source["tracked_paths"], source["untracked_paths"]
        require(
            isinstance(tracked, list)
            and tracked
            and isinstance(untracked, list)
            and len(set(tracked + untracked)) == len(tracked + untracked),
            "INVALID_SOURCE_CHECKPOINT",
        )
        require(
            isinstance(source["dirty_patch_path"], str)
            and source["dirty_patch_path"] not in tracked + untracked,
            "DIRTY_PATCH_REQUIRED",
        )
        actual_inventory = {
            k: v
            for k, v in filemap(
                root, skip={".git", ".agentos"}, limit=257, max_bytes=64 * 1024 * 1024
            ).items()
            if k not in {".git", ".agentos"}
        }
        require(
            set(actual_inventory)
            == set(paths)
            == set(tracked + untracked + [source["dirty_patch_path"]])
            and source["inventory_sha256"] == sha(encoded(actual_inventory)),
            "INCOMPLETE_WORKSPACE_CHECKPOINT",
        )
        store = self._completion_store()
        import shutil

        needed = sum((root / name).stat().st_size for name in paths) + 8 * 1024 * 1024
        require(
            shutil.disk_usage(store.root).free >= needed, "CHECKPOINT_SPACE_REQUIRED"
        )
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            # Pausing must commit before capture; never start a new action during backup.
            c["paused"] = True
            c["audit"].append({"kind": "CHECKPOINT_PAUSED", "at": checked_at})
        state = self.read()
        require(
            target["source_commit"] == state["completion"]["contract"]["source_commit"]
            and target["environment"]
            == state["completion"]["contract"]["environment_fingerprint"],
            "CHECKPOINT_TARGET_MISMATCH",
        )
        captures = []
        total = 0
        for name in paths:
            require(
                not name.startswith((".git/", ".agentos/"))
                and name not in {".git", ".agentos"},
                "PRIVATE_METADATA_NOT_CAPTURED",
            )
            data = bounded(within(root, name, allow_missing=False))
            total += len(data)
            require(total <= 64 * 1024 * 1024, "SIZE_LIMIT")
            captures.append(
                {
                    "path": name,
                    "size_bytes": len(data),
                    "sha256": sha(data),
                    "ref": store.put(data, "application/octet-stream"),
                }
            )
        require(
            sha(encoded({item["path"]: item["sha256"] for item in captures}))
            == source["inventory_sha256"],
            "SOURCE_CHANGED_DURING_CHECKPOINT",
        )
        snapshot_ref = store.put_json(state)
        checkpoint = {
            "schema": "agentos.completion-checkpoint/v1",
            "snapshot_ref": snapshot_ref,
            "captures": captures,
            "target": target,
            "checked_at": checked_at,
            "generation": state["completion"]["generation"],
            "ownership_epoch": state["completion"]["ownership_epoch"],
        }
        reference = store.put_json(checkpoint)
        # Immediately read every captured byte; a saved pointer is not a verified backup.
        self.completion_verify_checkpoint(reference)
        return {
            "status": "CHECKPOINT_VERIFIED",
            "checkpoint_ref": reference,
            "revision": state["revision"],
            "dispatch_paused": True,
        }

    def completion_verify_checkpoint(self, checkpoint_ref):
        store = self._completion_store()
        checkpoint = store.json(checkpoint_ref)
        require(
            set(checkpoint)
            == {
                "schema",
                "snapshot_ref",
                "captures",
                "target",
                "checked_at",
                "generation",
                "ownership_epoch",
            }
            and checkpoint["schema"] == "agentos.completion-checkpoint/v1",
            "INVALID_CHECKPOINT",
        )
        state = store.json(checkpoint["snapshot_ref"])
        require(
            state["completion"]["schema"] == SCHEMA
            and state["completion"]["paused"] is True
            and state["completion"]["generation"] == checkpoint["generation"]
            and state["completion"]["ownership_epoch"] == checkpoint["ownership_epoch"],
            "INVALID_CHECKPOINT",
        )
        for capture in checkpoint["captures"]:
            data = store.get(capture["ref"])
            require(
                len(data) == capture["size_bytes"] and sha(data) == capture["sha256"],
                "CHECKPOINT_BYTES_MISMATCH",
            )
        return checkpoint, state

    def completion_rehearse_restore(self, checkpoint_ref, destination):
        from pathlib import Path

        from .handoff_store import durable
        from .safeio import within

        checkpoint, state = self.completion_verify_checkpoint(checkpoint_ref)
        target = Path(destination)
        require(
            not target.exists() and not target.is_symlink(),
            "RESTORE_DESTINATION_EXISTS",
        )
        target.mkdir(mode=0o700, parents=True)
        store = self._completion_store()
        for capture in checkpoint["captures"]:
            durable(
                within(target, capture["path"]),
                store.get(capture["ref"]),
                immutable=True,
            )
        for capture in checkpoint["captures"]:
            require(
                sha(within(target, capture["path"]).read_bytes()) == capture["sha256"],
                "RESTORE_BYTES_MISMATCH",
            )
        # Reconstruct the paused coordinator and every completion-owned object
        # in a disposable namespace, rather than verify source files alone.
        recovery_root = (
            target
            / ".agentos-recovery"
            / "state"
            / "work-coordination"
            / self.root.name
        )
        recovery = Store(recovery_root, "completion-evidence")
        seen = set()

        def transfer(value, depth=0):
            require(depth <= 32, "CHECKPOINT_REFERENCE_DEPTH")
            if isinstance(value, dict):
                if set(value) == {"object_id", "locator", "size_bytes", "media_type"}:
                    if not value["locator"].startswith("aos://completion-evidence/"):
                        return  # External Library refs stay protected; not loaded implicitly.
                    if value["object_id"] in seen:
                        return
                    seen.add(value["object_id"])
                    require(len(seen) <= 1024, "SIZE_LIMIT")
                    raw = store.get(value)
                    require(
                        recovery.put(raw, value["media_type"]) == value,
                        "RESTORE_OBJECT_MISMATCH",
                    )
                    if value["media_type"] == "application/json":
                        from .handoff_store import parse

                        transfer(parse(raw), depth + 1)
                else:
                    for item in value.values():
                        transfer(item, depth + 1)
            elif isinstance(value, list):
                for item in value:
                    transfer(item, depth + 1)

        transfer(checkpoint_ref)
        digest = sha(encoded(state))
        durable(
            recovery_root / "snapshots" / (digest + ".json"),
            encoded(state),
            immutable=True,
        )
        durable(
            recovery_root / "HEAD.json",
            encoded(
                {
                    "schema": state["schema"],
                    "revision": state["revision"],
                    "snapshot_sha256": digest,
                    "size_bytes": len(encoded(state)),
                }
            ),
            immutable=True,
        )
        from .work_coordination import Coordinator

        recovered = Coordinator(recovery_root.parents[2], recovery_root.name)
        require(
            recovered.read() == state
            and recovered.read()["completion"]["paused"] is True,
            "RESTORE_STATE_MISMATCH",
        )
        return {
            "schema": "agentos.completion-restore-rehearsal/v1",
            "checkpoint_ref": checkpoint_ref,
            "snapshot_sha256": sha(encoded(state)),
            "artifact_hashes": [v["sha256"] for v in checkpoint["captures"]],
            "destination_verified": True,
            "processes_started": False,
            "recovered_store_sha256": sha(encoded(recovered.read())),
            "captured_objects": len(seen),
        }

    def completion_restore(
        self,
        actor,
        expected_revision,
        checked_at,
        checkpoint_ref,
        rehearsal_ref,
        verify_target,
        *,
        target_schema=SCHEMA,
    ):
        require(target_schema == SCHEMA, "UNSUPPORTED_COMPLETION_DOWNGRADE")
        require(callable(verify_target), "EXACT_RESTORE_TARGET_REQUIRED")
        checkpoint, previous = self.completion_verify_checkpoint(checkpoint_ref)
        store = self._completion_store()
        rehearsal = store.json(rehearsal_ref)
        require(
            rehearsal.get("schema") == "agentos.completion-restore-rehearsal/v1"
            and rehearsal.get("checkpoint_ref") == checkpoint_ref
            and rehearsal.get("snapshot_sha256") == sha(encoded(previous))
            and rehearsal.get("recovered_store_sha256") == sha(encoded(previous))
            and rehearsal.get("artifact_hashes")
            == [v["sha256"] for v in checkpoint["captures"]]
            and rehearsal.get("destination_verified") is True,
            "RESTORE_REHEARSAL_REQUIRED",
        )
        target_proof = verify_target("restore", copy.deepcopy(checkpoint))
        require(
            isinstance(target_proof, dict)
            and set(target_proof)
            == {
                "target_ref",
                "environment",
                "source_commit",
                "old_writer_quiescent",
                "receiver_fence_verified",
                "reconciled_operation_ids",
                "current_authority",
                "restored_artifact_hashes",
            },
            "INVALID_RESTORE_TARGET",
        )
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _s,
            c,
        ):
            require(
                c["paused"] and target_proof["current_authority"] is True,
                "RESTORE_SCOPE_REQUIRED",
            )
            require(
                all(
                    target_proof[k] == checkpoint["target"][k]
                    for k in ("target_ref", "environment", "source_commit")
                )
                and target_proof["restored_artifact_hashes"]
                == [v["sha256"] for v in checkpoint["captures"]],
                "RESTORE_TARGET_MISMATCH",
            )
            require(
                all(
                    c["contract"][k] == previous["completion"]["contract"][k]
                    for k in DEPENDENCIES
                ),
                "RESTORE_DEPENDENCY_MISMATCH",
            )
            require(
                target_proof["receiver_fence_verified"] is True
                or (
                    target_proof["old_writer_quiescent"] is True
                    and not any(o["state"] == "UNKNOWN" for o in c["operations"])
                    and set(target_proof["reconciled_operation_ids"])
                    >= {o["operation_id"] for o in c["operations"] if o["identity"]}
                ),
                "BLOCKED_UNSAFE_TAKEOVER",
            )
            # Keep newer cancellation/policy/ledger facts; never roll back external truth.
            c["generation"] += 1
            c["ownership_epoch"] += 1
            c["cancel_fence"] += 1
            c["lease_expires_at"] = (
                checked_at + c["contract"]["limits"]["lease_seconds"]
            )
            c["review"], c["handoff"], c["delivery"] = None, None, "NOT_DELIVERED"
            for result in c["results"].values():
                receipt = store.json(result["receipt_ref"])
                for ref in receipt["evidence_refs"]:
                    store.get(ref)
                # Exact dependencies and restored bytes were independently revalidated.
                result["restored_from_generation"] = result["generation"]
                result["generation"] = c["generation"]
                result["restore_validation_ref"] = rehearsal_ref
            for op in c["operations"]:
                if op["state"] == "PREPARED":
                    op["state"] = "SUPERSEDED"
            c["paused"] = False
            c["audit"].append(
                {
                    "kind": "VERIFIED_RESTORE",
                    "checkpoint_ref": checkpoint_ref,
                    "rehearsal_ref": rehearsal_ref,
                    "target_proof": target_proof,
                    "at": checked_at,
                }
            )
        return self.completion_status(checked_at)

    def completion_record_result(
        self,
        actor,
        expected_revision,
        identity,
        receipt_ref,
        checked_at,
        verify_execution=None,
    ):
        store = self._completion_store()
        receipt = store.json(receipt_ref)
        require(callable(verify_execution), "AUTHENTICATED_EXECUTION_VERIFIER_REQUIRED")
        require(
            verify_execution(copy.deepcopy(receipt), copy.deepcopy(identity)) is True,
            "HOST_EVIDENCE_REQUIRED",
        )
        from .result_gate import verify_completion_execution

        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            op = next(
                (
                    o
                    for o in c["operations"]
                    if o["operation_id"] == identity["operation_id"]
                ),
                None,
            )
            require(
                op and op["identity"] == identity and op["admitted"],
                "RESULT_IDENTITY_MISMATCH",
            )
            if op["result_ref"] == receipt_ref:
                return self.completion_status(checked_at)
            require(op["state"] == "UNKNOWN", "RESULT_ALREADY_RECORDED")
            verify_completion_execution(receipt, identity, op, store)
            op.update(state="COMPLETED", result_ref=copy.deepcopy(receipt_ref))
            op["usage"] = {
                "tokens": receipt["tokens"],
                "cost_units": receipt["cost_units"],
                "runtime": receipt["runtime"],
            }
            current = (
                identity["generation"] == c["generation"]
                and identity["ownership_epoch"] == c["ownership_epoch"]
                and identity["cancel_fence"] == c["cancel_fence"]
                and c["state"] not in TERMINAL
                and all(identity[k] == c["contract"][k] for k in DEPENDENCIES)
            )
            if current:
                c["actual_runtime"] = receipt["runtime"]
                c["remaining_budget"]["tokens"] = max(
                    0, c["remaining_budget"]["tokens"] - receipt["tokens"]
                )
                c["remaining_budget"]["cost_units"] = max(
                    0, c["remaining_budget"]["cost_units"] - receipt["cost_units"]
                )
                result = {
                    **{k: receipt[k] for k in DEPENDENCIES},
                    "generation": c["generation"],
                    "criterion_id": op["criterion_id"],
                    "status": receipt["status"],
                    "receipt_ref": copy.deepcopy(receipt_ref),
                    "run_id": receipt["run_id"],
                }
                c["results"][op["criterion_id"]] = result
                fingerprint = sha(
                    encoded(sorted(k for k in c["results"] if current_result(c, k)))
                )
                c["no_progress"] = (
                    0
                    if fingerprint != c["progress_fingerprint"]
                    else c["no_progress"] + 1
                )
                c["progress_fingerprint"] = fingerprint
                c["review"] = None
                c["handoff"] = None
                c["delivery"] = "NOT_DELIVERED"
            else:
                c["audit"].append(
                    {
                        "kind": "LATE_RESULT_AUDIT_ONLY",
                        "operation_id": op["operation_id"],
                    }
                )
        self._fault("after_completion_result_commit")
        return self.completion_status(checked_at)

    def completion_reconcile(
        self, actor, expected_revision, operation_id, checked_at, verify_operation
    ):
        require(callable(verify_operation), "EXACT_OPERATION_VERIFIER_REQUIRED")
        s = self.read()
        self._owner(s, actor)
        op = next(
            (
                o
                for o in s["completion"]["operations"]
                if o["operation_id"] == operation_id
            ),
            None,
        )
        require(op and op["state"] == "UNKNOWN", "NO_UNKNOWN_OPERATION")
        identity = copy.deepcopy(op["identity"])
        proof_ref = verify_operation(identity)  # External query outside the state lock.
        if proof_ref is None:
            return {"status": "UNKNOWN", "operation_id": operation_id}
        proof = self._completion_store().json(proof_ref)
        require(
            proof.get("schema") == "agentos.completion-reconciliation/v1"
            and set(proof)
            == {
                "schema",
                "operation_id",
                "nonce",
                "generation",
                "ownership_epoch",
                "outcome",
                "evidence_hash",
                "checked_at",
                "provider",
                "authoritative",
                "dedup_valid_until",
                "processing_horizon",
            },
            "INVALID_RECONCILIATION",
        )
        require(
            all(
                proof[k] == identity[k]
                for k in ("operation_id", "nonce", "generation", "ownership_epoch")
            ),
            "RECONCILIATION_IDENTITY_MISMATCH",
        )
        hash_value(proof["evidence_hash"])
        valid_id(proof["provider"])
        require(
            identity["checked_at"] <= clock(proof["checked_at"]) <= checked_at,
            "INVALID_RECONCILIATION_TIME",
        )
        # Hash must identify independently retrieved bytes in the same evidence store.
        from .handoff_store import bounded

        store = self._completion_store()
        digest = proof["evidence_hash"]
        evidence_path = store.path(f"objects/sha256/{digest[:2]}/{digest}")
        require(
            evidence_path.is_file() and not evidence_path.is_symlink(),
            "RECONCILIATION_EVIDENCE_REQUIRED",
        )
        require(
            sha(bounded(evidence_path)) == digest, "RECONCILIATION_EVIDENCE_REQUIRED"
        )
        require(
            proof["outcome"]
            in {
                "COMPLETED",
                "RUNNING",
                "ADMITTED",
                "UNKNOWN",
                "CONFIRMED_NOT_ADMITTED",
            },
            "INVALID_RECONCILIATION",
        )
        with self._completion_transaction(actor, expected_revision, checked_at) as (
            _,
            c,
        ):
            live = next(o for o in c["operations"] if o["operation_id"] == operation_id)
            require(
                live["identity"] == identity and live["state"] == "UNKNOWN",
                "RECONCILIATION_CONFLICT",
            )
            c["audit"].append(
                {"kind": "RECONCILIATION", "proof_ref": proof_ref, "at": checked_at}
            )
            if proof["outcome"] == "CONFIRMED_NOT_ADMITTED":
                require(
                    proof["authoritative"] is True
                    and not live["admitted"]
                    and clock(proof["dedup_valid_until"]) > checked_at
                    and clock(proof["processing_horizon"])
                    <= proof["dedup_valid_until"],
                    "UNKNOWN_EFFECT_NO_RETRY",
                )
                delay = c["contract"]["limits"]["backoff"][min(live["attempt"] - 1, 2)]
                jitter = int(live["idempotency_key"][:2], 16) % 3
                live.update(
                    state="NOT_ADMITTED",
                    retry_at=checked_at + delay + jitter,
                    dedup_valid_until=proof["dedup_valid_until"],
                )
            elif proof["outcome"] == "COMPLETED" and proof["authoritative"] is True:
                # A terminal operation fact is not a test result or goal acceptance.
                live.update(state="RECONCILED", reconciliation_ref=proof_ref)
        return self.completion_status(checked_at)

    def completion_status(self, checked_at):
        clock(checked_at)
        s = self.read()
        c = s.get("completion")
        require(c and c.get("schema") == SCHEMA, "COMPLETION_NOT_ACTIVATED")
        state, blocker = projection(c, checked_at)
        return {
            "schema": "agentos.completion-status/v1",
            "revision": s["revision"],
            "project_state": state,
            "parent_state": s["parent_state"],
            "owner": s["owner"],
            "generation": c["generation"],
            "ownership_epoch": c["ownership_epoch"],
            "observed_at": c["checked_at"],
            "source": "verified-coordinator-HEAD",
            "fresh": checked_at < c["lease_expires_at"],
            "blocker": blocker,
            "age_seconds": max(0, checked_at - c["checked_at"]),
            "status_freshness": "CURRENT"
            if c["checked_at"] <= checked_at < c["lease_expires_at"]
            else "STALE",
            "remaining": [
                r["criterion_id"]
                for r in c["contract"]["criteria"]
                if not current_result(c, r["criterion_id"])
            ],
            "next_step": "reconcile"
            if state == "BLOCKED_UNKNOWN_OUTCOME"
            else "review-and-deliver"
            if state == "VERIFYING"
            else "bounded-step"
            if state == "READY"
            else None,
            "next_owner": s["owner"],
            "delivery_status": c["delivery"],
            "models": copy.deepcopy(c["models"]),
            "actual_runtime": c["actual_runtime"],
            "unknown_operations": [
                o["operation_id"] for o in c["operations"] if o["state"] == "UNKNOWN"
            ],
            "project_completion_proven": state == "ACCEPTED",
            "native_hooks": "DISABLED",
        }

    def completion_public_status(self, checked_at):
        """Explicit bounded presentation, without owner/host/task/process IDs."""
        actual = self.completion_status(checked_at)
        keys = (
            "project_state",
            "parent_state",
            "observed_at",
            "source",
            "fresh",
            "age_seconds",
            "status_freshness",
            "blocker",
            "next_step",
            "delivery_status",
            "project_completion_proven",
            "native_hooks",
        )
        return {
            "schema": "agentos.completion-public-status/v1",
            **{k: actual[k] for k in keys},
            "remaining_criteria": len(actual["remaining"]),
            "unknown_operations": len(actual["unknown_operations"]),
            "actual_model": actual["models"]["actual"],
        }
