"""Synchronous local coordination ledger; adapters own actual session/target I/O.

Immutable snapshots and a hash-bound HEAD retain one logical owner's decisions.
Actor/provider labels are trusted adapter inputs, not identity authentication.
Nothing here launches work, sends messages, executes archived actions or grants
authority. Unknown effects never turn into a retry because time has elapsed.
"""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from .handoff_store import (
    HandoffError,
    bounded,
    durable,
    encoded,
    parse,
    publisher_lock,
    require,
    scan_secrets,
    sha,
    valid_id,
)
from .overlay import validate_roots
from .safeio import identifier, now, within

SCHEMA = "agentos.work-coordination/v1"
LIMIT = 1024 * 1024
ACTION_KINDS = {
    "continue",
    "review",
    "next-stage",
    "verify-goal",
    "verify-target",
    "replan",
    "inspect-progress",
    "owner-decision",
}


def text(value):
    require(isinstance(value, str) and 0 < len(value.strip()) <= 4000, "INVALID_INPUT")
    return value


def session(value):
    require(
        isinstance(value, dict)
        and set(value) == {"session_id", "kind", "parent_session_id"},
        "INVALID_SESSION",
    )
    valid_id(value["session_id"])
    require(value["kind"] in {"session", "subagent"}, "INVALID_SESSION")
    require(
        (value["kind"] == "session" and value["parent_session_id"] is None)
        or (
            value["kind"] == "subagent"
            and value["parent_session_id"]
            and value["parent_session_id"] != value["session_id"]
        ),
        "INVALID_SESSION",
    )
    if value["parent_session_id"] is not None:
        valid_id(value["parent_session_id"])


def scopes(values):
    require(isinstance(values, list) and len(values) <= 64, "INVALID_WRITE_SET")
    for value in values:
        require(set(value) == {"resource", "paths"}, "INVALID_WRITE_SET")
        text(value["resource"])
        require(
            isinstance(value["paths"], list) and 0 < len(value["paths"]) <= 64,
            "INVALID_WRITE_SET",
        )
        for path in value["paths"]:
            text(path)
            require(
                not path.startswith("/")
                and "\\" not in path
                and ".." not in PurePosixPath(path).parts
                and str(PurePosixPath(path)) == path,
                "INVALID_WRITE_SET",
            )


def overlaps(left, right):
    return any(
        a["resource"] == b["resource"]
        and any(
            x == "."
            or y == "."
            or x == y
            or x.startswith(y + "/")
            or y.startswith(x + "/")
            for x in a["paths"]
            for y in b["paths"]
        )
        for a in left
        for b in right
    )


