"""Disposable synthetic metadata only; no native target or protected asset."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest
import test_foundation
from test_foundation import documents

from agent_os import handoff_diagnostics as hd
from agent_os import project as project
from agent_os import refusal_recovery as rr
from agent_os.interrupted_continuation import SupportedReadThreadObserver
from agent_os.safeio import GateError, atomic_json, sha
from agent_os.turns import turn_path

setup = test_foundation.setup
ORIGIN = '11111111-1111-4111-8111-111111111111'
CURRENT = '22222222-2222-4222-8222-222222222222'
THREAD = '33333333-3333-4333-8333-333333333333'
WORKFLOW = 'synthetic-run-label-20261027'
SESSION = 'synthetic-session-label'


@pytest.fixture
def factory(setup, monkeypatch):
    root, home, answers = setup

    def make(schema=None, bound=None):
        schema = schema or rr.WORKFLOW_REQUEST
        bound = bound or (WORKFLOW if schema == rr.WORKFLOW_REQUEST else ORIGIN)
        task = project.enter(root, answers, session_id=SESSION, turn_id=bound, user_home=home)['task_id']
        documents((root, home, answers), task)
        assert project.run_check(root, task, 'unit')['status'] == 'PASS'
        value = project.load_task(root, task)
        paths = {'project': root / '.agentos/project.json',
                 'task': root / f'.agentos/tasks/{task}/task.json',
                 'turn': turn_path(home, SESSION),
                 'events': root / f'.agentos/tasks/{task}/events.jsonl'}
        attempt = 'a' * 32
        witness = {'status': 'BLOCKED', 'error': rr.ERROR}
        w = {'root': str(root), 'path': 'synthetic-witness.json', 'bytes': 0,
             'sha256': '0' * 64, 'kind': 'owner_attested_legacy', 'attempt_id': None, 'exit_code': 2}
        if schema != rr.REQUEST:
            now = datetime.now(timezone.utc).isoformat()
            diagnostic = {'schema': hd.SCHEMA, 'status': 'BLOCKED', 'error': 'SECRET_DETECTED',
                          'category': 'SECRET_DETECTED', 'task_id': task, 'revision': value['revision'],
                          'profile': 'checkpoint', 'attempt_id': attempt, 'attempted_at': now,
                          'recorded_at': now, 'session_id': SESSION, 'turn_id': bound,
                          'stage': 'embedded_asset', 'payload_fingerprint': None,
                          'source_snapshot_sha256': None, 'capture_manifest': None, 'candidate_ref': None,
                          'asset': {'asset_id': 'source:synthetic', 'path': 'source/never-open.json',
                                    'sha256': 'b' * 64, 'bytes': 32}}
            diagnostic['gaps'] = hd._gaps(diagnostic)
            hd.validate_receipt(diagnostic)
            relative = f'.agentos/tasks/{task}/diagnostics/{attempt}.json'
            raw = rr.enc(diagnostic)
            destination = root / relative
            destination.parent.mkdir(parents=True)
            destination.write_bytes(raw)
            ref = {'path': relative, 'bytes': len(raw), 'sha256': sha(raw)}
            witness['diagnostic'] = {'schema': hd.ENVELOPE, 'attempt_id': attempt,
                                     'metadata_status': 'SAVED', 'receipt': ref}
            w.update(kind='owner_attested_modern_v1', attempt_id=attempt, diagnostic=ref)
        raw = rr.enc(witness)
        (root / w['path']).write_bytes(raw)
        w.update(bytes=len(raw), sha256=sha(raw))
        r = {'schema': schema, 'root': str(root), 'user_home': str(home), 'operation_id': 'c' * 32,
             'actor_id': 'synthetic-owner', 'session_id': SESSION, 'project_id': value['project_id'],
             'task_id': task, 'revision': value['revision'],
             'expected': {**{k + '_sha256': sha(paths[k].read_bytes()) for k in ('project', 'task', 'turn')},
                          'bound_turn_id': bound, 'status': 'VERIFYING'},
             'witness': w, 'goal': {'state': 'OPEN', 'ref': 'synthetic:original-goal', 'sha256': sha(rr.enc(answers))},
             'next_owner': 'synthetic-owner', 'next_scope': {'ref': 'synthetic:scope', 'write_paths': answers['write_paths']}}
        if schema == rr.WORKFLOW_REQUEST:
            r['native_origin'] = {'thread_id': THREAD, 'turn_id': ORIGIN,
                                  'observation_ref': 'synthetic:reviewed-native-origin',
                                  'observation_sha256': sha(b'synthetic mapping observation')}

        # All A/B/C tests must stay on metadata ports, never original source/library.
        def forbidden(*args, **kwargs):
            raise AssertionError('source/scanner/capture/library port invoked')
        import agent_os.handoff_lifecycle as lifecycle
        import agent_os.handoff_store as store
        import agent_os.handoff as handoff
        monkeypatch.setattr(lifecycle, 'deliver', forbidden)
        monkeypatch.setattr(store, 'scan_secrets', forbidden)
        monkeypatch.setattr(handoff.Library, '__init__', forbidden)
        monkeypatch.setattr(project, 'source_snapshot', forbidden)
        original_read = rr._read

        def metadata_read(path, *args, **kwargs):
            assert Path(path) != root / 'source/never-open.json'
            return original_read(path, *args, **kwargs)
        monkeypatch.setattr(rr, '_read', metadata_read)
        return root, home, task, answers, r, paths

    return make


def permit(r, phase='ack', current=ORIGIN, *, ack=None, journal=None):
    now = datetime.now(timezone.utc)
    return {'schema': rr.PERMIT, 'owner_attested': True, 'decision_ref': 'synthetic:owner-grant',
            'decision_sha256': sha(b'synthetic grant, no live authority'), 'actor_id': r['actor_id'],
            'session_id': r['session_id'], 'current_turn_id': current, 'observed_at': now.isoformat(),
            'observation_ref': 'synthetic:supported-read', 'valid_from': (now - timedelta(seconds=1)).isoformat(),
            'valid_until': (now + timedelta(seconds=300)).isoformat(), 'revoked': False,
            **{k: r[k] for k in ('root', 'project_id', 'task_id', 'revision', 'operation_id')},
            'request_sha256': sha(rr.enc(r)), 'phase': phase, 'receipt_sha256': ack, 'journal_sha256': journal}


def observer(r, current=ORIGIN, *, origin_status=None, current_status='inProgress', effect=None, wrong_thread=False):
    origin_status = origin_status or ('inProgress' if current == ORIGIN else 'completed')
    def read_thread(**params):
        if effect:
            effect()
        previous = params.get('cursor') == 'origin'
        turn = {'id': ORIGIN, 'status': origin_status} if previous else {'id': current, 'status': current_status}
        return {'thread': {'id': CURRENT if wrong_thread else THREAD, 'cwd': r['root']},
                'turns': [turn], 'page': {'hasMore': current != ORIGIN and not previous,
                                        'nextCursor': 'origin' if current != ORIGIN and not previous else None}}
    return SupportedReadThreadObserver(read_thread)


def images(case):
    return {k: p.read_bytes() for k, p in case[-1].items()}


def ack_digest(case):
    r = case[-2]
    return sha((rr.area(case[0], case[2], r['operation_id']) / 'ack.json').read_bytes())


def ack(case):
    root, home, task, _, r, _ = case
    return rr.acknowledge(root, home, task, r, permit(r), observer=observer(r))


def advance(case):
    root, home, task, _, r, _ = case
    a = permit(r, 'advance', CURRENT, ack=ack_digest(case))
    return project.next_turn(root, home, session_id=SESSION,
                             previous_turn=r['expected']['bound_turn_id'], turn_id=CURRENT,
                             task_id=task, recovery_request=r, recovery_permit=a,
                             recovery_observer=observer(r, CURRENT))


def validate_postimages(case):
    source = Path(__file__).resolve().parents[1]
    root, _, task, *_ = case
    task_schema = json.loads((source / 'schemas/project-task-v1.schema.json').read_text())
    event_schema = json.loads((source / 'schemas/project-event-v1.schema.json').read_text())
    jsonschema.validate(project.load_task(root, task), task_schema)
    for line in (root / f'.agentos/tasks/{task}/events.jsonl').read_text().splitlines():
        jsonschema.validate(json.loads(line), event_schema)


def test_v3_full_abc_preserves_workflow_witness_and_goal(factory):
    case = factory(); root, home, task, answers, r, paths = case
    witness = (root / r['witness']['path']).read_bytes()
    diagnostic = (root / r['witness']['diagnostic']['path']).read_bytes()
    result = ack(case)
    assert result['schema'] == rr.WORKFLOW_RECEIPT and result['partial_objects'] == 'UNKNOWN'
    assert result['ready_granted'] is result['semantic_acceptance'] is False
    assert project.load_task(root, task)['turn_id'] == WORKFLOW
    validate_postimages(case)
    with pytest.raises(GateError, match='recovery_advance_required'):
        project.enter(root, answers, session_id=SESSION, turn_id=WORKFLOW, user_home=home, resume_task=task)
    assert advance(case)['status'] == 'ADVANCED'
    assert project.load_task(root, task)['turn_id'] == WORKFLOW
    resumed = project.enter(root, answers, session_id=SESSION, turn_id=CURRENT, user_home=home, resume_task=task)
    value = project.load_task(root, task)
    assert resumed['task_id'] == task and value['revision'] == 2 and value['status'] == 'INTAKE'
    assert value['turn_id'] == CURRENT and value['answers'] == answers
    assert 'ready' not in value and value['receipts'] == []
    assert value['recovery']['state'] == 'CONSUMED' and value['recovery']['native_origin'] == r['native_origin']
    assert (root / r['witness']['path']).read_bytes() == witness
    assert (root / r['witness']['diagnostic']['path']).read_bytes() == diagnostic
    assert json.loads(paths['turn'].read_text())['turn_id'] == CURRENT
    validate_postimages(case)


@pytest.mark.parametrize('schema', [rr.REQUEST, rr.MODERN_REQUEST])
def test_legacy_uuid_roundtrip_requires_no_new_observer_or_fields(factory, schema):
    case = factory(schema); root, home, task, answers, r, _ = case
    result = rr.acknowledge(root, home, task, r, permit(r))
    assert result['schema'] == (rr.RECEIPT if schema == rr.REQUEST else rr.MODERN_RECEIPT)
    assert 'native_origin' not in result
    a = permit(r, 'advance', CURRENT, ack=ack_digest(case))
    assert rr.advance(root, home, task, r, a)['status'] == 'ADVANCED'
    project.enter(root, answers, session_id=SESSION, turn_id=CURRENT, user_home=home, resume_task=task)
    validate_postimages(case)


@pytest.mark.parametrize('schema', [rr.REQUEST, rr.MODERN_REQUEST])
def test_v1_v2_still_reject_workflow_labels(factory, schema):
    case = factory(schema, WORKFLOW); root, home, task, _, r, _ = case
    before = images(case)
    with pytest.raises(GateError, match='recovery_metadata_invalid'):
        rr.acknowledge(root, home, task, r, permit(r))
    assert images(case) == before and not rr.pending(root).exists()


@pytest.mark.parametrize('mutation', ['root', 'project', 'task', 'revision', 'session', 'label', 'task_cas', 'project_cas', 'turn_cas', 'origin_uuid', 'origin_extra', 'legacy_witness', 'missing_diagnostic', 'diagnostic_pin'])
def test_identity_request_and_modern_witness_drifts_refuse_before_writes(factory, mutation):
    case = factory(); root, home, task, _, r, _ = case
    if mutation == 'root': r['root'] += '/foreign'
    if mutation == 'project': r['project_id'] = 'project-' + '0' * 16
    if mutation == 'task': r['task_id'] = 'task-' + '0' * 16
    if mutation == 'revision': r['revision'] += 1
    if mutation == 'session': r['session_id'] += '-foreign'
    if mutation == 'label': r['expected']['bound_turn_id'] += '-foreign'
    if mutation.endswith('_cas'): r['expected'][mutation[:-4] + '_sha256'] = '0' * 64
    if mutation == 'origin_uuid': r['native_origin']['turn_id'] = WORKFLOW
    if mutation == 'origin_extra': r['native_origin']['extra'] = True
    if mutation == 'legacy_witness': r['witness']['kind'] = 'owner_attested_legacy'
    if mutation == 'missing_diagnostic': r['witness'].pop('diagnostic')
    if mutation == 'diagnostic_pin': r['witness']['diagnostic']['sha256'] = '0' * 64
    before = images(case)
    with pytest.raises(GateError):
        rr.acknowledge(root, home, task, r, permit(r), observer=observer(r))
    assert images(case) == before and not rr.pending(root).exists() and not rr.marker(root).exists()


@pytest.mark.parametrize('change', ['missing', 'plain_json', 'thread', 'current_status', 'origin_status', 'stale', 'cas_during_observe'])
def test_supported_native_observation_is_mandatory_and_cas_is_rechecked(factory, change):
    case = factory(); root, home, task, _, r, paths = case
    current = CURRENT
    ob = observer(r, current)
    if change == 'missing': ob = None
    if change == 'plain_json': ob = {'source': 'supported_read_thread'}
    if change == 'thread': ob = observer(r, current, wrong_thread=True)
    if change == 'current_status': ob = observer(r, current, current_status='completed')
    if change == 'origin_status': ob = observer(r, current, origin_status='inProgress')
    if change == 'stale':
        class Stale:
            def read_turn_metadata(self, *args, **kwargs):
                value = ob_original.read_turn_metadata(*args, **kwargs)
                value['observed_at'] = (datetime.now(timezone.utc) - timedelta(seconds=121)).isoformat()
                return value
        ob_original = ob; ob = Stale()
    if change == 'cas_during_observe':
        def mutate():
            value = json.loads(paths['project'].read_text()); value['synthetic_drift'] = True
            atomic_json(paths['project'], value)
        ob = observer(r, current, effect=mutate)
    before = images(case)
    with pytest.raises(GateError):
        rr.acknowledge(root, home, task, r, permit(r, current=current), observer=ob)
    after = images(case)
    if change == 'cas_during_observe':
        assert {k: v for k, v in after.items() if k != 'project'} == {k: v for k, v in before.items() if k != 'project'}
    else: assert after == before
    assert not rr.pending(root).exists() and not rr.marker(root).exists()


def test_b_compares_actual_native_origin_not_workflow_label(factory):
    case = factory(); root, home, task, _, r, _ = case; ack(case)
    before = images(case)
    with pytest.raises(GateError, match='recovery_current_turn_required'):
        rr.advance(root, home, task, r, permit(r, 'advance', ORIGIN, ack=ack_digest(case)), observer=observer(r))
    assert images(case) == before and not rr.pending(root).exists()


@pytest.mark.parametrize('field', ['origin', 'current'])
def test_native_uuid_cannot_be_a_label(factory, field):
    case = factory(); root, home, task, _, r, _ = case
    a = permit(r)
    if field == 'origin': r['native_origin']['turn_id'] = WORKFLOW; a = permit(r)
    else: a['current_turn_id'] = WORKFLOW
    with pytest.raises(GateError):
        rr.acknowledge(root, home, task, r, a, observer=observer(r))
    assert not rr.pending(root).exists()


@pytest.mark.parametrize('phase', ['ack', 'advance'])
def test_interrupted_transaction_reconciles_only_exact_metadata_once(factory, monkeypatch, phase):
    case = factory(); root, home, task, _, r, paths = case
    if phase == 'advance': ack(case)
    current = CURRENT if phase == 'advance' else ORIGIN
    a = permit(r, phase, current, ack=ack_digest(case) if phase == 'advance' else None)
    target = paths['turn'] if phase == 'advance' else paths['task']
    original = rr.write
    def fail_target(path, *args, **kwargs):
        if path == target: raise OSError('synthetic interrupted target write')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(rr, 'write', fail_target)
    with pytest.raises(GateError, match='recovery_operation_unknown'):
        (rr.advance if phase == 'advance' else rr.acknowledge)(root, home, task, r, a, observer=observer(r, current))
    assert rr.marker(root).exists() and rr.pending(root).exists()
    assert rr.status(root, home, task, r['operation_id'])['status'] == 'PREPARED'
    monkeypatch.setattr(rr, 'write', original)
    if phase == 'advance':
        wrong = permit(r, 'reconcile', ORIGIN, journal=sha(rr.marker(root).read_bytes()))
        with pytest.raises(GateError, match='recovery_turn_changed_requires_review'):
            rr.reconcile(root, home, task, r, wrong, observer=observer(r))
    authority = permit(r, 'reconcile', current, journal=sha(rr.marker(root).read_bytes()))
    result = rr.reconcile(root, home, task, r, authority, observer=observer(r, current))
    assert result['status'] == ('ADVANCED' if phase == 'advance' else 'ACKNOWLEDGED')
    assert not rr.marker(root).exists() and not rr.pending(root).exists()
    after = images(case)
    replay = (rr.advance if phase == 'advance' else rr.acknowledge)(root, home, task, r, a)
    assert replay['historical_replay'] is True and images(case) == after
    assert sum(json.loads(line)['event'] == 'REFUSAL_ACKNOWLEDGED' for line in paths['events'].read_text().splitlines()) == 1


def test_incomplete_prejournal_preparation_remains_unknown(factory, monkeypatch):
    case = factory(); root, home, task, _, r, _ = case; before = images(case)
    original = rr.write
    def fail_request(path, *args, **kwargs):
        if path.name == 'request.json': raise OSError('synthetic pre-journal interruption')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(rr, 'write', fail_request)
    with pytest.raises(GateError, match='recovery_operation_unknown'): ack(case)
    assert rr.pending(root).exists() and not rr.marker(root).exists()
    assert rr.status(root, home, task, r['operation_id'])['status'] == 'UNKNOWN'
    with pytest.raises(GateError, match='refusal_recovery_transaction_pending'): ack(case)
    assert images(case) == before


def test_tampered_staged_v3_origin_never_writes_a_target(factory, monkeypatch):
    case = factory(); root, home, task, _, r, paths = case; before = images(case)
    original = rr.write
    def fail_target(path, *args, **kwargs):
        if path == paths['task']: raise OSError('synthetic interrupted target')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(rr, 'write', fail_target)
    with pytest.raises(GateError): ack(case)
    monkeypatch.setattr(rr, 'write', original)
    staged = rr._staged(root, r, 'ack', 'task', 'after')
    value = json.loads(staged.read_text()); value['recovery']['native_origin']['turn_id'] = True
    raw = rr.enc(value); staged.write_bytes(raw)
    journal = json.loads(rr.marker(root).read_text()); journal['files'][0]['after'] = {'bytes': len(raw), 'sha256': sha(raw)}
    rr.marker(root).write_bytes(rr.enc(journal))
    with pytest.raises(GateError):
        rr.reconcile(root, home, task, r, permit(r, 'reconcile', journal=sha(rr.marker(root).read_bytes())), observer=observer(r))
    assert images(case) == before and rr.marker(root).exists() and rr.pending(root).exists()


@pytest.mark.parametrize('change', ['empty_label', 'long_label', 'boolean_label', 'request_bytes', 'witness_bytes', 'diagnostic_bytes'])
def test_v3_keeps_finite_metadata_bounds_before_reservation(factory, change):
    case = factory(); root, home, task, _, r, _ = case; before = images(case)
    if change == 'empty_label': r['expected']['bound_turn_id'] = ' '
    if change == 'long_label': r['expected']['bound_turn_id'] = 'x' * 201
    if change == 'boolean_label': r['expected']['bound_turn_id'] = True
    if change == 'request_bytes': r['next_scope']['write_paths'] = [f'{i:02d}-' + 'x' * 300 for i in range(64)]
    if change == 'witness_bytes': r['witness']['bytes'] = rr.MAX_DOCUMENT + 1
    if change == 'diagnostic_bytes': r['witness']['diagnostic']['bytes'] = rr.MAX_DOCUMENT + 1
    with pytest.raises(GateError):
        rr.acknowledge(root, home, task, r, permit(r), observer=observer(r))
    assert images(case) == before and not rr.pending(root).exists()


def test_b_without_observer_and_c_with_changed_scope_stay_blocked(factory):
    case = factory(); root, home, task, answers, r, _ = case; ack(case)
    before = images(case)
    with pytest.raises(GateError, match='recovery_supported_observer_unavailable'):
        rr.advance(root, home, task, r, permit(r, 'advance', CURRENT, ack=ack_digest(case)))
    assert images(case) == before and not rr.pending(root).exists()
    advance(case)
    before = images(case); changed = copy.deepcopy(answers); changed['write_paths'].append('unapproved.py')
    with pytest.raises(GateError, match='recovery_resume_scope_mismatch'):
        project.enter(root, changed, session_id=SESSION, turn_id=CURRENT, user_home=home, resume_task=task)
    assert images(case) == before


@pytest.mark.parametrize('phase', ['ack', 'advance'])
def test_v3_rechecks_authority_after_native_observation(factory, phase):
    case = factory(); root, home, task, _, r, _ = case
    if phase == 'advance': ack(case)
    current = CURRENT if phase == 'advance' else ORIGIN
    a = permit(r, phase, current, ack=ack_digest(case) if phase == 'advance' else None)
    before = images(case)
    def revoke(): a['revoked'] = True
    with pytest.raises(GateError, match='recovery_authority_invalid'):
        (rr.advance if phase == 'advance' else rr.acknowledge)(root, home, task, r, a, observer=observer(r, current, effect=revoke))
    assert images(case) == before and not rr.pending(root).exists()


def test_v3_a_rechecks_whole_witness_after_native_observation(factory):
    case = factory(); root, home, task, _, r, _ = case; before = images(case)
    def change_witness(): (root / r['witness']['path']).write_text('{}\n')
    with pytest.raises(GateError, match='recovery_witness_mismatch'):
        rr.acknowledge(root, home, task, r, permit(r), observer=observer(r, effect=change_witness))
    assert images(case) == before and not rr.pending(root).exists()
