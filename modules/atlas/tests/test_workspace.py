"""Real argv tests for the explicit local workspace boundary; synthetic inputs only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/atlas/scripts"
COMMAND = SCRIPTS / "workspace.py"
T1 = "2026-01-01T00:00:00Z"
T2 = "2026-01-01T00:01:00Z"


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="atlas-workspace-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "project with spaces"
        (self.root / "source").mkdir(parents=True)
        (self.root / ".atlas").mkdir()
        self.matrix = {"schema": "example.work-matrix/v1", "revision": 1, "updated_at": T1,
                       "steps": [{"id": "A", "parent_id": None, "title": "Preserve source work", "created_at": T1}],
                       "events": [{"id": "E-A", "step_id": "A", "at": T1, "status": "doing", "executor_ids": ["Existing-writer"], "note": "Source observation"}],
                       "actors": [{"id": "Existing-writer"}], "actor_events": [], "actor_updates": [], "activity_events": []}
        self.binding = {"schema": "atlas.upstream-binding/v1", "project": {"id": "EXAMPLE", "title": "Example", "objective": "Controlled local project", "writer": "Existing-writer", "authority_ref": "Synthetic test instruction", "scope_note": "Declared input only"},
                        "matrix": {"path": "source/matrix.json", "allowed_schema": "example.work-matrix/v1"},
                        "history": {"paths": [], "directories": [], "coverage_note": "Earlier versions unavailable"}, "documents": [], "output": ".atlas/output"}
        self.registry = self.base / "PROJECTS.json"
        self.model = {"schema": "atlas.workspace/v1", "projects": [{"key": "example", "root": str(self.root), "binding": ".atlas/UPSTREAM.json"}]}
        self.save(self.root / "source/matrix.json", self.matrix)
        self.save(self.root / ".atlas/UPSTREAM.json", self.binding)
        self.save(self.registry, self.model)

    @staticmethod
    def save(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def cli(self, *args, code=0):
        result = subprocess.run([sys.executable, "-B", str(COMMAND), "--registry", str(self.registry), *args],
                                cwd=self.base, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout) if code != 2 else result

    def tree(self):
        return {str(p.relative_to(self.root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                for p in self.root.rglob("*") if p.is_file()}

    def append(self):
        self.matrix["revision"] = 2
        self.matrix["updated_at"] = T2
        self.matrix["events"].append({"id": "E-A-2", "step_id": "A", "at": T2, "status": "done", "executor_ids": ["Existing-writer"], "note": "Scoped source claim"})
        self.save(self.root / "source/matrix.json", self.matrix)

    def test_list_is_exact_declared_inventory_and_does_not_bootstrap(self):
        before = self.tree()
        result = self.cli("list")
        self.assertEqual(result, {"schema": "atlas.workspace.list/v1", "projects": self.model["projects"]})
        self.assertEqual(before, self.tree())

    def test_real_start_finish_and_read_commands_preserve_sources_and_noop(self):
        source = (self.root / "source/matrix.json").read_bytes()
        started = self.cli("start", "example", "--work", "A")
        self.assertEqual(started["status"], "CONTEXT_LOADED")
        self.assertEqual(started["refresh"]["status"], "IMPORTED_PARTIAL")
        self.assertEqual(started["packet"]["work"]["id"], "A")
        self.assertEqual(started["packet"]["work"]["writer"], "Existing-writer")
        self.assertEqual(started["packet"]["work"]["acceptance"], [])
        self.assertEqual(started["packet"]["work"]["evidence"], [])
        pointer = json.loads((self.root / ".atlas/output/CURRENT.json").read_text())
        expected = self.root / ".atlas/output/releases" / pointer["release"] / "index.html"
        self.assertEqual(started["view_path"], str(expected))
        self.assertEqual(started["current"], pointer)
        self.assertTrue(expected.is_file())
        before = self.tree()
        self.assertEqual(self.cli("finish", "example")["status"], "NO_CHANGE")
        self.assertEqual(self.cli("packet", "example", "--work", "A")["packet"]["work"]["id"], "A")
        self.assertEqual(self.cli("audit", "example")["status"], "PROJECT_CONTROL_REVIEW")
        self.assertEqual(self.cli("reconcile", "example")["status"], "READ_ONLY")
        page = self.cli("history", "example", "--limit", "1")
        self.assertEqual(len(page["revisions"]), 1)
        self.assertEqual(page["view_path"], str(expected))
        self.assertEqual(before, self.tree())
        self.assertEqual(source, (self.root / "source/matrix.json").read_bytes())

    def test_material_change_new_view_and_actual_history_cursor(self):
        first = self.cli("refresh", "example")
        self.append()
        second = self.cli("finish", "example")
        self.assertEqual(second["status"], "IMPORTED_PARTIAL")
        self.assertIn("A", second["changed_work_ids"])
        self.assertNotEqual(first["view_path"], second["view_path"])
        self.assertTrue(Path(first["view_path"]).is_file())
        first_page = self.cli("history", "example", "--limit", "1")
        self.assertEqual(len(first_page["revisions"]), 1)
        self.assertIsNotNone(first_page["next_cursor"])
        next_page = self.cli("history", "example", "--limit", "1", "--cursor", first_page["next_cursor"])
        self.assertEqual(len(next_page["revisions"]), 1)
        self.assertNotEqual(first_page["revisions"][0]["id"], next_page["revisions"][0]["id"])
        self.assertIsNone(next_page["next_cursor"])
        self.assertEqual(next_page["view_path"], second["view_path"])

    def test_audit_and_packet_do_not_implicitly_refresh_owning_inputs(self):
        self.cli("refresh", "example")
        self.append()
        before = self.tree()
        audit = self.cli("audit", "example")
        packet = self.cli("packet", "example", "--work", "A")
        self.assertEqual(audit["product_execution"], "NOT_RUN")
        self.assertEqual(packet["packet"]["work"]["state"], "DOING")
        self.assertEqual(before, self.tree())

    def test_unknown_project_and_shell_text_are_not_executed(self):
        before = self.tree()
        marker = self.base / "MUST_NOT_EXIST"
        result = self.cli("refresh", "example; touch " + str(marker), code=1)
        self.assertEqual(result["code"], "WORKSPACE_UNKNOWN_PROJECT")
        self.assertFalse(marker.exists())
        self.assertEqual(before, self.tree())

    def test_fixed_argv_rejects_unsupported_actions_and_options(self):
        before = self.tree()
        for args in (("deploy", "example"), ("start", "example"), ("packet", "example"),
                     ("refresh", "example", "--shell", "echo BAD"), ("audit", "example", "--work", "A"),
                     ("history", "example", "--lim", "1")):
            with self.subTest(args=args):
                self.cli(*args, code=2)
        self.assertEqual(before, self.tree())

    def test_history_bounds_and_cursor_are_enforced_by_core(self):
        self.cli("refresh", "example")
        before = self.tree()
        for limit in ("0", "101"):
            self.assertEqual(self.cli("history", "example", "--limit", limit, code=1)["code"], "HISTORY_PAGE_LIMIT")
        self.assertEqual(self.cli("history", "example", "--cursor", "invalid", code=1)["status"], "REFUSED")
        self.assertEqual(before, self.tree())

    def test_registry_schema_duplicate_keys_roots_and_fields_are_refused(self):
        for mutate in (
            lambda m: m.update(schema="wrong"),
            lambda m: m.update(discover=True),
            lambda m: m["projects"].append(copy.deepcopy(m["projects"][0])),
            lambda m: m["projects"].append({**m["projects"][0], "key": "other"}),
            lambda m: m["projects"][0].update(command="external-action"),
        ):
            model = copy.deepcopy(self.model)
            mutate(model)
            self.save(self.registry, model)
            with self.subTest(model=model):
                self.assertEqual(self.cli("list", code=1)["status"], "REFUSED")
        self.registry.write_text('{"schema":"atlas.workspace/v1","schema":"atlas.workspace/v1","projects":[]}', encoding="utf-8")
        self.assertEqual(self.cli("list", code=1)["status"], "REFUSED")

    def test_only_existing_absolute_plain_roots_are_accepted(self):
        file = self.base / "plain-file"
        file.write_text("data")
        link = self.base / "linked-root"
        link.symlink_to(self.root, target_is_directory=True)
        parent_link = self.base / "linked-parent"
        parent_link.symlink_to(self.base, target_is_directory=True)
        for root in ("relative-root", str(self.base / "absent"), str(file), str(link),
                     str(parent_link / self.root.name), str(self.root / ".." / self.root.name)):
            model = copy.deepcopy(self.model)
            model["projects"][0]["root"] = root
            self.save(self.registry, model)
            with self.subTest(root=root):
                self.assertEqual(self.cli("list", code=1)["status"], "REFUSED")

    def test_binding_path_escape_and_symlink_are_refused_without_mutation(self):
        for binding in ("../outside.json", "/absolute.json", "source/matrix.json"):
            model = copy.deepcopy(self.model)
            model["projects"][0]["binding"] = binding
            self.save(self.registry, model)
            self.assertEqual(self.cli("refresh", "example", code=1)["status"], "REFUSED")
        self.save(self.registry, self.model)
        original = self.root / ".atlas/UPSTREAM.json"
        original.rename(self.base / "binding.json")
        original.symlink_to(self.base / "binding.json")
        self.assertEqual(self.cli("refresh", "example", code=1)["status"], "REFUSED")
        self.assertFalse((self.root / ".atlas/IMPORT_STATE.json").exists())

    def test_corrupt_current_or_release_never_returns_successful_view(self):
        refreshed = self.cli("refresh", "example")
        current = self.root / ".atlas/output/CURRENT.json"
        pointer = current.read_bytes()
        current.write_text("{}")
        before = self.tree()
        self.assertEqual(self.cli("audit", "example", code=1)["status"], "REFUSED")
        self.assertEqual(before, self.tree())
        current.write_bytes(pointer)
        Path(refreshed["view_path"]).write_text("CORRUPT INDEX")
        before = self.tree()
        self.assertEqual(self.cli("packet", "example", "--work", "A", code=1)["status"], "REFUSED")
        self.assertEqual(before, self.tree())

    def test_no_release_history_and_reconcile_are_read_only(self):
        before = self.tree()
        result = self.cli("history", "example")
        self.assertEqual(result["status"], "NO_RELEASES")
        self.assertIsNone(result["view_path"])
        self.assertIsNone(result["current"])
        self.assertEqual(self.cli("reconcile", "example")["status"], "READ_ONLY")
        self.assertEqual(before, self.tree())


if __name__ == "__main__":
    unittest.main()
