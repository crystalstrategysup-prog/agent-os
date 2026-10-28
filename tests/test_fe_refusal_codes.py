"""Actual CLI refusals using synthetic source or a finite injected engine fault."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'src/agent_os/resources/fe_tools'


def invoke(code, args, cwd):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    return subprocess.run([sys.executable, '-I', '-B', '-c', code, *map(str,args)],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=20)


def test_integrated_cli_strict_graph_cap_is_classified(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    body = ''.join(f'def f{i}():\n    return f{i+1}()\n\n' for i in range(14))
    body += 'def f14():\n    return 1\n'
    path = source / 'sample.py'; path.write_text(body)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    output = tmp_path / 'bundle'
    code = ('import sys;sys.path.insert(0,sys.argv[1]);'
            'from agent_os.fe_module import main;raise SystemExit(main(sys.argv[2:]))')
    result = invoke(code, [ROOT/'src','extract','--source-root',source,
                          '--entry','sample:f0','--capture-mode','STRICT','--out',output], tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout) == {'schema':'function-extractor.cli/v1','status':'REFUSED',
                                        'error_class':'ValueError','error_code':'graph_expansion_cap'}
    assert result.stderr == '' and not output.exists()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize('kind', ['sensitive-reason','multiple-args','subclass','other-class'])
def test_cli_does_not_expose_unreviewed_error_text(tmp_path, kind):
    # Fault is injected only at the engine boundary; real CLI main/serialization
    # and exit behavior execute in an isolated child. No target source executes.
    code = '''import sys,types
sys.path.insert(0,sys.argv[1])
from tools.function_extractor import cli
class CustomValueError(ValueError): pass
private = "PRIVATE_FIXTURE_REASON_NOT_FOR_OUTPUT /nonpublic/fixture/input.json graph_expansion_cap-extra"
errors = {"sensitive-reason":ValueError(private), "multiple-args":ValueError("graph_expansion_cap",private),
          "subclass":CustomValueError("graph_expansion_cap"), "other-class":RuntimeError("graph_expansion_cap")}
def refused(*args,**kwargs): raise errors[sys.argv[2]]
cli.load_engine=lambda name: types.SimpleNamespace(freeze_bundle=refused)
raise SystemExit(cli.main(["extract","--source-root",sys.argv[3],"--entry","sample:f0","--out",sys.argv[4]]))
'''
    output = tmp_path/'bundle'
    result = invoke(code,[TOOLS,kind,tmp_path,output],tmp_path)
    assert result.returncode == 2
    expected = {'subclass':'CustomValueError','other-class':'RuntimeError'}.get(kind,'ValueError')
    assert json.loads(result.stdout) == {'schema':'function-extractor.cli/v1','status':'REFUSED','error_class':expected}
    assert result.stderr == '' and not output.exists()
    assert 'PRIVATE_FIXTURE' not in result.stdout and '/nonpublic/' not in result.stdout


def test_release_contracts_match_actual_mcp_reader(tmp_path):
    code = """import sys,json,tomllib
from pathlib import Path
sys.path.insert(0,sys.argv[1]);root=Path(sys.argv[2])
from agent_os import __version__
from agent_os.mcp_server import response
assert tomllib.loads((root/'pyproject.toml').read_text())['project']['version']==__version__
for name in ['cli-contract-v1.json','mcp-tools-v1.json']:
 a=json.loads((root/'schemas'/name).read_text());b=json.loads((root/'src/agent_os/resources/contracts'/name).read_text());assert a==b
 assert (a['distribution_version'] if name.startswith('cli-') else a['serverInfo']['version'])==__version__
assert response({'jsonrpc':'2.0','id':1,'method':'initialize'})['result']['serverInfo']['version']==__version__
"""
    result=invoke(code,[ROOT/'src',ROOT],tmp_path)
    assert result.returncode==0,result.stdout+result.stderr
