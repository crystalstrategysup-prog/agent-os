"""Synthetic presentation selection and immutable-history upgrade regressions.

Run from the AgentOS repository with unittest discovery. Source scripts are read
from modules/atlas; every mutation stays in a temporary copy and synthetic root.
"""
import contextlib
import copy
import hashlib
import importlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "modules/atlas/skills/atlas/scripts"
T0 = "2026-01-01T00:00:00Z"
T1 = "2026-01-01T00:01:00Z"
T2 = "2026-01-01T00:02:00Z"
T3 = "2026-01-01T00:03:00Z"
T4 = "2026-01-01T00:04:00Z"
SECTIONS = ["roadmap", "contracts", "documents", "actors", "history", "relations", "coverage"]


@contextlib.contextmanager
def isolated_engine(path):
    names = {p.stem for p in path.glob("*.py")}
    previous_modules = {name: sys.modules.get(name) for name in names}
    previous_path = list(sys.path)
    previous_bytecode = sys.dont_write_bytecode
    try:
        for name in names:
            sys.modules.pop(name, None)
        sys.path.insert(0, str(path))
        sys.dont_write_bytecode = True
        yield importlib.import_module("import_matrix")
    finally:
        for name, module in previous_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        sys.path[:] = previous_path
        sys.dont_write_bytecode = previous_bytecode


