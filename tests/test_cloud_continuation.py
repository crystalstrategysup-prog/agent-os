"""Owner-port fixtures using cloud fields. Never evidence of real cloud adoption."""
from __future__ import annotations

import copy
import json

import pytest
from test_continuation_causal import mapping, queued_causal
from test_continuation_dispatch import queued
from test_foundation import setup as foundation_setup

from agent_os import cloud_continuation as cloud
from agent_os import continuation as c
from agent_os import continuation_causal as v3
from agent_os.safeio import GateError, atomic_json, filemap

setup = foundation_setup


class FixturePort:
    identity = cloud.IDENTITY

    def __init__(self, home):
        self.home, self.rows, self.calls = home, [], []
        self.lose_response = False
        self.status = 'received'
        self.returned_turn = 'fixture-actual-cloud-turn'
        self.returned_thread = mapping()['target_thread_id']
        self.before_send = lambda: None
        self.before_read = lambda: None
        self.page = None

    def send_message(self, thread_id, message):
        self.calls.append(('send', thread_id, message)); self.before_send()
        wire = json.loads(message[len(v3.REQUEST_PREFIX):])
        request = {'challenge': wire['challenge'], 'request_sha256': wire['request_sha256']}
        ack = v3.ack(request, self.status, 'Fixture refused review.' if self.status == 'received_refused' else None)
        self.rows = [{'id': 'fixture-assistant', 'turnId': 'fixture-actual-cloud-turn', 'role': 'assistant',
                      'text': v3.ACK_PREFIX + json.dumps(ack)},
                     {'id': 'fixture-user', 'turnId': 'fixture-actual-cloud-turn', 'role': 'user', 'text': message}]
        if self.lose_response:
            raise TimeoutError('fixture response lost after durable user input')
        return {'threadId': self.returned_thread, 'turnId': self.returned_turn, 'admissionOutcome': 'accepted'}

    def read(self, thread_id, *, cursor, limit):
        self.calls.append(('read', thread_id, cursor)); self.before_read()
        assert limit == 50
        if self.page:
            return copy.deepcopy(self.page(cursor))
        return {'items': copy.deepcopy(self.rows), 'nextCursor': None,
                'latestTurn': {'id': 'unrelated-turn', 'status': 'completed'}}


def fixture(setup):
    item = queued_causal(setup)
    port = FixturePort(setup[1]); gates = []
    provider = cloud.CloudProvider(port, mapping(), verify_authority=lambda phase, pin: gates.append((phase, pin)))
    return port, provider, item, gates


def run(setup, provider, item):
    return cloud.run(setup[1], item['id'], 'parent', item['revision'], provider, payload='Review frozen source.')


def sends(port):
    return sum(x[0] == 'send' for x in port.calls)


def lost(setup):
    port, provider, item, gates = fixture(setup); port.lose_response = True
    assert run(setup, provider, item)['state'] == 'DELIVERY_UNKNOWN'
    return port, provider, c.read(setup[1], item['id']), gates


@pytest.mark.parametrize('status', ['received', 'received_refused'])
def test_explicit_pair_is_receipt_only_and_duplicate_never_sends(setup, status):
    port, provider, item, gates = fixture(setup); port.status = status
    result = run(setup, provider, item)
    assert result['state'] == ('RECEIVED' if status == 'received' else 'RECEIVED_REFUSED')
    assert result['work_acceptance_proven'] is False and result['project_completion_proven'] is False
    current = c.read(setup[1], item['id']); before = filemap(setup[1])
    assert run(setup, provider, current)['reason'] == 'already_received_no_send'
    assert filemap(setup[1]) == before and sends(port) == 1
    assert [g[0] for g in gates].count('record-receipt') == 1


def test_challenge_committed_before_send_and_all_io_releases_local_locks(setup):
    port, provider, item, _ = fixture(setup)
    def unlocked():
        assert not (setup[1] / 'state/continuations.lock').exists()
        assert not cloud._lock_path(setup[1], item['id']).exists()
        current = c.read(setup[1], item['id'])
        assert current['state'] == 'DELIVERY_UNKNOWN'
        assert cloud._load_intent(setup[1], current)['state'] == 'MAY_HAVE_BEEN_SENT'
        assert v3.validate_request(current)['text'] == port.calls[0][2]
    port.before_send = unlocked; port.before_read = unlocked
    assert run(setup, provider, item)['state'] == 'RECEIVED'


def test_lost_send_response_recovered_from_read_without_resend_or_timestamps(setup):
    port, provider, unknown, _ = lost(setup)
    assert cloud._load_intent(setup[1], unknown)['actual_turn_id'] is None
    assert run(setup, provider, unknown)['state'] == 'RECEIVED'
    assert sends(port) == 1 and not any('At' in k for r in port.rows for k in r)


@pytest.mark.parametrize('case', ['generic-activity', 'tool', 'user-ack', 'quoted', 'fenced', 'wrong-turn',
                                  'no-user', 'no-ack', 'truncated', 'partial-page', 'wrong-user', 'duplicate-user',
                                  'duplicate-ack', 'same-id', 'wrong-digest', 'wrong-nonce', 'wrong-generation',
                                  'wrong-ledger', 'wrong-operation', 'wrong-target', 'wrong-workstream', 'work-accepted'])
