"""Exact late PROBE/pre-WORK fixtures; no native sessions or live registry."""
import contextlib
import copy
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agent_os.codex_launch import _commands
from agent_os.safeio import atomic_json, digest, GateError
from agent_os.screen_adoption import adopt_screen
from agent_os.screen_late_probe import (FLAGS, reconcile_late_probe, select_late_probe,
                                        verify_late_probe, history_root, _paths)
from agent_os.screen_successor import _edge
from agent_os.session_launch import LaunchError
from test_screen_launch import screen_fixture
from test_screen_successor import case as successful_parent
from test_screen_reconciliation import pin, SID
from test_screen_adoption import Guard

OP = '11111111-2222-3333-4444-555555555555'
ATTEMPT = '22222222-3333-4444-5555-666666666666'
TURN = 'late-probe-turn'


def case(f):
    source, previous, root = successful_parent(f)
    request = copy.deepcopy(f['request'])
    original = copy.deepcopy(previous)
    old = f['home'] / 'state/screen-workers/failed-probe'
    boot = {'request': request, 'codex_binary': str(f['codex_binary']),
            'codex_home': f['environment'].get('CODEX_HOME'),
            'adoption_retained_startup': json.loads((source / 'startup.json').read_text())}
    identity = {'schema': 'agentos.screen-worker/v1', 'name': 'failed-probe', 'worker_id': 'failed-worker',
                'screen_pid': 2**30+10, 'request_sha256': digest(request), 'bootstrap_sha256': digest(boot)}
    startup = dict(boot['adoption_retained_startup'], connection_id='failed-connection', attempt_id=ATTEMPT)
    state = dict(identity, status='FAILED', worker_pid=2**30+11, connection_id='failed-connection',
                 session_id=SID, operation='probe', operation_id=OP)
    message = {'id': OP, 'operation': 'probe', 'worker_id': identity['worker_id'],
               'connection_id': state['connection_id'], 'payload': {'request': request, 'startup': startup, 'attempt': ATTEMPT}}
    response = {'id': OP, 'worker_id': identity['worker_id'], 'connection_id': state['connection_id'],
                'request_sha256': digest(message), 'status': 'UNKNOWN', 'error': 'screen_provider_TimeoutError'}
    values = {'identity.json': identity, 'bootstrap.json': boot, 'startup.json': startup, 'state.json': state,
              'request.json': message, 'pending.json': {'operation': 'probe', 'operation_id': OP,
                'request_sha256': digest(message), 'status': 'PENDING'}, 'responses/'+OP+'.json': response}
    for n, v in values.items(): atomic_json(old/n, v)
    failed = {'schema': 'agentos.screen-adoption-successor/v1', 'session_id': SID,
              'status': 'RECONCILIATION_REQUIRED', 'resume_may_have_started': True, 'work_accepted': False,
              'request_sha256': digest(request), 'adoption_sha256': digest(original),
              'successor': {'predecessor_sha256': pin(root), 'destination_name': identity['name']},
              'before_resume': {'attempt_id': ATTEMPT, 'request_sha256': digest(request),
                                'adoption_sha256': digest(original), 'new_worker': state}}
    edge = _edge(f['home'], SID, pin(root)); atomic_json(edge, failed)
    launchpath = f['home']/'state/session-launch'/(digest(request['launch_id'])+'.json')
    launch = {'schema': 'agentos.session-launch-receipt/v1', 'attempt_id': ATTEMPT, 'request_sha256': digest(request),
              'session_id': SID, 'status': 'UNKNOWN', 'phase': 'STOPPED', 'provider_mutation_started': True,
              'work_accepted': False, 'error': response['error'], 'startup': startup,
              'trace': ['ADMITTED_FOR_STARTUP_ONLY', 'CREATING', 'STARTUP_READBACK_VERIFIED', 'STOPPED']}
    atomic_json(launchpath, launch)
    replacement = copy.deepcopy(request); replacement.update(launch_id='late-probe-fresh-launch', probe_budget_seconds=180)
    contract = {k: request.get(k) for k in ('original_goal','scope','acceptance','context','authority')}
    replacement['context']['adopted_original_contract'] = contract
    actor = {'session_id': 'old-owner', 'turn_id': 'old-turn', 'task_id': 'old-task'}
    claim = f['home']/'state/dispatch'/(digest([actor['session_id'],actor['turn_id']])+'.json')
    proof = {'schema': 'agentos.late-probe-evidence/v1', 'session_id': SID, 'operation_id': OP, 'turn_id': TURN,
             'attempt_id': ATTEMPT, 'worker_id': identity['worker_id'], 'connection_id': state['connection_id'],
             'request_sha256': digest(request), 'native_status': 'completed', 'coverage': 'COMPLETE',
             'cleanup_complete': True, 'native_work_count': 0, 'claim_state': 'ABSENT', 'claim_path': str(claim),
             'dispatch_binding_sha256': digest(actor), 'commands': [
                {'id': cap, 'command': script, 'cwd': request['workspace'], 'status': 'completed',
                 'exit_code': 0, 'output': marker+'\n', 'output_truncated': False}
                for cap, (script, marker) in _commands(request, ATTEMPT).items()],
             'execution_code_pins': {n:'a'*64 for n in ['screen_launch.py','codex_launch.py','screen_adoption.py','session_launch.py']},
             'source_refs': [{'ref': 'exact-native-probe-observation', 'sha256': 'b'*64}]}
    proofpath = f['home']/'evidence/late-probe.json'; atomic_json(proofpath, proof)
    plan = {'schema': 'agentos.late-probe-request/v1', 'session_id': SID, 'operation_id': OP, 'turn_id': TURN,
            'failed_adoption': original, 'failed_adoption_sha256': pin(edge), 'failed_worker_name': identity['name'],
            'failed_launch_sha256': pin(launchpath), 'replacement_name': f['name'], 'replacement_request': replacement,
            'worker_pins': {n:pin(old/n) for n in values}, 'dispatch_binding': actor,
            'probe_evidence': {'path': str(proofpath), 'sha256': pin(proofpath)}}
    return plan, edge, launchpath, old, proofpath, claim


