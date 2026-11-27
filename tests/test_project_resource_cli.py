"""CLI boundary tests: observation stays private, bounded and effect free."""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_os import cli
from agent_os.config import AgentOSPaths
from agent_os.project_resource_cli import MAX_INPUT_BYTES, read_input
from agent_os.safeio import GateError


class ResourceCliTest(unittest.TestCase):
    def setUp(self):
        self.area = tempfile.TemporaryDirectory(prefix="resource-cli-")
        self.root = Path(self.area.name)
        self.addCleanup(self.area.cleanup)

    def payload(self):
        return {"schema": "agentos.resource-observation-request/v1",
                "project_id": "project-synthetic", "task_id": "task-synthetic",
                "run_id": "run-synthetic", "operation_id": "observe-synthetic",
                "roots": [{"admitted_root_id": "root-synthetic", "path": str(self.root)}],
                "resources": [], "capacity": []}

    def invoke(self, args, stdin=""):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch("sys.stdin", io.StringIO(stdin)):
            code = cli.main(args)
        return code, json.loads(out.getvalue())

    def test_stdin_plan_needs_no_home_network_or_task_and_leaks_no_path(self):
        with patch.object(AgentOSPaths, "discover", side_effect=AssertionError("home")), \
                patch.object(cli, "update_advisory_check", side_effect=AssertionError("network")):
            code, result = self.invoke(["--home", str(self.root / "unused-home"),
                                       "project", "resource", "plan", "--input", "-"],
                                      json.dumps(self.payload()))
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "OBSERVATION_ONLY")
        self.assertEqual(result["effects"], "NONE")
        for field in ("apply_supported", "reservation_supported", "admission_granted",
                      "authority_granted", "task_mutation", "physical_cleanup_supported"):
            self.assertIs(result[field], False)
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_file_plan_preserves_descriptor_and_other_files(self):
        selected = self.root / "private-descriptor.json"
        raw = json.dumps(self.payload()).encode()
        selected.write_bytes(raw)
        sentinel = self.root / "unrelated-secret.txt"
        sentinel.write_text("private-sentinel-value")
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()}
        code, result = self.invoke(["project", "resource", "plan", "--input", str(selected)])
        self.assertEqual(code, 0)
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns)
                                  for p in self.root.iterdir()})
        rendered = json.dumps(result)
        self.assertNotIn(sentinel.name, rendered)
        self.assertNotIn("private-sentinel-value", rendered)

    def test_bad_descriptor_never_echoes_supplied_filename(self):
        path = self.root / "private-sensitive-name.json"
        path.write_text('{"path":"secret-value", bad}')
        code, result = self.invoke(["project", "resource", "plan", "--input", str(path)])
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertNotIn("private-sensitive", json.dumps(result))
        self.assertNotIn("secret-value", json.dumps(result))

    def test_duplicate_nonfinite_and_large_json_are_refused(self):
        samples = ['{"schema":1,"schema":2}', '{"value":NaN}',
                   '{"value":Infinity}', " " * (MAX_INPUT_BYTES + 1)]
        for raw in samples:
            with self.subTest(raw=raw[:30]), patch("sys.stdin", io.StringIO(raw)):
                with self.assertRaises(GateError):
                    read_input("-")

    def test_link_and_fifo_inputs_are_refused_without_reading(self):
        source = self.root / "request.json"
        source.write_text(json.dumps(self.payload()))
        link = self.root / "alias.json"
        link.symlink_to(source)
        with self.assertRaises(GateError):
            read_input(str(link))
        if hasattr(os, "mkfifo"):
            fifo = self.root / "pipe"
            os.mkfifo(fifo)
            with self.assertRaises(GateError):
                read_input(str(fifo))

    def test_unimplemented_effects_and_arbitrary_path_arguments_are_refused(self):
        for action in ("apply", "reserve", "release-lease", "reconcile"):
            code, result = self.invoke(["project", "resource", action,
                                       "--path", str(self.root / "private-name")])
            self.assertEqual(code, 2)
            self.assertEqual(result["error"], "resource_plan_arguments_invalid")
            self.assertNotIn(str(self.root), json.dumps(result))
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
