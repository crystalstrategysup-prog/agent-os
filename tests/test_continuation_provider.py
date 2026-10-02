"""Synthetic RPC/ledger integration. NO real native/root delivery acceptance."""
from __future__ import annotations

import copy
import os
import time
from datetime import UTC, datetime

import pytest
from test_continuation_dispatch import move, queued, rejected
from test_foundation import setup as foundation_setup

from agent_os import continuation as c
from agent_os import continuation_provider as d
from agent_os.codex_rpc import NAMESPACE, SCHEMA_SHA256, VERSION, NativeRpcError
from agent_os.safeio import GateError, atomic_json, filemap

setup = foundation_setup


class FixtureRpc:
    def __init__(self, root):
        self.identity = {'provider': NAMESPACE, 'version': VERSION, 'schema_sha256': SCHEMA_SHA256}
        self.calls = []
        self.rows = []
        self.fail_read = False
        self.lose_response = False
        self.before_invoke = lambda: None
        self.metadata = {'id': 'fixture-existing-thread', 'cwd': str(root), 'sessionId': 'fixture-session',
                         'cliVersion': VERSION, 'ephemeral': False, 'historyMode': 'paginated',
                         'canAcceptDirectInput': True, 'status': {'type': 'idle'}}

    def call(self, method, params):
        self.calls.append((method, copy.deepcopy(params)))
        if method == 'thread/read':
            if self.fail_read:
                raise NativeRpcError(-32600)
            return {'thread': copy.deepcopy(self.metadata)}
        if method == 'turn/start':
            self.before_invoke()
            assert set(params) == {'threadId', 'clientUserMessageId', 'input'}
            time.sleep(.003)
            user = {'turnId': 'fixture-real-response-turn', 'startedAtMs': int(datetime.now(UTC).timestamp() * 1000),
                    'item': {'type': 'userMessage', 'id': 'fixture-producer-user',
                             'clientId': params['clientUserMessageId'], 'content': copy.deepcopy(params['input'])}}
            time.sleep(.003)
            later = {'turnId': user['turnId'], 'startedAtMs': int(datetime.now(UTC).timestamp() * 1000),
                     'item': {'type': 'agentMessage', 'id': 'fixture-producer-later', 'text': 'Synthetic public activity'}}
            self.rows = [later, user]
            if self.lose_response:
                raise TimeoutError('synthetic result loss after durable input')
            return {'turn': {'id': user['turnId'], 'items': [], 'status': 'inProgress'}}
        assert method == 'thread/items/list'
        return {'data': copy.deepcopy(self.rows), 'nextCursor': None}


def fixture(setup):
    root = setup[0]
    rpc = FixtureRpc(root)
    mapping = {'schema': 'agentos.continuation-adapter-binding/v1', 'provider': NAMESPACE,
               'target_owner': 'independent-reviewer', 'target_id': 'fixture-existing-thread',
               'workstream_id': 'fixture-workstream', 'parent_owner': 'parent'}
    gates = []
    provider = d.NativeProvider(rpc, mapping, cwd=str(root), session_id='fixture-session',
                                thread_cli_version=VERSION,
                                verify_authority=lambda phase, bound: gates.append((phase, bound)))
    return rpc, provider, queued(setup), gates


def run(setup, provider, item):
    return d.run(setup[1], item['id'], 'parent', item['revision'], provider)


def sends(rpc):
    return sum(method == 'turn/start' for method, _ in rpc.calls)


def test_actual_rpc_queries_drive_fixture_ack_and_duplicate_does_not_send(setup):
    rpc, provider, item, gates = fixture(setup)

    def committed():
        current = c.read(setup[1], item['id'])
        assert current['state'] == 'DELIVERY_UNKNOWN'
        intent = d._load_intent(setup[1], current, provider)
        assert intent['state'] == 'MAY_HAVE_BEEN_INVOKED' and intent['actual_turn_id'] is None
        assert intent['ledger_revision_at_begin'] == current['revision']
        assert '"ledger_revision":' + str(current['revision']) in intent['text']

    rpc.before_invoke = committed
    result = run(setup, provider, item)
    assert result['state'] == 'ACKNOWLEDGED' and result['project_completion_proven'] is False
    ack = c.read(setup[1], item['id'])
    assert ack['receipt']['user_event_id'] == 'fixture-producer-user'
    before = filemap(setup[1])
    assert run(setup, provider, ack)['reason'] == 'already_acknowledged_no_send'
    assert filemap(setup[1]) == before and sends(rpc) == 1
    assert [x[0] for x in gates].count('acknowledge') == 1