class Review:
    def __init__(self, mutate=None, **overrides): self.mutate, self.overrides = mutate, overrides
    @contextlib.contextmanager
    def __call__(self, plan):
        def check(q):
            if self.mutate: self.mutate(plan)
            return {**q, **{k:True for k in FLAGS}, 'observed_at':time.time(), 'owner_exclusion_token':'held-owner',
                    'reviewer':'synthetic-root', 'evidence_ref':'native-and-effect-review', **self.overrides}
        yield check


class LiveGuard(Guard):
    def __init__(self, **overrides): super().__init__(); self.overrides = overrides
    @contextlib.contextmanager
    def __call__(self, request, adoption):
        with super().__call__(request, adoption) as check:
            yield lambda q: {**check(q), 'late_probe_binding_sha256':digest(q['late_probe_binding']),
                'terminal_turn_id':TURN, 'late_probe_effects_only_verified':True,
                'both_owned_lineages_absent':True, 'fresh_same_connection_probes_required':True,
                'current_target_security_verified':True, **self.overrides}


def adopt(plan, ref):
    return {'session_id':SID, 'old_name':plan['failed_worker_name'], 'old_pins':plan['worker_pins'], 'late_probe_recovery':ref}


def test_once_continuation_fresh_probe_preserves_failed_lineages(screen_fixture):
    f=screen_fixture; plan, edge, launch, old, proof, claim = case(f)
    originals={p:p.read_bytes() for p in [edge,launch,*old.rglob('*.json')]}
    ref=reconcile_late_probe(f['home'],plan,owning_guard=Review()); adoption=adopt(plan,ref)
    receipt,_,_=verify_late_probe(f['home'],adoption)
    assert receipt['old_probe_accepted'] is False and receipt['work_replay_authorized'] is False
    selected=select_late_probe(f['home'],f['name'],plan['replacement_request'],adoption)
    claims=[]
    result=adopt_screen(**dict(f,request=plan['replacement_request']),adoption=adoption,
                        adoption_guard=LiveGuard(),dispatch_claim=lambda:claims.append(True))
    assert claims==[True] and result['session_id']==SID and result['work']['delivery']=='accepted'
    assert result['probe']['status']=='PASS' and result['probe']['attempt_id'] != ATTEMPT
    assert result['startup']['connection_id'] != json.loads((old/'startup.json').read_text())['connection_id']
    assert result['startup']['model']==json.loads((old/'startup.json').read_text())['model']
    assert all(p.read_bytes()==raw for p,raw in originals.items()) and not claim.exists()
    node=json.loads(selected.journal.read_text()); assert node['status']=='DISPATCH_OBSERVED'
    path,pins=history_root(f['home'],{'session_id':SID,'late_probe_history':ref});assert path==selected.journal and pins
    with pytest.raises(LaunchError,match='attempt_already_reserved'):
        select_late_probe(f['home'],f['name'],plan['replacement_request'],adoption)


