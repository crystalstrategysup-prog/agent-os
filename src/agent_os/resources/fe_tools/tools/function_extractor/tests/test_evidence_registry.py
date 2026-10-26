"""New Contract Engine observational evidence QA. No replay/DB/provider/control."""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from tools.function_extractor import evidence_registry as er
from tools.function_extractor.contract_engine import resolve_contracts, selected_rule_digest

PRIVATE='RESIDENT_PRIVATE_CANARY https://example.invalid/token SECRET_TOKEN'


def trace(state='unknown', status='RETURNED', complete=True, attempts=1):
    return {'schema':'route-probe.trace/v1','status':status,'source_entry':'worker:run','correlation_id':'a'*32,
            'fixture_sha256':er._digest({'args':[PRIVATE],'kwargs':{}}),
            'sandbox':{'audit':True,'seccomp':True},'result_summary':{'type':'str','state':state},
            'spans':[{'phase':'call','event':'return','symbol':'worker.run','file':'worker.py','line':13,
                      'evidence':'REAL_CODE','attempts':attempts}],
            'trace_recording':{'complete':complete,'recorded_events':1,'dropped_events':0,'selected_modules':[]}}


def environment():
    return {'source_sha256':'1'*64,'bundle_sha256':'2'*64,'manifest_source_sha256':'3'*64,'runner_sha256':'4'*64,'profile_sha256':'5'*64,'runner':'subprocess'}


def inputs(tmp_path, declarations=None):
    declarations=declarations or [('norm','APPROVED_INTERNAL','delivery_state',{'state':'unknown'})]
    sources=[];bindings=[]
    for name,level,kind,constraint in declarations:
        payload={'schema':'function-extractor.rule-declarations/v1',
                 'boundaries':[{'boundary_id':'send','symbol':'worker.run','kind':'python'}],
                 'rules':[{'boundary_id':'send','kind':kind,'constraint':constraint}]}
        path=tmp_path/(name+'.json');path.write_text(json.dumps(payload))
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        metadata={'retrieved_at':'2026-10-22T00:00:00Z','version':'snapshot-v1',
                  'primary_ref':'https://example.invalid/official','primary_sha256':'b'*64,
                  'official_schema':False,'machine_adapter':True}
        sources.append({'source_id':name,'kind':'rules','path':path.name,'sha256':sha,'metadata':metadata})
        if level!='UNSPECIFIED':bindings.append({'source_id':name,'sha256':sha,'provenance':level,'authority_ref':'reviewed-qa-snapshot'})
    route={'route_id':'qa-route','entry':'worker:run','graph_sha256':'c'*64,
           'source_pins':[{'path':'worker.py','sha256':'d'*64}]}
    cmap=resolve_contracts(route,sources,{'id':'qa-revision','source_root':str(tmp_path),'authority_bindings':bindings})
    assert cmap['status']!='REFUSED',cmap
    rows=[]
    for i,rule in enumerate(cmap['rules']):
        fixture={'args':[PRIVATE],'kwargs':{}}
        rows.append({'id':f'case-{i}','entry':'worker:run','binding_id':'qa-binding','variant':'fault',
                     'rule_ids':[rule['rule_id']],'provenance':[], 'execution_mode':'REPLAY','fixture':fixture,
                     'fixture_digest':er._digest(fixture),'expected':{'schema':'function-extractor.contract/v1','version':1,'expected_status':'RETURNED'},
                     'expected_delivery_state':'unknown','evidence_scope':'SIMULATED',
                     'source_pins':route['source_pins'],'selected_rule_digest':selected_rule_digest(cmap,[rule['rule_id']])})
    scenarios={'schema':'function-extractor.generated-scenarios/v1','version':1,'route_id':'qa-route',
               'contract_digest':cmap['content_digest'],'profile_digest':'e'*64,'seed':7,'budget':{},'cases':rows,'coverage':{}}
    scenarios['content_digest']=er._content(scenarios)
    run={'schema':'contract-run/v1','source_sha256':er.source_digest(cmap),'contract_sha256':cmap['content_digest'],
         'fixture_sha256':scenarios['content_digest'],'cases':[{'case_id':c['id'],'trace':trace(),'environment':environment()} for c in rows]}
    return run,cmap,scenarios


