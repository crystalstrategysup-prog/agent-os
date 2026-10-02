"""Synthetic v3 core boundaries. No cloud/native delivery is performed."""
from __future__ import annotations

import copy
import json

import pytest
from test_continuation_dispatch import closed, move, queued
from test_foundation import setup as foundation_setup

from agent_os import continuation as c
from agent_os import continuation_causal as v3
from agent_os import continuation_migration as migration
from agent_os.safeio import GateError, atomic_json, digest, filemap, now, sha

setup = foundation_setup


def queued_causal(setup):
    return c.reconcile_causal(setup[1], setup[0], closed(setup))


def mapping():
    return {'provider': v3.PROVIDER, 'contract_sha256': v3.CONTRACT_SHA256,
            'parent_owner': 'parent', 'target_owner': 'independent-reviewer',
            'target_thread_id': 'fixture-cloud-target', 'workstream_id': 'fixture-cloud-workstream'}


def begun(setup):
    item = move(setup[1], queued_causal(setup), 'claim')
    return c.transition(setup[1], item['id'], 'parent', item['revision'], 'begin-delivery',
                        delivery={'pin': mapping(), 'payload': 'Please review exact frozen source.'})


def receipt(item, status='received'):
    request = item['delivery_request']
    assistant = v3.ack(request, status, 'Cannot review this scope.' if status == 'received_refused' else None)
    text = v3.ACK_PREFIX + json.dumps(assistant)
    return {'schema': v3.RECEIPT_SCHEMA, 'evidence_kind': v3.KIND, 'acceptance_scope': v3.SCOPE,
            'provider': v3.PROVIDER, 'contract_sha256': v3.CONTRACT_SHA256,
            'mapping_digest': digest(mapping()), 'ledger_id': item['id'], 'attempt_id': item['attempt_id'],
            'delivery_generation': item['delivery_generation'], 'delivery_nonce': item['delivery_nonce'],
            'request_sha256': request['request_sha256'], 'target_thread_id': mapping()['target_thread_id'],
            'workstream_id': mapping()['workstream_id'], 'target_owner': mapping()['target_owner'],
            'turn_id': 'actual-fixture-turn', 'user_event_id': 'actual-fixture-user',
            'assistant_event_id': 'actual-fixture-assistant', 'user_text_sha256': sha(request['text'].encode()),
            'assistant_text_sha256': sha(text.encode()), 'assistant_ack': assistant,
            'status': 'RECEIVED' if status == 'received' else 'RECEIVED_REFUSED', 'checked_at': now()}


@pytest.mark.parametrize('status', ['received', 'received_refused'])
def test_core_records_received_only_immutable_receipt_without_producer_timestamps(setup, status):
    item = begun(setup)
    original = copy.deepcopy(item['delivery_request'])
    result = move(setup[1], item, 'record-receipt', receipt(item, status))
    assert result['state'] == ('RECEIVED' if status == 'received' else 'RECEIVED_REFUSED')
    assert result['receipt_acceptance_scope'] == 'received_only'
    assert result['delivery_request'] == original and len(result['receipt_history']) == 1
    assert 'user_event_at' not in result['receipt'] and 'later_activity_at' not in result['receipt']
    assert c.read(setup[1], item['id']) == result
    assert c.status(setup[1])['project_completion_proven'] is False
    before = filemap(setup[1])
    with pytest.raises(GateError):
        move(setup[1], result, 'record-receipt', result['receipt'])
    assert filemap(setup[1]) == before


@pytest.mark.parametrize('field', ['ledger_id', 'attempt_id', 'delivery_generation', 'delivery_nonce',
                                  'target_owner', 'target_thread_id', 'workstream_id', 'mapping_digest',
                                  'request_sha256', 'user_text_sha256', 'acceptance_scope', 'schema',
                                  'contract_sha256', 'status'])
def test_wrong_receipt_binding_never_consumes_or_reopens_unknown(setup, field):
    item = begun(setup); value = receipt(item)
    value[field] = 2 if field == 'delivery_generation' else 'wrong'
    before = filemap(setup[1])
    with pytest.raises(GateError):
        move(setup[1], item, 'record-receipt', value)
    assert filemap(setup[1]) == before and c.read(setup[1], item['id'])['state'] == 'DELIVERY_UNKNOWN'


