"""Two bounded real-argv tests for view readback, using synthetic local projects."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


DEFAULT_SCRIPTS = Path(__file__).resolve().parents[1] / "modules/atlas/skills/atlas/scripts"
SCRIPTS = Path(os.environ.get("ATLAS_VIEWS_SCRIPTS", DEFAULT_SCRIPTS)).resolve()
COMMAND = Path(os.environ.get("ATLAS_VIEWS_COMMAND", SCRIPTS / "workspace.py")).resolve()
T1 = "2026-01-01T00:00:00Z"
T2 = "2026-01-01T00:01:00Z"


class WorkspaceViewsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="atlas-views-test-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "project with spaces"
        (self.root / "source").mkdir(parents=True)
        (self.root / ".atlas").mkdir()
        self.matrix = {"schema": "example.work-matrix/v1", "revision": 1,
                       "updated_at": T1,
                       "steps": [{"id": "A", "parent_id": None, "title": "Keep the owning source", "created_at": T1}],
                       "events": [{"id": "E1", "step_id": "A", "at": T1, "status": "doing", "executor_ids": ["Writer"]}],
                       "actors": [{"id": "Writer"}], "actor_events": [], "actor_updates": [], "activity_events": []}
        binding = {"schema": "atlas.upstream-binding/v1",
                   "project": {"id": "EXAMPLE", "title": "Example", "objective": "Read the retained project view", "writer": "Writer", "authority_ref": "Synthetic test", "scope_note": "Synthetic input only"},
                   "matrix": {"path": "source/matrix.json", "allowed_schema": "example.work-matrix/v1"},
                   "history": {"paths": [], "directories": [], "coverage_note": "Only the declared synthetic version"},
                   "documents": [], "output": ".atlas/output"}
        self.registry = self.base / "PROJECTS.json"
        self.save(self.root / "source/matrix.json", self.matrix)
        self.save(self.root / ".atlas/UPSTREAM.json", binding)
        self.save(self.registry, {"schema": "atlas.workspace/v1", "projects": [{"key": "example", "root": str(self.root), "binding": ".atlas/UPSTREAM.json"}]})

    @staticmethod
    def encoded(value):
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()

    def save(self, path, value):
        path.write_bytes(self.encoded(value))

    def cli(self, *args, code=0):
        env = {**os.environ, "PYTHONPATH": str(SCRIPTS), "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run([sys.executable, "-B", str(COMMAND), "--registry", str(self.registry), *args],
                                cwd=self.base, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertLess(len(result.stdout.encode()), 32 * 1024)
        return json.loads(result.stdout)

    def tree(self):
        return {str(p.relative_to(self.base)): {"directory": p.is_dir(), "mode": p.stat().st_mode,
                "mtime_ns": p.stat().st_mtime_ns,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None}
                for p in self.base.rglob("*")}

    def presentation_fixture(self, *, pin_matches=True, legacy=False):
        """Reseal synthetic release data for readback tests; no renderer/UI claim."""
        output = self.root / ".atlas/output"
        pointer = json.loads((output / "CURRENT.json").read_text())
        release = output / "releases" / pointer["release"]
        snapshot = json.loads((release / "snapshot.json").read_text())
        source = next(row for row in snapshot["documents"]
                      if row.get("kind") == "json" and json.loads(row["content"]).get("schema") == "example.work-matrix/v1")
        snapshot["atlas"]["presentation"] = {
            "schema": "atlas.presentation/v1", "renderer": "ATLAS-READABLE-1.0.0",
            "sections": ["roadmap", "contracts", "documents", "actors", "history", "relations", "coverage"],
            "source_matrix_status": "PINNED", "source_matrix_doc_id": source["id"],
            "source_matrix_sha256": source["sha256"] if pin_matches else "0" * 64}
        if legacy:
            snapshot["atlas"].pop("presentation", None)
        # Wide gap data reproduces the stdout-budget risk without a large test suite.
        snapshot["atlas"]["coverage"]["issues"] = ["UNMAPPED_SYNTHETIC_ITEM"] * 5000
        snapshot["atlas"]["coverage"]["domains"][0]["missing_ids"] = ["GAP-" + str(i) for i in range(5000)]
        self.save(release / "snapshot.json", snapshot)
        manifest = json.loads((release / "MANIFEST.json").read_text())
        raw = (release / "snapshot.json").read_bytes()
        manifest["files"]["snapshot.json"] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        self.save(release / "MANIFEST.json", manifest)
        pointer["manifest_sha256"] = hashlib.sha256((release / "MANIFEST.json").read_bytes()).hexdigest()
        self.save(output / "CURRENT.json", pointer)
        return release, pointer

    def test_verified_views_are_bounded_read_only_and_do_not_follow_new_source(self):
        self.cli("refresh", "example")
        release, pointer = self.presentation_fixture()
        self.matrix["revision"] = 2
        self.matrix["updated_at"] = T2
        self.matrix["events"].append({"id": "E2", "step_id": "A", "at": T2, "status": "done", "executor_ids": ["Writer"]})
        self.save(self.root / "source/matrix.json", self.matrix)
        before = self.tree()
        result = self.cli("views", "example")
        self.assertEqual(result["status"], "ARTIFACTS_READY")
        self.assertEqual(result["current"], pointer)
        self.assertEqual(result["source_revision"], 1)
        self.assertEqual(result["source_revision_status"], "MATCHED_PINNED_DOCUMENT")
        self.assertEqual(result["freshness"]["owning_sources"], "NOT_COMPARED")
        self.assertEqual(result["presentation"], {"status": "NOT_REQUESTED", "browser": "NOT_REQUESTED"})
        self.assertEqual(result["coverage"]["issue_count"], 5000)
        self.assertEqual(result["coverage"]["domains"][0]["missing_count"], 5000)
        for section in ("contracts", "roadmap"):
            self.assertTrue(result["sections"][section]["anchor_supported"])
            self.assertEqual(result["sections"][section]["url"], (self.root / ".atlas/output/index.html").as_uri() + "#" + section)
            self.assertEqual(result["sections"][section]["immutable_url"], (release / "index.html").as_uri() + "#" + section)
        for key, name in (("html", "index.html"), ("json", "snapshot.json")):
            item = result["artifacts"][key]
            self.assertEqual(Path(item["path"]), release / name)
            self.assertEqual(item["sha256"], hashlib.sha256((release / name).read_bytes()).hexdigest())
        self.assertEqual(self.tree(), before)
        self.presentation_fixture(pin_matches=False)
        before = self.tree()
        mismatch = self.cli("views", "example")
        self.assertEqual((mismatch["source_revision"], mismatch["source_revision_status"]), ("UNKNOWN", "PIN_MISMATCH"))
        self.assertEqual(self.tree(), before)

    def test_no_current_legacy_and_incomplete_views_never_claim_opened_or_repair(self):
        before = self.tree()
        empty = self.cli("views", "example")
        self.assertEqual(empty["status"], "NO_CURRENT_VIEW")
        self.assertIsNone(empty["current"])
        self.assertIsNone(empty["view_path"])
        self.assertEqual(empty["artifacts"], {})
        self.assertEqual(self.tree(), before)
        self.cli("refresh", "example")
        self.presentation_fixture(legacy=True)
        before = self.tree()
        legacy = self.cli("views", "example")
        self.assertEqual(legacy["source_revision"], "UNKNOWN")
        for value in legacy["sections"].values():
            self.assertFalse(value["anchor_supported"])
            self.assertNotIn("#", value["url"])
        self.assertEqual(self.tree(), before)
        Path(legacy["view_path"]).write_text("SYNTHETIC CORRUPT INDEX")
        before = self.tree()
        invalid = self.cli("views", "example", code=1)
        self.assertEqual(invalid, {"status": "REFUSED", "code": "OUTPUT_FILE_HASH"})
        self.assertEqual(self.tree(), before)


if __name__ == "__main__":
    unittest.main()
