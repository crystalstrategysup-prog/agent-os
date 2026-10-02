"""Optional existing-target native provider driver, not a daemon or scheduler.

RPC origin and real target authority/lease are the selecting owner's boundary.
This driver queries that route itself; it never accepts a caller's event receipt.
Local tests using a fixture RPC are not evidence of actual provider acceptance.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from . import continuation as c
from . import continuation_adapter as a
from .codex_rpc import NAMESPACE, SCHEMA_SHA256, VERSION, NativeRpcError
from .safeio import (
    GateError,
    atomic_json,
    digest,
    lock,
    nonempty,
    now,
    read_json,
    within,
)

MAX_PAGES = 4
PAGE_SIZE = 50


class Rpc(Protocol):
    identity: dict

    def call(self, method: str, params: dict) -> dict: ...


def _timestamp(entry: dict) -> datetime:
    value = entry.get('startedAtMs')
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GateError('provider_producer_timestamp_missing')
    try:
        return datetime.fromtimestamp(value / 1000, UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise GateError('provider_timestamp_invalid') from exc


class NativeProvider:
    def __init__(self, rpc: Rpc, mapping: dict, *, cwd: str, session_id: str,
                 thread_cli_version: str,
                 verify_authority: Callable[[str, dict], None]):
        if rpc.identity != {'provider': NAMESPACE, 'version': VERSION, 'schema_sha256': SCHEMA_SHA256}:
            raise GateError('selected_native_rpc_contract_mismatch')
        if mapping.get('provider') != NAMESPACE:
            raise GateError('native_provider_namespace_mismatch')
        if not callable(verify_authority):
            raise GateError('owner_authority_and_lease_verifier_required')
        self.rpc = rpc
        self.mapping = dict(mapping)
        self.cwd = nonempty(cwd, 'target_cwd', 2000)
        self.session_id = nonempty(session_id, 'target_session_id', 300)
        self.thread_cli_version = nonempty(thread_cli_version, 'thread_creation_cli_version', 100)
        self.verify_authority = verify_authority

    def pin(self, item: dict) -> dict:
        if self.rpc.identity != {'provider': NAMESPACE, 'version': VERSION, 'schema_sha256': SCHEMA_SHA256}:
            raise GateError('selected_native_rpc_contract_mismatch')
        return {'mapping': a.binding(self.mapping, item), 'cwd': self.cwd,
                'session_id': self.session_id, 'thread_cli_version': self.thread_cli_version,
                'rpc_identity': self.rpc.identity}

    def metadata(self, *, dispatch: bool = False) -> None:
        self.verify_authority('dispatch' if dispatch else 'read', self.mapping)
        thread = self.rpc.call('thread/read', {'threadId': self.mapping['target_id'], 'includeTurns': False})['thread']
        if (thread.get('id') != self.mapping['target_id'] or thread.get('cwd') != self.cwd
                or thread.get('sessionId') != self.session_id or thread.get('cliVersion') != self.thread_cli_version
                or thread.get('ephemeral') is not False
                or thread.get('historyMode') not in {'legacy', 'paginated'}):
            raise GateError('native_target_identity_or_persistence_mismatch')
        if dispatch and (thread.get('canAcceptDirectInput') is not True
                         or thread.get('status') != {'type': 'idle'}):
            raise GateError('existing_idle_direct_input_target_required')

    def invoke(self, intent: dict) -> str:
        self.verify_authority('dispatch', self.mapping)
        response = self.rpc.call('turn/start', {
            'threadId': self.mapping['target_id'], 'clientUserMessageId': intent['client_message_id'],
            'input': [{'type': 'text', 'text': intent['text']}],
        })
        return nonempty(response['turn']['id'], 'actual_provider_turn_id', 300)

    def evidence(self, item: dict, intent: dict) -> tuple[dict, dict] | None:
        self.metadata()
        entries = []
        cursor = None
        seen_cursors = set()
        for _ in range(MAX_PAGES):
            params = {'threadId': self.mapping['target_id'], 'limit': PAGE_SIZE, 'sortDirection': 'desc'}
            if cursor is not None:
                params['cursor'] = cursor
            page = self.rpc.call('thread/items/list', params)
            data = page['data']
            if not isinstance(data, list) or len(data) > PAGE_SIZE:
                raise GateError('bounded_provider_items_required')
            entries.extend(data)
            cursor = page.get('nextCursor')
            if cursor is None:
                break
            nonempty(cursor, 'provider_cursor', 2000)
            if cursor in seen_cursors:
                raise GateError('provider_pagination_cycle')
            seen_cursors.add(cursor)
        # Page boundaries and order come from the selected RPC, never local clocks.
        ordered = list(reversed(entries))
        ids = [nonempty(x['item']['id'], 'provider_event_id', 300) for x in ordered]
        if len(ids) != len(set(ids)):
            raise GateError('duplicate_provider_event_identity')
        matches = [(i, x) for i, x in enumerate(ordered)
                   if x['item'].get('type') == 'userMessage'
                   and x['item'].get('clientId') == intent['client_message_id']]
        if len(matches) != 1:
            return None
        index, user = matches[0]
        # text_elements defaults to[] in native persisted input.
        if (user['item'].get('content') != [{'type': 'text', 'text': intent['text']}]
                and user['item'].get('content') != [{'type': 'text', 'text': intent['text'], 'text_elements': []}]):
            raise GateError('provider_exact_input_correlation_mismatch')
        turn_id = nonempty(user['turnId'], 'actual_provider_turn_id', 300)
        if intent.get('actual_turn_id') is not None and intent['actual_turn_id'] != turn_id:
            raise GateError('provider_invocation_turn_mismatch')
        user_at = _timestamp(user)
        started = datetime.fromisoformat(item['delivery_started_at'])
        if user_at < started:
            raise GateError('provider_event_predates_delivery')
        later = None
        for entry in ordered[index + 1:]:
            if entry['turnId'] != turn_id:
                continue
            if entry['item']['type'] == 'userMessage':
                raise GateError('interleaved_input_requires_provider_reconciliation')
            if entry['item']['type'] == 'agentMessage':
                later = entry
                break
        if later is None:
            return None
        later_at = _timestamp(later)
        checked_at = datetime.now(UTC)
        if not user_at < later_at <= checked_at:
            raise GateError('provider_strict_event_order_required')
        receipt = {
            'schema': c.RECEIPT_SCHEMA, 'attempt_id': item['attempt_id'],
            'delivery_generation': item['delivery_generation'], 'delivery_nonce': item['delivery_nonce'],
            'target_owner': self.mapping['target_owner'], 'provider': NAMESPACE,
            'checked_at': checked_at.isoformat(), 'status': 'ACCEPTED',
            'user_event_id': user['item']['id'], 'later_activity_id': later['item']['id'],
            'user_event_at': user_at.isoformat(), 'later_activity_at': later_at.isoformat(),
        }
        proof = {'actual_turn_id': turn_id, 'user_event_id': user['item']['id'],
                 'later_activity_id': later['item']['id'], 'client_message_id': intent['client_message_id'],
                 'input_digest': digest(user['item']['content']), 'checked_at': checked_at.isoformat(),
                 'query_scope': {'provider': NAMESPACE, 'schema_sha256': SCHEMA_SHA256,
                                 'thread_id': self.mapping['target_id'], 'sort_direction': 'desc',
                                 'page_limit': PAGE_SIZE, 'items_scanned': len(entries)}}
        # No transcript, reasoning, command payload or arbitrary provider body persisted.
        return receipt, proof


def _intent(provider: NativeProvider, item: dict) -> dict:
    request = a.request(item, provider.mapping)
    envelope = {k: request[k] for k in (
        'schema', 'provider', 'target_id', 'workstream_id', 'target_owner', 'parent_owner',
        'operation_key', 'delivery_generation', 'delivery_nonce', 'delivery_started_at', 'ledger_id', 'ledger_revision',
    )}
    envelope['next_action'] = item['continuation']['next_action']
    text = 'AgentOS continuation envelope\n' + json.dumps(envelope, sort_keys=True, separators=(',', ':'))
    return {'schema': 'agentos.native-invocation-intent/v1',
            'pin': provider.pin(item), 'item_id': item['id'], 'attempt_id': item['attempt_id'],
            'delivery_generation': item['delivery_generation'], 'delivery_nonce': item['delivery_nonce'],
            'ledger_revision_at_begin': item['revision'],
            'client_message_id': digest(envelope), 'text': text, 'text_digest': digest(text),
            'actual_turn_id': None, 'state': 'MAY_HAVE_BEEN_INVOKED', 'at': now()}


def _intent_path(home: Path, item: dict) -> Path:
    return within(home, f"state/continuation-provider/{item['id']}/{item['delivery_generation']}.json")


def _load_intent(home: Path, item: dict, provider: NativeProvider) -> dict:
    path = _intent_path(home, item)
    if not path.exists():
        raise GateError('unknown_delivery_missing_invocation_intent_no_resend')
    value = read_json(path)
    began_at_revision = value.get('ledger_revision_at_begin')
    if (isinstance(began_at_revision, bool) or not isinstance(began_at_revision, int)
            or not 1 <= began_at_revision <= item['revision']):
        raise GateError('provider_intent_revision_invalid')
    # The immutable invocation envelope keeps its admitted revision while the
    # eventual ACK still CAS-checks the fresh item revision.
    expected = _intent(provider, {**item, 'revision': began_at_revision})
    for key in ('schema', 'pin', 'item_id', 'attempt_id', 'delivery_generation', 'delivery_nonce',
                'ledger_revision_at_begin', 'client_message_id', 'text', 'text_digest'):
        if value.get(key) != expected[key]:
            raise GateError('provider_intent_binding_mismatch')
    return value


def _unknown(item: dict, reason: str) -> dict:
    return {'state': item['state'], 'item_id': item['id'], 'revision': item['revision'],
            'reason': reason, 'resend_permitted': False, 'project_completion_proven': False}


def _reconcile(home: Path, item: dict, actor: str, provider: NativeProvider) -> dict:
    intent = _load_intent(home, item, provider)
    try:
        evidence = provider.evidence(item, intent)
    except (NativeRpcError, OSError, TimeoutError):
        return _unknown(item, 'provider_read_unavailable_no_non_delivery_proof')
    except (ValueError, KeyError, TypeError):
        return _unknown(item, 'provider_evidence_unverified')
    if evidence is None:
        return _unknown(item, 'matching_accepted_user_and_later_activity_not_observed')
    receipt, proof = evidence
    a.check_receipt(item, provider.mapping, receipt, 'acknowledge')
    provider.verify_authority('acknowledge', provider.mapping)
    # Retain query provenance before CAS. CAS failure never permits another send.
    intent.update(state='EVENT_CHAIN_OBSERVED', evidence=proof)
    atomic_json(_intent_path(home, item), intent)
    result = c.transition(home, item['id'], actor, item['revision'], 'acknowledge', receipt)
    return {**_unknown(result, 'selected_rpc_event_chain_acknowledged'),
            'actual_provider_turn_id': proof['actual_turn_id']}


def run(home: Path, item_id: str, actor: str, revision: int, provider: NativeProvider) -> dict:
    """One explicitly selected action. Existing UNKNOWN is query-only.

    Never performs not-sent: native error responses do not supply an authoritative
    operation-specific non-delivery contract. Real cloud root needs its own port.
    """
    from .overlay import validate_roots

    validate_roots(home)
    c._path(home, item_id)  # Validate before deriving a lock path.
    with lock(within(home, f'state/continuation-provider/{item_id}.lock')):
        item = c.read(home, item_id)
        if item['schema'] != c.ITEM_SCHEMA:
            raise GateError('legacy_delivery_binding_requires_owner_reconciliation')
        if actor != item['continuation']['parent_owner'] or isinstance(revision, bool) or revision != item['revision']:
            raise GateError('provider_actor_or_revision_conflict')
        provider.pin(item)
        if item['state'] == 'ACKNOWLEDGED':
            return _unknown(item, 'already_acknowledged_no_send')
        if item['state'] == 'DELIVERY_UNKNOWN':
            return _reconcile(home, item, actor, provider)
        # The owner gate and exact-target read occur before any ledger admission.
        provider.metadata(dispatch=True)
        if item['state'] == 'PENDING':
            item = c.transition(home, item_id, actor, item['revision'], 'claim')
        item = c.transition(home, item_id, actor, item['revision'], 'begin-delivery')
        intent = _intent(provider, item)
        path = _intent_path(home, item)
        if path.exists():
            raise GateError('provider_generation_intent_already_exists')
        atomic_json(path, intent)  # Commit uncertainty BEFORE the external call.
        try:
            # Serialize compliant ledger writers and installer final queue checks
            # across the final revision check and this bounded invocation.
            with lock(within(home, 'state/continuations.lock')):
                current = c.read(home, item_id)
                if (current['revision'] != item['revision']
                        or current['state'] != 'DELIVERY_UNKNOWN'
                        or current['delivery_nonce'] != item['delivery_nonce']):
                    raise GateError('provider_pre_invocation_cas_conflict')
                intent['actual_turn_id'] = provider.invoke(intent)
            atomic_json(path, intent)
        except (NativeRpcError, OSError, TimeoutError, ValueError, KeyError, TypeError):
            # Result loss is not failure-to-send; recover by read on a later call.
            return _unknown(item, 'provider_invocation_result_unknown')
        return _reconcile(home, item, actor, provider)
