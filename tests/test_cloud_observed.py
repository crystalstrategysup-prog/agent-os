"""Synthetic authenticated-port contract fixtures, never live adoption evidence."""
from __future__ import annotations

import copy
import json

import pytest
from test_continuation_dispatch import closed
from test_foundation import setup as foundation_setup

from agent_os import cloud_observed as o
from agent_os.safeio import GateError, atomic_json, digest, filemap, read_json, sha

setup = foundation_setup


class FixturePort:
    def __init__(self):
        self.identity = {'provider': o.PROVIDER, 'send_tool': 'cloud_threads.send_message',
                         'read_tool': 'cloud_threads.read', 'inspected_schema_sha256': None}
        self.calls, self.rows = [], []
        self.lose_send = False; self.status = 'received'; self.returned_turn = 'actual-fixture-turn'
        self.pages = None; self.before_send = lambda: None; self.before_read = lambda: None

    def send_message(self, thread_id, message):
        self.calls.append(('send', thread_id, message)); self.before_send()
        wire = json.loads(message[len(o.REQUEST_PREFIX):]); challenge = wire['challenge']
        item = {'challenge': challenge, 'request_sha256': wire['request_sha256']}
        text = o.ACK_PREFIX + json.dumps(o.ack(item, self.status, 'Fixture refusal' if self.status == 'received_refused' else None))
        self.rows = [{'id': 'actual-assistant', 'turnId': 'actual-fixture-turn', 'role': 'assistant', 'text': text},
                     {'id': 'actual-user', 'turnId': 'actual-fixture-turn', 'role': 'user', 'text': message}]
        if self.lose_send: raise TimeoutError('Fixture send response lost')
        return {'threadId': thread_id, 'turnId': self.returned_turn, 'admissionOutcome': 'accepted'}

    def read(self, thread_id, *, cursor, limit):
        self.calls.append(('read', thread_id, cursor)); self.before_read(); assert limit == 50
        response = self.pages(cursor) if self.pages else {'items': self.rows, 'nextCursor': None}
        return o.RawRead(json.dumps(response, sort_keys=True).encode(), 'fixture-read-' + str(len(self.calls)))


def fixture(setup):
    task = closed(setup)
    pin = {'provider': o.PROVIDER, 'adapter_sha256': o.ADAPTER_SHA256, 'parent_owner': 'parent',
           'target_owner': 'independent-reviewer', 'target_thread_id': 'actual-fixture-target', 'workstream_id': 'receipt-only-fixture'}
    item = o.prepare(setup[1], setup[0], task, 'parent', pin, payload='Receipt-only canary; no work execution requested.')
    port = FixturePort()
    provider = o.Provider(port, pin, verify_authority=lambda phase, pin: None,
                          verify_complete=lambda raw, selected: None)
    return port, provider, item


def run(setup, provider, item):
    return o.run(setup[1], item['id'], 'parent', item['revision'], provider)


def sends(port): return sum(x[0] == 'send' for x in port.calls)


def lost(setup):
    port, provider, item = fixture(setup); port.lose_send = True
    assert run(setup, provider, item)['state'] == 'DELIVERY_UNKNOWN'
    return port, provider, o.read(setup[1], item['id'])


@pytest.mark.parametrize('status', ['received', 'received_refused'])
def test_one_original_response_records_historical_receipt_only_and_repeat_has_no_io(setup, status):
    port, provider, item = fixture(setup); port.status = status
    state = 'OBSERVED_RECEIVED' if status == 'received' else 'OBSERVED_RECEIVED_REFUSED'
    result = run(setup, provider, item)
    assert result['state'] == state and result['work_acceptance_proven'] is False
    assert result['project_completion_proven'] is False and result['coordinator_state_changed'] is False
    current = o.read(setup[1], item['id']); before = filemap(setup[1]); calls = copy.deepcopy(port.calls)
    observation = read_json(o._base(setup[1], item['id']) / 'observations' / (current['observation_ref'] + '.json'))
    assert observation['original_response_sha256'] == sha(json.dumps({'items': port.rows, 'nextCursor': None}, sort_keys=True).encode())
    assert observation['pair_sha256'] == digest(observation['selected_pair'])
    assert observation['selected_pair'][0]['text'] == item['text'] and observation['read_invocation_ref']
    assert not (setup[1] / 'state/continuations').exists()
    assert run(setup, provider, current)['state'] == state
    assert filemap(setup[1]) == before and port.calls == calls and sends(port) == 1


