"""A tiny dependency-free MCP stdio server for safe AgentOS tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .config import AgentOSPaths
from .doctor import run as doctor_run
from .onboarding import public_plan
from .tasks import normalize_task

MCP_CONTRACT = json.loads(
    (Path(__file__).parent / "resources/contracts/mcp-tools-v1.json").read_text(
        encoding="utf-8"
    )
)
if MCP_CONTRACT["serverInfo"]["version"] != __version__:
    raise RuntimeError("mcp_contract_version_mismatch")
PROTOCOL_VERSION = MCP_CONTRACT["protocolVersion"]
TOOLS = MCP_CONTRACT["tools"]


def response(message: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        raise ValueError("message_must_be_object")  # noqa: TRY004 - invalid JSON-RPC payload
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "crystal-agent-os", "version": __version__},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params") or {}
        if not isinstance(params, dict):
            raise ValueError("params_must_be_object")
        result = _call(str(params.get("name") or ""), params.get("arguments", {}))
    elif method == "ping":
        result = {}
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Method not found"},
        }
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if not isinstance(arguments, dict):
            raise TypeError("arguments_must_be_object")
        spec = next((t for t in TOOLS if t["name"] == name), None)
        if not spec:
            raise ValueError("unknown_tool")
        allowed = set(spec["inputSchema"].get("properties", {}))
        if set(arguments) - allowed:
            raise ValueError("unknown_argument")
        required = set(spec["inputSchema"].get("required", []))
        if required - set(arguments):
            raise ValueError("required_argument_missing")
        for key, val in arguments.items():
            rule = spec["inputSchema"]["properties"][key]
            if rule.get("type") == "string":
                if not isinstance(val, str):
                    raise ValueError("argument_type:" + key)
                if len(val) < rule.get("minLength", 0) or len(val) > rule.get(
                    "maxLength", 10000
                ):
                    raise ValueError("argument_length:" + key)
            if rule.get("type") == "array":
                if not isinstance(val, list) or any(
                    not isinstance(x, str) for x in val
                ):
                    raise ValueError("argument_type:" + key)
                if len(val) < rule.get("minItems", 0):
                    raise ValueError("argument_length:" + key)
            if "enum" in rule and val not in rule["enum"]:
                raise ValueError("argument_enum:" + key)
        if name == "agentos_get_telegram_setup_plan":
            value = public_plan()
        elif name == "agentos_normalize_task":
            value = normalize_task(
                str(arguments.get("objective") or ""),
                str(arguments.get("target") or "local"),
                str(arguments.get("risk") or "R0"),
            ).as_dict()
        elif name == "agentos_get_project_entry_plan":
            from .project import QUESTIONS

            value = {
                "schema": "agentos.entry-plan/v1",
                "questions": QUESTIONS,
                "cycle": [
                    "dossier",
                    "roadmap",
                    "stage",
                    "ready",
                    "implementation",
                    "checks",
                    "docs_refresh",
                    "close",
                ],
                "entry_required_every_task": False,
                "entry_required_for": "project_changes",
                "read_only_intake_required": False,
                "native_hooks": "DISABLED",
                "external_authority_granted": False,
            }
        elif name == "agentos_select_documents":
            from .doc_catalog import select

            types, features = arguments.get("types"), arguments.get("features", [])
            if not isinstance(types, list) or not isinstance(features, list):
                raise ValueError("types_and_features_must_be_arrays")
            value = select(types, features)
        elif name == "agentos_get_foundation_status":
            from .overlay import metadata

            value = metadata(AgentOSPaths.discover().home)
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
            outgoing = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
        if outgoing is not None:
            print(
                json.dumps(outgoing, ensure_ascii=False, separators=(",", ":")),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
