"""Synthetic offline roots: read safety, truthful gaps and no workflow effects."""
import contextlib
import errno
import hashlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_os import project_diagnostics as diagnostic


def snapshot(root):
    result = {}
    for path in root.rglob("*"):
        info = path.lstat()
        result[path.relative_to(root).as_posix()] = (
            info.st_mode, info.st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None,
        )
    return result


@unittest.skipUnless(hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd,
                     "Descriptor-relative inspection requires a qualified platform")
class ProjectDiagnosticTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="agentos-diagnostic-synthetic-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        self.root = self.home / "project"
        self.root.mkdir()
        self.project = {"schema": "agentos.project/v1", "id": "project-synthetic", "documents": {}}
        self.save_project()

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        return path

    def save_project(self):
        self.write(".agentos/project.json", json.dumps(self.project))

    def document(self, name="architecture", path="docs/ARCHITECTURE.md", body=b"# Private synthetic document\n", **extra):
        self.write(path, body)
        self.project["documents"][name] = {"path": path, "sha256": hashlib.sha256(body).hexdigest(),
                                           "status": "current", **extra}
        self.save_project()
        return self.root / path

    def task(self, status="READY", **extra):
        self.project["active_task"] = "task-synthetic"
        self.save_project()
        value = {"schema": "agentos.project-task/v1", "id": "task-synthetic", "project_id": self.project["id"],
                 "status": status, "selection": {"required": list(self.project["documents"])},
                 "answers": {"authority": "PRIVATE_BODY_MUST_NEVER_APPEAR"}, **extra}
        self.write(".agentos/tasks/task-synthetic/task.json", json.dumps(value))

    def codes(self, value):
        return value["finding_counts"]

    def inspect_unchanged(self):
        before = snapshot(self.root)
        value = diagnostic.diagnose(self.root)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(value["effect"], "READ_ONLY")
        return value

    def test_verified_hashes_without_bodies_or_configuration_effects(self):
        secret = b"PRIVATE_BODY_MUST_NEVER_APPEAR\n"
        self.document(body=secret)
        self.task()
        self.write("README.md", "[Architecture](docs/ARCHITECTURE.md)\n")
        value = self.inspect_unchanged()
        self.assertEqual(value["schema"], "agentos.project-diagnostics/v1")
        self.assertEqual(value["status"], "OBSERVED")
        self.assertEqual(value["documents"]["verified"], 1)
        self.assertNotIn(secret.decode().strip(), json.dumps(value))
        self.assertEqual(value["task"]["recorded_status"], "READY")
        self.assertIs(value["task"]["recorded_task_terminal"], False)
        self.assertEqual(value["task"]["writer_activity"], "UNKNOWN")
        self.assertEqual(value["coverage"]["live_activity"], "NOT_CHECKED")
        self.assertFalse((self.home / ".agentos").exists())

    def test_missing_stale_and_unregistered_documents_remain_distinct(self):
        changed = self.document()
        self.document("dossier", "docs/DOSSIER.md")
        self.task(selection={"required": ["architecture", "dossier", "roadmap"]})
        changed.write_text("changed bytes")
        (self.root / "docs/DOSSIER.md").unlink()
        value = self.inspect_unchanged()
        self.assertTrue({"DOCUMENT_HASH_MISMATCH", "DOCUMENT_MISSING", "DOCUMENT_UNREGISTERED"} <= self.codes(value).keys())
        self.assertEqual(value["documents"]["verified"], 0)
        self.assertEqual(value["status"], "FINDINGS")

    def test_review_state_does_not_become_current_from_hash_match(self):
        self.document(status="draft")
        value = self.inspect_unchanged()
        self.assertIn("DOCUMENT_REVIEW_STALE", self.codes(value))
        self.assertEqual(value["documents"]["records"][0]["state"], "STALE")

    def test_terminal_pointer_is_history_not_proof_of_a_live_or_dead_process(self):
        for status in ("CLOSED", "CHECKPOINT"):
            with self.subTest(status=status):
                self.task(status)
                value = self.inspect_unchanged()
                self.assertIs(value["task"]["recorded_task_terminal"], True)
                self.assertEqual(value["task"]["state"], "RECORDED_TERMINAL")
                self.assertEqual(value["task"]["live_activity"], "NOT_CHECKED")
                self.assertEqual(value["task"]["writer_activity"], "UNKNOWN")
                self.assertIn("ACTIVE_POINTER_TERMINAL", self.codes(value))

    def test_task_binding_mismatch_and_missing_are_unknown(self):
        self.task(project_id="different-project")
        value = self.inspect_unchanged()
        self.assertIn("TASK_BINDING_INVALID", self.codes(value))
        self.assertIsNone(value["task"]["recorded_task_terminal"])
        (self.root / ".agentos/tasks/task-synthetic/task.json").unlink()
        value = self.inspect_unchanged()
        self.assertIn("TASK_METADATA_MISSING", self.codes(value))
        self.assertEqual(value["task"]["writer_activity"], "UNKNOWN")

    def test_pending_journal_is_a_hold_without_reading_or_repairing_its_body(self):
        self.write(".agentos/scoped-transaction.json", "NOT_JSON_PRIVATE_PREIMAGES")
        (self.root / ".agentos/write.lock").mkdir()
        value = self.inspect_unchanged()
        self.assertEqual(value["transactions"]["holds"], 2)
        self.assertIn("PENDING_TRANSACTION", self.codes(value))
        self.assertIn("LOCK_PRESENT", self.codes(value))
        self.assertNotIn("NOT_JSON_PRIVATE_PREIMAGES", json.dumps(value))

    def test_permission_failure_is_not_absence_and_error_text_is_not_echoed(self):
        self.document(path="locked.md")
        original = os.open
        def denied(name, *args, **kwargs):
            if name == "locked.md":
                raise PermissionError(errno.EACCES, "PRIVATE_EXCEPTION_DETAIL")
            return original(name, *args, **kwargs)
        with patch.object(os, "open", denied), patch.object(os, "supports_dir_fd", os.supports_dir_fd | {denied}):
            value = self.inspect_unchanged()
        self.assertIn("DOCUMENT_UNREADABLE", self.codes(value))
        self.assertNotIn("DOCUMENT_MISSING", self.codes(value))
        self.assertNotIn("PRIVATE_EXCEPTION_DETAIL", json.dumps(value))
        self.assertFalse(value["coverage"]["complete"])

    def test_unreadable_control_directory_does_not_hide_pending_state(self):
        original = os.open
        def denied(name, *args, **kwargs):
            if name == ".agentos":
                raise PermissionError(errno.EACCES, "denied")
            return original(name, *args, **kwargs)
        with patch.object(os, "open", denied), patch.object(os, "supports_dir_fd", os.supports_dir_fd | {denied}):
            value = diagnostic.diagnose(self.root)
        self.assertIn("TRANSACTION_MARKER_UNREADABLE", self.codes(value))
        self.assertEqual(value["status"], "INCOMPLETE")
        self.assertNotEqual(value["project"]["state"], "MISSING")

    def test_symlink_file_parent_and_root_alias_are_refused(self):
        outside = self.home / "outside.md"
        outside.write_text("PRIVATE_OUTSIDE_BODY")
        target = self.document()
        target.unlink()
        target.symlink_to(outside)
        value = diagnostic.diagnose(self.root)
        self.assertIn("DOCUMENT_UNSAFE", self.codes(value))
        target.unlink()
        (self.root / "docs").rmdir()
        (self.root / "docs").symlink_to(self.home, target_is_directory=True)
        value = diagnostic.diagnose(self.root)
        self.assertIn("DOCUMENT_UNSAFE", self.codes(value))
        alias = self.home / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        value = diagnostic.diagnose(alias)
        self.assertIn("ROOT_UNSAFE", self.codes(value))
        self.assertNotIn("PRIVATE_OUTSIDE_BODY", json.dumps(value))

    def test_control_alias_hardlink_and_fifo_are_not_regular_references(self):
        target = self.document()
        os.link(target, self.home / "hardlink")
        value = diagnostic.diagnose(self.root)
        self.assertIn("DOCUMENT_UNSAFE", self.codes(value))
        (self.home / "hardlink").unlink()
        target.unlink()
        os.mkfifo(target)
        value = diagnostic.diagnose(self.root)
        self.assertIn("DOCUMENT_UNSAFE", self.codes(value))
        target.unlink()
        (self.root / ".atlas").symlink_to(self.home, target_is_directory=True)
        value = diagnostic.diagnose(self.root)
        self.assertEqual(value["atlas"]["local_binding"], "UNKNOWN")
        self.assertIn("ATLAS_METADATA_UNSAFE", self.codes(value))

    def test_invalid_ids_and_unsafe_paths_are_not_reflected(self):
        marker = "PRIVATE_INVALID_VALUE\n"
        self.project["active_task"] = marker + "../../outside"
        self.project["documents"][marker] = {"path": "../" + marker, "sha256": "a" * 64, "status": "current"}
        self.save_project()
        value = diagnostic.diagnose(self.root)
        self.assertIn("ACTIVE_TASK_POINTER_INVALID", self.codes(value))
        self.assertIn("REFERENCE_UNSAFE", self.codes(value))
        self.assertNotIn("PRIVATE_INVALID_VALUE", json.dumps(value))

    def test_corrupt_duplicate_nonobject_and_oversized_metadata(self):
        for raw in (b"{broken", b"[]", b'{"schema":"a","schema":"b"}', b"x" * (diagnostic.MAX_JSON + 1)):
            with self.subTest(size=len(raw)):
                self.write(".agentos/project.json", raw)
                value = self.inspect_unchanged()
                self.assertEqual(value["status"], "INCOMPLETE")
                self.assertTrue({"PROJECT_METADATA_INVALID", "PROJECT_METADATA_TOO_LARGE"} & self.codes(value).keys())

    def test_mismatched_schema_and_invalid_pin_fail_closed(self):
        self.project["schema"] = "other/v1"
        self.save_project()
        self.assertIn("PROJECT_METADATA_INVALID", self.codes(self.inspect_unchanged()))
        self.project["schema"] = "agentos.project/v1"
        self.document(sha256="invalid-pin")
        value = self.inspect_unchanged()
        self.assertIn("REFERENCE_PIN_INVALID", self.codes(value))

    def test_large_document_and_total_budget_are_explicitly_incomplete(self):
        self.document(body=b"x" * (diagnostic.MAX_DOCUMENT + 1))
        value = self.inspect_unchanged()
        self.assertIn("DOCUMENT_TOO_LARGE", self.codes(value))
        self.document(body=b"x" * 1024)
        project_size = (self.root / ".agentos/project.json").stat().st_size
        with patch.object(diagnostic, "MAX_TOTAL_BYTES", project_size + 1023):
            value = self.inspect_unchanged()
        self.assertIn("DOCUMENT_READ_LIMIT", self.codes(value))
        self.assertEqual(value["status"], "INCOMPLETE")

    def test_changed_file_is_not_reported_verified(self):
        target = self.document()
        target_inode = target.stat().st_ino
        original = os.read
        mutated = False
        def changing(fd, size):
            nonlocal mutated
            data = original(fd, size)
            if not mutated and os.fstat(fd).st_ino == target_inode:
                mutated = True
                target.write_bytes(target.read_bytes() + b"changed")
            return data
        with patch.object(os, "read", changing):
            value = diagnostic.diagnose(self.root)
        self.assertIn("DOCUMENT_CHANGED", self.codes(value))
        self.assertEqual(value["documents"]["verified"], 0)

    def test_absence_at_known_atlas_paths_does_not_prove_global_absence(self):
        value = self.inspect_unchanged()
        self.assertEqual(value["atlas"]["local_binding"], "ABSENT_AT_KNOWN_PATHS")
        self.assertEqual(value["atlas"]["coverage"], "UNKNOWN")
        self.assertEqual(value["atlas"]["registry"], "NOT_CHECKED")
        (self.root / ".atlas").mkdir()
        value = self.inspect_unchanged()
        self.assertEqual(value["atlas"]["local_binding"], "UNKNOWN")

    def test_local_atlas_pins_and_work_references_do_not_claim_graph_coverage(self):
        body = b'{"private_body":"NOT_TO_OUTPUT"}'
        self.write(".atlas/documents/index.json", body)
        self.write(".atlas/work/W1.json", b"UNREAD_WORK_BODY")
        atlas = {"schema": "atlas.project/v1", "id": "synthetic-atlas", "mode": "native",
                 "documents": {"path": ".atlas/documents/index.json", "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)},
                 "work_files": [".atlas/work/W1.json"]}
        self.write(".atlas/project.json", json.dumps(atlas))
        value = self.inspect_unchanged()
        self.assertEqual(value["atlas"]["local_binding"], "PRESENT_AT_KNOWN_PATHS")
        self.assertEqual(value["atlas"]["coverage"], "UNKNOWN")
        self.assertNotIn("NOT_TO_OUTPUT", json.dumps(value))
        self.assertNotIn("UNREAD_WORK_BODY", json.dumps(value))
        self.write(".atlas/documents/index.json", b"changed")
        value = self.inspect_unchanged()
        self.assertEqual(value["atlas"]["local_binding"], "UNKNOWN")

    def test_corrupt_atlas_shapes_do_not_crash_or_become_absent(self):
        for value in ({"schema": "atlas.project/v1", "id": "example", "mode": []},
                      {"schema": "atlas.project/v1", "id": "example", "mode": "native", "work_files": {}},
                      {"schema": "atlas.project/v1"}):
            with self.subTest(value=value):
                self.write(".atlas/project.json", json.dumps(value))
                result = self.inspect_unchanged()
                self.assertEqual(result["atlas"]["local_binding"], "UNKNOWN")
                self.assertIn("ATLAS_METADATA_INVALID", self.codes(result))
        (self.root / ".atlas/project.json").unlink()
        self.write(".atlas/UPSTREAM.json", '{"schema":"atlas.upstream-binding/v1"}')
        result = self.inspect_unchanged()
        self.assertEqual(result["atlas"]["local_binding"], "UNKNOWN")
        self.assertIn("ATLAS_UPSTREAM_INVALID", self.codes(result))

    def test_local_markdown_links_report_exact_missing_docs_without_recursive_reads(self):
        self.write("AGENTS.md", "[Docs](docs/README.md)\n[Engineering](ENGINEERING.md)\n[Remote](https://example.invalid/private.md)\n")
        self.write("README.md", "```md\n[Example](not-a-real-file.md)\n```\n[Safe](./present.md#section)\n[Unsafe](../outside.md)\n")
        self.write("present.md", "PRIVATE_LINK_TARGET_BODY\n[nested](uninspected.md)")
        value = self.inspect_unchanged()
        missing = {r["path"] for r in value["links"]["records"] if r["state"] == "MISSING"}
        self.assertEqual(missing, {"docs/README.md", "ENGINEERING.md"})
        self.assertIn("MARKDOWN_LINK_UNSAFE", self.codes(value))
        self.assertNotIn("uninspected.md", json.dumps(value))
        self.assertNotIn("PRIVATE_LINK_TARGET_BODY", json.dumps(value))

    def test_output_and_reference_caps_never_return_false_completeness(self):
        prefix = "/".join(["x" * 150] * 4)
        self.project["documents"] = {"doc-" + str(i): {"path": prefix + "/" + str(i) + ".md", "sha256": "a" * 64, "status": "current"} for i in range(300)}
        self.save_project()
        value = self.inspect_unchanged()
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        self.assertLessEqual(len(encoded), diagnostic.MAX_STDOUT_BYTES)
        self.assertEqual(value["documents"]["declared"], 300)
        self.assertEqual(value["status"], "INCOMPLETE")
        self.assertIs(value["coverage"]["complete"], False)
        self.assertIs(value["coverage"]["truncated"], True)
        self.assertIn("OUTPUT_LIMIT", self.codes(value))

    def test_unregistered_and_missing_roots_are_readonly_and_different(self):
        (self.root / ".agentos/project.json").unlink()
        (self.root / ".agentos").rmdir()
        value = self.inspect_unchanged()
        self.assertIn("PROJECT_METADATA_MISSING", self.codes(value))
        self.assertFalse((self.root / ".agentos").exists())
        value = diagnostic.diagnose(self.home / "missing")
        self.assertIn("ROOT_MISSING", self.codes(value))
        self.assertFalse(value["coverage"]["complete"])

    def test_unsupported_descriptor_platform_is_explicitly_not_qualified(self):
        with patch.object(os, "supports_dir_fd", set()):
            value = diagnostic.diagnose(self.root)
        self.assertEqual(value["status"], "NOT_QUALIFIED")
        self.assertIn("ROOT_PLATFORM_NOT_QUALIFIED", self.codes(value))

    def test_foundation_dispatch_has_no_home_discovery_or_mutation(self):
        from agent_os import foundation_cli
        sentinel = types.ModuleType("agent_os.config")
        sentinel.AgentOSPaths = types.SimpleNamespace(discover=lambda *a: self.fail("home discovery"))
        before = snapshot(self.home)
        output = io.StringIO()
        with patch.dict(sys.modules, {"agent_os.config": sentinel}), contextlib.redirect_stdout(output):
            code = foundation_cli.dispatch(["--home", str(self.home / "missing-home"), "project", "diagnose", "--root", str(self.root)])
        value = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(value["schema"], diagnostic.SCHEMA)
        self.assertEqual(snapshot(self.home), before)
        self.assertLessEqual(len(output.getvalue().encode()), diagnostic.MAX_STDOUT_BYTES)

    def test_observed_gaps_are_advisory_not_an_intake_or_readiness_gate(self):
        target = self.document()
        target.unlink()
        value, code = diagnostic.command(["--root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertTrue(value["advisory"])
        self.assertEqual(value["status"], "FINDINGS")
        self.assertEqual(value["next_action"]["subject"], "docs/ARCHITECTURE.md")
        self.assertEqual(value["next_action"]["route"], "agentos project document")
        self.assertNotIn("next_actions", value)
        self.write(".agentos/project.json", "invalid")
        value, code = diagnostic.command(["--root", str(self.root)])
        self.assertEqual((code, value["status"]), (0, "INCOMPLETE"))
        self.assertFalse((self.root / ".agentos/write.lock").exists())


if __name__ == "__main__":
    unittest.main()
