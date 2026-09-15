"""Local, non-secret health checks."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .config import AgentOSPaths, load_config


def run(paths: AgentOSPaths) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    checks.append({"id": "home_exists", "ok": paths.home.is_dir()})
    checks.append({"id": "config_valid", "ok": _config_valid(paths)})
    checks.append({"id": "secret_dir_private", "ok": _private_directory(paths.secrets)})
    return {
        "schema": "agent-os.doctor/v1",
        "status": "PASS" if all(item["ok"] for item in checks) else "FAIL",
        "checks": checks,
    }


def _config_valid(paths: AgentOSPaths) -> bool:
    try:
        load_config(paths)
    except (OSError, ValueError):
        return False
    return True


def _private_directory(path: Path) -> bool:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return False
    return path.is_dir() and mode & 0o077 == 0 and path.stat().st_uid == os.getuid()
