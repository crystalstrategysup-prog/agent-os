"""New parent-boundary QA with synthetic trace fixtures, no target/provider run.

REAL_CODE/audit fields below are admission-fixture data, not execution receipts.
Actual original target execution is separately recorded by the guarded runner.
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from tools.function_extractor import api, cli, evidence_registry as er
from tools.function_extractor.contract_engine import content_digest, resolve_contracts
from tools.function_extractor.scenario_engine import generate_scenarios
from tools.function_extractor.runner.bundle import pack_bundle
from tools.function_extractor.runner.loader import load_engine
from tools.function_extractor.wire_contract import (
    compile_contract_observation_plan, evaluate_contract_observation,
    observation_content_digest,
)
from tools.function_extractor.workflow import _case_key, contract_matrix, digest

CANARY = 'PRIVATE_BODY_CANARY_NOT_TO_BE_PERSISTED'


def setup_route(tmp_path, *, negative=False, expected=None, rule_ids=None):
    source = tmp_path / 'source'; source.mkdir()
    (source/'worker.py').write_text('def run(value):\n    return value\n')
    frozen = tmp_path / 'frozen'
    load_engine('route_probe').freeze_bundle(source, 'worker:run', frozen)
    pack_bundle(frozen, frozen/'route_bundle.json')
    manifest = json.loads((frozen/'manifest.json').read_text())
    pins = [{'path':r['path'],'sha256':r['sha256']} for r in manifest['files']]
    rules = {'schema':'function-extractor.rule-declarations/v1',
        'boundaries':[{'boundary_id':d,'symbol':'worker.run','kind':'python'} for d in ('in','out')],
        'rules':[{'rule_id':'input','boundary_id':'in','kind':'input_schema',
                  'constraint':{'type':'object','required':['value'],'properties':{'value':{'type':'string'}}}},
                 {'rule_id':'output','boundary_id':'out','kind':'output_schema',
                  'constraint':{'type':'object','required':['ok'],'properties':{'ok':{'type':'boolean'}}}}]}
    rp=tmp_path/'rules.json';rp.write_text(json.dumps(rules))
    sha=hashlib.sha256(rp.read_bytes()).hexdigest()
    cmap=resolve_contracts({'route_id':'qa-wire','entry':'worker:run','graph_sha256':manifest['graph_sha256'],'source_pins':pins},
        [{'source_id':'unit-rules','kind':'rules','path':rp.name,'sha256':sha}],
        {'id':'synthetic-unit-contract','source_root':str(tmp_path),'authority_bindings':[
            {'source_id':'unit-rules','sha256':sha,'provenance':'APPROVED_INTERNAL','authority_ref':'SYNTHETIC_QA_NOT_PRODUCTION'}]})
    assert cmap['status'] != 'REFUSED', cmap
    bindings=[{'binding_id':'request' if direction=='input' else 'response',
        'boundary_id':'in' if direction=='input' else 'out','direction':direction,
        'phase':'REQUEST' if direction=='input' else 'RESPONSE','file':'worker.py',
        'sha256':pins[0]['sha256'],'symbol':'run','line':1 if direction=='input' else 2}
        for direction in ('input','output')]
    chosen=rule_ids or ['input','output']
    row={'binding_id':'qa-case','variant':'negative' if negative else 'valid','rule_ids':chosen,
        'fixture':{'args':[CANARY],'kwargs':{}},'expected':{'schema':'function-extractor.contract/v1','version':1,'expected_status':'RETURNED'},
        'expected_delivery_state':'unknown','evidence_scope':'SYNTHETIC_ADMISSION_UNIT_FIXTURE_NO_EXECUTION'}
    if expected is not None: row['observation_expectations']=expected
    profile={'schema':'function-extractor.scenario-profile/v1','version':1,'profile_id':'qa-wire',
        'route_id':'qa-wire','entry':'worker:run','bindings':[row]}
    cases=generate_scenarios(cmap,profile,534,{'max_cases':4,'max_input_variants':0})
    assert cases['status']=='GENERATED',cases
    scoped=[b for b in bindings if ('input' if b['direction']=='input' else 'output') in chosen]
    plan=compile_contract_observation_plan(cmap,manifest,rule_ids=chosen,bindings=scoped)
    assert plan['status']=='COMPILED',plan
    fixture_sha=cases['cases'][0]['fixture_digest']
    env={'source_sha256':er.source_digest(cmap),'bundle_sha256':'2'*64,'manifest_source_sha256':'3'*64,
         'runner_sha256':'4'*64,'profile_sha256':'5'*64,'runner':'subprocess'}
    observations=[]
    for binding in scoped:
        val={'value':CANARY} if binding['direction']=='input' else {'ok':CANARY if negative else True,'private':CANARY}
        observation=evaluate_contract_observation(plan,binding_id=binding['binding_id'],value=val,
            phase=binding['phase'],anchor={k:binding[k] for k in ('file','sha256','symbol','line')},invocation_id=1)
        assert observation['status']=='EVALUATED',observation
        observations.append(observation)
    packet={'schema':'function-extractor.contract-observations/v1','version':1,'plan':plan,
        'fixture_sha256':fixture_sha,'runner_sha256':env['runner_sha256'],'observations':observations,
        'complete':True,'dropped_observations':0}
    packet['content_digest']=observation_content_digest(packet)
    trace={'schema':'route-probe.trace/v1','status':'RETURNED','source_entry':'worker:run','fixture_sha256':fixture_sha,
        'sandbox':{'audit':True,'seccomp':True},'result_summary':{'type':'dict','state':'unknown'},
        'spans':[{'phase':'call','event':'call','evidence':'REAL_CODE','file':'worker.py','symbol':'run','line':1}],
        'trace_recording':{'complete':True,'recorded_events':1,'dropped_events':0,'selected_modules':[]},
        'contract_observations':packet}
    run={'schema':'contract-run/v1','source_sha256':er.source_digest(cmap),'contract_sha256':cmap['content_digest'],
         'fixture_sha256':cases['content_digest'],'cases':[{'case_id':'qa-case','trace':trace,'environment':env}]}
    return frozen,manifest,cmap,profile,cases,plan,bindings,run


def validate(data):
    _,_,cmap,_,cases,_,_,run=data
    return er.validate_run(run,cmap,cases)


def test_actual_observation_facts_admitted_and_no_values_in_validation(tmp_path):
    data=setup_route(tmp_path)
    result=validate(data)
    assert result['status']=='VALIDATED',result
    assert result['cases'][0]['test_verdict']=='PASS'
    assert result['cases'][0]['delivery_state']=='unknown'
    assert {r['observed_schema_verdict'] for r in result['cases'][0]['rules']}=={'PASS'}
    assert result['coverage']['boundaries']['observed']==2
    assert CANARY not in json.dumps(result)
    assert CANARY not in json.dumps(data[-1]['cases'][0]['trace']['contract_observations'])
    er._validated(result)


def test_expected_malformed_peer_is_not_application_bug_or_delivery_proof(tmp_path):
    data=setup_route(tmp_path,negative=True,expected={'output':'FAIL'})
    original=copy.deepcopy(data[2])
    result=validate(data);case=result['cases'][0]
    assert case['test_verdict']=='PASS'
    out=next(r for r in case['rules'] if r['rule_id']=='output')
    assert out['observed_schema_verdict']=='FAIL'
    assert out['expected_schema_verdict']=='FAIL'
    assert out['test_verdict']=='PASS' and out['classification']=='EXPECTED_FAILURE'
    assert result['production_acceptance'] is False and data[2]==original
    er._validated(result)


def test_unexpected_bad_response_is_separate_environment_failure(tmp_path):
    result=validate(setup_route(tmp_path,negative=True))
    out=next(r for r in result['cases'][0]['rules'] if r['rule_id']=='output')
    assert (out['observed_schema_verdict'],out['test_verdict'],out['classification'])==('FAIL','FAIL','ENVIRONMENT_DEPENDENT')


def test_missing_or_false_guard_metadata_never_passes_wire_admission(tmp_path):
    data=setup_route(tmp_path)
    for guards in ({'audit':False,'seccomp':True},{'audit':True,'seccomp':False},{}):
        data[-1]['cases'][0]['trace']['sandbox']=guards
        result=validate(data)
        assert result['status']=='VALIDATED',result
        assert result['cases'][0]['test_verdict']=='UNKNOWN'
        assert {r['reason_code'] for r in result['cases'][0]['rules']}=={'wire_guards_unverified'}
        assert result['cases'][0]['cache_eligible'] is False


@pytest.mark.parametrize('negative,expected',[(False,None),(True,None),(True,{'output':'FAIL'})])
def test_incomplete_trace_cannot_pass_or_compare_schema_as_complete(tmp_path,negative,expected):
    data=setup_route(tmp_path,negative=negative,expected=expected)
    data[-1]['cases'][0]['trace']['trace_recording']['complete']=False
    result=validate(data)
    assert result['cases'][0]['test_verdict']=='UNKNOWN'
    assert all(r['test_verdict']=='UNKNOWN' for r in result['cases'][0]['rules'])
    assert not result['cases'][0]['cache_eligible']


def test_legacy_and_fixture_asserted_observations_are_not_wire_proof(tmp_path):
    data=setup_route(tmp_path)
    trace=data[-1]['cases'][0]['trace'];packet=trace.pop('contract_observations')
    trace['result_summary']['ok']=True
    # A scenario fixture can carry arbitrary public JSON; it cannot create the
    # separate runner-owned trace channel, even with a structurally valid packet.
    case=data[4]['cases'][0]
    case['fixture']['claimed_observations']=packet
    case['fixture_digest']=digest(case['fixture']);data[4]['content_digest']=content_digest(data[4])
    data[-1]['fixture_sha256']=data[4]['content_digest'];trace['fixture_sha256']=case['fixture_digest']
    result=validate(data)
    assert result['cases'][0]['test_verdict']=='UNKNOWN'
    assert {r['reason_code'] for r in result['cases'][0]['rules']}=={'wire_value_unobserved'}


@pytest.mark.parametrize('where',['runner','fixture','anchor','source','schema'])
def test_foreign_or_forged_metadata_never_produces_positive_comparison(tmp_path,where):
    data=setup_route(tmp_path);trace=data[-1]['cases'][0]['trace'];packet=trace['contract_observations']
    if where=='runner':packet['runner_sha256']='a'*64
    elif where=='fixture':packet['fixture_sha256']='a'*64
    elif where=='anchor':trace['spans'][0]['symbol']='unrelated'
    elif where=='source':packet['observations'][0]['checks'][0]['source_sha256']='a'*64
    else:packet['observations'][0]['checks'][0]['schema_sha256']='a'*64
    packet['content_digest']=observation_content_digest(packet)
    result=validate(data)
    assert result['status']=='REFUSED' or all(r['test_verdict']!='PASS' for r in result['cases'][0]['rules'])


def test_independent_negative_expectation_changes_both_cache_identities(tmp_path):
    data=setup_route(tmp_path,negative=True)
    first=validate(data);case=data[4]['cases'][0];environment=data[-1]['cases'][0]['environment']
    key_before=_case_key(case,environment)
    case['observation_expectations']={'output':'FAIL'}
    data[4]['content_digest']=content_digest(data[4]);data[-1]['fixture_sha256']=data[4]['content_digest']
    second=validate(data)
    assert first['cases'][0]['test_verdict']=='FAIL' and second['cases'][0]['test_verdict']=='PASS'
    assert first['cases'][0]['cache_key'] != second['cases'][0]['cache_key']
    assert key_before != _case_key(case,environment)


def test_single_direction_and_non_schema_matrix_preflight(tmp_path):
    data=setup_route(tmp_path,rule_ids=['output'])
    frozen,_,cmap,_,cases,_,bindings,_=data;calls=[]
    def execute(runner,bundle,fixture,timeout,**kwargs):
        calls.append(kwargs)
        trace=copy.deepcopy(data[-1]['cases'][0]['trace'])
        trace['contract_observations']['runner_sha256']=kwargs['runner_sha256']
        trace['contract_observations']['plan']=kwargs['contract_plan']
        trace['contract_observations']['content_digest']=observation_content_digest(trace['contract_observations'])
        return trace
    result=contract_matrix(contract_map=cmap,scenarios=cases,bundle_path=frozen/'route_bundle.json',bundle_roles={},runner='subprocess',
        timeout=2,output=tmp_path/'run',registry=tmp_path/'generated',execute=execute,observation_bindings=bindings)
    assert result['status']=='PASS',result
    assert len(calls)==1 and len(calls[0]['contract_plan']['bindings'])==1


def test_bad_plan_preflight_never_dispatches_child(tmp_path):
    data=setup_route(tmp_path);bindings=copy.deepcopy(data[6]);bindings[0]['sha256']='a'*64
    calls=[]
    with pytest.raises(ValueError):
        contract_matrix(contract_map=data[2],scenarios=data[4],bundle_path=data[0]/'route_bundle.json',bundle_roles={},
            runner='subprocess',timeout=2,output=tmp_path/'run',registry=tmp_path/'generated',
            execute=lambda *a,**k:calls.append(1),observation_bindings=bindings)
    assert calls==[]


def test_cli_passes_plan_separately_from_fixture(tmp_path,monkeypatch,capsys):
    data=setup_route(tmp_path);captured=[]
    cmap_path=tmp_path/'map.json';cmap_path.write_text(json.dumps(data[2]))
    bp=tmp_path/'bindings.json';bp.write_text(json.dumps({'schema':'function-extractor.contract-capture-bindings/v1','version':1,'bindings':data[6]}))
    fp=tmp_path/'fixture.json';fp.write_text(json.dumps(data[4]['cases'][0]['fixture']))
    def fake(runner,bundle,fixture,timeout,**kw):
        captured.append((copy.deepcopy(fixture),kw))
        return {'schema':'route-probe.trace/v1','status':'RETURNED','spans':[]}
    monkeypatch.setattr(cli,'_execute',fake)
    code=cli.main(['replay','--bundle',str(data[0]/'route_bundle.json'),'--fixture',str(fp),'--contracts',str(cmap_path),
        '--observation-bindings',str(bp),'--runner','subprocess','--out',str(tmp_path/'cli-run')])
    assert code==0,capsys.readouterr().out
    assert captured[0][1]['contract_plan']['status']=='COMPILED'
    assert 'contract_plan' not in captured[0][0] and 'contract_observations' not in captured[0][0]


def test_closed_expected_fields_cannot_hide_missing_or_unrelated_rules(tmp_path):
    data=setup_route(tmp_path)
    bad=copy.deepcopy(data[3]);bad['bindings'][0]['observation_expectations']={'unrelated':'FAIL'}
    assert generate_scenarios(data[2],bad,534,{'max_cases':4,'max_input_variants':0})['status']=='REFUSED'
    bad['bindings'][0]['observation_expectations']={'output':'UNKNOWN'}
    assert generate_scenarios(data[2],bad,534,{'max_cases':4,'max_input_variants':0})['status']=='REFUSED'


def test_selected_rule_digest_uses_requested_ids_with_lower_rank_conflict_closure(tmp_path):
    data=setup_route(tmp_path)
    cmap=copy.deepcopy(data[2]);source=copy.deepcopy(cmap['sources'][0])
    source.update(source_id='observed',provenance='OBSERVED',sha256='a'*64)
    cmap['sources'].append(source)
    official=next(r for r in cmap['rules'] if r['rule_id']=='output')
    official['conflicts']=['observed-output']
    other=copy.deepcopy(official)
    other.update(rule_id='observed-output',source_id='observed',provenance='OBSERVED',
        constraint={'type':'string'},conflicts=['output'])
    cmap['rules'].append(other);cmap['rules'].sort(key=lambda r:r['rule_id'])
    cmap['content_digest']=content_digest(cmap)
    plan=compile_contract_observation_plan(cmap,data[1],rule_ids=['input','output'],bindings=data[6])
    assert plan['status']=='COMPILED',plan
    assert len(plan['rules'])==3 and plan['rule_ids']==['input','output']
    packet=copy.deepcopy(data[-1]['cases'][0]['trace']['contract_observations'])
    packet['plan']=plan;packet['observations']=[]
    for binding in data[6]:
        packet['observations'].append(evaluate_contract_observation(plan,binding_id=binding['binding_id'],
            value={'value':CANARY} if binding['direction']=='input' else {'ok':True},phase=binding['phase'],
            anchor={k:binding[k] for k in ('file','sha256','symbol','line')},invocation_id=1))
    packet['content_digest']=observation_content_digest(packet)
    trace=copy.deepcopy(data[-1]['cases'][0]['trace']);trace['contract_observations']=packet
    api._trace(trace)
    assert er._wire_verdict(official,trace,cmap,data[-1]['cases'][0]['environment'])==('PASS','wire_schema_valid')


def test_new_optional_artifacts_formally_validate_without_remote_schema_loading(tmp_path):
    import subprocess
    data=setup_route(tmp_path,negative=True,expected={'output':'FAIL'})
    folder=Path(__file__).resolve().parents[1]/'contracts'
    # Use the already installed validator; all external resolution is denied.
    names=['trace.schema.json','json-value.schema.json','ce_contract_observations.schema.json',
           'ce_profile.schema.json','ce_scenarios.schema.json','ce_evidence_validation.schema.json','ce_run.schema.json']
    schemas={n:json.loads((folder/n).read_text()) for n in names}
    valid=[['trace.schema.json',data[-1]['cases'][0]['trace']],['ce_profile.schema.json',data[3]],
           ['ce_scenarios.schema.json',data[4]],['ce_evidence_validation.schema.json',validate(data)],['ce_run.schema.json',data[-1]]]
    invalid=[]
    bad=copy.deepcopy(valid[0][1]);bad['contract_observations']['raw_body']=CANARY
    invalid.append(['trace.schema.json',bad])
    bad=copy.deepcopy(data[3]);bad['bindings'][0]['observation_expectations']['output']='UNKNOWN'
    invalid.append(['ce_profile.schema.json',bad])
    script='''import json,sys
from jsonschema import Draft202012Validator,RefResolver
v=json.load(sys.stdin)
def deny(uri):raise LookupError('unregistered_schema')
base='https://function-extractor.invalid/contracts/v1/'
store={}
for name,schema in v['schemas'].items():
 Draft202012Validator.check_schema(schema)
 store[base+name]=schema
 if '$id' in schema:store[schema['$id']]=schema
def validator(name):
 schema=v['schemas'][name]
 resolver=RefResolver(base_uri=schema.get('$id',base+name),referrer=schema,store=store,handlers={'http':deny,'https':deny,'file':deny})
 return Draft202012Validator(schema,resolver=resolver)
for name,value in v['valid']:validator(name).validate(value)
for name,value in v['invalid']:
 if validator(name).is_valid(value):raise SystemExit(2)
print(json.dumps({'schemas':len(v['schemas']),'valid':len(v['valid']),'negative':len(v['invalid'])}))
'''
    result=subprocess.run(['/usr/bin/python3','-I','-c',script],input=json.dumps({'schemas':schemas,'valid':valid,'invalid':invalid}),
        capture_output=True,text=True,timeout=20)
    assert result.returncode==0,{'category':'FORMAL_OBSERVATION_SCHEMA_FAILURE','exit':result.returncode}
    assert json.loads(result.stdout)=={'schemas':7,'valid':5,'negative':2}
