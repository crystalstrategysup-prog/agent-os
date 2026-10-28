"""Update scope regressions; synthetic hashes, no installer or live effects."""
import copy
import json
import os
import subprocess
import sys

import pytest

from agent_os.investigation import verification_plan
from agent_os.safeio import GateError


def request():
    kinds = ['artifact-integrity', 'compatibility', 'post-install-smoke',
             'regression', 'installer-rehearsal', 'regression']
    return {'checks': [dict(id=f'check-{i}', kind=kind,
                           dependency_pins={'code': 'a' * 64, 'tests-and-contract': 'b' * 64},
                           environment_pins={'runtime': 'c' * 64}, coverage='COMPLETE')
                       for i, kind in enumerate(kinds)], 'evidence': []}


def qualified():
    value = request()
    plan = verification_plan(value)
    value['evidence'] = [dict(check_id=row['id'], input_key=row['input_key'],
                              outcome='PASS', receipt_ref='retained/check.json',
                              receipt_sha256='d' * 64) for row in plan['checks']]
    return value


def test_unchanged_update_reuses_offline_checks_but_rechecks_current_target():
    value = qualified()
    before = copy.deepcopy(value)
    plan = verification_plan(value)
    assert [row['action'] for row in plan['checks']] == ['RUN'] * 3 + ['REUSE'] * 3
    assert plan['execution_authorized'] is False
    assert value == before


@pytest.mark.parametrize('field', ['dependency_pins', 'environment_pins'])
def test_changed_code_test_contract_or_runtime_invalidates_only_affected_check(field):
    value = qualified()
    value['checks'][3][field]['changed-dependency'] = 'e' * 64
    actions = [row['action'] for row in verification_plan(value)['checks']]
    assert actions == ['RUN'] * 4 + ['REUSE'] * 2


@pytest.mark.parametrize('coverage', ['PARTIAL', 'UNKNOWN'])
def test_incomplete_dependency_scope_is_never_reused(coverage):
    value = qualified()
    value['checks'][3]['coverage'] = coverage
    assert verification_plan(value)['checks'][3]['action'] == 'RUN'


@pytest.mark.parametrize('outcome', ['FAIL', 'UNKNOWN', 'BLOCKED'])
def test_latest_bad_evidence_overrides_old_pass(outcome):
    value = qualified()
    newer = dict(value['evidence'][3], outcome=outcome)
    value['evidence'].append(newer)
    assert verification_plan(value)['checks'][3]['action'] == 'RUN'


def test_missing_or_empty_pins_and_missing_receipt_cannot_reuse():
    for field in ['dependency_pins', 'environment_pins']:
        value = qualified()
        value['checks'][3][field] = {}
        assert verification_plan(value)['checks'][3]['action'] == 'RUN'
    value = qualified()
    value['evidence'] = []
    assert all(row['action'] == 'RUN' for row in verification_plan(value)['checks'])
    value = qualified()
    del value['evidence'][3]['receipt_sha256']
    with pytest.raises(GateError):
        verification_plan(value)


@pytest.mark.parametrize('mutation', ['duplicate', 'missing-fresh', 'effect', 'extra', 'bad-hash', 'oversize'])
def test_invalid_or_effectful_plans_are_refused(mutation):
    value = request()
    if mutation == 'duplicate': value['checks'][1]['id'] = 'check-0'
    elif mutation == 'missing-fresh': value['checks'].pop(0)
    elif mutation == 'effect': value['checks'][3]['kind'] = 'external-send'
    elif mutation == 'extra': value['checks'][3]['skip_safety'] = True
    elif mutation == 'bad-hash': value['checks'][3]['dependency_pins']['code'] = 'main'
    elif mutation == 'oversize': value['checks'] *= 20
    with pytest.raises(GateError): verification_plan(value)


def test_module_entry_calls_the_same_planner_without_writes(tmp_path):
    value = qualified()
    document = tmp_path / 'plan.json'
    document.write_text(json.dumps(value))
    before = list(tmp_path.iterdir())
    result = subprocess.run([sys.executable, '-B', '-m', 'agent_os.investigation',
                             '--update-plan', str(document)], env=os.environ,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == verification_plan(value)
    assert list(tmp_path.iterdir()) == before


@pytest.mark.parametrize('body', ['{"private-canary":',
                                 '{"checks":[],"checks":[],"evidence":[]}',
                                 '[]'])
def test_module_entry_refuses_bad_json_without_echoing_input(tmp_path, body):
    document = tmp_path / 'bad.json'
    document.write_text(body)
    result = subprocess.run([sys.executable, '-B', '-m', 'agent_os.investigation',
                             '--update-plan', str(document)], env=os.environ,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {'status': 'BLOCKED',
                                       'error': 'invalid_update_verification_plan'}
    assert result.stderr == ''
    assert 'private-canary' not in result.stdout
