"""Bounded adapter regression tests. All inputs are synthetic local project data."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/atlas/scripts"))
import import_matrix as im

T1 = "2026-01-01T00:00:00Z"
T2 = "2026-01-01T00:01:00Z"
T3 = "2026-01-01T00:02:00Z"


class ImportMatrixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="atlas-import-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "source/history").mkdir(parents=True)
        (self.root / ".atlas").mkdir()
        self.matrix = {"schema": "example.work-matrix/v1", "revision": 1, "updated_at": T1,
                       "steps": [{"id": "GROUP", "parent_id": None, "title": "Group", "created_at": T1}] +
                                [{"id": x, "parent_id": "GROUP", "title": "Work " + x, "created_at": T1, "source_definition": {"expected": x}} for x in ("A", "B", "U", "W")],
                       "events": [{"id": "E-GROUP", "step_id": "GROUP", "at": T1, "status": "done", "executor_ids": ["Actor-A"], "note": "Reported source status"},
                                  {"id": "E-A", "step_id": "A", "at": T1, "status": "doing", "executor_ids": ["Actor-A"], "note": "Source doing"},
                                  {"id": "E-B", "step_id": "B", "at": T1, "status": "done", "executor_ids": ["Actor-B"], "accepted": True, "note": "Source accepted claim"},
                                  {"id": "E-U", "step_id": "U", "at": T1, "status": "done", "executor_ids": ["Actor-A", "Actor-B"], "note": "Multiple executors"},
                                  {"id": "E-W", "step_id": "W", "at": T1, "status": "waiting", "note": "Waiting"}],
                       "actors": [{"id": "Actor-A"}, {"id": "Actor-B"}], "actor_events": [], "actor_updates": [], "activity_events": []}
        self.binding = {"schema": "atlas.upstream-binding/v1", "project": {"id": "EXAMPLE", "title": "Example", "objective": "Controlled local project", "writer": "Existing-writer", "authority_ref": "Synthetic test instruction", "scope_note": "Partial declared source replay"},
                        "matrix": {"path": "source/matrix.json", "allowed_schema": "example.work-matrix/v1"},
                        "history": {"paths": [], "directories": ["source/history"], "coverage_note": "Earlier full versions unavailable"}, "documents": [], "output": ".atlas/output"}
        self.save()

    def save(self):
        (self.root / "source/matrix.json").write_bytes(im.nav.canonical(self.matrix))
        (self.root / ".atlas/UPSTREAM.json").write_bytes(im.nav.canonical(self.binding))

    def tree(self):
        return {str(p.relative_to(self.root)): im.sha(p.read_bytes()) for p in self.root.rglob("*") if p.is_file()}

    def snapshot(self):
        return im.atlas.current_output(self.root / ".atlas/output")[1]

    def works(self):
        return {w["id"]: w for w in self.snapshot()["atlas"]["works"]}

    def test_first_import_noop_and_source_status_boundaries(self):
        source_before = (self.root / "source/matrix.json").read_bytes()
        first = im.refresh(self.root, at=T2)
        self.assertEqual(first["status"], "IMPORTED_PARTIAL")
        w = self.works()
        self.assertEqual({k: w[k]["state"] for k in ("GROUP", "A", "B", "U", "W")},
                         {"GROUP": "PLANNED", "A": "DOING", "B": "REVIEW", "U": "UNKNOWN", "W": "PAUSED"})
        self.assertTrue(all(x["activity"] is None and x["acceptance"] == [] and x["evidence"] == [] for x in w.values()))
        self.assertEqual((self.root / "source/matrix.json").read_bytes(), source_before)
        before = self.tree()
        self.assertEqual(im.refresh(self.root, at=T3)["status"], "NO_CHANGE")
        self.assertEqual(before, self.tree())
        self.assertEqual(self.snapshot()["atlas"]["coverage"]["status"], "PARTIAL")

    def test_append_updates_only_affected_work_and_preserves_history(self):
        im.refresh(self.root, at=T2)
        old = self.works()
        old_paths = self.snapshot()["atlas"]["work_paths"]
        original = (self.root / "source/matrix.json").read_bytes()
        (self.root / "source/history/one.json").write_bytes(original)
        self.matrix["events"].append({"id": "E-A-2", "step_id": "A", "at": T2, "status": "done", "executor_ids": ["Actor-A"], "note": "New source result"})
        self.matrix["revision"] = 2
        self.matrix["updated_at"] = T2
        self.save()
        result = im.refresh(self.root, at=T3)
        self.assertEqual(set(result["changed_work_ids"]), {"A", im.GAP_ID})
        new = self.works()
        self.assertEqual(new["A"]["events"][:len(old["A"]["events"])], old["A"]["events"])
        self.assertEqual(old_paths["B"], self.snapshot()["atlas"]["work_paths"]["B"])
        self.assertEqual(new["B"], old["B"])
        self.assertEqual(result["matrix_history_count"], 2)
        self.assertEqual(len(self.snapshot()["atlas"]["matrix_history"]), 1)
        self.assertEqual((self.root / "source/history/one.json").read_bytes(), original)

    def test_event_rewrite_refused_before_projection_mutation(self):
        im.refresh(self.root, at=T2)
        self.matrix["events"][0]["note"] = "Rewritten"
        self.save()
        before = self.tree()
        with self.assertRaisesRegex(im.nav.Invalid, "SOURCE_EVENT_REWRITE"):
            im.refresh(self.root, at=T3)
        self.assertEqual(before, self.tree())

    def test_definition_rewrite_refused(self):
        im.refresh(self.root, at=T2)
        self.matrix["steps"][1]["source_definition"] = {"expected": "different"}
        self.save()
        with self.assertRaisesRegex(im.nav.Invalid, "SOURCE_DEFINITION_REWRITE:A"):
            im.refresh(self.root, at=T3)

    def test_document_append_and_content_versions_without_reset(self):
        im.refresh(self.root, at=T2)
        (self.root / "source/contract.md").write_text("# Contract draft\n")
        self.binding["documents"].append({"id": "CONTRACT", "path": "source/contract.md", "title": "Contract", "role": "contract draft", "domain": "contracts"})
        self.save()
        im.refresh(self.root, at=T3)
        first = copy.deepcopy(self.snapshot()["input"]["documents"])
        first_release = self.snapshot()["input"]["release"]["id"]
        (self.root / "source/contract.md").write_text("# Contract revision\n")
        im.refresh(self.root, at="2026-01-01T00:03:00Z")
        second = self.snapshot()["input"]["documents"]
        self.assertEqual(len(second), len(first))
        self.assertNotIn(first[-1]["id"], [d["id"] for d in second])
        _, archived = im.nav.verify_release(self.root / ".atlas/output", first_release)
        self.assertEqual(archived["input"]["documents"], first)
        self.assertEqual((self.root / first[-1]["path"]).read_text(), "# Contract draft\n")

    def save_catalog(self, catalog):
        raw = im.nav.canonical(catalog)
        (self.root / "source/catalog.json").write_bytes(raw)
        self.binding["semantic_catalog"] = im.pin("source/catalog.json", raw)
        self.save()

    def catalog_fixture(self):
        for key in ("DA", "DB"):
            path = "source/" + key + ".md"
            (self.root / path).write_text("# " + key + " declaration\n")
            self.binding["documents"].append({"id": key, "path": path, "title": key, "role": "explicit source declaration", "domain": "documents"})
        modules = [{"id": "M" + key, "title": "Module " + key, "purpose": "Synthetic " + key, "state_owner": "Existing-writer", "dependencies": [], "docs": ["D" + key]} for key in ("A", "B")]
        contracts = [{"id": "C" + key, "contract_key": "API-" + key, "title": "Method " + key, "version": "1", "lifecycle": "current", "module": "M" + key,
                      "state_owner": "Existing-writer", "input": "Explicit input", "output": "Explicit result", "parameters": [], "errors": [], "auth": "Existing authorization",
                      "dependencies": ["CB"] if key == "A" else [], "usage": "Documented source declaration", "docs": ["D" + key], "evidence_state": "FACT", "execution": "NOT_RUN"} for key in ("A", "B")]
        return {"schema": "atlas.semantic-catalog/v1", "modules": modules, "contracts": contracts,
                "relations": [{"from": "DA", "to": "CA", "type": "describes", "evidence_docs": ["DA"]}],
                "work_bindings": [{"work_id": "A", "entity_ids": ["CA"]}, {"work_id": "B", "entity_ids": ["CB"]}],
                "work_context": [{"work_id": "B", "outcome": "Source-defined result B", "result_claim": "Prior documentary acceptance only", "next_action": {"actor": "Existing-writer", "action": "Reuse the preserved source result for the next dependent change"}}],
                "patch_bindings": []}

    def test_semantic_packet_dependency_closure_and_legacy_result_scope(self):
        catalog = self.catalog_fixture()
        catalog["patch_bindings"] = [{"work_id": "A", "patch_doc_id": "DB", "target_doc_id": "DA", "base_sha256": im.sha((self.root / "source/DA.md").read_bytes()), "selectors": ["/method"], "source_state": "APPLIED in historical source claim"}]
        self.save_catalog(catalog)
        im.refresh(self.root, at=T2)
        packet = im.atlas.packet(self.snapshot(), "A")
        self.assertEqual(len(packet["contracts"]), 2)
        self.assertEqual(len(packet["modules"]), 2)
        self.assertEqual(len(packet["documents"]), 2)
        self.assertEqual(next(a["patch"]["state"] for a in packet["work"]["artifacts"] if a["role"] == "patch"), "PROPOSED")
        work = self.works()["B"]
        self.assertEqual(work["outcome"], "Source-defined result B")
        self.assertIn("SOURCE_CLAIM", work["result"])
        self.assertIn('"accepted":true', work["result"])
        self.assertIn("Prior documentary acceptance only", work["result"])
        self.assertEqual(work["acceptance"], [])
        self.assertEqual(work["evidence"], [])
        self.assertIn("Reuse", work["next_action"]["action"])
        before = self.tree()
        self.assertEqual(im.refresh(self.root, at=T3)["status"], "NO_CHANGE")
        self.assertEqual(before, self.tree())

    def test_semantic_document_delta_does_not_rewrite_unrelated_work(self):
        catalog = self.catalog_fixture()
        self.save_catalog(catalog)
        im.refresh(self.root, at=T2)
        previous = self.works()
        old_cards = {c["contract_key"]: c for c in self.snapshot()["input"]["contracts"]}
        (self.root / "source/DA.md").write_text("# DA revised declaration\n")
        result = im.refresh(self.root, at=T3)
        self.assertIn("A", result["changed_work_ids"])
        self.assertNotIn("B", result["changed_work_ids"])
        self.assertEqual(previous["B"], self.works()["B"])
        cards = {c["contract_key"]: c for c in self.snapshot()["input"]["contracts"]}
        self.assertNotEqual(old_cards["API-A"]["id"], cards["API-A"]["id"])
        self.assertEqual(old_cards["API-B"], cards["API-B"])
        self.assertEqual(len(self.snapshot()["input"]["documents"]), 3)

    def test_catalog_pin_and_patch_base_refuse_without_publishing(self):
        catalog = self.catalog_fixture()
        self.save_catalog(catalog)
        im.refresh(self.root, at=T2)
        old_project = (self.root / im.PROJECT).read_bytes()
        (self.root / "source/catalog.json").write_text('{}\n')
        with self.assertRaisesRegex(im.nav.Invalid, "SEMANTIC_CATALOG_PIN"):
            im.refresh(self.root, at=T3)
        self.assertEqual(old_project, (self.root / im.PROJECT).read_bytes())
        catalog["patch_bindings"] = [{"work_id": "A", "patch_doc_id": "DB", "target_doc_id": "DA", "base_sha256": "0" * 64, "selectors": ["/method"], "source_state": "proposed"}]
        self.save_catalog(catalog)
        with self.assertRaisesRegex(im.nav.Invalid, "SEMANTIC_PATCH_BASE_CHANGED:A"):
            im.refresh(self.root, at=T3)
        self.assertEqual(old_project, (self.root / im.PROJECT).read_bytes())

    def test_retained_history_warm_read_is_cached_and_stat_delta_is_rehashed(self):
        original = (self.root / "source/matrix.json").read_bytes()
        history = self.root / "source/history/one.json"
        history.write_bytes(original)
        im.refresh(self.root, at=T2)
        actual_read = im.read
        seen = []
        def traced_read(root, path, *args, **kwargs):
            seen.append(path)
            return actual_read(root, path, *args, **kwargs)
        with mock.patch.object(im, "read", side_effect=traced_read):
            self.assertEqual(im.refresh(self.root, at=T3)["status"], "NO_CHANGE")
        self.assertNotIn("source/history/one.json", seen)
        rewritten = copy.deepcopy(self.matrix)
        rewritten["events"][0]["note"] = "Forbidden historical replacement"
        history.write_bytes(im.nav.canonical(rewritten))
        before = self.tree()
        with self.assertRaisesRegex(im.nav.Invalid, "SOURCE_HISTORY_REWRITE_OR_REMOVAL"):
            im.refresh(self.root, at=T3)
        self.assertEqual(before, self.tree())

    def test_writer_binding_change_refused(self):
        im.refresh(self.root, at=T2)
        self.binding["project"]["writer"] = "Different-writer"
        self.save()
        with self.assertRaisesRegex(im.nav.Invalid, "UPSTREAM_AUTHORITY_MIGRATION_REQUIRED"):
            im.refresh(self.root, at=T3)

    def test_pointer_excludes_envelope_and_unrelated_changes_are_noop(self):
        self.binding["matrix"]["pointer"] = "/currentPriority1ParallelWork/ownerWorkMatrix"
        self.save()
        envelope = {"currentPriority1ParallelWork": {"ownerWorkMatrix": self.matrix}, "unrelated": "DO_NOT_COPY_ENVELOPE"}
        (self.root / "source/matrix.json").write_bytes(im.nav.canonical(envelope))
        im.refresh(self.root, at=T2)
        for p in (self.root / ".atlas").rglob("*"):
            if p.is_file():
                self.assertNotIn(b"DO_NOT_COPY_ENVELOPE", p.read_bytes())
        before = {p: h for p, h in self.tree().items() if p.startswith(".atlas/")}
        envelope["unrelated"] = "UNRELATED_CHANGED"
        (self.root / "source/matrix.json").write_bytes(im.nav.canonical(envelope))
        self.assertEqual(im.refresh(self.root, at=T3)["status"], "NO_CHANGE")
        self.assertEqual(before, {p: h for p, h in self.tree().items() if p.startswith(".atlas/")})

    def test_confirmed_prepublication_failure_rolls_back_own_pointer(self):
        source = (self.root / "source/matrix.json").read_bytes()
        with mock.patch.object(im.atlas, "cycle", side_effect=im.nav.Invalid("TEST_PREPUBLICATION_FAILURE")):
            with self.assertRaisesRegex(im.nav.Invalid, "TEST_PREPUBLICATION_FAILURE"):
                im.refresh(self.root, at=T2)
        self.assertFalse((self.root / im.PROJECT).exists())
        self.assertFalse((self.root / im.PENDING).exists())
        self.assertEqual(source, (self.root / "source/matrix.json").read_bytes())
        self.assertEqual(im.refresh(self.root, at=T3)["status"], "IMPORTED_PARTIAL")

    def test_lost_ack_retains_original_pending_identity_for_readback(self):
        cycle = im.atlas.cycle
        def lost_ack(*args, **kwargs):
            cycle(*args, **kwargs)
            raise im.nav.Invalid("TEST_LOST_ACK")
        with mock.patch.object(im.atlas, "cycle", side_effect=lost_ack):
            with self.assertRaisesRegex(im.nav.Invalid, "TEST_LOST_ACK"):
                im.refresh(self.root, at=T2)
        before = self.tree()
        r = im.reconcile(self.root)
        self.assertEqual(r["status"], "RECONCILE_REQUIRED")
        self.assertIsNotNone(r["pending"])
        self.assertIsNotNone(r["output_current"])
        self.assertEqual(before, self.tree())
        with self.assertRaisesRegex(im.nav.Invalid, "IMPORT_PENDING_RECONCILE_REQUIRED"):
            im.refresh(self.root, at=T3)


if __name__ == "__main__":
    unittest.main()