def test_response_loss_then_authoritative_read_recovers_without_resend(setup):
    rpc, provider, item, _ = fixture(setup)
    rpc.lose_response = True
    assert run(setup, provider, item)['state'] == 'DELIVERY_UNKNOWN'
    unknown = c.read(setup[1], item['id'])
    assert d._load_intent(setup[1], unknown, provider)['actual_turn_id'] is None
    assert run(setup, provider, unknown)['state'] == 'ACKNOWLEDGED'
    assert sends(rpc) == 1


def test_thread_not_loaded_before_admission_preserves_pending(setup):
    rpc, provider, item, _ = fixture(setup)
    rpc.fail_read = True
    before = filemap(setup[1])
    with pytest.raises(NativeRpcError):
        run(setup, provider, item)
    assert filemap(setup[1]) == before and sends(rpc) == 0


def test_thread_not_loaded_after_response_loss_stays_owned_unknown(setup):
    rpc, provider, item, _ = fixture(setup)
    rpc.lose_response = True
    run(setup, provider, item)
    rpc.fail_read = True
    unknown = c.read(setup[1], item['id'])
    before = filemap(setup[1])
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    assert filemap(setup[1]) == before and sends(rpc) == 1


@pytest.mark.parametrize('case', ['user-timestamp', 'later-timestamp', 'clientId', 'wrong-content',
                                  'wrong-turn', 'reverse-time', 'equal-time', 'duplicate-id',
                                  'duplicate-input', 'interleaved-input', 'no-later', 'old-time'])
def test_missing_or_uncorrelated_evidence_cannot_ack_or_resend(setup, case):
    rpc, provider, item, _ = fixture(setup)
    rpc.lose_response = True
    run(setup, provider, item)
    later, user = rpc.rows
    if case == 'user-timestamp':
        user.pop('startedAtMs')
    elif case == 'later-timestamp':
        later.pop('startedAtMs')
    elif case == 'clientId':
        user['item'].pop('clientId')
    elif case == 'wrong-content':
        user['item']['content'][0]['text'] = 'Other operation'
    elif case == 'wrong-turn':
        later['turnId'] = 'unrelated-turn'
    elif case == 'reverse-time':
        user['startedAtMs'], later['startedAtMs'] = later['startedAtMs'], user['startedAtMs']
    elif case == 'equal-time':
        later['startedAtMs'] = user['startedAtMs']
    elif case == 'duplicate-id':
        later['item']['id'] = user['item']['id']
    elif case == 'duplicate-input':
        second = copy.deepcopy(user); second['item']['id'] = 'duplicate-user'
        rpc.rows.append(second)
    elif case == 'interleaved-input':
        second = copy.deepcopy(user); second['item'].update(id='interleaved-user', clientId='unrelated')
        rpc.rows.insert(1, second)
    elif case == 'no-later':
        rpc.rows = [user]
    else:
        user['startedAtMs'] -= 10000
    unknown = c.read(setup[1], item['id'])
    before = filemap(setup[1])
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    assert filemap(setup[1]) == before and sends(rpc) == 1


@pytest.mark.parametrize('field,value', [('cwd', '/wrong'), ('sessionId', 'wrong'), ('id', 'wrong'),
                                      ('cliVersion', 'future'), ('ephemeral', True),
                                      ('historyMode', None), ('status', {'type': 'active'}),
                                      ('canAcceptDirectInput', False)])
def test_exact_idle_persistent_target_preflight_is_required(setup, field, value):
    rpc, provider, item, _ = fixture(setup)
    rpc.metadata[field] = value
    before = filemap(setup[1])
    with pytest.raises(GateError):
        run(setup, provider, item)
    assert filemap(setup[1]) == before and sends(rpc) == 0


def test_failed_owner_gate_never_admits_invocation(setup):
    rpc, provider, item, _ = fixture(setup)

    def denied(phase, mapping):
        raise GateError('owner_target_lease_unavailable')

    provider.verify_authority = denied
    before = filemap(setup[1])
    with pytest.raises(GateError):
        run(setup, provider, item)
    assert filemap(setup[1]) == before and rpc.calls == []


