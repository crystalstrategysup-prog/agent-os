"""Exercise the shipped scripts outside the application's import layout."""
import json
import os
from pathlib import Path
import subprocess
import sys
import venv

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'src/agent_os/resources/skills/function-extractor/scripts'


def invoke(name, cwd, *args):
    return subprocess.run([sys.executable, '-I', '-B', str(SCRIPTS / name), *args],
                          cwd=cwd, env={'HOME': str(cwd), 'PATH': os.defpath},
                          capture_output=True, text=True, timeout=15)


def test_packaged_cli_has_no_application_checkout_or_user_state(tmp_path):
    assert os.access(SCRIPTS / 'fe', os.X_OK)
    result = invoke('fe', tmp_path, '--version')
    assert result.returncode == 0, result.stderr
    assert '0.4.6' in result.stdout
    result = invoke('fe', tmp_path, 'discover', '--help')
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('name', ['fe-environment', 'fe-environment-catalog',
                                  'fe-environment-ensure'])
def test_environment_helpers_use_selected_project_and_fail_closed(tmp_path, name):
    selected = tmp_path / 'selected'
    selected.mkdir()
    result = invoke(name, tmp_path, '--source-root', str(selected))
    assert result.returncode == 2, result.stdout + result.stderr
    document = json.loads(result.stdout)
    assert document['status'] != 'EXISTING_QUALIFIED'
    assert list(selected.iterdir()) == []
    assert set(tmp_path.iterdir()) == {selected}


def test_bootstrap_reexecutes_only_its_own_existing_release_python(tmp_path):
    """A minimal disposable release proves dispatch, without installing code."""
    release = tmp_path / 'release'
    venv.EnvBuilder(with_pip=False).create(release / '.venv')
    python = release / '.venv/bin/python'
    package = release / '.venv/lib/fake-site/agent_os'
    scripts = package / 'resources/skills/function-extractor/scripts'
    scripts.mkdir(parents=True)
    (package / 'fe_module.py').write_text('# packaged identity\n')
    engine = package / 'resources/fe_tools/tools/function_extractor/cli.py'
    engine.parent.mkdir(parents=True)
    engine.write_text('# engine identity\n')
    (package / '__init__.py').write_text('')
    (package / 'module_registry.py').write_text("def verify(): return {'status':'PASS'}\n")
    (scripts / '_bootstrap.py').write_bytes((SCRIPTS / '_bootstrap.py').read_bytes())
    script = scripts / 'probe'
    script.write_text("import runpy,json,sys\nfrom pathlib import Path\n"
                      "root,project=runpy.run_path(str(Path(__file__).with_name('_bootstrap.py')))['prepare'](__file__)\n"
                      "print(json.dumps({'prefix':sys.prefix,'isolated':sys.flags.isolated,'root':str(root),'args':sys.argv[1:]}))\n")
    result = subprocess.run([sys.executable, '-I', '-B', str(script), 'retained-argument'],
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    assert Path(actual['prefix']).resolve() == python.parent.parent.resolve()
    assert actual['isolated'] == 1 and actual['args'] == ['retained-argument']
    assert Path(actual['root']) == package / 'resources/fe_tools'
