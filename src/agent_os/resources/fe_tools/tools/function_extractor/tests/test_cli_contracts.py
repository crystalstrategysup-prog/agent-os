"""New CLI contract checks only; tiny local Git and pure frozen targets.

No AVL scenarios, application DB, Docker, provider, secrets or live state.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from tools.function_extractor import cli
from tools.function_extractor.runner.bundle import pack_bundle
from tools.function_extractor.runner.loader import load_engine


def _git(root, *args):
    result = subprocess.run(['/usr/bin/git', '-C', str(root), *args],
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'GIT_CONFIG_NOSYSTEM': '1',
             'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0'},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=True)
    return result.stdout.decode().strip()


@pytest.fixture
def tiny_repo(tmp_path):
    repo = tmp_path / 'repo'
    source = repo / 'src'
    source.mkdir(parents=True)
    template = tmp_path / 'empty-git-template'
    template.mkdir()
    _git(repo, 'init', '--quiet', '--template=' + str(template))
    (source/'calc.py').write_text('def inc(value):\n    return value + 1\n\ndef double(value):\n    return value * 2\n')
    _git(repo, 'add', 'src/calc.py')
    _git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@invalid',
         '-c', 'core.hooksPath=/dev/null', 'commit', '--quiet', '--no-gpg-sign', '-m', 'fixture')
    return repo, source, _git(repo, 'rev-parse', 'HEAD')


def _extract(source, output, commit=None, adapter=None):
    argv = ['extract', '--source-root', str(source), '--entry', 'calc:inc', '--out', str(output)]
    if commit is not None:
        argv += ['--source-ref', commit]
    if adapter is not None:
        argv += ['--adapter', adapter]
    return cli.main(argv)


def _portable(source, output, entry):
    load_engine('route_probe').freeze_bundle(source, entry, output)
    path = output/'route_bundle.json'
    pack_bundle(output, path)
    return path


def _write(path, value):
    path.write_text(json.dumps(value) + '\n')
    return path


def _contract():
    return {'schema': 'function-extractor.contract/v1', 'version': 1,
            'expected_status': 'RETURNED', 'result_summary': {'type': 'int'},
            'guards': {'audit': True, 'seccomp': True},
            'phase_events': [{'phase': 'entry', 'event': 'ENTER'}]}


def _matrix(tmp_path, bundle, roles, cases, output='matrix'):
    role_file = _write(tmp_path/('roles-'+output+'.json'), roles)
    scenarios = _write(tmp_path/('cases-'+output+'.json'), {'scenarios': cases})
    return cli.main(['matrix', '--bundle', str(bundle), '--bundle-map', str(role_file),
        '--scenarios', str(scenarios), '--runner', 'subprocess', '--timeout', '10',
        '--out', str(tmp_path/output)])


def test_source_ref_matches_actual_local_git_objects(tiny_repo, tmp_path, capsys):
    repo, source, commit = tiny_repo
    output = tmp_path/'bundle'
    assert _extract(source, output, commit) == 0
    report = json.loads(capsys.readouterr().out)
    pin = json.loads((output/'manifest.json').read_text())['source_pin']
    assert report['status'] == 'FROZEN'
    assert pin['status'] == 'GIT_OBJECTS_VERIFIED' and pin['commit'] == commit
    assert pin['git_files'] == ['calc.py'] and pin['file_hash_only_additions'] == []
    assert pin['loaded_runtime_proof'] is False
    assert _git(repo, 'rev-parse', 'HEAD') == commit
    assert _git(repo, 'status', '--porcelain') == ''


def test_source_ref_rejects_changed_tracked_bytes(tiny_repo, tmp_path, capsys):
    _, source, commit = tiny_repo
    (source/'calc.py').write_text('def inc(value):\n    return value + 999\n')
    output = tmp_path/'changed'
    assert _extract(source, output, commit) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'REFUSED'
    assert not (output/'route_bundle.json').exists()


def test_untracked_adapter_is_explicit_file_hash_only_addition(tiny_repo, tmp_path, capsys):
    _, source, commit = tiny_repo
    (source/'fixture_adapter.py').write_text(
        'def prepare(target, fixture, context):\n'
        '    return {"args": fixture["args"], "kwargs": {}}\n')
    output = tmp_path/'with-adapter'
    assert _extract(source, output, commit, 'fixture_adapter:prepare') == 0
    capsys.readouterr()
    pin = json.loads((output/'manifest.json').read_text())['source_pin']
    assert pin['commit'] == commit and pin['git_files'] == ['calc.py']
    assert pin['file_hash_only_additions'] == ['fixture_adapter.py']
    assert pin['loaded_runtime_proof'] is False


def test_missing_source_ref_never_claims_git_commit(tiny_repo, tmp_path, capsys):
    _, source, _ = tiny_repo
    output = tmp_path/'hash-only'
    assert _extract(source, output) == 0
    capsys.readouterr()
    assert json.loads((output/'manifest.json').read_text())['source_pin'] == {
        'status': 'FILE_HASH_ONLY', 'commit': None}


@pytest.mark.parametrize('fault', ['wrong_hash', 'wrong_entry', 'missing_role'])
def test_bundle_role_refusals_happen_before_execution(tiny_repo, tmp_path, monkeypatch, capsys, fault):
    _, source, _ = tiny_repo
    portable = _portable(source, tmp_path/'role-bundle', 'calc:inc')
    digest = hashlib.sha256(portable.read_bytes()).hexdigest()
    role = {'path': str(portable), 'sha256': '0'*64 if fault=='wrong_hash' else digest}
    roles = {} if fault=='missing_role' else {'one': role}
    case = {'id': 'role', 'entry': 'calc:double' if fault=='wrong_entry' else 'calc:inc',
            'bundle_role': 'one', 'fixture': {'args': [2]}, 'expected': _contract()}
    calls = []
    def no_execute(*args, **kwargs):
        calls.append(True)
        raise AssertionError('role must be qualified before execute')
    monkeypatch.setattr(cli, '_execute', no_execute)
    code = _matrix(tmp_path, portable, roles, [case])
    report = json.loads(capsys.readouterr().out)
    assert calls == []
    assert code == (3 if fault=='missing_role' else 2)
    assert report['status'] == ('UNKNOWN' if fault=='missing_role' else 'REFUSED')


def test_typed_matrix_executes_separately_pinned_pure_entrypoints(tiny_repo, tmp_path, capsys):
    _, source, _ = tiny_repo
    inc = _portable(source, tmp_path/'inc', 'calc:inc')
    double = _portable(source, tmp_path/'double', 'calc:double')
    roles = {name: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
             for name, path in [('first', inc), ('second', double)]}
    cases = [
        {'id': 'plus', 'entry': 'calc:inc', 'bundle_role': 'first',
         'fixture': {'args': [2], 'expected_result': 3}, 'expected': _contract()},
        {'id': 'times', 'entry': 'calc:double', 'bundle_role': 'second',
         'fixture': {'args': [4], 'expected_result': 8}, 'expected': _contract()},
    ]
    assert _matrix(tmp_path, inc, roles, cases) == 0
    capsys.readouterr()
    report = json.loads((tmp_path/'matrix/scenario_results.json').read_text())
    assert report['status'] == 'PASS'
    assert [x['status'] for x in report['cases']] == ['PASS', 'PASS']
    for index, entry in enumerate(['calc:inc', 'calc:double']):
        trace = json.loads((tmp_path/'matrix'/str(index)/'trace.json').read_text())
        assert trace['source_entry'] == entry
        assert trace['result_matches_expected'] is True
        assert trace['target_outcome']['status'] == 'RETURNED'
        assert trace['sandbox']['audit'] is True and trace['sandbox']['seccomp'] is True


def test_matrix_expected_result_mismatch_cannot_be_pass(tiny_repo, tmp_path, capsys):
    _, source, _ = tiny_repo
    portable = _portable(source, tmp_path/'pure', 'calc:inc')
    roles = {'one': {'path': str(portable), 'sha256': hashlib.sha256(portable.read_bytes()).hexdigest()}}
    case = {'id': 'wrong-value', 'entry': 'calc:inc', 'bundle_role': 'one',
            'fixture': {'args': [2], 'expected_result': 999}, 'expected': _contract()}
    code = _matrix(tmp_path, portable, roles, [case])
    capsys.readouterr()
    trace = json.loads((tmp_path/'matrix/0/trace.json').read_text())
    report = json.loads((tmp_path/'matrix/scenario_results.json').read_text())
    assert trace['result_matches_expected'] is False
    assert code != 0 and report['status'] != 'PASS'
    assert report['cases'][0]['status'] == 'FAIL'


def test_role_sensitive_path_refuses_before_execution(tiny_repo, tmp_path, monkeypatch, capsys):
    _, source, _ = tiny_repo
    portable = _portable(source, tmp_path/'pure', 'calc:inc')
    sensitive = tmp_path/'credentials'
    sensitive.mkdir()
    selected = sensitive/'synthetic-bundle.json'
    selected.write_bytes(portable.read_bytes())
    roles = {'one': {'path': str(selected), 'sha256': hashlib.sha256(selected.read_bytes()).hexdigest()}}
    case = {'id': 'sensitive', 'entry': 'calc:inc', 'bundle_role': 'one',
            'fixture': {'args': [2]}, 'expected': _contract()}
    calls = []
    def no_execute(*args, **kwargs):
        calls.append(True)
        raise AssertionError('sensitive path must refuse before execute')
    monkeypatch.setattr(cli, '_execute', no_execute)
    assert _matrix(tmp_path, portable, roles, [case]) == 2
    capsys.readouterr()
    assert calls == []