def test_expected_unknown_is_pass_not_delivery_success_and_redacted(tmp_path):
    run,cmap,scenarios=inputs(tmp_path);before=copy.deepcopy((cmap,scenarios))
    result=er.validate_run(run,cmap,scenarios)
    assert result['status']=='VALIDATED'
    case=result['cases'][0]
    assert (case['delivery_state'],case['test_verdict'],case['diagnostic_status'])==('unknown','PASS','CONFORMANT')
    assert case['rules'][0]['classification']=='EXPECTED_FAILURE'
    assert case['rules'][0]['trace_anchors']==[{'file':'worker.py','symbol':'worker.run','line':13}]
    assert result['coverage']['branches']['denominator_known'] is False
    assert PRIVATE not in json.dumps(result) and (cmap,scenarios)==before


def test_normative_failure_and_observed_drift_never_learn_expected(tmp_path):
    run,cmap,s=inputs(tmp_path,[('official','OFFICIAL','delivery_state',{'state':'unknown'}),('observed','OBSERVED','delivery_state',{'state':'sent'})])
    original=copy.deepcopy(cmap)
    out=er.validate_run(run,cmap,s)
    assert out['cases'][0]['test_verdict']=='PASS'
    assert out['cases'][1]['rules'][0]['classification']=='DOCUMENTATION_DRIFT'
    assert out['cases'][1]['test_verdict']=='UNKNOWN'
    run['cases'][0]['trace']=trace('sent')
    out=er.validate_run(run,cmap,s)
    assert out['cases'][0]['rules'][0]['classification']=='CODE_BUG'
    assert cmap==original


def test_missing_wire_values_and_unsupported_semantics_are_gaps(tmp_path):
    run,cmap,s=inputs(tmp_path,[('shape','APPROVED_INTERNAL','output_schema',{'type':'string'}),('meaning','APPROVED_INTERNAL','semantic',{'require':'secret'})])
    out=er.validate_run(run,cmap,s)
    assert all(c['test_verdict']=='UNKNOWN' for c in out['cases'])
    assert all(c['rules'][0]['classification']=='CONTRACT_GAP' for c in out['cases'])
    # Summary is not the wire string: no false string-vs-object CODE_BUG.
    rule_kinds={r['rule_id']:r['kind'] for r in cmap['rules']}
    shape=next(c for c in out['cases'] if rule_kinds[c['rules'][0]['rule_id']]=='output_schema')
    assert shape['rules'][0]['reason_code']=='wire_value_unobserved'


def test_equal_rank_conflict_and_incomplete_recording_remain_unknown(tmp_path):
    run,cmap,s=inputs(tmp_path,[('left','APPROVED_INTERNAL','delivery_state',{'state':'unknown'}),('right','APPROVED_INTERNAL','delivery_state',{'state':'sent'})])
    out=er.validate_run(run,cmap,s)
    assert all(c['test_verdict']=='UNKNOWN' for c in out['cases'])
    assert all(c['rules'][0]['classification']=='CONTRACT_GAP' for c in out['cases'])
    p=tmp_path/'single';p.mkdir();run,cmap,s=inputs(p)
    run['cases'][0]['trace']=trace(complete=False)
    assert er.validate_run(run,cmap,s)['cases'][0]['test_verdict']=='UNKNOWN'


def test_no_retry_derived_from_actual_observation_and_environment_failure(tmp_path):
    run,cmap,s=inputs(tmp_path,[('retry','APPROVED_INTERNAL','no_retry',{'max_attempts':1})])
    run['cases'][0]['trace']=trace(attempts=2)
    out=er.validate_run(run,cmap,s)
    assert out['cases'][0]['rules'][0]['classification']=='CODE_BUG'
    run['cases'][0]['trace']=trace('failed',status='DENIED',attempts=2)
    assert er.validate_run(run,cmap,s)['cases'][0]['rules'][0]['classification']=='ENVIRONMENT_DEPENDENT'