def test_committed_wire_before_one_send_and_callbacks_do_not_hold_journal_lock(setup):
    port, provider, item = fixture(setup)
    def committed():
        assert not o._lock(setup[1], item['id']).exists()
        assert o.read(setup[1], item['id'])['state'] == 'DELIVERY_UNKNOWN'
        assert port.calls[0][2] == o.read(setup[1], item['id'])['text']
    port.before_send = committed; port.before_read = committed
    assert run(setup, provider, item)['state'] == 'OBSERVED_RECEIVED'


def test_lost_result_recovers_unique_same_response_without_resend_or_guessed_time(setup):
    port, provider, unknown = lost(setup)
    assert run(setup, provider, unknown)['state'] == 'OBSERVED_RECEIVED' and sends(port) == 1
    current = o.read(setup[1], unknown['id'])
    value = read_json(o._base(setup[1], unknown['id']) / 'observations' / (current['observation_ref'] + '.json'))
    assert value['send_result'] is None and not any(k.endswith('_at') for k in value if k != 'checked_at')


@pytest.mark.parametrize('case', ['split-reads', 'split-pages', 'mutated-omitted-user'])
def test_never_stitches_cached_records_across_original_responses(setup, case):
    port, provider, unknown = lost(setup); assistant, user = copy.deepcopy(port.rows)
    if case == 'split-pages':
        port.pages = lambda cursor: {'items': [user] if cursor is None else [assistant],
                                     'nextCursor': 'next' if cursor is None else None}
        assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    else:
        port.rows = [user]
        assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
        if case == 'mutated-omitted-user': user['text'] += ' Edited but omitted from later response'
        port.rows = [assistant]
        assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    assert not (o._base(setup[1], unknown['id']) / 'observations').exists() and sends(port) == 1


def test_search_next_page_accepts_only_when_that_single_page_has_entire_pair(setup):
    port, provider, unknown = lost(setup); rows = copy.deepcopy(port.rows)
    port.pages = lambda cursor: {'items': rows[1:] if cursor is None else rows,
                                 'nextCursor': 'next' if cursor is None else 'remaining-unread-history'}
    assert run(setup, provider, unknown)['state'] == 'OBSERVED_RECEIVED' and sends(port) == 1
    assert len([x for x in port.calls if x[0] == 'read']) == 2


@pytest.mark.parametrize('case', ['quoted', 'clipped', 'generic', 'role-tool', 'role-user', 'wrong-turn',
                                  'truncated', 'summary', 'partial-page', 'wrong-provider', 'wrong-target',
                                  'duplicate-id', 'duplicate-user', 'duplicate-ack', 'nonce', 'digest',
                                  'generation', 'operation', 'ledger', 'target', 'workstream', 'bool-generation'])
def test_incomplete_untrusted_or_wrong_causal_pair_cannot_receive(setup, case):
    port, provider, unknown = lost(setup); assistant, user = port.rows
    if case == 'quoted': assistant['text'] = '> ' + assistant['text']
    elif case == 'clipped': assistant['text'] = assistant['text'][:-1]
    elif case == 'generic': assistant['text'] = 'Receipt received; task complete'
    elif case == 'role-tool': assistant['role'] = 'tool'
    elif case == 'role-user': assistant['role'] = 'user'
    elif case == 'wrong-turn': assistant['turnId'] = 'other-turn'
    elif case == 'truncated': assistant['truncated'] = True
    elif case == 'summary': assistant['summary'] = True
    elif case == 'partial-page': port.pages = lambda cursor: {'items': port.rows, 'partial': True}
    elif case == 'wrong-provider': port.pages = lambda cursor: {'items': port.rows, 'provider': 'native'}
    elif case == 'wrong-target': port.pages = lambda cursor: {'items': port.rows, 'threadId': 'other-target'}
    elif case == 'duplicate-id': assistant['id'] = user['id']
    elif case in {'duplicate-user', 'duplicate-ack'}:
        extra = copy.deepcopy(user if case == 'duplicate-user' else assistant); extra['id'] += '-other'; port.rows.append(extra)
    else:
        value = json.loads(assistant['text'][len(o.ACK_PREFIX):])
        field = {'nonce':'delivery_nonce','digest':'request_sha256','generation':'delivery_generation',
                 'operation':'operation_key','ledger':'ledger_id','target':'target_thread_id',
                 'workstream':'workstream_id','bool-generation':'delivery_generation'}[case]
        value[field] = True if case == 'bool-generation' else 2 if case == 'generation' else 'wrong'
        assistant['text'] = o.ACK_PREFIX + json.dumps(value)
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    assert sends(port) == 1 and not (o._base(setup[1], unknown['id']) / 'observations').exists()


