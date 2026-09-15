"""Local, non-secret health checks."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .config import AgentOSPaths, load_config
from .session_hub import CodexRunner
from .speech import capabilities as speech_capabilities


def run(paths: AgentOSPaths) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    checks.append({"id": "home_exists", "ok": paths.home.is_dir()})
    checks.append({"id": "config_valid", "ok": _config_valid(paths)})
    checks.append({"id": "secret_dir_private", "ok": _private_directory(paths.secrets)})
    try:
        config = load_config(paths)
        runner = CodexRunner(config)
        checks.append(
            {
                "id": "codex_executable",
                "ok": True,
                "available": runner.capabilities()["codex"],
            }
        )
        checks.append(
            {
                "id": "telegram_owner_allowlist",
                "ok": not config.get("telegram_session_hub", {}).get("enabled")
                or bool(config.get("telegram_session_hub", {}).get("owner_ids")),
            }
        )
        speech = speech_capabilities(config)
        checks.append(
            {
                "id": "speech_optional",
                "ok": True,
                "available": bool(
                    speech["local_whisper"]
                    or (speech["openai_sdk"] and speech["openai_key_configured"])
                ),
            }
        )
    except (OSError, ValueError):
        checks.append({"id": "codex_executable", "ok": False})
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
