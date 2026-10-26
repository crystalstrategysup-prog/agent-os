"""NEW structural CE schema QA only: no target/runner/native/container execution."""
import copy
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from tools.function_extractor.contract_engine import resolve_contracts
from tools.function_extractor.scenario_engine import generate_scenarios


def test_current_profiles_generated_artifacts_and_run_workflow_shapes_formally_validate():
    folder=ROOT/'tools/function_extractor/contracts'
    names=['ce_profile.schema.json','ce_scenarios.schema.json','ce_run.schema.json','ce_workflow.schema.json']
    schemas={p.name:json.loads(p.read_text()) for p in folder.glob('*.schema.json')}
    store={s['$id']:s for s in schemas.values() if '$id' in s}
    store.update(schemas)
    store.update({(folder/name).as_uri():s for name,s in schemas.items()})
    valid=[]
    generated=[]
    for route in ('avl','tenant_labels'):
        spec=json.loads((ROOT/f'tools/function_extractor/profiles/newcontract_{route}.inputs.json').read_text())
        profile=json.loads((ROOT/f'tools/function_extractor/profiles/newcontract_{route}.profile.json').read_text())
        spec['revision']['source_root']=str(ROOT)
        cmap=resolve_contracts(**spec)
        assert cmap['status']!='REFUSED'
        scenarios=generate_scenarios(cmap,profile,17,{'max_cases':128,'max_input_variants':0})
        assert scenarios['status'] in {'GENERATED','PARTIAL'} and scenarios['cases']
        valid.extend([['ce_profile.schema.json',profile],['ce_scenarios.schema.json',scenarios]])
        generated.append(scenarios)
    # These two envelopes are structural synthetic canaries, NOT observed execution.
    row=generated[1]['cases'][0]
    t={'schema':'route-probe.trace/v1','status':'RETURNED','sandbox':{'audit':True,'seccomp':True},'spans':[],
       'source_entry':row['entry'],'fixture_sha256':row['fixture_digest']}
    run={'schema':'contract-run/v1','source_sha256':'1'*64,'contract_sha256':generated[1]['contract_digest'],
         'fixture_sha256':generated[1]['content_digest'],'cases':[{'case_id':row['id'],'trace':t,
         'environment':{'source_sha256':'1'*64,'bundle_sha256':'2'*64,'manifest_source_sha256':'3'*64,
                        'runner_sha256':'4'*64,'profile_sha256':'5'*64,'runner':'subprocess'}}]}
    workflow={'schema':'function-extractor.contract-workflow/v1','version':1,'status':'UNKNOWN',
              'counts':{'PASS':0,'FAIL':0,'UNKNOWN':1},'cases':[{'case_id':row['id'],'executed_this_run':False,
              'cache_hit':False,'scope':'VALIDATION_ONLY'}],
              'timing':{'bundle_verification_seconds':0.0,'execution_seconds':0.0,'validation_seconds':0.0,'total_seconds':0.0},
              'registry':{'schema':'ce-evidence.sync/v1','status':'WRITTEN','key':'6'*64,'content_digest':'7'*64,'normative_modified':False},
              'source_sha256':'1'*64,'contract_sha256':generated[1]['contract_digest'],'runner_sha256':'4'*64,
              'profile_sha256':'5'*64,'production_effects':0,'live_provider_observed':False,'historical_cause':'NOT_REPRODUCED'}
    valid.extend([['ce_run.schema.json',run],['ce_workflow.schema.json',workflow],
                  ['ce_workflow.schema.json',{'schema':'function-extractor.contract-workflow/v1','status':'BLOCKED_LIVE_PROOF','production_effects':0}],
                  ['ce_scenarios.schema.json',{'schema':'function-extractor.generated-scenarios/v1','version':1,'status':'REFUSED','cases':[],'errors':['SCENARIO_INPUT_INVALID']}]])
    invalid=[]
    profile_bad=copy.deepcopy(valid[0][1]);profile_bad['bindings'][0]['unknown_field']='SYNTHETIC_PRIVATE_CANARY'
    invalid.append(['ce_profile.schema.json',profile_bad])
    profile_bad=copy.deepcopy(valid[0][1]);profile_bad['version']=True
    invalid.append(['ce_profile.schema.json',profile_bad])
    scenarios_bad=copy.deepcopy(generated[0]);scenarios_bad['cases'][0]['fixture']=[]
    invalid.append(['ce_scenarios.schema.json',scenarios_bad])
    scenarios_bad=copy.deepcopy(generated[0]);scenarios_bad['cases'][0]['fixture_digest']='not-a-sha'
    invalid.append(['ce_scenarios.schema.json',scenarios_bad])
    run_bad=copy.deepcopy(run);run_bad['cases'][0]['environment']['token']='SYNTHETIC_PRIVATE_CANARY'
    invalid.append(['ce_run.schema.json',run_bad])
    run_bad=copy.deepcopy(run);run_bad['cases'][0]['trace']['status']='UNVERIFIED_SUCCESS'
    invalid.append(['ce_run.schema.json',run_bad])
    workflow_bad=copy.deepcopy(workflow);workflow_bad['production_effects']=1
    invalid.append(['ce_workflow.schema.json',workflow_bad])
    workflow_bad=copy.deepcopy(workflow);workflow_bad['cases'][0]['cache_hit']='false'
    invalid.append(['ce_workflow.schema.json',workflow_bad])
    # Cross-artifact URNs are resolved from this exact local store, never fetched.
    def check_refs(v):
        if type(v) is dict:
            if '$ref' in v:assert v['$ref']=='#' or v['$ref'].startswith('#/') or v['$ref'].split('#',1)[0] in store
            for child in v.values():check_refs(child)
        elif type(v) is list:
            for child in v:check_refs(child)
    for schema in schemas.values():check_refs(schema)
    script='''import json,sys
from jsonschema import Draft202012Validator,RefResolver
from pathlib import Path
v=json.load(sys.stdin)
store={s['$id']:s for s in v['schemas'].values() if '$id' in s}
store.update(v['schemas'])
store.update({(Path(v['folder'])/name).as_uri():s for name,s in v['schemas'].items()})
def no_retrieval(uri):raise AssertionError('schema_network_retrieval_forbidden')
def validator(schema):return Draft202012Validator(schema,resolver=RefResolver.from_schema(schema,store=store,handlers={k:no_retrieval for k in ('http','https','urn','file')}))
for schema in v['schemas'].values():Draft202012Validator.check_schema(schema)
for name,data in v['valid']:validator(v['schemas'][name]).validate(data)
for name,data in v['invalid']:
 if validator(v['schemas'][name]).is_valid(data):raise SystemExit(2)
print(json.dumps({'formal_schemas':len(v['selected']),'valid_artifacts':len(v['valid']),'malformed_refused':len(v['invalid'])}))
'''
    proc=subprocess.run(['/usr/bin/python3','-I','-W','ignore::DeprecationWarning','-c',script],input=json.dumps({'schemas':schemas,'folder':str(folder),'selected':names,'valid':valid,'invalid':invalid}),
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=20)
    assert proc.returncode==0, {'category':'FORMAL_SCHEMA_QA_FAILED','returncode':proc.returncode}
    result=json.loads(proc.stdout)
    assert result=={'formal_schemas':4,'valid_artifacts':8,'malformed_refused':8}
    assert proc.stderr=='' and 'SYNTHETIC_PRIVATE_CANARY' not in proc.stdout