def test_origin_and_complete_record_verifiers_are_required_before_acceptance(setup):
    port, provider, unknown = lost(setup)
    def denied(raw, selected): raise GateError('actual API projection contains summaries only')
    provider.verify_complete = denied
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    port.identity = {**port.identity, 'provider': 'codex.app-server'}
    with pytest.raises(GateError, match='provider_or_pin_changed'): run(setup, provider, unknown)
    assert sends(port) == 1


def test_original_bytes_are_parsed_here_not_a_caller_selected_array(setup):
    port, provider, unknown = lost(setup)
    port.read = lambda *args, **kwargs: {'items': port.rows}
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 1


def test_replayed_previous_challenge_cannot_certify_new_disposable_journal(setup):
    port, provider, unknown = lost(setup); old_rows = copy.deepcopy(port.rows)
    pin = {**provider.pin, 'workstream_id': 'distinct-authorized-fixture-canary'}
    fresh = o.prepare(setup[1], setup[0], unknown['stage']['task_id'], 'parent', pin, payload='Another receipt-only canary')
    new_port = FixturePort(); new_provider = o.Provider(new_port, pin, verify_authority=lambda phase, pin: None,
                                                     verify_complete=lambda raw, selected: None)
    new_port.lose_send = True; run(setup, new_provider, fresh); new_port.rows = old_rows
    assert run(setup, new_provider, o.read(setup[1], fresh['id']))['state'] == 'DELIVERY_UNKNOWN'
    assert sends(port) == sends(new_port) == 1


@pytest.mark.parametrize('failure', ['evidence', 'cas-before-write', 'cas-after-write'])
def test_faults_preserve_append_only_evidence_and_unknown_or_terminal_without_resend(setup, monkeypatch, failure):
    port, provider, unknown = lost(setup); real_append, real_atomic = o.create_only_bytes, o.atomic_json
    if failure == 'evidence':
        def bad(path, data): raise OSError('fixture evidence write failed')
        monkeypatch.setattr(o, 'create_only_bytes', bad)
    else:
        def failed(path, value):
            if failure == 'cas-after-write': real_atomic(path, value)
            raise OSError('fixture CAS result lost')
        monkeypatch.setattr(o, 'atomic_json', failed)
    expected = 'OBSERVED_RECEIVED' if failure == 'cas-after-write' else 'DELIVERY_UNKNOWN'
    assert run(setup, provider, unknown)['state'] == expected and sends(port) == 1
    monkeypatch.setattr(o, 'create_only_bytes', real_append); monkeypatch.setattr(o, 'atomic_json', real_atomic)
    current = o.read(setup[1], unknown['id'])
    if failure == 'cas-before-write':
        assert len(list((o._base(setup[1], unknown['id']) / 'observations').glob('*.json'))) == 1
        port.rows = []
        assert run(setup, provider, current)['state'] == 'DELIVERY_UNKNOWN'  # Cannot consume old cached pair.
    else:
        assert run(setup, provider, current)['state'] == 'OBSERVED_RECEIVED'
    assert sends(port) == 1


