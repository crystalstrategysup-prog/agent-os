"""New saved-trace CLI boundaries only; all trace data here is synthetic QA.

No target replay, provider, DB, container or current runtime is executed. The
separate guarded compatibility run supplies actual original-code evidence.
"""
import copy
import json
from pathlib import Path
import subprocess

import pytest

from tools.function_extractor import __version__, api, cli
from tools.function_extractor.diagnostics import compare_trace_paths
from tools.function_extractor.runner.bundle import canonical
from tools.function_extractor.wire_contract import (
    evaluate_contract_observation, observation_content_digest,
)
from tools.function_extractor.tests.test_contract_witness_integration import setup_route


def trace():
    return {'schema':'route-probe.trace/v1','status':'RETURNED',
        'source_entry':'unit:call','sandbox':{'audit':True,'seccomp':True},
        'result_summary':{'type':'str','state':'unknown'},'spans':[],
        'trace_recording':{'complete':True,'recorded_events':0,
                           'dropped_events':0,'selected_modules':[]}}


def write(path, value):
    path.write_bytes(canonical(value))
    return path


def run(paths, output):
    return cli.main(['repeatability', *[arg for p in paths for arg in ('--trace',str(p))],
                     '--out',str(output)])


@pytest.fixture(autouse=True)
def no_target_execution(monkeypatch):
    def denied(*args,**kwargs):
        raise AssertionError('saved-trace command must not dispatch a target')
    monkeypatch.setattr(cli,'_execute',denied)


def test_extract_and_replay_new_metadata_matches_package_version(tmp_path,capsys,monkeypatch):
    source=tmp_path/'source'; source.mkdir()
    (source/'calc.py').write_text('def inc(value):\n    return value + 1\n')
    frozen=tmp_path/'frozen'
    assert cli.main(['extract','--source-root',str(source),'--entry','calc:inc',
                     '--out',str(frozen)])==0
    extracted=json.loads(capsys.readouterr().out)
    assert extracted['tool_version']==__version__
    fixture=write(tmp_path/'fixture.json',{'args':[1]})
    # Exercise CLI metadata/report generation only, never a child target.
    monkeypatch.setattr(cli,'_execute',lambda *a,**k:trace())
    output=tmp_path/'replay'
    assert cli.main(['replay','--bundle',str(frozen/'route_bundle.json'),
                     '--fixture',str(fixture),'--runner','subprocess','--out',str(output)])==0
    emitted=json.loads(capsys.readouterr().out)
    manifest=json.loads((output/'evidence_manifest.json').read_bytes())
    assert emitted['tool_version']==manifest['tool_version']==__version__
    with pytest.raises(SystemExit) as stop:
        cli.main(['--version'])
    assert stop.value.code==0
    assert capsys.readouterr().out.strip()=='function-extractor '+__version__


def test_repeatability_keeps_full_witness_when_path_matches(tmp_path,capsys):
    data=setup_route(tmp_path)
    original=data[-1]['cases'][0]['trace']; changed=copy.deepcopy(original)
    plan=data[5]; binding=data[6][1]
    changed['contract_observations']['observations'][1]=evaluate_contract_observation(
        plan,binding_id=binding['binding_id'],value={'ok':'SYNTHETIC_PRIVATE_CANARY'},
        phase=binding['phase'],anchor={k:binding[k] for k in ('file','sha256','symbol','line')},
        invocation_id=1)
    changed['contract_observations']['content_digest']=observation_content_digest(
        changed['contract_observations'])
    assert compare_trace_paths(original,changed)['status']=='MATCH'
    paths=[write(tmp_path/'a.json',original),write(tmp_path/'b.json',changed)]
    out=tmp_path/'mismatch.json'
    assert run(paths,out)==3
    result=json.loads(capsys.readouterr().out)
    assert result==json.loads(out.read_bytes())==api.verify_repeatability([original,changed])
    assert result['status']=='MISMATCH'
    assert not result['data']['repeatability']['normalized_equal']
    assert 'SYNTHETIC_PRIVATE_CANARY' not in out.read_text()


def test_saved_result_is_deterministic_and_not_delivery_acceptance(tmp_path,capsys):
    first=trace(); second=copy.deepcopy(first)
    first['correlation_id']='a'*32; second['correlation_id']='b'*32
    first['trace_recording']['complete']=second['trace_recording']['complete']=False
    files=[write(tmp_path/'a.json',first),write(tmp_path/'b.json',second)]
    outputs=[tmp_path/'one.json',tmp_path/'two.json']
    for output in outputs:
        assert run(files,output)==0
        result=json.loads(capsys.readouterr().out)
        assert result['status']=='REPEATABLE'
        assert result['data']['repeatability']['production_acceptance'] is False
        assert result==api.verify_repeatability([first,second])
    assert outputs[0].read_bytes()==outputs[1].read_bytes()
    assert outputs[0].stat().st_mode & 0o777==0o600


@pytest.mark.parametrize('count',[1,101])
def test_count_refusal_precedes_reads(tmp_path,capsys,monkeypatch,count):
    def no_read(*args,**kwargs):
        raise AssertionError('count must be checked before reads')
    monkeypatch.setattr(cli,'_read',no_read)
    out=tmp_path/'out.json'
    assert run([tmp_path/'does-not-exist.json']*count,out)==2
    assert json.loads(capsys.readouterr().out)['status']=='REFUSED'
    assert not out.exists()


