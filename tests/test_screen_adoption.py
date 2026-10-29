"""Finite same-SID adoption fixtures; no real Codex or host workers."""
import contextlib
import copy
import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from agent_os.codex_launch import CodexLaunchProvider, StdioRpc
from agent_os.safeio import atomic_json, digest
from agent_os.screen_adoption import adopt_screen, _old_readback
from agent_os.session_launch import LaunchError
from test_thread_continuation import ExistingRpc, SID
from test_codex_launch import fixture
from test_screen_launch import screen_fixture


def profile(tmp_path):
    request, _, _ = fixture(tmp_path)
    request['executor']['approved_sandbox'] = 'danger-full-access'
    rpc = ExistingRpc(request)
    rpc.config['sandbox_mode'] = 'danger-full-access'
    retained = {'session_id': SID, 'workspace': request['workspace'], 'connection_id': 'historical-connection',
                'model': 'fixture-model', 'model_provider': 'openai', 'reasoning_effort': 'medium',
                'sandbox': 'danger-full-access', 'approval_policy': 'never'}
    original = rpc.call
    response = {'thread': {'id': SID}, 'cwd': request['workspace'], 'model': 'fixture-model',
                'modelProvider': 'openai', 'reasoningEffort': 'medium', 'approvalPolicy': 'never',
                'sandbox': {'type': 'dangerFullAccess'}, 'approvalsReviewer': 'user', 'runtimeWorkspaceRoots': []}
    def call(method, params, *, deadline=None):
        if method == 'thread/resume':
            rpc.calls.append((method, copy.deepcopy(params)))
            assert params == {'threadId': SID, 'excludeTurns': True}
            return copy.deepcopy(response)
        return original(method, params, deadline=deadline)
    rpc.call = call
    return request, rpc, retained, response


def test_adoption_provider_same_sid_defaults_distinct_no_overrides(tmp_path):
    request, rpc, retained, _ = profile(tmp_path)
    provider = CodexLaunchProvider(rpc)
    observed = provider.describe_adoption(request, retained, 'attempt')
    assert observed['model_metadata_source'] == 'retained_startup_candidate_only'
    assert observed['model_preflight']['configured_model'] == 'fixture-default'
    startup = provider.resume(request, retained, 'attempt')
    assert startup['session_id'] == SID and startup['connection_id'] != retained['connection_id']
    assert startup['model_metadata_source'] == 'thread_resume_response'
    assert startup['permission_readback']['historical_reviewer_and_runtime_roots'] == 'UNKNOWN'
    assert [m for m, _ in rpc.calls] == ['config/read', 'model/list', 'thread/resume', 'config/read', 'thread/read', 'model/list']
    with pytest.raises(LaunchError): provider.resume(request, retained, 'another-operation')
    assert sum(m == 'thread/resume' for m, _ in rpc.calls) == 1


@pytest.mark.parametrize('key,value', [('model','fixture-default'), ('modelProvider','wrong-provider'),
    ('reasoningEffort',None), ('cwd','/different'), ('approvalPolicy','on-request'),
    ('sandbox',{'type':'dangerFullAccess','writableRoots':['/unexpected']}), ('thread',{'id':'wrong-id'})])
def test_adoption_resume_drift_rejected_before_probe(tmp_path, key, value):
    request, rpc, retained, response = profile(tmp_path)
    provider = CodexLaunchProvider(rpc); provider.describe_adoption(request, retained, 'attempt')
    response[key] = value
    with pytest.raises(LaunchError): provider.resume(request, retained, 'attempt')
    assert all(m != 'turn/start' for m, _ in rpc.calls)


@pytest.mark.parametrize('field,value', [('sandbox','workspace-write'),('approval_policy','on-request')])
def test_adoption_unknown_permission_profiles_never_resume(tmp_path, field, value):
    request, rpc, retained, _ = profile(tmp_path); retained[field] = value
    with pytest.raises(LaunchError, match='adoption_permission_profile_unsupported'):
        CodexLaunchProvider(rpc).describe_adoption(request, retained, 'attempt')
    assert rpc.calls == []


