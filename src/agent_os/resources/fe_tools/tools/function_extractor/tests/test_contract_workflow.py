"""Changed contract CLI/orchestration only; no production clients or Docker."""
import copy
import hashlib
import json
from pathlib import Path

from tools.function_extractor import cli
from tools.function_extractor.contract_engine import resolve_contracts, content_digest
from tools.function_extractor.scenario_engine import generate_scenarios
from tools.function_extractor.runner.bundle import pack_bundle
from tools.function_extractor.runner.loader import load_engine
from tools.function_extractor.workflow import contract_matrix, digest, read_json


def inputs(tmp):
    source = tmp / 'source'; source.mkdir()
    (source/'sample.py').write_text('def run(value=1):\n    return value + 1\n')
    frozen=tmp/'frozen'
    load_engine('route_probe').freeze_bundle(source,'sample:run',frozen)
    pack_bundle(frozen,frozen/'route_bundle.json')
    manifest=read_json(frozen/'manifest.json')
    route={'route_id':'sample','entry':'sample:run','graph_sha256':manifest['graph_sha256'],
           'source_pins':sorted([{'path':p['path'],'sha256':p['sha256']} for p in manifest['files']],key=lambda p:p['path'])}
    rules={'schema':'function-extractor.rule-declarations/v1','boundaries':[{'boundary_id':'guards','symbol':'sample.run','kind':'python'}],
           'rules':[{'rule_id':'guard','boundary_id':'guards','kind':'trace_match','constraint':{'schema':'function-extractor.contract/v1','version':1,'guards':{'audit':True,'seccomp':True}}}]}
    path=tmp/'rules.json';path.write_text(json.dumps(rules));sha=hashlib.sha256(path.read_bytes()).hexdigest()
    resolution={'route':route,'sources':[{'source_id':'owner','kind':'rules','path':'rules.json','sha256':sha}],
                'revision':{'id':'test-v1','source_root':str(tmp),'authority_bindings':[{'source_id':'owner','sha256':sha,'provenance':'APPROVED_INTERNAL','authority_ref':'synthetic-fixture-owner'}]}}
    cmap=resolve_contracts(**resolution)
    bindings=[{'binding_id':name,'variant':name,'rule_ids':['guard'],'fixture':{'args':[n],'kwargs':{},'expected_result':n+1},
               'expected':{'schema':'function-extractor.contract/v1','version':1,'expected_status':'RETURNED','guards':{'audit':True,'seccomp':True}},
               'expected_delivery_state':None,'evidence_scope':'SYNTHETIC_TEST'} for n,name in enumerate(('a','b'))]
    profile={'schema':'function-extractor.scenario-profile/v1','version':1,'profile_id':'qa','route_id':'sample','entry':'sample:run','bindings':bindings}
    scenarios=generate_scenarios(cmap,profile,budget={'max_cases':40,'max_input_variants':0})
    return frozen/'route_bundle.json',resolution,cmap,profile,scenarios


def fake_execute(counter):
    def execute(runner,bundle,fixture,timeout):
        counter.append(fixture)
        return {'schema':'route-probe.trace/v1','status':'RETURNED','source_entry':'sample:run','fixture_sha256':digest(fixture),
                'sandbox':{'audit':True,'seccomp':True},'spans':[], 'result_summary':{'type':'int'},'result_matches_expected':True,
                'trace_recording':{'complete':True,'recorded_events':0,'dropped_events':0,'selected_modules':[]}}
    return execute


def run(tmp,bundle,cmap,scenarios,name,counter,registry=None):
    return contract_matrix(contract_map=cmap,scenarios=scenarios,bundle_path=bundle,bundle_roles={},runner='subprocess',timeout=2,
                           output=tmp/name,registry=registry or tmp/'generated',execute=fake_execute(counter))


def test_workflow_first_run_cached_repeat_and_unrelated_contract_change(tmp_path):
    bundle,_,cmap,profile,scenarios=inputs(tmp_path);calls=[]
    first=run(tmp_path,bundle,cmap,scenarios,'first',calls)
    assert first['status']=='PASS' and len(calls)==2
    second=run(tmp_path,bundle,cmap,scenarios,'warm',calls)
    assert second['status']=='PASS' and len(calls)==2 and all(c['cache_hit'] for c in second['cases'])
    altered=copy.deepcopy(cmap)
    altered['boundaries'].append({'boundary_id':'unused','symbol':'sample.other','kind':'python'})
    altered['rules'].append({'rule_id':'unused','boundary_id':'unused','source_id':'owner','kind':'semantic','constraint':{},'provenance':'APPROVED_INTERNAL','conflicts':[]})
    altered['content_digest']=content_digest(altered)
    changed=generate_scenarios(altered,profile,budget={'max_cases':40,'max_input_variants':0})
    third=run(tmp_path,bundle,altered,changed,'unrelated',calls)
    assert third['status']=='PASS' and len(calls)==2


def test_selected_contract_change_invalidates_affected_cache_and_expected_is_not_learned(tmp_path):
    bundle,_,cmap,profile,s=inputs(tmp_path);calls=[];run(tmp_path,bundle,cmap,s,'first',calls)
    # Only b changes its independent expected value; a retains prior evidence.
    profile['bindings'][1]['expected']['result_summary']={'type':'str'}
    changed=generate_scenarios(cmap,profile,budget={'max_cases':40,'max_input_variants':0})
    result=run(tmp_path,bundle,cmap,changed,'changed',calls)
    assert len(calls)==3 and result['status']=='FAIL'
    assert sum(c['cache_hit'] for c in result['cases'])==1
    assert profile['bindings'][1]['expected']['result_summary']=={'type':'str'}


