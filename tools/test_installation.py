#!/usr/bin/env python3
"""Repeatable offline install/update/rollback test. Uses only disposable fixture roots.

Requires local pip, setuptools>=68 and wheel to build a synthetic previous release.
An optional --overlay is imported ONLY into a temporary user home; no real home is touched.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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

    # The actual installer must handle pip's shell trampoline for venv paths
    # containing spaces; every update and rollback in this fixture exercises it.
    with tempfile.TemporaryDirectory(prefix="agentos install check ") as td:
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
        release_dir = core / "releases" / b["release_id"]
        site = next((release_dir / ".venv/lib").glob("python*/site-packages"))
        workflow_file = site / "agent_os/workflow.py"
        original_workflow = workflow_file.read_bytes()
        reactivate = [
            sys.executable,
            installer,
            "install",
            "--wheel",
            wheel,
            "--sha256",
            digest(wheel),
            "--version",
            __version__,
            "--core-home",
            core,
            "--user-home",
            user,
            "--apply",
            "--expected-current",
            b["release_id"],
        ]

        def blocked_reactivation(expected_error):
            result = subprocess.run(
                [str(x) for x in reactivate],
                capture_output=True,
                text=True,
                timeout=30,
                env={**os.environ, "PIP_NO_INDEX": "1"},
                check=False,
            )
            value = json.loads(result.stdout)
            assert result.returncode == 2 and value["status"] == "BLOCKED"
            assert expected_error in value["error"], value
            assert (core / "current").resolve() == release_dir.resolve()
            assert snapshot() == before
            runs.append(
                {
                    "check": "corrupt_installed_payload_refused",
                    "expected_error": expected_error,
                    "return_code": result.returncode,
                }
            )

        workflow_file.write_bytes(original_workflow + b"\n# fixture drift\n")
        blocked_reactivation("installed_payload_mismatch")
        workflow_file.write_bytes(original_workflow)
        held = workflow_file.with_suffix(".held")
        workflow_file.rename(held)
        blocked_reactivation("installed_payload_mismatch")
        held.rename(workflow_file)
        extra = site / "agent_os/unexpected.py"
        extra.write_text("# fixture extra module\n")
        blocked_reactivation("installed_payload_extra")
        extra.unlink()
        workflow_file.rename(held)
        workflow_file.symlink_to(held)
        blocked_reactivation("installed_payload_mismatch")
        workflow_file.unlink()
        held.rename(workflow_file)
        manifest_path = release_dir / "INSTALL.json"
        original_manifest = manifest_path.read_bytes()
        manifest = json.loads(original_manifest)
        manifest["overlay_schema"] = 99
        manifest_path.write_text(json.dumps(manifest))
        blocked_reactivation("release_schema_incompatible")
        manifest_path.write_bytes(original_manifest)
        entrypoint = release_dir / ".venv/bin/agentos"
        original_entrypoint = entrypoint.read_bytes()
        entrypoint.write_bytes(original_entrypoint + b"\n# fixture drift\n")
        blocked_reactivation("installed_entrypoint_hash_mismatch")
        entrypoint.write_bytes(original_entrypoint)
        manifest_without_hashes = json.loads(original_manifest)
        manifest_without_hashes.pop("script_sha256")
        manifest_path.write_text(json.dumps(manifest_without_hashes))
        entrypoint.write_bytes(original_entrypoint + b"\n# fixture drift\n")
        blocked_reactivation("installed_entrypoint_hash_contract_missing")
        entrypoint.write_bytes(original_entrypoint)
        manifest_path.write_bytes(original_manifest)
        marker = t / "unverified-cache-executed.txt"
        cache_script = """import importlib.util, importlib._bootstrap_external as be, sys
