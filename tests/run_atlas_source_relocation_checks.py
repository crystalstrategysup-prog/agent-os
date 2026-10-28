"""Run every selected regression in a fresh interpreter, without module collisions.

The facade intentionally refuses foreign bare module names. Canonical standalone
tests and facade tests therefore cannot share sys.modules. Physical TMPDIR keeps
the unchanged direct-call fixtures canonical on macOS; no path guard is relaxed.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "PYTHONPATH": str(root / "src"),
                   "PYTHONDONTWRITEBYTECODE": "1",
                   "TMPDIR": str(Path(tempfile.gettempdir()).resolve())}
    groups = ["tests/test_atlas_source_relocation.py",
              "modules/atlas/tests/test_atlas.py",
              "modules/atlas/tests/test_navigator.py",
              "tests/test_atlas_module.py",
              "tests/test_source_selection.py"]
    failed = []
    for path in groups:
        print("CHECK " + path, flush=True)
        result = subprocess.run([sys.executable, "-B", "-m", "pytest", "-q",
                                 "--tb=short", "-p", "no:cacheprovider", path],
                                cwd=root, env=environment, timeout=45)
        if result.returncode:
            failed.append(path)
    print("SELECTED_REGRESSIONS_" + ("FAIL:" + ",".join(failed) if failed else "PASS"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