def test_unknown_and_validation_only_do_not_dispatch_or_claim_target_coverage(tmp_path):
    bundle,_,cmap,_,s=inputs(tmp_path);calls=[]
    for row in s['cases']:row['execution_mode']='UNKNOWN'
    s['content_digest']=content_digest(s)
    result=run(tmp_path,bundle,cmap,s,'unknown',calls)
    assert result['status']=='UNKNOWN' and not calls
    assert read_json(tmp_path/'unknown'/'validation.json')['coverage']['variants']['executed']==0


def test_wrong_source_closure_and_wrong_trace_fixture_refuse_before_publication(tmp_path):
    import pytest
    bundle,_,cmap,_,s=inputs(tmp_path);calls=[]
    bad=copy.deepcopy(cmap);bad['route']['source_pins'][0]['sha256']='a'*64;bad['content_digest']=content_digest(bad)
    ss=copy.deepcopy(s);ss['contract_digest']=bad['content_digest'];ss['content_digest']=content_digest(ss)
    with pytest.raises(ValueError):run(tmp_path,bundle,bad,ss,'bad',calls)
    assert calls==[]
    def wrong(*args):
        trace=fake_execute(calls)(*args);trace['fixture_sha256']='b'*64;return trace
    with pytest.raises(ValueError):
        contract_matrix(contract_map=cmap,scenarios=s,bundle_path=bundle,bundle_roles={},runner='subprocess',timeout=2,
                        output=tmp_path/'badtrace',registry=tmp_path/'generated',execute=wrong)
    assert not (tmp_path/'generated'/'index.json').exists()


def test_integration_mode_blocks_before_output_and_cli_contract_chain(tmp_path,capsys):
    bundle,resolution,cmap,profile,s=inputs(tmp_path)
    result=contract_matrix(contract_map=cmap,scenarios=s,bundle_path=bundle,bundle_roles={},runner='subprocess',timeout=2,
                           output=tmp_path/'blocked',registry=tmp_path/'generated',execute=lambda *a:None,mode='allowlisted-integration')
    assert result['status']=='BLOCKED_LIVE_PROOF' and not (tmp_path/'blocked').exists()
    for name,value in [('input',resolution),('profile',profile)]: (tmp_path/(name+'.json')).write_text(json.dumps(value))
    assert cli.main(['contracts','resolve','--inputs',str(tmp_path/'input.json'),'--out',str(tmp_path/'contracts.json')])==0
    assert cli.main(['scenarios','generate','--contracts',str(tmp_path/'contracts.json'),'--profile',str(tmp_path/'profile.json'),'--out',str(tmp_path/'cases.json')])==0
    assert read_json(tmp_path/'cases.json')['cases']
    capsys.readouterr()


def test_whole_budget_is_finite_and_does_not_dispatch_remaining_cases(tmp_path,monkeypatch):
    from tools.function_extractor import workflow
    bundle,_,cmap,_,s=inputs(tmp_path);calls=[];clock=[0.0]
    monkeypatch.setattr(workflow.time,'monotonic',lambda:clock[0])
    def execute(*args):
        trace=fake_execute(calls)(*args);clock[0]+=2;return trace
    result=contract_matrix(contract_map=cmap,scenarios=s,bundle_path=bundle,bundle_roles={},runner='subprocess',timeout=2,
                           output=tmp_path/'bounded',registry=tmp_path/'generated',execute=execute,budget_seconds=1)
    assert len(calls)==1 and result['status']=='UNKNOWN'
    assert sum(c['executed_this_run'] for c in result['cases'])==1


def test_report_rejects_forged_validated_data_and_private_fields():
    from tools.function_extractor.workflow import report_value
    canary='PRIVATE_REPORT_CANARY'
    forged={'status':'VALIDATED','cases':[{'test_verdict':'PASS','resident_body':canary}],'coverage':{}}
    report=report_value(forged)
    assert report['status']=='REFUSED' and canary not in json.dumps(report)


def test_materialization_uses_exact_admitted_bytes_not_a_reopened_source_path(tmp_path,monkeypatch):
    from tools.function_extractor import workflow
    bundle,_,cmap,_,s=inputs(tmp_path);calls=[];original=workflow.materialize_bundle
    before=bundle.read_bytes()
    def switched(path):
        assert Path(path)!=bundle and Path(path).read_bytes()==before
        bundle.write_bytes(b'caller-path-changed-after-admission')
        return original(path)
    monkeypatch.setattr(workflow,'materialize_bundle',switched)
    result=run(tmp_path,bundle,cmap,s,'snapshot',calls)
    assert result['status']=='PASS' and len(calls)==2


def test_secret_bundle_path_is_refused_before_any_payload_read(tmp_path,monkeypatch):
    import pytest
    _,_,cmap,_,s=inputs(tmp_path);reads=[]
    def forbidden(*args):
        reads.append(args[0]);raise AssertionError('payload read was reached')
    monkeypatch.setattr(load_engine('route_probe_replay'),'_read_public',forbidden)
    with pytest.raises(ValueError):
        run(tmp_path,tmp_path/'credentials.json',cmap,s,'secret-path',[])
    assert reads==[]
