"""Affected applicability regressions; pure fixtures, no target or network."""
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.function_extractor import contract_engine as ce
from tools.function_extractor import wire_contract as wc
from tools.function_extractor.tests.test_wire_contract import (
    inputs, compile_plan, observe, packet, admit, FIXTURE, RUNNER,
)

ROOT = Path(__file__).resolve().parents[3]


def test_formatted_after_parsing_length_is_out_of_plain_scope():
    plan = compile_plan()
    assert plan['status'] == 'COMPILED'
    result = observe(plan, value={'chat_id': 123, 'text': '&amp;' * 1000,
                                 'parse_mode': 'HTML'})
    check = result['checks'][0]
    assert check['test_verdict'] == 'UNKNOWN'
    assert check['reason_code'] == 'CONTRACT_SCOPE_UNSUPPORTED'


@pytest.mark.parametrize('field,value', [
    ('parse_mode', 'HTML'), ('parse_mode', None), ('parse_mode', ''),
    ('parse_mode', False), ('entities', []), ('entities', None),
    ('entities', False), ('entities', [{'type': 'bold', 'offset': 0, 'length': 1}]),
])
def test_presence_excludes_before_plain_schema_without_value_leak(field, value):
    plan = compile_plan()
    request = {'chat_id': 123, 'text': 'PRIVATE_SCOPE_SENTINEL', field: value}
    before = copy.deepcopy(request)
    with patch.object(wc.ce, 'validate_schema', side_effect=AssertionError('must not validate')):
        result = observe(plan, value=request)
    assert result['checks'][0]['reason_code'] == 'CONTRACT_SCOPE_UNSUPPORTED'
    assert result['checks'][0]['test_verdict'] == 'UNKNOWN'
    assert request == before
    assert 'PRIVATE_SCOPE_SENTINEL' not in json.dumps(result)
    assert field not in result


@pytest.mark.parametrize('value,verdict', [
    ({'chat_id': 1, 'text': 'x'}, 'PASS'),
    ({'chat_id': 1, 'text': 'x' * 4096}, 'PASS'),
    ({'chat_id': 1, 'text': ''}, 'FAIL'),
    ({'chat_id': 1, 'text': 'x' * 4097}, 'FAIL'),
    ({'chat_id': 1}, 'FAIL'), ({'chat_id': 1, 'text': 123}, 'FAIL'),
    ([], 'FAIL'),
])
def test_plain_schema_preserves_validity_and_bounds(value, verdict):
    assert observe(compile_plan(), value=value)['checks'][0]['test_verdict'] == verdict


@pytest.mark.parametrize('selector', [None, 'plain', True, [], {}])
def test_new_compiler_requires_exact_selector(selector):
    _, _, bindings = inputs()
    if selector is None:
        bindings[0].pop('applicability', None)
    else:
        bindings[0]['applicability'] = selector
    assert compile_plan(bindings=bindings)['status'] == 'REFUSED'


def test_selector_cannot_be_applied_to_output_or_foreign_boundary():
    contract, manifest, bindings = inputs()
    bindings[1]['applicability'] = 'PLAIN_TEXT_ONLY'
    assert compile_plan(bindings=bindings)['status'] == 'REFUSED'
    bindings[1].pop('applicability')
    bindings[0]['extra_selector'] = True
    assert compile_plan(bindings=bindings)['status'] == 'REFUSED'
    bindings[0].pop('extra_selector')
    contract['boundaries'][0]['boundary_id'] = 'other-input'
    contract['rules'][0]['boundary_id'] = 'other-input'
    bindings[0]['boundary_id'] = 'other-input'
    contract['content_digest'] = ce.content_digest(contract)
    assert compile_plan(contract, manifest, bindings)['status'] == 'REFUSED'


def legacy_shape(plan):
    """Synthetic v1 old shape; not a newly authenticated historical receipt."""
    old = copy.deepcopy(plan)
    old['bindings'][0].pop('applicability')
    old['content_digest'] = wc.observation_content_digest(old)
    return old


def test_historical_shape_readable_but_new_evaluation_unqualified():
    plan = compile_plan(); old = legacy_shape(plan)
    assert wc.validate_contract_observation_plan(old, inputs()[1])['status'] == 'VALID'
    new = observe(old)
    assert new['checks'][0]['reason_code'] == 'CONTRACT_SCOPE_UNSUPPORTED'
    # Reconstruct an old-shaped saved schema check, without asserting its origin.
    saved = copy.deepcopy(new)
    saved['checks'][0].update(test_verdict='PASS', reason_code='SCHEMA_MATCH')
    assert admit(packet(old, [saved]), old)['status'] == 'VALID'
    assert plan['content_digest'] != old['content_digest']
    assert plan['selected_rule_digest'] == old['selected_rule_digest']


