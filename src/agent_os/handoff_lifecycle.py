"""Verified project terminal transitions; historical evidence never grants authority."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .handoff import Library, checked, local_principal, timestamp
from .handoff_store import HandoffError, encoded, require
from .safeio import GateError, atomic_json, digest, read_json, within

TOPICS = [
    {
        "topic_id": "agentos:delivery",
        "title": "Result delivery",
        "aliases": ["\u043f\u0435\u0440\u0435\u0434\u0430\u0447\u0430 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u0430"],
        "redirect": None,
    },
    {
        "topic_id": "agentos:continuity",
        "title": "Work continuity",
        "aliases": ["\u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0435\u043d\u0438\u0435 \u0440\u0430\u0431\u043e\u0442\u044b"],
        "redirect": None,
    },
]


def draft(
    *,
    handoff_id,
    entity_id,
    project_id,
    title,
    objective,
    criteria,
    evidence_bytes,
    deliverables,
    principal,
    state="completed",
    next_step="Start a fresh authorized task.",
):
    """A caller supplies reviewed facts. This helper does not infer authorization."""
    at = timestamp()
    return {
        "handoff_id": handoff_id,
        "producer": principal,
        "created_at": at,
        "entity": {
            "entity_id": entity_id,
            "kind": "work",
            "parent_id": None,
            "state": state,
            "scope_revision": 1,
            "required_children": [],
            "approval": {
                "required": False,
                "agent_checked": True,
                "user_confirmed": False,
                "evidence_ids": [],
            },
        },
        "scope": {
            "objective": objective,
            "boundaries": "Only the explicitly contracted local work; external effects need current separate authority.",
            "criteria": criteria,
            "request_evidence_ids": ["evidence:review"],
            "change_refs": [],
        },
        "facets": {
            "title": title,
            "summary": objective,
            "project_id": [project_id] if project_id else [],
            "stage_id": [],
            "topic_id": [item["topic_id"] for item in TOPICS],
            "related_entity_id": [],
            "result_type": "checkpoint" if state != "completed" else "result",
            "language": "en",
            "aliases": [],
        },
        "deliverables": [
            {
                "asset_id": item,
                "path": "results/" + item.replace(":", "-"),
                "preservation": "embedded",
                "required": True,
                "media_type": "application/octet-stream",
            }
            for item in deliverables
        ],
        "results": [
            {
                "criterion_id": item["criterion_id"],
                "status": "pass" if state == "completed" else "unknown",
                "evidence_ids": ["evidence:review"],
                "deliverable_ids": list(deliverables),
            }
            for item in criteria
        ],
        "decisions": checked([]),
        "permissions": checked([]),
        "open_items": checked([]),
        "evidence": [
            {
                "asset_id": "evidence:review",
                "path": "evidence/review.json",
                "preservation": "embedded",
                "required": True,
                "media_type": "application/json",
                "source_ref": {
                    "source_kind": "local_project_review",
                    "source_id": entity_id,
                    "source_revision": "sha256:"
                    + hashlib.sha256(evidence_bytes).hexdigest(),
                    "locator": "local://project-review/" + entity_id,
                    "observed_at": at,
                    "snapshot_ref": None,
                    "selector": {
                        "kind": "utf8_bytes",
                        "start": 0,
                        "end": len(evidence_bytes),
                    },
                    "author": principal,
                    "adapter_version": "agentos.project-lifecycle/v1",
                    "capture_scope": "full",
                    "source_freshness": "current",
                },
            }
        ],
        "recovery": {
            "level": "self_contained",
            "first_assets": list(deliverables),
            "dependencies": [],
            "required_access": [],
            "not_restored": [
                "External services, credentials, chat sessions and prior permissions."
            ],
            "next_step": next_step,
            "read_only_checks": [
                {"asset_id": item, "kind": "sha256"} for item in deliverables
            ],
        },
        "privacy": {
            "scope_id": None,
            "classification": "scope_private",
            "retention": "owner_policy_no_automatic_deletion",
            "redaction": ["Credentials and session contents excluded."],
        },
        "limitations": [
            "Local captured evidence only; no external runtime or renewed permission claim."
        ],
    }


def deliver(root, task, review, assessment, *, profile, user_home=None):
    """Called under the project write lock before a terminal status is persisted."""
    home = Path(user_home or task.get("handoff_user_home") or "")
    if not user_home and not task.get("handoff_user_home"):
        raise GateError("handoff_user_home_required")
    principal = local_principal()
    library_path = home / "results-library"
    try:
        library = (
            Library(library_path)
            if library_path.exists()
            else Library.create(library_path, principal, topics=TOPICS)
        )
        current = library._authorize(principal, write=True)
        from .project import SKIP, document_check, source_snapshot
        from .source_links import attest_directory_link

        snapshot = source_snapshot(root)
        require(
            profile != "completion"
            or assessment["source_sha256"] == snapshot["sha256"],
            "INTEGRITY_FAILED",
        )
        docs = document_check(root, task)
        link_rechecks = []
        for path, expected in snapshot.get("symlinks", {}).items():
            metadata, recheck = attest_directory_link(root, root / path, SKIP)
            require(metadata == expected, "INTEGRITY_FAILED")
            link_rechecks.append(recheck)
        payload = {
            "task_id": task["id"],
            "revision": task["revision"],
            "answers": task["answers"],
            "review": review,
            "assessment": assessment,
            "source_snapshot": snapshot,
            "documents": docs,
        }
        fingerprint = hashlib.sha256(encoded(payload)).hexdigest()
        journal_path = within(
            root, f".agentos/tasks/{task['id']}/handoff-{profile}-{fingerprint}.json"
        )
        journal = read_json(journal_path) if journal_path.exists() else None
        if journal:
            require(
                journal["payload_sha256"] == fingerprint,
                "HANDOFF_REVIEW_CHANGED_RETRY_REQUIRED",
            )
        else:
            assets = {"evidence:review": encoded(payload)}
            deliverables = []
            captured_paths = {}
            captured_links = []
            # Preserve approved changed surfaces and current selected documents,
            # not an unbounded project history or unrelated data directory.
            approved = task["answers"]["write_paths"]
            files = {
                path: digest
                for path, digest in snapshot["files"].items()
                if any(
                    path == allowed or path.startswith(allowed.rstrip("/") + "/")
                    for allowed in approved
                )
            }
            from .project import load_project

            project = load_project(root)
            for doc_id, expected in docs["document_hashes"].items():
                files[project["documents"][doc_id]["path"]] = expected
            for i, (path, expected) in enumerate(sorted(files.items())):
                asset_id = f"source:{i:06d}"
                metadata = snapshot.get("symlinks", {}).get(path)
                if metadata is not None:
                    require(digest(metadata) == expected, "INTEGRITY_FAILED")
                    data = encoded({"path": path, "metadata": metadata})
                    captured_paths[asset_id] = f"source-links/source-{i:06d}.json"
                    captured_links.append(path)
                else:
                    data = within(root, path).read_bytes()
                    require(
                        hashlib.sha256(data).hexdigest() == expected,
                        "INTEGRITY_FAILED",
                    )
                    captured_paths[asset_id] = "source/" + path
                assets[asset_id] = data
                deliverables.append(asset_id)
            if not deliverables:
                assets["result:report"] = encoded(review)
                deliverables.append("result:report")
            manifest = draft(
                handoff_id="handoff:" + task["id"],
                entity_id=task["id"],
                project_id=task["project_id"],
                title="Project work " + task["id"],
                objective=task["answers"]["objective"],
                criteria=[
                    {"criterion_id": item["id"], "description": item["criterion"]}
                    for item in task["answers"]["acceptance"]
                ],
                evidence_bytes=assets["evidence:review"],
                deliverables=deliverables,
                principal=principal,
                state="completed" if profile == "completion" else "active",
                next_step=review["next_step"],
            )
            manifest["entity"]["scope_revision"] = task["revision"]
            manifest["privacy"]["scope_id"] = current["library_id"]
            manifest["limitations"] = [review["limitations"]]
            if set(snapshot["files"]) - set(files):
                manifest["recovery"]["level"] = "external_required"
                manifest["recovery"]["dependencies"] = [
                    {
                        "dependency_id": "source-baseline:" + snapshot["sha256"],
                        "required": True,
                        "status": "unknown",
                    }
                ]
                manifest["limitations"].append(
                    "Only approved result surfaces and current entry documents are captured; other source files require the recorded baseline."
                )
            for path in captured_links:
                manifest["recovery"]["level"] = "external_required"
                manifest["recovery"]["dependencies"].append(
                    {
                        "dependency_id": "source-link:"
                        + hashlib.sha256(path.encode()).hexdigest(),
                        "required": True,
                        "status": "unknown",
                    }
                )
                manifest["recovery"]["not_restored"].append(
                    "Directory alias "
                    + path
                    + " (metadata preserved; reconstruction not implemented)."
                )
                manifest["limitations"].append(
                    "Tracked directory alias "
                    + path
                    + " is captured as metadata only and is never followed or reconstructed."
                )
            for item in manifest["deliverables"]:
                if item["asset_id"] in captured_paths:
                    item["path"] = captured_paths[item["asset_id"]]
            manifest["decisions"] = checked(
                [
                    {
                        "decision_id": "decision:" + task["id"] + ":" + profile,
                        "decision": review["summary"],
                        "reasons": "Current scoped assessment and semantic review.",
                        "alternatives": [
                            "Leave the work open without claiming completion."
                        ],
                        "actor": review.get("reviewer", principal),
                        "at": manifest["created_at"],
                        "evidence_ids": ["evidence:review"],
                    }
                ]
            )
            manifest["permissions"] = checked(
                [
                    {
                        "permission_id": "permission:" + task["id"],
                        "action": "scoped_local_project_change",
                        "object": task["project_id"] + "/" + task["id"],
                        "recipient": principal,
                        "data_scope": task["answers"]["scope_in"],
                        "limits": task["answers"]["scope_out"]
                        + "; "
                        + task["answers"]["constraints"],
                        "author": "current_entry_authority_attestation",
                        "at": task["entered_at"],
                        "expires_at": None,
                        "one_time": False,
                        "revoked": False,
                        "evidence_ids": ["evidence:review"],
                    }
                ]
            )
            manifest["open_items"] = checked(review.get("open_items", []))
            for item in manifest["open_items"]["items"]:
                _, _, live_routes, live_tree = library._view(principal)
                existing = live_tree.find(live_routes["tasks"], item["task_id"])
                library.update_task(
                    item, existing["revision"] if existing else 0, principal
                )
            existing = library.search(
                {"filters": {"handoff_id": manifest["handoff_id"]}}, principal
            )["results"]
            revision = existing[0]["manifest_ref"]["object_id"] if existing else None
            candidate = library.build_handoff(
                manifest, revision, principal, assets=assets, acceptance_profile=profile
            )
            journal = {
                "payload_sha256": fingerprint,
                "candidate_ref": candidate,
                "idempotency_key": task["id"] + ":" + profile + ":" + fingerprint[:24],
                "library_root": str(library_path),
            }
            atomic_json(journal_path, journal)
        # Bind capture and retries to the same attested link/index and source.
        for recheck in link_rechecks:
            recheck()
        require(source_snapshot(root) == snapshot, "INTEGRITY_FAILED")
        require(document_check(root, task) == docs, "INTEGRITY_FAILED")
        receipt = library.publish_handoff(
            journal["candidate_ref"],
            library._authorize(principal)["generation"],
            journal["idempotency_key"],
            principal,
            acceptance_profile=profile,
        )
        hid = "handoff:" + task["id"]
        resolved = library.resolve(hid, principal)
        require(
            resolved["row"]["manifest_ref"] == journal["candidate_ref"], "INDEX_STALE"
        )
        for topic in [item["topic_id"] for item in TOPICS]:
            found = library.search(
                {
                    "filters": {
                        "handoff_id": hid,
                        "project_id": task["project_id"],
                        "topic_id": topic,
                    }
                },
                principal,
            )
            require(
                found["coverage"]["status"] == "complete"
                and len(found["results"]) == 1,
                "INDEX_STALE",
            )
        return {
            "library_root": str(library_path),
            "handoff_id": hid,
            "manifest_ref": journal["candidate_ref"],
            "receipt": receipt,
            "profile": profile,
            "cleanup_authorized": False,
        }
    except (HandoffError, OSError) as exc:
        raise GateError("handoff_acceptance_failed:" + str(exc)) from exc


def verify(binding):
    library = Library(Path(binding["library_root"]))
    resolved = library.resolve(binding["handoff_id"], local_principal())
    require(resolved["row"]["manifest_ref"] == binding["manifest_ref"], "INDEX_STALE")
    require(resolved["manifest"]["entity"]["state"] == "completed", "SCOPE_INCOMPLETE")
    for item in resolved["manifest"]["deliverables"] + resolved["manifest"]["evidence"]:
        if item["required"]:
            library.store.get(item["ref"])
    return {"status": "PASS", "manifest_ref": binding["manifest_ref"]}