def file_hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class AtlasReadableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="atlas-readable-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.engine = self.base / "scripts"
        shutil.copytree(SCRIPTS, self.engine, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.root = self.base / "project"
        (self.root / "source/history").mkdir(parents=True)
        (self.root / ".atlas").mkdir()

    def fixture(self, im, *, pointer="", with_history=False):
        matrix = {"schema": "synthetic.work-matrix/v1", "revision": 1, "updated_at": T1,
                  "steps": [{"id": "GROUP", "parent_id": None, "title": "Source group", "order": 1},
                            {"id": "ITEM", "parent_id": "GROUP", "title": "Source item", "order": 2,
                             "scope_note": "Complete source note " + "x" * 21000,
                             "source_definition": {"expected": "Documented scoped result", "extra": {"preserve": True}}}],
                  "events": [{"id": "EV-1", "step_id": "ITEM", "at": T1, "status": "done", "accepted": True,
                              "executor_ids": ["Worker"], "reviewer_ids": ["Reviewer"],
                              "note": "Source acceptance remains distinct from native acceptance", "evidence": [{"ref": "source/result.json"}]}],
                  "actors": [{"id": "Worker", "session_url": None}, {"id": "Reviewer", "session_url": None}],
                  "actor_events": [], "actor_updates": [], "activity_events": [],
                  "coverage": {"current_stage": "GROUP", "gaps": ["Runtime not verified"]},
                  "snapshot_summary": "A scoped source result", "custom_metadata": {"retained": [1, False, None]}}
        binding = {"schema": "atlas.upstream-binding/v1",
                   "project": {"id": "SYNTHETIC", "title": "Synthetic project", "objective": "Keep useful source facts accessible",
                               "writer": "Existing-writer", "authority_ref": "Synthetic instruction", "scope_note": "Declared source only"},
                   "matrix": {"path": "source/matrix.json", "allowed_schema": matrix["schema"], "pointer": pointer},
                   "history": {"paths": [], "directories": ["source/history"], "coverage_note": "Only retained synthetic history"},
                   "documents": [], "output": ".atlas/output"}
        raw = im.nav.canonical(matrix if not pointer else {"snapshot": {"matrix": matrix}, "unrelated": "OUTSIDE_SELECTION"})
        (self.root / "source/matrix.json").write_bytes(raw)
        (self.root / ".atlas/UPSTREAM.json").write_bytes(im.nav.canonical(binding))
        if with_history:
            previous = copy.deepcopy(matrix)
            previous["revision"] = 0
            previous["updated_at"] = T0
            previous["events"] = []
            (self.root / "source/history/initial.json").write_bytes(im.nav.canonical(previous))
        return matrix

    def alternate(self, im, snapshot, change_documents, change_project=None):
        documents = copy.deepcopy(snapshot["input"])
        change_documents(documents["documents"])
        raw = im.nav.canonical(documents)
        (self.root / "case-documents.json").write_bytes(raw)
        project = copy.deepcopy(snapshot["atlas"]["project"])
        project["documents"] = im.pin("case-documents.json", raw)
        if change_project:
            change_project(project)
        (self.root / "case-project.json").write_bytes(im.nav.canonical(project))
        return im.atlas.load_project(self.root, "case-project.json", at=T2)

    def test_exact_source_selection_and_safe_degradation(self):
        with isolated_engine(self.engine) as im:
            matrix = self.fixture(im, pointer="/snapshot/matrix")
            im.refresh(self.root, at=T2)
            _, snapshot = im.atlas.current_output(self.root / ".atlas/output")
            doc = snapshot["documents"][0]
            expected = {"schema": "atlas.presentation/v1", "renderer": "ATLAS-READABLE-1.0.0", "sections": SECTIONS,
                        "source_matrix_status": "PINNED", "source_matrix_doc_id": doc["id"], "source_matrix_sha256": doc["sha256"]}
            self.assertEqual(snapshot["atlas"]["presentation"], expected)
            self.assertEqual(im.nav.parse(doc["content"]), matrix)
            self.assertNotIn("OUTSIDE_SELECTION", doc["content"])
            self.assertTrue(all(not w["acceptance"] and not w["evidence"] and w["activity"] is None
                                for w in snapshot["atlas"]["works"]))

            pointerless = self.alternate(im, snapshot,
                lambda docs: docs[0].update(source_ref="source/matrix.json [owning matrix projection source]"),
                lambda project: project.update(source_ref="source/matrix.json pointer="))
            self.assertEqual(pointerless["atlas"]["presentation"], expected)
            explicit_empty = self.alternate(im, snapshot,
                lambda docs: docs[0].update(source_ref="source/matrix.json [owning matrix projection source] pointer="),
                lambda project: project.update(source_ref="source/matrix.json pointer="))
            self.assertEqual(explicit_empty["atlas"]["presentation"], expected)
            workspace = importlib.import_module("workspace")
            for value in (snapshot, pointerless, explicit_empty):
                self.assertEqual(workspace.source_revision(value, value["atlas"]["presentation"]),
                                 (matrix["revision"], "MATCHED_PINNED_DOCUMENT"))
            def duplicate_empty_forms(docs):
                docs[0]["source_ref"] = "source/matrix.json [owning matrix projection source]"
                docs.append({**docs[0], "id": "SECOND-EMPTY-FORM",
                             "source_ref": "source/matrix.json [owning matrix projection source] pointer="})
            ambiguous_empty = self.alternate(im, snapshot, duplicate_empty_forms,
                lambda project: project.update(source_ref="source/matrix.json pointer="))
            self.assertEqual(ambiguous_empty["atlas"]["presentation"]["source_matrix_status"], "AMBIGUOUS")
            self.assertIsNone(ambiguous_empty["atlas"]["presentation"]["source_matrix_doc_id"])
            self.assertIsNone(ambiguous_empty["atlas"]["presentation"]["source_matrix_sha256"])
            self.assertEqual(workspace.source_revision(ambiguous_empty, ambiguous_empty["atlas"]["presentation"]),
                             ("UNKNOWN", "AMBIGUOUS"))
            cases = [
                ("unrelated", lambda docs: docs[0].update(source_ref="source/matrix.json [unrelated source]"), None, "UNAVAILABLE"),
                ("archived", lambda docs: docs[0].update(lifecycle="archived"), None, "UNAVAILABLE"),
                ("ambiguous", lambda docs: docs.append({**docs[0], "id": "OTHER-DOCUMENT"}), None, "AMBIGUOUS"),
                ("native", lambda docs: None, lambda project: project.update(mode="native", source_ref="Native source description"), "UNAVAILABLE"),
            ]
            for label, change_documents, change_project, status in cases:
                with self.subTest(label=label):
                    value = self.alternate(im, snapshot, change_documents, change_project)
                    self.assertEqual(value["atlas"]["presentation"]["source_matrix_status"], status)
                    self.assertIsNone(value["atlas"]["presentation"]["source_matrix_doc_id"])
                    self.assertIsNone(value["atlas"]["presentation"]["source_matrix_sha256"])
                    self.assertEqual(value["atlas"]["works"], snapshot["atlas"]["works"])
                    self.assertEqual(value["atlas"]["summary"], snapshot["atlas"]["summary"])
            with self.assertRaisesRegex(im.nav.Invalid, "DOCUMENT_HASH"):
                self.alternate(im, snapshot, lambda docs: docs[0].update(sha256="0" * 64))

            # A valid JSON document with the marker but no matrix shape degrades;
            # a random JSON document must not become a roadmap by resemblance.
            raw = im.nav.canonical({"schema": "other/v1", "steps": [None], "events": []})
            (self.root / "not-matrix.json").write_bytes(raw)
            invalid = self.alternate(im, snapshot, lambda docs: docs[0].update(im.pin("not-matrix.json", raw)))
            self.assertEqual(invalid["atlas"]["presentation"]["source_matrix_status"], "UNAVAILABLE")

    def test_toolchain_refresh_preserves_work_and_history_then_is_noop(self):
        with isolated_engine(self.engine) as im:
            matrix = self.fixture(im, with_history=True)
            source_before = file_hashes(self.root / "source")
            binding_before = (self.root / ".atlas/UPSTREAM.json").read_bytes()
            first = im.refresh(self.root, at=T2)
            output = self.root / ".atlas/output"
            old_pointer, old = im.atlas.current_output(output)
            owning_doc = next(doc for doc in old["documents"] if doc["source_ref"] ==
                              "source/matrix.json [owning matrix projection source] pointer=")
            self.assertEqual(old["atlas"]["presentation"], {
                "schema": "atlas.presentation/v1", "renderer": "ATLAS-READABLE-1.0.0", "sections": SECTIONS,
                "source_matrix_status": "PINNED", "source_matrix_doc_id": owning_doc["id"],
                "source_matrix_sha256": owning_doc["sha256"]})
            workspace = importlib.import_module("workspace")
            self.assertEqual(workspace.source_revision(old, old["atlas"]["presentation"]),
                             (matrix["revision"], "MATCHED_PINNED_DOCUMENT"))
            old_release_files = file_hashes(output / "releases" / old_pointer["release"])
            old_state = im.nav.parse((self.root / im.STATE).read_bytes())
            old_meta = im.nav.parse((self.root / old_state["generation"] / "IMPORT.json").read_bytes())
            self.assertEqual(first["matrix_history_count"], 2)

            # Change only presentation toolchain bytes in the temporary engine.
            # Real source_bundle/cycle behavior must create one successor release.
            viewer = self.engine / "viewer.js"
            viewer.write_bytes(viewer.read_bytes() + b"\n/* synthetic presentation-only upgrade */\n")
            update = im.refresh(self.root, at=T3)
            pointer, current = im.atlas.current_output(output)
            self.assertEqual(update["status"], "IMPORTED_PARTIAL")
            self.assertEqual(update["changed_work_ids"], [])
            self.assertEqual(update["matrix_history_count"], 2)
            self.assertEqual(update["matrix_history_page_count"], 0)
            self.assertEqual(current["atlas"]["matrix_history_total"], old["atlas"]["matrix_history_total"])
            self.assertEqual(current["atlas"]["works"], old["atlas"]["works"])
            self.assertEqual(current["atlas"]["work_paths"], old["atlas"]["work_paths"])
            self.assertEqual(current["atlas"]["summary"], old["atlas"]["summary"])
            self.assertEqual(current["atlas"]["presentation"], old["atlas"]["presentation"])
            self.assertEqual(workspace.source_revision(current, current["atlas"]["presentation"]),
                             (matrix["revision"], "MATCHED_PINNED_DOCUMENT"))
            self.assertNotEqual(pointer["release"], old_pointer["release"])
            self.assertEqual(current["input"]["release"]["previous"], old_pointer["manifest_sha256"])
            self.assertEqual(current["atlas"]["project"]["projection_archive"]["previous_release"], old_pointer["release"])
            self.assertEqual(len(list((output / "releases").iterdir())), 2)
            state = im.nav.parse((self.root / im.STATE).read_bytes())
            meta = im.nav.parse((self.root / state["generation"] / "IMPORT.json").read_bytes())
            self.assertEqual(meta["matrix"], old_meta["matrix"])
            im.nav.verify_release(output, old_pointer["release"], old_pointer["manifest_sha256"])
            self.assertEqual(file_hashes(output / "releases" / old_pointer["release"]), old_release_files)
            self.assertEqual(file_hashes(self.root / "source"), source_before)
            self.assertEqual((self.root / ".atlas/UPSTREAM.json").read_bytes(), binding_before)
            before_noop = file_hashes(self.root)
            self.assertEqual(im.refresh(self.root, at=T4)["status"], "NO_CHANGE")
            self.assertEqual(file_hashes(self.root), before_noop)


if __name__ == "__main__":
    unittest.main()