from pathlib import Path
module, marker = map(Path, sys.argv[1:])
source = module.read_bytes()
stat = module.stat()
payload = source.decode() + "\\nfrom pathlib import Path as _Path\\n_Path(" + repr(str(marker)) + ").write_text('bad')\\n"
cache = Path(importlib.util.cache_from_source(str(module)))
cache.parent.mkdir(exist_ok=True)
cache.write_bytes(be._code_to_timestamp_pyc(compile(payload, str(module), 'exec'), int(stat.st_mtime), len(source)))
"""
        run([release_dir / ".venv/bin/python", "-I", "-c", cache_script,
             site / "agent_os/__init__.py", marker])
        # Find the interpreter's actual cache tag rather than assuming Python 3.11.
        cache = next((site / "agent_os/__pycache__").glob("__init__.*.pyc"))
        assert run(reactivate[:-3])["status"] == "PLANNED"
        assert cache.exists(), "plan must not modify installed cache"
        run(reactivate)
        assert not marker.exists(), "unverified bytecode executed during activation"
        # A package-directory ancestor redirected into the user overlay must
        # fail before cache normalization can unlink an owner file.
        python_tree = site.parent
        foreign = user / "foreign-python-tree"
        python_tree.rename(foreign)
        python_tree.symlink_to(foreign, target_is_directory=True)
        foreign_cache = foreign / "site-packages/agent_os/__pycache__/owner-sentinel.pyc"
        foreign_cache.parent.mkdir(exist_ok=True)
        foreign_cache.write_bytes(b"owner cache sentinel")
        try:
            result = subprocess.run(
                [str(x) for x in reactivate], capture_output=True, text=True,
                timeout=30, env={**os.environ, "PIP_NO_INDEX": "1"}, check=False,
            )
            value = json.loads(result.stdout)
            assert result.returncode == 2 and value["status"] == "BLOCKED", value
            assert "installed_site_packages_directory_invalid" in value["error"], value
            assert foreign_cache.read_bytes() == b"owner cache sentinel"
            assert (core / "current").resolve() == release_dir.resolve()
            runs.append({
                "check": "package_ancestor_symlink_refused_without_owner_write",
                "argv": [str(x) for x in reactivate],
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "owner_cache_preserved": True,
                "current_preserved": True,
            })
        finally:
            python_tree.unlink()
            foreign_cache.unlink()
            foreign.rename(python_tree)
        assert snapshot() == before
        # Public beta.5 can have either pip launcher template. The v1 check
        # accepts only exact known bodies, without weakening v2 hash checks.
        spec = importlib.util.spec_from_file_location("agentos_test_installer", installer)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        old_scripts = {}
        for name, target in (("agentos", "agent_os.cli"), ("agentos-hook", "agent_os.hooks")):
            script = release_dir / ".venv/bin" / name
            old_scripts[script] = script.read_bytes()
            body = script.read_text()
            prefix = body[:body.index("import sys\n")]
            script.write_text(
                prefix + "# -*- coding: utf-8 -*-\nimport re\nimport sys\n"
                + f"from {target} import main\nif __name__ == '__main__':\n"
                + "    sys.argv[0] = re.sub(r'(-script\\.pyw|\\.exe)?$', '', sys.argv[0])\n"
                + "    sys.exit(main())\n"
            )
        try:
            selected_release = release_dir.resolve()
            module._verify_owned_payload(
                selected_release, selected_release / wheel.name, None, legacy=True
            )
            tampered = selected_release / ".venv/bin/agentos"
            tampered.write_bytes(tampered.read_bytes() + b"# unexpected launcher tail\n")
            try:
                module._verify_owned_payload(
                    selected_release, selected_release / wheel.name, None, legacy=True
                )
            except module.InstallError as exc:
                assert "legacy_entrypoint_not_canonical" in str(exc)
            else:
                raise AssertionError("legacy launcher tail accepted")
            runs.append({
                "check": "legacy_launcher_templates",
                "status": "PASS",
                "templates": ["pip-removesuffix", "pip-re.sub"],
                "unexpected_tail_refused": True,
                "fixture": "installed stable wheel with exact old pip script body",
            })
        finally:
            for script, original in old_scripts.items():
                script.write_bytes(original)
        workflow_file.write_bytes(original_workflow + b"\n# damaged current fixture\n")
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
        assert (core / "current").resolve() == (core / "releases" / a["release_id"]).resolve()
        workflow_file.write_bytes(original_workflow)
        install(wheel, __version__, a["release_id"])
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
        # Use a separate no-space prefix: Linux pip emits an unquoted /bin/sh
        # trampoline for a long safe path, unlike the quoted space-path form.
        with tempfile.TemporaryDirectory(prefix="agentos-long-") as long_td:
            long_base = Path(long_td)
            long_core = (
                long_base / ("long-" + "x" * 65) / ("y" * 70) / ("z" * 70) / "core"
            )
            long_user = long_base / "user"
            long_user.mkdir()
            long_install = run([
                sys.executable, installer, "install", "--wheel", wheel,
                "--sha256", digest(wheel), "--version", __version__,
                "--core-home", long_core, "--user-home", long_user,
                "--apply", "--expected-current", "none",
            ])
            assert long_install["status"] == "INSTALLED"
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
                "corrupt_installed_payload_refused": True,
                "package_ancestor_symlink_refused_without_owner_write": True,
                "legacy_launcher_templates": True,
                "damaged_current_can_switch_to_verified_release": True,
                "space_and_long_paths": True,
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
