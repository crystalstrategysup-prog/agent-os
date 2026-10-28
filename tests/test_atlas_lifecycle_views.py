"""Current-entry and matrix freshness regressions; all inputs are synthetic."""
import copy
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

import test_atlas_readable as baseline


def facade_module():
    source = Path(__file__).resolve().parents[1] / "src/agent_os/atlas_module.py"
    spec = importlib.util.spec_from_file_location("_synthetic_lifecycle_facade", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LifecycleViewTests(unittest.TestCase):
    def setUp(self):
        self.fixture_case = baseline.AtlasReadableTests()
        self.fixture_case.setUp()
        self.addCleanup(self.fixture_case.doCleanups)
        self.root = self.fixture_case.root
        self.engine = self.fixture_case.engine

    def prepare(self, im, pointer=""):
        matrix = self.fixture_case.fixture(im, pointer=pointer, with_history=True)
        im.refresh(self.root, at=baseline.T2)
        binding = im.binding_model(im.read(self.root, ".atlas/UPSTREAM.json"))
        output = self.root / binding["output"]
        return matrix, binding, output

    def advance(self, im, matrix, pointer=""):
        newer = copy.deepcopy(matrix)
        newer["revision"] += 1
        newer["updated_at"] = baseline.T3
        newer["events"].append({"id": "EV-2", "step_id": "ITEM", "at": baseline.T3,
                                "status": "doing", "executor_ids": ["Worker"],
                                "note": "A new bounded follow-up has started; no new acceptance."})
        value = newer if not pointer else {"snapshot": {"matrix": newer}, "unrelated": "OUTSIDE_SELECTION"}
        (self.root / "source/matrix.json").write_bytes(im.nav.canonical(value))
        return newer

    def test_current_entry_advances_but_past_release_does_not(self):
        with baseline.isolated_engine(self.engine) as im:
            matrix, binding, output = self.prepare(im)
            workspace = importlib.import_module("workspace")
            first = workspace.project_views(self.root, binding)
            retained = Path(first["artifacts"]["html"]["path"])
            old_html = retained.read_bytes()
            self.assertEqual(first["current_view"]["status"], "CURRENT")
            self.assertEqual(Path(first["view_path"]), output / "index.html")
            self.assertEqual((output / "index.html").read_bytes(), old_html)
            self.advance(im, matrix)
            im.refresh(self.root, at=baseline.T4)
            before_read = baseline.file_hashes(self.root)
            second = workspace.project_views(self.root, binding)
            self.assertEqual(baseline.file_hashes(self.root), before_read)
            self.assertNotEqual(second["release"], first["release"])
            self.assertEqual(second["view_path"], first["view_path"])
            self.assertEqual(second["freshness"]["matrix"]["status"], "MATCHED")
            self.assertEqual(second["freshness"]["matrix"]["documents"], "NOT_COMPARED")
            self.assertEqual(second["source_revision"], 2)
            self.assertEqual(retained.read_bytes(), old_html)
            self.assertNotEqual((output / "index.html").read_bytes(), old_html)
            self.assertEqual((output / "index.html").read_bytes(),
                             Path(second["artifacts"]["html"]["path"]).read_bytes())
            self.assertEqual(second["sections"]["roadmap"]["url"],
                             (output / "index.html").as_uri() + "#roadmap")
            references = facade_module()._references(second)
            self.assertEqual(len(references), 2)
            self.assertEqual(references[1]["path"], second["artifacts"]["html"]["path"])

    def test_unsaved_projection_is_reported_without_read_side_effect(self):
        with baseline.isolated_engine(self.engine) as im:
            matrix, binding, output = self.prepare(im)
            workspace = importlib.import_module("workspace")
            self.advance(im, matrix)
            before = baseline.file_hashes(self.root)
            result = workspace.project_views(self.root, binding)
            self.assertEqual(before, baseline.file_hashes(self.root))
            self.assertEqual(result["source_revision"], 1)
            self.assertEqual(result["freshness"]["matrix"]["source_revision"], 2)
            self.assertEqual(result["freshness"]["matrix"]["status"], "CHANGED")
            self.assertIn("finish", result["next_action"])

    def test_embedded_matrix_ignores_unrelated_envelope_changes(self):
        with baseline.isolated_engine(self.engine) as im:
            matrix, binding, _ = self.prepare(im, "/snapshot/matrix")
            workspace = importlib.import_module("workspace")
            source = self.root / "source/matrix.json"
            envelope = im.nav.parse(source.read_bytes())
            envelope["unrelated"] = {"preserve": "not part of the selected matrix"}
            source.write_bytes(im.nav.canonical(envelope))
            result = workspace.project_views(self.root, binding)
            self.assertEqual(result["freshness"]["matrix"]["status"], "MATCHED")
            self.assertEqual(result["source_revision"], matrix["revision"])

    def test_missing_source_keeps_verified_view_with_unknown_freshness(self):
        with baseline.isolated_engine(self.engine) as im:
            _, binding, _ = self.prepare(im)
            workspace = importlib.import_module("workspace")
            (self.root / "source/matrix.json").unlink()
            before = baseline.file_hashes(self.root)
            result = workspace.project_views(self.root, binding)
            self.assertEqual(result["status"], "ARTIFACTS_READY")
            self.assertEqual(result["freshness"]["matrix"]["status"], "UNKNOWN")
            self.assertEqual(before, baseline.file_hashes(self.root))

    def test_work_parameters_prepare_once_and_preserve_original_pins_on_retry(self):
        with baseline.isolated_engine(self.engine) as im:
            matrix, binding, _ = self.prepare(im, "/snapshot/matrix")
            workspace = importlib.import_module("workspace")
            profile = {"schema": "atlas.matrix-writer/v1", "binding": ".atlas/UPSTREAM.json",
                       "project_id": binding["project"]["id"], "writer": binding["project"]["writer"],
                       "matrix": binding["matrix"], "lock_path": ".atlas/CHECKPOINT.lock",
                       "history": {"mode": "retained-operation-snapshots", "previous_payload_hash": "selected-canonical"},
                       "document_paths": ["source/note.md"]}
            (self.root / ".atlas/WRITER.json").write_bytes(im.nav.canonical(profile))
            (self.root / "source/note.md").write_text("Before\n")
            (self.root / "source/prepared.md").write_text("Prepared actual documentation delta\n")
            (self.root / "source/receipt.json").write_text('{"status":"DISPATCHED"}\n')
            args = workspace.parser().parse_args([
                "--registry", str(self.root / "registry.json"), "work", "synthetic",
                "--operation", "dispatch-item-1", "--work", "ITEM", "--phase", "dispatch",
                "--executor", "Worker", "--note", "The assigned worker received the scoped task.",
                "--next-action", "Main writer integrates prepared documentation while awaiting the result.",
                "--evidence", "source/receipt.json", "--document-edit", "source/note.md", "source/prepared.md"])
            source_before = (self.root / "source/matrix.json").read_bytes()
            record_path = workspace.prepare_work_record(self.root, binding, ".atlas/UPSTREAM.json", args)
            record_bytes = (self.root / record_path).read_bytes()
            record = im.nav.parse(record_bytes)
            self.assertEqual(record["status"], "doing")
            self.assertEqual(record["expected_source"], {"sha256": im.nav.digest(source_before),
                                                       "bytes": len(source_before), "revision": matrix["revision"]})
            self.assertNotIn("activity", record)
            self.assertEqual((self.root / "source/note.md").read_text(), "Before\n")
            self.assertEqual((self.root / "source/matrix.json").read_bytes(), source_before)
            # A retry of the same operation must not silently attach a newer
            # matrix or overwrite the prepared original timestamp/doc preimage.
            self.advance(im, matrix, "/snapshot/matrix")
            (self.root / "source/prepared.md").write_text("A later unrelated draft\n")
            before_retry = baseline.file_hashes(self.root)
            self.assertEqual(workspace.prepare_work_record(self.root, binding, ".atlas/UPSTREAM.json", args), record_path)
            self.assertEqual(baseline.file_hashes(self.root), before_retry)
            self.assertEqual((self.root / record_path).read_bytes(), record_bytes)
            args.note = "A different work fact needs its own operation identity."
            with self.assertRaisesRegex(im.nav.Invalid, "CHECKPOINT_OPERATION_PARAMETERS_CHANGED"):
                workspace.prepare_work_record(self.root, binding, ".atlas/UPSTREAM.json", args)
            self.assertEqual(baseline.file_hashes(self.root), before_retry)

    def test_work_parameters_require_explicit_matching_writer_before_preparing(self):
        with baseline.isolated_engine(self.engine) as im:
            _, binding, _ = self.prepare(im)
            workspace = importlib.import_module("workspace")
            args = workspace.parser().parse_args([
                "--registry", str(self.root / "registry.json"), "work", "synthetic",
                "--operation", "start-item-1", "--work", "ITEM", "--phase", "start",
                "--executor", "Worker", "--note", "Implementation starts.", "--next-action", "Deliver the scoped change."])
            before = baseline.file_hashes(self.root)
            with self.assertRaises(im.nav.Invalid):
                workspace.prepare_work_record(self.root, binding, ".atlas/UPSTREAM.json", args)
            self.assertEqual(baseline.file_hashes(self.root), before)
            profile = {"schema": "atlas.matrix-writer/v1", "binding": ".atlas/UPSTREAM.json",
                       "project_id": "ANOTHER-PROJECT", "writer": binding["project"]["writer"],
                       "matrix": binding["matrix"]}
            (self.root / ".atlas/WRITER.json").write_bytes(im.nav.canonical(profile))
            before = baseline.file_hashes(self.root)
            with self.assertRaisesRegex(im.nav.Invalid, "CHECKPOINT_WRITER_BINDING_CHANGED"):
                workspace.prepare_work_record(self.root, binding, ".atlas/UPSTREAM.json", args)
            self.assertEqual(baseline.file_hashes(self.root), before)

    def test_large_checkpoint_preserves_exact_recovery_identity_and_all_conflicts(self):
        facade = facade_module()
        value = {"status": "CHECKPOINT_PENDING", "operation_id": "dispatch-item-1", "phase": "dispatch",
                 "work_id": "ITEM", "executor_id": "Worker", "event_id": "CP-EXACT",
                 "next_action": "Integrate the prepared result.", "recorded_status": "CHECKPOINT_PUBLISHED",
                 "pending": True, "source_effect": "PARTIAL", "record_sha256": "a" * 64,
                 "error": "CHECKPOINT_SOURCE_CONFLICT", "prepared_record": ".atlas/checkpoint-records/dispatch-item-1.json",
                 "observed": [{"path": "docs/a.md", "state": "AFTER"}, {"path": "source/matrix.json", "state": "CONFLICT"}],
                 "projection": {"status": "NOT_PUBLISHED"}, "verbose_diagnostics": "x" * 40000}
        rendered = facade._render(json.dumps(value), 0, ["work", "synthetic"])
        result = json.loads(rendered)
        self.assertLess(len(rendered.encode()), 32768)
        self.assertEqual(result["control"]["operation_id"], value["operation_id"])
        self.assertEqual(result["control"]["record_sha256"], value["record_sha256"])
        self.assertEqual(result["control"]["source_effect"], "PARTIAL")
        for key in ("work_id", "executor_id", "event_id", "next_action", "recorded_status"):
            self.assertEqual(result["control"][key], value[key])
        self.assertEqual(result["control"]["observed"]["state_counts"], {"AFTER": 1, "CONFLICT": 1})
        self.assertTrue(result["control"]["observed"]["all_states_counted"])
        self.assertIn("checkpoint", facade._MODULE_NAMES)

    def test_typed_work_call_records_and_publishes_once_end_to_end(self):
        with baseline.isolated_engine(self.engine) as im:
            matrix = self.fixture_case.fixture(im)
            matrix["actors"].append({"id": "Existing-writer"})
            matrix["events"][0].update(status="planned", accepted=False)
            (self.root / "source/matrix.json").write_bytes(im.nav.canonical(matrix))
            binding = im.binding_model(im.read(self.root, ".atlas/UPSTREAM.json"))
            profile = {"schema": "atlas.matrix-writer/v1", "binding": ".atlas/UPSTREAM.json",
                       "project_id": binding["project"]["id"], "writer": binding["project"]["writer"],
                       "matrix": {**binding["matrix"], "pointer": ""}, "lock_path": ".atlas/CHECKPOINT.lock",
                       "history": {"mode": "retained-operation-snapshots", "previous_payload_hash": "source-bytes"},
                       "document_paths": []}
            (self.root / ".atlas/WRITER.json").write_bytes(im.nav.canonical(profile))
            registry = self.root / "registry.json"
            registry.write_bytes(im.nav.canonical({"schema": "atlas.workspace/v1", "projects": [
                {"key": "synthetic", "root": str(self.root), "binding": ".atlas/UPSTREAM.json"}]}))
            im.refresh(self.root, at=baseline.T2)
            old_current = im.atlas.current_output(self.root / ".atlas/output")[0]
            workspace = importlib.import_module("workspace")
            args = workspace.parser().parse_args([
                "--registry", str(registry), "work", "synthetic", "--operation", "assigned-item-1",
                "--work", "ITEM", "--phase", "dispatch", "--executor", "Worker",
                "--note", "The scoped assignment was handed to Worker.",
                "--next-action", "Integrate available documentation while awaiting the result."])
            result = workspace.run(args)
            self.assertEqual(result["status"], "CHECKPOINT_PUBLISHED", result)
            self.assertEqual(result["current_view"]["status"], "CURRENT")
            self.assertNotEqual(result["current"], old_current)
            current = im.atlas.current_output(self.root / ".atlas/output")[1]
            work = next(row for row in current["atlas"]["works"] if row["id"] == "ITEM")
            self.assertEqual(work["state"], "DOING")
            self.assertIsNone(work["activity"])
            self.assertEqual(work["acceptance"], [])
            before_retry = baseline.file_hashes(self.root)
            repeated = workspace.run(args)
            self.assertTrue(repeated["replayed"])
            self.assertEqual(repeated["current"], result["current"])
            self.assertEqual(baseline.file_hashes(self.root), before_retry)

    def test_missing_alias_reads_immutable_and_explicit_repair_is_idempotent(self):
        with baseline.isolated_engine(self.engine) as im:
            _, binding, output = self.prepare(im)
            workspace = importlib.import_module("workspace")
            alias = output / "index.html"
            alias.unlink()
            before = baseline.file_hashes(self.root)
            result = workspace.project_views(self.root, binding)
            self.assertEqual(result["current_view"]["status"], "MISSING")
            self.assertEqual(result["view_path"], result["artifacts"]["html"]["path"])
            self.assertEqual(before, baseline.file_hashes(self.root))
            pointer = result["current"]
            repaired = workspace.publish_view_receipt(self.root, binding)
            self.assertEqual(repaired["current_view"]["status"], "CURRENT")
            self.assertEqual(im.atlas.current_output(output)[0], pointer)
            stat = alias.stat()
            fixed = baseline.file_hashes(self.root)
            again = workspace.publish_view_receipt(self.root, binding)
            self.assertEqual(again["current_view"]["outcome"], "NO_CHANGE")
            self.assertEqual(baseline.file_hashes(self.root), fixed)
            self.assertEqual((alias.stat().st_ino, alias.stat().st_mtime_ns), (stat.st_ino, stat.st_mtime_ns))

    def test_only_verified_old_release_can_be_replaced(self):
        with baseline.isolated_engine(self.engine) as im:
            matrix, binding, output = self.prepare(im)
            workspace = importlib.import_module("workspace")
            old_html = (output / "index.html").read_bytes()
            self.advance(im, matrix)
            im.refresh(self.root, at=baseline.T4)
            pointer, _ = im.atlas.current_output(output)
            current_html = (output / "index.html").read_bytes()
            (output / "index.html").write_bytes(old_html)
            stale = im.nav.current_view_status(output, expected_release=pointer["release"],
                                               expected_manifest_sha256=pointer["manifest_sha256"])
            self.assertEqual(stale["status"], "STALE")
            workspace.publish_view_receipt(self.root, binding)
            self.assertEqual((output / "index.html").read_bytes(), current_html)
            (output / "index.html").write_bytes(b"Unrelated owner file. Keep it intact.")
            before = baseline.file_hashes(output)
            with self.assertRaises(im.nav.Invalid):
                workspace.publish_view_receipt(self.root, binding)
            self.assertEqual(before, baseline.file_hashes(output))
            self.assertEqual(im.atlas.current_output(output)[0], pointer)

    def test_current_pin_race_is_explicit(self):
        with baseline.isolated_engine(self.engine) as im:
            matrix, _, output = self.prepare(im)
            first, _ = im.atlas.current_output(output)
            self.advance(im, matrix)
            im.refresh(self.root, at=baseline.T4)
            now, _ = im.atlas.current_output(output)
            before = baseline.file_hashes(output)
            result = im.nav.current_view_status(output, expected_release=first["release"],
                                                expected_manifest_sha256=first["manifest_sha256"])
            self.assertEqual(result["status"], "CURRENT_CHANGED")
            self.assertEqual(result["release"], now["release"])
            self.assertEqual(result["expected_release"], first["release"])
            with self.assertRaisesRegex(im.nav.Invalid, "CURRENT_CHANGED"):
                im.nav.publish_current_view(output, expected_release=first["release"],
                                            expected_manifest_sha256=first["manifest_sha256"])
            self.assertEqual(before, baseline.file_hashes(output))


if __name__ == "__main__":
    unittest.main(verbosity=2)
