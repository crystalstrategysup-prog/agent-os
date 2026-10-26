"""Synthetic owning-source transactions; no network, native operations or private data."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/atlas/scripts"))
import checkpoint as cp

T0 = "2026-01-01T00:00:00Z"
T1 = "2026-01-01T00:01:00Z"
T2 = "2026-01-01T00:02:00Z"
T3 = "2026-01-01T00:03:00Z"


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="atlas-checkpoint-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "source/history").mkdir(parents=True)
        (self.root / "prepared").mkdir()
        (self.root / ".atlas").mkdir()
        self.matrix = {"schema": "example.work-matrix/v1", "revision": 1, "updated_at": T0,
            "previous_payload_sha256": "0" * 64, "policy": {"accepted": "Owner evidence only"},
            "steps": [{"id": "GROUP", "parent_id": None, "title": "Group", "created_at": T0},
                      {"id": "A", "parent_id": "GROUP", "title": "Implement A", "created_at": T0},
                      {"id": "B", "parent_id": "GROUP", "title": "Accepted historic B", "created_at": T0}],
            "events": [{"id": "E1", "step_id": "A", "at": T0, "status": "planned", "executor_ids": ["Worker"], "note": "Planned"},
                       {"id": "E2", "step_id": "B", "at": T0, "status": "done", "executor_ids": ["Root"], "accepted": True, "note": "Historical source acceptance"}],
            "actors": [{"id": "Root"}, {"id": "Worker"}], "actor_events": [], "actor_updates": [], "activity_events": []}
        self.binding = {"schema": "atlas.upstream-binding/v1", "project": {"id": "EXAMPLE", "title": "Example",
            "objective": "Record real source facts", "writer": "Root", "authority_ref": "Explicit synthetic writer", "scope_note": "Declared source subset"},
            "matrix": {"path": "source/matrix.json", "allowed_schema": "example.work-matrix/v1"},
            "history": {"paths": [], "directories": ["source/history"], "coverage_note": "Only retained snapshots are known"},
            "documents": [{"id": "DOC", "path": "source/note.md", "title": "Note", "role": "Work note", "domain": "documents"}],
            "output": ".atlas/output"}
        self.profile = {"schema": "atlas.matrix-writer/v1", "binding": ".atlas/UPSTREAM.json", "project_id": "EXAMPLE", "writer": "Root",
            "matrix": {**self.binding["matrix"], "pointer": ""}, "lock_path": cp.LOCK,
            "document_paths": ["source/note.md"], "history": {"mode": "retained-operation-snapshots", "previous_payload_hash": "source-bytes"}}
        self.write("source/matrix.json", cp.nav.canonical(self.matrix))
        self.write("source/note.md", b"# Existing note\n")
        os.chmod(self.root / "source/note.md", 0o640)
        self.write(".atlas/UPSTREAM.json", cp.nav.canonical(self.binding))
        self.write(cp.PROFILE, cp.nav.canonical(self.profile))
        cp.adapter.refresh(self.root, at=T0)

    def write(self, rel, raw):
        (self.root / rel).write_bytes(raw)

    def pin(self, rel):
        return cp.adapter.pin(rel, (self.root / rel).read_bytes())

    def record(self, operation="start-a", phase="start", status="doing", at=T1):
        source = self.pin("source/matrix.json")
        matrix = cp.adapter.pointer_value(cp.nav.parse((self.root / source["path"]).read_bytes()), self.profile["matrix"]["pointer"])
        return {"schema": "atlas.checkpoint/v1", "operation_id": operation, "project_id": "EXAMPLE", "writer": "Root", "work_id": "A",
            "phase": phase, "at": at, "expected_source": {"sha256": source["sha256"], "bytes": source["bytes"], "revision": matrix["revision"]},
            "executor_id": "Worker", "status": status, "note": "Started the already assigned work", "next_action": "Read the scoped source and implement A",
            "evidence": [], "document_edits": []}

    def run_record(self, record, at=T3):
        path = "prepared/" + record["operation_id"] + ".json"
        self.write(path, cp.nav.canonical(record))
        return cp.checkpoint(self.root, path, at=at)

    def current(self):
        return cp.adapter.atlas.current_output(self.root / ".atlas/output")

    def test_dispatch_immediate_projection_idempotence_and_history(self):
        before = (self.root / "source/matrix.json").read_bytes()
        old_pointer, old_snapshot = self.current()
        record = self.record(phase="dispatch")
        result = self.run_record(record)
        self.assertEqual(result["status"], "CHECKPOINT_PUBLISHED", result)
        current = json.loads((self.root / "source/matrix.json").read_bytes())
        self.assertEqual(current["events"][:-1], self.matrix["events"])
        self.assertEqual(current["previous_payload_sha256"], cp.adapter.sha(before))
        self.assertEqual(current["activity_events"], [])
        self.assertFalse(current["events"][-1]["accepted"])
        work = next(w for w in self.current()[1]["atlas"]["works"] if w["id"] == "A")
        self.assertEqual(work["state"], "DOING")
        self.assertIsNone(work["activity"])
        self.assertEqual(work["acceptance"], [])
        self.assertEqual((self.root / cp.OPERATIONS / "start-a/file-00.before").read_bytes(), before)
        retained = cp.adapter.nav.verify_release(self.root / ".atlas/output", old_pointer["release"])[1]
        self.assertEqual(retained, old_snapshot)
        now_pointer = self.current()[0]
        again = self.run_record(record)
        self.assertTrue(again["replayed"])
        self.assertEqual(self.current()[0], now_pointer)
        self.assertEqual(json.loads((self.root / "source/matrix.json").read_bytes()), current)
        changed = copy.deepcopy(record)
        changed["note"] = "Different fact using the same operation"
        with self.assertRaisesRegex(cp.nav.Invalid, "PAYLOAD_CONFLICT"):
            self.run_record(changed)

    def test_embedded_matrix_preserves_surrounding_bytes(self):
        # Use a new root before any imported lineage, preserving an arbitrary JSON envelope.
        self.root = self.root / "nested"
        (self.root / "source/history").mkdir(parents=True)
        (self.root / "prepared").mkdir()
        (self.root / ".atlas").mkdir()
        pointer = "/currentPriority1ParallelWork/ownerWorkMatrix"
        self.binding["matrix"]["pointer"] = pointer
        self.profile["matrix"]["pointer"] = pointer
        self.profile["history"]["previous_payload_hash"] = "selected-canonical"
        prefix = b'{ "untouched": [ 1,  2 ], "currentPriority1ParallelWork": { "ownerWorkMatrix": '
        suffix = b', "other": {"literal":"keep  these spaces"} }, "tail": 1.00 }\n'
        self.write("source/matrix.json", prefix + cp.nav.canonical(self.matrix).rstrip(b"\n") + suffix)
        self.write("source/note.md", b"# Existing note\n")
        self.write(".atlas/UPSTREAM.json", cp.nav.canonical(self.binding))
        self.write(cp.PROFILE, cp.nav.canonical(self.profile))
        cp.adapter.refresh(self.root, at=T0)
        result = self.run_record(self.record())
        self.assertEqual(result["status"], "CHECKPOINT_PUBLISHED", result)
        after = (self.root / "source/matrix.json").read_bytes()
        self.assertTrue(after.startswith(prefix) and after.endswith(suffix))
        selected = cp.adapter.pointer_value(json.loads(after), pointer)
        self.assertEqual(selected["revision"], 2)
        self.assertEqual(selected["previous_payload_sha256"], cp.adapter.sha(cp.nav.canonical(self.matrix)))

    def test_documents_result_and_no_duplicate_progress_fact(self):
        self.write("prepared/note.md", b"# Known result and next action\n")
        self.write("prepared/proof.json", b'{"result":"documented source result"}\n')
        record = self.record(operation="result-a", phase="complete", status="done")
        record["evidence"] = [self.pin("prepared/proof.json")]
        record["document_edits"] = [{"path": "source/note.md", "before": {k: self.pin("source/note.md")[k] for k in ("sha256", "bytes")}, "after": self.pin("prepared/note.md")}]
        result = self.run_record(record)
        self.assertEqual(result["status"], "CHECKPOINT_PUBLISHED", result)
        self.assertEqual((self.root / "source/note.md").read_bytes(), b"# Known result and next action\n")
        self.assertEqual((self.root / "source/note.md").stat().st_mode & 0o777, 0o640)
        work = next(w for w in self.current()[1]["atlas"]["works"] if w["id"] == "A")
        self.assertEqual(work["state"], "REVIEW")
        self.assertEqual(work["acceptance"], [])
        progress = self.record("progress-a", "progress", "doing", T2)
        self.assertEqual(self.run_record(progress)["status"], "CHECKPOINT_PUBLISHED")
        old_source, old_current = (self.root / "source/matrix.json").read_bytes(), self.current()[0]
        same = self.record("same-progress", "progress", "doing", T3)
        self.assertEqual(self.run_record(same)["status"], "NO_CHANGE")
        self.assertEqual(old_source, (self.root / "source/matrix.json").read_bytes())
        self.assertEqual(old_current, self.current()[0])

    def test_partial_document_commit_blocks_import_and_resumes_exact_operation(self):
        self.write("prepared/note.md", b"# Intended note delta\n")
        record = self.record()
        record["document_edits"] = [{"path": "source/note.md", "before": {k: self.pin("source/note.md")[k] for k in ("sha256", "bytes")}, "after": self.pin("prepared/note.md")}]
        actual_replace = cp._replace
        def interrupted(root, rel, *args):
            if rel == "source/matrix.json":
                raise OSError("synthetic interruption before matrix commit")
            return actual_replace(root, rel, *args)
        with mock.patch.object(cp, "_replace", side_effect=interrupted):
            first = self.run_record(record)
        self.assertEqual(first["status"], "CHECKPOINT_PENDING")
        self.assertEqual(first["source_effect"], "PARTIAL")
        self.assertTrue((self.root / cp.adapter.LOCK).exists())
        with self.assertRaisesRegex(cp.nav.Invalid, "IMPORT_LOCK"):
            cp.adapter.refresh(self.root, at=T3)
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        state = cp.reconcile(self.root, "start-a", at=T3)
        self.assertEqual(state["source_effect"], "PARTIAL")
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        result = cp.reconcile(self.root, "start-a", finish_pending=True, at=T3)
        self.assertEqual(result["status"], "CHECKPOINT_PUBLISHED", result)
        self.assertFalse((self.root / cp.adapter.LOCK).exists())
        self.assertEqual(len(json.loads((self.root / "source/matrix.json").read_bytes())["events"]), 3)

    def test_publication_failure_then_foreign_edit_is_not_overwritten(self):
        old_current = self.current()[0]
        with mock.patch.object(cp.adapter, "refresh", side_effect=cp.nav.Invalid("synthetic projection refusal")):
            result = self.run_record(self.record())
        self.assertEqual(result["source_effect"], "COMMITTED")
        self.assertEqual(self.current()[0], old_current)
        self.assertFalse((self.root / cp.adapter.LOCK).exists())
        foreign = b'{"foreign":"edit preserved"}\n'
        self.write("source/matrix.json", foreign)
        closed = cp.reconcile(self.root, "start-a", finish_pending=True, at=T3)
        self.assertEqual(closed["status"], "CHECKPOINT_PENDING")
        self.assertEqual(closed["source_effect"], "UNKNOWN")
        self.assertEqual((self.root / "source/matrix.json").read_bytes(), foreign)
        self.assertEqual(self.current()[0], old_current)

    def test_invalid_owner_stale_source_paths_and_modes_refuse(self):
        source_before = (self.root / "source/matrix.json").read_bytes()
        cases = []
        wrong_owner = self.record("wrong-owner"); wrong_owner["writer"] = "Worker"; cases.append(wrong_owner)
        stale = self.record("stale"); stale["expected_source"]["sha256"] = "f" * 64; cases.append(stale)
        boolean = self.record("boolean"); boolean["expected_source"]["revision"] = True; cases.append(boolean)
        parent = self.record("parent"); parent["work_id"] = "GROUP"; cases.append(parent)
        escape = self.record("escape"); escape["evidence"] = [{"path": "../escape", "sha256": "0" * 64, "bytes": 0}]; cases.append(escape)
        for record in cases:
            with self.subTest(operation=record["operation_id"]), self.assertRaises(cp.nav.Invalid):
                self.run_record(record)
        (self.root / "prepared/link").symlink_to(self.root / "source/note.md")
        linked = self.record("linked"); linked["evidence"] = [self.pin("prepared/link")]
        with self.assertRaises(cp.nav.Invalid):
            self.run_record(linked)
        self.assertEqual((self.root / "source/matrix.json").read_bytes(), source_before)
        self.assertFalse((self.root / cp.PENDING).exists())
        with cp._lock(self.root), self.assertRaisesRegex(cp.nav.Invalid, "WRITER_BUSY"):
            self.run_record(self.record("busy"))

    def test_activity_requires_bound_record_and_dispatch_never_fabricates_it(self):
        receipt = {"scope": "ACTIVITY", "result": "PASS", "actor_id": "Worker", "step_id": "A", "state": "active", "at": T1,
                   "valid_until": "2026-01-01T00:10:00Z", "source": "supported_native_wait", "ref": "synthetic-observation-1"}
        self.write("prepared/activity.json", cp.nav.canonical(receipt))
        record = self.record()
        record["activity"] = {"observed_at": T1, "valid_until": receipt["valid_until"], "source": receipt["source"], "ref": receipt["ref"], "receipt": self.pin("prepared/activity.json")}
        dispatch = copy.deepcopy(record); dispatch["phase"] = "dispatch"; dispatch["operation_id"] = "invalid-dispatch"
        with self.assertRaisesRegex(cp.nav.Invalid, "ACTIVITY_NOT_DISPATCH"):
            self.run_record(dispatch)
        result = self.run_record(record)
        self.assertEqual(result["activity"], "RECORDED_OBSERVATION", result)
        matrix = json.loads((self.root / "source/matrix.json").read_bytes())
        self.assertEqual(matrix["activity_events"][-1]["valid_until"], receipt["valid_until"])
        self.assertEqual(matrix["activity_events"][-1]["evidence"][0]["ref"], receipt["ref"])
        self.assertTrue(all(w["activity"] is None for w in self.current()[1]["atlas"]["works"]))

    def test_retained_plan_corruption_cannot_redirect_or_change_transition(self):
        self.write("prepared/note.md", b"# Expected note\n")
        record = self.record()
        record["document_edits"] = [{"path": "source/note.md", "before": {k: self.pin("source/note.md")[k] for k in ("sha256", "bytes")}, "after": self.pin("prepared/note.md")}]
        with mock.patch.object(cp, "_finish", side_effect=lambda root, plan, *args: cp._pending_result(root, plan)):
            self.assertEqual(self.run_record(record)["status"], "CHECKPOINT_PENDING")
        base = self.root / cp.OPERATIONS / "start-a"
        plan_raw = (base / "PLAN.json").read_bytes()
        plan = json.loads(plan_raw)
        self.write("source/unowned.md", (self.root / "source/note.md").read_bytes())
        plan["files"][0]["path"] = "source/unowned.md"
        (base / "PLAN.json").write_bytes(cp.nav.canonical(plan))
        before = {p: p.read_bytes() for p in (self.root / "source").rglob("*") if p.is_file()}
        rejected = cp.reconcile(self.root, "start-a", finish_pending=True, at=T3)
        self.assertIn("RETAINED_DESTINATION_SCOPE", rejected["error"])
        self.assertEqual(before, {p: p.read_bytes() for p in (self.root / "source").rglob("*") if p.is_file()})
        plan = json.loads(plan_raw)
        source = plan["files"][-1]
        after_path = self.root / source["after"]["path"]
        changed = json.loads(after_path.read_bytes())
        changed["events"][0]["accepted"] = True
        after_path.write_bytes(cp.nav.canonical(changed))
        source["after"] = self.pin(source["after"]["path"])
        (base / "PLAN.json").write_bytes(cp.nav.canonical(plan))
        rejected = cp.reconcile(self.root, "start-a", finish_pending=True, at=T3)
        self.assertIn("RETAINED_TRANSITION_MISMATCH", rejected["error"])
        self.assertEqual(before, {p: p.read_bytes() for p in (self.root / "source").rglob("*") if p.is_file()})
        self.assertFalse((self.root / cp.adapter.LOCK).exists())

    def test_result_written_before_pending_cleanup_reconciles_without_republication(self):
        actual = cp._unlink_ours
        def interrupted(root, path, raw):
            if path == cp.PENDING:
                raise OSError("synthetic final cleanup interruption")
            return actual(root, path, raw)
        with mock.patch.object(cp, "_unlink_ours", side_effect=interrupted):
            first = self.run_record(self.record())
        self.assertEqual(first["status"], "CHECKPOINT_PENDING")
        before_source, before_current = (self.root / "source/matrix.json").read_bytes(), self.current()[0]
        before_receipt = (self.root / cp.OPERATIONS / "start-a/RESULT.json").read_bytes()
        self.assertEqual(cp.reconcile(self.root, "start-a", at=T3)["error"], "CHECKPOINT_FINALIZATION_PENDING")
        with mock.patch.object(cp.adapter, "refresh", side_effect=AssertionError("must not republish")):
            result = cp.reconcile(self.root, "start-a", finish_pending=True, at=T3)
        self.assertEqual(result["status"], "CHECKPOINT_PUBLISHED")
        self.assertFalse(result["pending"])
        self.assertEqual((self.root / "source/matrix.json").read_bytes(), before_source)
        self.assertEqual(self.current()[0], before_current)
        self.assertEqual((self.root / cp.OPERATIONS / "start-a/RESULT.json").read_bytes(), before_receipt)

    def test_patch_base_and_history_documents_refuse_before_source_effects(self):
        self.write("prepared/note.md", b"# New base would invalidate an existing patch\n")
        catalogue = {"schema": "atlas.semantic-catalog/v1", "modules": [], "contracts": [], "relations": [],
                     "work_bindings": [], "work_context": [], "patch_bindings": [{"work_id": "A", "patch_doc_id": "DOC",
                         "target_doc_id": "DOC", "base_sha256": self.pin("source/note.md")["sha256"], "selectors": ["/section"], "source_state": "proposed"}]}
        self.write("source/catalog.json", cp.nav.canonical(catalogue))
        self.binding["semantic_catalog"] = self.pin("source/catalog.json")
        self.write(".atlas/UPSTREAM.json", cp.nav.canonical(self.binding))
        record = self.record()
        record["document_edits"] = [{"path": "source/note.md", "before": {k: self.pin("source/note.md")[k] for k in ("sha256", "bytes")}, "after": self.pin("prepared/note.md")}]
        before = {p: p.read_bytes() for p in (self.root / "source").rglob("*") if p.is_file()}
        with self.assertRaisesRegex(cp.nav.Invalid, "PATCH_BASE_CHANGE"):
            self.run_record(record)
        self.assertEqual(before, {p: p.read_bytes() for p in (self.root / "source").rglob("*") if p.is_file()})
        self.binding["history"]["paths"].append("source/note.md")
        self.write(".atlas/UPSTREAM.json", cp.nav.canonical(self.binding))
        with self.assertRaisesRegex(cp.nav.Invalid, "HISTORY_IS_NOT_DOCUMENT_DESTINATION"):
            self.run_record(record)
        self.assertFalse((self.root / cp.PENDING).exists())


if __name__ == "__main__":
    unittest.main()
