"""Generate a minimal MCP client entry without exposing credentials."""

from __future__ import annotations

import sys


def client_config() -> dict[str, object]:
    return {
        "mcpServers": {
            "agent-os": {
                "command": sys.executable,
                "args": ["-m", "agent_os.mcp_server"],
                "env": {"AGENT_OS_HOME": "${AGENT_OS_HOME}"},
            }
        }
    }
