"""Package-embedded, isolated Function Extractor CLI without app imports.

Keeps the existing FE interpreter/import layout unchanged inside package data.
A subinterpreter-like process (Python -I) prevents collisions with the user's
application ``tools`` package. It inherits the current OS/sandbox authority.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys

_TOOLS = Path(__file__).resolve().parent / 'resources' / 'fe_tools'
_CODE = ('import sys;sys.path.insert(0,sys.argv[1]);'
         'from tools.function_extractor.cli import main;'
         'raise SystemExit(main(sys.argv[2:]))')

def main(argv=None):
    from .module_registry import verify
    result = verify()
    if result['status'] != 'PASS':
        print(json.dumps({'status':'BLOCKED','reason':'PACKAGED_MODULE_PIN_MISMATCH'},
                         ensure_ascii=False))
        return 2
    if argv is None:
        argv = sys.argv[1:]
    if not (_TOOLS / 'tools/function_extractor/cli.py').is_file():
        print(json.dumps({'status':'BLOCKED','reason':'FE_ENGINE_NOT_INSTALLED'}))
        return 2
    # Hide caller PYTHONPATH/credential-bearing application environment;
    # this does not change user id, privileges, hooks or sandbox settings.
    allow = ('PATH','LANG','LC_ALL','TZ','SYSTEMROOT','TMPDIR','TMP','TEMP')
    env = {k:os.environ[k] for k in allow if k in os.environ}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONNOUSERSITE'] = '1'
    try:
        completed = subprocess.run([sys.executable,'-I','-B','-c',_CODE,str(_TOOLS),*argv],
                                   env=env,check=False,timeout=900)
        return completed.returncode
    except subprocess.TimeoutExpired:
        print(json.dumps({'status':'UNKNOWN','reason':'FE_PROCESS_DEADLINE'}))
        return 3

if __name__ == '__main__':
    raise SystemExit(main())
