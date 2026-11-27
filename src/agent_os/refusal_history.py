"""Reconcile past completed checkpoints before a nonaccepting SAVED disposition."""
from . import accepted_checkpoint_history as history
from . import refusal_recovery as rr
from .handoff import Library, local_principal


def verify(root, home, request, task):
    task_id = request["task_id"]
    revision = request["revision"]
    if task.get("closeout") or not task.get("checkpoint"):
        rr.fail("recovery_publication_unreconciled")
    result = history._qualify(root, home, task_id=task_id, project_id=request["project_id"],
                              revision=revision, reuse_verified_objects=True)
    rows = {row["revision"]: row for row in result["journals"]}
    if not rows or len(rows) != len(result["journals"]):
        rr.fail("recovery_history_conflict")
    library = Library(home / "results-library")
    events_path = rr._path(root, f".agentos/tasks/{task_id}/events.jsonl")
    events = rr._read(events_path, rr.MAX_METADATA)
    current = 0
    latest = None
    for line in events.splitlines():
        event = rr.parse(line)
        if event["event"] == "ENTER":
            observed = event["details"]["revision"]
            if type(observed) is not int or observed != current + 1:
                rr.fail("recovery_history_revision")
            current = observed
        elif event["event"] == "CHECKPOINT":
            checkpoint = event["details"]
            handoff = checkpoint["handoff"]
            row = rows.pop(current, None)
            if (not row or checkpoint["complete"] is not False or handoff["profile"] != "checkpoint"
                    or handoff["library_root"] != str(home / "results-library")
                    or handoff["handoff_id"] != "handoff:" + task_id
                    or handoff["cleanup_authorized"] is not False or handoff["manifest_ref"] != row["manifest_ref"]
                    or handoff["receipt"] != library.reconcile(row["idempotency_key"], local_principal())):
                rr.fail("recovery_history_conflict")
            latest = checkpoint
        elif event["event"] in {"CLOSE", "CLOSEOUT"}:
            rr.fail("recovery_publication_unreconciled")
    if rows or latest != task["checkpoint"] or current != revision:
        rr.fail("recovery_history_incomplete")
    head = library.resolve("handoff:" + task_id, local_principal())["row"]
    if head["publication_state"] != "accepted" or head["manifest_ref"] != latest["handoff"]["manifest_ref"]:
        rr.fail("recovery_history_head_changed")
    if result["sha256"] != request["accepted_checkpoint_history_sha256"]:
        rr.fail("recovery_history_changed")