@pytest.mark.parametrize('state', ['PENDING', 'CLAIMED', 'DELIVERY_UNKNOWN', 'ACKNOWLEDGED'])
def test_legacy_v1_refused_before_rpc_and_preserved(setup, state):
    rpc, provider, item, _ = fixture(setup)
    item.update(schema=c.LEGACY_ITEM_SCHEMA, state=state)
    atomic_json(c._path(setup[1], item['id']), item)
    before = filemap(setup[1])
    with pytest.raises(GateError, match='legacy_delivery_binding'):
        run(setup, provider, item)
    assert filemap(setup[1]) == before and rpc.calls == []


def test_failed_intent_write_after_begin_never_invokes_and_recovery_cannot_resend(setup, monkeypatch):
    rpc, provider, item, _ = fixture(setup)

    def failed(path, value):
        raise OSError('fixture intent write failure')

    monkeypatch.setattr(d, 'atomic_json', failed)
    with pytest.raises(OSError):
        run(setup, provider, item)
    unknown = c.read(setup[1], item['id'])
    assert unknown['state'] == 'DELIVERY_UNKNOWN' and sends(rpc) == 0
    with pytest.raises(GateError, match='missing_invocation_intent_no_resend'):
        run(setup, provider, unknown)
    assert sends(rpc) == 0


def test_lost_ack_commit_is_read_back_and_never_reinvoked(setup, monkeypatch):
    rpc, provider, item, _ = fixture(setup)
    original = c.atomic_json

    def lost_response(path, value):
        original(path, value)
        if value.get('state') == 'ACKNOWLEDGED':
            raise OSError('fixture ACK result loss')

    monkeypatch.setattr(c, 'atomic_json', lost_response)
    with pytest.raises(OSError):
        run(setup, provider, item)
    ack = c.read(setup[1], item['id'])
    assert ack['state'] == 'ACKNOWLEDGED'
    assert run(setup, provider, ack)['state'] == 'ACKNOWLEDGED' and sends(rpc) == 1


def test_old_generation_event_cannot_ack_current_generation(setup):
    rpc, provider, item, _ = fixture(setup)
    rpc.lose_response = True
    run(setup, provider, item)
    first = c.read(setup[1], item['id'])
    old_rows = copy.deepcopy(rpc.rows)
    # Fixture ONLY authoritative non-delivery; native adapter never invents it.
    claimed = move(setup[1], first, 'not-sent', rejected(first, 'fixture-authoritative-rejection'))
    second = move(setup[1], claimed, 'begin-delivery')
    atomic_json(d._intent_path(setup[1], second), d._intent(provider, second))
    rpc.rows = old_rows
    before = filemap(setup[1])
    assert run(setup, provider, second)['state'] == 'DELIVERY_UNKNOWN'
    assert filemap(setup[1]) == before and sends(rpc) == 1
    with pytest.raises(GateError, match='revision_conflict'):
        run(setup, provider, first)


def test_changed_mapping_for_unknown_cannot_rebind_target(setup):
    rpc, provider, item, _ = fixture(setup)
    rpc.lose_response = True
    run(setup, provider, item)
    unknown = c.read(setup[1], item['id'])
    provider.mapping['target_id'] = 'replacement-target'
    calls = len(rpc.calls)
    with pytest.raises(GateError, match='intent_binding_mismatch'):
        run(setup, provider, unknown)
    assert len(rpc.calls) == calls and sends(rpc) == 1


def test_cross_provider_and_schema_identity_refused(setup):
    rpc, provider, _, _ = fixture(setup)
    for identity in [{'provider': 'cloud-relabel'}, {**rpc.identity, 'schema_sha256': 'wrong'}]:
        rpc.identity = identity
        with pytest.raises(GateError, match='rpc_contract_mismatch'):
            d.NativeProvider(rpc, provider.mapping, cwd=str(setup[0]), session_id='fixture-session',
                             thread_cli_version=VERSION,
                             verify_authority=lambda phase, bound: None)


def test_read_only_pagination_is_bounded_and_cycle_does_not_ack(setup):
    rpc, provider, item, _ = fixture(setup)
    rpc.lose_response = True
    run(setup, provider, item)
    original = rpc.call

    def repeated(method, params):
        if method == 'thread/items/list':
            rpc.calls.append((method, params))
            return {'data': [], 'nextCursor': 'same-cursor'}
        return original(method, params)

    rpc.call = repeated
    unknown = c.read(setup[1], item['id'])
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    assert sends(rpc) == 1
    assert sum(m == 'thread/items/list' for m, _ in rpc.calls) == 2