def test_all_three_tampers_and_closed_environment_refused(tmp_path):
    run,cmap,s=inputs(tmp_path)
    for target in ('run','map','scenarios','trace','environment'):
        r,m,ss=copy.deepcopy((run,cmap,s))
        if target=='run':r['source_sha256']='f'*64
        elif target=='map':m['rules'][0]['constraint']['state']='sent'
        elif target=='scenarios':ss['cases'][0]['fixture']['args']=[PRIVATE+'tampered']
        elif target=='trace':r['cases'][0]['trace']['provider_body']=PRIVATE
        else:r['cases'][0]['environment']={'token':PRIVATE}
        assert er.validate_run(r,m,ss)['status']=='REFUSED'


def test_atomic_idempotent_schema_checked_passport_and_readonly_lookup(tmp_path):
    run,cmap,s=inputs(tmp_path);out=er.validate_run(run,cmap,s);root=tmp_path/'generated'
    first=er.sync_docs(out,root);assert first['status']=='WRITTEN'
    before={p.name:p.read_bytes() for p in root.iterdir()}
    assert er.sync_docs(out,root)['status']=='UNCHANGED'
    assert before=={p.name:p.read_bytes() for p in root.iterdir()}
    hit=er.load_registry(root,out['source_sha256'],out['contract_sha256'],out['fixture_sha256'])
    assert hit['status']=='HIT' and hit['record']['passport']['status']=='OBSERVED'
    assert er.load_case_registry(root,out['cases'][0]['cache_key'])['status']=='HIT'
    assert PRIVATE not in ''.join(p.read_text() for p in root.iterdir())
    # Lookup on an absent root does not create any lock, directory or files.
    absent=tmp_path/'absent'/'generated'
    assert er.load_registry(absent,'a'*64,'b'*64,'c'*64)['status']=='MISS' and not absent.exists()


def test_tampered_record_and_schema_reexport_refused(tmp_path):
    run,cmap,s=inputs(tmp_path);out=er.validate_run(run,cmap,s);root=tmp_path/'generated'
    receipt=er.sync_docs(out,root);assert receipt['status']=='WRITTEN'
    file=root/(receipt['key']+'.json');record=json.loads(file.read_text());record['passport']['credential']=PRIVATE;file.write_text(json.dumps(record))
    assert er.load_registry(root,out['source_sha256'],out['contract_sha256'],out['fixture_sha256'])['status']=='REFUSED'
    forged=copy.deepcopy(out);forged['cases'][0]['resident_text']=PRIVATE;forged['content_digest']=er._content(forged)
    assert er.sync_docs(forged,tmp_path/'other'/'generated')['status']=='REFUSED'


def test_path_symlink_hardlink_and_canonical_refused(tmp_path):
    run,cmap,s=inputs(tmp_path);out=er.validate_run(run,cmap,s)
    canonical=tmp_path/'canonical'/'generated'
    assert er.sync_docs(out,canonical)['status']=='REFUSED' and not canonical.exists()
    outside=tmp_path/'outside';outside.mkdir();link=tmp_path/'linked';link.symlink_to(outside,target_is_directory=True)
    assert er.sync_docs(out,link/'generated')['status']=='REFUSED' and not (outside/'generated').exists()
    root=tmp_path/'generated';root.mkdir();target=tmp_path/'do-not-touch';target.write_text('canary')
    (root/'.sync.lock').hardlink_to(target)
    assert er.sync_docs(out,root)['status']=='REFUSED' and target.read_text()=='canary'


def test_concurrent_same_input_has_one_atomic_document_and_no_lost_records(tmp_path):
    run,cmap,s=inputs(tmp_path);out=er.validate_run(run,cmap,s);root=tmp_path/'generated'
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(lambda _:er.sync_docs(out,root),range(12)))
    assert sum(r['status']=='WRITTEN' for r in results)==1
    assert all(r['status'] in {'WRITTEN','UNCHANGED','REFUSED'} for r in results)  # Busy is now fail-closed without waiting.
    assert er.load_registry(root,out['source_sha256'],out['contract_sha256'],out['fixture_sha256'])['status']=='HIT'
    assert len(list(root.glob('*.json')))==2


