"""Optional speech-to-text capability detection and transcription."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def capabilities(config: dict[str, Any]) -> dict[str, Any]:
    section = config.get("telegram_session_hub", {}).get("speech", {})
    local_executable = str(section.get("local_whisper_executable", "whisper"))
    key_env = str(section.get("openai_api_key_env", "OPENAI_API_KEY"))
    try:
        import openai  # noqa: F401

        sdk_available = True
    except ImportError:
        sdk_available = False
    return {
        "provider": section.get("provider", "auto"),
        "local_whisper": shutil.which(local_executable) is not None,
        "openai_sdk": sdk_available,
        "openai_key_configured": bool(os.environ.get(key_env)),
        "openai_model": section.get("openai_model", "gpt-transcribe"),
        "setup": [
            "Local: install whisper and FFmpeg; no transcription API key is required.",
            "OpenAI: pip install 'crystal-agent-os[speech]' and set the configured API-key environment variable outside Telegram.",
        ],
    }


def transcribe(path: Path, config: dict[str, Any]) -> str:
    section = config.get("telegram_session_hub", {}).get("speech", {})
    requested = str(section.get("provider", "auto"))
    ready = capabilities(config)
    if requested in {"auto", "local"} and ready["local_whisper"]:
        return _local_whisper(path, section)
    if requested in {"auto", "openai"} and ready["openai_sdk"] and ready["openai_key_configured"]:
        return _openai(path, section)
    raise RuntimeError("speech_not_configured")


def _local_whisper(path: Path, section: dict[str, Any]) -> str:
    executable = str(section.get("local_whisper_executable", "whisper"))
    with tempfile.TemporaryDirectory(prefix="agentos-stt-") as directory:
        completed = subprocess.run(
            [executable, str(path), "--output_format", "txt", "--output_dir", directory],
            capture_output=True,
            text=True,
            timeout=int(section.get("timeout_seconds", 600)),
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("local_whisper_failed")
        result = Path(directory) / f"{path.stem}.txt"
        if not result.is_file():
            raise RuntimeError("local_whisper_output_missing")
        return result.read_text(encoding="utf-8").strip()


def _openai(path: Path, section: dict[str, Any]) -> str:
    from openai import OpenAI

    key_env = str(section.get("openai_api_key_env", "OPENAI_API_KEY"))
    client = OpenAI(api_key=os.environ[key_env])
    with path.open("rb") as audio:
        result = client.audio.transcriptions.create(
            model=str(section.get("openai_model", "gpt-transcribe")), file=audio
        )
    return str(result.text).strip()
