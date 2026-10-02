"""Optional owner-wired cloud port. Positive receipt evidence, never work acceptance.

The owner verifies callback origin, persistent immutable records, authority and
target lease. Callbacks use existing cloud tools; fixtures do not prove adoption.
No local lock is held during callback I/O. UNKNOWN never invokes another send.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from . import continuation as c
from . import continuation_causal as causal
from .safeio import (
    GateError,
    atomic_json,
    digest,
    lock,
    nonempty,
    now,
    read_json,
    sha,
    within,
)

MAX_PAGES = 4
PAGE_SIZE = 50
MAX_WITNESSES = 32
IDENTITY = {'provider': causal.PROVIDER, 'contract_sha256': causal.CONTRACT_SHA256,
            'stable_item_ids_and_content': True}


class CloudPort(Protocol):
    """Owner shim normalizes pagination; it must bound its own external calls."""
    identity: dict

    def send_message(self, thread_id: str, message: str) -> dict: ...

    def read(self, thread_id: str, *, cursor: str | None, limit: int) -> dict: ...


class CloudProvider:
    def __init__(self, port: CloudPort, mapping: dict, *,
                 verify_authority: Callable[[str, dict], None]):
        if port.identity != IDENTITY or not callable(verify_authority):
            raise GateError('verified_cloud_port_and_owner_lease_required')
        self.port, self.mapping, self.verify_authority = port, dict(mapping), verify_authority

    def pin(self, item: dict) -> dict:
        if self.port.identity != IDENTITY:
            raise GateError('cloud_port_contract_changed')
        bound = causal.pin(self.mapping, item)
        if item.get('delivery_request') is not None and item['delivery_request']['pin'] != bound:
            raise GateError('cloud_committed_pin_changed_no_resend')
        return bound

    def authorize(self, phase: str, item: dict) -> dict:
        bound = self.pin(item)
        self.verify_authority(phase, dict(bound))
        if self.pin(item) != bound:
            raise GateError('cloud_authorized_pin_changed')
        return bound

    def observations(self, item: dict) -> dict:
        bound = self.authorize('read', item)
        request = causal.validate_request(item)
        observations, identities, cursors = {}, {}, set()
        cursor = None
        for _ in range(MAX_PAGES):
            page = self.port.read(bound['target_thread_id'], cursor=cursor, limit=PAGE_SIZE)
            if (not isinstance(page, dict) or page.get('threadId', bound['target_thread_id']) != bound['target_thread_id']
                    or page.get('truncated', False) is not False or page.get('partial', False) is not False):
                raise GateError('complete_selected_cloud_page_required')
            rows = page.get('items')
            if not isinstance(rows, list) or len(rows) > PAGE_SIZE:
                raise GateError('bounded_cloud_items_required')
            for row in rows:
                if not isinstance(row, dict):
                    raise GateError('cloud_item_object_required')
                event_id = nonempty(row.get('id'), 'cloud_event_id', 300)
                turn_id = nonempty(row.get('turnId'), 'cloud_turn_id', 300)
                role, text = row.get('role'), row.get('text')
                if not isinstance(role, str) or not isinstance(text, str):
                    raise GateError('complete_cloud_identity_and_text_required')
                if len(text.encode()) > 65536:
                    raise GateError('bounded_cloud_item_text_required')
                fingerprint = digest({'turn_id': turn_id, 'role': role, 'text': text,
                                      'truncated': row.get('truncated', False), 'partial': row.get('partial', False)})
                if event_id in identities and identities[event_id] != fingerprint:
                    raise GateError('cloud_item_identity_mutated')
                identities[event_id] = fingerprint
                if row.get('truncated', False) is not False or row.get('partial', False) is not False:
                    # A partial matching record cannot be a complete witness.
                    if text == request['text'] or text.startswith(causal.ACK_PREFIX):
                        raise GateError('complete_cloud_causal_witness_required')
                    continue
                witness = {'id': event_id, 'turn_id': turn_id, 'role': role, 'text_sha256': sha(text.encode())}
                if role == 'user' and text == request['text']:
                    observations[event_id] = witness
                elif role == 'assistant' and text.startswith(causal.ACK_PREFIX):
                    try:
                        witness['ack'] = causal.parse_ack(text, request)
                    except GateError:
                        # Invalid/stale ACK never qualifies as activity evidence.
                        continue
                    observations[event_id] = witness
            cursor = page.get('nextCursor')
            if cursor is None:
                break
            nonempty(cursor, 'cloud_cursor', 2000)
            if cursor in cursors:
                raise GateError('cloud_pagination_cycle')
            cursors.add(cursor)
        if len(observations) > MAX_WITNESSES:
            raise GateError('cloud_causal_witness_limit')
        return {'witnesses': observations, 'observed_identities': identities}


def _lock_path(home: Path, item_id: str) -> Path:
    c._path(home, item_id)
    return within(home, f'state/continuation-cloud/{item_id}.lock')


def _intent_path(home: Path, item: dict) -> Path:
    return within(home, f"state/continuation-cloud/{item['id']}/{item['delivery_generation']}.json")


def _intent(item: dict) -> dict:
    request = causal.validate_request(item)
    return {'schema': 'agentos.cloud-causal-intent/v1', 'item_id': item['id'],
            'request_sha256': request['request_sha256'], 'pin': request['pin'],
            'delivery_generation': item['delivery_generation'], 'delivery_nonce': item['delivery_nonce'],
            'state': 'MAY_HAVE_BEEN_SENT', 'actual_turn_id': None, 'response_observed': False,
            'blocked_reason': None, 'witnesses': {}}


def _load_intent(home: Path, item: dict) -> dict:
    path = _intent_path(home, item)
    expected = _intent(item)
    if not path.exists():
        # The core request is enough to query after intent persistence loss.
        # It never licenses another send.
        return expected
    value = read_json(path)
    if not isinstance(value, dict) or set(value) != set(expected):
        raise GateError('cloud_intent_shape_changed')
    for key in ('schema', 'item_id', 'request_sha256', 'pin', 'delivery_generation', 'delivery_nonce', 'state'):
        if value[key] != expected[key]:
            raise GateError('cloud_intent_binding_changed')
    if value['actual_turn_id'] is not None:
        nonempty(value['actual_turn_id'], 'cloud_response_turn', 300)
    if not isinstance(value['response_observed'], bool) or not isinstance(value['witnesses'], dict):
        raise GateError('cloud_intent_evidence_invalid')
    if len(value['witnesses']) > MAX_WITNESSES:
        raise GateError('cloud_causal_witness_limit')
    for event_id, witness in value['witnesses'].items():
        keys = {'id', 'turn_id', 'role', 'text_sha256'}
        if witness.get('role') == 'assistant':
            keys.add('ack')
            causal.validate_ack(witness.get('ack'), item['delivery_request'])
        if (set(witness) != keys or witness['id'] != event_id or witness['role'] not in {'user', 'assistant'}
                or not causal._hash(witness['text_sha256'])):
            raise GateError('cloud_cached_witness_invalid')
        nonempty(event_id, 'cached_event_id', 300)
        nonempty(witness['turn_id'], 'cached_turn_id', 300)
        if witness['role'] == 'user' and witness['text_sha256'] != sha(item['delivery_request']['text'].encode()):
            raise GateError('cloud_cached_user_mismatch')
    return value


def _result(item: dict, reason: str) -> dict:
    return {'state': item['state'], 'item_id': item['id'], 'revision': item['revision'], 'reason': reason,
            'acceptance_scope': causal.SCOPE, 'resend_permitted': False,
            'work_acceptance_proven': False, 'project_completion_proven': False}


def _receipt(item: dict, intent: dict) -> dict | None:
    if intent['blocked_reason']:
        return None
    request = causal.validate_request(item)
    users = [w for w in intent['witnesses'].values() if w['role'] == 'user']
    assistants = [w for w in intent['witnesses'].values() if w['role'] == 'assistant']
    if len(users) > 1 or len(assistants) > 1:
        raise GateError('ambiguous_cloud_causal_pair')
    if not users or not assistants:
        return None
    user, assistant = users[0], assistants[0]
    if (user['id'] == assistant['id'] or user['turn_id'] != assistant['turn_id']
            or (intent['actual_turn_id'] is not None and intent['actual_turn_id'] != user['turn_id'])):
        raise GateError('cloud_same_actual_turn_required')
    bound = request['pin']
    return {'schema': causal.RECEIPT_SCHEMA, 'evidence_kind': causal.KIND, 'acceptance_scope': causal.SCOPE,
            'provider': causal.PROVIDER, 'contract_sha256': causal.CONTRACT_SHA256,
            'mapping_digest': digest(bound), 'ledger_id': item['id'], 'attempt_id': item['attempt_id'],
            'delivery_generation': item['delivery_generation'], 'delivery_nonce': item['delivery_nonce'],
            'request_sha256': request['request_sha256'], 'target_thread_id': bound['target_thread_id'],
            'workstream_id': bound['workstream_id'], 'target_owner': bound['target_owner'],
            'turn_id': user['turn_id'], 'user_event_id': user['id'], 'assistant_event_id': assistant['id'],
            'user_text_sha256': user['text_sha256'], 'assistant_text_sha256': assistant['text_sha256'],
            'assistant_ack': assistant['ack'],
            'status': 'RECEIVED' if assistant['ack']['status'] == 'received' else 'RECEIVED_REFUSED',
            'checked_at': now()}


def run(home: Path, item_id: str, actor: str, revision: int, provider: CloudProvider, *, payload: str) -> dict:
    """Commit before one invocation; all subsequent UNKNOWN calls query only."""
    send = False
    preflight = c.read(home, item_id)
    if (preflight['schema'] != causal.ITEM_SCHEMA or actor != preflight['continuation']['parent_owner']
            or isinstance(revision, bool) or revision != preflight['revision']):
        raise GateError('cloud_requires_explicit_v3_owner_revision')
    verified_pin = None
    if preflight['schema'] == causal.ITEM_SCHEMA and preflight['state'] in {'PENDING', 'CLAIMED'}:
        verified_pin = provider.authorize('prepare', preflight)
    with lock(_lock_path(home, item_id)):
        item = c.read(home, item_id)
        if item['schema'] != causal.ITEM_SCHEMA:
            raise GateError('cloud_requires_explicit_v3_preserve_old_item')
        if actor != item['continuation']['parent_owner'] or isinstance(revision, bool) or revision != item['revision']:
            raise GateError('cloud_owner_or_revision_conflict')
        bound = provider.pin(item)
        if item['state'] in causal.TERMINAL:
            return _result(item, 'already_received_no_send')
        if item['state'] in {'PENDING', 'CLAIMED'}:
            if bound != verified_pin:
                raise GateError('cloud_preflight_pin_changed')
            if item['state'] == 'PENDING':
                item = c.transition(home, item_id, actor, item['revision'], 'claim')
            item = c.transition(home, item_id, actor, item['revision'], 'begin-delivery',
                                delivery={'pin': bound, 'payload': payload})
            atomic_json(_intent_path(home, item), _intent(item))
            send = True
        elif item['delivery_request']['pin'] != bound:
            raise GateError('cloud_committed_pin_changed_no_resend')
        admitted = item
    if send:
        # No continuation/driver lock survives callback stalls or exceptions.
        try:
            provider.authorize('invoke', admitted)
            response = provider.port.send_message(bound['target_thread_id'], admitted['delivery_request']['text'])
        except (GateError, OSError, RuntimeError, KeyError, TypeError, ValueError):
            return _result(c.read(home, item_id), 'send_outcome_unknown_query_only')
        with lock(_lock_path(home, item_id)):
            item = c.read(home, item_id)
            intent = _load_intent(home, item)
            intent['response_observed'] = True
            if (not isinstance(response, dict) or response.get('threadId') != bound['target_thread_id']
                    or 'turnId' not in response or 'admissionOutcome' not in response):
                intent['blocked_reason'] = 'cloud_send_response_scope_ambiguous'
            else:
                turn = response['turnId']
                if turn is not None and (not isinstance(turn, str) or not turn or len(turn) > 300):
                    intent['blocked_reason'] = 'cloud_send_response_turn_ambiguous'
                else:
                    intent['actual_turn_id'] = turn
            atomic_json(_intent_path(home, item), intent)
    try:
        observed = provider.observations(admitted)
    except GateError as exc:
        if 'identity_mutated' in str(exc):
            with lock(_lock_path(home, item_id)):
                item = c.read(home, item_id)
                if item['state'] == 'DELIVERY_UNKNOWN' and item['revision'] == admitted['revision']:
                    intent = _load_intent(home, item)
                    intent['blocked_reason'] = str(exc)
                    atomic_json(_intent_path(home, item), intent)
        return _result(c.read(home, item_id), 'read_incomplete_or_unverified_unknown')
    except (OSError, RuntimeError, KeyError, TypeError, ValueError):
        return _result(c.read(home, item_id), 'read_incomplete_or_unverified_unknown')
    provider.authorize('record-receipt', admitted)
    # Recheck fresh core revision after external reads; no stale query can CAS.
    with lock(_lock_path(home, item_id)):
        item = c.read(home, item_id)
        if item['state'] in causal.TERMINAL:
            return _result(item, 'already_received_no_send')
        if item['revision'] != admitted['revision']:
            return _result(item, 'cloud_query_revision_conflict')
        intent = _load_intent(home, item)
        if intent['blocked_reason']:
            return _result(item, intent['blocked_reason'])
        try:
            for event_id, witness in intent['witnesses'].items():
                old = digest({'turn_id': witness['turn_id'], 'role': witness['role'],
                              'text_sha256': witness['text_sha256']})
                fresh = observed['witnesses'].get(event_id)
                if event_id in observed['observed_identities'] and (fresh is None or old != digest({
                        'turn_id': fresh['turn_id'], 'role': fresh['role'], 'text_sha256': fresh['text_sha256']})):
                    raise GateError('cloud_cached_item_identity_mutated')
            for event_id, witness in observed['witnesses'].items():
                previous = intent['witnesses'].get(event_id)
                if previous is not None and previous != witness:
                    raise GateError('cloud_cached_item_identity_mutated')
                intent['witnesses'][event_id] = witness
            if len(intent['witnesses']) > MAX_WITNESSES:
                raise GateError('cloud_causal_witness_limit')
            receipt = _receipt(item, intent)
        except GateError as exc:
            intent['blocked_reason'] = str(exc)
            atomic_json(_intent_path(home, item), intent)
            return _result(item, 'cloud_contradictory_evidence_unknown')
        atomic_json(_intent_path(home, item), intent)
        if receipt is None:
            return _result(item, 'explicit_complete_causal_pair_missing')
        try:
            item = c.transition(home, item_id, actor, admitted['revision'], 'record-receipt', receipt)
        except (GateError, OSError):
            # Atomic commit may have succeeded before its response was lost.
            item = c.read(home, item_id)
            return _result(item, 'receipt_commit_reconciled_no_resend')
        return _result(item, 'causal_received_only_proven')
