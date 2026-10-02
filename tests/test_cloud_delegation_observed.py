"""Synthetic delegation route; no live call, grant, install or publisher."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest
from test_continuation_dispatch import closed
from test_foundation import setup as foundation_setup

from agent_os import cloud_delegation_observed as d
from agent_os import cloud_observed as old
from agent_os.safeio import GateError, atomic_json, filemap, read_json, sha

setup = foundation_setup
SOURCE = '11111111-1111-7111-8111-111111111111'
TARGET = '22222222-2222-7222-8222-222222222222'
OTHER = '33333333-3333-7333-8333-333333333333'


class FixturePort:
    def __init__(self, pin):
        self.pin = pin
        self.identity = {'provider': 'cloud_threads', 'send_tool': 'cloud_threads.send_message',
                         'read_tool': 'cloud_threads.read', 'inspected_schema_sha256': None}
        self.calls, self.rows = [], []
        self.status = 'received'; self.turn = 'fixture-genuine-admitted-turn'
        self.lose_result = False; self.fail_read = False; self.pages = None
        self.before_send = lambda: None; self.before_read = lambda: None

    def send_message(self, target, text):
        self.calls.append(('send', target, text)); self.before_send()
        wire = json.loads(text.split('\n', 1)[1]); challenge = wire['challenge']
        value = {'schema': 'agentos.cloud-delegation-observed-ack/v1', 'acceptance_scope': 'observed_received_only',
                 'status': self.status, 'ledger_id': challenge['ledger_id'], 'operation_key': challenge['operation_key'],
                 'delivery_generation': challenge['delivery_generation'], 'delivery_nonce': challenge['delivery_nonce'],
                 'request_sha256': wire['request_sha256'], 'source_thread_id': self.pin['source_thread_id'],
                 'target_thread_id': target, 'workstream_id': challenge['workstream_id']}
        if self.status == 'received_refused': value['refusal_reason'] = 'Fixture refusal'
        envelope = '<codex_delegation><source_thread_id>' + self.pin['source_thread_id'] + '</source_thread_id><input>' + text + '</input></codex_delegation>'
        self.rows = [{'id': 'fixture-assistant', 'turnId': 'fixture-genuine-admitted-turn', 'role': 'assistant',
                      'text': 'AGENTOS_CLOUD_DELEGATION_ACK_V1\n' + json.dumps(value)},
                     {'id': 'fixture-ingress', 'turnId': 'fixture-genuine-admitted-turn', 'role': 'tool', 'text': envelope}]
        if self.lose_result: raise TimeoutError('Actual fixture result lost after delivery')
        return {'threadId': target, 'turnId': self.turn, 'admissionOutcome': 'accepted'}

    def read(self, target, *, cursor, limit):
        self.calls.append(('read', target, cursor)); self.before_read(); assert limit == 50
        if self.fail_read: raise TimeoutError('Fixture read unavailable')
        page = self.pages(cursor) if self.pages else {'items': self.rows, 'nextCursor': None}
        return d.RawRead(json.dumps(page, sort_keys=True).encode(), 'fixture-read-reference')


def fixture(setup):
    task = closed(setup)
    pin = {'provider': 'cloud_threads', 'adapter_sha256': d.ADAPTER_SHA256, 'parent_owner': 'parent',
           'target_owner': 'independent-reviewer', 'source_thread_id': SOURCE, 'target_thread_id': TARGET,
           'workstream_id': 'fixture-receipt-only', 'ingress_kind': d.INGRESS,
           'serialization_profile': d.PROFILE, 'serialization_profile_sha256': d.PROFILE_SHA256}
    item = d.prepare(setup[1], setup[0], task, 'parent', pin, payload='Receipt-only canary. No commands or business actions.')
    port = FixturePort(pin)
    provider = d.Provider(port, pin, verify_authority=lambda phase, pin: None,
                          verify_complete=lambda raw, selected: None, verify_route=lambda phase, pin: None,
                          verify_admission=lambda returned, pin: None)
    return port, provider, item


def run(setup, provider, item): return d.run(setup[1], item['id'], 'parent', item['revision'], provider)
def sends(port): return sum(x[0] == 'send' for x in port.calls)


def admitted_unknown(setup):
    port, provider, item = fixture(setup); port.fail_read = True
    assert run(setup, provider, item)['state'] == 'DELIVERY_UNKNOWN'
    port.fail_read = False
    return port, provider, d.read(setup[1], item['id'])


@pytest.mark.parametrize('status', ['received', 'received_refused'])
def test_exact_tool_wrapper_pair_observed_only_in_admitted_turn_and_replay_no_io(setup, status):
    port, provider, item = fixture(setup); port.status = status
    result = run(setup, provider, item)
    assert result['state'] == ('OBSERVED_RECEIVED' if status == 'received' else 'OBSERVED_RECEIVED_REFUSED')
    assert not result['work_acceptance_proven'] and not result['project_completion_proven'] and not result['coordinator_state_changed']
    current = d.read(setup[1], item['id']); before = filemap(setup[1]); calls = copy.deepcopy(port.calls)
    observation = read_json(d._base(setup[1], item['id']) / 'observations' / (current['observation_ref'] + '.json'))
    assert observation['selected_pair'][0]['role'] == 'tool'
    assert observation['selected_pair'][0]['text'] == item['expected_ingress']
    assert observation['original_send_text'] == item['text']
    assert observation['original_send_text_sha256'] == sha(item['text'].encode())
    assert observation['expected_ingress_sha256'] == sha(item['expected_ingress'].encode())
    assert observation['send_result']['turnId'] == observation['selected_pair'][0]['turnId'] == observation['selected_pair'][1]['turnId']
    assert observation['original_response_sha256'] == sha(json.dumps({'items': port.rows, 'nextCursor': None}, sort_keys=True).encode())
    assert run(setup, provider, current)['state'] == current['state']
    assert filemap(setup[1]) == before and port.calls == calls and sends(port) == 1
    assert not (setup[1] / 'state/continuations').exists()


def test_exact_canonical_challenge_keys_hash_and_distinct_P_E_hashes(setup):
    _port, _provider, item = fixture(setup)
    keys = {'schema','acceptance_scope','ingress_kind','serialization_profile','serialization_profile_sha256',
            'ledger_id','operation_key','delivery_generation','delivery_nonce','source_thread_id','target_thread_id',
            'workstream_id','mapping_digest','adapter_sha256','stage_identity_sha256','journal_revision_at_admission',
            'payload','payload_sha256'}
    assert set(item['challenge']) == keys
    encoded = json.dumps(item['challenge'], ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    assert item['request_sha256'] == hashlib.sha256(encoded).hexdigest()
    assert item['text_sha256'] == hashlib.sha256(item['text'].encode()).hexdigest()
    assert item['ingress_sha256'] == hashlib.sha256(item['expected_ingress'].encode()).hexdigest()
    assert len({item['request_sha256'], item['text_sha256'], item['ingress_sha256']}) == 3
    assert item['challenge']['journal_revision_at_admission'] == 2


def test_unicode_and_payload_whitespace_remain_exact_without_normalization(setup):
    _port, provider, item = fixture(setup)
    payload = '  \u041f\u0440\u0438\u0432\u0435\u0442 🚀 e\u0301  '
    current = d.prepare(setup[1], setup[0], item['stage']['task_id'], 'parent',
                        {**provider.pin, 'workstream_id':'unicode-receipt-only'}, payload=payload)
    assert current['challenge']['payload'] == payload
    assert current['challenge']['payload_sha256'] == hashlib.sha256(payload.encode('utf-8')).hexdigest()
    assert '\u041f\u0440\u0438\u0432\u0435\u0442 🚀 e\u0301' in current['text']
    assert '\\u041f' not in current['text']


def test_competing_caller_during_send_cannot_send_or_guess_missing_admission(setup):
    port, provider, item = fixture(setup)
    def competing():
        assert run(setup, provider, d.read(setup[1], item['id']))['state'] == 'DELIVERY_UNKNOWN'
    port.before_send = competing
    assert run(setup, provider, item)['state'] == 'OBSERVED_RECEIVED' and sends(port) == 1


def test_terminal_evidence_cannot_be_rewritten_under_same_reference(setup):
    _port, provider, item = fixture(setup); run(setup, provider, item)
    current = d.read(setup[1], item['id'])
    path = d._base(setup[1], item['id']) / 'observations' / (current['observation_ref'] + '.json')
    value = read_json(path); value['selected_pair'][0]['role'] = 'user'; atomic_json(path, value)
    with pytest.raises(GateError, match='evidence_changed'): d.read(setup[1], item['id'])


def test_commits_complete_source_wrapper_payload_before_one_send_without_locks(setup):
    port, provider, item = fixture(setup)
    def committed():
        assert not d._lock(setup[1], item['id']).exists()
        current = d.read(setup[1], item['id'])
        assert current['state'] == 'DELIVERY_UNKNOWN' and current['revision'] == 2
        assert current['text'] == port.calls[0][2] and current['pin']['source_thread_id'] == SOURCE
        assert current['expected_ingress'] == '<codex_delegation><source_thread_id>' + SOURCE + '</source_thread_id><input>' + current['text'] + '</input></codex_delegation>'
    port.before_send = committed; port.before_read = committed
    assert run(setup, provider, item)['state'] == 'OBSERVED_RECEIVED'


@pytest.mark.parametrize('case', ['source', 'stripped', 'inner-only', 'nested', 'wrapper-space', 'attribute', 'namespace',
                                  'prefix', 'suffix', 'payload', 'entity', 'cdata', 'role-user', 'role-assistant',
                                  'wrong-ingress-turn', 'wrong-ack-turn', 'both-other-turn', 'truncated', 'summary',
                                  'partial-page', 'wrong-provider', 'wrong-target', 'same-id', 'duplicate-ingress',
                                  'duplicate-ack', 'ack-source', 'ack-nonce', 'ack-gen', 'ack-digest', 'ack-ledger',
                                  'ack-operation', 'ack-target', 'ack-workstream', 'ack-extra', 'ack-bool', 'ack-duplicate-key',
                                  'ack-CRLF', 'ack-extra-LF', 'ack-trailing-LF', 'ack-leading-space', 'ack-quoted', 'ack-clipped'])
def test_substitution_truncation_replay_or_wrong_profile_remains_unknown(setup, case):
    port, provider, unknown = admitted_unknown(setup); assistant, ingress = port.rows
    if case == 'source': ingress['text'] = ingress['text'].replace(SOURCE, OTHER, 1)
    elif case == 'stripped': ingress['text'] = unknown['text']
    elif case == 'inner-only': ingress['text'] = '<input>' + unknown['text'] + '</input>'
    elif case == 'nested': ingress['text'] = '<codex_delegation>' + ingress['text'] + '</codex_delegation>'
    elif case == 'wrapper-space': ingress['text'] = ingress['text'].replace('<input>', '<input> ')
    elif case == 'attribute': ingress['text'] = ingress['text'].replace('<codex_delegation>', '<codex_delegation x="1">')
    elif case == 'namespace': ingress['text'] = ingress['text'].replace('<codex_delegation>', '<codex_delegation xmlns="x">')
    elif case == 'prefix': ingress['text'] = 'Note\n' + ingress['text']
    elif case == 'suffix': ingress['text'] += '\n'
    elif case == 'payload': ingress['text'] = ingress['text'].replace('No commands', 'Run commands')
    elif case == 'entity': ingress['text'] = ingress['text'].replace('<input>', '&lt;input&gt;')
    elif case == 'cdata': ingress['text'] = ingress['text'].replace('<input>', '<input><![CDATA[').replace('</input>', ']]></input>')
    elif case == 'role-user': ingress['role'] = 'user'
    elif case == 'role-assistant': ingress['role'] = 'assistant'
    elif case == 'wrong-ingress-turn': ingress['turnId'] = 'other-turn'
    elif case == 'wrong-ack-turn': assistant['turnId'] = 'other-turn'
    elif case == 'both-other-turn': ingress['turnId'] = assistant['turnId'] = 'other-turn'
    elif case == 'truncated': ingress['truncated'] = True
    elif case == 'summary': assistant['summary'] = True
    elif case == 'partial-page': port.pages = lambda cursor: {'items': port.rows, 'partial': True}
    elif case == 'wrong-provider': port.pages = lambda cursor: {'items': port.rows, 'provider': 'native'}
    elif case == 'wrong-target': port.pages = lambda cursor: {'items': port.rows, 'threadId': OTHER}
    elif case == 'same-id': assistant['id'] = ingress['id']
    elif case.startswith('duplicate-'):
        extra = copy.deepcopy(ingress if case == 'duplicate-ingress' else assistant); extra['id'] += '-other'; port.rows.append(extra)
    elif case == 'ack-CRLF': assistant['text'] = assistant['text'].replace('\n', '\r\n', 1)
    elif case == 'ack-extra-LF': assistant['text'] = assistant['text'].replace('\n', '\n\n', 1)
    elif case == 'ack-trailing-LF': assistant['text'] += '\n'
    elif case == 'ack-leading-space': assistant['text'] = assistant['text'].replace('\n', '\n ', 1)
    elif case == 'ack-quoted': assistant['text'] = '> ' + assistant['text']
    elif case == 'ack-clipped': assistant['text'] = assistant['text'][:-1]
    elif case == 'ack-duplicate-key': assistant['text'] = assistant['text'].replace('"status": "received"', '"status": "received", "status": "received"')
    else:
        value = json.loads(assistant['text'].split('\n', 1)[1])
        field = {'ack-source':'source_thread_id','ack-nonce':'delivery_nonce','ack-gen':'delivery_generation',
                 'ack-digest':'request_sha256','ack-ledger':'ledger_id','ack-operation':'operation_key',
                 'ack-target':'target_thread_id','ack-workstream':'workstream_id','ack-extra':'extra',
                 'ack-bool':'delivery_generation'}[case]
        value[field] = True if case == 'ack-bool' else 2 if case == 'ack-gen' else 'wrong'
        assistant['text'] = d.ACK_PREFIX + json.dumps(value)
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    assert run(setup, provider, d.read(setup[1], unknown['id']))['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 1
    assert not (d._base(setup[1], unknown['id']) / 'observations').exists()


@pytest.mark.parametrize('case', ['split-pages', 'split-reads'])
def test_no_pair_stitched_across_original_responses(setup, case):
    port, provider, unknown = admitted_unknown(setup); assistant, ingress = copy.deepcopy(port.rows)
    if case == 'split-pages':
        port.pages = lambda cursor: {'items': [ingress] if cursor is None else [assistant], 'nextCursor': 'next' if cursor is None else None}
        assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    else:
        port.rows = [ingress]; assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
        port.rows = [assistant]; assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    assert sends(port) == 1


def test_later_page_requires_complete_pair_by_itself(setup):
    port, provider, unknown = admitted_unknown(setup); rows = copy.deepcopy(port.rows)
    port.pages = lambda cursor: {'items': rows[1:] if cursor is None else rows, 'nextCursor': 'next' if cursor is None else 'unread-rest'}
    assert run(setup, provider, unknown)['state'] == 'OBSERVED_RECEIVED' and sends(port) == 1


@pytest.mark.parametrize('turn', [None, '', 'other-admitted-turn'])
def test_missing_null_or_wrong_genuine_admitted_turn_never_guesses_from_correct_ack(setup, turn):
    port, provider, item = fixture(setup); port.turn = turn
    assert run(setup, provider, item)['state'] == 'DELIVERY_UNKNOWN'
    assert run(setup, provider, d.read(setup[1], item['id']))['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 1


def test_lost_send_result_with_exact_pair_stays_unknown_without_admission_or_resend(setup):
    port, provider, item = fixture(setup); port.lose_result = True
    assert run(setup, provider, item)['state'] == 'DELIVERY_UNKNOWN'
    unknown = d.read(setup[1], item['id'])
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 1
    assert not any(x[0] == 'read' for x in port.calls)


@pytest.mark.parametrize('gate', ['authority', 'route', 'admission', 'complete'])
def test_unverified_origin_source_serialization_admission_or_full_record_cannot_certify(setup, gate):
    port, provider, item = fixture(setup)
    def denied(*args): raise GateError('actual fixture verification denied')
    if gate == 'authority': provider.verify_authority = denied
    elif gate == 'route': provider.verify_route = denied
    elif gate == 'admission': provider.verify_admission = denied
    else: provider.verify_complete = denied
    if gate in {'authority', 'route'}:
        before = filemap(setup[1])
        with pytest.raises(GateError): run(setup, provider, item)
        assert filemap(setup[1]) == before and not port.calls
    else:
        assert run(setup, provider, item)['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 1


@pytest.mark.parametrize('source', [SOURCE.upper(), ' ' + SOURCE, 'not-a-thread'])
def test_source_thread_id_has_exact_supported_representation(setup, source):
    if source == SOURCE: source = SOURCE.replace('11111111', 'aaaaaaaa').upper()
    _port, provider, item = fixture(setup)
    with pytest.raises(GateError): d.prepare(setup[1], setup[0], item['stage']['task_id'], 'parent',
                                           {**provider.pin, 'source_thread_id': source}, payload='Receipt-only')


@pytest.mark.parametrize('payload', ['Contains < tag', 'Contains > close', 'Contains & entity'])
def test_unsupported_literal_profile_refuses_before_send(setup, payload):
    port, provider, item = fixture(setup)
    with pytest.raises(GateError, match='unsupported_delegation_literal_payload'):
        d.prepare(setup[1], setup[0], item['stage']['task_id'], 'parent',
                  {**provider.pin, 'workstream_id': 'different-profile-fixture'}, payload=payload)
    assert not port.calls


def test_old_user_only_adapter_still_refuses_exact_tool_wrapper_with_correct_old_ack(setup):
    _port, provider, item = fixture(setup)
    pin = {k: provider.pin[k] for k in ('provider','parent_owner','target_owner','target_thread_id','workstream_id')}
    pin['adapter_sha256'] = old.ADAPTER_SHA256
    legacy = old.prepare(setup[1], setup[0], item['stage']['task_id'], 'parent', pin, payload='Old receipt-only vector')
    wrapper = '<codex_delegation><source_thread_id>' + SOURCE + '</source_thread_id><input>' + legacy['text'] + '</input></codex_delegation>'
    page = {'items':[{'id':'tool-ingress','role':'tool','turnId':'T','text':wrapper},
                     {'id':'assistant-ack','role':'assistant','turnId':'T','text':old.ACK_PREFIX+json.dumps(old.ack(legacy))}]}
    assert old._pair(page, legacy) is None


@pytest.mark.parametrize('failure', ['evidence', 'cas-before', 'cas-after'])
def test_loss_keeps_unknown_or_known_historical_terminal_without_resend(setup, monkeypatch, failure):
    port, provider, unknown = admitted_unknown(setup); append, atomic = d.create_only_bytes, d.atomic_json
    if failure == 'evidence':
        def bad(path, data): raise OSError('Fixture evidence failed')
        monkeypatch.setattr(d, 'create_only_bytes', bad)
    else:
        def lost_write(path, value):
            if failure == 'cas-after': atomic(path, value)
            raise OSError('Fixture CAS loss')
        monkeypatch.setattr(d, 'atomic_json', lost_write)
    assert run(setup, provider, unknown)['state'] == ('OBSERVED_RECEIVED' if failure == 'cas-after' else 'DELIVERY_UNKNOWN')
    monkeypatch.setattr(d, 'create_only_bytes', append); monkeypatch.setattr(d, 'atomic_json', atomic)
    if failure == 'cas-before':
        port.rows = []
        assert run(setup, provider, d.read(setup[1], unknown['id']))['state'] == 'DELIVERY_UNKNOWN'
    else:
        assert run(setup, provider, d.read(setup[1], unknown['id']))['state'] == 'OBSERVED_RECEIVED'
    assert sends(port) == 1


def test_stale_cas_preserves_uncommitted_evidence_and_unknown(setup):
    port, provider, unknown = admitted_unknown(setup)
    def changed():
        item = d.read(setup[1], unknown['id']); item['revision'] += 1; atomic_json(d._path(setup[1], item['id']), item)
    port.before_read = changed
    assert run(setup, provider, unknown)['reason'] == 'stale_observation_cas_refused'
    assert d.read(setup[1], unknown['id'])['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 1


def test_previous_complete_pair_cannot_certify_new_nonce_workstream(setup):
    port, provider, unknown = admitted_unknown(setup); rows = copy.deepcopy(port.rows)
    pin = {**provider.pin, 'workstream_id': 'another-authorized-fixture'}
    item = d.prepare(setup[1], setup[0], unknown['stage']['task_id'], 'parent', pin, payload='Distinct canary')
    next_port = FixturePort(pin); next_port.fail_read = True
    next_provider = d.Provider(next_port, pin, verify_authority=lambda *args:None, verify_route=lambda *args:None,
                               verify_admission=lambda *args:None, verify_complete=lambda *args:None)
    run(setup, next_provider, item); next_port.fail_read = False; next_port.rows = rows
    assert run(setup, next_provider, d.read(setup[1], item['id']))['state'] == 'DELIVERY_UNKNOWN'
    assert sends(port) == sends(next_port) == 1


def test_later_wrapper_mutation_appends_discrepancy_without_erasing_historical_fact(setup):
    port, provider, item = fixture(setup); run(setup, provider, item)
    current = d.read(setup[1], item['id']); evidence = d._base(setup[1], item['id']) / 'observations' / (current['observation_ref'] + '.json')
    original, journal = evidence.read_bytes(), d._path(setup[1], item['id']).read_bytes()
    port.rows[1]['text'] = port.rows[1]['text'].replace(SOURCE, OTHER, 1)
    assert d.recheck(setup[1], item['id'], provider)['reason'] == 'later_discrepancy_appended'
    assert evidence.read_bytes() == original and d._path(setup[1], item['id']).read_bytes() == journal
    assert run(setup, provider, current)['state'] == 'OBSERVED_RECEIVED' and sends(port) == 1


@pytest.mark.parametrize('change', ['extra-field', 'wrong-nonce', 'trailing-LF', 'duplicate-key'])
@pytest.mark.parametrize('competitor_first', [False, True])
def test_ack_ambiguity_reviewer_repro_fails_closed(setup, change, competitor_first):
    port, provider, item = admitted_unknown(setup)
    other = copy.deepcopy(port.rows[0]); other['id'] = 'independent-conflicting-ack'
    if change == 'trailing-LF': other['text'] += '\n'
    elif change == 'duplicate-key':
        other['text'] = other['text'].replace('{', '{"status":"received_refused",', 1)
    else:
        body = json.loads(other['text'].split('\n', 1)[1])
        if change == 'extra-field': body.update(status='received_refused', refusal_reason='Do not accept', extra=True)
        else: body['delivery_nonce'] = '0' * 32
        other['text'] = d.ACK_PREFIX + json.dumps(body)
    port.rows.insert(0 if competitor_first else len(port.rows), other)
    result = run(setup, provider, item)
    assert sends(port) == 1
    assert result['state'] == 'DELIVERY_UNKNOWN', result
    journal = d._path(setup[1], item['id']).read_bytes()
    assert not list((d._base(setup[1], item['id']) / 'observations').glob('*.json'))
    assert run(setup, provider, d.read(setup[1], item['id']))['state'] == 'DELIVERY_UNKNOWN'
    assert d._path(setup[1], item['id']).read_bytes() == journal and sends(port) == 1


@pytest.mark.parametrize('change', ['valid-refusal', 'duplicate-valid', 'CRLF', 'missing-LF', 'malformed-json', 'summary', 'truncated'])
@pytest.mark.parametrize('competitor_first', [False, True])
def test_ack_ambiguity_all_same_turn_candidates_participate(setup, change, competitor_first):
    port, provider, item = admitted_unknown(setup)
    other = copy.deepcopy(port.rows[0]); other['id'] = 'another-same-turn-candidate'
    if change == 'valid-refusal':
        body = json.loads(other['text'].split('\n', 1)[1])
        body.update(status='received_refused', refusal_reason='Do not accept')
        other['text'] = d.ACK_PREFIX + json.dumps(body)
    elif change == 'CRLF': other['text'] = other['text'].replace('\n', '\r\n', 1)
    elif change == 'missing-LF': other['text'] = other['text'].replace('\n', '', 1)
    elif change == 'malformed-json': other['text'] = d.ACK_PREFIX + '{'
    elif change in {'summary', 'truncated'}: other[change] = True
    port.rows.insert(0 if competitor_first else len(port.rows), other)
    journal = d._path(setup[1], item['id']).read_bytes()
    for _ in range(2):
        result = run(setup, provider, d.read(setup[1], item['id']))
        assert result['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 1
        assert d._path(setup[1], item['id']).read_bytes() == journal
        assert not list((d._base(setup[1], item['id']) / 'observations').glob('*.json'))


@pytest.mark.parametrize('change', ['valid', 'valid-refusal', 'wrong-nonce', 'trailing-LF', 'CRLF', 'malformed-json', 'summary', 'truncated'])
def test_ack_ambiguity_other_turn_history_does_not_compete(setup, change):
    port, provider, item = admitted_unknown(setup)
    other = copy.deepcopy(port.rows[0]); other.update(id='unrelated-ack', turnId='another-actual-turn')
    if change in {'valid-refusal', 'wrong-nonce'}:
        body = json.loads(other['text'].split('\n', 1)[1])
        if change == 'valid-refusal': body.update(status='received_refused', refusal_reason='Other turn refusal')
        else: body['delivery_nonce'] = '0' * 32
        other['text'] = d.ACK_PREFIX + json.dumps(body)
    elif change == 'trailing-LF': other['text'] += '\n'
    elif change == 'CRLF': other['text'] = other['text'].replace('\n', '\r\n', 1)
    elif change == 'malformed-json': other['text'] = d.ACK_PREFIX + '{'
    elif change in {'summary', 'truncated'}: other[change] = True
    port.rows.insert(0, other)
    assert run(setup, provider, item)['state'] == 'OBSERVED_RECEIVED' and sends(port) == 1
    current = d.read(setup[1], item['id'])
    observed = read_json(d._base(setup[1], item['id']) / 'observations' / (current['observation_ref'] + '.json'))
    assert observed['selected_pair'][1]['id'] == 'fixture-assistant'
    assert all(row['turnId'] == port.turn for row in observed['selected_pair'])


@pytest.mark.parametrize('kind', ['generic', 'quoted', 'fenced', 'user', 'tool'])
def test_ack_ambiguity_same_turn_non_candidates_remain_permitted(setup, kind):
    port, provider, item = admitted_unknown(setup)
    other = copy.deepcopy(port.rows[0]); other['id'] = 'unrelated-same-turn-message'
    if kind == 'generic': other['text'] = 'Ordinary assistant activity'
    elif kind == 'quoted': other['text'] = '> ' + other['text']
    elif kind == 'fenced': other['text'] = '```\n' + other['text'] + '\n```'
    else: other['role'] = kind
    port.rows.insert(0, other)
    assert run(setup, provider, item)['state'] == 'OBSERVED_RECEIVED' and sends(port) == 1