def test_case_keys_ignore_unrelated_rules_but_bind_fixture_source_and_adapter(tmp_path):
    run,cmap,s=inputs(tmp_path);first=er.validate_run(run,cmap,s);key=first['cases'][0]['cache_key']
    root=tmp_path/'generated';assert er.sync_docs(first,root)['status']=='WRITTEN'
    r,m,ss=copy.deepcopy((run,cmap,s));r['cases'][0]['environment']={'bundle_sha256':'f'*64,'runner':'container'}
    assert er.validate_run(r,m,ss)['cases'][0]['cache_key']!=key
    r,m,ss=copy.deepcopy((run,cmap,s));ss['cases'][0]['fixture']['args']=[];ss['cases'][0]['fixture_digest']=er._digest(ss['cases'][0]['fixture']);ss['content_digest']=er._content(ss);r['fixture_sha256']=ss['content_digest'];r['cases'][0]['trace']['fixture_sha256']=ss['cases'][0]['fixture_digest']
    assert er.validate_run(r,m,ss)['cases'][0]['cache_key']!=key
    # Whole map identity differs, but a new unrelated boundary/rule does not stale this selected case.
    extra={'boundary_id':'other','kind':'semantic','constraint':{},'source_id':m['sources'][0]['source_id'],'provenance':'APPROVED_INTERNAL'}
    extra['rule_id']='rule:'+er._digest(extra)[:24];extra['conflicts']=[]
    m['boundaries'].append({'boundary_id':'other','symbol':'other.run','kind':'python'});m['rules'].append(extra);m['content_digest']=er._content(m)
    ss['contract_digest']=m['content_digest'];ss['content_digest']=er._content(ss);r['contract_sha256']=m['content_digest'];r['fixture_sha256']=ss['content_digest']
    # Restore unchanged fixture identity to isolate unrelated-rule effect.
    ss['cases'][0]=copy.deepcopy(s['cases'][0]);r['cases'][0]['trace']['fixture_sha256']=s['cases'][0]['fixture_digest'];ss['content_digest']=er._content(ss);r['fixture_sha256']=ss['content_digest']
    assert er.validate_run(r,m,ss)['cases'][0]['cache_key']==key
    assert er.load_case_registry(root,key)['status']=='HIT'


def test_multi_trace_batch_keeps_individual_trace_budget_and_branch_denominator(tmp_path):
    run,cmap,s=inputs(tmp_path);t=run['cases'][0]['trace'];t['spans']*=1600
    t['trace_recording']['recorded_events']=1600
    # More than2MB overall with each admitted trace well below2MB.
    base=s['cases'][0]
    s['cases']=[{**copy.deepcopy(base),'id':f'case-{i}'} for i in range(12)]
    s['content_digest']=er._content(s);run['fixture_sha256']=s['content_digest']
    run['cases']=[{'case_id':c['id'],'trace':copy.deepcopy(t)} for c in s['cases']]
    assert len(er._canonical(run))>2_000_000
    run.update(branch_inventory=['positive','negative'],branch_observations=['negative'])
    out=er.validate_run(run,cmap,s)
    assert out['status']=='VALIDATED' and out['coverage']['branches']=={'total':2,'observed':1,'denominator_known':True}
    run['branch_observations']=['not-in-inventory']
    assert er.validate_run(run,cmap,s)['status']=='REFUSED'


def test_phase_event_counter_distinguishes_unknown_from_witnessed_retry(tmp_path):
    run,cmap,s=inputs(tmp_path,[('counter','APPROVED_INTERNAL','no_retry',{'phase':'real_http_request','event':'written','max_count':1})])
    out=er.validate_run(run,cmap,s)
    assert out['cases'][0]['test_verdict']=='UNKNOWN'
    span={'phase':'real_http_request','event':'written','count':1,'evidence':'SIMULATED'}
    run['cases'][0]['trace']['spans']=[span]
    run['cases'][0]['trace']['trace_recording']['recorded_events']=1
    assert er.validate_run(run,cmap,s)['cases'][0]['test_verdict']=='PASS'
    run['cases'][0]['trace']['spans'].append(copy.deepcopy(span))
    run['cases'][0]['trace']['trace_recording']['recorded_events']=2
    assert er.validate_run(run,cmap,s)['cases'][0]['test_verdict']=='FAIL'


