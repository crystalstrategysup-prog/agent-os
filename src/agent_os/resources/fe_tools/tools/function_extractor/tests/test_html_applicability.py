"""Selected emitted HTML contract, not full Telegram parsing or delivery proof."""
import copy
import json
from pathlib import Path
import subprocess

import pytest

from tools.function_extractor import contract_engine as ce, wire_contract as wc
from tools.function_extractor.tests.test_wire_contract import inputs, observe, packet, admit

CONTRACTS = Path(__file__).resolve().parents[1] / 'contracts'


def html_plan():
    contract, manifest, bindings = inputs()
    rules = json.loads((CONTRACTS / 'telegram_sendmessage_html.rules.json').read_text())
    contract['boundaries'] = rules['boundaries']
    contract['rules'][0].update(rules['rules'][0])
    contract['content_digest'] = ce.content_digest(contract)
    bindings[0].update(boundary_id='telegram.sendMessage.html.bold', applicability='HTML_BOLD_TEXT_V1')
    return wc.compile_contract_observation_plan(contract, manifest,
        rule_ids=[r['rule_id'] for r in contract['rules']], bindings=bindings)


@pytest.mark.parametrize('text,verdict', [
    ('Synthetic route probe', 'PASS'),
    ('<b>От:</b> label\n<b>Кому:</b> recipient\n\n&lt;&gt;&amp;&quot;&#x27;', 'PASS'),
    ('<b>' + '&amp;' * 4096 + '</b>', 'PASS'),
    ('&#128512;' * 4096, 'PASS'),
    ('<b>' + '&amp;' * 4097 + '</b>', 'FAIL'),
    ('<b></b>', 'FAIL'), ('', 'FAIL'),
    ('<b>x', 'FAIL'), ('x</b>', 'FAIL'), ('x & y', 'FAIL'),
    ('<i>valid but outside selected contract</i>', 'UNKNOWN'),
    ('<b class="x">x</b>', 'UNKNOWN'),
    ('<b><b>x</b></b>', 'UNKNOWN'),
    ('&apos;', 'UNKNOWN'), ('&#0;', 'UNKNOWN'), ('&#xD800;', 'UNKNOWN'),
    ('&#999999999999999999999999;', 'UNKNOWN'),
    ('<!--x-->text', 'UNKNOWN'), ('<b/>text', 'UNKNOWN'),
])
def test_selected_html_after_parsing(text, verdict):
    plan = html_plan()
    assert plan['status'] == 'COMPILED', plan
    value = {'chat_id': 123, 'text': text, 'parse_mode': 'HTML'}
    before = copy.deepcopy(value)
    result = observe(plan, value=value)
    assert result['checks'][0]['test_verdict'] == verdict
    assert value == before
    assert 'recipient' not in json.dumps(result)
    response = observe(plan, 'response')
    assert response['checks'][0]['test_verdict'] == 'PASS'
    assert admit(packet(plan, [result, response]), plan)['status'] == 'VALID'


@pytest.mark.parametrize('changes', [{'parse_mode': 'MarkdownV2'}, {'parse_mode': None},
    {'entities': []}, {'text': 'x' * 524289}])
def test_unsupported_and_bounded_remain_unknown(changes):
    result = observe(html_plan(), value={'chat_id': 1, 'text': 'x', 'parse_mode': 'HTML', **changes})
    assert result['checks'][0]['test_verdict'] == 'UNKNOWN'


def test_new_html_compilation_requires_exact_applicability():
    plan = html_plan()
    contract, manifest, bindings = inputs()
    rules = json.loads((CONTRACTS / 'telegram_sendmessage_html.rules.json').read_text())
    contract['boundaries'] = rules['boundaries']
    contract['rules'][0].update(rules['rules'][0])
    contract['content_digest'] = ce.content_digest(contract)
    bindings[0]['boundary_id'] = 'telegram.sendMessage.html.bold'
    for selector in (None, 'PLAIN_TEXT_ONLY', 'HTML', True):
        bindings[0].pop('applicability', None)
        if selector is not None:
            bindings[0]['applicability'] = selector
        assert wc.compile_contract_observation_plan(contract, manifest,
            rule_ids=[r['rule_id'] for r in contract['rules']], bindings=bindings)['status'] == 'REFUSED'
    assert plan['content_digest'] != inputs()[0]['content_digest']


def test_html_never_evaluates_foreign_callbacks():
    calls = []
    class Foreign:
        def __str__(self): calls.append('str'); raise AssertionError()
        def __repr__(self): calls.append('repr'); raise AssertionError()
        def __eq__(self, other): calls.append('eq'); raise AssertionError()
    result = observe(html_plan(), value={'chat_id':1,'parse_mode':'HTML','text':Foreign()})
    assert result['checks'][0]['test_verdict'] == 'UNKNOWN' and not calls


def test_html_formal_plan_and_bindings_match_selected_profile():
    plan = html_plan()
    wrapper = json.loads((CONTRACTS/'telegram_sendmessage_html.observation-bindings.json').read_text())
    script = '''import json,sys
from pathlib import Path
import jsonschema
folder=Path(sys.argv[1])
for name,value in json.load(sys.stdin):
 schema=json.loads((folder/name).read_text())
 def deny(uri): raise AssertionError('remote schema forbidden')
 resolver=jsonschema.RefResolver.from_schema(schema,handlers={'http':deny,'https':deny})
 jsonschema.Draft202012Validator(schema,resolver=resolver).validate(value)
'''
    result = subprocess.run(['/usr/bin/python3','-B','-c',script,str(CONTRACTS)],
        input=json.dumps([['ce_contract_capture_bindings.schema.json',wrapper],
                          ['ce_contract_observation_plan.schema.json',plan]]),
        text=True,capture_output=True,timeout=15)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('formatted_boundary', ['telegram.sendMessage.html.bold', 'telegram.sendMessage.plain'])
def test_schema_only_mutations_cannot_bypass_after_parsing_scope(formatted_boundary):
    from tools.function_extractor.scenario_engine import generate_scenarios
    contract, _, _ = inputs()
    if formatted_boundary.endswith('.bold'):
        rules = json.loads((CONTRACTS/'telegram_sendmessage_html.rules.json').read_text())
        contract['boundaries'] = rules['boundaries']
        contract['rules'][0].update(rules['rules'][0])
    contract['content_digest'] = ce.content_digest(contract)
    profile = {'schema':'function-extractor.scenario-profile/v1','version':1,
        'profile_id':'raw-scope-negative','route_id':'sample-route','entry':'sample:run',
        'input_seed':{'chat_id':1,'text':'&amp;'*1000,'parse_mode':'HTML'},
        'bindings':[{'binding_id':'route','variant':'valid','rule_ids':[r['rule_id'] for r in contract['rules']],
            'fixture':{'args':[],'kwargs':{}},'expected':{'schema':'function-extractor.contract/v1',
                'version':1,'expected_status':'RETURNED'},'expected_delivery_state':'unknown',
            'evidence_scope':'SYNTHETIC_GENERATOR_NO_EXECUTION'}]}
    result = generate_scenarios(contract,profile,534,{'max_cases':40,'max_input_variants':16})
    assert result['status'] == 'PARTIAL', result
    shaped = [r for r in result['cases'] if r['binding_id'] is None and
              (formatted_boundary.endswith('.bold') or
               (type(r['fixture']['input']) is dict and 'parse_mode' in r['fixture']['input']))]
    assert shaped
    for row in shaped:
        assert row['execution_mode'] == 'UNKNOWN'
        assert row['expected_schema_status'] == 'UNSPECIFIED'
        assert row['validation_result']['status'] == 'UNKNOWN'
