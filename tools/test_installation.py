#!/usr/bin/env python3
"""Repeatable offline install/update/rollback test. Uses only disposable fixture roots.

Requires local pip, setuptools>=68 and wheel to build a synthetic previous release.
An optional --overlay is imported ONLY into a temporary user home; no real home is touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(wheel: Path, overlay: Path | None = None) -> dict:
    source = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(source / "src"))
    from agent_os import __version__

    wheel = wheel.resolve()
    if not wheel.is_file():
        raise ValueError("wheel_required")
    runs = []

    def run(argv):
        env = {
            **os.environ,
            "PIP_NO_INDEX": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        r = subprocess.run(
            [str(x) for x in argv],
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
            check=False,
        )
        runs.append(
            {
                "argv": [str(x) for x in argv],
                "return_code": r.returncode,
                "stdout": r.stdout[-30000:],
                "stderr": r.stderr[-5000:],
            }
        )
        if r.returncode:
            raise RuntimeError(r.stdout + "\n" + r.stderr)
        return json.loads(r.stdout) if r.stdout.strip().startswith("{") else r.stdout

    with tempfile.TemporaryDirectory(prefix="agentos-install-check-") as td:
        t = Path(td)
        fixture = t / "prior-fixture-source"
        shutil.copytree(
            source,
            fixture,
            ignore=shutil.ignore_patterns(
                ".agentos",
                "__pycache__",
                ".venv",
                "*.egg-info",
                ".pytest_cache",
                "build",
                "dist",
            ),
        )
        p = fixture / "src/agent_os/__init__.py"
        p.write_text(p.read_text().replace(__version__, "0.0.0-beta.0"))
        p = fixture / "pyproject.toml"
        p.write_text(
            re.sub(r'(?m)^version = ".*"$', 'version = "0.0.0b0"', p.read_text())
        )
        p = fixture / "src/agent_os/resources/contracts/mcp-tools-v1.json"
        contract = json.loads(p.read_text())
        contract["serverInfo"]["version"] = "0.0.0-beta.0"
        p.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n")
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                t / "fixture-dist",
                fixture,
            ]
        )
        prior = next((t / "fixture-dist").glob("*.whl"))
        core = t / "core"
        user = t / "user"
        user.mkdir()
        (user / "config.json").write_text(
            '{"schema":"agent-os.community-config/v5","fixture":"retain me exactly","custom":17}\n'
        )
        (user / "knowledge").mkdir()
        (user / "knowledge/local.txt").write_text("Synthetic knowledge sentinel.\n")
        (user / "secrets").mkdir()
        (user / "secrets/fixture-only.txt").write_text(
            "FAKE TEST DATA, NOT AN ACTUAL SECRET\n"
        )

        def snapshot():
            return {
                p.relative_to(user).as_posix(): digest(p)
                for p in user.rglob("*")
                if p.is_file()
            }

        before = snapshot()
        installer = source / "tools/install.py"

        def install(w, ver, current, apply=True):
            a = [
                sys.executable,
                installer,
                "install",
                "--wheel",
                w,
                "--sha256",
                digest(w),
                "--version",
                ver,
                "--core-home",
                core,
                "--user-home",
                user,
            ]
            if apply:
                a += ["--apply", "--expected-current", current]
            return run(a)

        plan = install(prior, "0.0.0-beta.0", "none", False)
        assert plan["status"] == "PLANNED"
        assert not core.exists()
        a = install(prior, "0.0.0-beta.0", "none")
        assert snapshot() == before
        b = install(wheel, __version__, a["release_id"])
        assert snapshot() == before
        run(
            [
                sys.executable,
                installer,
                "rollback",
                "--release-id",
                a["release_id"],
                "--core-home",
                core,
                "--user-home",
                user,
                "--apply",
                "--expected-current",
                b["release_id"],
            ]
        )
        assert snapshot() == before
        install(wheel, __version__, a["release_id"])
        assert snapshot() == before
        agent = core / "current/.venv/bin/agentos"
        newuser = t / "newuser"
        if overlay:
            result = run(
                [
                    agent,
                    "--home",
                    newuser,
                    "overlay",
                    "import",
                    "--source",
                    overlay.resolve(),
                ]
            )
            assert result["status"] == "READY"
            assert not newuser.exists()
            result = run(
                [
                    agent,
                    "--home",
                    newuser,
                    "overlay",
                    "import",
                    "--source",
                    overlay.resolve(),
                    "--apply",
                ]
            )
            assert result["status"] == "IMPORTED"
            config_before = digest(newuser / "config.json")
        else:
            config_before = None
        run([agent, "--home", newuser, "init"])
        if config_before:
            assert digest(newuser / "config.json") == config_before
        assert run([agent, "--home", newuser, "overlay", "status"])["status"] == "PASS"
        result = run(
            [
                agent,
                "--home",
                newuser,
                "integrate",
                "codex",
                "--codex-home",
                t / "fixture-codex",
                "--skills-home",
                t / "fixture-skills",
                "--apply",
            ]
        )
        assert result["hook_trust_changed"] is False
        resources = run([agent, "resources", "--list"])
        assert (
            "skills/agentos-project-entry/SKILL.md" in resources["files"]
            and "docs/PROCESS.md" in resources["files"]
        )
        return {
            "schema": "agentos.local-install-verification/v1",
            "status": "PASS",
            "environment": {
                "system": platform.system(),
                "machine": platform.machine(),
                "python": platform.python_version(),
            },
            "at": datetime.now(UTC).isoformat(),
            "wheel_sha256": digest(wheel),
            "prior_release": "SYNTHETIC version-only 0.0.0-beta.0 fixture, not an actual public release",
            "checks": {
                "offline_initial_install": True,
                "offline_update": True,
                "rollback": True,
                "reactivate": True,
                "user_tree_unchanged": snapshot() == before,
                "overlay_import_and_init_preserve_config": bool(overlay),
                "installed_resource_presence": True,
                "integration_preserves_native_trust": True,
            },
            "target_mac_verified": False,
            "native_hooks_activated": False,
            "private_runtime_parity_verified": False,
            "user_sentinel_hashes": before,
            "runs": runs,
        }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wheel", type=Path, required=True)
    p.add_argument("--overlay", type=Path)
    p.add_argument("--report", type=Path)
    a = p.parse_args()
    value = verify(a.wheel, a.overlay)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(text)
    print(
        json.dumps(
            {
                k: v
                for k, v in value.items()
                if k not in ("runs", "user_sentinel_hashes")
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