@pytest.mark.parametrize('kind',['status','operation','operation_id','pending','foreign_worker','foreign_connection','attempt','launchtrace','work','claim','command','nonce','cwd','exit','cleanup','inflight','extra_command','provenance'])
def test_unqualified_late_probe_refuses(screen_fixture,kind):
    f=screen_fixture;plan,edge,launch,old,proofpath,claim=case(f)
    name='state.json'; value=json.loads((old/name).read_text()); proof=json.loads(proofpath.read_text())
    if kind=='status': value['status']='BUSY'
    elif kind=='operation': value['operation']='dispatch'
    elif kind=='operation_id': value['operation_id']='33333333-4444-5555-6666-777777777777'
    elif kind=='pending': name='pending.json';value=json.loads((old/name).read_text());value['operation']='dispatch'
    elif kind=='foreign_worker': value['worker_id']='foreign'
    elif kind=='foreign_connection': value['connection_id']='foreign'
    elif kind=='attempt': name='startup.json';value=json.loads((old/name).read_text());value['attempt_id']='foreign'
    elif kind=='launchtrace': v=json.loads(launch.read_text());v['trace'].insert(-1,'DISPATCHING');atomic_json(launch,v);plan['failed_launch_sha256']=pin(launch)
    elif kind=='work': v=json.loads(edge.read_text());v['before_dispatch']={};atomic_json(edge,v);plan['failed_adoption_sha256']=pin(edge)
    elif kind=='claim': atomic_json(claim,{'status':'CLAIMED'})
    elif kind=='command': proof['commands'][0]['command']='echo arbitrary'
    elif kind=='nonce': proof['commands'][0]['output']='foreign\n'
    elif kind=='cwd': proof['commands'][0]['cwd']='/foreign'
    elif kind=='exit': proof['commands'][0]['exit_code']=1
    elif kind=='cleanup': proof['cleanup_complete']=False
    elif kind=='inflight': proof['native_status']='inProgress'
    elif kind=='extra_command': proof['commands'].append(proof['commands'][0])
    elif kind=='provenance': proof['source_refs']=[]
    if kind in ['status','operation','operation_id','pending','foreign_worker','foreign_connection','attempt']:
        atomic_json(old/name,value);plan['worker_pins'][name]=pin(old/name)
    atomic_json(proofpath,proof);plan['probe_evidence']['sha256']=pin(proofpath)
    with pytest.raises(LaunchError): reconcile_late_probe(f['home'],plan,owning_guard=Review())


@pytest.mark.parametrize('kind',['source_live','failed_live','source_lock','failed_lock','unknown_predecessor','stale_tip','foreign_adoption','changed_scope'])
def test_ancestry_quiescence_and_request_binding(screen_fixture,kind):
    f=screen_fixture;plan,edge,_,old,_,_=case(f)
    if kind=='source_live':
        source=f['home']/'state/screen-workers/old';state=json.loads((source/'state.json').read_text());state['worker_pid']=os.getpid();atomic_json(source/'state.json',state)
        plan['failed_adoption']['old_pins']['state.json']=pin(source/'state.json')
        v=json.loads(edge.read_text());v['adoption_sha256']=digest(plan['failed_adoption']);atomic_json(edge,v);plan['failed_adoption_sha256']=pin(edge)
    elif kind=='failed_live':
        state=json.loads((old/'state.json').read_text());state['worker_pid']=os.getpid();atomic_json(old/'state.json',state);plan['worker_pins']['state.json']=pin(old/'state.json')
        v=json.loads(edge.read_text());v['before_resume']['new_worker']['worker_pid']=os.getpid();atomic_json(edge,v);plan['failed_adoption_sha256']=pin(edge)
    elif kind in ['source_lock','failed_lock']:
        p=(f['home']/'state/screen-workers/old' if kind=='source_lock' else old)/'worker.lock';p.mkdir()
    elif kind=='unknown_predecessor':
        root=f['home']/'state/screen-adoptions'/(SID+'.json');v=json.loads(root.read_text());v['status']='UNKNOWN';atomic_json(root,v)
    elif kind=='stale_tip': plan['failed_adoption_sha256']='a'*64
    elif kind=='foreign_adoption': plan['failed_adoption']['old_name']='foreign'
    elif kind=='changed_scope':plan['replacement_request']['scope']='foreign'
    with pytest.raises(LaunchError): reconcile_late_probe(f['home'],plan,owning_guard=Review())


