from concurrent.futures import ThreadPoolExecutor
import copy
import json
import pytest
from agent_os import project_lite as lite
from agent_os.safeio import GateError, atomic_json


def request(executor='one', operation='register', task='fix'):
    return {'operation_id':operation, 'executor':executor, 'kind':'REGISTER', 'payload':{
        'project_key':'sample', 'task_key':task, 'goal':'Fix bounded defect', 'scope':'Own source tree',
        'acceptance':'Offline regressions pass', 'authority_ref':'Owner source-only task', 'effect':'source-only'}}


def root(tmp_path):
    p=tmp_path/'source';p.mkdir();return p


def test_local_no_central_dependency_and_exact_replay(tmp_path, monkeypatch):
    r=root(tmp_path)
    monkeypatch.setattr('agent_os.turns.bind_turn',lambda *a,**k:pytest.fail('central turn must not be used'))
    a=lite.record(r,request());b=lite.record(r,request())
    assert a['status']==b['status']=='LOCAL_RECORDED' and b['replay']
    assert a['ready'] is a['authority_granted'] is False
    assert lite.status(r)['event_count']==1
    assert not (r/'.agentos/project.json').exists()
    p=request();p['payload']['goal']='Different goal'
    assert lite.record(r,p)['status']=='CONFLICT'
    assert lite.record(r,request('other','other-op'))['status']=='CONFLICT'


@pytest.mark.parametrize('effect',['production','external-send','credentials','db-write','offline-test-with-network',None])
def test_independent_effects_rejected(tmp_path,effect):
    r=root(tmp_path);p=request();p['payload']['effect']=effect
    with pytest.raises(GateError):lite.record(r,p)
    assert lite.status(r)['status']=='NOT_RECORDED'


def test_sync_idempotence_incremental_and_other_journal_conflict(tmp_path):
    r=root(tmp_path);home=tmp_path/'central';home.mkdir()
    a=lite.record(r,request())
    assert lite.sync(r,home)['added_events']==1
    assert lite.sync(r,home)['added_events']==0
    lite.record(r,{'operation_id':'progress','executor':'one','kind':'PROGRESS','task_id':a['task_id'],'payload':{'facts':['verified SHA']}})
    assert lite.sync(r,home)['added_events']==1
    other=tmp_path/'other';other.mkdir();lite.record(other,request())
    assert lite.sync(other,home)['status']=='CONFLICT'
    registry=json.loads((home/'state/local-projects/registry.json').read_text())
    assert len(registry['journals'])==1


def test_sync_failure_preserves_local_and_reconciles_after_commit(tmp_path,monkeypatch):
    r=root(tmp_path);home=tmp_path/'central';home.mkdir();lite.record(r,request())
    original=lite.atomic_json
    def failed(path,value):
        if 'registry.json' in str(path):
            original(path,value);raise OSError('lost reply after replace')
        return original(path,value)
    monkeypatch.setattr(lite,'atomic_json',failed)
    assert lite.sync(r,home)['sync']=='UNKNOWN'
    monkeypatch.setattr(lite,'atomic_json',original)
    assert lite.sync(r,home)['added_events']==0
    assert lite.status(r)['event_count']==1


def test_local_permission_failure_and_after_replace_reconciliation(tmp_path,monkeypatch):
    r=root(tmp_path);original=lite.atomic_json
    monkeypatch.setattr(lite,'atomic_json',lambda *a,**k: (_ for _ in ()).throw(PermissionError('read only')))
    assert lite.record(r,request())['status']=='NOT_RECORDED'
    def after(path,value):original(path,value);raise OSError('after replace')
    monkeypatch.setattr(lite,'atomic_json',after)
    assert lite.record(r,request())['status']=='LOCAL_RECORDED'
    assert lite.status(r)['event_count']==1


def test_corrupt_local_and_central_journals_never_overwritten(tmp_path):
    r=root(tmp_path);home=tmp_path/'central';home.mkdir();lite.record(r,request());lite.sync(r,home)
    path=home/'state/local-projects/registry.json';old=path.read_bytes();value=json.loads(old)
    next(iter(value['journals'].values()))['events'][0]['payload']['goal']='tamper'
    atomic_json(path,value);tampered=path.read_bytes()
    with pytest.raises(GateError):lite.sync(r,home)
    assert path.read_bytes()==tampered
    path=r/'.agentos/lite/journal.json';value=json.loads(path.read_text());value['events'][0]['payload']['goal']='tamper';atomic_json(path,value)
    with pytest.raises(GateError):lite.record(r,request())


def test_competing_executors_and_no_lost_updates(tmp_path):
    r=root(tmp_path)
    def run(i):
        try:return lite.record(r,request('exec'+str(i),'op'+str(i)))['status']
        except GateError as e:return str(e)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,[1,2]))
    assert results.count('LOCAL_RECORDED')==1
    assert lite.status(r)['event_count']==1


def test_pending_legacy_transaction_and_active_writer_preserved(tmp_path):
    r=root(tmp_path);p=r/'.agentos/entry-transaction.json';p.parent.mkdir();p.write_text('{}')
    with pytest.raises(GateError,match='reconciliation'):lite.record(r,request())
    assert p.read_text()=='{}'
    p.unlink();atomic_json(r/'.agentos/project.json',{'active_task':'task-active'})
    atomic_json(r/'.agentos/tasks/task-active/task.json',{'status':'INTAKE'})
    with pytest.raises(GateError,match='reconciliation'):lite.record(r,request())


def test_symlink_and_unknown_executor_rejected(tmp_path):
    r=root(tmp_path);other=tmp_path/'other';other.mkdir();(r/'.agentos').symlink_to(other,target_is_directory=True)
    with pytest.raises(GateError):lite.record(r,request())
    (r/'.agentos').unlink();a=lite.record(r,request())
    assert lite.record(r,{'operation_id':'bad','executor':'other','kind':'RESULT','task_id':a['task_id'],'payload':{}})['status']=='CONFLICT'