def test_ambiguous_incomplete_or_unbound_evidence_never_receives_or_resends(setup, case):
    port, provider, unknown, _ = lost(setup); assistant, user = port.rows
    if case == 'generic-activity': assistant['text'] = 'Working on review; done.'
    elif case == 'tool': assistant['role'] = 'tool'
    elif case == 'user-ack': assistant['role'] = 'user'
    elif case == 'quoted': assistant['text'] = '> ' + assistant['text']
    elif case == 'fenced': assistant['text'] = '```\n' + assistant['text'] + '\n```'
    elif case == 'wrong-turn': assistant['turnId'] = 'other-turn'
    elif case == 'no-user': port.rows = [assistant]
    elif case == 'no-ack': port.rows = [user]
    elif case == 'truncated': assistant['truncated'] = True
    elif case == 'partial-page': port.page = lambda cursor: {'items': port.rows, 'partial': True}
    elif case == 'wrong-user': user['text'] += '\nEdited'
    elif case in {'duplicate-user', 'duplicate-ack'}:
        extra = copy.deepcopy(user if case == 'duplicate-user' else assistant); extra['id'] += '-duplicate'; port.rows.append(extra)
    elif case == 'same-id': assistant['id'] = user['id']
    else:
        ack = json.loads(assistant['text'][len(v3.ACK_PREFIX):])
        field = {'wrong-digest': 'request_sha256', 'wrong-nonce': 'delivery_nonce',
                 'wrong-generation': 'delivery_generation', 'wrong-ledger': 'ledger_id',
                 'wrong-operation': 'operation_key', 'wrong-target': 'target_thread_id',
                 'wrong-workstream': 'workstream_id', 'work-accepted': 'status'}[case]
        ack[field] = 2 if field == 'delivery_generation' else 'wrong'
        assistant['text'] = v3.ACK_PREFIX + json.dumps(ack)
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    assert run(setup, provider, c.read(setup[1], unknown['id']))['state'] == 'DELIVERY_UNKNOWN'
    assert sends(port) == 1


def test_complete_pair_across_pages_does_not_need_timestamp_or_snapshot_absence(setup):
    port, provider, unknown, _ = lost(setup)
    assistant, user = copy.deepcopy(port.rows)
    port.page = lambda cursor: {'items': [assistant] if cursor is None else [user],
                                'nextCursor': 'older' if cursor is None else 'still-more-omitted'}
    # Four bounded pages can overlap; immutable identical events deduplicate.
    def pages(cursor):
        if cursor is None: return {'items': [assistant], 'nextCursor': 'older'}
        if cursor == 'older': return {'items': [user], 'nextCursor': 'more'}
        return {'items': [], 'nextCursor': 'more2' if cursor == 'more' else 'unread-rest'}
    port.page = pages
    assert run(setup, provider, unknown)['state'] == 'RECEIVED'
    assert len([x for x in port.calls if x[0] == 'read']) == 4 and sends(port) == 1


def test_complete_positive_witnesses_can_span_bounded_reads(setup):
    port, provider, unknown, _ = lost(setup); assistant, user = copy.deepcopy(port.rows)
    port.rows = [user]
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    port.rows = [assistant]
    assert run(setup, provider, c.read(setup[1], unknown['id']))['state'] == 'RECEIVED'
    assert sends(port) == 1


def test_cached_mutating_identity_permanently_holds_even_when_later_restored(setup):
    port, provider, unknown, _ = lost(setup); assistant, user = copy.deepcopy(port.rows)
    port.rows = [user]; run(setup, provider, unknown)
    user['text'] += ' altered'; port.rows = [assistant, user]
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    port.rows = [assistant]
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 1


def test_mutating_identity_across_pages_cannot_later_restore_the_pair(setup):
    port, provider, unknown, _ = lost(setup); assistant, user = copy.deepcopy(port.rows)
    changed = copy.deepcopy(user); changed['text'] += ' changed'
    port.page = lambda cursor: {'items': [assistant, user] if cursor is None else [changed],
                                'nextCursor': 'older' if cursor is None else None}
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    port.page = None
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 1


def test_contradictory_received_and_refused_acks_remain_unknown(setup):
    port, provider, unknown, _ = lost(setup)
    ack = v3.ack(unknown['delivery_request'], 'received_refused', 'Contradictory fixture refusal')
    port.rows.append({'id': 'other-assistant', 'turnId': 'fixture-actual-cloud-turn', 'role': 'assistant',
                      'text': v3.ACK_PREFIX + json.dumps(ack)})
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 1


