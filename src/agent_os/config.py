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
        from .overlay import validate_roots

        preferred = os.environ.get("AGENTOS_USER_HOME")
        legacy = os.environ.get("AGENT_OS_HOME")
        if (
            home is None
            and preferred
            and legacy
            and Path(preferred).expanduser().resolve()
            != Path(legacy).expanduser().resolve()
        ):
            raise ValueError("ambiguous_user_home_environment")
        root = (
            (home or Path(preferred or legacy or "~/.agentos-user"))
            .expanduser()
            .absolute()
        )
        validate_roots(root)
        root = root.resolve()
        return cls(root, root / "config.json", root / "state", root / "secrets")

    def initialize(self) -> None:
        from .overlay import SCHEMA, validate_roots
        from .safeio import atomic_json, read_json, within

        validate_roots(self.home)
        for rel in (
            "config.json",
            "state",
            "secrets",
            "overlay.json",
            "knowledge",
            "preferences",
            "extensions",
            "projects",
        ):
            within(self.home, rel)
        overlay_path = self.home / "overlay.json"
        if overlay_path.exists() and read_json(overlay_path).get("schema") != SCHEMA:
            raise ValueError("unsupported_overlay_schema")
        self.home.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state.mkdir(mode=0o700, exist_ok=True)
        self.secrets.mkdir(mode=0o700, exist_ok=True)
        self.home.chmod(0o700)
        self.state.chmod(0o700)
        self.secrets.chmod(0o700)
        if not overlay_path.exists():
            atomic_json(
                overlay_path,
                {
                    "schema": SCHEMA,
                    "version": "1.0.0",
                    "overlay_id": "local-user",
                    "host_binding": None,
                    "secrets_included": False,
                },
            )
        for rel in ("knowledge", "preferences", "extensions", "projects"):
            (self.home / rel).mkdir(mode=0o700, exist_ok=True)
        if not self.config.exists():
            self.config.write_text(
                json.dumps(default_config(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self.config.chmod(0o600)


def default_config() -> dict[str, object]:
    return {
        "schema": "agent-os.community-config/v5",
        "name": "My AgentOS",
        "governance": {
            # Applies to project changes only; not a prompt-time/hook requirement.
            "intake_required": True,
            "closeout_required": True,
            "external_authority_granted": False,
        },
        "telegram_business": {"enabled": False, "onboarding": "telegram_qr"},
        "mcp": {"transport": "stdio", "allow_arbitrary_shell": False},
        "update_advisory": {
            "enabled": True,
            "interval_seconds": 172800,
            "failure_retry_seconds": 21600,
            "automatic_install": False,
        },
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
    from .safeio import read_json, within

    raw = read_json(within(paths.home, "config.json", allow_missing=False))
    if not isinstance(raw, dict):
        raise ValueError("config_must_be_object")  # noqa: TRY004 - invalid stored JSON
    if raw.get("schema") not in {
        "agent-os.community-config/v1",
        "agent-os.community-config/v2",
        "agent-os.community-config/v3",
        "agent-os.community-config/v4",
        "agent-os.community-config/v5",
    }:
        raise ValueError("unsupported_config_schema")
    upgraded = _merge(default_config(), raw)
    upgraded["schema"] = "agent-os.community-config/v5"
    # These are architectural invariants, not user-disable switches.
    if (
        upgraded.get("governance", {}).get("intake_required") is not True
        or upgraded.get("governance", {}).get("closeout_required") is not True
    ):
        raise ValueError("governance_cannot_be_disabled")
    return upgraded


def _merge(
    defaults: dict[str, object], supplied: dict[str, object]
) -> dict[str, object]:
    result = dict(defaults)
    for key, value in supplied.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = value
    return result