class Coordinator:
    def __init__(self, home, stream_id):
        validate_roots(home)
        self.root = within(home, "state/work-coordination/" + identifier(stream_id))

    @classmethod
    def create(
        cls,
        home,
        stream_id,
        actor,
        goal,
        criteria,
        work,
        *,
        coordinator_session,
        max_parallel=4,
    ):
        self = cls(home, stream_id)
        valid_id(actor)
        text(goal)
        session(coordinator_session)
        require(
            isinstance(criteria, list)
            and criteria
            and len(criteria) <= 64
            and len(set(criteria)) == len(criteria),
            "INVALID_GOAL",
        )
        for criterion in criteria:
            valid_id(criterion)
        require(
            type(max_parallel) is int and 1 <= max_parallel <= 32, "INVALID_CAPACITY"
        )
        require(isinstance(work, list) and 0 < len(work) <= 128, "SIZE_LIMIT")
        rows = {}
        for item in copy.deepcopy(work):
            require(
                set(item)
                == {
                    "work_id",
                    "entity_id",
                    "handoff_id",
                    "role",
                    "session",
                    "depends_on",
                    "write_set",
                    "state",
                    "required",
                },
                "INVALID_WORK",
            )
            for key in ["work_id", "entity_id", "handoff_id", "role"]:
                valid_id(item[key])
            session(item["session"])
            scopes(item["write_set"])
            require(
                item["state"] in {"pending", "running"}
                and type(item["required"]) is bool,
                "INVALID_WORK",
            )
            require(
                item["work_id"] not in rows
                and isinstance(item["depends_on"], list)
                and len(item["depends_on"]) <= 128
                and len(set(item["depends_on"])) == len(item["depends_on"]),
                "INVALID_WORK",
            )
            rows[item["work_id"]] = item
            item.update(latest_notice_id=None, accepted_notice_id=None)
        visited = set()

        def visit(key, path):
            require(key in rows and key not in path, "INVALID_DEPENDENCIES")
            if key in visited:
                return
            for dependency in rows[key]["depends_on"]:
                visit(dependency, path | {key})
            visited.add(key)

        for key in rows:
            visit(key, set())
        sessions = {coordinator_session["session_id"]: coordinator_session}
        for item in rows.values():
            value = item["session"]
            require(
                value["session_id"] not in sessions
                or sessions[value["session_id"]] == value,
                "INVALID_SESSION",
            )
            sessions[value["session_id"]] = value
        for value in sessions.values():
            if value["kind"] == "subagent":
                require(
                    value["parent_session_id"] in sessions
                    and sessions[value["parent_session_id"]]["kind"] == "session",
                    "INVALID_SESSION",
                )
        require(
            sum(w["state"] == "running" for w in rows.values()) <= max_parallel,
            "CAPACITY_EXCEEDED",
        )
        running = [w for w in rows.values() if w["state"] == "running"]
        for i, item in enumerate(running):
            require(
                not any(
                    overlaps(item["write_set"], other["write_set"])
                    for other in running[:i]
                ),
                "WRITE_SET_CONFLICT",
            )
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        with publisher_lock(self.root / "publisher.lock"):
            require(not (self.root / "HEAD.json").exists(), "DESTINATION_EXISTS")
            self._save(
                {
                    "schema": SCHEMA,
                    "revision": 1,
                    "owner": actor,
                    "coordinator_session": coordinator_session,
                    "goal": goal,
                    "criteria": criteria,
                    "parent_state": "open",
                    "goal_acceptance": None,
                    "max_parallel": max_parallel,
                    "work": rows,
                    "notices": [],
                    "decisions": [],
                    "actions": [],
                    "checkpoints": [],
                    "consumed_event_ids": [],
                }
            )
        return self

    def _fault(self, point):
        """Fixture injection only; no production callback supplied by an archive."""

    def read(self):
        head = parse(bounded(within(self.root, "HEAD.json"), 4096))
        require(
            set(head) == {"schema", "revision", "snapshot_sha256", "size_bytes"}
            and head["schema"] == SCHEMA
            and type(head["revision"]) is int,
            "INTEGRITY_FAILED",
        )
        digest = head["snapshot_sha256"]
        require(
            isinstance(digest, str)
            and len(digest) == 64
            and all(c in "0123456789abcdef" for c in digest),
            "INTEGRITY_FAILED",
        )
        raw = bounded(within(self.root, "snapshots/" + digest + ".json"), LIMIT)
        require(
            sha(raw) == digest and len(raw) == head["size_bytes"], "INTEGRITY_FAILED"
        )
        state = parse(raw)
        require(
            state["schema"] == SCHEMA and state["revision"] == head["revision"],
            "INTEGRITY_FAILED",
        )
        return state

    def _save(self, state):
        data = encoded(state)
        scan_secrets(data)
        require(
            len(data) <= LIMIT
            and len(state["notices"]) <= 1024
            and len(state["actions"]) <= 1024
            and len(state["decisions"]) <= 1024
            and len(state["checkpoints"]) <= 128
            and len(state["consumed_event_ids"]) <= 1024,
            "SIZE_LIMIT",
        )
        digest = sha(data)
        durable(
            within(self.root, "snapshots/" + digest + ".json"), data, immutable=True
        )
        durable(
            within(self.root, "HEAD.json"),
            encoded(
                {
                    "schema": SCHEMA,
                    "revision": state["revision"],
                    "snapshot_sha256": digest,
                    "size_bytes": len(data),
                }
            ),
        )

    @staticmethod
    def _owner(state, actor):
        require(state["owner"] == actor, "OWNER_MISMATCH")

    @staticmethod
    def _cas(state, expected_revision):
        require(
            type(expected_revision) is int and state["revision"] == expected_revision,
            "REVISION_CONFLICT",
        )

    @staticmethod
    def _accepted(library, principal, handoff_id, manifest_ref, entity_id=None):
        resolved = library.resolve(handoff_id, principal)
        require(resolved["row"]["manifest_ref"] == manifest_ref, "STALE_RESULT")
        m = resolved["manifest"]
        require(
            entity_id is None or m["entity"]["entity_id"] == entity_id,
            "RESULT_BINDING_MISMATCH",
        )
        for item in m["deliverables"] + m["evidence"]:
            if item["required"]:
                require(item["preservation"] == "embedded", "SOURCE_UNAVAILABLE")
                library.store.get(item["ref"])
        return m

    def receive(
        self,
        actor,
        notification_id,
        work_id,
        library,
        principal,
        manifest_ref,
        expected_revision,
        *,
        origin="provider",
    ):
        valid_id(notification_id)
        require(origin in {"provider", "reconciled"}, "INVALID_INPUT")
        with publisher_lock(self.root / "publisher.lock"):
            s = self.read()
            self._owner(s, actor)
            require(
                work_id in s["work"] and s["parent_state"] == "open", "INVALID_WORK"
            )
            work = s["work"][work_id]
            m = self._accepted(
                library, principal, work["handoff_id"], manifest_ref, work["entity_id"]
            )
            for item in s["notices"]:
                same = (
                    item["work_id"] == work_id and item["manifest_ref"] == manifest_ref
                )
                require(
                    item["notification_id"] != notification_id or same,
                    "NOTIFICATION_CONFLICT",
                )
                if same:
                    require(
                        work.get("latest_notice_id") == item["notification_id"],
                        "STALE_NOTIFICATION",
                    )
                    return item
            self._cas(s, expected_revision)
            notice = {
                "notification_id": notification_id,
                "work_id": work_id,
                "handoff_id": work["handoff_id"],
                "manifest_ref": manifest_ref,
                "result_state": m["entity"]["state"],
                "origin": origin,
                "received_at": now(),
                "review": None,
                "superseded_by": None,
            }
            for previous in s["notices"]:
                if previous["work_id"] == work_id:
                    previous["superseded_by"] = notification_id
            work.update(latest_notice_id=notification_id, accepted_notice_id=None)
            if work["state"] == "completed":
                work["state"] = "held"
            s["notices"].append(notice)
            s["revision"] += 1
            self._save(s)
            self._fault("after_receive_commit")
            return notice

    def recover_notice(self, actor, work_id, library, principal, expected_revision):
        s = self.read()
        self._owner(s, actor)
        require(work_id in s["work"], "INVALID_WORK")
        resolved = library.resolve(s["work"][work_id]["handoff_id"], principal)
        ref = resolved["row"]["manifest_ref"]
        return self.receive(
            actor,
            "recovered:" + sha(encoded({"work_id": work_id, "ref": ref})),
            work_id,
            library,
            principal,
            ref,
            expected_revision,
            origin="reconciled",
        )

    def review(
        self, actor, notification_id, review, library, principal, expected_revision
    ):
        require(
            set(review)
            == {
                "verdict",
                "original_goal",
                "summary",
                "reasons",
                "remaining",
                "evidence_ids",
                "next_actions",
                "waiting",
            },
            "INVALID_REVIEW",
        )
        require(review["verdict"] in {"accepted", "partial", "held"}, "INVALID_REVIEW")
        for key in ["summary", "reasons"]:
            text(review[key])
        require(
            isinstance(review["remaining"], list) and review["remaining"],
            "ORPHANED_PARENT_WORK",
        )
        for item in review["remaining"]:
            text(item)
        with publisher_lock(self.root / "publisher.lock"):
            s = self.read()
            self._owner(s, actor)
            require(
                s["parent_state"] == "open" and review["original_goal"] == s["goal"],
                "ORIGINAL_GOAL_MISMATCH",
            )
            notices = [
                n for n in s["notices"] if n["notification_id"] == notification_id
            ]
            require(len(notices) == 1, "NOT_FOUND")
            notice = notices[0]
            require(
                s["work"][notice["work_id"]].get("latest_notice_id") == notification_id
                and notice.get("superseded_by") is None,
                "STALE_NOTIFICATION",
            )
            m = self._accepted(
                library,
                principal,
                notice["handoff_id"],
                notice["manifest_ref"],
                s["work"][notice["work_id"]]["entity_id"],
            )
            require(
                review["evidence_ids"]
                and set(review["evidence_ids"])
                <= {e["asset_id"] for e in m["evidence"]},
                "EVIDENCE_UNRESOLVED",
            )
            for evidence_id in review["evidence_ids"]:
                library.read_evidence(notice["handoff_id"], evidence_id, principal)
            if notice["review"] is not None:
                require(notice["review"] == review, "REVIEW_CONFLICT")
                return s
            self._cas(s, expected_revision)
            work = s["work"][notice["work_id"]]
            if review["verdict"] == "accepted":
                require(m["entity"]["state"] == "completed", "PARTIAL_RESULT")
                require(
                    not any(
                        a["target"] == work["work_id"] and a["state"] == "unknown"
                        for a in s["actions"]
                    ),
                    "UNKNOWN_EFFECT_NO_RETRY",
                )
                work["state"] = "completed"
                work["accepted_notice_id"] = notification_id
            else:
                work["state"] = "running" if review["verdict"] == "partial" else "held"
                work["accepted_notice_id"] = None
            actions = review["next_actions"]
            require(isinstance(actions, list) and len(actions) <= 128, "INVALID_ACTION")
            targets = [
                a.get("target")
                for a in actions
                if isinstance(a, dict) and a.get("target") != "parent"
            ]
            require(len(targets) == len(set(targets)), "DUPLICATE_ASSIGNMENT")
            if not actions:
                wait = review["waiting"]
                require(
                    isinstance(wait, dict)
                    and set(wait) == {"kind", "reason", "evidence_ids"}
                    and wait["kind"] in {"user-pause", "unavoidable-blocker"}
                    and wait["evidence_ids"]
                    and set(wait["evidence_ids"]) <= set(review["evidence_ids"]),
                    "ORPHANED_PARENT_WORK",
                )
                text(wait["reason"])
                if wait["kind"] != "user-pause":
                    require(
                        not any(
                            w["state"] in {"pending", "running", "planned"}
                            and w["work_id"] != work["work_id"]
                            and all(
                                s["work"][d]["state"] == "completed"
                                for d in w["depends_on"]
                            )
                            for w in s["work"].values()
                        ),
                        "INDEPENDENT_WORK_MUST_CONTINUE",
                    )
            else:
                require(review["waiting"] is None, "INVALID_ACTION")
            for i, action in enumerate(actions):
                require(
                    set(action) == {"target", "kind", "summary"}
                    and action["kind"] in ACTION_KINDS,
                    "INVALID_ACTION",
                )
                text(action["summary"])
                if action["target"] == "parent":
                    target_session = s["coordinator_session"]
                else:
                    require(action["target"] in s["work"], "INVALID_WORK")
                    target = s["work"][action["target"]]
                    require(
                        all(
                            s["work"][d]["state"] == "completed"
                            for d in target["depends_on"]
                        ),
                        "DEPENDENCY_INCOMPLETE",
                    )
                    require(
                        target["state"] in {"pending", "running", "held"},
                        "INVALID_WORK",
                    )
                    peers = [
                        w
                        for w in s["work"].values()
                        if w["work_id"] != target["work_id"]
                        and w["state"] in {"running", "planned", "held"}
                    ]
                    require(
                        not any(
                            overlaps(target["write_set"], w["write_set"]) for w in peers
                        ),
                        "WRITE_SET_CONFLICT",
                    )
                    if target["state"] == "pending":
                        target["state"] = "planned"
                    target_session = target["session"]
                aid = "action:" + sha(
                    encoded(
                        {
                            "notification_id": notification_id,
                            "index": i,
                            "action": action,
                        }
                    )
                )
                s["actions"].append(
                    {
                        **action,
                        "action_id": aid,
                        "operation_id": aid,
                        "session": target_session,
                        "state": "planned",
                        "generation": 0,
                        "nonce": None,
                        "receipt_ref": None,
                    }
                )
            require(
                sum(
                    w["state"] in {"running", "planned", "held"}
                    for w in s["work"].values()
                )
                <= s["max_parallel"],
                "CAPACITY_EXCEEDED",
            )
            notice["review"] = copy.deepcopy(review)
            s["decisions"].append(
                {
                    "notification_id": notification_id,
                    "at": now(),
                    "review": copy.deepcopy(review),
                }
            )
            s["revision"] += 1
            self._save(s)
            self._fault("after_review_commit")
            return s

    def checkpoint(self, actor, reason, expected_revision):
        text(reason)
        with publisher_lock(self.root / "publisher.lock"):
            s = self.read()
            self._owner(s, actor)
            self._cas(s, expected_revision)
            s["checkpoints"].append(
                {
                    "at": now(),
                    "reason": reason,
                    "work": copy.deepcopy(s["work"]),
                    "requested_sessions": [
                        w["session"]
                        for w in s["work"].values()
                        if w["state"] != "completed"
                    ],
                }
            )
            s["revision"] += 1
            self._save(s)
            return s

    def begin_action(self, actor, action_id, expected_revision):
        with publisher_lock(self.root / "publisher.lock"):
            s = self.read()
            self._owner(s, actor)
            self._cas(s, expected_revision)
            require(s["parent_state"] == "open", "PARENT_ALREADY_COMPLETED")
            items = [a for a in s["actions"] if a["action_id"] == action_id]
            require(len(items) == 1, "NOT_FOUND")
            action = items[0]
            if action["target"] != "parent":
                target = s["work"][action["target"]]
                require(target["state"] != "completed", "WORK_ALREADY_COMPLETED")
                require(
                    all(
                        s["work"][d]["state"] == "completed"
                        for d in target["depends_on"]
                    ),
                    "DEPENDENCY_INCOMPLETE",
                )
            require(
                not any(
                    a["action_id"] != action_id
                    and a["target"] == action["target"]
                    and a["state"] == "unknown"
                    for a in s["actions"]
                ),
                "UNKNOWN_EFFECT_NO_RETRY",
            )
            require(
                action["state"] in {"planned", "confirmed-not-executed"},
                "UNKNOWN_EFFECT_NO_RETRY",
            )
            require(action["generation"] < 128, "RETRY_LIMIT_REQUIRES_REVIEW")
            action.update(
                state="unknown",
                generation=action["generation"] + 1,
                nonce=uuid.uuid4().hex,
                receipt_ref=None,
            )
            s["revision"] += 1
            self._save(s)
            self._fault("after_action_admission")
            return action

    def record_outcome(
        self, actor, action_id, library, principal, proof_ref, expected_revision
    ):
        library._authorize(principal)
        proof = parse(library.store.get(proof_ref))
        require(
            set(proof)
            == {
                "schema",
                "action_id",
                "operation_id",
                "generation",
                "nonce",
                "provider",
                "event_id",
                "observed_at",
                "status",
            }
            and proof["schema"] == "agentos.coordinator-action-receipt/v1"
            and proof["status"]
            in {"completed", "not-executed", "running", "stopped", "unknown"},
            "UNPROVEN_OUTCOME",
        )
        for key in ["provider", "event_id", "observed_at"]:
            text(proof[key])
        try:
            observed = datetime.fromisoformat(proof["observed_at"])
            require(
                observed.tzinfo is not None
                and observed <= datetime.now(UTC) + timedelta(minutes=5),
                "UNPROVEN_OUTCOME",
            )
        except ValueError as exc:
            raise HandoffError("UNPROVEN_OUTCOME") from exc
        with publisher_lock(self.root / "publisher.lock"):
            s = self.read()
            self._owner(s, actor)
            items = [a for a in s["actions"] if a["action_id"] == action_id]
            require(len(items) == 1, "NOT_FOUND")
            action = items[0]
            require(
                all(
                    proof[k] == action[k]
                    for k in ["action_id", "operation_id", "generation", "nonce"]
                ),
                "OUTCOME_BINDING_MISMATCH",
            )
            if action["receipt_ref"] == proof_ref:
                return action
            self._cas(s, expected_revision)
            require(action["state"] == "unknown", "OUTCOME_CONFLICT")
            event_key = sha(encoded({k: proof[k] for k in ["provider", "event_id"]}))
            require(event_key not in s["consumed_event_ids"], "REPLAYED_EVENT")
            s["consumed_event_ids"].append(event_key)
            action.update(
                receipt_ref=proof_ref,
                execution_status=proof["status"],
                observed_at=proof["observed_at"],
            )
            action["state"] = {
                "completed": "completed",
                "not-executed": "confirmed-not-executed",
            }.get(proof["status"], "unknown")
            s["revision"] += 1
            self._save(s)
            self._fault("after_outcome_commit")
            return action

    def verify_goal(
        self,
        actor,
        library,
        principal,
        handoff_id,
        manifest_ref,
        summary,
        expected_revision,
    ):
        text(summary)
        m = self._accepted(library, principal, handoff_id, manifest_ref)
        with publisher_lock(self.root / "publisher.lock"):
            s = self.read()
            self._owner(s, actor)
            self._cas(s, expected_revision)
            require(
                s["parent_state"] == "open"
                and m["entity"]["state"] == "completed"
                and m["scope"]["objective"] == s["goal"],
                "ORIGINAL_GOAL_MISMATCH",
            )
            require(
                all(
                    w["state"] == "completed"
                    for w in s["work"].values()
                    if w["required"]
                ),
                "PARENT_SCOPE_INCOMPLETE",
            )
            require(
                not any(
                    n["review"] is None and n.get("superseded_by") is None
                    for n in s["notices"]
                ),
                "PENDING_RESULT_REVIEW",
            )
            for work in s["work"].values():
                if not work["required"]:
                    continue
                notices = [
                    n
                    for n in s["notices"]
                    if n["notification_id"] == work.get("latest_notice_id")
                    and n["work_id"] == work["work_id"]
                    and n["notification_id"] == work.get("accepted_notice_id")
                    and n.get("superseded_by") is None
                    and n["review"] is not None
                    and n["review"]["verdict"] == "accepted"
                ]
                require(len(notices) == 1, "CHILD_ACCEPTANCE_UNBOUND")
                current = self._accepted(
                    library,
                    principal,
                    work["handoff_id"],
                    notices[0]["manifest_ref"],
                    work["entity_id"],
                )
                require(current["entity"]["state"] == "completed", "PARTIAL_RESULT")
                for eid in notices[0]["review"]["evidence_ids"]:
                    library.read_evidence(work["handoff_id"], eid, principal)
            passed = {
                r["criterion_id"]
                for r in m["results"]
                if r["status"] == "pass" and r["evidence_ids"]
            }
            require(set(s["criteria"]) <= passed, "USER_RESULT_NOT_VERIFIED")
            for eid in {
                e
                for r in m["results"]
                if r["criterion_id"] in s["criteria"]
                for e in r["evidence_ids"]
            }:
                library.read_evidence(handoff_id, eid, principal)
            require(
                not any(a["state"] == "unknown" for a in s["actions"]),
                "UNKNOWN_EFFECT_NO_RETRY",
            )
            s.update(
                parent_state="completed",
                goal_acceptance={
                    "handoff_id": handoff_id,
                    "manifest_ref": manifest_ref,
                    "summary": summary,
                    "at": now(),
                },
            )
            s["revision"] += 1
            self._save(s)
            return s

    def status(self):
        s = self.read()
        return {
            "revision": s["revision"],
            "parent_state": s["parent_state"],
            "unreviewed_notices": [
                n["notification_id"]
                for n in s["notices"]
                if n["review"] is None and n.get("superseded_by") is None
            ],
            "superseded_notices": [
                n["notification_id"]
                for n in s["notices"]
                if n.get("superseded_by") is not None
            ],
            "planned_actions": [
                a["action_id"] for a in s["actions"] if a["state"] == "planned"
            ],
            "unknown_effects": [
                a["action_id"] for a in s["actions"] if a["state"] == "unknown"
            ],
            "remaining_work": [
                k for k, w in s["work"].items() if w["state"] != "completed"
            ],
            "received_results": len(s["notices"]),
            "reviewed_results": len(s["decisions"]),
            "declared_sessions": len(
                {
                    w["session"]["session_id"]
                    for w in s["work"].values()
                    if w["session"]["kind"] == "session"
                }
            ),
            "declared_subagents": len(
                {
                    w["session"]["session_id"]
                    for w in s["work"].values()
                    if w["session"]["kind"] == "subagent"
                }
            ),
            "verified_live_sessions": None,
            "verified_live_subagents": None,
            "commands_executed": [],
            "continuous_operation_proven": False,
        }