def test_input_unknown_keeps_response_independent_and_closed_admission():
    plan = compile_plan()
    request = observe(plan, value={'chat_id': 1, 'text': 'x', 'parse_mode': 'HTML'})
    response = observe(plan, 'response', {'ok': True, 'result': {'message_id': 7, 'chat': {}}})
    assert response['checks'][0]['test_verdict'] == 'PASS'  # selected Message subset only
    assert admit(packet(plan, [request, response]), plan)['status'] == 'VALID'
    for verdict in ('PASS', 'FAIL'):
        bad = copy.deepcopy(request); bad['checks'][0]['test_verdict'] = verdict
        assert admit(packet(plan, [bad, response]), plan)['status'] == 'REFUSED'
    bad = copy.deepcopy(response)
    bad['checks'][0].update(test_verdict='UNKNOWN', reason_code='CONTRACT_SCOPE_UNSUPPORTED')
    assert admit(packet(plan, [request, bad]), plan)['status'] == 'REFUSED'
    changed = copy.deepcopy(plan); changed['bindings'][0].pop('applicability')
    assert wc.validate_contract_observation_plan(changed, inputs()[1])['status'] == 'REFUSED'


def test_foreign_objects_never_execute_callbacks_or_text_conversion():
    calls = []
    class Trap:
        def __repr__(self): calls.append('repr'); raise AssertionError()
        def __str__(self): calls.append('str'); raise AssertionError()
        def __eq__(self, other): calls.append('eq'); raise AssertionError()
        def __hash__(self): calls.append('hash'); return hash('parse_mode')
    plan = compile_plan()
    trap = Trap(); request = {trap: 'private'}; calls.clear()
    assert observe(plan, value=request)['checks'][0]['test_verdict'] == 'UNKNOWN'
    # Excluded request does not inspect the text value at all.
    assert observe(plan, value={'text': trap, 'parse_mode': 'HTML'})['checks'][0]['reason_code'] == 'CONTRACT_SCOPE_UNSUPPORTED'
    assert observe(plan, value=trap)['checks'][0]['test_verdict'] == 'UNKNOWN'
    assert calls == []


def test_conflict_and_unspecified_precedence_preserved():
    contract, _, _ = inputs()
    for rule in contract['rules']:
        rule['provenance'] = 'UNSPECIFIED'
    contract['sources'][0]['provenance'] = 'UNSPECIFIED'
    contract['sources'][0]['authority_ref'] = None
    contract['content_digest'] = ce.content_digest(contract)
    assert observe(compile_plan(contract), value={'parse_mode': 'HTML'})['checks'][0]['reason_code'] == 'CONTRACT_UNSPECIFIED'
    contract, _, _ = inputs(); first = contract['rules'][0]
    peer = copy.deepcopy(first); peer['rule_id'] = 'competing'
    peer['constraint']['required'] = []; peer['conflicts'] = [first['rule_id']]
    first['conflicts'] = [peer['rule_id']]; contract['rules'].append(peer)
    contract['content_digest'] = ce.content_digest(contract)
    checks = observe(compile_plan(contract), value={'parse_mode': 'HTML'})['checks']
    assert {row['reason_code'] for row in checks} == {'CONTRACT_CONFLICT'}


