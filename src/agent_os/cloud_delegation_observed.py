"""Exact source-bound tool delegation observation; frozen user-only core unchanged.

Owner callbacks verify real tool origin, target authority/lease and complete
record attribution. Local identity labels/hashes are not authentication.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from . import continuation as c
from . import project as p
from .safeio import (
    MAX_JSON,
    GateError,
    _parse_json,
    atomic_json,
    create_only_bytes,
    digest,
    lock,
    nonempty,
    now,
    read_json,
    sha,
    within,
)

PROVIDER = 'cloud_threads'
ADAPTER_SHA256 = sha(Path(__file__).read_bytes())
SCOPE = 'observed_received_only'
KIND = 'single_read_delegation_ingress_observation'
INGRESS = 'codex_delegation_tool/v1'
LEDGER = 'agentos.cloud-delegation-journal/v1'
REQUEST = 'agentos.cloud-delegation-request/v1'
ACK = 'agentos.cloud-delegation-observed-ack/v1'
RECEIPT = 'agentos.cloud-delegation-observed-receipt/v1'
REQUEST_PREFIX = 'AGENTOS_CLOUD_DELEGATION_REQUEST_V1\n'
ACK_PREFIX = 'AGENTOS_CLOUD_DELEGATION_ACK_V1\n'
PROFILE = 'codex_delegation.literal_utf8_no_xml_delimiters/v1'
PROFILE_DECLARATION = {'id': PROFILE, 'ingress_kind': INGRESS, 'role': 'tool',
                       'envelope_template': '<codex_delegation><source_thread_id>S</source_thread_id><input>P</input></codex_delegation>',
                       'source_format': 'lowercase_canonical_uuid', 'serialization': 'literal_utf8',
                       'unsupported_in_P': ['<', '>', '&']}
PROFILE_SHA256 = digest(PROFILE_DECLARATION)
TERMINAL = {'OBSERVED_RECEIVED', 'OBSERVED_RECEIVED_REFUSED'}
FLAGS = ('truncated', 'partial', 'summary', 'isSummary', 'textTruncated')
MAX_PAGES = 4


@dataclass(frozen=True)
class RawRead:
    """One original tool-result serialization, never an aggregate of pages.