def test_stale_revision_appends_uncommitted_observation_but_cannot_cas(setup):
    port, provider, unknown = lost(setup)
    def interleave():
        current = o.read(setup[1], unknown['id']); current['revision'] += 1
        atomic_json(o._path(setup[1], unknown['id']), current)
    port.before_read = interleave
    assert run(setup, provider, unknown)['reason'] == 'stale_observation_cas_refused'
    assert o.read(setup[1], unknown['id'])['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 1


def test_later_mutation_appends_discrepancy_preserving_original_observation_and_state(setup):
    port, provider, item = fixture(setup); run(setup, provider, item)
    current = o.read(setup[1], item['id']); path = o._base(setup[1], item['id']) / 'observations' / (current['observation_ref'] + '.json')
    original = path.read_bytes(); intent = o._path(setup[1], item['id']).read_bytes()
    port.rows[1]['text'] = 'Edited provider user record'
    assert o.recheck(setup[1], item['id'], provider)['reason'] == 'later_discrepancy_appended'
    assert path.read_bytes() == original and o._path(setup[1], item['id']).read_bytes() == intent
    assert len(list((o._base(setup[1], item['id']) / 'discrepancies').glob('*.json'))) == 1
    assert run(setup, provider, current)['state'] == 'OBSERVED_RECEIVED' and sends(port) == 1


def test_later_omission_is_not_deletion_or_reason_to_reopen(setup):
    port, provider, item = fixture(setup); run(setup, provider, item); port.rows = []
    assert o.recheck(setup[1], item['id'], provider)['reason'] == 'no_positive_discrepancy'
    assert o.read(setup[1], item['id'])['state'] == 'OBSERVED_RECEIVED' and sends(port) == 1


def test_known_returned_turn_must_match_and_null_returned_turn_uses_unique_pair(setup):
    port, provider, item = fixture(setup); port.returned_turn = None
    assert run(setup, provider, item)['state'] == 'OBSERVED_RECEIVED'


def test_wrong_known_returned_turn_cannot_certify_observation(setup):
    port, provider, item = fixture(setup); port.returned_turn = 'other-returned-turn'
    assert run(setup, provider, item)['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 1


def test_competing_caller_during_send_reads_only_and_never_invokes(setup):
    port, provider, item = fixture(setup)
    def compete():
        assert run(setup, provider, o.read(setup[1], item['id']))['state'] == 'DELIVERY_UNKNOWN'
    port.before_send = compete
    assert run(setup, provider, item)['state'] == 'OBSERVED_RECEIVED' and sends(port) == 1


def test_late_contradictory_send_result_appends_discrepancy_without_erasing_observation(setup):
    port, provider, item = fixture(setup); real_send = port.send_message
    def send_and_observe(thread_id, message):
        result = real_send(thread_id, message)
        assert run(setup, provider, o.read(setup[1], item['id']))['state'] == 'OBSERVED_RECEIVED'
        return {**result, 'turnId': 'contradictory-late-turn'}
    port.send_message = send_and_observe
    assert run(setup, provider, item)['state'] == 'OBSERVED_RECEIVED' and sends(port) == 1
    assert len(list((o._base(setup[1], item['id']) / 'discrepancies').glob('*.json'))) == 1


@pytest.mark.parametrize('case', ['actor', 'revision', 'provider', 'origin'])
def test_bad_authority_or_revision_refuses_before_new_invocation(setup, case):
    port, provider, item = fixture(setup); before = filemap(setup[1])
    actor, revision = 'parent', item['revision']
    if case == 'actor': actor = 'other-parent'
    elif case == 'revision': revision += 1
    elif case == 'provider': port.identity = {**port.identity, 'provider': 'native'}
    else:
        def denied(phase, pin): raise GateError('unverified origin or target lease')
        provider.verify_authority = denied
    with pytest.raises(GateError): o.run(setup[1], item['id'], actor, revision, provider)
    assert filemap(setup[1]) == before and not port.calls


def test_observation_bytes_cannot_be_rewritten_under_same_reference(setup):
    _port, provider, item = fixture(setup); run(setup, provider, item)
    current = o.read(setup[1], item['id'])
    path = o._base(setup[1], item['id']) / 'observations' / (current['observation_ref'] + '.json')
    value = read_json(path); value['selected_pair'][1]['text'] += ' Edited'
    atomic_json(path, value)
    with pytest.raises(GateError, match='terminal_evidence_changed'): o.read(setup[1], item['id'])


def test_unrelated_nonmessage_entry_needs_no_invented_message_fields(setup):
    port, provider, unknown = lost(setup)
    port.rows.append({'id': 'actual-tool-entry', 'role': 'tool', 'type': 'command'})
    assert run(setup, provider, unknown)['state'] == 'OBSERVED_RECEIVED' and sends(port) == 1


def test_source_drift_after_unknown_does_not_erase_historical_receipt(setup):
    port, provider, unknown = lost(setup); (setup[0] / 'later.txt').write_text('Later owner source')
    assert run(setup, provider, unknown)['state'] == 'OBSERVED_RECEIVED' and sends(port) == 1
