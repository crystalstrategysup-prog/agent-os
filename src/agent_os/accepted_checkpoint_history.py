"""Read-only qualification of accepted checkpoint history, never recovery authority.

Only completed-continuation/v2 opts in. Default refusal recovery remains strict.
Current Library ACL, registry, operation receipts and immutable bytes are checked;
caller ACKs and saved qualification reports cannot substitute for these reads.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
from contextlib import contextmanager
from pathlib import Path

from . import refusal_recovery as rr
from .handoff import Library, local_principal
from .handoff_store import HandoffError, encoded
from .safeio import GateError, sha, within

SCHEMA = "agentos.accepted-checkpoint-history/v1"
MAX_JOURNALS = 32
MAX_JOURNAL_BYTES = 16 * 1024
MAX_REQUIRED_REFS = 1024
MAX_REQUIRED_BYTES = 64 * 1024 * 1024
NAME = re.compile(r"handoff-checkpoint-([0-9a-f]{64})\.json")


def fail(code):
    raise GateError("accepted_checkpoint_history_" + code)


def inventory(root, task_id):
    directory = within(root, f".agentos/tasks/{task_id}")
    if not directory.is_dir():
        fail("task_directory")
    result = {}
    with os.scandir(directory) as entries:
        for count, entry in enumerate(entries, 1):
            if count > rr.MAX_TASK_METADATA_ENTRIES:
                fail("inventory_limit")
            if not entry.name.lower().startswith("handoff-"):
                continue
            match = NAME.fullmatch(entry.name)
            if not match or not entry.is_file(follow_symlinks=False):
                fail("unqualified_journal")
            if len(result) >= MAX_JOURNALS:
                fail("journal_limit")
            raw = rr._read(Path(entry.path), MAX_JOURNAL_BYTES)
            result[entry.name] = (sha(raw), match[1], raw)
    return dict(sorted(result.items()))


@contextmanager
def library_read_lock(home):
    """Share the existing POSIX publisher lock; never create/replace a lock file.

    Writers already use exclusive nonblocking flock on this exact stable inode.
    A busy/unsupported Library stops this operation; there is no policy fallback.
    """
    if os.name != "posix":
        fail("library_lock_unsupported")
    import fcntl
    fd = None
    try:
        path = within(Path(home).resolve(), "results-library/publisher.lock", allow_missing=False)
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            fail("library_lock_invalid")
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except (OSError, ValueError):
        if fd is not None:
            os.close(fd)
        fail("library_busy_or_unavailable")
    try:
        yield
    finally:
        os.close(fd)


def qualify(root, home, *, task_id, project_id, revision):
    with library_read_lock(home):
        return _qualify(root, home, task_id=task_id, project_id=project_id, revision=revision)


def _qualify(root, home, *, task_id, project_id, revision):
    """Bounded detached metadata only; does not write journals or publish anything.

    The continuation transaction validates actual project/task identity separately.
    The digest excludes unrelated Library generation changes, but includes the
    selected current ACL and every exact journal and accepted historical manifest.
    Same-UID cooperative-filesystem trust and current target authority still apply.
    """
    root = Path(root).resolve()
    home = Path(home).resolve()
    rr.ident(task_id, r"task-[0-9a-f]{16}")
    rr.short(project_id)
    if type(revision) is not int or revision < 1:
        fail("revision")
    library_path = home / "results-library"
    try:
        journals = inventory(root, task_id)
        library = Library(library_path)
        principal = local_principal()
        current = library._authorize(principal)
        acl_hash = sha(encoded(current["access"]))
        rows, ref_count, ref_bytes = [], 0, 0
        for name, (journal_sha, fingerprint, raw) in journals.items():
            journal = rr.parse(raw)
            rr.keys(journal, "payload_sha256 candidate_ref idempotency_key library_root")
            if (journal["library_root"] != str(library_path)
                    or journal["payload_sha256"] != fingerprint
                    or journal["idempotency_key"] != task_id + ":checkpoint:" + fingerprint[:24]):
                fail("journal_identity")
            ref = journal["candidate_ref"]
            # The Store checks the full typed ref, exact locator, size and hash.
            if not isinstance(ref, dict) or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(ref.get("object_id", ""))):
                fail("manifest_ref")
            receipt = library.reconcile(journal["idempotency_key"], principal)
            hid = "handoff:" + task_id
            accepted = receipt.get("accepted")
            if (receipt.get("status") != "accepted" or receipt.get("library_id") != current["library_id"]
                    or receipt.get("accepted_count") != 1 or not isinstance(accepted, list) or len(accepted) != 1
                    or accepted[0].get("handoff_id") != hid or accepted[0].get("manifest_ref") != ref):
                fail("not_accepted")
            resolved = library.resolve(hid, principal, revision=ref["object_id"])
            publication_state = resolved["row"].get("publication_state")
            # Exact historical receipts survive retract. A retracted/unknown
            # current registry row is not admissible accepted history. Normal
            # supersession retains a proven older checkpoint, not new authority.
            if publication_state not in {"accepted", "superseded"}:
                fail("publication_state")
            manifest = resolved["manifest"]
            entity, facets = manifest["entity"], manifest["facets"]
            old_revision = entity["scope_revision"]
            if (resolved["row"]["manifest_ref"] != ref or manifest["handoff_id"] != hid
                    or entity["entity_id"] != task_id or entity["state"] != "active"
                    or type(old_revision) is not int or not 1 <= old_revision < revision
                    or facets["project_id"] != [project_id] or facets["result_type"] != "checkpoint"
                    or manifest["privacy"]["scope_id"] != current["library_id"]):
                fail("manifest_identity")
            evidence = [item for item in manifest["evidence"] if item["asset_id"] == "evidence:review"]
            if (len(evidence) != 1 or evidence[0].get("required") is not True
                    or evidence[0]["ref"]["object_id"] != "sha256:" + fingerprint):
                fail("payload_identity")
            payload = None
            for asset in manifest["deliverables"] + manifest["evidence"]:
                if asset.get("required") is not True:
                    continue
                asset_ref = asset["ref"]
                size = asset_ref["size_bytes"]
                if type(size) is not int or size < 0:
                    fail("ref_size")
                ref_count += 1
                ref_bytes += size
                if ref_count > MAX_REQUIRED_REFS or ref_bytes > MAX_REQUIRED_BYTES:
                    fail("required_object_limit")
                data = library.store.get(asset_ref)
                if asset["asset_id"] == "evidence:review":
                    payload = rr.parse(data)
            if not isinstance(payload, dict) or payload.get("task_id") != task_id or payload.get("revision") != old_revision:
                fail("payload_identity")
            rows.append({"journal": name, "journal_sha256": journal_sha,
                         "payload_sha256": fingerprint, "manifest_ref": ref,
                         "idempotency_key": journal["idempotency_key"],
                         "publication_state": publication_state,
                         "accepted_generation": receipt["generation"], "revision": old_revision})
        after = library._authorize(principal)
        if after["library_id"] != current["library_id"] or sha(encoded(after["access"])) != acl_hash:
            fail("library_changed")
        if inventory(root, task_id) != journals:
            fail("journals_changed")
        body = {"schema": SCHEMA, "root": str(root), "user_home": str(home),
                "task_id": task_id, "project_id": project_id, "revision": revision,
                "library_id": current["library_id"], "acl_sha256": acl_hash, "journals": rows}
        return {**body, "sha256": sha(encoded(body)), "ready_granted": False,
                "semantic_acceptance": False, "historical_permissions_grant_authority": False}
    except (HandoffError, OSError, KeyError, TypeError, ValueError, AttributeError, RecursionError, OverflowError) as exc:
        if isinstance(exc, GateError) and str(exc).startswith("accepted_checkpoint_history_"):
            raise
        fail("unqualified")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("root", "home", "task-id", "project-id"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--revision", type=int, required=True)
    args = parser.parse_args()
    try:
        result = qualify(args.root, args.home, task_id=args.task_id,
                         project_id=args.project_id, revision=args.revision)
    except GateError as exc:
        print(json.dumps({"status": "HOLD", "error": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
