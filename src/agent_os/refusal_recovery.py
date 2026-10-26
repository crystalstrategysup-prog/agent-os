"""Explicit nonaccepting refusal disposition. Metadata only, never a handoff.

Authority/observations are owner-attested local input, not core-authenticated
human identity. Callers must verify that evidence independently. Same-owner
cooperative filesystem trust applies; no source/library/scanner dependency.
"""
from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

from .task_metadata import limit as task_metadata_limit
from .safeio import GateError, _parse_json, atomic_bytes, create_only_bytes, sha, within, lock, nonempty

REQUEST = 'agentos.refusal-recovery-request/v1'
MODERN_REQUEST = 'agentos.refusal-recovery-request/v2'
MODERN_RECEIPT = 'agentos.refusal-recovery-receipt/v2'
PERMIT = 'agentos.refusal-recovery-permit/v1'
RECEIPT = 'agentos.refusal-recovery-receipt/v1'
JOURNAL = 'agentos.refusal-recovery-transaction/v1'
MAX_SCOPE_PATHS = 64  # Explicit metadata list capacity; no broader path authority.
MAX_DOCUMENT = 16 * 1024
MAX_METADATA = 4 * 1024 * 1024  # Existing safeio metadata ceiling, not source/scanner capacity.
OBSERVATION_SECONDS = 900
ERROR = 'handoff_acceptance_failed:SECRET_DETECTED'
RESERVATION = 'agentos.refusal-recovery-reservation/v1'
MAX_TASK_METADATA_ENTRIES = 256


def fail(code='recovery_metadata_invalid'):
    raise GateError(code)