def test_fifo_record_and_readonly_generated_root_refuse_without_blocking(tmp_path):
    import os,time
    run,cmap,s=inputs(tmp_path);out=er.validate_run(run,cmap,s);root=tmp_path/'generated'
    receipt=er.sync_docs(out,root);assert receipt['status']=='WRITTEN'
    record=root/(receipt['key']+'.json');record.unlink();os.mkfifo(record)
    start=time.monotonic()
    assert er.load_registry(root,out['source_sha256'],out['contract_sha256'],out['fixture_sha256'])['status']=='REFUSED'
    assert time.monotonic()-start<1
    other=tmp_path/'readonly'/'generated';other.mkdir(parents=True);other.chmod(0o500)
    try:assert er.sync_docs(out,other)['status']=='REFUSED' and list(other.iterdir())==[]
    finally:other.chmod(0o700)


def test_actual_fixture_pin_and_complete_environment_gate_cache_admission(tmp_path):
    run,cmap,s=inputs(tmp_path)
    positive=er.validate_run(run,cmap,s)
    assert positive['cases'][0]['test_verdict']=='PASS' and positive['cases'][0]['cache_eligible'] is True
    root=tmp_path/'positive'/'generated'
    assert er.sync_docs(positive,root)['status']=='WRITTEN'
    assert er.load_case_registry(root,positive['cases'][0]['cache_key'])['status']=='HIT'
    wrong=copy.deepcopy(run);wrong['cases'][0]['trace']['fixture_sha256']='f'*64
    assert er.validate_run(wrong,cmap,s)['status']=='REFUSED'
    missing=copy.deepcopy(run);missing['cases'][0]['trace'].pop('fixture_sha256')
    observed=er.validate_run(missing,cmap,s)
    assert observed['cases'][0]['test_verdict']=='UNKNOWN' and observed['cases'][0]['expected_contract_verdict']=='PASS'
    assert observed['cases'][0]['cache_eligible'] is False
    for field in environment():
        incomplete=copy.deepcopy(run);incomplete['cases'][0]['environment'].pop(field)
        compared=er.validate_run(incomplete,cmap,s);case=compared['cases'][0]
        assert case['test_verdict']=='PASS' and case['cache_eligible'] is False
        cache=tmp_path/field/'generated'
        assert er.sync_docs(compared,cache)['status']=='WRITTEN'
        assert er.load_case_registry(cache,case['cache_key'])['status']=='MISS'


def test_negative_attempt_observation_cannot_satisfy_no_retry(tmp_path):
    # Actual pure rule evaluator also refuses negatives if supplied outside the tracevalidator.
    rule={'kind':'no_retry','constraint':{'max_attempts':1}}
    assert er._evaluate(rule,{'spans':[{'attempts':-1}]},'unknown',{})==('UNKNOWN','attempts_unobserved')
    rule={'kind':'no_retry','constraint':{'phase':'real_http_request','event':'written','max_count':1}}
    assert er._evaluate(rule,{'spans':[{'phase':'real_http_request','event':'written','count':-1}]},'unknown',{})==('UNKNOWN','attempts_unobserved')


def test_completed_trace_proof_requires_entry_closed_status_and_consistent_recorder(tmp_path):
    run,cmap,s=inputs(tmp_path)
    assert er.validate_run(run,cmap,s)['cases'][0]['test_verdict']=='PASS'
    for mutation in ('missing_entry','missing_recording','drops','count'):
        r=copy.deepcopy(run);t=r['cases'][0]['trace']
        if mutation=='missing_entry':t.pop('source_entry')
        elif mutation=='missing_recording':t.pop('trace_recording')
        elif mutation=='drops':t['trace_recording']['dropped_events']=1
        else:t['trace_recording']['recorded_events']=0
        result=er.validate_run(r,cmap,s)
        assert result['cases'][0]['test_verdict']=='UNKNOWN' and not result['cases'][0]['cache_eligible']
    r=copy.deepcopy(run);r['cases'][0]['trace']['source_entry']='foreign:route'
    assert er.validate_run(r,cmap,s)['status']=='REFUSED'
    r=copy.deepcopy(run);r['cases'][0]['trace']['status']='SECRET_UNKNOWN_STATUS'
    assert er.validate_run(r,cmap,s)['status']=='REFUSED'


