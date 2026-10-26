"""Synthetic public lifecycle cases; no real consumer identity or metadata."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import threading
import time
import tomllib

import pytest

from agent_os import __version__, project as p, turns
from agent_os.safeio import GateError, atomic_json, lock, read_json


def files(root):
    return {f.relative_to(root).as_posix(): f.read_bytes()
            for f in root.rglob('*') if f.is_file()}


def answers():
    result = {key: 'Synthetic local lifecycle fixture, no external target or authority.'
              for key in p.QUESTIONS}
    result.update(change_kind='implementation', write_paths=['module.py'],
                  acceptance=[{'id': 'A1', 'criterion': 'Synthetic approved process passes.',
                               'checks': ['unit']}],
                  checks=[{'id': 'unit', 'argv': [sys.executable, '-c',
                            'print("synthetic PASS")'], 'timeout': 30}])
    return result


def prepare(root, task):
    doc = root/'docs/lifecycle-fixture.md'
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text('# Synthetic lifecycle fixture\n\nTask: '+task+'\n\n'
        'Local synthetic source only. Verify the exact lifecycle operation, identities, '
        'retained task bytes and guarded failure behavior. No external effects or user data. '
        'Remove only the temporary fixture after its checks.\n')
    for role in p.load_task(root, task)['selection']['required']:
        p.register_document(root, role, 'docs/lifecycle-fixture.md', 'fixture reviewer',
            'synthetic test source', 'Reviewed bounded fixture lifecycle contract.',
            task if role == 'stage' else None)
    assert p.ready(root, task, 'fixture reviewer')['status'] == 'READY'


def make_case(tmp_path, terminal='CHECKPOINT', foreign=True):
    root = tmp_path/'parent'; root.mkdir()
    home = tmp_path/'user'
    context = {key: 'Synthetic local lifecycle fixture; no external data or target.'
               for key in p.CONTEXT_KEYS}
    p.initialize(root, 'Synthetic parent', ['general'], [], context)
    child = root/'work/isolated'; child.mkdir(parents=True)
    p.initialize(child, 'Synthetic isolated module', ['general'], [], context)
    a = answers()
    old = p.enter(root, a, session_id='worker', turn_id='old', user_home=home)['task_id']
    prepare(root, old)
    if terminal == 'CLOSED':
        assert p.run_check(root, old, 'unit')['status'] == 'PASS'
        review = {'reviewer': 'fixture reviewer', 'summary': 'Synthetic contract verified.',
            'next_step': 'Explicit new fixture entry.', 'limitations': 'Synthetic scope only.',
            'scope_reviewed': True, 'accepted_criteria': ['A1'],
            'reviewed_documents': p.load_task(root, old)['selection']['required'],
            'deployment_status': 'not_requested'}
        assert p.close(root, old, review)['status'] == 'CLOSED'
    else:
        p.checkpoint(root, old, 'Synthetic unfinished checkpoint', 'Continue explicitly')
    other = None
    if foreign:
        other = p.enter(root, a, session_id='other-worker', turn_id='ui', user_home=home)['task_id']
        prepare(root, other)
        assert p.run_check(root, other, 'unit')['status'] == 'PASS'
        assert p.load_task(root, other)['status'] == 'VERIFYING'
    return root, home, child, old, other, a


def advance(case, **overrides):
    root, home, _, old, _, _ = case
    values = {'session_id': 'worker', 'previous_turn': 'old', 'turn_id': 'new', 'task_id': old}
    values.update(overrides)
    return p.next_turn(root, home, **values)


@pytest.mark.parametrize('terminal', ['CHECKPOINT', 'CLOSED'])
def test_foreign_terminal_cli_then_isolated_entry(tmp_path, terminal):
    case = make_case(tmp_path, terminal)
    root, home, child, old, other, a = case
    parent_before = files(root/'.agentos')
    other_before = turns.turn_path(home, 'other-worker').read_bytes()
    result, code = p.command(['next-turn', '--root', str(root), '--session', 'worker',
        '--from-turn', 'old', '--turn', 'new', '--task', old], home)
    assert code == 0 and result['status'] == 'INTAKE_REQUIRED'
    receipt = read_json(turns.turn_path(home, 'worker'))
    assert receipt['task_id'] is None and receipt['root'] == str(root)
    assert receipt['turn_id'] == 'new' and receipt['hook_seen'] is False
    assert files(root/'.agentos') == parent_before
    value = p.enter(child, a, session_id='worker', turn_id='new', user_home=home)
    assert value['status'] == 'INTAKE' and value['task_id'] not in {old, other}
    assert p.load_task(child, value['task_id'])['receipts'] == []
    assert 'ready' not in p.load_task(child, value['task_id'])
    assert files(root/'.agentos') == parent_before
    assert turns.turn_path(home, 'other-worker').read_bytes() == other_before
    assert p.load_project(root)['active_task'] == other
    assert p.load_task(root, old)['status'] == terminal


@pytest.mark.parametrize('terminal', ['CHECKPOINT', 'CLOSED'])
def test_same_active_terminal_route_stays_supported(tmp_path, terminal):
    case = make_case(tmp_path, terminal, foreign=False)
    root, home, _, old, _, _ = case
    before = files(root/'.agentos')
    assert advance(case)['status'] == 'INTAKE_REQUIRED'
    assert files(root/'.agentos') == before
    assert p.load_project(root)['active_task'] == old
    assert read_json(turns.turn_path(home, 'worker'))['task_id'] is None


@pytest.mark.parametrize('status', ['INTAKE', 'READY', 'VERIFYING', 'CONTINUATION_REQUIRED'])
def test_foreign_nonterminal_task_cannot_release_receipt(tmp_path, status):
    case = make_case(tmp_path); root, home, _, old, _, _ = case
    value = p.load_task(root, old); value['status'] = status
    atomic_json(p.task_path(root, old), value)  # Deliberately corrupted synthetic fixture only.
    before, receipts = files(root/'.agentos'), files(home/'state')
    with pytest.raises(GateError, match='standalone_turn_task_mismatch'):
        advance(case)
    assert files(root/'.agentos') == before and files(home/'state') == receipts


@pytest.mark.parametrize('field,value', [
    ('project_id', 'project-unrelated'), ('session_id', 'wrong-worker'), ('turn_id', 'stale')])
def test_foreign_old_task_identity_must_match(tmp_path, field, value):
    case = make_case(tmp_path); root, home, _, old, _, _ = case
    task = p.load_task(root, old); task[field] = value
    atomic_json(p.task_path(root, old), task)
    before, receipts = files(root/'.agentos'), files(home/'state')
    with pytest.raises(GateError, match='standalone_turn_task_mismatch'):
        advance(case)
    assert files(root/'.agentos') == before and files(home/'state') == receipts


@pytest.mark.parametrize('pointer', [None, '', [], 'task-absent'])
def test_foreign_pointer_must_name_an_existing_task(tmp_path, pointer):
    case = make_case(tmp_path); root, home, *_ = case
    project = p.load_project(root); project['active_task'] = pointer
    atomic_json(p.project_file(root), project)
    before, receipts = files(root/'.agentos'), files(home/'state')
    with pytest.raises(GateError):
        advance(case)
    assert files(root/'.agentos') == before and files(home/'state') == receipts


def test_foreign_active_task_must_belong_to_same_project(tmp_path):
    case = make_case(tmp_path); root, home, _, _, other, _ = case
    task = p.load_task(root, other); task['project_id'] = 'project-unrelated'
    atomic_json(p.task_path(root, other), task)
    before, receipts = files(root/'.agentos'), files(home/'state')
    with pytest.raises(GateError, match='standalone_turn_task_mismatch'):
        advance(case)
    assert files(root/'.agentos') == before and files(home/'state') == receipts


@pytest.mark.parametrize('field,value', [('schema', 'wrong'), ('session_id', 'wrong-worker'),
    ('root', '/synthetic-unrelated-root'), ('turn_id', 'stale'),
    ('task_id', 'task-unrelated'), ('status', 'INTAKE_REQUIRED')])
def test_exact_prior_receipt_fields_are_required(tmp_path, field, value):
    case = make_case(tmp_path); root, home, *_ = case
    path = turns.turn_path(home, 'worker'); receipt = read_json(path); receipt[field] = value
    atomic_json(path, receipt)
    before, receipts = files(root/'.agentos'), files(home/'state')
    with pytest.raises(GateError, match='standalone_turn_transition_mismatch'):
        advance(case)
    assert files(root/'.agentos') == before and files(home/'state') == receipts


@pytest.mark.parametrize('override', [{'session_id': 'wrong-worker'}, {'previous_turn': 'wrong'},
    {'turn_id': 'old'}, {'task_id': 'task-absent'}])
def test_wrong_call_identity_or_nonnew_turn_refuses(tmp_path, override):
    case = make_case(tmp_path); root, home, *_ = case
    before, receipts = files(root/'.agentos'), files(home/'state')
    with pytest.raises(GateError):
        advance(case, **override)
    assert files(root/'.agentos') == before and files(home/'state') == receipts


def test_public_call_at_a_copied_wrong_root_refuses(tmp_path):
    case = make_case(tmp_path); root, home, _, old, _, _ = case
    other_root = tmp_path/'copied-project'
    shutil.copytree(root, other_root)
    before, copied, receipts = files(root/'.agentos'), files(other_root/'.agentos'), files(home/'state')
    with pytest.raises(GateError, match='standalone_turn_transition_mismatch'):
        p.next_turn(other_root, home, session_id='worker', previous_turn='old',
                    turn_id='new', task_id=old)
    assert files(root/'.agentos') == before and files(other_root/'.agentos') == copied
    assert files(home/'state') == receipts


def test_terminal_status_is_rechecked_under_project_lock(tmp_path, monkeypatch):
    case = make_case(tmp_path); root, home, _, old, _, _ = case
    loader = p.load_task; seen = 0
    def changed(selected_root, ident):
        nonlocal seen
        task = loader(selected_root, ident)
        if ident == old:
            seen += 1
            if seen > 1:
                task = deepcopy(task); task['status'] = 'VERIFYING'
        return task
    monkeypatch.setattr(p, 'load_task', changed)
    before, receipts = files(root/'.agentos'), files(home/'state')
    with pytest.raises(GateError, match='standalone_turn_task_mismatch'):
        advance(case)
    assert seen == 2 and files(root/'.agentos') == before and files(home/'state') == receipts


def test_missing_and_replayed_receipt_do_not_get_cleared(tmp_path):
    case = make_case(tmp_path); root, home, *_ = case
    path = turns.turn_path(home, 'worker'); original = path.read_bytes(); path.unlink()
    before = files(root/'.agentos')
    with pytest.raises(GateError, match='standalone_previous_turn_missing'):
        advance(case)
    assert not path.exists() and files(root/'.agentos') == before
    path.write_bytes(original)
    assert advance(case)['status'] == 'INTAKE_REQUIRED'
    receipt = path.read_bytes()
    for overrides in ({}, {'previous_turn': 'new', 'turn_id': 'later'}):
        with pytest.raises(GateError):
            advance(case, **overrides)
        assert path.read_bytes() == receipt and files(root/'.agentos') == before


@pytest.mark.parametrize('target', ['project', 'turn'])
def test_existing_locks_refuse_without_touching_other_state(tmp_path, target):
    case = make_case(tmp_path); root, home, *_ = case
    directory = root/'.agentos/write.lock' if target == 'project' else home/'state/turns.lock'
    with lock(directory):
        before, receipts = files(root/'.agentos'), files(home/'state')
        with pytest.raises(GateError, match='busy_or_stale_lock_manual_review_required'):
            advance(case)
        assert files(root/'.agentos') == before and files(home/'state') == receipts


@pytest.mark.parametrize('marker', ['entry-transaction.json', 'refusal-recovery-transaction.json',
                                  'interrupted-continuation-pending.json', 'refusal-recovery-pending'])
def test_pending_recovery_is_not_bypassed(tmp_path, marker):
    case = make_case(tmp_path); root, home, *_ = case
    path = root/'.agentos'/marker
    if marker == 'refusal-recovery-pending': path.mkdir()
    else: atomic_json(path, {'synthetic': 'pending'})
    before, receipts = files(root/'.agentos'), files(home/'state')
    with pytest.raises(GateError): advance(case)
    assert files(root/'.agentos') == before and files(home/'state') == receipts


def test_explicit_recovery_route_stays_separate(tmp_path):
    case = make_case(tmp_path); root, home, _, old, _, _ = case
    before, receipts = files(root/'.agentos'), files(home/'state')
    with pytest.raises(GateError, match='recovery_parameters_for_nonrecovery_task'):
        advance(case, recovery_request={})
    assert files(root/'.agentos') == before and files(home/'state') == receipts
    task = p.load_task(root, old); task['status'] = 'RECOVERY_REQUIRED'
    atomic_json(p.task_path(root, old), task); before = files(root/'.agentos')
    with pytest.raises(GateError, match='recovery_advance_required'):
        advance(case)
    assert files(root/'.agentos') == before and files(home/'state') == receipts


def test_project_then_user_turn_lock_order(tmp_path, monkeypatch):
    case = make_case(tmp_path); events = []
    @contextmanager
    def watched(path):
        label = path.name; events.append(('enter', label))
        with lock(path): yield
        events.append(('exit', label))
    monkeypatch.setattr(p, 'lock', watched)
    monkeypatch.setattr(turns, 'lock', watched)
    assert advance(case)['status'] == 'INTAKE_REQUIRED'
    assert events == [('enter', 'write.lock'), ('enter', 'turns.lock'),
                      ('exit', 'turns.lock'), ('exit', 'write.lock')]


def test_concurrent_transition_has_one_winner(tmp_path):
    case = make_case(tmp_path); root, home, *_ = case
    before = files(root/'.agentos'); barrier = threading.Barrier(2)
    def attempt():
        barrier.wait(timeout=5)
        try: return advance(case)['status']
        except GateError as exc: return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert results.count('INTAKE_REQUIRED') == 1
    assert set(results) <= {'INTAKE_REQUIRED', 'busy_or_stale_lock_manual_review_required',
                            'standalone_turn_transition_mismatch'}
    assert files(root/'.agentos') == before
    assert read_json(turns.turn_path(home, 'worker'))['task_id'] is None


@pytest.mark.parametrize('committed', [False, True])
def test_atomic_failure_preserves_tasks_and_requires_receipt_readback(tmp_path, monkeypatch, committed):
    case = make_case(tmp_path); root, home, *_ = case
    before = files(root/'.agentos'); path = turns.turn_path(home, 'worker'); original = path.read_bytes()
    writer = turns.atomic_json
    def failed(path, value):
        if committed: writer(path, value)
        raise OSError('synthetic atomic failure')
    monkeypatch.setattr(turns, 'atomic_json', failed)
    with pytest.raises(OSError): advance(case)
    assert files(root/'.agentos') == before
    observed = read_json(path)
    if committed:
        assert observed['status'] == 'INTAKE_REQUIRED' and observed['turn_id'] == 'new'
    else:
        assert path.read_bytes() == original


def test_candidate_public_version_identity():
    root = Path(__file__).resolve().parents[1]
    assert tomllib.loads((root/'pyproject.toml').read_text())['project']['version'] == __version__
    mcp = read_json(root/'src/agent_os/resources/contracts/mcp-tools-v1.json')
    cli = read_json(root/'src/agent_os/resources/contracts/cli-contract-v1.json')
    assert mcp['serverInfo']['version'] == cli['distribution_version'] == __version__