@pytest.mark.parametrize('action', ['claim', 'begin-delivery', 'acknowledge', 'not-sent'])
def test_unknown_v3_has_no_retry_or_timestamp_v2_escape(setup, action):
    item = begun(setup); before = filemap(setup[1])
    with pytest.raises(GateError):
        move(setup[1], item, action)
    assert filemap(setup[1]) == before


def test_exact_request_committed_and_missing_delivery_preserves_claimed(setup):
    item = move(setup[1], queued_causal(setup), 'claim'); before = filemap(setup[1])
    with pytest.raises(GateError, match='explicit_causal_delivery'):
        move(setup[1], item, 'begin-delivery')
    assert filemap(setup[1]) == before
    admitted = c.transition(setup[1], item['id'], 'parent', item['revision'], 'begin-delivery',
                            delivery={'pin': mapping(), 'payload': 'Exact payload'})
    challenge = admitted['delivery_request']['challenge']
    assert challenge['ledger_revision_at_begin'] == admitted['revision']
    assert challenge['payload'] == 'Exact payload' and challenge['payload_sha256'] == sha(b'Exact payload')
    assert len(challenge['delivery_nonce']) == 32 and v3.validate_request(admitted) == admitted['delivery_request']


def test_existing_v2_is_preserved_and_cannot_consume_v3(setup):
    item = queued(setup); before = filemap(setup[1])
    with pytest.raises(GateError, match='existing_noncausal'):
        c.reconcile_causal(setup[1], setup[0], item['identity']['task_id'])
    assert filemap(setup[1]) == before
    with pytest.raises(GateError, match='scope_mismatch'):
        move(setup[1], item, 'record-receipt', {})


@pytest.mark.parametrize('state', ['PENDING', 'CLAIMED', 'DELIVERY_UNKNOWN', 'RECEIVED', 'RECEIVED_REFUSED'])
def test_legacy_migration_cannot_downgrade_any_causal_state(setup, state):
    item = queued_causal(setup) if state in {'PENDING', 'CLAIMED'} else begun(setup)
    if state == 'CLAIMED':
        # Separate synthetic untouched item, before delivery.
        item = move(setup[1], item, 'claim')
    if state in v3.TERMINAL:
        item = move(setup[1], item, 'record-receipt', receipt(item, 'received' if state == 'RECEIVED' else 'received_refused'))
    before = filemap(setup[1])
    with pytest.raises(GateError, match='causal_item_not_legacy'):
        migration.migrate(setup[1], item['id'], 'parent', item['revision'], apply=True)
    assert filemap(setup[1]) == before


def test_terminal_read_revalidates_request_and_receipt_binding(setup):
    item = begun(setup)
    item = move(setup[1], item, 'record-receipt', receipt(item))
    item['receipt']['assistant_ack']['delivery_nonce'] = '0' * 32
    item['receipt_history'][-1] = item['receipt']
    atomic_json(c._path(setup[1], item['id']), item)
    with pytest.raises(GateError, match='challenge_mismatch'):
        c.read(setup[1], item['id'])


@pytest.mark.parametrize('wrap', ['quoted', 'fenced', 'user prose', 'duplicate-key', 'work-status'])
def test_ack_must_be_standalone_complete_exact_received_only(setup, wrap):
    item = begun(setup); request = item['delivery_request']
    text = v3.ACK_PREFIX + json.dumps(v3.ack(request))
    if wrap == 'quoted': text = '> ' + text
    elif wrap == 'fenced': text = '```json\n' + text + '\n```'
    elif wrap == 'user prose': text += '\nWork complete.'
    elif wrap == 'duplicate-key': text = text.replace('"status": "received"', '"status": "received", "status": "received"')
    else: text = text.replace('"received"', '"accepted"')
    with pytest.raises(GateError):
        v3.parse_ack(text, request)


@pytest.mark.parametrize('generation', [True, 1.0, '1'])
def test_ack_generation_requires_exact_integer_type(setup, generation):
    item = begun(setup); request = item['delivery_request']; value = v3.ack(request)
    value['delivery_generation'] = generation
    with pytest.raises(GateError, match='integer_generation'):
        v3.parse_ack(v3.ACK_PREFIX + json.dumps(value), request)
