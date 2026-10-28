"""Opt-in source-only accounting. This journal grants no execution authority."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from .safeio import GateError, MAX_JSON, atomic_json, digest, identifier, lock, nonempty, now, read_json, read_json_input, within

SCHEMA = 'agentos.local-journal/v1'
EFFECTS = {'source-only', 'offline-test'}


def _path(root):
    if not root.is_dir() or root.is_symlink():
        raise GateError('local_root_must_be_existing_real_directory')
    return within(root, '.agentos/lite/journal.json')


def _load(root):
    path = _path(root)
    value = read_json(path) if path.exists() else {'schema': SCHEMA, 'root': str(root.resolve()), 'events': []}
    if not isinstance(value, dict) or value.get('schema') != SCHEMA or value.get('root') != str(root.resolve()) or not isinstance(value.get('events'), list):
        raise GateError('local_journal_invalid')
    previous = None
    seen = set()
    tasks = {}
    for seq, event in enumerate(value['events'], 1):
        if not isinstance(event, dict):
            raise GateError('local_event_invalid')
        body = {k: v for k, v in event.items() if k != 'hash'}
        if event.get('seq') != seq or event.get('previous') != previous or event.get('hash') != digest(body):
            raise GateError('local_journal_integrity_conflict')
        op = identifier(event.get('operation_id'))
        if op in seen:
            raise GateError('local_duplicate_operation')
        seen.add(op)
        identifier(event.get('task_id')); identifier(event.get('executor'))
        if event.get('kind') == 'REGISTER':
            payload = event.get('payload')
            _registration(payload)
            task_id = _task_id(payload)
            if task_id != event['task_id'] or task_id in tasks:
                raise GateError('local_task_identity_conflict')
            tasks[task_id] = event
        elif event.get('kind') in {'PROGRESS', 'CHECKPOINT', 'RESULT'}:
            if event['task_id'] not in tasks or tasks[event['task_id']]['executor'] != event['executor']:
                raise GateError('local_executor_conflict')
            if not isinstance(event.get('payload'), dict):
                raise GateError('local_payload_invalid')
        else:
            raise GateError('local_event_kind_invalid')
        previous = event['hash']
    return value


def _registration(value):
    if not isinstance(value, dict) or value.get('effect') not in EFFECTS:
        raise GateError('local_effect_not_permitted')
    for key in ('project_key', 'task_key'):
        identifier(value.get(key))
    for key in ('goal', 'scope', 'acceptance', 'authority_ref'):
        nonempty(value.get(key), key)


def _task_id(payload):
    return 'local-' + digest([payload['project_key'], payload['task_key']])[:32]


def _legacy_guard(root):
    # Never hide interrupted entry or an already active writer in this root.
    for rel in ('.agentos/entry-transaction.json', '.agentos/refusal-recovery.json', '.agentos/interrupted-continuation.json'):
        if within(root, rel).exists():
            raise GateError('local_legacy_reconciliation_required')
    project_path = within(root, '.agentos/project.json')
    if project_path.exists():
        project = read_json(project_path)
        task = project.get('active_task')
        if task:
            identifier(task)
            record = read_json(within(root, f'.agentos/tasks/{task}/task.json'))
            if record.get('status') not in {'CLOSED', 'CHECKPOINT'}:
                raise GateError('local_existing_writer_reconciliation_required')


def _response(status, **extra):
    return {'status': status, 'ready': False, 'authority_granted': False, **extra}


def record(root: Path, request: dict) -> dict:
    """Atomic, idempotent one-event transition. No user home is inspected."""
    operation = identifier(request.get('operation_id'))
    executor = identifier(request.get('executor'))
    kind = request.get('kind')
    payload = request.get('payload')
    if not isinstance(payload, dict) or kind not in {'REGISTER', 'PROGRESS', 'CHECKPOINT', 'RESULT'}:
        raise GateError('local_request_invalid')
    if kind == 'REGISTER':
        _registration(payload)
        task_id = _task_id(payload)
    else:
        task_id = identifier(request.get('task_id'))
    wanted = {'operation_id': operation, 'executor': executor, 'kind': kind, 'task_id': task_id, 'payload': payload}
    try:
        with lock(within(root, '.agentos/lite/write.lock')):
            _legacy_guard(root)
            ledger = _load(root)
            for event in ledger['events']:
                if event['operation_id'] == operation:
                    if any(event.get(k) != v for k, v in wanted.items()):
                        return _response('CONFLICT', reason='operation_identity_conflict')
                    return _response('LOCAL_RECORDED', task_id=task_id, event_hash=event['hash'], replay=True)
            registration = next((e for e in ledger['events'] if e['task_id'] == task_id and e['kind'] == 'REGISTER'), None)
            if kind == 'REGISTER' and registration is not None:
                return _response('CONFLICT', reason='task_already_registered', task_id=task_id)
            if kind != 'REGISTER' and (registration is None or registration['executor'] != executor):
                return _response('CONFLICT', reason='task_or_executor_mismatch')
            event = {**wanted, 'seq': len(ledger['events']) + 1, 'at': now(), 'previous': ledger['events'][-1]['hash'] if ledger['events'] else None}
            event['hash'] = digest(event)
            ledger['events'].append(event)
            if len(json.dumps(ledger).encode()) > MAX_JSON // 2:
                raise GateError('local_journal_size_limit')
            atomic_json(_path(root), ledger)
            observed = _load(root)
            if observed != ledger:
                raise GateError('local_readback_conflict')
            return _response('LOCAL_RECORDED', task_id=task_id, event_hash=event['hash'], replay=False)
    except OSError:
        # A failure can follow replacement: do not lie that nothing was written.
        try:
            match = next((e for e in _load(root)['events'] if e['operation_id'] == operation), None)
        except (OSError, ValueError):
            return _response('NOT_RECORDED', storage_outcome='UNKNOWN', operation_id=operation)
        if match is not None and all(match.get(k) == v for k, v in wanted.items()):
            return _response('LOCAL_RECORDED', task_id=task_id, event_hash=match['hash'], reconciled=True)
        return _response('NOT_RECORDED', storage_outcome='NOT_OBSERVED', operation_id=operation)


def status(root: Path) -> dict:
    path = _path(root)
    if not path.exists():
        return _response('NOT_RECORDED', event_count=0)
    ledger = _load(root)
    return _response('LOCAL_RECORDED', event_count=len(ledger['events']), head=ledger['events'][-1]['hash'] if ledger['events'] else None)


def sync(root: Path, central_home: Path) -> dict:
    """Explicit additive projection; sync never calls enter/ready/bind_turn."""
    # Local then central lock order, one atomic central commit. No local marker
    # can claim future sync freshness. Readback is repeated on every sync.
    if central_home.resolve() == root.resolve() or root.resolve() in central_home.resolve().parents or central_home.resolve() in root.resolve().parents:
        raise GateError('local_central_roots_must_be_disjoint')
    try:
        with lock(within(root, '.agentos/lite/write.lock')):
            ledger = _load(root)
            if not ledger['events']:
                return _response('NOT_RECORDED', event_count=0)
            target = within(central_home, 'state/local-projects/registry.json')
            with lock(within(central_home, 'state/local-projects/sync.lock')):
                registry = read_json(target) if target.exists() else {'schema': 'agentos.local-registry/v1', 'journals': {}}
                _validate_registry(registry)
                journals = registry['journals']
                source = digest(ledger['root'])
                for key, other in journals.items():
                    if key == source:
                        continue
                    theirs = {e['task_id'] for e in other['events']}
                    if any(e['task_id'] in theirs for e in ledger['events']):
                        return _response('CONFLICT', reason='central_task_owned_by_other_journal')
                old = journals.get(source)
                if old is not None and (old['root'] != ledger['root'] or ledger['events'][:len(old['events'])] != old['events']):
                    return _response('CONFLICT', reason='central_history_diverged')
                added = len(ledger['events']) - len(old['events']) if old else len(ledger['events'])
                journals[source] = ledger
                if len(json.dumps(registry).encode()) > MAX_JSON // 2:
                    raise GateError('local_registry_size_limit')
                if added:
                    atomic_json(target, registry)
                if read_json(target) != registry:
                    raise GateError('local_sync_readback_conflict')
                return _response('SYNCED', added_events=added, head=ledger['events'][-1]['hash'])
    except OSError:
        return _response('LOCAL_RECORDED', sync='UNKNOWN', reason='central_unavailable_reconcile_same_sync')


def _validate_registry(registry):
    if not isinstance(registry, dict) or registry.get('schema') != 'agentos.local-registry/v1' or not isinstance(registry.get('journals'), dict):
        raise GateError('local_registry_invalid')
    # Validate projected chains without dereferencing any root from stored data.
    for key, ledger in registry['journals'].items():
        if not isinstance(ledger, dict) or key != digest(ledger.get('root')) or ledger.get('schema') != SCHEMA or not isinstance(ledger.get('events'), list):
            raise GateError('local_registry_integrity_conflict')
        previous = None
        for seq, event in enumerate(ledger['events'], 1):
            if not isinstance(event, dict) or event.get('seq') != seq or event.get('previous') != previous or event.get('hash') != digest({k:v for k,v in event.items() if k != 'hash'}):
                raise GateError('local_registry_integrity_conflict')
            previous = event['hash']


def command(argv, user_home):
    parser = argparse.ArgumentParser(prog='agentos project local')
    parser.add_argument('action', choices=('record', 'status', 'sync'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--request', type=Path)
    args = parser.parse_args(argv)
    if args.action == 'record':
        if args.request is None:
            parser.error('--request is required for record')
        result = record(args.root, read_json_input(args.request))
    elif args.action == 'status':
        result = status(args.root)
    else:
        result = sync(args.root, user_home)
    return result, 0 if result['status'] in {'LOCAL_RECORDED', 'SYNCED'} else 2
