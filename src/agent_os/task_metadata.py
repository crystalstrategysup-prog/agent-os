"""Explicit project-only task JSON ceiling; never a generic JSON/provider limit."""
from pathlib import Path
import json
import re

from .safeio import (GateError, MAX_JSON, _parse_json, atomic_bytes, atomic_json,
                     identifier, lock, read_json, sha, within)

SCHEMA = 'agentos.project-task-metadata-budget/v1'
DEFAULT = MAX_JSON
MAXIMUM = 32 * 1024 * 1024
MAX_REVISION = 2147483647
LOWERING_TASKS = 10000
LOWERING_ENTRIES = 256


def budget(project):
    if not isinstance(project, dict):
        raise GateError('invalid_task_metadata_budget')
    if 'task_metadata_budget_revision' in project and (
        type(project['task_metadata_budget_revision']) is not int
        or not 1 <= project['task_metadata_budget_revision'] <= MAX_REVISION
    ):
        raise GateError('invalid_task_metadata_budget_revision')
    if 'task_metadata_budget' not in project:
        return {'schema': SCHEMA, 'max_bytes': DEFAULT}
    value = project['task_metadata_budget']
    if (not isinstance(value, dict) or set(value) != {'schema', 'max_bytes'}
            or value['schema'] != SCHEMA or type(value['max_bytes']) is not int
            or not DEFAULT <= value['max_bytes'] <= MAXIMUM):
        raise GateError('invalid_task_metadata_budget')
    return dict(value)


def limit(root):
    # Project policy itself remains under the unchanged generic4MiB reader.
    project = read_json(within(root, '.agentos/project.json'))
    if not isinstance(project, dict) or project.get('schema') != 'agentos.project/v1':
        raise GateError('unsupported_project_schema')
    return budget(project)['max_bytes']


def path(root, task_id):
    return within(root, '.agentos/tasks/' + identifier(task_id) + '/task.json')


def read_bytes(root, task_id):
    p = path(root, task_id)
    cap = limit(root)
    if p.is_symlink():
        raise GateError('symlink_file_refused')
    if not p.is_file():
        raise GateError('regular_json_file_required')
    with p.open('rb') as stream:
        data = stream.read(cap + 1)
    if len(data) > cap:
        raise GateError('json_size_limit')
    return data


def read_task(root, task_id):
    return _parse_json(read_bytes(root, task_id))


def encoded(task, cap=DEFAULT, *, error='task_metadata_limit'):
    if type(cap) is not int or not DEFAULT <= cap <= MAXIMUM:
        raise GateError('invalid_task_metadata_budget')
    data = (json.dumps(task, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    if len(data) > cap:
        raise GateError(error)
    return data


def write_bytes(root, task_id, data):
    if not isinstance(data, bytes):
        raise GateError('task_metadata_bytes_required')
    if len(data) > limit(root):
        raise GateError('task_metadata_limit')
    atomic_bytes(path(root, task_id), data)
    if read_bytes(root, task_id) != data:
        raise GateError('task_metadata_readback_failed')


def write_task(root, task):
    write_bytes(root, task['id'], encoded(task, limit(root)))


def _lowering_compatible(root, cap):
    # No arbitrary source traversal, body reads or deletion. Unknown retained
    # preimages make a lower policy unsafe even if the active task is small.
    backups = within(root, '.agentos/entry-backups')
    if backups.is_symlink() or (backups.exists() and any(backups.iterdir())):
        raise GateError('task_metadata_lowering_preimages_unverified')
    directory = within(root, '.agentos/tasks')
    if not directory.exists():
        return
    count = 0
    for child in directory.iterdir():
        count += 1
        if count > LOWERING_TASKS or child.is_symlink() or not child.is_dir():
            raise GateError('task_metadata_lowering_inventory_unverified')
        entries = 0
        for entry in child.iterdir():
            entries += 1
            if entries > LOWERING_ENTRIES or entry.is_symlink():
                raise GateError('task_metadata_lowering_inventory_unverified')
            if entry.name in {'interrupted-continuation', 'refusal-recovery'} or entry.name.startswith('handoff-'):
                raise GateError('task_metadata_lowering_preimages_unverified')
        task = child / 'task.json'
        if not task.is_file() or task.stat().st_size > cap:
            raise GateError('task_metadata_lowering_unreadable_task')


def set_budget(root, max_bytes=None, *, reset=False,
               expected_project_sha256=None, expected_budget_revision=None):
    from .project import root_path, load_project, project_file, _require_entry_recovered
    root = root_path(root)
    if reset and max_bytes is not None:
        raise GateError('task_metadata_set_reset_conflict')
    has_hash = expected_project_sha256 is not None
    if has_hash != (expected_budget_revision is not None):
        raise GateError('task_metadata_cas_pair_required')
    if has_hash:
        if (type(expected_project_sha256) is not str
                or re.fullmatch('[0-9a-f]{64}', expected_project_sha256) is None
                or type(expected_budget_revision) is not int
                or not 0 <= expected_budget_revision <= MAX_REVISION):
            raise GateError('task_metadata_cas_invalid')
        if max_bytes is None and not reset:
            raise GateError('task_metadata_cas_requires_write')
    if max_bytes is not None:
        budget({'task_metadata_budget': {'schema': SCHEMA, 'max_bytes': max_bytes}})
    changed = False
    if max_bytes is not None or reset:
        _require_entry_recovered(root)
        with lock(within(root, '.agentos/write.lock')):
            _require_entry_recovered(root)
            project = load_project(root)
            if has_hash:
                if sha(project_file(root).read_bytes()) != expected_project_sha256:
                    raise GateError('task_metadata_project_sha256_mismatch')
                if project.get('task_metadata_budget_revision', 0) != expected_budget_revision:
                    raise GateError('task_metadata_revision_mismatch')
            desired = None if reset else {'schema': SCHEMA, 'max_bytes': max_bytes}
            changed = project.get('task_metadata_budget') != desired
            if changed:
                target_limit = DEFAULT if reset else max_bytes
                if target_limit < budget(project)['max_bytes']:
                    _lowering_compatible(root, target_limit)
                generation = project.get('task_metadata_budget_revision', 0) + 1
                if generation > MAX_REVISION:
                    raise GateError('task_metadata_budget_revision_exhausted')
                project['task_metadata_budget_revision'] = generation
                if reset:
                    project.pop('task_metadata_budget', None)
                else:
                    project['task_metadata_budget'] = desired
                project['revision'] += 1
                atomic_json(project_file(root), project)
    else:
        project = load_project(root)
    return {'schema': 'agentos.task-metadata-budget-readback/v1', 'status': 'PASS',
            'root': str(root), 'project_id': project['id'], 'changed': changed,
            'explicit': 'task_metadata_budget' in project, 'project_revision': project['revision'],
            'budget_revision': project.get('task_metadata_budget_revision', 0),
            'effective': budget(project), 'external_authority_granted': False,
            'readiness': 'Normal current re-entry/READY required after policy change; no admission granted.'}