@pytest.mark.parametrize('case', ['pin', 'authority', 'stale-revision', 'owner', 'identity'])
def test_changed_contract_or_authority_cannot_send_or_consume(setup, case):
    port, provider, item, _ = fixture(setup); before = filemap(setup[1])
    actor, revision = 'parent', item['revision']
    if case == 'pin': provider.mapping['target_owner'] = 'other-owner'
    elif case == 'authority':
        def denied(phase, pin): raise GateError('fixture owner lease denied')
        provider.verify_authority = denied
    elif case == 'stale-revision': revision += 1
    elif case == 'owner': actor = 'other-parent'
    else: port.identity = {**cloud.IDENTITY, 'contract_sha256': '0' * 64}
    with pytest.raises(GateError):
        cloud.run(setup[1], item['id'], actor, revision, provider, payload='Review')
    assert port.calls == [] and filemap(setup[1]) == before


def test_provider_pin_changed_during_send_cannot_relabel_other_target_evidence(setup):
    port, provider, item, _ = fixture(setup)
    def changed(): provider.mapping['target_thread_id'] = 'other-cloud-target'
    port.before_send = changed
    assert run(setup, provider, item)['state'] == 'DELIVERY_UNKNOWN'
    assert sends(port) == 1 and not any(call[0] == 'read' for call in port.calls)
    with pytest.raises(GateError, match='committed_pin_changed'):
        run(setup, provider, c.read(setup[1], item['id']))


def test_admitted_receipt_survives_later_source_edit_without_new_admission(setup):
    port, provider, unknown, _ = lost(setup)
    (setup[0] / 'later-source.txt').write_text('Later owner work')
    assert run(setup, provider, unknown)['state'] == 'RECEIVED' and sends(port) == 1


def test_failed_intent_write_commits_unknown_without_sending_and_never_retries(setup, monkeypatch):
    port, provider, item, _ = fixture(setup)
    real = cloud.atomic_json
    def failed(path, value): raise OSError('fixture intent persistence failed')
    monkeypatch.setattr(cloud, 'atomic_json', failed)
    with pytest.raises(OSError): run(setup, provider, item)
    unknown = c.read(setup[1], item['id'])
    assert unknown['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 0
    monkeypatch.setattr(cloud, 'atomic_json', real)
    assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 0


@pytest.mark.parametrize('case', ['null-turn', 'wrong-turn', 'wrong-thread'])
def test_send_admission_and_returned_turn_only_constrain_positive_pair(setup, case):
    port, provider, item, _ = fixture(setup)
    if case == 'null-turn': port.returned_turn = None
    elif case == 'wrong-turn': port.returned_turn = 'unrelated-turn'
    else: port.returned_thread = 'other-thread'
    assert run(setup, provider, item)['state'] == ('RECEIVED' if case == 'null-turn' else 'DELIVERY_UNKNOWN')
    assert sends(port) == 1


def test_existing_unknown_with_lost_intent_is_query_only(setup):
    port, provider, unknown, _ = lost(setup)
    cloud._intent_path(setup[1], unknown).unlink()
    assert run(setup, provider, unknown)['state'] == 'RECEIVED' and sends(port) == 1


def test_two_callers_interleave_during_send_but_only_one_invokes(setup):
    port, provider, item, _ = fixture(setup)
    def competing():
        unknown = c.read(setup[1], item['id'])
        assert run(setup, provider, unknown)['state'] == 'DELIVERY_UNKNOWN'
    port.before_send = competing
    assert run(setup, provider, item)['state'] == 'RECEIVED' and sends(port) == 1


def test_stale_query_revision_cannot_commit_receipt(setup):
    port, provider, unknown, _ = lost(setup)
    def changed():
        item = c.read(setup[1], unknown['id']); item['revision'] += 1
        atomic_json(c._path(setup[1], item['id']), item)
    port.before_read = changed
    assert run(setup, provider, unknown)['reason'] == 'cloud_query_revision_conflict'
    assert c.read(setup[1], unknown['id'])['state'] == 'DELIVERY_UNKNOWN' and sends(port) == 1


def test_lost_receipt_commit_response_reconciles_known_terminal(setup, monkeypatch):
    port, provider, item, _ = fixture(setup); real = c.atomic_json
    def commit_then_lose(path, value):
        real(path, value)
        if value['state'] == 'RECEIVED': raise OSError('fixture lost receipt commit response')
    monkeypatch.setattr(c, 'atomic_json', commit_then_lose)
    assert run(setup, provider, item)['state'] == 'RECEIVED'
    assert run(setup, provider, c.read(setup[1], item['id']))['state'] == 'RECEIVED' and sends(port) == 1


def test_old_v2_refused_before_any_callback_and_unverified_port_cannot_admit(setup):
    item = queued(setup); port = FixturePort(setup[1])
    provider = cloud.CloudProvider(port, mapping(), verify_authority=lambda phase, pin: None)
    before = filemap(setup[1])
    with pytest.raises(GateError, match='explicit_v3'):
        run(setup, provider, item)
    assert filemap(setup[1]) == before and port.calls == []
    port.identity = {**cloud.IDENTITY, 'stable_item_ids_and_content': False}
    with pytest.raises(GateError, match='verified_cloud'):
        cloud.CloudProvider(port, mapping(), verify_authority=lambda phase, pin: None)
