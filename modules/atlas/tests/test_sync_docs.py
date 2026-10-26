"""Bounded document snapshot lifecycle, including interrupted same-plan recovery."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/atlas/scripts"))
import catalog
import import_matrix as adapter
import sync_docs


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


class DocumentSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="atlas-docs-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "project"
        self.source = self.base / "new-docs"
        self.target = self.root / "work/atlas-sources/canonical"
        self.target.mkdir(parents=True)
        (self.root / ".atlas").mkdir()
        (self.root / "owning").mkdir()
        self.api = {"version": "1", "operations": [{"id": "Example.receive", "entry": "receive(value)",
                     "inputs": ["value: explicitly declared text"], "outputs": ["result: source declaration"], "module": "Example"}]}
        (self.target / "api.json").write_bytes(pretty(self.api))
        (self.target / "NOTES.md").write_bytes(b"# Existing document\n\nThe original source declaration.\n")
        self.matrix = {"schema": "synthetic.matrix/v1", "revision": 1, "updated_at": "2026-01-01T00:00:00Z",
                       "actors": [{"id": "Writer"}], "actor_events": [], "actor_updates": [], "activity_events": [],
                       "steps": [{"id": "A", "title": "Continue source work", "parent_id": None, "created_at": "2026-01-01T00:00:00Z"}],
                       "events": [{"id": "E1", "step_id": "A", "at": "2026-01-01T00:00:00Z", "status": "doing", "executor_ids": ["Writer"]}]}
        self.matrix_path = self.root / "owning/matrix.json"
        self.matrix_path.write_bytes(pretty(self.matrix))
        self.spec = {"schema": "atlas.catalog-source/v1", "format": "operation-registry", "path": "api.json", "document_id": "DOC-API"}
        semantic, source_pin = catalog.compile_catalog(self.target, self.spec)
        semantic["work_bindings"] = [{"work_id": "A", "entity_ids": [semantic["contracts"][0]["id"], "DOC-NOTE"]}]
        semantic["work_context"] = [{"work_id": "A", "outcome": "Retain the declared result", "next_action": {"actor": "Writer", "action": "Continue source assignment"}}]
        sem_path = "work/atlas-sources/SEMANTIC_CATALOG.json"
        sem_raw = pretty(semantic)
        (self.root / sem_path).write_bytes(sem_raw)
        rows = [{**adapter.pin(name, (self.target / name).read_bytes()), "selected_in_view": True} for name in ("NOTES.md", "api.json")]
        inventory = {"schema": "atlas.project-document-snapshot/v1", "project": "synthetic", "origin": "Explicit synthetic fixture",
                     "scope": "All declared source files", "offline_index_only": False, "files": rows, "catalog_source": source_pin}
        inventory_path = "work/atlas-sources/SOURCE_INVENTORY.json"
        (self.root / inventory_path).write_bytes(pretty(inventory))
        self.binding = {"schema": "atlas.upstream-binding/v1", "project": {"id": "SYNTHETIC", "title": "Synthetic", "objective": "Keep project control",
                        "writer": "Writer", "authority_ref": "Synthetic test", "scope_note": "Bounded fixture"},
                        "matrix": {"path": "owning/matrix.json", "allowed_schema": self.matrix["schema"]},
                        "history": {"paths": [], "directories": [], "coverage_note": "No earlier version exists in this fixture"},
                        "documents": [{"id": i, "path": p, "title": i, "role": "Pinned source copy", "domain": "documents"} for i, p in
                                      (("DOC-API", "work/atlas-sources/canonical/api.json"), ("DOC-NOTE", "work/atlas-sources/canonical/NOTES.md"),
                                       ("DOC-SOURCE-INVENTORY", inventory_path))],
                        "output": ".atlas/output", "semantic_catalog": adapter.pin(sem_path, sem_raw)}
        (self.root / ".atlas/UPSTREAM.json").write_bytes(pretty(self.binding))
        (self.root / ".atlas/CATALOG_SOURCE.json").write_bytes(pretty(self.spec))
        config = {"schema": "atlas.document-sync/v1", "destination": "work/atlas-sources/canonical", "inventory": inventory_path,
                  "catalog_spec": ".atlas/CATALOG_SOURCE.json", "semantic_catalog": sem_path}
        (self.root / ".atlas/DOCUMENT_SYNC.json").write_bytes(pretty(config))
        shutil.copytree(self.target, self.source)

    def files(self, root=None):
        root = root or self.root
        return {p.relative_to(root).as_posix(): (adapter.sha(p.read_bytes()), p.stat().st_mtime_ns)
                for p in root.rglob("*") if p.is_file()}

    def test_unchanged_documents_preserve_pretty_encoding_and_every_file(self):
        adapter.refresh(self.root)
        before = self.files()
        self.assertEqual(sync_docs.update(self.root, self.source)["status"], "NO_CHANGE")
        self.assertEqual(self.files(), before)

    def test_new_doc_and_api_delta_preserve_matrix_sources_and_history(self):
        adapter.refresh(self.root)
        old_pointer, old_snapshot = adapter.atlas.current_output(self.root / ".atlas/output")
        old_files = self.files()
        owning = self.matrix_path.read_bytes()
        api = copy.deepcopy(self.api)
        api["operations"][0]["outputs"] = ["Changed explicit result"]
        (self.source / "api.json").write_bytes(pretty(api))
        (self.source / "NEW.md").write_bytes(b"# Newly declared documentation\n")
        upstream_before = self.files(self.source)
        result = sync_docs.update(self.root, self.source)
        self.assertEqual(result["status"], "DOCUMENT_SNAPSHOT_UPDATED")
        self.assertEqual(result["projection"]["status"], "IMPORTED_PARTIAL")
        self.assertEqual(self.matrix_path.read_bytes(), owning)
        self.assertEqual(upstream_before, self.files(self.source))
        self.assertEqual((self.target / "api.json").read_bytes(), (self.source / "api.json").read_bytes())
        _, current = adapter.atlas.current_output(self.root / ".atlas/output")
        self.assertEqual(len(current["input"]["documents"]), len(old_snapshot["input"]["documents"]) + 1)
        self.assertTrue(all(c["execution"] == "NOT_RUN" for c in current["input"]["contracts"]))
        _, prior = adapter.nav.verify_release(self.root / ".atlas/output", old_pointer["release"])
        self.assertEqual(prior, old_snapshot)
        for path, state in old_files.items():
            if path.startswith(".atlas/imports/") or path.startswith(".atlas/output/releases/"):
                self.assertEqual(self.files()[path], state)
        unchanged = self.files()
        self.assertEqual(sync_docs.update(self.root, self.source)["status"], "NO_CHANGE")
        self.assertEqual(unchanged, self.files())

    def test_interruption_blocks_refresh_and_finishes_same_pinned_plan(self):
        adapter.refresh(self.root)
        (self.source / "NOTES.md").write_bytes(b"# Updated original document\n")
        original_replace = sync_docs.replace_one
        calls = []
        def interrupt(root, item, raw):
            if calls:
                raise OSError("Synthetic interruption after first file")
            calls.append(item["path"])
            return original_replace(root, item, raw)
        with mock.patch.object(sync_docs, "replace_one", interrupt):
            with self.assertRaisesRegex(OSError, "Synthetic interruption"):
                sync_docs.update(self.root, self.source)
        pending_before = (self.root / sync_docs.PENDING).read_bytes()
        before_read = self.files()
        report = sync_docs.reconcile(self.root)
        self.assertEqual(report["status"], "DOCUMENT_SYNC_RECONCILE_REQUIRED")
        self.assertEqual({row["state"] for row in report["files"]}, {"BEFORE", "AFTER"})
        self.assertEqual(before_read, self.files())
        with self.assertRaisesRegex(adapter.nav.Invalid, "DOCUMENT_SYNC_PENDING_RECONCILE_REQUIRED"):
            adapter.refresh(self.root)
        finished = sync_docs.reconcile(self.root, finish_pending=True)
        self.assertEqual(finished["generation"], json.loads(pending_before)["generation"])
        self.assertFalse((self.root / sync_docs.PENDING).exists())
        self.assertEqual(finished["projection"]["status"], "IMPORTED_PARTIAL")

    def test_symlink_source_refuses_before_snapshot_write(self):
        (self.source / "linked.md").symlink_to(self.matrix_path)
        before = self.files()
        with self.assertRaisesRegex(adapter.nav.Invalid, "DOCUMENT_SOURCE_SYMLINK"):
            sync_docs.update(self.root, self.source)
        self.assertEqual(before, self.files())

    def test_manual_generated_card_edits_are_not_silently_overwritten(self):
        path = self.root / self.binding["semantic_catalog"]["path"]
        data = json.loads(path.read_bytes())
        data["contracts"][0]["auth"] = "Explicit manual review"
        raw = pretty(data)
        path.write_bytes(raw)
        self.binding["semantic_catalog"] = adapter.pin(self.binding["semantic_catalog"]["path"], raw)
        (self.root / ".atlas/UPSTREAM.json").write_bytes(pretty(self.binding))
        before = self.files()
        with self.assertRaisesRegex(adapter.nav.Invalid, "MANUAL_CATALOG_EDITS_REQUIRE_RECONCILE"):
            sync_docs.update(self.root, self.source)
        self.assertEqual(before, self.files())

    def test_removed_bound_document_requires_explicit_retirement(self):
        (self.source / "NOTES.md").unlink()
        before = self.files()
        with self.assertRaisesRegex(adapter.nav.Invalid, "DOCUMENT_REMOVAL_REQUIRES_EXPLICIT_RETIREMENT"):
            sync_docs.update(self.root, self.source)
        self.assertEqual(before, self.files())

    def test_unregistered_structured_files_are_not_copied_as_new_documents(self):
        (self.source / "credentials.json").write_bytes(b'{"synthetic":"never-a-real-secret"}\n')
        before = self.files()
        with self.assertRaisesRegex(adapter.nav.Invalid, "UNREGISTERED_NON_MARKDOWN_DOCUMENT"):
            sync_docs.update(self.root, self.source)
        self.assertEqual(before, self.files())
        self.assertFalse((self.target / "credentials.json").exists())

    def test_invalid_or_oversized_selected_text_refuses_before_write(self):
        for raw, code in ((b"\xffinvalid", "DOCUMENT_UTF8"), (b"x" * (adapter.nav.MAX_FILE + 1), "DOCUMENT_SELECTED_FILE_LIMIT")):
            with self.subTest(code=code):
                (self.source / "NOTES.md").write_bytes(raw)
                before = self.files()
                with self.assertRaisesRegex(adapter.nav.Invalid, code):
                    sync_docs.update(self.root, self.source)
                self.assertEqual(before, self.files())

    def test_recovery_refuses_concurrent_document_changes(self):
        (self.source / "NOTES.md").write_bytes(b"# New proposed version\n")
        with mock.patch.object(sync_docs, "replace_one", side_effect=OSError("Synthetic stop")):
            with self.assertRaises(OSError):
                sync_docs.update(self.root, self.source)
        (self.target / "NOTES.md").write_bytes(b"# Other writer intervened\n")
        before = self.files()
        with self.assertRaisesRegex(adapter.nav.Invalid, "DOCUMENT_DESTINATION_CHANGED_RECONCILE"):
            sync_docs.reconcile(self.root, finish_pending=True)
        self.assertEqual(before, self.files())


if __name__ == "__main__":
    unittest.main()