@pytest.mark.parametrize('override',[{'native_evidence_verified':False},{'owner_exclusion_held':False},{'observed_at':0},{'current_target_security_verified':False}])
def test_held_review_required(screen_fixture,override):
    f=screen_fixture;plan,*_=case(f)
    with pytest.raises(LaunchError,match='owning_review_not_bound'):
        reconcile_late_probe(f['home'],plan,owning_guard=Review(**override))


def test_guard_mutation_refuses_and_receipt_source_change_refuses(screen_fixture):
    f=screen_fixture;plan,_,_,_,proof,_=case(f)
    with pytest.raises(LaunchError,match='owning_review_not_bound'):
        reconcile_late_probe(f['home'],plan,owning_guard=Review(mutate=lambda p:p['replacement_request'].update(scope='foreign')))
    ref=reconcile_late_probe(f['home'],plan,owning_guard=Review())
    proof.write_text('{}')
    with pytest.raises(LaunchError): select_late_probe(f['home'],f['name'],plan['replacement_request'],adopt(plan,ref))


def test_publication_race_has_one_receipt_and_no_retry(screen_fixture):
    f=screen_fixture;plan,*_=case(f);barrier=threading.Barrier(2)
    def run():
        barrier.wait()
        try:return reconcile_late_probe(f['home'],plan,owning_guard=Review())
        except GateError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
    assert sum(x is not None for x in results)==1
    with pytest.raises(LaunchError):reconcile_late_probe(f['home'],plan,owning_guard=Review())


def test_live_security_refusal_precedes_transport(screen_fixture):
    f=screen_fixture;plan,*_=case(f);ref=reconcile_late_probe(f['home'],plan,owning_guard=Review())
    with pytest.raises(LaunchError,match='late_probe_live_review_not_bound'):
        adopt_screen(**dict(f,request=plan['replacement_request']),adoption=adopt(plan,ref),
            adoption_guard=LiveGuard(current_target_security_verified=False),dispatch_claim=lambda:pytest.fail('claim'))
    assert not (f['home']/'state/screen-workers'/f['name']).exists()


@pytest.mark.parametrize('kind',['foreign_schema','malformed_link'])
def test_failed_journal_schema_and_link_controlled_refusal(screen_fixture,kind):
    f=screen_fixture;plan,edge,*_=case(f)
    row=json.loads(edge.read_text())
    if kind=='foreign_schema':row['schema']='foreign'
    else:row['successor']=None
    atomic_json(edge,row);plan['failed_adoption_sha256']=pin(edge)
    with pytest.raises(LaunchError):reconcile_late_probe(f['home'],plan,owning_guard=Review())


def test_old_terminal_probe_never_substitutes_for_fresh_failed_probe(screen_fixture):
    f=screen_fixture;plan,*_=case(f);ref=reconcile_late_probe(f['home'],plan,owning_guard=Review())
    f['environment']['FIXTURE_MODE']='ack'
    with pytest.raises(LaunchError,match='harmless_probe_failed'):
        adopt_screen(**dict(f,request=plan['replacement_request']),adoption=adopt(plan,ref),
            adoption_guard=LiveGuard(),dispatch_claim=lambda:pytest.fail('claim before fresh probe'))
    _,attempt=_paths(f['home'],SID,plan['failed_adoption_sha256'])
    assert json.loads(attempt.read_text())['status']=='RECONCILIATION_REQUIRED'
    assert not (Path(plan['replacement_request']['workspace'])/'fixture-business.jsonl').exists()
    with pytest.raises(LaunchError,match='attempt_already_reserved'):
        select_late_probe(f['home'],f['name'],plan['replacement_request'],adopt(plan,ref))


@pytest.mark.parametrize('status',['BUSY','STARTING'])
def test_late_probe_continuation_requires_ready_destination(screen_fixture,status):
    f=screen_fixture;plan,*_=case(f);ref=reconcile_late_probe(f['home'],plan,owning_guard=Review())
    class NotReady(LiveGuard):
        @contextlib.contextmanager
        def __call__(self,request,adoption):
            with super().__call__(request,adoption) as check:
                def observe(q):
                    if q['new_worker'] is not None:q['new_worker']['status']=status
                    return check(q)
                yield observe
    with pytest.raises(LaunchError,match='late_probe_live_review_not_bound'):
        adopt_screen(**dict(f,request=plan['replacement_request']),adoption=adopt(plan,ref),
            adoption_guard=NotReady(),dispatch_claim=lambda:pytest.fail('claim without READY'))
    assert not (Path(plan['replacement_request']['workspace'])/'fixture-business.jsonl').exists()
