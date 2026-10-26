#!/usr/bin/env python3
"""Run Atlas's fixed public local checks with recorded commands and runtimes.

Usage: python3 -B check.py [--list]
The root comes from __file__, so the command works from any working directory.
Only the explicitly named bundled unittest modules and Atlas UI suite are selected. The
navigator unittest invokes the bundled generic DOM harness on its own temporary
synthetic snapshot. No package installation, product/host command, Git action,
service, or network operation is started. No environment values are reported.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
MAX_SUITE_SECONDS = 60
FIXED_INPUTS = (
    "check.py", "tests/test_navigator.py", "tests/test_atlas.py",
    "tests/test_import_matrix.py", "tests/test_projection_archive.py", "tests/test_catalog.py",
    "tests/test_import_history_pages.py", "tests/test_workspace.py", "tests/test_sync_docs.py",
    "tests/ui_dom.cjs", "tests/test_atlas_ui.cjs",
    "skills/atlas/scripts/navigator.py", "skills/atlas/scripts/atlas.py",
    "skills/atlas/scripts/import_matrix.py", "skills/atlas/scripts/catalog.py",
    "skills/atlas/scripts/workspace.py", "skills/atlas/scripts/sync_docs.py",
    "skills/atlas/scripts/viewer.js", "skills/atlas/scripts/viewer.css",
    "skills/atlas/scripts/navigator.schema.json",
    "skills/atlas/scripts/atlas.project.schema.json",
    "skills/atlas/scripts/atlas.work.schema.json",
    "skills/atlas/scripts/atlas.inventory.schema.json",
    "skills/atlas/scripts/OPERATIONS.json",
    "skills/atlas/scripts/WORKSPACE_OPERATIONS.json",
)


def file_pins():
    pins = []
    for relative in FIXED_INPUTS:
        path = ROOT / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError("MISSING_OR_LINKED_CHECK_INPUT:" + relative)
        raw = path.read_bytes()
        pins.append({"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return pins


def commands(node):
    return [
        {"id": "public_unittest", "argv": [sys.executable, "-B", "-m", "unittest", "-v", "test_navigator", "test_atlas",
            "test_import_matrix", "test_projection_archive", "test_catalog", "test_import_history_pages", "test_workspace", "test_sync_docs"],
         "cwd": str(ROOT / "tests"), "minimum_checks": 161},
        {"id": "atlas_ui", "argv": [node or "node", str(ROOT / "tests/test_atlas_ui.cjs")],
         "cwd": str(ROOT), "minimum_checks": 47},
    ]


def child_environment(node):
    # Do not pass token-bearing variables, Python import overrides, or NODE_OPTIONS.
    path_parts = [str(Path(node).parent), str(Path(sys.executable).parent), os.defpath]
    env = {"PATH": os.pathsep.join(path_parts), "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONHASHSEED": "0", "PYTHONUTF8": "1", "LANG": "C", "LC_ALL": "C"}
    if os.name == "nt" and "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


def execute(spec, env, timeout=MAX_SUITE_SECONDS):
    result = {**spec, "status": "NOT_RUN"}
    started = time.monotonic()
    try:
        completed = subprocess.run(spec["argv"], cwd=spec["cwd"], env=env, shell=False,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        result.update(exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr,
                      status="PASS" if completed.returncode == 0 else "FAIL")
    except subprocess.TimeoutExpired as exc:
        decode = lambda value: value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")
        result.update(status="TIMEOUT", exit_code=None, stdout=decode(exc.stdout), stderr=decode(exc.stderr))
    except OSError as exc:
        result.update(status="REFUSED", exit_code=None, code=type(exc).__name__, errno=exc.errno)
    result["duration_seconds"] = round(time.monotonic() - started, 6)
    return result


def assess(result):
    if result["status"] != "PASS":
        return
    if result["id"] == "public_unittest":
        match = re.search(r"^Ran (\d+) tests? in [0-9.]+s$", result["stderr"], re.MULTILINE)
        result["checks"] = int(match.group(1)) if match else None
        final_ok = re.search(r"^OK$", result["stderr"], re.MULTILINE) is not None
        nested = []
        for line in result["stdout"].splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict) and "checks" in item and "level" in item:
                nested.append(item)
        result["nested_dom_receipts"] = nested
        nested_ok = (len(nested) == 1 and nested[0].get("status") == "PASS"
                     and type(nested[0].get("checks")) is int and nested[0]["checks"] >= 25
                     and nested[0].get("level") == "PURE_LOGIC_AND_MINIMAL_DOM_NOT_VISUAL")
        success = final_ok and result["checks"] is not None and result["checks"] >= result["minimum_checks"] and nested_ok
    else:
        try:
            receipt = json.loads(result["stdout"])
        except ValueError:
            receipt = {}
        if not isinstance(receipt, dict):
            receipt = {}
        result["receipt"] = receipt
        result["checks"] = receipt.get("checks")
        success = (receipt.get("status") == "PASS" and type(result["checks"]) is int
                   and result["checks"] >= result["minimum_checks"]
                   and receipt.get("level") == "PURE_LOGIC_AND_MINIMAL_DOM_NOT_VISUAL"
                   and receipt.get("network") is False
                   and receipt.get("browser_visual_acceptance") == "NOT_RUN")
    if not success:
        result.update(status="REFUSED", code="CHECK_RECEIPT_INCOMPLETE")


def main():
    report = {"schema": "atlas.local-checks/v1", "status": "REFUSED",
              "invocation": list(getattr(sys, "orig_argv", [sys.executable, *sys.argv])), "root": str(ROOT),
              "limits": {"scope": "BUNDLED_SYNTHETIC_LOCAL_CHECKS", "product_tests": "NOT_RUN",
                         "host_actions": "NOT_RUN", "browser_visual_acceptance": "NOT_RUN"}}
    try:
        if sys.argv[1:] not in ([], ["--list"]):
            raise ValueError("USAGE:python3 -B check.py [--list]")
        node = shutil.which("node")
        report["inputs"] = file_pins()
        report["runtimes"] = {"python": {"executable": sys.executable, "version": platform.python_version(),
                                             "implementation": platform.python_implementation(), "status": "CURRENT_PROCESS"},
                              "node": {"executable": node, "version": None, "status": "NOT_PROBED"}}
        report["suites"] = [{**spec, "status": "NOT_RUN"} for spec in commands(node)]
        if sys.argv[1:] == ["--list"]:
            report["status"] = "LISTED_NOT_RUN"
        else:
            if node is None:
                raise ValueError("NODE_RUNTIME_MISSING")
            report["started_at"] = datetime.now(timezone.utc).isoformat()
            env = child_environment(node)
            version = execute({"id": "node_version", "argv": [node, "--version"], "cwd": str(ROOT)}, env, timeout=10)
            report["runtime_probe"] = version
            if version["status"] != "PASS" or re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+[^\s]*", version["stdout"].strip()) is None:
                raise ValueError("NODE_RUNTIME_PROBE_FAILED")
            report["runtimes"]["node"].update(version=version["stdout"].strip(), status="PROBED")
            report["suites"] = []
            for spec in commands(node):
                result = execute(spec, env)
                assess(result)
                report["suites"].append(result)
            report["status"] = "PASS" if all(suite["status"] == "PASS" for suite in report["suites"]) else "REFUSED"
    except (OSError, ValueError, UnicodeError) as exc:
        report["code"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False))
    return 0 if report["status"] in ("PASS", "LISTED_NOT_RUN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