@pytest.mark.parametrize('params', [{'threadId':SID,'excludeTurns':False},
    {'threadId':SID,'excludeTurns':True,'model':'override'}, {'threadId':'bad','excludeTurns':True}])
def test_adoption_rpc_allows_only_exact_no_override_resume(params):
    rpc = object.__new__(StdioRpc)
    with pytest.raises(LaunchError): rpc.call('thread/resume', params)


def old_registry(f):
    old = f['home']/'state/screen-workers/old';old.mkdir(parents=True)
    retained = {'session_id':SID,'workspace':f['request']['workspace'],'connection_id':'old-connection',
        'model':'fixture-model','model_provider':'openai','reasoning_effort':'medium',
        'sandbox':'danger-full-access','approval_policy':'never'}
    records = {'identity.json':{'worker_id':'old-owned-worker','screen_pid':2**30},
        'state.json':{'worker_id':'old-owned-worker','session_id':SID,'worker_pid':2**30+1,'status':'READY'},
        'startup.json':retained, 'bootstrap.json':{'codex_binary':str(f['codex_binary']),
         'codex_home':f['environment'].get('CODEX_HOME'),'request':f['request']},
        'failed.json':{'status':'MISMATCH','error':'startup_changed:model'}}
    for name,value in records.items():atomic_json(old/name,value)
    (old/'worker.lock').touch()
    original_contract={key:copy.deepcopy(f['request'].get(key)) for key in ('original_goal','scope','acceptance','context','authority')}
    f['request']['context']['adopted_original_contract']=original_contract
    adoption={'session_id':SID,'old_name':'old','old_pins':{name:hashlib.sha256((old/name).read_bytes()).hexdigest() for name in records}}
    return old,adoption


class Guard:
    def __init__(self):self.held=False;self.phases=[];self.fail=None
    @contextlib.contextmanager
    def __call__(self, request, adoption):
        self.held=True
        try:
            def check(query):
                assert self.held
                phase=query['phase'];self.phases.append(phase)
                return {**query,'observed_at':time.time(),'owner_exclusion_held':True,
                    'owner_exclusion_token':'fixture-controller-lock','session_id':SID,
                    'old_owned_lineage_absent':True,'terminal_effects_reconciled':phase!=self.fail,
                    'terminal_turn_id':'fixture-terminal-turn','evidence_ref':'synthetic-live-owner-check',
                    'source_writer_state':'FREE' if phase=='before_transport' else 'NEW_WORKER_OWNED',
                    'new_worker_sha256':digest(query['new_worker']) if query['new_worker'] is not None else None}
            yield check
        finally:self.held=False


def configure_adoption(f):
    f['request']['executor']['approved_sandbox']='danger-full-access'
    path=f['codex_binary'];text=path.read_text().replace("'sandbox_mode':'workspace-write'","'sandbox_mode':'danger-full-access'")
    text=text.replace("elif method=='thread/start':", "elif method in {'thread/start','thread/resume'}:\n  if method=='thread/resume': assert m['params']=={'threadId':'"+SID+"','excludeTurns':True}")
    text=text.replace("{'type':'workspaceWrite','networkAccess':True}","{'type':'dangerFullAccess'}")
    path.write_text(text)


def test_adoption_actual_synthetic_mailbox_resume_probe_dispatch_and_sid_once(screen_fixture):
    f=screen_fixture;configure_adoption(f);old,adoption=old_registry(f);guard=Guard();claims=[]
    call={**f,'adoption':adoption,'adoption_guard':guard,'dispatch_claim':lambda:claims.append(guard.held)}
    result=adopt_screen(**call)
    assert result['session_id']==SID and result['work']['status']=='completed'
    assert result['startup']['model_metadata_source']=='thread_resume_response'
    assert claims==[True] and not guard.held
    assert guard.phases==['before_transport','before_resume','before_dispatch','before_dispatch']
    for name,pin in adoption['old_pins'].items():assert hashlib.sha256((old/name).read_bytes()).hexdigest()==pin
    f['request']['launch_id']='another-launch-cannot-bypass-sid'
    with pytest.raises(LaunchError,match='adoption_sid_requires_reconciliation'):adopt_screen(**call)


