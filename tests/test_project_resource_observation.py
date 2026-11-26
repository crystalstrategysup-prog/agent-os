"""Observation is useful without becoming an implicit destructive permission.

Real temporary directories exercise metadata/path behavior. Small independent
capacity examples replace only OS capacity snapshots, never the calculation.
No test requires a mount, a quota change, a service stop or a project mutation.
"""

from contextlib import ExitStack
from copy import deepcopy
import errno
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_os import project_resources as r
from agent_os.safeio import GateError


MOUNT = {"status": "OBSERVED", "namespace_inode": 123, "mount_id": 42,
         "filesystem_type": "ext4", "filesystem_scope": "LOCAL"}
PHYSICAL = {"status": "OBSERVED", "source": "STATVFS", "available_bytes": 220,
            "available_inodes": 10, "total_bytes": 1000, "total_inodes": 100}


class ResourceObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agentos-observation-", dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "private-Bearer-secret-not-an-id"
        self.root.mkdir(mode=0o700)
        self.leaf = self.root / "private-build-secret-name"
        self.leaf.mkdir(mode=0o700)
        (self.leaf / "unique.txt").write_text("original data must remain unchanged")

    def payload(self):
        return {
            "schema": r.REQUEST_SCHEMA, "project_id": "project-a", "task_id": "task-a",
            "run_id": "run-a", "operation_id": "operation-a",
            "roots": [{"admitted_root_id": "root-a", "path": str(self.root)}],
            "resources": [{
                "resource_id": "resource-a", "admitted_root_id": "root-a",
                "relative_name": self.leaf.name, "class": "build-output", "owner_id": "worker-a",
                "origin": "DECLARED_RUN", "reproducible": True, "inputs_ref": "inputs-a",
                "process_state": "STOPPED", "dependencies": "CLEAR",
                "release_condition": "SATISFIED", "retention": None,
            }],
            "capacity": [{
                "admitted_root_id": "root-a", "remaining_peak": {"bytes": 80, "inodes": 5},
                "headroom": {"bytes": 40, "inodes": 2},
                "unconsumed_reservations": [{"reservation_id": "reservation-a", "bytes": 100, "inodes": 3}],
                "quota": {"status": "UNKNOWN", "required": False,
                          "available_bytes": None, "available_inodes": None},
            }],
        }

    def planned(self, payload=None):
        with patch.object(r, "_mount_identity", return_value=deepcopy(MOUNT)), \
                patch.object(r, "_physical_snapshot", return_value=deepcopy(PHYSICAL)):
            return r.observe_plan(self.payload() if payload is None else payload)

    def test_actual_metadata_is_read_only_private_and_not_a_tree_size(self):
        data = (self.leaf / "unique.txt").read_bytes()
        metadata = self.leaf.stat()
        supplied = self.payload()
        before = deepcopy(supplied)
        with ExitStack() as stack:
            for name in ("write", "unlink", "remove", "rename", "replace", "mkdir", "kill", "killpg"):
                stack.enter_context(patch.object(r.os, name, side_effect=AssertionError("mutation")))
            stack.enter_context(patch.object(r.os, "scandir", side_effect=AssertionError("tree scan")))
            stack.enter_context(patch.object(r.os, "walk", side_effect=AssertionError("tree scan")))
            actual_open = open

            def metadata_only(path, *args, **kwargs):
                self.assertTrue(str(path).startswith("/proc/self/"))
                return actual_open(path, *args, **kwargs)

            stack.enter_context(patch("builtins.open", side_effect=metadata_only))
            result = r.observe_plan(supplied)
        self.assertEqual(supplied, before)
        self.assertEqual(result["roots"][0]["observation_status"], "OBSERVED")
        resource = result["resources"][0]
        self.assertEqual(resource["identity"]["inode"], metadata.st_ino)
        self.assertEqual(resource["identity"]["type"], "DIRECTORY")
        self.assertEqual(resource["size"], {"logical_bytes": None, "allocated_bytes": None,
                                             "tree_bytes": None, "source": "NOT_MEASURED"})
        self.assertEqual(resource["recursive_inventory"], "NOT_PERFORMED")
        self.assertEqual((self.leaf / "unique.txt").read_bytes(), data)
        self.assertEqual(self.leaf.stat().st_mtime_ns, metadata.st_mtime_ns)
        self.assertEqual(result["effects"], "NONE")
        for flag in ("physical_cleanup_supported", "reservation_supported", "apply_supported",
                     "admission_granted", "authority_granted", "task_mutation"):
            self.assertIs(result[flag], False)
        self.assertEqual(result["native_hooks"], "DISABLED")
        serialized = json.dumps(result)
        for private in (str(self.root), self.leaf.name, "unique.txt", data.decode()):
            self.assertNotIn(private, serialized)

    def test_candidate_is_only_declared_qualification_and_file_size_is_metadata(self):
        payload = self.payload()
        payload["resources"][0]["relative_name"] += "/unique.txt"
        payload["resources"][0]["class"] = "test-database"
        result = self.planned(payload)["resources"][0]
        self.assertEqual(result["status"], "CANDIDATE_FOR_QUALIFICATION")
        self.assertEqual(result["declarations"]["source"], "CALLER_DECLARED")
        self.assertFalse(result["deletion_authorized"])
        self.assertEqual(result["size"]["logical_bytes"], len((self.leaf / "unique.txt").read_bytes()))
        self.assertIsNone(result["size"]["tree_bytes"])
        self.assertEqual(result["next_action"], "QUALIFY_TREE_WRITERS_AND_RECOVERY")

    def test_active_unknown_and_unreleased_resources_hold(self):
        for key, value, reason in (
            ("owner_id", None, "OWNER_UNKNOWN"),
            ("origin", "UNKNOWN", "ORIGIN_UNKNOWN"),
            ("class", "unknown", "CLASS_UNKNOWN"),
            ("process_state", "ACTIVE", "PROCESS_ACTIVE"),
            ("process_state", "UNKNOWN", "PROCESS_UNKNOWN"),
            ("dependencies", "ACTIVE", "DEPENDENCIES_ACTIVE"),
            ("release_condition", "OPEN", "RELEASE_OPEN"),
            ("reproducible", None, "REPRODUCTION_UNKNOWN"),
            ("inputs_ref", None, "REPRODUCTION_INPUTS_UNKNOWN"),
        ):
            with self.subTest(key=key, value=value):
                payload = self.payload()
                payload["resources"][0][key] = value
                result = self.planned(payload)["resources"][0]
                self.assertEqual(result["status"], "HOLD")
                self.assertIn(reason, result["reasons"])

    def test_backups_accepted_history_and_unique_data_are_retained(self):
        for classification in ("temporary-backup", "durable-backup", "accepted-checkpoint",
                               "deliverable", "journal", "shared-cache", "private-cache",
                               "reproducible-temporary"):
            with self.subTest(classification=classification):
                payload = self.payload()
                payload["resources"][0]["class"] = classification
                self.assertEqual(self.planned(payload)["resources"][0]["status"], "RETAINED")
        payload = self.payload()
        payload["resources"][0]["reproducible"] = False
        self.assertEqual(self.planned(payload)["resources"][0]["next_action"], "PRESERVE_UNIQUE_DATA")
        payload["resources"][0]["retention"] = {
            "owner_id": "reviewer-a", "reason_code": "ROLLBACK_WINDOW",
            "next_review": "2026-01-01T12:30:00+00:00",
        }
        retained = self.planned(payload)["resources"][0]
        self.assertEqual(retained["status"], "RETAINED")
        self.assertEqual(retained["next_action"], "REVIEW_RETENTION")
        self.assertEqual(retained["retention"]["owner_id"], "reviewer-a")
        # A past review timestamp is not expiry and never becomes delete authority.
        self.assertFalse(retained["deletion_authorized"])

    def test_unsafe_paths_are_rejected_before_observation(self):
        for value in ("../private", "/absolute", "nested/../../private", "a//b", "a/./b", "a\\b", "a\x00b"):
            with self.subTest(value=value):
                payload = self.payload()
                payload["resources"][0]["relative_name"] = value
                with patch.object(r, "_mount_table", side_effect=AssertionError("observed invalid input")):
                    with self.assertRaisesRegex(GateError, "^resource_observation_invalid_path$"):
                        r.observe_plan(payload)

    def test_symlink_roots_parents_and_leaves_are_not_followed(self):
        outside = Path(self.temp.name) / "outside-private-target"
        outside.mkdir(mode=0o700)
        (outside / "unique.txt").write_text("keep me")
        link = self.root / "link"
        link.symlink_to(outside, target_is_directory=True)
        for mode in ("root", "parent", "leaf"):
            with self.subTest(mode=mode):
                payload = self.payload()
                if mode == "root":
                    payload["roots"][0]["path"] = str(link)
                else:
                    payload["resources"][0]["relative_name"] = "link/unique.txt" if mode == "parent" else "link"
                result = self.planned(payload)["resources"][0]
                self.assertEqual(result["status"], "HOLD")
                self.assertIn("SYMLINK", result["reasons"])
        self.assertEqual((outside / "unique.txt").read_text(), "keep me")
        self.assertTrue(link.is_symlink())

    def test_hardlinks_hold_but_directory_link_count_is_not_a_file_link(self):
        target = self.leaf / "unique.txt"
        os.link(target, self.root / "second-name")
        payload = self.payload()
        payload["resources"][0]["relative_name"] += "/unique.txt"
        result = self.planned(payload)["resources"][0]
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("HARDLINK_OR_UNLINKED", result["reasons"])
        self.assertEqual(self.planned()["resources"][0]["status"], "CANDIDATE_FOR_QUALIFICATION")
        self.assertEqual((self.root / "second-name").stat().st_ino, target.stat().st_ino)

    def test_mount_and_platform_unknown_never_qualify_a_candidate(self):
        with patch.object(r.sys, "platform", "darwin"):
            result = r.observe_plan(self.payload())["resources"][0]
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("MOUNT_IDENTITY_UNKNOWN", result["reasons"])
        unknown_fs = {**MOUNT, "filesystem_type": "UNKNOWN", "filesystem_scope": "UNKNOWN"}
        with patch.object(r, "_mount_identity", return_value=unknown_fs):
            result = r.observe_plan(self.payload())["resources"][0]
        self.assertIn("FILESYSTEM_PROFILE_UNQUALIFIED", result["reasons"])
        self.assertEqual(result["status"], "HOLD")

    def test_without_metadata_handle_regular_target_is_never_opened(self):
        fd = os.open(self.leaf, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, fd)
        # Exercise the leaf reader directly so the observation of parent roots
        # cannot hide an unsafe open of a replaced regular file or device.
        with patch.object(r.sys, "platform", "darwin"), \
                patch.object(r.os, "open", side_effect=AssertionError("target opened")):
            identity, mount, size, reasons = r._resource_metadata(fd, "unique.txt", (None, {}))
        self.assertEqual(identity["type"], "REGULAR_FILE")
        self.assertEqual(mount["status"], "UNKNOWN")
        self.assertEqual(size["source"], "FILE_METADATA")
        self.assertIn("METADATA_HANDLE_UNAVAILABLE", reasons)

    def test_nested_mount_same_device_and_nonprivate_root_hold(self):
        with patch.object(r, "_mount_identity", side_effect=[MOUNT, {**MOUNT, "mount_id": 43}]):
            result = r.observe_plan(self.payload())["resources"][0]
        self.assertIn("NESTED_MOUNT", result["reasons"])
        self.assertEqual(result["status"], "HOLD")
        self.root.chmod(0o755)
        result = self.planned()["resources"][0]
        self.assertIn("ROOT_NOT_PRIVATE_OWNER", result["reasons"])
        self.assertEqual(result["status"], "HOLD")

    def test_missing_and_os_errors_do_not_leak_input_or_exception_paths(self):
        payload = self.payload()
        payload["roots"][0]["path"] += "/missing-secret"
        result = self.planned(payload)
        self.assertEqual(result["resources"][0]["status"], "HOLD")
        self.assertEqual(result["volumes"][0]["assessment"]["status"], "UNKNOWN")
        with patch.object(r, "_open_root", side_effect=OSError(errno.EACCES, "private-Bearer-secret", str(self.root))):
            denied = r.observe_plan(self.payload())
        self.assertIn("INACCESSIBLE", denied["roots"][0]["reasons"])
        self.assertNotIn("private-Bearer-secret", json.dumps(denied))
        self.assertNotIn("missing-secret", json.dumps(result))

    def test_capacity_220_minus_40_minus_100_fits_80_not_90_and_inodes_matter(self):
        payload = self.payload()
        # Existing data is already reflected in available space, not charged again.
        (self.leaf / "already-written").write_bytes(b"x" * 10000)
        result = self.planned(payload)["volumes"][0]
        self.assertEqual(result["assessment"]["status"], "FITS_REPORTED_VALUES")
        self.assertIn("QUOTA_UNKNOWN", result["assessment"]["reasons"])
        self.assertEqual(result["assessment"]["bytes"]["available_after_allowances"], 80)
        self.assertFalse(result["admission_granted"])
        payload["capacity"][0]["remaining_peak"]["bytes"] = 90
        self.assertEqual(self.planned(payload)["volumes"][0]["assessment"]["status"], "INSUFFICIENT")
        payload["capacity"][0]["remaining_peak"] = {"bytes": 80, "inodes": 6}
        result = self.planned(payload)["volumes"][0]["assessment"]
        self.assertEqual(result["bytes"]["status"], "FITS_REPORTED_VALUES")
        self.assertEqual(result["inodes"]["status"], "INSUFFICIENT")
        self.assertEqual(result["status"], "INSUFFICIENT")

    def test_required_unknown_quota_unknown_budget_and_known_quota_limit(self):
        payload = self.payload()
        payload["capacity"][0]["quota"]["required"] = True
        result = self.planned(payload)["volumes"][0]["assessment"]
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIn("QUOTA_UNKNOWN", result["reasons"])
        payload["capacity"][0]["remaining_peak"]["bytes"] = 90
        self.assertEqual(self.planned(payload)["volumes"][0]["assessment"]["status"], "INSUFFICIENT")
        payload["capacity"][0]["remaining_peak"]["bytes"] = None
        self.assertEqual(self.planned(payload)["volumes"][0]["assessment"]["status"], "UNKNOWN")
        payload["capacity"][0]["remaining_peak"]["bytes"] = 80
        payload["capacity"][0]["quota"].update(status="DECLARED", available_bytes=200, available_inodes=10)
        self.assertEqual(self.planned(payload)["volumes"][0]["assessment"]["status"], "INSUFFICIENT")

    def test_shared_volume_does_not_double_capacity_or_existing_reservations(self):
        payload = self.payload()
        nested = self.root / "second-admitted-root"
        nested.mkdir(mode=0o700)
        payload["roots"].append({"admitted_root_id": "root-b", "path": str(nested)})
        second = deepcopy(payload["capacity"][0])
        second["admitted_root_id"] = "root-b"
        for budget in (payload["capacity"][0], second):
            budget["remaining_peak"] = {"bytes": 45, "inodes": 2}
        payload["capacity"].append(second)
        result = self.planned(payload)
        self.assertEqual(len(result["volumes"]), 1)
        volume = result["volumes"][0]
        self.assertEqual(volume["physical"]["available_bytes"], 220)
        self.assertEqual(volume["declared"]["unconsumed_reserved"]["bytes"], 100)
        self.assertEqual(volume["declared"]["headroom"]["bytes"], 40)
        self.assertEqual(volume["declared"]["remaining_peak"]["bytes"], 90)
        self.assertEqual(volume["assessment"]["status"], "INSUFFICIENT")
        payload["capacity"][1]["unconsumed_reservations"][0]["bytes"] = 101
        conflicting = self.planned(payload)["volumes"][0]["assessment"]
        self.assertEqual(conflicting["status"], "UNKNOWN")
        self.assertIn("RESERVATION_CONFLICT", conflicting["reasons"])

    def test_statvfs_unknown_inodes_and_failures_are_not_zero_or_a_grant(self):
        raw = SimpleNamespace(f_frsize=1, f_bsize=1, f_bavail=220, f_blocks=1000,
                              f_files=0, f_favail=0)
        with patch.object(r.os, "fstatvfs", return_value=raw):
            result = r.observe_plan(self.payload())["volumes"][0]
        self.assertEqual(result["physical"]["available_bytes"], 220)
        self.assertIsNone(result["physical"]["available_inodes"])
        self.assertEqual(result["assessment"]["status"], "UNKNOWN")
        with patch.object(r.os, "fstatvfs", side_effect=OSError(errno.EIO, "private-secret")):
            result = r.observe_plan(self.payload())["volumes"][0]
        self.assertIsNone(result["physical"]["available_bytes"])
        self.assertEqual(result["assessment"]["status"], "UNKNOWN")
        self.assertNotIn("private-secret", json.dumps(result))

    def test_invalid_descriptor_limits_and_bool_quantities_are_safe_refusals(self):
        invalid = []
        payload = self.payload()
        payload["private-secret-extra-field"] = "private-secret-value"
        invalid.append(payload)
        payload = self.payload()
        payload["capacity"][0]["remaining_peak"]["bytes"] = True
        invalid.append(payload)
        payload = self.payload()
        payload["resources"].append(deepcopy(payload["resources"][0]))
        invalid.append(payload)
        payload = self.payload()
        payload["project_id"] = "private/secret/id"
        invalid.append(payload)
        payload = self.payload()
        payload["resources"][0]["retention"] = {"owner_id": "owner-a", "reason_code": "ROLLBACK_WINDOW"}
        invalid.append(payload)
        payload = self.payload()
        payload["roots"][0]["path"] = "/" + "private-secret" * r.MAX_INPUT_BYTES
        invalid.append(payload)
        for payload in invalid:
            with self.subTest(keys=list(payload)):
                with self.assertRaises(GateError) as caught:
                    r.observe_plan(payload)
                self.assertRegex(str(caught.exception), r"^resource_observation_[a-z_]+$")
                self.assertNotIn("private", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
