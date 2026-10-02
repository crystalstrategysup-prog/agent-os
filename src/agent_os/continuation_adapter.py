"""Pure provider binding contract. No I/O, authentication, send or receipt grant."""
from __future__ import annotations

from . import continuation as c
from .safeio import GateError, nonempty


def binding(value: dict, item: dict) -> dict:
    keys = {"schema", "provider", "target_owner", "target_id", "workstream_id", "parent_owner"}
    if not isinstance(value, dict) or set(value) != keys or value.get("schema") != "agentos.continuation-adapter-binding/v1":
        raise GateError("invalid_continuation_adapter_binding")
    for key in keys:
        nonempty(value[key], key, 300)
    if (value["target_owner"] != item["continuation"]["next_owner"]
            or value["parent_owner"] != item["continuation"]["parent_owner"]):
        raise GateError("adapter_owner_binding_mismatch")
    return dict(value)


def request(item: dict, mapping: dict) -> dict:
    mapping = binding(mapping, item)
    if item["schema"] != c.ITEM_SCHEMA or item["state"] != "DELIVERY_UNKNOWN":
        raise GateError("committed_v2_unknown_required")
    return {"schema": "agentos.continuation-provider-request/v1", "provider": mapping["provider"],
            "target_id": mapping["target_id"], "workstream_id": mapping["workstream_id"],
            "target_owner": mapping["target_owner"], "parent_owner": mapping["parent_owner"],
            "operation_key": item["attempt_id"], "delivery_generation": item["delivery_generation"],
            "delivery_nonce": item["delivery_nonce"], "delivery_started_at": item["delivery_started_at"],
            "ledger_id": item["id"], "ledger_revision": item["revision"],
            "target_authority_proven": False, "provider_invocation_performed": False}


def check_receipt(item: dict, mapping: dict, receipt: dict, action: str) -> dict:
    """Pins namespace and checks structure; actual provider provenance is external."""
    mapping = binding(mapping, item)
    request(item, mapping)
    if action not in {"acknowledge", "not-sent"}:
        raise GateError("invalid_adapter_outcome")
    if not isinstance(receipt, dict) or receipt.get("provider") != mapping["provider"]:
        raise GateError("adapter_provider_namespace_mismatch")
    receipt_id = c._check_receipt(item, receipt, action)
    return {"schema": "agentos.continuation-adapter-check/v1", "status": "STRUCTURE_MATCHES",
            "receipt_id": receipt_id, "request": request(item, mapping),
            "external_provenance_proven": False, "delivery_acceptance_proven": False,
            "ledger_transition_performed": False,
            "next": "Authorized real adapter must verify durable provider origin, exact target/call correlation and authority before recording the receipt."}