def test_formal_binding_plan_observation_packet_and_legacy_shapes(tmp_path):
    plan = compile_plan(); old = legacy_shape(plan)
    request = observe(plan, value={'parse_mode': None})
    response = observe(plan, 'response')
    wrapper = json.loads((ROOT / 'tools/function_extractor/contracts/telegram_sendmessage.observation-bindings.json').read_text())
    docs = [
        ('ce_contract_capture_bindings.schema.json', wrapper, True),
        ('ce_contract_observation_plan.schema.json', plan, True),
        ('ce_contract_observation_plan.schema.json', old, True),
        ('ce_contract_observation.schema.json', request, True),
        ('ce_contract_observations.schema.json', packet(plan, [request, response]), True),
    ]
    bad = copy.deepcopy(wrapper); bad['bindings'][1]['applicability'] = 'PLAIN_TEXT_ONLY'
    docs.append(('ce_contract_capture_bindings.schema.json', bad, False))
    bad = copy.deepcopy(plan); bad['bindings'][0]['applicability'] = True
    docs.append(('ce_contract_observation_plan.schema.json', bad, False))
    # Existing installed formal validator only; no dependencies/network fetched.
    script = '''import json,sys
from pathlib import Path
import jsonschema
root=Path(sys.argv[1])
for filename,document,expected in json.load(sys.stdin):
    schema=json.loads((root/filename).read_text())
    def deny(uri): raise AssertionError('remote schema forbidden')
    resolver=jsonschema.RefResolver.from_schema(schema,handlers={'http':deny,'https':deny})
    valid=not list(jsonschema.Draft202012Validator(schema,resolver=resolver).iter_errors(document))
    assert valid==expected,filename
print('APPLICABILITY_FORMAL_SCHEMAS_VALID')
'''
    result = subprocess.run(['/usr/bin/python3', '-B', '-c', script,
        str(ROOT / 'tools/function_extractor/contracts')], input=json.dumps(docs),
        text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'APPLICABILITY_FORMAL_SCHEMAS_VALID'


@pytest.mark.parametrize('expected', ['PASS', 'FAIL'])
def test_downstream_unknown_not_uplifted_or_positive_cached(expected):
    """Synthetic complete admission trace, never an execution/provider receipt."""
    from tools.function_extractor import evidence_registry as er
    from tools.function_extractor.scenario_engine import generate_scenarios
    from tools.function_extractor.workflow import _case_key, digest
    contract, manifest, bindings = inputs(); plan = compile_plan()
    rule_id = 'telegram.sendMessage.plain.input'
    profile = {'schema': 'function-extractor.scenario-profile/v1', 'version': 1,
        'profile_id': 'scope-unit', 'route_id': 'sample-route', 'entry': 'sample:run',
        'bindings': [{'binding_id': 'formatted', 'variant': 'valid',
            'rule_ids': [row['rule_id'] for row in contract['rules']],
            'fixture': {'args': [], 'kwargs': {}},
            'expected': {'schema': 'function-extractor.contract/v1', 'version': 1,
                         'expected_status': 'RETURNED'},
            'observation_expectations': {rule_id: expected},
            'expected_delivery_state': 'unknown',
            'evidence_scope': 'SYNTHETIC_ADMISSION_NO_EXECUTION'}]}
    scenarios = generate_scenarios(contract, profile, 534, {'max_cases': 4, 'max_input_variants': 0})
    assert scenarios['status'] == 'GENERATED', scenarios
    case = scenarios['cases'][0]
    request = observe(plan, value={'chat_id': 1, 'text': 'x', 'parse_mode': 'HTML'})
    observed = packet(plan, [request, observe(plan, 'response')], fixture_sha256=case['fixture_digest'])
    trace = {'schema': 'route-probe.trace/v1', 'status': 'RETURNED',
        'source_entry': 'sample:run', 'fixture_sha256': case['fixture_digest'],
        'sandbox': {'audit': True, 'seccomp': True},
        'spans': [{'phase': 'call', 'event': 'call', 'evidence': 'REAL_CODE',
                   'file': 'sample.py', 'symbol': 'run', 'line': 1}],
        'trace_recording': {'complete': True, 'recorded_events': 1, 'dropped_events': 0,
                            'selected_modules': []}, 'contract_observations': observed}
    env = {'source_sha256': er.source_digest(contract), 'bundle_sha256': '1' * 64,
           'manifest_source_sha256': '2' * 64, 'runner_sha256': RUNNER,
           'profile_sha256': digest({'observation_plan': plan['content_digest']}), 'runner': 'subprocess'}
    run = {'schema': 'contract-run/v1', 'source_sha256': er.source_digest(contract),
        'contract_sha256': contract['content_digest'], 'fixture_sha256': scenarios['content_digest'],
        'cases': [{'case_id': 'formatted', 'trace': trace, 'environment': env}]}
    validated = er.validate_run(run, contract, scenarios)
    assert validated['status'] == 'VALIDATED', validated
    actual = validated['cases'][0]
    assert actual['test_verdict'] == 'UNKNOWN' and actual['cache_eligible'] is False
    check = next(r for r in actual['rules'] if r['rule_id'] == rule_id)
    assert check['observed_schema_verdict'] == 'UNKNOWN'
    assert check['classification'] == 'CONTRACT_GAP'
    old_env = {**env, 'profile_sha256': digest({'observation_plan': legacy_shape(plan)['content_digest']})}
    assert _case_key(case, env) != _case_key(case, old_env)
