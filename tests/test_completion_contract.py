"""P1 relational/shape contract tests, not host acceptance."""

import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

from agent_os.continuation_adapter import validate_completion_freshness
from agent_os.safeio import GateError


@pytest.mark.parametrize(
    "changes",
    [
        {"capability_checked_at": None},
        {"capability_checked_at": True},
        {"capability_checked_at": 101},
        {"capability_expires_at": 100},
        {"capability_expires_at": 401},
        {"policy_expires_at": 100},
        {"policy_scope_hash": "c" * 64},
        {"capability_snapshot_hash": "c" * 64},
        {"checked_at": 99},
    ],
)
def test_admission_freshness_and_current_scope(changes):
    value = {
        "capability_checked_at": 90,
        "capability_expires_at": 190,
        "policy_expires_at": 200,
        "checked_at": 100,
        "capability_snapshot_hash": "a" * 64,
        "policy_scope_hash": "b" * 64,
    }
    validate_completion_freshness(value, "a" * 64, "b" * 64, 100)
    with pytest.raises(GateError):
        validate_completion_freshness({**value, **changes}, "a" * 64, "b" * 64, 100)


def test_versioned_event_payload_and_schema_mirror():
    root = Path(__file__).resolve().parents[1]
    source = root / "schemas/completion-v1.schema.json"
    assert (
        source.read_bytes()
        == (
            root / "src/agent_os/resources/schemas/completion-v1.schema.json"
        ).read_bytes()
    )
    validator = jsonschema.Draft202012Validator(json.loads(source.read_text()))
    event = {
        "schema": "agentos.completion-event/v1",
        "event_id": "event-demo-001",
        "kind": "TURN_FINISHED",
        "generation": 1,
        "causal_sequence": 1,
        "observed_at": 100,
        "payload": {
            "turn_id": "turn-demo-001",
            "executor_ref": "executor-demo-a",
            "status": "COMPLETED",
        },
    }
    validator.validate(event)
    for field in ("turn_id", "executor_ref", "status"):
        invalid = deepcopy(event)
        invalid["payload"].pop(field)
        assert list(validator.iter_errors(invalid))
