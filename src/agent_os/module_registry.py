"""Offline package module inventory. No external authority conferred."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from . import __version__

_BASE=Path(__file__).resolve().parent / 'resources'
_MANIFEST='contracts/agentos-modules-v1.json'

def verify():
    raw=(_BASE/_MANIFEST).read_bytes()
    metadata=json.loads(raw)
    failures=[]
    for name, info in metadata['modules'].items():
        for pin in info['pins']:
            path=_BASE / pin['path']
            if (not path.is_file() or path.is_symlink()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != pin['sha256']):
                failures.append({'module':name,'path':pin['path']})
    return {'status':'PASS' if not failures else 'PIN_MISMATCH',
            'schema':'agentos.modules-readback/v1','release':__version__,
            'modules':{name:{'version':v['version'],'files_checked':len(v['pins'])}
                for name,v in metadata['modules'].items()},'failures':failures}

def command(argv):
    if argv and argv not in (['check'],['list']):
        return {'status':'BLOCKED','reason':'MODULES_USAGE'},2
    res=verify()
    return res,0 if res['status']=='PASS' else 2
