"""History lifetime and bounded metadata checks using only synthetic local inputs."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/atlas/scripts"))
import import_matrix as im

T1 = "2026-01-01T00:00:00Z"
T2 = "2026-01-01T00:01:00Z"
T3 = "2026-01-01T00:02:00Z"
T4 = "2026-01-01T00:03:00Z"
T5 = "2026-01-01T00:04:00Z"


class ImportHistoryPageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="atlas-history-page-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "source/history").mkdir(parents=True)
        (self.root / ".atlas").mkdir()
        self.matrix = {"schema": "example.work-matrix/v1", "revision": 1, "updated_at": T1,
                       "steps": [{"id": "A", "parent_id": None, "title": "Synthetic work", "created_at": T1}],
                       "events": [{"id": "E-A", "step_id": "A", "at": T1, "status": "planned", "executor_ids": ["Actor-A"]}],
                       "actors": [{"id": "Actor-A"}], "actor_events": [], "actor_updates": [], "activity_events": []}
        self.binding = {"schema": "atlas.upstream-binding/v1", "project": {
            "id": "HISTORY-EXAMPLE", "title": "History example", "objective": "Retain every selected matrix",
            "writer": "Existing-writer", "authority_ref": "Synthetic fixture", "scope_note": "Declared synthetic inputs only"},
            "matrix": {"path": "source/matrix.json", "allowed_schema": "example.work-matrix/v1"},
            "history": {"paths": [], "directories": ["source/history"], "coverage_note": "Synthetic complete selected sequence"},
            "documents": [], "output": ".atlas/output"}
        self.save()

    def save(self):
        (self.root / "source/matrix.json").write_bytes(im.nav.canonical(self.matrix))
        (self.root / ".atlas/UPSTREAM.json").write_bytes(im.nav.canonical(self.binding))

    def add_history(self, revision, at=T1, name=None):
        model = {**copy.deepcopy(self.matrix), "revision": revision, "updated_at": at}
        raw = im.nav.canonical(model)
        path = "source/history/" + (name or f"{revision:05}.json")
        (self.root / path).write_bytes(raw)
        return model, im.pin(path, raw)

    def metadata(self):
        state = json.loads((self.root / im.STATE).read_bytes())
        return state, json.loads((self.root / state["generation"] / "IMPORT.json").read_bytes())

    def projection_tree(self):
        return {str(p.relative_to(self.root)): im.sha(p.read_bytes()) for p in (self.root / ".atlas").rglob("*") if p.is_file()}

    def test_2001_distinct_histories_reuse_pages_warm_no_change_and_remain_queryable(self):
        originals = []
        for revision in range(1, 1001):
            self.matrix, source_pin = self.add_history(revision)
            originals.append(source_pin)
        self.save()
        first = im.refresh(self.root, at=T2)
        self.assertEqual(first["matrix_history_count"], 1000)
        first_state, _ = self.metadata()
        first_files = self.projection_tree()
        for revision in range(1001, 2001):
            self.matrix, source_pin = self.add_history(revision, T2)
            originals.append(source_pin)
        self.save()
        self.assertEqual(im.refresh(self.root, at=T3)["matrix_history_count"], 2000)
        _, before = self.metadata()
        self.matrix, source_pin = self.add_history(2001, T3, "00000-new.json")
        originals.append(source_pin)
        self.save()
        third = im.refresh(self.root, at=T4)
        self.assertEqual(third["matrix_history_count"], 2001)
        self.assertEqual(third["matrix_history_page_count"], 1)
        _, after = self.metadata()
        self.assertNotIn("history_origins", after)
        self.assertNotIn("retained_matrices", after)
        self.assertEqual(after["history_metadata"]["row_count"], 4002)
        self.assertEqual(set(after["identity"]["histories"]), {"count", "sha256"})
        self.assertEqual(after["identity"]["histories"]["count"], 2001)
        self.assertLess(len(im.nav.canonical(after)), 64 * 1024)
        for key in im.HISTORY_SECTIONS:
            pages = after["history_metadata"][key]["pages"]
            self.assertEqual([p["count"] for p in pages], [2000, 1])
            self.assertEqual(pages[0], before["history_metadata"][key]["pages"][0])
        observed = []
        actual_read = im.read
        def traced(root, path, *args, **kwargs):
            observed.append(path)
            return actual_read(root, path, *args, **kwargs)
        unchanged = self.projection_tree()
        with mock.patch.object(im, "read", side_effect=traced):
            warm = im.refresh(self.root, at=T5)
        self.assertEqual(warm["status"], "NO_CHANGE")
        self.assertFalse(any(p.startswith("source/history/") for p in observed))
        self.assertFalse(any(p.startswith(first_state["generation"] + "/history/") for p in observed))
        self.assertEqual(unchanged, self.projection_tree())
        self.assertEqual(warm["capacity"]["metadata_rows"], {"used": 4002, "limit": 100000, "remaining": 95998})
        self.assertEqual(warm["capacity"]["source_entries"]["used"], 2001)
        self.assertEqual(warm["capacity"]["new_matrix_page"]["used"], 0)
        first_page = im.atlas.history(self.root / ".atlas/output", limit=100)
        self.assertTrue(first_page["has_more"])
        second_page = im.atlas.history(self.root / ".atlas/output", limit=100, cursor=first_page["next_cursor"])
        self.assertFalse(second_page["has_more"])
        entries = first_page["imported_matrix_history"] + second_page["imported_matrix_history"]
        self.assertEqual(len(entries), 2001)
        self.assertEqual({r["file"]["sha256"] for r in entries}, {p["sha256"] for p in originals})
        self.assertTrue(all(r["raw_source_read_now"] is False for r in entries))
        now = self.projection_tree()
        for path, digest in first_files.items():
            if path.startswith(first_state["generation"] + "/") or "/releases/" in path:
                self.assertEqual(now[path], digest)
        for p in originals:
            self.assertEqual(im.pin(p["path"], (self.root / p["path"]).read_bytes()), p)

    def test_metadata_tamper_refuses_before_projection_changes(self):
        self.add_history(1)
        im.refresh(self.root, at=T2)
        _, meta = self.metadata()
        page = meta["history_metadata"]["history_origins"]["pages"][0]
        path = self.root / page["path"]
        path.write_bytes(path.read_bytes() + b" ")
        before = self.projection_tree()
        with self.assertRaisesRegex(im.nav.Invalid, "IMPORT_HISTORY_PAGE_HASH"):
            im.refresh(self.root, at=T3)
        self.assertEqual(before, self.projection_tree())
        self.assertFalse((self.root / im.LOCK).exists())

    def test_index_strict_counts_page_paths_and_symlinks(self):
        self.add_history(1)
        im.refresh(self.root, at=T2)
        _, meta = self.metadata()
        mutations = [
            (lambda x: x["history_metadata"].update(row_count=True), "CAPACITY"),
            (lambda x: x["history_metadata"]["history_origins"].update(count=True), "SECTION_COUNT"),
            (lambda x: x["history_metadata"]["history_origins"]["pages"][0].update(count=True), "PAGE_COUNT"),
            (lambda x: x["history_metadata"]["history_origins"]["pages"][0].update(path="../escape.json"), "UNSAFE_PATH"),
            (lambda x: x["history_metadata"]["history_origins"].update(sha256="0" * 64), "SECTION_HASH"),
        ]
        for change, code in mutations:
            with self.subTest(code=code):
                invalid = copy.deepcopy(meta)
                change(invalid)
                with self.assertRaisesRegex(im.nav.Invalid, code):
                    im.hydrate_history_metadata(self.root, invalid)
        page = self.root / meta["history_metadata"]["history_origins"]["pages"][0]["path"]
        saved = page.with_suffix(".saved")
        page.rename(saved)
        page.symlink_to(saved)
        with self.assertRaisesRegex(im.nav.Invalid, "SYMLINK"):
            im.hydrate_history_metadata(self.root, meta)

    def test_legacy_inline_metadata_migrates_without_old_source_payload_reads(self):
        self.add_history(1)
        im.refresh(self.root, at=T2)
        state, meta = self.metadata()
        # A synthetic v1.1 IMPORT layout, with an exact matching state pin.
        legacy = im.hydrate_history_metadata(self.root, meta)
        legacy.pop("history_metadata")
        legacy["version"] = "ATLAS-WM-IMPORT-1.1.0"
        legacy["identity"]["histories"] = [{"path": r["path"], "sha256": r["selected_sha256"]} for r in legacy["history_origins"]]
        raw = im.nav.canonical(legacy)
        (self.root / state["generation"] / "IMPORT.json").write_bytes(raw)
        state["generation_meta_sha256"] = im.sha(raw)
        (self.root / im.STATE).write_bytes(im.nav.canonical(state))
        self.matrix["revision"] = 2
        self.matrix["updated_at"] = T2
        self.save()
        seen = []
        actual_read = im.read
        def traced(root, path, *args, **kwargs):
            seen.append(path)
            return actual_read(root, path, *args, **kwargs)
        with mock.patch.object(im, "read", side_effect=traced):
            result = im.refresh(self.root, at=T3)
        self.assertEqual(result["matrix_history_count"], 2)
        self.assertNotIn("source/history/00001.json", seen)
        _, current = self.metadata()
        self.assertIn("history_metadata", current)
        self.assertNotIn("retained_matrices", current)

    def test_new_page_and_total_metadata_capacity_refuse_before_generation(self):
        for revision in range(1, 2002):
            self.matrix, _ = self.add_history(revision)
        self.save()
        before = self.projection_tree()
        with self.assertRaisesRegex(im.nav.Invalid, "IMPORT_NEW_MATRIX_PAGE_CAPACITY_EXCEEDED"):
            im.refresh(self.root, at=T2)
        self.assertEqual(before, self.projection_tree())
        self.assertFalse((self.root / ".atlas/imports").exists())
        # Exercise the same combined-row gate at a smaller budget without writing
        # 100001 files; the real 100000 bound is asserted separately.
        self.assertEqual(im.MAX_METADATA_ROWS, 100000)
        with mock.patch.object(im, "MAX_METADATA_ROWS", 4001):
            with self.assertRaisesRegex(im.nav.Invalid, "IMPORT_HISTORY_METADATA_CAPACITY_EXCEEDED"):
                im.refresh(self.root, at=T2)
        self.assertEqual(before, self.projection_tree())

    def test_directory_scan_budget_counts_non_json_entries_and_stops(self):
        self.assertEqual(im.MAX_SOURCE_ENTRIES, 100000)
        scanned = []
        class Entries:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def __iter__(self):
                for n in range(150000):
                    scanned.append(n)
                    yield types.SimpleNamespace(name="ignored.txt")
        with mock.patch.object(im.os, "scandir", return_value=Entries()):
            with self.assertRaisesRegex(im.nav.Invalid, "IMPORT_SOURCE_ENTRY_CAPACITY_EXCEEDED"):
                im.history_paths(self.root, self.binding)
        self.assertEqual(len(scanned), 100001)
        self.assertFalse((self.root / ".atlas/imports").exists())

    def test_new_raw_budget_stops_before_reading_over_limit_file_or_writing_generation(self):
        self.assertEqual(im.atlas.MAX_SELECTED, 32 * 1024 * 1024)
        raw = im.nav.canonical({**self.matrix, "padding": "x" * (7 * 1024 * 1024)})
        for index in range(5):
            (self.root / f"source/history/{index}.json").write_bytes(raw)
        seen = []
        actual_read = im.read
        def traced(root, path, *args, **kwargs):
            seen.append(path)
            return actual_read(root, path, *args, **kwargs)
        before = self.projection_tree()
        with mock.patch.object(im, "read", side_effect=traced):
            with self.assertRaisesRegex(im.nav.Invalid, "IMPORT_TOTAL_LIMIT_NEW_INPUTS_ARCHIVE_REQUIRED"):
                im.refresh(self.root, at=T2)
        self.assertEqual(len([p for p in seen if p.startswith("source/history/")]), 4)
        self.assertNotIn("source/history/4.json", seen)
        self.assertFalse((self.root / ".atlas/imports").exists())
        self.assertEqual(before, self.projection_tree())

    def test_document_pending_blocks_before_lock_and_is_rechecked_under_lock(self):
        pending = self.root / im.DOC_PENDING
        raw = im.nav.canonical({"operation_id": "SYNTHETIC-DOC-SYNC"})
        pending.write_bytes(raw)
        before = self.projection_tree()
        with self.assertRaisesRegex(im.nav.Invalid, "DOCUMENT_SYNC_PENDING_RECONCILE_REQUIRED"):
            im.refresh(self.root, at=T2)
        self.assertEqual(before, self.projection_tree())
        self.assertFalse((self.root / im.LOCK).exists())
        result = im.reconcile(self.root)
        self.assertEqual(result["status"], "RECONCILE_REQUIRED")
        self.assertEqual(result["doc_sync_pending"], {"operation_id": "SYNTHETIC-DOC-SYNC"})
        pending.unlink()
        actual_open = im.os.open
        def race(path, flags, *args, **kwargs):
            fd = actual_open(path, flags, *args, **kwargs)
            if Path(path) == self.root / im.LOCK:
                pending.write_bytes(raw)
            return fd
        with mock.patch.object(im.os, "open", side_effect=race):
            with self.assertRaisesRegex(im.nav.Invalid, "DOCUMENT_SYNC_PENDING_RECONCILE_REQUIRED"):
                im.refresh(self.root, at=T2)
        self.assertFalse((self.root / ".atlas/imports").exists())
        self.assertFalse((self.root / im.LOCK).exists())


if __name__ == "__main__":
    unittest.main()
