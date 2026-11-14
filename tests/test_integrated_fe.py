import json
import os
from pathlib import Path
import subprocess
import sys
from agent_os import __version__, fe_module
from agent_os.module_registry import verify

def test_pinned_module_registry_and_release():
    result=verify()
    assert result['status']=='PASS' and result['release']==__version__
    assert set(result['modules'])=={'agentos','atlas','function-extractor'}

def test_fe_version_works_without_platform_checkout(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('PYTHONPATH','/this/does/not/exist')
    assert fe_module.main(['--version'])==0
    # With an isolated child, neither original application's top-level
    # tools namespace nor central user home is imported into this interpreter.
    assert 'tools.function_extractor' not in sys.modules
    assert not Path.home().joinpath('.agentos-user/state/turns.lock').exists()
    assert list(tmp_path.iterdir()) == []

def test_fe_help_offline():
    assert fe_module.main(['discover','--help'])==0

def test_pinned_fe_diagnostic_rejects_missing_completeness(tmp_path):
    root=Path(__file__).resolve().parents[1]
    from agent_os import fe_module
    script=("from tools.function_extractor.diagnostic_attribution import attribute_unknown;"
            "x={'status':'RETURNED','result_summary':{'state':'unknown'},'spans':[{'phase':'socket_fault','event':'READ_TIMEOUT','evidence':'SIMULATED'}]};"
            "c={'rules':[{'boundary_id':'AVL-H06'}]};p={'facts':{'sendMessage':{'success_result':'Message'}}};"
            "assert attribute_unknown(x,c,p)['status']=='UNKNOWN_CAUSE';"
            "x['trace_recording']={'complete':True,'dropped_events':0,'recorded_events':1,'selected_modules':['app.sample']};"
            "assert attribute_unknown(x,c,p)['status']=='ATTRIBUTED_SIMULATED'")
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
    r=subprocess.run([sys.executable,'-I','-B','-c','import sys;sys.path.insert(0,sys.argv[1]);'+script,str(fe_module._TOOLS)],env=env,capture_output=True,text=True,timeout=8)
    assert r.returncode==0, r.stderr

def test_module_registry_detects_tamper(tmp_path,monkeypatch):
    from agent_os import module_registry
    resources=tmp_path/'res';resources.mkdir();(resources/'contracts').mkdir()
    metadata={'schema':'agentos.modules/v1','modules':{'agentos':{'version':'v','pins':[{'path':'x','sha256':'0'*64}]}}}
    (resources/'contracts/agentos-modules-v1.json').write_text(json.dumps(metadata))
    (resources/'x').write_text('unexpected')
    monkeypatch.setattr(module_registry,'_BASE',resources)
    assert module_registry.verify()['status']=='PIN_MISMATCH'