@pytest.mark.parametrize('count',[2,100])
def test_count_boundaries_preserve_input_order_and_cardinality(tmp_path,capsys,count):
    p=write(tmp_path/'trace.json',trace()); out=tmp_path/'out.json'
    assert run([p]*count,out)==0
    result=json.loads(capsys.readouterr().out)['data']['repeatability']
    assert result['runs']==len(result['digests'])==count


@pytest.mark.parametrize('fault',['unknown_private_field','bad_observation_digest'])
def test_invalid_trace_is_closed_refusal_without_data_echo(tmp_path,capsys,fault):
    if fault=='unknown_private_field':
        bad=trace(); bad['auth']='SYNTHETIC_PRIVATE_CANARY'
    else:
        data=setup_route(tmp_path); bad=data[-1]['cases'][0]['trace']
        bad['contract_observations']['content_digest']='0'*64
    files=[write(tmp_path/'bad.json',bad),write(tmp_path/'good.json',trace())]
    output=tmp_path/'result.json'
    assert run(files,output)==2
    text=capsys.readouterr().out
    assert json.loads(text)['status']=='REFUSED'
    assert 'SYNTHETIC_PRIVATE_CANARY' not in text+output.read_text()


@pytest.mark.parametrize('kind',['symlink_input','secret_input','symlink_output','existing_output'])
def test_safe_paths_and_exclusive_output_retained(tmp_path,capsys,kind):
    p=write(tmp_path/'trace.json',trace()); paths=[p,p]; out=tmp_path/'out.json'
    preserved=tmp_path/'preserved.json'; preserved.write_bytes(b'PRESERVE_ORIGINAL')
    if kind=='symlink_input':
        link=tmp_path/'link.json'; link.symlink_to(p); paths[0]=link
    elif kind=='secret_input':
        secret=write(tmp_path/'credentials.json',trace()); paths[0]=secret
    elif kind=='symlink_output':out.symlink_to(preserved)
    else:out.write_bytes(b'PRESERVE_ORIGINAL')
    assert run(paths,out)==2
    assert json.loads(capsys.readouterr().out)['status']=='REFUSED'
    assert preserved.read_bytes()==b'PRESERVE_ORIGINAL'
    if kind=='existing_output':assert out.read_bytes()==b'PRESERVE_ORIGINAL'


def test_raw_per_trace_and_compact_total_budget_precede_comparison(tmp_path,capsys,monkeypatch):
    called=[]
    def no_compare(*args):
        called.append(True); raise AssertionError('overbudget comparison')
    monkeypatch.setattr(api,'verify_repeatability',no_compare)
    oversized=tmp_path/'oversized.json'; oversized.write_bytes(b' '*2_000_001)
    small=write(tmp_path/'small.json',trace())
    assert run([oversized,small],tmp_path/'too-large.json')==2
    assert json.loads(capsys.readouterr().out)['status']=='REFUSED'
    bulky=trace(); bulky['spans']=[{'phase':'call','event':'call','evidence':'REAL_CODE',
        'file':'unit.py','symbol':'x'*256,'line':1} for _ in range(4900)]
    bulky['trace_recording']['recorded_events']=len(bulky['spans'])
    size=len(canonical(bulky)); assert 8_000_000/5 < size < 2_000_000
    path=write(tmp_path/'bulky.json',bulky)
    assert run([path]*5,tmp_path/'aggregate.json')==2
    assert json.loads(capsys.readouterr().out)['status']=='REFUSED'
    assert called==[]


def test_unexpected_api_unknown_stays_unknown_and_exit_two(tmp_path,capsys,monkeypatch):
    value={'schema':'function-extractor.result/v1','version':1,
        'operation':'verify_repeatability','status':'UNKNOWN','data':{},
        'errors':['UNEXPECTED_DEPENDENCY_FAILURE']}
    monkeypatch.setattr(api,'verify_repeatability',lambda *a:value)
    p=write(tmp_path/'trace.json',trace()); out=tmp_path/'out.json'
    assert run([p,p],out)==2
    assert json.loads(capsys.readouterr().out)==json.loads(out.read_bytes())==value


def test_new_outputs_match_existing_offline_result_schema(tmp_path,capsys):
    a=trace(); b=copy.deepcopy(a); b['result_summary']['state']='sent'
    paths=[write(tmp_path/'a.json',a),write(tmp_path/'b.json',b)]
    outputs=[]
    for pair,name in [([paths[0],paths[0]],'equal'),(paths,'different')]:
        out=tmp_path/(name+'.json'); assert run(pair,out) in (0,3)
        capsys.readouterr(); outputs.append(json.loads(out.read_bytes()))
    folder=Path(cli.__file__).parent/'contracts'
    # Reuse installed system jsonschema; never install packages or fetch refs.
    script='''import json,sys
from pathlib import Path
import jsonschema
root=Path(sys.argv[1]); schemas=[json.loads(p.read_text()) for p in root.glob('*.schema.json')]
store={s['$id']:s for s in schemas if '$id' in s}; schema=json.loads((root/'result.schema.json').read_text())
def deny(uri): raise AssertionError('external schema retrieval forbidden')
resolver=jsonschema.RefResolver.from_schema(schema,store=store,handlers={'http':deny,'https':deny})
for item in json.load(sys.stdin): jsonschema.Draft202012Validator(schema,resolver=resolver).validate(item)
print('FORMAL_RESULTS_VALID')
'''
    r=subprocess.run(['/usr/bin/python3','-B','-c',script,str(folder)],
        input=json.dumps(outputs),capture_output=True,text=True,timeout=15)
    assert r.returncode==0,r.stderr
    assert r.stdout.strip()=='FORMAL_RESULTS_VALID'
