"""A tiny dependency-free MCP stdio server for safe AgentOS tools."""

from __future__ import annotations

import json
import sys
from typing import Any

from .config import AgentOSPaths
from .doctor import run as doctor_run
from .onboarding import public_plan
from .tasks import normalize_task

PROTOCOL_VERSION = "2025-06-18"

TOOLS = [
    {
        "name": "agentos_get_telegram_setup_plan",
        "description": "Return the secret-free Telegram Business onboarding plan.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "agentos_normalize_task",
        "description": "Normalize a bounded task request without executing it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string", "minLength": 1, "maxLength": 2000},
                "target": {"type": "string", "enum": ["local", "remote", "custom"]},
                "risk": {"type": "string", "enum": ["R0", "R1", "R2", "R3", "R4", "R5"]},
            },
            "required": ["objective"],
            "additionalProperties": False,
        },
    },
    {
        "name": "agentos_doctor",
        "description": "Run non-secret checks against the local AgentOS home.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def response(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "crystal-agent-os", "version": "0.1.0"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params") or {}
        result = _call(str(params.get("name") or ""), params.get("arguments") or {})
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if name == "agentos_get_telegram_setup_plan":
            value = public_plan()
        elif name == "agentos_normalize_task":
            value = normalize_task(
                str(arguments.get("objective") or ""),
                str(arguments.get("target") or "local"),
                str(arguments.get("risk") or "R0"),
            ).as_dict()
        elif name == "agentos_doctor":
            value = doctor_run(AgentOSPaths.discover())
        else:
            raise ValueError("unknown_tool")
    except (OSError, TypeError, ValueError) as exc:
        return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
    return {
        "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
        "structuredContent": value,
    }


def main() -> int:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            outgoing = response(message)
        except (json.JSONDecodeError, TypeError, ValueError):
            outgoing = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        if outgoing is not None:
            print(json.dumps(outgoing, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