def enc(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()


def keys(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        fail()


def ident(value, pattern):
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        fail()
    return value


def short(value):
    return ident(value, r'[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,299}')


def digest(value):
    return ident(value, r'[0-9a-f]{64}')


def uuid(value):
    return ident(value, r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


def op(value):
    return ident(value, r'[0-9a-f]{32}')


def canonical(value):
    if not isinstance(value, str) or len(value) > 2048 or not Path(value).is_absolute():
        fail()
    if str(Path(value).resolve()) != value:
        fail('recovery_canonical_root_required')
    return Path(value)


def stamp(value):
    if not isinstance(value, str) or len(value) > 40:
        fail()
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
            fail()
        return result
    except (ValueError, OverflowError):
        fail()


def _read(path, limit=MAX_DOCUMENT, missing=False):
    # Every caller supplies a known exact metadata path, never source/object discovery.
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    except FileNotFoundError:
        if missing:
            return None
        fail()
    except OSError:
        fail()
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            fail()
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        after = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if len(raw) != before.st_size or len(raw) > limit or any(getattr(before, k) != getattr(after, k) for k in fields):
            fail()
        return raw
    except OSError:
        fail()
    finally:
        os.close(fd)


def parse(raw):
    try:
        return _parse_json(raw)
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise GateError('recovery_metadata_invalid') from None


def document(path):
    return parse(_read(Path(path)))


def _sync(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _sync_to(path, boundary):
    current = path.parent
    while True:
        _sync(current)
        if current == boundary:
            break
        if boundary not in current.parents:
            fail()
        current = current.parent


def write(path, raw, boundary, *, only=False, readback_limit=MAX_METADATA):
    if only:
        create_only_bytes(path, raw, mode=0o600)
    else:
        atomic_bytes(path, raw, mode=0o600)
    _sync_to(path, boundary)
    if _read(path, readback_limit) != raw:
        fail('recovery_readback_failed')


def _path(root, rel):
    try:
        return within(root, rel)
    except (ValueError, OSError, TypeError):
        raise GateError('recovery_metadata_invalid') from None


def area(root, task_id, operation):
    ident(task_id, r'task-[0-9a-f]{16}'); op(operation)
    return _path(root, f'.agentos/tasks/{task_id}/refusal-recovery/{operation}')


def marker(root):
    return _path(root, '.agentos/refusal-recovery-transaction.json')


def pending(root):
    return _path(root, '.agentos/refusal-recovery-pending')


def require_clear(root):
    if pending(root).exists() or marker(root).exists():
        fail('refusal_recovery_transaction_pending')


def _reject_handoff_journals(root, task_id):
    # Real deliver writes direct task metadata handoff-{profile}-{fingerprint}.json.
    # Names only, bounded one directory; no journal body, source or library reads.
    directory = _path(root, f'.agentos/tasks/{task_id}')
    try:
        with os.scandir(directory) as entries:
            for count, entry in enumerate(entries, 1):
                if count > MAX_TASK_METADATA_ENTRIES:
                    fail('recovery_task_metadata_inventory_unavailable')
                if entry.name.lower().startswith('handoff-'):
                    # checkpoint/completion and uncertain handoff-shaped records
                    # all require their own separately authorized reconciliation.
                    fail('recovery_publication_unreconciled')
    except OSError:
        raise GateError('recovery_task_metadata_inventory_unavailable') from None


def _reserve(root, request, permit, phase, at):
    # This signal exists BEFORE request/permit/preimage preparation. Any error
    # after creation is UNKNOWN and every ordinary lifecycle gate stays closed.
    path = pending(root)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        fail('refusal_recovery_transaction_pending')
    except OSError:
        try:
            os.lstat(path)
        except FileNotFoundError:
            # No reservation and no preparation was started by this invocation.
            raise GateError('recovery_preparation_not_started') from None
        except OSError:
            raise GateError('recovery_operation_unknown') from None
        raise GateError('recovery_operation_unknown') from None
    _sync(path.parent)  # Establish durable fail-closed namespace before preparation.
    identity = {'schema': RESERVATION, 'operation_id': request['operation_id'],
                'task_id': request['task_id'], 'revision': request['revision'],
                'phase': phase, 'request_sha256': sha(enc(request)),
                'permit_sha256': sha(enc(permit)), 'at': at}
    write(path/'identity.json', enc(identity), root, only=True)


def _reservation(root, request):
    raw = _read(pending(root)/'identity.json', missing=True)
    if raw is None:
        return None
    value = parse(raw)
    keys(value, 'schema operation_id task_id revision phase request_sha256 permit_sha256 at')
    if (value['schema'] != RESERVATION or value['operation_id'] != request['operation_id']
            or value['task_id'] != request['task_id'] or type(value['revision']) is not int
            or value['revision'] != request['revision'] or value['phase'] not in {'ack','advance'}
            or value['request_sha256'] != sha(enc(request))):
        fail('recovery_operation_conflict')
    digest(value['permit_sha256']); stamp(value['at'])
    return value


def _release_committed_reservation(root, request, journal):
    path = pending(root)
    if not path.exists():
        return  # Crash after reservation release: the full journal still gates entry.
    identity = _reservation(root, request)
    if identity is not None:
        if identity['phase'] != journal['phase'] or identity['permit_sha256'] != journal['permit_sha256']:
            fail('recovery_operation_conflict')
        (path/'identity.json').unlink()
    # Only called after ALL fixed semantic postimages have been read back.
    # Missing identity may be a crash between unlink and rmdir; unknown extra
    # files make rmdir refuse. Incomplete preparation is NEVER removed here.
    path.rmdir()
    _sync(path.parent)


def validate_request(root, home, task_id, request):
    keys(request, 'schema root user_home operation_id actor_id session_id project_id task_id revision expected witness goal next_owner next_scope')
    if request['schema'] not in (REQUEST, MODERN_REQUEST) or canonical(request['root']) != root or canonical(request['user_home']) != home or request['task_id'] != task_id:
        fail('recovery_identity_mismatch')
    op(request['operation_id']); short(request['actor_id']); nonempty(request['session_id'], 'session_id', 200)
    ident(task_id, r'task-[0-9a-f]{16}'); ident(request['project_id'], r'project-[0-9a-f]{16}')
    if type(request['revision']) is not int or not 1 <= request['revision'] <= 2147483647:
        fail()
    e = request['expected']; keys(e, 'task_sha256 project_sha256 turn_sha256 bound_turn_id status')
    for key in ('task_sha256', 'project_sha256', 'turn_sha256'): digest(e[key])
    uuid(e['bound_turn_id'])
    if e['status'] != 'VERIFYING': fail()
    w = request['witness']; modern = request['schema'] == MODERN_REQUEST
    keys(w, 'root path bytes sha256 kind attempt_id exit_code' + (' diagnostic' if modern else ''))
    canonical(w['root']); digest(w['sha256']); _path(Path(w['root']), w['path'])
    if (not isinstance(w['path'], str) or not w['path'].endswith('.json') or type(w['bytes']) is not int
            or not 0 < w['bytes'] <= MAX_DOCUMENT
            or type(w['exit_code']) is not int or w['exit_code'] != 2): fail()
    if modern:
        if w['kind'] != 'owner_attested_modern_v1': fail()
        op(w['attempt_id'])
        _diagnostic_reference(request, w['diagnostic'])
    elif w['kind'] != 'owner_attested_legacy' or w['attempt_id'] is not None:
        fail()
    g = request['goal']; keys(g, 'state ref sha256'); short(g['ref']); digest(g['sha256'])
    if g['state'] != 'OPEN': fail()
    short(request['next_owner']); n = request['next_scope']; keys(n, 'ref write_paths'); short(n['ref'])
    if not isinstance(n['write_paths'], list) or not 0 < len(n['write_paths']) <= MAX_SCOPE_PATHS: fail()
    if any(not isinstance(x,str) for x in n['write_paths']) or len(set(n['write_paths']))!=len(n['write_paths']):fail()
    for path in n['write_paths']:
        if not isinstance(path, str) or len(path) > 512: fail()
        _path(root, path)
    if len(enc(request)) > MAX_DOCUMENT: fail()
    return request


def _diagnostic_reference(request, value):
    keys(value, 'path bytes sha256')
    expected = f".agentos/tasks/{request['task_id']}/diagnostics/{request['witness']['attempt_id']}.json"
    if (value['path'] != expected or type(value['bytes']) is not int
            or not 0 < value['bytes'] <= MAX_DOCUMENT): fail()
    digest(value['sha256'])
    _path(Path(request['root']), expected)
    return value


def _modern_fields(request):
    if request['schema'] == MODERN_REQUEST:
        return {'original_attempt_id': request['witness']['attempt_id'],
                'diagnostic_receipt': dict(request['witness']['diagnostic'])}
    return {}


def _task_recovery(request):
    value = {'schema': MODERN_RECEIPT if request['schema'] == MODERN_REQUEST else RECEIPT,
             'operation_id': request['operation_id'], 'revision': request['revision'],
             'request_sha256': sha(enc(request))}
    value.update(_modern_fields(request))
    return value


def _event_details(request):
    value = {'operation_id': request['operation_id'],
             'refusal_witness_sha256': request['witness']['sha256'],
             'full_goal': 'OPEN', 'partial_objects': 'UNKNOWN'}
    if request['schema'] == MODERN_REQUEST:
        value.update(schema=MODERN_RECEIPT, **_modern_fields(request))
    return value


def _validate_witness(root, request):
    w = request['witness']
    raw = _read(_path(Path(w['root']), w['path']))
    if _pin(raw) != {'bytes': w['bytes'], 'sha256': w['sha256']}:
        fail('recovery_witness_mismatch')
    witness = parse(raw)
    if request['schema'] == REQUEST:
        keys(witness, 'status error')
        if witness != {'status': 'BLOCKED', 'error': ERROR}: fail('recovery_witness_invalid')
        return
    keys(witness, 'status error diagnostic')
    if witness['status'] != 'BLOCKED' or witness['error'] != ERROR:
        fail('recovery_witness_invalid')
    # Reuse only pure producer validators. Never read its failing asset or library.
    from .handoff_diagnostics import public_envelope, validate_receipt
    from types import SimpleNamespace
    try:
        envelope = public_envelope(SimpleNamespace(handoff_diagnostic=witness['diagnostic']))
    except (ValueError, TypeError, RecursionError, OverflowError):
        fail('recovery_diagnostic_invalid')
    if envelope is None: fail('recovery_diagnostic_invalid')
    if envelope['metadata_status'] != 'SAVED': fail('recovery_diagnostic_unavailable')
    if (envelope['attempt_id'] != w['attempt_id']
            or enc(envelope['receipt']) != enc(w['diagnostic'])):
        fail('recovery_diagnostic_identity_mismatch')
    declared = _diagnostic_reference(request, envelope['receipt'])
    raw = _read(_path(root, declared['path']))
    if _pin(raw) != {'bytes': declared['bytes'], 'sha256': declared['sha256']}:
        fail('recovery_diagnostic_mismatch')
    try:
        metadata = validate_receipt(parse(raw))
    except (ValueError, TypeError, RecursionError, OverflowError):
        fail('recovery_diagnostic_invalid')
    if (metadata['task_id'] != request['task_id']
            or metadata['revision'] != request['revision']
            or metadata['attempt_id'] != w['attempt_id']
            or metadata['session_id'] != request['session_id']
            or metadata['turn_id'] != request['expected']['bound_turn_id']):
        fail('recovery_diagnostic_identity_mismatch')


def validate_permit(request, permit, phase, receipt_sha=None, journal_sha=None):
    keys(permit, 'schema owner_attested decision_ref decision_sha256 actor_id session_id current_turn_id observed_at observation_ref valid_from valid_until revoked root project_id task_id revision operation_id request_sha256 phase receipt_sha256 journal_sha256')
    if type(permit['revision']) is not int or not 1 <= permit['revision'] <= 2147483647:
        fail('recovery_authority_invalid')
    if (permit['schema'] != PERMIT or permit['owner_attested'] is not True or permit['revoked'] is not False
            or permit['phase'] != phase or permit['receipt_sha256'] != receipt_sha or permit['journal_sha256'] != journal_sha):
        fail('recovery_authority_invalid')
    for key in ('root', 'project_id', 'task_id', 'revision', 'operation_id', 'actor_id', 'session_id'):
        if permit[key] != request[key]: fail('recovery_authority_invalid')
    if permit['request_sha256'] != sha(enc(request)): fail('recovery_authority_invalid')
    digest(permit['decision_sha256']); short(permit['decision_ref']); short(permit['observation_ref']); uuid(permit['current_turn_id'])
    current = datetime.now(timezone.utc); observed = stamp(permit['observed_at'])
    if not 0 <= (current-observed).total_seconds() <= OBSERVATION_SECONDS or stamp(permit['valid_from']) > current:
        fail('recovery_authority_stale')
    if permit['valid_until'] is not None and stamp(permit['valid_until']) < current:
        fail('recovery_authority_stale')
    if phase == 'advance' and permit['current_turn_id'] == request['expected']['bound_turn_id']:
        fail('recovery_current_turn_required')
    if len(enc(permit)) > MAX_DOCUMENT: fail()


def _paths(root, home, request):
    from .turns import turn_path
    # Existing home/core separation and exact existing task-selected home stay mandatory.
    from .overlay import validate_roots
    validate_roots(home)
    return (_path(root, '.agentos/project.json'),
            _path(root, f".agentos/tasks/{request['task_id']}/task.json"),
            turn_path(home, request['session_id']))


def _metadata(root, home, request):
    paths = _paths(root, home, request)
    raws = [_read(p, task_metadata_limit(root) if i == 1 else MAX_METADATA) for i, p in enumerate(paths)]
    values = [parse(raw) for raw in raws]
    project, task, binding = values
    if (not all(isinstance(x, dict) for x in values)
            or project.get('schema') != 'agentos.project/v1' or project.get('id') != request['project_id']
            or project.get('active_task') != request['task_id'] or task.get('schema') != 'agentos.project-task/v1'
            or task.get('id') != request['task_id'] or task.get('project_id') != request['project_id']
            or type(task.get('revision')) is not int or task['revision'] != request['revision']
            or task.get('session_id') != request['session_id'] or task.get('turn_id') != request['expected']['bound_turn_id']
            or task.get('handoff_user_home') != str(home) or binding.get('schema') != 'agentos.turn/v1'
            or binding.get('session_id') != request['session_id'] or binding.get('root') != str(root)):
        fail('recovery_identity_mismatch')
    return paths, raws, values


def _base_receipt(request, phase, at, permit_sha):
    return {'schema': MODERN_RECEIPT if request['schema'] == MODERN_REQUEST else RECEIPT, 'operation_id': request['operation_id'], 'task_id': request['task_id'],
            'revision': request['revision'], 'request_sha256': sha(enc(request)), 'phase': phase, 'at': at,
            'original_error': ERROR, 'original_attempt_id': None, 'partial_objects': 'UNKNOWN',
            'full_goal': 'OPEN', 'next_owner': request['next_owner'], 'semantic_acceptance': False,
            'ready_granted': False, 'authority_basis': 'OWNER_ATTESTED_NOT_AUTHENTICATED_BY_CORE',
            'authority_permit_sha256': permit_sha, **_modern_fields(request)}


def _ack(root, request):
    p = area(root, request['task_id'], request['operation_id'])/'ack.json'; raw = _read(p, missing=True)
    if raw is None: fail('recovery_ack_required')
    value = parse(raw)
    keys(value, 'schema operation_id task_id revision request_sha256 phase at original_error original_attempt_id partial_objects full_goal next_owner semantic_acceptance ready_granted authority_basis authority_permit_sha256 task_before_sha256 task_after_sha256 project_sha256 turn_before_sha256 witness_sha256' + (' diagnostic_receipt' if request['schema'] == MODERN_REQUEST else ''))
    if (type(value['revision']) is not int or not 1 <= value['revision'] <= 2147483647
            or value['semantic_acceptance'] is not False or value['ready_granted'] is not False
            or enc({k: value[k] for k in _modern_fields(request)}) != enc(_modern_fields(request))
            or (request['schema'] == REQUEST and value['original_attempt_id'] is not None)):fail()
    expected = _base_receipt(request, 'ack', value['at'], sha(_read(area(root,request['task_id'],request['operation_id'])/'permit-ack.json')))
    if enc({k: value[k] for k in expected}) != enc(expected): fail()
    for key in ('task_before_sha256','task_after_sha256','project_sha256','turn_before_sha256','witness_sha256'): digest(value[key])
    if (value['task_before_sha256'] != request['expected']['task_sha256'] or value['project_sha256'] != request['expected']['project_sha256']
            or value['turn_before_sha256'] != request['expected']['turn_sha256'] or value['witness_sha256'] != request['witness']['sha256']): fail()
    stamp(value['at'])
    return value, raw


def _advance_receipt(root, request):
    p = area(root, request['task_id'], request['operation_id'])/'advance.json'; raw = _read(p, missing=True)
    if raw is None: return None, None
    value = parse(raw)
    keys(value, 'schema operation_id task_id revision request_sha256 phase at original_error original_attempt_id partial_objects full_goal next_owner semantic_acceptance ready_granted authority_basis authority_permit_sha256 task_after_sha256 turn_before_sha256 turn_after_sha256 target_turn_id ack_sha256' + (' diagnostic_receipt' if request['schema'] == MODERN_REQUEST else ''))
    if (type(value['revision']) is not int or not 1 <= value['revision'] <= 2147483647
            or value['semantic_acceptance'] is not False or value['ready_granted'] is not False
            or enc({k: value[k] for k in _modern_fields(request)}) != enc(_modern_fields(request))
            or (request['schema'] == REQUEST and value['original_attempt_id'] is not None)):fail()
    expected = _base_receipt(request, 'advance', value['at'], sha(_read(area(root,request['task_id'],request['operation_id'])/'permit-advance.json')))
    if enc({k: value[k] for k in expected}) != enc(expected): fail()
    for key in ('task_after_sha256','turn_before_sha256','turn_after_sha256','ack_sha256'):digest(value[key])
    uuid(value['target_turn_id']); stamp(value['at'])
    return value, raw


def _result(request, state, *, replay=False, journal_sha=None):
    return {'schema': MODERN_RECEIPT if request['schema'] == MODERN_REQUEST else RECEIPT, 'status': state, 'operation_id': request['operation_id'],
            'task_id': request['task_id'], 'revision': request['revision'], 'historical_replay': replay,
            'full_goal': 'OPEN', 'partial_objects': 'UNKNOWN', 'semantic_acceptance': False,
            'ready_granted': False, 'journal_sha256': journal_sha, **_modern_fields(request)}


def _targets(root, home, request, phase):
    _, task, turn = _paths(root, home, request); directory = area(root, request['task_id'], request['operation_id'])
    if phase == 'ack':
        return [('task',task,root), ('events',task.parent/'events.jsonl',root), ('ack',directory/'ack.json',root)]
    if phase == 'advance':
        return [('turn',turn,home), ('advance',directory/'advance.json',root)]
    fail()


def _pin(raw):
    return None if raw is None else {'sha256': sha(raw), 'bytes': len(raw)}


def _staged(root, request, phase, label, side):
    return area(root, request['task_id'], request['operation_id'])/f'{phase}-{label}.{side}'


def _prepare(root, home, request, permit, phase, data, at):
    # Qualify exact typed row bounds before reserving or staging anything.
    for label,path,_ in _targets(root,home,request,phase):
        cap=task_metadata_limit(root) if label=='task' else MAX_METADATA
        if len(data[label])>cap or (label not in {'task','events'} and len(data[label])>MAX_DOCUMENT):fail()
        _read(path,cap,missing=True)
    _reserve(root, request, permit, phase, at)
    directory = area(root, request['task_id'], request['operation_id'])
    # Only the first actual operation may prepare. Incomplete preparation remains UNKNOWN.
    for name,raw in [('request.json',enc(request)),(f'permit-{phase}.json',enc(permit))]:
        p=directory/name; current=_read(p,missing=True)
        if current is not None and current != raw: fail('recovery_operation_conflict')
        if current is None:write(p,raw,root,only=True)
    records=[]
    for label,path,_ in _targets(root,home,request,phase):
        cap=task_metadata_limit(root) if label=='task' else MAX_METADATA
        before=_read(path,cap,missing=True); after=data[label]
        if len(after)>cap or (label not in {'task','events'} and len(after)>MAX_DOCUMENT):fail()
        for side,raw in [('before',before),('after',after)]:
            if raw is not None:write(_staged(root,request,phase,label,side),raw,root,only=True,readback_limit=cap)
        records.append({'label':label,'before':_pin(before),'after':_pin(after)})
    j={'schema':JOURNAL,'operation_id':request['operation_id'],'task_id':request['task_id'],
       'phase':phase,'request_sha256':sha(enc(request)),'permit_sha256':sha(enc(permit)),'at':at,'files':records}
    write(marker(root),enc(j),root,only=True)
    _finish(root,home,request,j)


def _journal(root, request):
    raw=_read(marker(root)); j=parse(raw)
    keys(j,'schema operation_id task_id phase request_sha256 permit_sha256 at files')
    if (j['schema']!=JOURNAL or j['operation_id']!=request['operation_id'] or j['task_id']!=request['task_id']
            or j['request_sha256']!=sha(enc(request)) or j['phase'] not in {'ack','advance'}): fail('recovery_operation_conflict')
    stamp(j['at']);digest(j['permit_sha256'])
    labels = ['task','events','ack'] if j['phase']=='ack' else ['turn','advance']
    if not isinstance(j['files'],list) or len(j['files'])!=len(labels):fail()
    for record,label in zip(j['files'],labels):
        keys(record,'label before after')
        if record['label']!=label or record['after'] is None:fail()
        for side in ('before','after'):
            value=record[side]
            if value is not None:
                keys(value,'sha256 bytes');digest(value['sha256'])
                if type(value['bytes']) is not int or not 0<=value['bytes']<=(task_metadata_limit(root) if label=='task' else MAX_METADATA):fail()
    return j,raw


def _validate_postimages(root,home,request,j,loaded):
    # Typed canonical JSON preserves bool/int/float identity, unlike dict equality.
    # Key order/whitespace are representation only. Validate ALL postimages before writes.
    if j['phase']=='ack':
        before=parse(loaded['task'][0]); after=parse(loaded['task'][1]); expected=dict(before)
        expected.update(status='RECOVERY_REQUIRED',recovery=_task_recovery(request))
        if sha(loaded['task'][0])!=request['expected']['task_sha256'] or enc(after)!=enc(expected):fail()
        rec=parse(loaded['ack'][1]); expected_rec=_base_receipt(request,'ack',j['at'],j['permit_sha256'])
        expected_rec.update(task_before_sha256=sha(loaded['task'][0]),task_after_sha256=sha(loaded['task'][1]),
                            project_sha256=request['expected']['project_sha256'],turn_before_sha256=request['expected']['turn_sha256'],witness_sha256=request['witness']['sha256'])
        if enc(rec)!=enc(expected_rec):fail()
        event=enc({'at':j['at'],'event':'REFUSAL_ACKNOWLEDGED','details':_event_details(request)})
        if loaded['events'][1] != (loaded['events'][0] or b'')+event or loaded['ack'][0] is not None:fail()
    else:
        ack,ackraw=_ack(root,request); permit=parse(_read(area(root,request['task_id'],request['operation_id'])/'permit-advance.json'))
        # Current reconcile permission is validated separately; preserve the original target turn.
        before=parse(loaded['turn'][0]); expected={'schema':'agentos.turn/v1','session_id':request['session_id'],
            'turn_id':permit['current_turn_id'],'root':str(root),'task_id':None,'status':'INTAKE_REQUIRED',
            'at':j['at'],'hook_seen':False,'source':'standalone_cli'}
        if sha(loaded['turn'][0])!=ack['turn_before_sha256'] or enc(parse(loaded['turn'][1]))!=enc(expected):fail()
        rec=_base_receipt(request,'advance',j['at'],j['permit_sha256']); rec.update(task_after_sha256=ack['task_after_sha256'],
            turn_before_sha256=sha(loaded['turn'][0]),turn_after_sha256=sha(loaded['turn'][1]),
            target_turn_id=permit['current_turn_id'],ack_sha256=sha(ackraw))
        if enc(parse(loaded['advance'][1]))!=enc(rec) or loaded['advance'][0] is not None:fail()


def _finish(root, home, request, j):
    targets=_targets(root,home,request,j['phase']); records=j['files']
    original_permit=_read(area(root,request['task_id'],request['operation_id'])/('permit-'+j['phase']+'.json'))
    if sha(original_permit)!=j['permit_sha256']:fail('recovery_transaction_conflict')
    if not isinstance(records,list) or [x.get('label') if isinstance(x,dict) else None for x in records]!=[x[0] for x in targets]:fail()
    loaded={}
    for record,(label,path,_) in zip(records,targets):
        keys(record,'label before after'); pair=[]
        for side in ('before','after'):
            p=record[side]
            if p is not None:
                keys(p,'sha256 bytes');digest(p['sha256'])
                if type(p['bytes']) is not int or not 0<=p['bytes']<=(task_metadata_limit(root) if label=='task' else MAX_METADATA):fail()
                raw=_read(_staged(root,request,j['phase'],label,side),task_metadata_limit(root) if label=='task' else MAX_METADATA)
                if _pin(raw)!=p:fail()
            else:raw=None
            pair.append(raw)
        if pair[1] is None:fail()
        current=_read(path,task_metadata_limit(root) if label=='task' else MAX_METADATA,missing=True)
        if current not in pair:fail('recovery_transaction_conflict')
        loaded[label]=pair
    _validate_postimages(root,home,request,j,loaded)
    for label,path,boundary in targets:
        before,after=loaded[label]
        cap=task_metadata_limit(root) if label=='task' else MAX_METADATA
        if _read(path,cap,missing=True)!=after:write(path,after,boundary,only=before is None,readback_limit=cap)
    for label,path,_ in targets:
        if _read(path,task_metadata_limit(root) if label=='task' else MAX_METADATA)!=loaded[label][1]:fail('recovery_readback_failed')
    _release_committed_reservation(root, request, j)
    marker(root).unlink();_sync(marker(root).parent)


def _entry_clear(root):
    if _path(root,'.agentos/entry-transaction.json').exists():fail('entry_recovery_required')


def _protected_call(call):
    try:return call()
    except GateError:
        raise
    except (OSError,ValueError,TypeError,KeyError,RecursionError,OverflowError):
        raise GateError('recovery_operation_unknown') from None


def acknowledge(root, home, task_id, request, permit):
    def run():
        validate_request(root,home,task_id,request);validate_permit(request,permit,'ack')
        with lock(_path(root,'.agentos/write.lock')), lock(_path(home,'state/turns.lock')):
            _entry_clear(root);require_clear(root)
            directory=area(root,task_id,request['operation_id'])
            if (directory/'ack.json').exists():
                _ack(root,request);return _result(request,'ACKNOWLEDGED',replay=True)
            if (directory/'request.json').exists():fail('recovery_operation_unfinished')
            _,raws,values=_metadata(root,home,request);project,task,binding=values;e=request['expected']
            if [sha(x) for x in raws]!=[e['project_sha256'],e['task_sha256'],e['turn_sha256']]:fail('recovery_cas_mismatch')
            if task.get('status')!='VERIFYING' or binding.get('status')!='ENTERED' or binding.get('task_id')!=task_id or binding.get('turn_id')!=e['bound_turn_id']:fail('recovery_state_invalid')
            if task.get('checkpoint') or task.get('closeout'):fail('recovery_publication_unreconciled')
            _reject_handoff_journals(root, task_id)
            w=request['witness'];_validate_witness(root,request)
            task=dict(task);task.update(status='RECOVERY_REQUIRED',recovery=_task_recovery(request))
            at=datetime.now(timezone.utc).isoformat();ack=_base_receipt(request,'ack',at,sha(enc(permit)))
            ack.update(task_before_sha256=sha(raws[1]),task_after_sha256=sha(enc(task)),project_sha256=sha(raws[0]),turn_before_sha256=sha(raws[2]),witness_sha256=w['sha256'])
            events=_read(_path(root,f'.agentos/tasks/{task_id}/events.jsonl'),MAX_METADATA,missing=True) or b''
            event={'at':at,'event':'REFUSAL_ACKNOWLEDGED','details':_event_details(request)}
            _prepare(root,home,request,permit,'ack',{'task':enc(task),'events':events+enc(event),'ack':enc(ack)},at)
            return _result(request,'ACKNOWLEDGED')
    return _protected_call(run)


def advance(root, home, task_id, request, permit):
    def run():
        validate_request(root,home,task_id,request)
        with lock(_path(root,'.agentos/write.lock')),lock(_path(home,'state/turns.lock')):
            _entry_clear(root);require_clear(root);ack,ackraw=_ack(root,request)
            validate_permit(request,permit,'advance',sha(ackraw))
            old,oldraw=_advance_receipt(root,request)
            if old is not None:
                if old['target_turn_id']!=permit['current_turn_id']:fail('recovery_turn_changed_requires_review')
                return _result(request,'ADVANCED',replay=True)
            if (area(root,task_id,request['operation_id'])/'permit-advance.json').exists():fail('recovery_operation_unfinished')
            _,raws,values=_metadata(root,home,request);project,task,binding=values
            if (sha(raws[0])!=ack['project_sha256'] or sha(raws[1])!=ack['task_after_sha256'] or sha(raws[2])!=ack['turn_before_sha256']):fail('recovery_cas_mismatch')
            if task.get('status')!='RECOVERY_REQUIRED' or binding.get('status')!='ENTERED' or binding.get('task_id')!=task_id:fail('recovery_state_invalid')
            at=datetime.now(timezone.utc).isoformat();turn={'schema':'agentos.turn/v1','session_id':request['session_id'],'turn_id':permit['current_turn_id'],'root':str(root),'task_id':None,'status':'INTAKE_REQUIRED','at':at,'hook_seen':False,'source':'standalone_cli'}
            rec=_base_receipt(request,'advance',at,sha(enc(permit)));rec.update(task_after_sha256=ack['task_after_sha256'],turn_before_sha256=sha(raws[2]),turn_after_sha256=sha(enc(turn)),target_turn_id=permit['current_turn_id'],ack_sha256=sha(ackraw))
            _prepare(root,home,request,permit,'advance',{'turn':enc(turn),'advance':enc(rec)},at)
            return _result(request,'ADVANCED')
    return _protected_call(run)


def status(root, home, task_id, operation):
    def run():
        directory=area(root,task_id,operation);raw=_read(directory/'request.json',missing=True)
        if raw is None:
            blocked = pending(root).exists() or marker(root).exists()
            return {'schema':RECEIPT,'status':'UNKNOWN' if blocked else 'METADATA_UNAVAILABLE',
                    'operation_id':operation,'task_id':task_id,'ready_granted':False,
                    'pending_identity':'NOT_VERIFIED_WITHOUT_SAVED_REQUEST' if blocked else None}
        request=validate_request(root,home,task_id,parse(raw))
        if marker(root).exists():
            j,jraw=_journal(root,request)
            return _result(request,'PREPARED',journal_sha=sha(jraw))
        if pending(root).exists():
            identity = _reservation(root, request)
            result = _result(request,'UNKNOWN')
            result['unknown_phase'] = identity['phase'] if identity else 'UNAVAILABLE'
            return result
        adv,_=_advance_receipt(root,request)
        if adv is not None:
            ack,ackraw=_ack(root,request)
            if adv['ack_sha256']!=sha(ackraw) or adv['task_after_sha256']!=ack['task_after_sha256']:fail()
            return _result(request,'ADVANCED',replay=True)
        if (directory/'ack.json').exists():
            _ack(root,request)
            if (directory/'permit-advance.json').exists():
                result=_result(request,'UNKNOWN');result['unknown_phase']='advance';result['acknowledged']=True
                return result
            return _result(request,'ACKNOWLEDGED',replay=True)
        return _result(request,'UNKNOWN')
    return _protected_call(run)


def reconcile(root, home, task_id, request, permit):
    def run():
        validate_request(root,home,task_id,request)
        with lock(_path(root,'.agentos/write.lock')),lock(_path(home,'state/turns.lock')):
            _entry_clear(root);j,jraw=_journal(root,request)
            validate_permit(request,permit,'reconcile',journal_sha=sha(jraw))
            # No original operation is re-executed; exact existing metadata postimages only.
            directory=area(root,task_id,request['operation_id'])
            stored=parse(_read(directory/'request.json'))
            if stored!=request:fail('recovery_operation_conflict')
            # Protect project/task/binding metadata outside this transaction's own targets.
            project_raw=_read(_path(root,'.agentos/project.json'),MAX_METADATA)
            if sha(project_raw)!=request['expected']['project_sha256']:fail('recovery_cas_mismatch')
            if j['phase']=='ack':
                from .turns import turn_path
                if sha(_read(turn_path(home,request['session_id'])))!=request['expected']['turn_sha256']:fail('recovery_cas_mismatch')
            else:
                ack,_=_ack(root,request)
                if sha(_read(_path(root,f'.agentos/tasks/{task_id}/task.json'),task_metadata_limit(root)))!=ack['task_after_sha256']:fail('recovery_cas_mismatch')
            audit=directory/('reconcile-permit-'+sha(enc(permit))+'.json')
            prior=_read(audit,missing=True)
            if prior is None:write(audit,enc(permit),root,only=True)
            elif prior!=enc(permit):fail('recovery_operation_conflict')
            _finish(root,home,request,j)
            return _result(request,'ACKNOWLEDGED' if j['phase']=='ack' else 'ADVANCED')
    return _protected_call(run)


def validate_resume(root, home, task, session_id, turn_id, answers):
    """Called under ordinary project enter lock, before answers/status mutation."""
    recovery=task.get('recovery')
    if not isinstance(recovery,dict) or recovery.get('schema') not in (RECEIPT,MODERN_RECEIPT):fail('recovery_resume_required')
    directory=area(root,task['id'],recovery.get('operation_id'))
    request=validate_request(root,home,task['id'],parse(_read(directory/'request.json')))
    if enc(recovery) != enc(_task_recovery(request)):fail('recovery_resume_cas_mismatch')
    if sorted(answers.get('write_paths',[]))!=sorted(request['next_scope']['write_paths']):
        fail('recovery_resume_scope_mismatch')
    ack,ackraw=_ack(root,request);adv,advraw=_advance_receipt(root,request)
    if adv is None:fail('recovery_advance_required')
    _,raws,_=_metadata(root,home,request)
    if (session_id!=request['session_id'] or turn_id!=adv['target_turn_id'] or sha(raws[0])!=ack['project_sha256']
            or sha(raws[1])!=ack['task_after_sha256'] or sha(raws[2])!=adv['turn_after_sha256']
            or adv['ack_sha256']!=sha(ackraw) or adv['task_after_sha256']!=ack['task_after_sha256']):fail('recovery_resume_cas_mismatch')
