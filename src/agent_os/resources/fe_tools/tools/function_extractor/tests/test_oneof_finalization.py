"""Bounded schema behavior and maintained Telegram adapter; no target effects."""
import hashlib
import json
from pathlib import Path

import pytest

from tools.function_extractor import contract_engine as ce

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


def test_real_http_success_fixture_matches_selected_message_contract():
    # Load only the public synthetic socket adapter, never a product module.
    import importlib.util
    path = Path(__file__).resolve().parents[3] / "backend/tools/route_probe_avl.py"
    spec = importlib.util.spec_from_file_location("fe_public_wire_fixture", path)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    status, wire = adapter._HttpBytes.wire("success")
    headers, raw = wire.split(b"\r\n\r\n", 1)
    assert status == 200 and (b"Content-Length: " + str(len(raw)).encode()) in headers
    response = json.loads(raw)
    rules = json.loads((CONTRACTS / "telegram_sendmessage.rules.json").read_text())["rules"]
    schema = next(r["constraint"] for r in rules if r["rule_id"] == "telegram.response.ok")
    assert ce.validate_schema(response, schema)["status"] == "VALID"
    assert response["result"]["chat"] == {"id": adapter.GROUP_ID, "type": "supergroup"}
    del response["result"]["chat"]
    assert ce.validate_schema(response, schema)["status"] == "INVALID"


@pytest.mark.parametrize("value,schema,expected", [
    ("x", {"oneOf": [{"type": "string"}, {"type": "integer"}]}, "VALID"),
    (3, {"oneOf": [{"type": "string"}, {"type": "integer"}]}, "VALID"),
    (True, {"oneOf": [{"type": "string"}, {"type": "integer"}]}, "INVALID"),
    (1.0, {"oneOf": [{"type": "boolean"}, {"type": "integer"}]}, "VALID"),
    (1, {"oneOf": [{"const": True}, {"type": "string"}]}, "INVALID"),
    ("x", {"oneOf": [{"type": "string"}, {"enum": ["x"]}]}, "INVALID"),
    (None, {"oneOf": [False, {"type": "null"}]}, "VALID"),
    ("x", {"oneOf": [{}, False]}, "VALID"),
    ("x", {"oneOf": [{}, {}]}, "INVALID"),
    ("", {"type": "string", "minLength": 1, "oneOf": [True]}, "INVALID"),
    ("x", {"oneOf": []}, "UNKNOWN"),
    ("x", {"oneOf": [True] * 9}, "UNKNOWN"),
    ("x", {"oneOf": {}}, "UNKNOWN"),
    ("x", {"oneOf": [True, {"pattern": "x"}]}, "UNKNOWN"),
    ("x", {"oneOf": [{"$ref": "https://example.invalid/schema"}]}, "UNKNOWN"),
    ("x", {"oneOf": [{"$ref": "#/$defs/missing"}]}, "UNKNOWN"),
    ("x", {"$defs": {"cycle": {"$ref": "#/$defs/cycle"}},
           "oneOf": [True, {"$ref": "#/$defs/cycle"}]}, "UNKNOWN"),
])
def test_exact_one_semantics_and_fail_closed_support(value, schema, expected):
    assert ce.validate_schema(value, schema)["status"] == expected


def test_local_refs_and_parent_constraints_are_retained():
    schema = {"$defs": {"number": {"type": "integer", "minimum": 2}},
              "oneOf": [{"$ref": "#/$defs/number"}, {"type": "string"}]}
    for value, expected in [(2, "VALID"), ("x", "VALID"), (1, "INVALID"), (True, "INVALID")]:
        assert ce.validate_schema(value, schema)["status"] == expected


def test_deep_and_evaluation_work_exhaustion_remain_unknown():
    deep = {"type": "string"}
    for _ in range(20):
        deep = {"oneOf": [deep]}
    assert ce.validate_schema("x", deep)["status"] == "UNKNOWN"
    repeated = {"type": "array", "items": {"oneOf": [{"type": "integer"}] * 8}}
    assert ce.validate_schema([1] * 8000, repeated)["status"] == "UNKNOWN"
    with pytest.raises(ValueError):
        ce._schema_check({"oneOf": [True, False]}, budget=[1])
    with pytest.raises(ValueError):
        ce._schema_errors(1, {"oneOf": [True, False]}, {}, budget=[1])


@pytest.mark.parametrize("value,expected", [
    ({"ok": True, "result": {"message_id": 3, "chat": {}}}, "VALID"),
    ({"ok": False, "error_code": 429}, "VALID"),
    ({"ok": False, "error_code": 400, "description": "synthetic"}, "VALID"),
    ({"ok": False}, "INVALID"),
    ({"ok": False, "error_code": True}, "INVALID"),
    ({"ok": False, "error_code": 429, "parameters": {"retry_after": True}}, "INVALID"),
    ({"ok": True}, "INVALID"),
    ({"ok": True, "result": {"chat": {}}}, "INVALID"),
    ({"ok": True, "result": {"message_id": True, "chat": {}}}, "INVALID"),
    ({"ok": 1, "result": {"message_id": 3, "chat": {}}}, "INVALID"),
])
def test_maintained_selected_telegram_envelope(value, expected):
    rules = json.loads((CONTRACTS / "telegram_sendmessage.rules.json").read_text())["rules"]
    schema = next(r["constraint"] for r in rules if r["rule_id"] == "telegram.response.ok")
    assert ce.validate_schema(value, schema)["status"] == expected


def test_partial_message_success_is_not_full_message_acceptance():
    provenance = json.loads((CONTRACTS / "telegram_sendmessage.provenance.json").read_text())
    assert provenance["official_schema"] is False
    assert provenance["machine_adapter"] is True
    assert provenance["coverage"]["full_message_schema"] is False
    assert provenance["coverage"]["request_applicability"] == "PLAIN_TEXT_ONLY"


def test_maintained_provenance_pins_the_actual_selected_sources():
    provenance = json.loads((CONTRACTS / "telegram_sendmessage.provenance.json").read_text())
    for key, name in [("adapter_sha256", "telegram_sendmessage.rules.json"),
                      ("primary_sha256", "telegram_sendmessage.current-primary.json")]:
        assert provenance[key] == hashlib.sha256((CONTRACTS / name).read_bytes()).hexdigest()