def test_adoption_live_pid_despite_free_lock_blocks_before_new_transport(screen_fixture):
    f=screen_fixture;configure_adoption(f);old,adoption=old_registry(f)
    state=json.loads((old/'state.json').read_text());state['worker_pid']=os.getpid();atomic_json(old/'state.json',state)
    adoption['old_pins']['state.json']=hashlib.sha256((old/'state.json').read_bytes()).hexdigest()
    with pytest.raises(LaunchError,match='adoption_old_worker_still_present'):_old_readback(f['home'],adoption)
    assert not (f['home']/'state/screen-workers/fixture').exists()


def test_adoption_guard_denial_before_resume_keeps_once_and_oldstate(screen_fixture):
    f=screen_fixture;configure_adoption(f);old,adoption=old_registry(f);guard=Guard();guard.fail='before_resume'
    with pytest.raises(LaunchError,match='adoption_live_reconciliation_required'):
        adopt_screen(**f,adoption=adoption,adoption_guard=guard,dispatch_claim=lambda:pytest.fail('claim'))
    journal=json.loads((f['home']/('state/screen-adoptions/'+SID+'.json')).read_text())
    assert journal['resume_may_have_started'] is False and journal['status']=='RECONCILIATION_REQUIRED'
    for name,pin in adoption['old_pins'].items():assert hashlib.sha256((old/name).read_bytes()).hexdigest()==pin
    with pytest.raises(LaunchError,match='adoption_sid_requires_reconciliation'):
        adopt_screen(**f,adoption=adoption,adoption_guard=guard,dispatch_claim=lambda:None)


@pytest.mark.parametrize('malformed',[[],None,'bad-thread'])
def test_adoption_malformed_resume_retains_unknown_no_work(tmp_path,malformed):
    request,rpc,retained,response=profile(tmp_path);provider=CodexLaunchProvider(rpc)
    provider.describe_adoption(request,retained,'attempt');response['thread']=malformed
    with pytest.raises(LaunchError) as error:provider.resume(request,retained,'attempt')
    assert error.value.status=='UNKNOWN' and error.value.receipt['startup']['resume_may_have_started'] is True
    assert all(m!='turn/start' for m,_ in rpc.calls)


def test_adoption_unknown_resume_blocks_even_new_name_and_operation(screen_fixture,monkeypatch):
    from agent_os.screen_launch import ScreenLaunchProvider
    f=screen_fixture;configure_adoption(f);old,adoption=old_registry(f);guard=Guard()
    def fail(*args,**kwargs):raise LaunchError('synthetic_response_lost',status='UNKNOWN')
    monkeypatch.setattr(ScreenLaunchProvider,'resume',fail)
    with pytest.raises(LaunchError):adopt_screen(**f,adoption=adoption,adoption_guard=guard,dispatch_claim=lambda:pytest.fail('claim'))
    journal=json.loads((f['home']/('state/screen-adoptions/'+SID+'.json')).read_text())
    assert journal['resume_may_have_started'] is True and not guard.held
    f['name']='different-name';f['request']['launch_id']='different-launch'
    with pytest.raises(LaunchError,match='adoption_sid_requires_reconciliation'):
        adopt_screen(**f,adoption=adoption,adoption_guard=guard,dispatch_claim=lambda:pytest.fail('claim'))
    assert not (f['home']/'state/screen-workers/different-name').exists()


def test_adoption_substituted_original_goal_rejected_before_worker(screen_fixture):
    f=screen_fixture;configure_adoption(f);old,adoption=old_registry(f)
    f['request']['context']['adopted_original_contract']['original_goal']='replacement-goal'
    with pytest.raises(LaunchError,match='adoption_original_contract_not_retained'):
        adopt_screen(**f,adoption=adoption,adoption_guard=Guard(),dispatch_claim=lambda:None)
    assert not (f['home']/'state/screen-workers/fixture').exists()


