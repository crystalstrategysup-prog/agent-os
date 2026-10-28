"""Explicit bounded selection of unfinished checkpoint capture surfaces."""
from pathlib import PurePosixPath
from .safeio import GateError,sha

SCHEMA = 'agentos.checkpoint-capture-selection/v1'

def validate(root,task,snapshot,request):
    if request is None:return None
    def require(ok):
        if not ok:raise GateError('checkpoint_capture_selection_invalid')
    require(isinstance(request,dict) and set(request)=={'schema','root','task_id','revision','task_sha256','project_sha256','source_sha256','authority_ref','capture_paths'})
    require(request['schema']==SCHEMA and request['root']==str(root))
    require(request['task_id']==task['id'] and type(request['revision']) is int and request['revision']==task['revision'])
    require(request['task_sha256']==sha((root/'.agentos/tasks'/task['id']/'task.json').read_bytes()))
    require(request['project_sha256']==sha((root/'.agentos/project.json').read_bytes()))
    require(request['source_sha256']==snapshot['sha256'])
    require(isinstance(request['authority_ref'],str) and 0<len(request['authority_ref'])<=512)
    paths=request['capture_paths']
    require(isinstance(paths,list) and 0<len(paths)<=64)
    selected=[]
    for path in paths:
        require(isinstance(path,str) and 0<len(path)<=1024)
        p=PurePosixPath(path)
        require(path not in {'.','..'} and not p.is_absolute() and path==p.as_posix() and '..' not in p.parts and '\\' not in path and '\x00' not in path and path not in selected)
        require(any(path==a or path.startswith(a.rstrip('/')+'/') for a in task['answers']['write_paths']))
        require(any(f==path or f.startswith(path+'/') for f in snapshot['files']))
        selected.append(path)
    return selected
