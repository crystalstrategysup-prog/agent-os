"""Safe local configuration primitives for the community edition."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AgentOSPaths:
    home: Path
    config: Path
    state: Path
    secrets: Path

    @classmethod
    def discover(cls, home: Path | None = None) -> AgentOSPaths:
        root = (home or Path(os.environ.get("AGENT_OS_HOME", "~/.agent-os"))).expanduser()
        return cls(root, root / "config.json", root / "state", root / "secrets")

    def initialize(self) -> None:
        self.home.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state.mkdir(mode=0o700, exist_ok=True)
        self.secrets.mkdir(mode=0o700, exist_ok=True)
        self.home.chmod(0o700)
        self.state.chmod(0o700)
        self.secrets.chmod(0o700)
        if not self.config.exists():
            self.config.write_text(
                json.dumps(default_config(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self.config.chmod(0o600)


def default_config() -> dict[str, object]:
    return {
        "schema": "agent-os.community-config/v3",
        "name": "My AgentOS",
        "telegram_business": {"enabled": False, "onboarding": "telegram_qr"},
        "mcp": {"transport": "stdio", "allow_arbitrary_shell": False},
        "model_routing": {
            "enabled": True,
            "delegate_by_default": False,
            "profiles": {
                "coordinator": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
                "worker": {"model": "gpt-5.6-terra", "reasoning_effort": "medium"},
                "fast": {"model": "gpt-5.6-luna", "reasoning_effort": "low"},
                "reviewer": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
                "critical": {"model": "gpt-6-astra", "reasoning_effort": "high"},
            },
        },
        "codex": {
            "executable": "codex",
            "home": "",
            "session_roots": [],
            "default_workspace": str(Path.home()),
            "allowed_workspaces": [str(Path.home())],
            "turn_timeout_seconds": 1800,
        },
        "telegram_session_hub": {
            "enabled": False,
            "owner_ids": [],
            "bot_token_env": "TELEGRAM_BOT_TOKEN",
            "poll_timeout_seconds": 25,
            "max_sessions": 20,
            "speech": {
                "provider": "auto",
                "local_whisper_executable": "whisper",
                "openai_api_key_env": "OPENAI_API_KEY",
                "openai_model": "gpt-transcribe",
                "timeout_seconds": 600,
            },
        },
    }


def load_config(paths: AgentOSPaths) -> dict[str, object]:
    raw = json.loads(paths.config.read_text(encoding="utf-8"))
    if raw.get("schema") not in {
        "agent-os.community-config/v1",
        "agent-os.community-config/v2",
        "agent-os.community-config/v3",
    }:
        raise ValueError("unsupported_config_schema")
    upgraded = _merge(default_config(), raw)
    upgraded["schema"] = "agent-os.community-config/v3"
    return upgraded


def _merge(defaults: dict[str, object], supplied: dict[str, object]) -> dict[str, object]:
    result = dict(defaults)
    for key, value in supplied.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = value
    return result