An invocation reference is retained only when genuinely available. The owner
bridge supplies original bytes and verifies full-record semantics; no new API
field such as complete/immutable is required.
"""
    raw: bytes
    invocation_ref: str | None = None


class Port(Protocol):
    identity: dict

    def send_message(self, thread_id: str, message: str) -> dict: ...

    def read(self, thread_id: str, *, cursor: str | None, limit: int) -> RawRead: ...


class Provider:
    def __init__(self, port: Port, pin: dict, *, verify_authority: Callable,
                 verify_complete: Callable, verify_route: Callable, verify_admission: Callable):
        if not all(callable(x) for x in (verify_authority, verify_complete, verify_route, verify_admission)):
            raise GateError('owner_route_admission_origin_lease_full_record_verifiers_required')
        self.port, self.pin = port, dict(pin)
        self.verify_authority, self.verify_complete = verify_authority, verify_complete
        self.verify_route, self.verify_admission = verify_route, verify_admission
        self.identity = dict(port.identity)
        expected = {'provider', 'send_tool', 'read_tool', 'inspected_schema_sha256'}
        if (set(self.identity) != expected or self.identity['provider'] != PROVIDER
                or self.identity['send_tool'] != 'cloud_threads.send_message'
                or self.identity['read_tool'] != 'cloud_threads.read'):
            raise GateError('actual_cloud_tool_identity_required')
        h = self.identity['inspected_schema_sha256']
        if h is not None and not _hash(h):
            raise GateError('inspected_schema_hash_invalid')

    def authorize(self, phase: str, item: dict) -> None:
        if self.port.identity != self.identity or self.pin != item['pin']:
            raise GateError('observed_provider_or_pin_changed')
        self.verify_authority(phase, dict(self.pin))
        self.verify_route(phase, dict(self.pin))
        if self.port.identity != self.identity or self.pin != item['pin']:
            raise GateError('observed_authorized_provider_changed')


def _hash(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(x in '0123456789abcdef' for x in value)


def _base(home: Path, item_id: str) -> Path:
    if not _hash(item_id):
        raise GateError('invalid_observation_id')
    return within(home, f'state/cloud-delegation/{item_id}')


def _path(home: Path, item_id: str) -> Path:
    return _base(home, item_id) / 'intent.json'


def _lock(home: Path, item_id: str) -> Path:
    return _base(home, item_id) / 'journal.lock'


def _canonical(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _canonical_digest(value: dict) -> str:
    return sha(_canonical(value))


def _thread(value: str) -> None:
    nonempty(value, 'actual_thread_uuid', 36)
    try:
        valid = str(uuid.UUID(value)) == value
    except (ValueError, AttributeError) as exc:
        raise GateError('exact_lowercase_thread_uuid_required') from exc
    if not valid: raise GateError('exact_lowercase_thread_uuid_required')


def _wire(challenge: dict) -> str:
    instruction = ('Emit exactly AGENTOS_CLOUD_DELEGATION_ACK_V1 followed by one LF byte, '
                   'then one standalone final JSON object with no surrounding whitespace or trailing LF; '
                   'schema=agentos.cloud-delegation-observed-ack/v1, '
                   'acceptance_scope=observed_received_only, status=received or received_refused, '
                   'ledger_id, operation_key, delivery_generation, delivery_nonce, request_sha256, '
                   'source_thread_id, target_thread_id and workstream_id echoed exactly. Refusal also requires refusal_reason. '
                   'Receipt of this input only; no execution, work acceptance or project completion. Do not quote or fence.')
    return REQUEST_PREFIX + _canonical({'schema': REQUEST, 'challenge': challenge,
                                        'request_sha256': _canonical_digest(challenge), 'ack_instruction': instruction}).decode('utf-8')


def _wrapper(source: str, text: str) -> str:
    _thread(source)
    if any(x in text for x in '<>&'): raise GateError('unsupported_delegation_literal_payload')
    return '<codex_delegation><source_thread_id>' + source + '</source_thread_id><input>' + text + '</input></codex_delegation>'


def ack(item: dict, status='received', reason=None) -> dict:
    value = {'schema': ACK, 'acceptance_scope': SCOPE, 'status': status,
             **{k: item['challenge'][k] for k in ('ledger_id', 'operation_key', 'delivery_generation',
                                                  'delivery_nonce', 'source_thread_id', 'target_thread_id', 'workstream_id')},
             'request_sha256': item['request_sha256']}
    if status == 'received_refused': value['refusal_reason'] = reason
    return value


def _ack(text: str, item: dict) -> dict:
    if not text.startswith(ACK_PREFIX) or len(text.encode()) > 8192:
        raise GateError('standalone_complete_observed_ack_required')
    body = text[len(ACK_PREFIX):]
    if not body.startswith('{') or not body.endswith('}'):
        raise GateError('exact_ack_one_LF_and_object_required')
    value = _parse_json(body)
    if (not isinstance(value, dict) or value.get('status') not in {'received', 'received_refused'}
            or type(value.get('delivery_generation')) is not int):
        raise GateError('observed_ack_status_or_generation_invalid')
    reason = value.get('refusal_reason')
    if value['status'] == 'received_refused': nonempty(reason, 'observed_refusal_reason', 1000)
    if value != ack(item, value['status'], reason):
        raise GateError('observed_ack_challenge_mismatch')
    return value


def _pin(pin: dict, continuation: dict) -> None:
    keys = {'provider', 'adapter_sha256', 'parent_owner', 'target_owner', 'source_thread_id',
            'target_thread_id', 'workstream_id', 'ingress_kind', 'serialization_profile', 'serialization_profile_sha256'}
    if not isinstance(pin, dict) or set(pin) != keys: raise GateError('delegation_exact_pin_required')
    for key in keys: nonempty(pin[key], 'delegation_pin_' + key, 300)
    _thread(pin['source_thread_id']); _thread(pin['target_thread_id'])
    if (pin['provider'] != PROVIDER or pin['adapter_sha256'] != ADAPTER_SHA256
            or pin['ingress_kind'] != INGRESS or pin['serialization_profile'] != PROFILE
            or pin['serialization_profile_sha256'] != PROFILE_SHA256
            or pin['parent_owner'] != continuation['parent_owner'] or pin['target_owner'] != continuation['next_owner']):
        raise GateError('delegation_owner_adapter_profile_mismatch')


def _challenge(item_id: str, pin: dict, stage: dict, payload: str, nonce: str) -> dict:
    return {'schema': REQUEST, 'acceptance_scope': SCOPE, 'ingress_kind': INGRESS,
            'serialization_profile': PROFILE, 'serialization_profile_sha256': PROFILE_SHA256,
            'ledger_id': item_id, 'operation_key': digest({'ledger': item_id, 'generation': 1}),
            'delivery_generation': 1, 'delivery_nonce': nonce, 'source_thread_id': pin['source_thread_id'],
            'target_thread_id': pin['target_thread_id'], 'workstream_id': pin['workstream_id'],
            'mapping_digest': digest(pin), 'adapter_sha256': ADAPTER_SHA256,
            'stage_identity_sha256': digest(stage), 'journal_revision_at_admission': 2,
            'payload': payload, 'payload_sha256': sha(payload.encode('utf-8'))}


def prepare(home: Path, root: Path, task_id: str, actor: str, pin: dict, *, payload: str) -> dict:
    """Create a disposable adapter journal for one selected CLOSED stage.

    No coordinator queue/receipt/capability schema is created or changed.
    """
    root = p.root_path(root)
    task = p.load_task(root, task_id)
    if task['status'] != 'CLOSED' or p.verify_closeout(root, task_id)['status'] != 'PASS':
        raise GateError('observed_verified_closed_stage_required')
    continuation = c.validate(task['closeout'].get('continuation'))
    _pin(pin, continuation)
    if actor != continuation['parent_owner']: raise GateError('delegation_owner_mismatch')
    nonempty(payload, 'observed_payload', 16000)
    if len(payload.encode()) > 16000: raise GateError('observed_payload_byte_limit')
    stage = {'root': str(root), 'task_id': task_id, 'task_revision': task['revision'],
             'project_id': task['project_id'], 'source_sha256': task['closeout']['assessment']['source_sha256']}
    item_id = digest({'stage': stage, 'pin': pin, 'scope': SCOPE, 'ingress_kind': INGRESS})
    with lock(_lock(home, item_id)):
        if _path(home, item_id).exists():
            item = read(home, item_id)
            if item['challenge']['payload'] != payload: raise GateError('existing_observed_payload_preserve_and_hold')
            return item
        challenge = _challenge(item_id, pin, stage, payload, uuid.uuid4().hex)
        text = _wire(challenge)
        wrapper = _wrapper(pin['source_thread_id'], text)
        item = {'schema': LEDGER, 'id': item_id, 'pin': dict(pin), 'stage': stage, 'continuation': continuation,
                'challenge': challenge, 'request_sha256': _canonical_digest(challenge), 'text': text,
                'text_sha256': sha(text.encode('utf-8')), 'expected_ingress': wrapper,
                'ingress_sha256': sha(wrapper.encode('utf-8')),
                'state': 'PENDING', 'revision': 1, 'observation_ref': None}
        atomic_json(_path(home, item_id), item)
        return item


def read(home: Path, item_id: str) -> dict:
    item = read_json(_path(home, item_id))
    if (item.get('schema') != LEDGER or item.get('id') != item_id or type(item.get('revision')) is not int
            or item['revision'] < 1 or item.get('state') not in {'PENDING', 'DELIVERY_UNKNOWN'} | TERMINAL
            or digest({'stage': item['stage'], 'pin': item['pin'], 'scope': SCOPE, 'ingress_kind': INGRESS}) != item_id):
        raise GateError('observed_journal_identity_invalid')
    _pin(item['pin'], c.validate(item['continuation']))
    challenge = item['challenge']
    expected = _challenge(item_id, item['pin'], item['stage'], challenge['payload'], challenge['delivery_nonce'])
    nonce = challenge['delivery_nonce']
    if (not isinstance(nonce, str) or len(nonce) != 32 or any(x not in '0123456789abcdef' for x in nonce)
            or challenge != expected or type(challenge['delivery_generation']) is not int
            or type(challenge['journal_revision_at_admission']) is not int
            or item['request_sha256'] != _canonical_digest(challenge) or item['text'] != _wire(challenge)
            or item['text_sha256'] != sha(item['text'].encode('utf-8'))
            or item['expected_ingress'] != _wrapper(item['pin']['source_thread_id'], item['text'])
            or item['ingress_sha256'] != sha(item['expected_ingress'].encode('utf-8'))):
        raise GateError('observed_committed_challenge_invalid')
    if item['state'] in TERMINAL:
        ref = item['observation_ref']
        if not _hash(ref): raise GateError('observed_terminal_evidence_required')
        observation = read_json(within(_base(home, item_id), 'observations/' + ref + '.json'))
        if digest(observation) != ref or observation['status'] != item['state']:
            raise GateError('observed_terminal_evidence_changed')
        _validate_observation(observation, item)
    elif item['observation_ref'] is not None:
        raise GateError('observed_uncommitted_terminal_ref')
    return item


def _binding(item: dict, *, admission=False) -> None:
    stage = item['stage']; root = Path(stage['root']); task = p.load_task(root, stage['task_id'])
    if (task['status'] != 'CLOSED' or task['revision'] != stage['task_revision']
            or task['project_id'] != stage['project_id'] or task['closeout']['assessment']['source_sha256'] != stage['source_sha256']
            or c.validate(task['closeout']['continuation']) != item['continuation']):
        raise GateError('observed_stage_binding_changed')
    if admission and p.verify_closeout(root, stage['task_id'])['status'] != 'PASS':
        raise GateError('observed_new_admission_source_stale')


def _page(response: RawRead, item: dict) -> dict:
    if not isinstance(response, RawRead) or not isinstance(response.raw, bytes) or len(response.raw) > MAX_JSON:
        raise GateError('one_original_bounded_read_response_required')
    if response.invocation_ref is not None: nonempty(response.invocation_ref, 'actual_read_invocation', 300)
    page = _parse_json(response.raw)
    if (not isinstance(page, dict) or not isinstance(page.get('items'), list) or len(page['items']) > 50
            or page.get('threadId', item['pin']['target_thread_id']) != item['pin']['target_thread_id']
            or any(page.get(f, False) is not False for f in FLAGS)):
        raise GateError('full_selected_read_response_required')
    if 'provider' in page and page['provider'] != PROVIDER: raise GateError('read_provider_mismatch')
    return page


def _pair(page: dict, item: dict, admitted_turn: str) -> list[dict] | None:
    ingresses, assistants, seen = [], [], {}
    for row in page['items']:
        if not isinstance(row, dict): raise GateError('actual_provider_item_required')
        if row.get('role') not in {'tool', 'assistant'}:
            continue  # Other roles cannot be this delegation/ACK pair.
        event_id = nonempty(row.get('id'), 'observed_event_id', 300)
        turn_id = nonempty(row.get('turnId'), 'observed_turn_id', 300)
        role, text = row.get('role'), row.get('text')
        if not isinstance(role, str) or not isinstance(text, str) or len(text.encode()) > 65536:
            raise GateError('full_provider_role_and_text_required')
        if event_id in seen: raise GateError('duplicate_ids_in_single_response')
        seen[event_id] = True
        # Reserved marker use in genuine admitted T is a candidate before ACK validation.
        candidate = role == 'assistant' and turn_id == admitted_turn and text.startswith(ACK_PREFIX[:-1])
        if any(row.get(f, False) is not False for f in FLAGS):
            if text == item['expected_ingress'] or candidate: raise GateError('truncated_or_summary_pair')
            continue
        selected = {'id': event_id, 'turnId': turn_id, 'role': role, 'text': text}
        if role == 'tool' and text == item['expected_ingress']: ingresses.append(selected)
        elif candidate:
            _ack(text, item)  # Invalid competing candidate must not disappear from the uniqueness gate.
            assistants.append(selected)
    if len(ingresses) > 1 or len(assistants) > 1: raise GateError('ambiguous_pair_in_single_response')
    if not ingresses or not assistants: return None
    pair = [ingresses[0], assistants[0]]
    if pair[0]['turnId'] != pair[1]['turnId']: raise GateError('observed_same_actual_turn_required')
    return pair


def _validate_observation(value: dict, item: dict) -> None:
    if (value.get('schema') != RECEIPT or value.get('evidence_kind') != KIND or value.get('acceptance_scope') != SCOPE
            or value.get('historical_observation') is not True or value.get('pin') != item['pin']
            or value.get('request_sha256') != item['request_sha256'] or value.get('challenge') != item['challenge']
            or value.get('ingress_kind') != INGRESS or value.get('original_send_text') != item['text']
            or value.get('original_send_text_sha256') != item['text_sha256']
            or value.get('expected_ingress_sha256') != item['ingress_sha256']
            or value.get('pair_sha256') != digest(value['selected_pair'])
            or not _hash(value.get('original_response_sha256'))):
        raise GateError('historical_observation_binding_invalid')
    identity = value.get('provider_identity')
    if (not isinstance(identity, dict) or identity.get('provider') != PROVIDER
            or identity.get('send_tool') != 'cloud_threads.send_message'
            or identity.get('read_tool') != 'cloud_threads.read'):
        raise GateError('historical_provider_identity_invalid')
    checked = datetime.fromisoformat(value['checked_at'])
    if checked.tzinfo is None or checked > datetime.now(UTC) + timedelta(minutes=5):
        raise GateError('historical_observer_timestamp_invalid')
    revision = value.get('journal_revision_at_observation')
    if type(revision) is not int or not 1 <= revision <= item['revision']:
        raise GateError('historical_observation_revision_invalid')
    returned = value.get('send_result')
    _admission(returned, item)
    pair = _pair({'items': value['selected_pair']}, item, returned['turnId'])
    if pair is None or value['assistant_ack'] != _ack(pair[1]['text'], item):
        raise GateError('historical_complete_pair_required')
    expected = 'OBSERVED_RECEIVED' if value['assistant_ack']['status'] == 'received' else 'OBSERVED_RECEIVED_REFUSED'
    if value['status'] != expected: raise GateError('observed_refusal_is_not_work_acceptance')
    if returned['turnId'] != pair[0]['turnId']:
        raise GateError('historical_returned_scope_mismatch')


def _append(path: Path, value: dict) -> str:
    key = digest(value)
    dest = path / (key + '.json')
    within(path.parent, path.name + '/' + key + '.json')
    encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    try: create_only_bytes(dest, encoded)
    except FileExistsError:
        if dest.read_bytes() != encoded: raise GateError('append_only_observation_conflict')
    return key


def _send_result(home: Path, item: dict) -> dict | None:
    path = _base(home, item['id']) / 'send.json'
    return read_json(path) if path.exists() else None


def _admission(returned: dict, item: dict) -> None:
    if (not isinstance(returned, dict) or set(returned) != {'threadId', 'turnId', 'admissionOutcome'}
            or returned['threadId'] != item['pin']['target_thread_id']):
        raise GateError('genuine_selected_admission_required')
    turn = nonempty(returned['turnId'], 'genuine_admitted_turn', 300)
    if turn != returned['turnId']: raise GateError('exact_genuine_admitted_turn_required')


def _result(item: dict, reason: str) -> dict:
    return {'state': item['state'], 'id': item['id'], 'revision': item['revision'], 'reason': reason,
            'acceptance_scope': SCOPE, 'resend_permitted': False, 'work_acceptance_proven': False,
            'project_completion_proven': False, 'coordinator_state_changed': False}


def run(home: Path, item_id: str, actor: str, revision: int, provider: Provider) -> dict:
    item = read(home, item_id)
    if actor != item['pin']['parent_owner'] or type(revision) is not int or revision != item['revision']:
        raise GateError('observed_owner_or_revision_conflict')
    if item['state'] in TERMINAL: return _result(item, 'historical_receipt_retained_no_send')
    provider.authorize('prepare' if item['state'] == 'PENDING' else 'read', item)
    send = False
    with lock(_lock(home, item_id)):
        current = read(home, item_id)
        if current['revision'] != revision: raise GateError('observed_revision_conflict')
        _binding(current, admission=current['state'] == 'PENDING')
        if current['state'] == 'PENDING':
            current.update(state='DELIVERY_UNKNOWN', revision=revision + 1)
            atomic_json(_path(home, item_id), current)
            send = True
        item = current
    if send:
        try:
            provider.authorize('invoke', item)
            returned = provider.port.send_message(item['pin']['target_thread_id'], item['text'])
            if (not isinstance(returned, dict) or not {'threadId', 'turnId', 'admissionOutcome'} <= set(returned)
                    or len(_canonical(returned)) > 4096):
                raise GateError('actual_send_projection_required')
            projection = {k: returned[k] for k in ('threadId', 'turnId', 'admissionOutcome')}
            _admission(projection, item)
            provider.verify_admission(projection, dict(item['pin']))
            provider.authorize('retain-admission', item)
            create_only_bytes(_base(home, item_id) / 'send.json', (json.dumps(projection, sort_keys=True) + '\n').encode())
        except (GateError, OSError, RuntimeError, TypeError, ValueError):
            return _result(read(home, item_id), 'uncertain_send_query_only')
    returned = _send_result(home, item)
    try:
        _admission(returned, item)
        provider.verify_admission(returned, dict(item['pin']))
        provider.authorize('verified-admission', item)
    except (GateError, OSError, RuntimeError, KeyError, TypeError, ValueError):
        return _result(read(home, item_id), 'missing_or_unverified_admission_unknown_no_resend')
    current = read(home, item_id)
    if current['state'] in TERMINAL:
        return _result(current, 'historical_receipt_retained_no_send')
    cursor, cursors = None, set()
    for _ in range(MAX_PAGES):
        try:
            provider.authorize('read', item)
            response = provider.port.read(item['pin']['target_thread_id'], cursor=cursor, limit=50)
            page = _page(response, item)
            pair = _pair(page, item, returned['turnId'])
            if pair is not None:
                provider.verify_complete(response, pair)
                provider.authorize('record-observation', item)
                if returned['turnId'] != pair[0]['turnId']:
                    raise GateError('observed_returned_turn_mismatch')
                parsed = _ack(pair[1]['text'], item)
                observation = {'schema': RECEIPT, 'evidence_kind': KIND, 'acceptance_scope': SCOPE,
                               'historical_observation': True, 'provider_identity': provider.identity,
                               'ingress_kind': INGRESS, 'original_send_text': item['text'],
                               'original_send_text_sha256': item['text_sha256'],
                               'expected_ingress_sha256': item['ingress_sha256'],
                               'pin': item['pin'], 'challenge': item['challenge'], 'request_sha256': item['request_sha256'],
                               'send_result': returned, 'read_invocation_ref': response.invocation_ref,
                               'selected_pair': pair, 'pair_sha256': digest(pair),
                               'original_response_sha256': sha(response.raw), 'assistant_ack': parsed,
                               'journal_revision_at_observation': item['revision'],
                               'checked_at': now(), 'status': 'OBSERVED_RECEIVED' if parsed['status'] == 'received' else 'OBSERVED_RECEIVED_REFUSED'}
                with lock(_lock(home, item_id)):
                    ref = _append(_base(home, item_id) / 'observations', observation)
                    current = read(home, item_id)
                    if current['state'] in TERMINAL: return _result(current, 'historical_receipt_retained_no_send')
                    if current['revision'] != item['revision']: return _result(current, 'stale_observation_cas_refused')
                    _binding(current)
                    current.update(state=observation['status'], observation_ref=ref, revision=current['revision'] + 1)
                    try: atomic_json(_path(home, item_id), current)
                    except OSError: return _result(read(home, item_id), 'observation_commit_readback_no_resend')
                    return _result(current, 'single_response_historical_receipt')
            pagination = page.get('pagination')
            nested = pagination.get('nextCursor') if isinstance(pagination, dict) else None
            if page.get('nextCursor') is not None and nested is not None and page['nextCursor'] != nested:
                raise GateError('ambiguous_actual_read_cursor')
            cursor = page.get('nextCursor', nested)
            if cursor is None: break
            nonempty(cursor, 'actual_read_cursor', 2000)
            if cursor in cursors: raise GateError('observed_pagination_cycle')
            cursors.add(cursor)
        except (GateError, OSError, RuntimeError, KeyError, TypeError, ValueError):
            return _result(read(home, item_id), 'read_or_evidence_incomplete_unknown')
    return _result(read(home, item_id), 'same_response_complete_pair_missing')


def recheck(home: Path, item_id: str, provider: Provider) -> dict:
    """One optional owner read appends discrepancy; original terminal never rewrites."""
    item = read(home, item_id)
    if item['state'] not in TERMINAL: raise GateError('historical_observation_required')
    provider.authorize('recheck', item)
    response = provider.port.read(item['pin']['target_thread_id'], cursor=None, limit=50)
    page = _page(response, item)
    original = read_json(within(_base(home, item_id), 'observations/' + item['observation_ref'] + '.json'))
    changes = []
    for old in original['selected_pair']:
        matches = [row for row in page['items'] if row.get('id') == old['id']]
        if len(matches) > 1: raise GateError('ambiguous_discrepancy_records')
        if not matches: continue  # Omission is not proof of deletion.
        row = matches[0]; provider.verify_complete(response, [row])
        if any(row.get(f, False) is not False for f in FLAGS): raise GateError('partial_discrepancy_record')
        current = {k: row[k] for k in ('id', 'turnId', 'role', 'text')}
        if current != old:
            changes.append({'id': old['id'], 'old_sha256': digest(old), 'observed_sha256': digest(current)})
    if changes:
        provider.authorize('append-discrepancy', item)
        discrepancy = {'schema': 'agentos.cloud-observation-discrepancy/v1', 'original_observation_ref': item['observation_ref'],
                       'provider_identity': provider.identity, 'read_invocation_ref': response.invocation_ref,
                       'original_response_sha256': sha(response.raw), 'changes': changes, 'checked_at': now(),
                       'scope': 'later_observation_does_not_erase_historical_receipt'}
        with lock(_lock(home, item_id)): _append(_base(home, item_id) / 'discrepancies', discrepancy)
    return _result(read(home, item_id), 'later_discrepancy_appended' if changes else 'no_positive_discrepancy')
