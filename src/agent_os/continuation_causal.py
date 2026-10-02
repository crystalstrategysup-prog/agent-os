"""Cloud-only v3 causal receipt. Proves input receipt, never successful work."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .safeio import GateError, _parse_json, digest, nonempty, sha

ITEM_SCHEMA = 'agentos.continuation-item/v3'
RECEIPT_SCHEMA = 'agentos.continuation-delivery-receipt/v3'
REQUEST_SCHEMA = 'agentos.cloud-causal-request/v1'
ACK_SCHEMA = 'agentos.cloud-receipt-ack/v1'
PROVIDER = 'cloud_threads'
SCOPE = 'received_only'
KIND = 'causal_challenge'
TERMINAL = {'RECEIVED', 'RECEIVED_REFUSED'}
ACK_PREFIX = 'AGENTOS_CLOUD_ACK_V1\n'
REQUEST_PREFIX = 'AGENTOS_CLOUD_CHALLENGE_V1\n'
CONTRACT = json.loads((Path(__file__).parent / 'resources/contracts/cloud-threads-causal-v1.json').read_text())
CONTRACT_SHA256 = digest(CONTRACT)
ACK_INSTRUCTION = ('Emit one standalone assistant message beginning AGENTOS_CLOUD_ACK_V1 followed by a JSON object '
                   'with schema=agentos.cloud-receipt-ack/v1, acceptance_scope=received_only, status=received '
                   'or received_refused, ledger_id, operation_key, delivery_generation, delivery_nonce, '
                   'request_sha256, target_thread_id and workstream_id echoed exactly from this challenge. '
                   'received_refused additionally requires refusal_reason. This acknowledges receipt of this '
                   'input only, never successful execution or acceptance of work. Do not quote or fence the ACK.')


def _hash(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(x in '0123456789abcdef' for x in value)


def pin(value: dict, item: dict) -> dict:
    keys = {'provider', 'contract_sha256', 'parent_owner', 'target_owner', 'target_thread_id', 'workstream_id'}
    if not isinstance(value, dict) or set(value) != keys:
        raise GateError('causal_provider_pin_required')
    for key in keys:
        nonempty(value[key], 'causal_pin_' + key, 300)
    if (value['provider'] != PROVIDER or value['contract_sha256'] != CONTRACT_SHA256
            or value['parent_owner'] != item['continuation']['parent_owner']
            or value['target_owner'] != item['continuation']['next_owner']):
        raise GateError('causal_provider_pin_mismatch')
    return dict(value)


def make_request(item: dict, delivery: dict) -> dict:
    if not isinstance(delivery, dict) or set(delivery) != {'pin', 'payload'}:
        raise GateError('explicit_causal_delivery_required')
    bound = pin(delivery['pin'], item)
    payload = nonempty(delivery['payload'], 'causal_payload', 16000)
    if len(payload.encode()) > 16000:
        raise GateError('causal_payload_byte_limit')
    challenge = {'schema': REQUEST_SCHEMA, 'provider': PROVIDER, 'contract_sha256': CONTRACT_SHA256,
                 'mapping_digest': digest(bound), 'target_thread_id': bound['target_thread_id'],
                 'workstream_id': bound['workstream_id'], 'ledger_id': item['id'],
                 'operation_key': item['attempt_id'], 'delivery_generation': item['delivery_generation'],
                 'delivery_nonce': item['delivery_nonce'], 'ledger_revision_at_begin': item['revision'] + 1,
                 'payload': payload, 'payload_sha256': sha(payload.encode())}
    request_hash = digest(challenge)
    wire = {'schema': REQUEST_SCHEMA, 'challenge': challenge, 'request_sha256': request_hash,
            'ack_instruction': ACK_INSTRUCTION}
    return {'schema': REQUEST_SCHEMA, 'pin': bound, 'challenge': challenge,
            'request_sha256': request_hash,
            'text': REQUEST_PREFIX + json.dumps(wire, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}


def validate_request(item: dict) -> dict:
    value = item.get('delivery_request')
    if not isinstance(value, dict) or set(value) != {'schema', 'pin', 'challenge', 'request_sha256', 'text'}:
        raise GateError('causal_committed_request_required')
    challenge = value['challenge']
    admitted_revision = challenge.get('ledger_revision_at_begin') if isinstance(challenge, dict) else None
    if (isinstance(admitted_revision, bool) or not isinstance(admitted_revision, int)
            or not 1 <= admitted_revision <= item['revision']):
        raise GateError('causal_request_revision_invalid')
    expected = make_request({**item, 'revision': admitted_revision - 1},
                            {'pin': value['pin'], 'payload': challenge.get('payload')})
    if value != expected:
        raise GateError('causal_committed_request_binding_mismatch')
    return value


def ack(request: dict, status: str = 'received', reason: str | None = None) -> dict:
    challenge = request['challenge']
    value = {'schema': ACK_SCHEMA, 'acceptance_scope': SCOPE, 'status': status,
             **{k: challenge[k] for k in ('ledger_id', 'operation_key', 'delivery_generation',
                                         'delivery_nonce', 'target_thread_id', 'workstream_id')},
             'request_sha256': request['request_sha256']}
    if status == 'received_refused':
        value['refusal_reason'] = reason
    return value


def parse_ack(text: str, request: dict) -> dict:
    if not isinstance(text, str) or not text.startswith(ACK_PREFIX) or len(text.encode()) > 8192:
        raise GateError('explicit_standalone_cloud_ack_required')
    try:
        value = _parse_json(text[len(ACK_PREFIX):])
    except (ValueError, UnicodeError) as exc:
        raise GateError('complete_cloud_ack_required') from exc
    validate_ack(value, request)
    return value


def validate_ack(value: dict, request: dict) -> None:
    if not isinstance(value, dict) or value.get('status') not in {'received', 'received_refused'}:
        raise GateError('received_only_ack_status_required')
    if type(value.get('delivery_generation')) is not int:
        raise GateError('causal_ack_integer_generation_required')
    reason = value.get('refusal_reason')
    if value['status'] == 'received_refused':
        nonempty(reason, 'refusal_reason', 1000)
    if value != ack(request, value['status'], reason):
        raise GateError('causal_ack_challenge_mismatch')


def receipt_key(receipt: dict) -> str:
    return digest({'provider': receipt['provider'], 'target_thread_id': receipt['target_thread_id'],
                   'turn_id': receipt['turn_id'], 'user_event_id': receipt['user_event_id'],
                   'assistant_event_id': receipt['assistant_event_id']})


def receipt_shape(receipt: dict) -> None:
    keys = {'schema', 'evidence_kind', 'acceptance_scope', 'provider', 'contract_sha256', 'mapping_digest',
            'ledger_id', 'attempt_id', 'delivery_generation', 'delivery_nonce', 'request_sha256',
            'target_thread_id', 'workstream_id', 'target_owner', 'turn_id', 'user_event_id',
            'assistant_event_id', 'user_text_sha256', 'assistant_text_sha256', 'assistant_ack', 'status', 'checked_at'}
    if (not isinstance(receipt, dict) or set(receipt) != keys or receipt['schema'] != RECEIPT_SCHEMA
            or receipt['evidence_kind'] != KIND or receipt['acceptance_scope'] != SCOPE
            or receipt['provider'] != PROVIDER or receipt['contract_sha256'] != CONTRACT_SHA256
            or receipt['status'] not in TERMINAL):
        raise GateError('causal_received_only_receipt_required')
    generation = receipt['delivery_generation']
    if isinstance(generation, bool) or not isinstance(generation, int) or not 1 <= generation <= 128:
        raise GateError('causal_generation_invalid')
    for key in keys - {'delivery_generation', 'assistant_ack'}:
        nonempty(receipt[key], 'causal_receipt_' + key, 300)
    for key in ('contract_sha256', 'mapping_digest', 'request_sha256', 'user_text_sha256', 'assistant_text_sha256'):
        if not _hash(receipt[key]):
            raise GateError('causal_evidence_digest_invalid')
    if receipt['user_event_id'] == receipt['assistant_event_id']:
        raise GateError('distinct_causal_provider_events_required')


def check_receipt(item: dict, receipt: dict) -> str:
    receipt_shape(receipt)
    request = validate_request(item)
    bound = request['pin']
    expected = {'ledger_id': item['id'], 'attempt_id': item['attempt_id'],
                'delivery_generation': item['delivery_generation'], 'delivery_nonce': item['delivery_nonce'],
                'target_owner': bound['target_owner'], 'target_thread_id': bound['target_thread_id'],
                'workstream_id': bound['workstream_id'], 'mapping_digest': digest(bound),
                'request_sha256': request['request_sha256'], 'user_text_sha256': sha(request['text'].encode())}
    if any(receipt[k] != value for k, value in expected.items()):
        raise GateError('causal_current_attempt_mismatch')
    validate_ack(receipt['assistant_ack'], request)
    state = 'RECEIVED' if receipt['assistant_ack']['status'] == 'received' else 'RECEIVED_REFUSED'
    if receipt['status'] != state:
        raise GateError('causal_refused_is_not_work_acceptance')
    key = receipt_key(receipt)
    if key in item['consumed_receipt_ids']:
        raise GateError('causal_receipt_already_consumed')
    try:
        checked = datetime.fromisoformat(receipt['checked_at'])
        started = datetime.fromisoformat(item['delivery_started_at'])
    except ValueError as exc:
        raise GateError('causal_observer_time_invalid') from exc
    if checked.tzinfo is None or not started <= checked <= datetime.now(UTC) + timedelta(minutes=5):
        raise GateError('causal_observer_time_invalid')
    return key
