"""Interrupted v2 over real disposable Library history; provider is synthetic."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from test_accepted_checkpoint_history import (
    setup, case, authority, journals, metadata, one_journal, qualified,
    request as completed_request, observer as completed_observer,
)
from test_foundation import documents
from agent_os import interrupted_continuation as ic
from agent_os import project as p
from agent_os import refusal_recovery as rr
from agent_os.handoff import Library, local_principal
from agent_os.safeio import GateError, atomic_json
from agent_os.turns import turn_path


def request(case):
    value = completed_request(case)
    value['schema'] = ic.INTERRUPTED_HISTORY_SCHEMA
    return value


def observer(r, **kwargs):
    return completed_observer(r, old=kwargs.pop('old', 'interrupted'), **kwargs)


def test_interrupted_history_full_entry_preserves_task_goal_and_journals(case):
    root, home, task, answers = case
    before = journals(case)
    r = request(case)
    assert not ic.completed(r)
    receipt = ic.advance(root, home, r, authority(r), observer=observer(r))
    assert receipt['schema'] == 'agentos.interrupted-continuation-receipt/v2'
    assert receipt['status'] == 'FULL_ENTRY_REQUIRED'
    assert receipt['ready_granted'] is False and receipt['semantic_acceptance'] is False
    assert p.check_ready(root, task)['status'] == 'BLOCKED'
    events = (root / f'.agentos/tasks/{task}/events.jsonl').read_text().splitlines()
    assert json.loads(events[-1])['event'] == 'INTERRUPTED_CONTINUATION'
    fresh = copy.deepcopy(answers)
    fresh['authority'] += ' synthetic:current-owner'
    result = p.enter(root, fresh, session_id='s', turn_id='new', user_home=home, resume_task=task)
    assert result['task_id'] == task
    documents((root, home, fresh), task)
    assert p.run_check(root, task, 'unit')['status'] == 'PASS'
    assert journals(case) == before
    saved = p.load_task(root, task)['answers']
    for key in ['objective', 'outcome', 'acceptance']:
        assert saved[key] == answers[key]


@pytest.mark.parametrize('mutation', [
    'missing-pin', 'bad-pin', 'extra-field', 'authority-kind', 'revoked', 'expired',
    'source', 'task-cas', 'goal', 'entry', 'refusal', 'no-observer',
    'old-completed', 'old-active', 'old-unknown', 'current-inactive', 'foreign-thread',
])
def test_interrupted_v2_rejects_unqualified_inputs_before_effects(case, mutation):
    root, home, task, _ = case
    r = request(case)
    if mutation == 'missing-pin': r.pop('accepted_checkpoint_history_sha256')
    if mutation == 'bad-pin': r['accepted_checkpoint_history_sha256'] = '0' * 64
    if mutation == 'extra-field': r['accepted'] = True
    a = authority(r)
    if mutation == 'authority-kind': a['schema'] = 'agentos.completed-continuation-authority/v1'
    if mutation == 'revoked': a['revoked'] = True
    if mutation == 'expired':
        a['valid_until'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    if mutation == 'source': (root / 'code.py').write_text('# deliberate source drift')
    if mutation == 'task-cas':
        path = root / f'.agentos/tasks/{task}/task.json'
        value = json.loads(path.read_text()); value['note'] = 'concurrent edit'; atomic_json(path, value)
    if mutation == 'goal':
        r['goal_sha256'] = '0' * 64; a = authority(r)
    if mutation == 'entry': (root / '.agentos/entry-transaction.json').write_text('{}')
    if mutation == 'refusal': rr.pending(root).mkdir()
    ob = observer(r)
    if mutation == 'no-observer': ob = None
    if mutation.startswith('old-'):
        ob = observer(r, old={'old-completed': 'completed', 'old-active': 'inProgress', 'old-unknown': 'unknown'}[mutation])
    if mutation == 'current-inactive': ob = observer(r, current='completed')
    if mutation == 'foreign-thread':
        ob = ic.SupportedReadThreadObserver(lambda **_: {'thread': {'id': 'foreign', 'cwd': str(root)}, 'turns': []})
    before = metadata(case)
    with pytest.raises(GateError):
        ic.advance(root, home, r, a, observer=ob)
    assert metadata(case) == before and not ic.marker(root).exists()


@pytest.mark.parametrize('mutation', ['unknown-journal', 'retracted', 'acl-revoked', 'corrupt-object'])
def test_interrupted_history_uses_current_library_proof(case, mutation):
    root, home, task, _ = case
    r = request(case)
    lib = Library(home / 'results-library')
    if mutation == 'unknown-journal':
        (one_journal(case).parent / 'handoff-unknown.json').write_text('{}')
    if mutation == 'retracted': lib.retract('handoff:' + task, 'Synthetic withdrawal', local_principal())
    if mutation == 'acl-revoked':
        path = home / 'results-library/ROOT.json'; value = json.loads(path.read_text())
        value['access']['readers'] = []; atomic_json(path, value)
    if mutation == 'corrupt-object':
        manifest = lib.resolve('handoff:' + task, local_principal())['manifest']
        oid = manifest['evidence'][0]['ref']['object_id'][7:]
        lib.store.path(f'objects/sha256/{oid[:2]}/{oid}').write_bytes(b'corrupt fixture')
    before = metadata(case)
    with pytest.raises(GateError):
        ic.advance(root, home, r, authority(r), observer=observer(r))
    assert metadata(case) == before and not ic.marker(root).exists()


@pytest.mark.parametrize('mutation', ['journal', 'retraction', 'acl'])
def test_interrupted_history_is_requalified_after_native_observation(case, mutation):
    root, home, task, _ = case
    r = request(case)
    once = []
    def effect():
        if once: return
        once.append(True)
        if mutation == 'journal': (one_journal(case).parent / 'handoff-new.json').write_text('{}')
        if mutation == 'retraction':
            Library(home / 'results-library').retract('handoff:' + task, 'Synthetic concurrent withdrawal', local_principal())
        if mutation == 'acl':
            path = home / 'results-library/ROOT.json'; value = json.loads(path.read_text())
            value['access']['readers'] = []; atomic_json(path, value)
    before = metadata(case)
    with pytest.raises(GateError):
        ic.advance(root, home, r, authority(r), observer=observer(r, effect=effect))
    assert once and metadata(case) == before and not ic.marker(root).exists()


@pytest.mark.parametrize('partial', [False, True])
def test_interrupted_exact_operation_reconcile_preserves_history(case, monkeypatch, partial):
    root, home, *_ = case
    r = request(case); a = authority(r)
    before = journals(case); original = ic.atomic_bytes
    if partial:
        def fault(path, raw):
            if path == turn_path(home, 's'): raise OSError('synthetic interrupted write')
            return original(path, raw)
        monkeypatch.setattr(ic, 'atomic_bytes', fault)
        with pytest.raises(OSError, match='synthetic interrupted'):
            ic.advance(root, home, r, a, observer=observer(r))
        assert ic.marker(root).exists()
        monkeypatch.setattr(ic, 'atomic_bytes', original)
    else:
        ic.advance(root, home, r, a, observer=observer(r))
        with pytest.raises(GateError, match='already_committed'):
            ic.advance(root, home, r, a, observer=observer(r))
    result = ic.reconcile(root, home, r, a, observer=observer(r))
    assert result['schema'] == 'agentos.interrupted-continuation-receipt/v2'
    after = metadata(case)
    assert ic.reconcile(root, home, r, a, observer=observer(r)) == result
    assert metadata(case) == after and journals(case) == before and not ic.marker(root).exists()


def test_interrupted_shared_library_lock_covers_commit_and_is_released(case, monkeypatch):
    from agent_os.handoff_store import HandoffError
    root, home, task, _ = case
    r = request(case); original = ic.atomic_bytes; attempted = []
    def at_commit(path, raw):
        if path == ic.marker(root) and not attempted:
            with pytest.raises(HandoffError, match='GENERATION_CONFLICT'):
                Library(home / 'results-library').retract('handoff:' + task, 'Synthetic competing writer', local_principal())
            attempted.append(True)
        return original(path, raw)
    monkeypatch.setattr(ic, 'atomic_bytes', at_commit)
    assert ic.advance(root, home, r, authority(r), observer=observer(r))['status'] == 'FULL_ENTRY_REQUIRED'
    assert attempted
    Library(home / 'results-library').retract('handoff:' + task, 'Synthetic later withdrawal', local_principal())


def test_interrupted_shared_library_busy_remains_hold(case):
    from agent_os.handoff_store import publisher_lock
    root, home, *_ = case
    r = request(case); before = metadata(case)
    with publisher_lock(home / 'results-library/publisher.lock'):
        with pytest.raises(GateError, match='library_busy_or_unavailable'):
            ic.advance(root, home, r, authority(r), observer=observer(r))
    assert metadata(case) == before and not ic.marker(root).exists()


def test_completed_v2_still_rejects_interrupted_old_turn(case):
    root, home, *_ = case
    r = completed_request(case); before = metadata(case)
    with pytest.raises(GateError, match='old_writer_not_completed'):
        ic.advance(root, home, r, authority(r), observer=observer(r))
    assert metadata(case) == before and not ic.marker(root).exists()