def test_runner_value_mismatch_fails_even_when_summary_type_contract_matches(tmp_path):
    run,cmap,s=inputs(tmp_path)
    # Simulates a concrete callable label mismatch while the public summary remains only str.
    run['cases'][0]['trace']['result_matches_expected']=False
    observed=er.validate_run(run,cmap,s);case=observed['cases'][0]
    assert case['rules'][0]['test_verdict']=='PASS'
    assert case['expected_contract_verdict']=='FAIL' and case['test_verdict']=='FAIL'
    assert case['diagnostic_status']=='DRIFT' and case['cache_eligible'] is False
    assert PRIVATE not in json.dumps(observed)


def test_required_expected_value_needs_positive_runner_comparison_proof(tmp_path):
    run,cmap,s=inputs(tmp_path)
    fixture=s['cases'][0]['fixture'];fixture['expected_result']='synthetic-label'
    s['cases'][0]['fixture_digest']=er._digest(fixture);s['content_digest']=er._content(s)
    run['fixture_sha256']=s['content_digest'];t=run['cases'][0]['trace'];t['fixture_sha256']=s['cases'][0]['fixture_digest']
    t['result_matches_expected']=True
    assert er.validate_run(run,cmap,s)['cases'][0]['test_verdict']=='PASS'
    t.pop('result_matches_expected')
    case=er.validate_run(run,cmap,s)['cases'][0]
    assert case['expected_contract_verdict']=='UNKNOWN' and case['test_verdict']=='UNKNOWN' and not case['cache_eligible']


def test_retained_registry_lock_refuses_immediately_without_retry_or_partial_publish(tmp_path):
    import fcntl,os,time
    run,cmap,s=inputs(tmp_path);out=er.validate_run(run,cmap,s);root=tmp_path/'generated'
    assert er.sync_docs(out,root)['status']=='WRITTEN'
    before={p.name:p.read_bytes() for p in root.iterdir()}
    fd=os.open(root/'.sync.lock',os.O_RDWR)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        started=time.monotonic()
        assert er.sync_docs(out,root)['status']=='REFUSED'
        assert er.load_registry(root,out['source_sha256'],out['contract_sha256'],out['fixture_sha256'])['status']=='REFUSED'
        assert er.load_case_registry(root,out['cases'][0]['cache_key'])['status']=='REFUSED'
        assert time.monotonic()-started<1
        assert before=={p.name:p.read_bytes() for p in root.iterdir()}
    finally:os.close(fd)
    assert er.sync_docs(out,root)['status']=='UNCHANGED'
    assert er.load_registry(root,out['source_sha256'],out['contract_sha256'],out['fixture_sha256'])['status']=='HIT'


def test_qualified_boundary_requires_exact_pinned_module_and_class_identity(tmp_path):
    run,cmap,s=inputs(tmp_path)
    cmap['boundaries'][0]['symbol']='worker:Runner.run';cmap['content_digest']=er._content(cmap)
    s['contract_digest']=cmap['content_digest'];s['content_digest']=er._content(s)
    run['contract_sha256']=cmap['content_digest'];run['fixture_sha256']=s['content_digest']
    span=run['cases'][0]['trace']['spans'][0];span['symbol']='Runner.run'
    out=er.validate_run(run,cmap,s)
    assert out['coverage']['boundaries']['observed_ids']==['send']
    assert out['cases'][0]['rules'][0]['trace_anchors']==[{'file':'worker.py','symbol':'Runner.run','line':13}]
    for file,symbol in [('foreign.py','Runner.run'),('nested/worker.py','Runner.run'),('worker.py','Foreign.run'),('worker.py','run')]:
        r=copy.deepcopy(run);r['cases'][0]['trace']['spans'][0].update(file=file,symbol=symbol)
        assert er.validate_run(r,cmap,s)['coverage']['boundaries']['observed']==0
    package_span={'file':'worker/__init__.py','symbol':'Runner.run'}
    assert not er._matches_boundary(package_span,'worker:Runner.run',cmap['route']['source_pins'])
    assert er._matches_boundary(package_span,'worker:Runner.run',[{'path':'worker/__init__.py','sha256':'a'*64}])
    assert er._matches_boundary({'symbol':'legacy.full'},'legacy.full',[])