def test_invocation_serializes_core_writers_but_read_only_status_does_not_consume(setup):
    rpc, provider, item, _ = fixture(setup)

    def interleave():
        current = c.read(setup[1], item['id'])
        before = filemap(setup[1])
        assert c.status(setup[1])['items'][0]['state'] == 'DELIVERY_UNKNOWN'
        assert filemap(setup[1]) == before
        with pytest.raises(GateError, match='busy_or_stale_lock'):
            move(setup[1], current, 'not-sent', rejected(current))
        assert c.read(setup[1], item['id']) == current

    rpc.before_invoke = interleave
    assert run(setup, provider, item)['state'] == 'ACKNOWLEDGED'


def test_event_query_cas_conflict_cannot_ack_changed_item(setup):
    rpc, provider, item, _ = fixture(setup)
    rpc.lose_response = True
    run(setup, provider, item)
    unknown = c.read(setup[1], item['id'])
    original = rpc.call

    def conflict(method, params):
        response = original(method, params)
        if method == 'thread/items/list':
            current = c.read(setup[1], item['id'])
            current['revision'] += 1  # Synthetic concurrent writer fixture.
            atomic_json(c._path(setup[1], item['id']), current)
        return response

    rpc.call = conflict
    with pytest.raises(GateError, match='revision_conflict'):
        run(setup, provider, unknown)
    assert c.read(setup[1], item['id'])['state'] == 'DELIVERY_UNKNOWN' and sends(rpc) == 1


def test_lost_intent_response_after_send_can_reconcile_durable_initial_intent(setup, monkeypatch):
    rpc, provider, item, _ = fixture(setup)
    original = d.atomic_json
    writes = []

    def lost_update(path, value):
        writes.append(value['state'])
        if len(writes) == 2:
            raise OSError('fixture failure before recording returned turn ID')
        original(path, value)

    monkeypatch.setattr(d, 'atomic_json', lost_update)
    assert run(setup, provider, item)['state'] == 'DELIVERY_UNKNOWN'
    unknown = c.read(setup[1], item['id'])
    assert d._load_intent(setup[1], unknown, provider)['actual_turn_id'] is None
    assert run(setup, provider, unknown)['state'] == 'ACKNOWLEDGED' and sends(rpc) == 1


def test_thread_creation_version_is_pinned_separately_from_current_rpc_version(setup):
    rpc, provider, item, _ = fixture(setup)
    provider.thread_cli_version = '0.158.0'
    rpc.metadata['cliVersion'] = '0.158.0'
    assert provider.rpc.identity['version'] == VERSION
    assert run(setup, provider, item)['state'] == 'ACKNOWLEDGED'


def test_malformed_provider_read_stays_unknown_without_resend(setup):
    rpc, provider, item, _ = fixture(setup)
    rpc.lose_response = True
    run(setup, provider, item)
    rpc.rows = [{'item': {'type': 'agentMessage'}}]
    unknown = c.read(setup[1], item['id'])
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    assert sends(rpc) == 1 and c.read(setup[1], item['id']) == unknown


def test_actor_and_revision_conflict_cannot_send(setup):
    rpc, provider, item, _ = fixture(setup)
    before = filemap(setup[1])
    for actor, revision in [('other-parent', item['revision']), ('parent', 999), ('parent', True)]:
        with pytest.raises(GateError, match='actor_or_revision_conflict'):
            d.run(setup[1], item['id'], actor, revision, provider)
    assert rpc.calls == [] and filemap(setup[1]) == before


def test_stalled_native_pipe_releases_ledger_driver_locks_and_never_resends(setup, tmp_path, monkeypatch):
    from test_codex_rpc import client

    rpc, provider, item, _ = fixture(setup)
    native, _ = client(tmp_path, monkeypatch, 'stalled-write')
    native.timeout = .05
    descriptor = native.process.stdin.fileno()
    os.set_blocking(descriptor, False)
    try:
        while True:
            try:
                os.write(descriptor, b'x' * 65536)
            except BlockingIOError:
                break
        original = rpc.call
        invocations = []

        def bridge(method, params):
            if method == 'turn/start':
                invocations.append(params)
                return native.call(method, params)
            return original(method, params)

        rpc.call = bridge
        started = time.monotonic()
        assert run(setup, provider, item)['state'] == 'DELIVERY_UNKNOWN'
        assert time.monotonic() - started < .7
        assert native.process.poll() is not None
        assert not (setup[1] / 'state/continuations.lock').exists()
        assert not (setup[1] / f"state/continuation-provider/{item['id']}.lock").exists()
        unknown = c.read(setup[1], item['id'])
        assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
        assert len(invocations) == 1
    finally:
        native.close()
