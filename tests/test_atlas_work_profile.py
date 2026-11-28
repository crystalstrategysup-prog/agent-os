"""The real Atlas façade, fresh CLI processes and no implicit authority."""
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest import mock
import pytest
from agent_os import atlas_module, workflow, doc_catalog

ROOT = Path(__file__).resolve().parents[1]


def choose(kind='project-change', effects=None, **facts):
    with atlas_module._workspace():
        return importlib.import_module('work_profile').select_profile(workflow.route(kind, effects), **facts)


def current(**extra):
    return {'changes': ['source'], 'bounded': True, 'context': 'CURRENT', 'writer': 'CURRENT', **extra}


@pytest.mark.parametrize('kind', ['question', 'search', 'audit', 'discovery'])
def test_read_only_direct_without_context_or_writer(kind):
    r = choose(kind)
    assert r['status'] == 'FAST_PATH' and r['mode'] == 'READ_ONLY' and r['writes'] == []
    assert r['foundation_route']['intake_required'] is False


def test_bounded_local_change_minimal_not_ready():
    r = choose(effects=['local-project-write'], **current())
    assert r['mode'] == 'MINIMAL' and r['status'] == 'PROFILE_SELECTED'
    assert r['ready_granted'] is r['product_writes_authorized'] is False
    assert r['foundation_route']['documentation_before_product_writes'] is True


@pytest.mark.parametrize('change', ['architecture', 'contract', 'data', 'multi-module',
                                    'multi-actor', 'new-project', 'instruction-routing'])
def test_full_for_real_complexity(change):
    r = choose(**current(changes=[change]))
    assert r['mode'] == 'FULL' and change in r['reasons']


def test_explicit_full_unbounded_or_missing_change_not_minimal():
    assert choose(**current(full=True))['mode'] == 'FULL'
    assert choose(**current(bounded=False))['mode'] == 'FULL'
    assert choose(**current(changes=[]))['mode'] == 'FULL'


@pytest.mark.parametrize('effect', workflow.TARGET_EFFECTS)
def test_target_controls_preserved(effect):
    r = choose(effects=[effect], **current())
    assert r['mode'] == 'FULL' and r['status'] == 'BLOCKED'
    assert r['foundation_route']['target_gates_required'] == [effect]
    assert r['external_authority_granted'] is False


@pytest.mark.parametrize('state', ['UNKNOWN', 'STALE', 'CONFLICT'])
@pytest.mark.parametrize('field', ['context', 'writer'])
def test_unknown_stale_or_conflict_never_ready(field, state):
    r = choose(**current(**{field: state}))
    assert r['status'] == 'UNKNOWN' and r['mode'] == 'FULL' and r['ready_granted'] is False


@pytest.mark.parametrize('fact', [{'bounded': 'true'}, {'full': 1}, {'changes': ['unknown']},
                                  {'changes': ['source', 'source']}, {'writer': 'FORCE'}])
def test_invalid_declarations_refused(fact):
    with pytest.raises(ValueError):
        choose(**current(**fact))


def test_write_cannot_be_called_read_only():
    with pytest.raises(ValueError, match='READ_ONLY_WITH_CHANGES'):
        choose('audit', **current())


def test_facade_never_reads_registry_for_optional_profile():
    stream = io.StringIO()
    with mock.patch.object(atlas_module, 'default_registry', side_effect=AssertionError('unneeded registry')):
        with contextlib.redirect_stdout(stream):
            assert atlas_module.main(['profile', '--kind', 'audit']) == 0
    assert json.loads(stream.getvalue())['mode'] == 'READ_ONLY'


def test_fresh_cli_has_no_user_state_writes(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), PYTHONPATH=str(ROOT / 'src'), PYTHONDONTWRITEBYTECODE='1')
    for kind in ('audit', 'project-change'):
        args = [sys.executable, '-B', '-m', 'agent_os', 'atlas', 'profile', '--kind', kind]
        if kind == 'project-change':
            args += ['--change', 'source', '--bounded', '--context', 'CURRENT', '--writer', 'CURRENT']
        p = subprocess.run(args, env=env, cwd=tmp_path, capture_output=True, text=True, timeout=10)
        assert p.returncode == 0, p.stdout + p.stderr
        r = json.loads(p.stdout)
        assert r['native_hooks'] == 'DISABLED' and r['writes'] == []
        if kind == 'project-change':
            assert r['foundation_route']['foundation_guidance']['development'] == {'level': 3, 'scope': 'task'}
    assert list(tmp_path.iterdir()) == []


def test_scoped_profile_preserves_real_target_gate(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), PYTHONPATH=str(ROOT / 'src'), PYTHONDONTWRITEBYTECODE='1')
    args = [sys.executable, '-B', '-m', 'agent_os', 'atlas', 'profile',
            '--kind', 'project-change', '--effect', 'deploy',
            '--development-level', '4', '--development-scope', 'stage:catalog']
    process = subprocess.run(args, env=env, cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert process.returncode == 2
    profile = json.loads(process.stdout)
    assert profile['status'] == 'BLOCKED' and profile['mode'] == 'FULL'
    route = profile['foundation_route']
    assert route['foundation_guidance']['development'] == {'level': 4, 'scope': 'stage:catalog'}
    assert route['target_gates_required'] == ['deploy'] and not profile['external_authority_granted']
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(('level', 'change', 'expected_level', 'mode'), [
    ('1D', 'source', 1, 'MINIMAL'), ('2', 'contract', 2, 'FULL'),
    ('3', 'source', 3, 'MINIMAL'), ('4', 'source', 4, 'MINIMAL'),
    ('5', 'contract', 5, 'FULL'),
])
def test_profile_facade_carries_caller_level_and_scope(level, change, expected_level, mode, capsys):
    args = ['profile', '--kind', 'project-change', '--change', change, '--bounded',
            '--context', 'CURRENT', '--writer', 'CURRENT', '--development-level', level,
            '--development-scope', 'module:catalog']
    assert atlas_module.main(args) == 0
    profile = json.loads(capsys.readouterr().out)
    assert profile['mode'] == mode
    assert profile['foundation_route']['foundation_guidance']['development'] == {
        'level': expected_level, 'scope': 'module:catalog',
    }
    assert not profile['product_writes_authorized'] and profile['writes'] == []


@pytest.mark.parametrize(('kind', 'fields', 'reason'), [
    ('project-change', ['--development-level', '1'], 'development_level_and_scope_required_together'),
    ('project-change', ['--development-scope', 'module'], 'development_level_and_scope_required_together'),
    ('project-change', ['--development-level', '0', '--development-scope', 'project'],
     'diagnostic_zero_use_project_diagnostics_with_saved_development_level'),
    ('audit', ['--development-level', '4', '--development-scope', 'stage'],
     'development_selection_requires_project_change'),
])
def test_profile_facade_refuses_invalid_development_selection(kind, fields, reason, capsys):
    assert atlas_module.main(['profile', '--kind', kind, *fields]) == 1
    assert json.loads(capsys.readouterr().out) == {'status': 'REFUSED', 'code': reason}


def test_full_reuses_existing_document_applicability():
    s = doc_catalog.select(['backend'], ['http-api'], 'architecture')
    assert {'architecture', 'contracts', 'http-api', 'security'} <= set(s['required'])
    assert 'model-card' not in s['required'] and 'safety' not in s['required']