def test_adoption_rejected_resume_retains_actual_foreign_sid_and_expected(tmp_path):
    request,rpc,retained,response=profile(tmp_path);provider=CodexLaunchProvider(rpc)
    provider.describe_adoption(request,retained,'attempt')
    foreign='01a0a2b6-522a-7501-9a78-c093c781141f'
    response.update(thread={'id':foreign},sandbox={'type':'workspaceWrite','writableRoots':['PRIVATE_FIXTURE']})
    with pytest.raises(LaunchError) as error:provider.resume(request,retained,'attempt')
    rejected=error.value.receipt['startup']
    assert rejected['session_id']==foreign and rejected['expected_session_id']==SID
    assert rejected['sandbox']=='workspace-write' and 'PRIVATE_FIXTURE' not in json.dumps(rejected)


def test_adoption_oversized_old_pin_refuses_before_transport(screen_fixture):
    f=screen_fixture;configure_adoption(f);old,adoption=old_registry(f)
    path=old/'failed.json'
    with path.open('wb') as stream:stream.truncate(1024*1024*1024)
    with pytest.raises(LaunchError,match='adoption_old_pin_input_limit'):_old_readback(f['home'],adoption)
    assert not (f['home']/'state/screen-workers/fixture').exists()


def test_adoption_aggregate_pin_budget_refuses(screen_fixture):
    f=screen_fixture;configure_adoption(f);old,adoption=old_registry(f)
    for i in range(5):
        path=old/('extra'+str(i)+'.json');path.write_bytes(b'x'*(128*1024))
        adoption['old_pins'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(LaunchError,match='adoption_old_pin_input_limit'):_old_readback(f['home'],adoption)


def test_adoption_rejected_resume_persists_actual_identity_in_worker(screen_fixture):
    f=screen_fixture;configure_adoption(f);old,adoption=old_registry(f)
    path=f['codex_binary'];text=path.read_text();foreign='01a0a2b6-522a-7501-9a78-c093c781141f'
    text=text.replace("  if mode=='missing-actual-provider':", "  if method=='thread/resume': result.update(thread={'id':'"+foreign+"'},sandbox={'type':'workspaceWrite','writableRoots':['PRIVATE_FIXTURE']})\n  if mode=='missing-actual-provider':")
    path.write_text(text)
    with pytest.raises(LaunchError):
        adopt_screen(**f,adoption=adoption,adoption_guard=Guard(),dispatch_claim=lambda:pytest.fail('claim'))
    rejected=json.loads((f['home']/'state/screen-workers/fixture/rejected-startup.json').read_text())
    assert rejected['session_id']==foreign and rejected['expected_session_id']==SID
    assert 'PRIVATE_FIXTURE' not in json.dumps(rejected)
    assert (f['home']/('state/screen-adoptions/'+SID+'.json')).exists()


def test_adoption_postresume_read_timeout_preserves_safe_actual_startup(tmp_path):
    request,rpc,retained,response=profile(tmp_path);provider=CodexLaunchProvider(rpc)
    provider.describe_adoption(request,retained,'attempt');original=rpc.call
    def timeout(method,params,**kwargs):
        if method=='config/read':raise TimeoutError('PRIVATE_FIXTURE_PROVIDER_TEXT')
        return original(method,params,**kwargs)
    rpc.call=timeout
    with pytest.raises(LaunchError) as error:provider.resume(request,retained,'attempt')
    assert error.value.status=='UNKNOWN' and error.value.code=='resume_current_readback_unavailable'
    actual=error.value.receipt['startup']
    assert actual['session_id']==SID and actual['expected_session_id']==SID
    assert actual['model']=='fixture-model' and actual['sandbox']=='danger-full-access'
    assert actual['approval_policy']=='never' and actual['model_metadata_source']=='thread_resume_response'
    assert 'PRIVATE_FIXTURE' not in json.dumps(error.value.receipt)
