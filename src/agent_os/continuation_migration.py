"""Explicit legacy promotion; owned/unknown/acknowledged evidence is never reset."""
from __future__ import annotations

from pathlib import Path

from . import continuation as c
from .safeio import GateError, atomic_json, create_only_bytes, lock, now, sha, within


def migrate(home: Path, item_id: str, actor: str, revision: int, *,
            apply: bool = False, expected_sha256: str | None = None) -> dict:
    from .overlay import validate_roots

    validate_roots(home)

    def inspect():
        item = c.read(home, item_id)
        if actor != item["continuation"]["parent_owner"]:
            raise GateError("continuation_parent_owner_mismatch")
        if isinstance(revision, bool) or revision != item["revision"]:
            raise GateError("continuation_revision_conflict")
        c._binding(item)
        path = c._path(home, item_id)
        original = path.read_bytes()
        before = sha(original)
        if item["schema"] == c.ITEM_SCHEMA:
            return item, original, {"status": "ALREADY_V2", "id": item_id, "state": item["state"],
                                    "source_sha256": before, "user_data_writes": []}
        if item['schema'] != c.LEGACY_ITEM_SCHEMA:
            raise GateError('causal_item_not_legacy_preserve_and_hold')
        untouched = (item["state"] == "PENDING" and item.get("attempt_id") is None
                     and item.get("receipt") is None and item.get("worker_started") is False
                     and not item.get("delivery_generation") and not item.get("receipt_history")
                     and not item.get("consumed_receipt_ids"))
        backup = f"backups/continuation-v1/{item_id}-{before}.json"
        return item, original, {"status": "PLANNED_PROMOTION" if untouched else "HOLD_LEGACY_UNBOUND",
                               "id": item_id, "state": item["state"], "source_sha256": before,
                               "backup": backup if untouched else None, "user_data_writes": [],
                               "dispatch_admitted": False, "provider_reconciliation_required": not untouched}

    if not apply:
        return inspect()[2]
    with lock(within(home, "state/continuations.lock")):
        item, original, plan = inspect()
        if expected_sha256 != plan["source_sha256"]:
            raise GateError("explicit_matching_legacy_sha256_required")
        if plan["status"] == "HOLD_LEGACY_UNBOUND":
            raise GateError("legacy_owned_outcome_requires_provider_reconciliation")
        if plan["status"] == "ALREADY_V2":
            return plan
        backup = within(home, plan["backup"])
        if backup.exists():
            if backup.read_bytes() != original:
                raise GateError("legacy_backup_conflict")
        else:
            create_only_bytes(backup, original)
        promoted = {**item, "schema": c.ITEM_SCHEMA, "revision": item["revision"] + 1, "at": now(),
                    "delivery_generation": 0, "delivery_nonce": None, "delivery_started_at": None,
                    "consumed_receipt_ids": [], "receipt_history": [],
                    "migration": {"schema": "agentos.continuation-migration/v1",
                                  "legacy_sha256": plan["source_sha256"], "backup": plan["backup"],
                                  "actor": actor, "from_revision": revision}}
        atomic_json(c._path(home, item_id), promoted)
        return {**plan, "status": "PROMOTED_PENDING_V2", "revision": promoted["revision"],
                "after_sha256": sha(c._path(home, item_id).read_bytes()),
                "user_data_writes": [plan["backup"], f"state/continuations/{item_id}.json"]}
