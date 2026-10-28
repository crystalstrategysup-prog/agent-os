"""Typed same-task interrupted/completed-turn continuation; never accepts product work.

The selected observer must query an existing supported metadata-only provider.
An arbitrary callback, a saved report, or this local receipt is not authority.
Human permission remains owner-attested, not authenticated by this core.
"""
from __future__ import annotations
import base64
import copy
import json
import re
import time
from datetime import datetime, timezone
from contextlib import nullcontext
from pathlib import Path
from .safeio import GateError, atomic_bytes, atomic_json, lock, sha, within
from .task_metadata import limit as task_metadata_limit
from .turns import turn_path
from . import refusal_recovery as rr

SCHEMA='agentos.interrupted-continuation-request/v1'
INTERRUPTED_HISTORY_SCHEMA='agentos.interrupted-continuation-request/v2'
RECEIPT='agentos.interrupted-continuation-receipt/v1'
COMPLETED_SCHEMA='agentos.completed-continuation-request/v1'
COMPLETED_HISTORY_SCHEMA='agentos.completed-continuation-request/v2'
COMPLETED_RECEIPT='agentos.completed-continuation-receipt/v1'
MAX_JOURNAL=24*1024*1024
# Fixed supported observer capacity v2. This changes pagination, never authority.
OBSERVER_TURN_LIMIT=1
OBSERVER_MAX_PAGES=40
OBSERVER_MAX_TURNS=40
OBSERVER_MAX_RESPONSE=4*1024*1024
OBSERVER_MAX_TOTAL_RESPONSE=16*1024*1024
OBSERVER_CALL_SECONDS=45
OBSERVER_TOTAL_SECONDS=120
METADATA_WIRE_LIMIT=64*1024


def provider_encoded(value):
    """Full provider envelope size boundary, before projection; never persist."""
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')


def metadata_page(value):
    """Strict, body-free projection. Not an authenticator of the caller/tool."""
    if not isinstance(value,dict):fail('provider_response')
    if 'isError'in value and type(value['isError'])is not bool:fail('provider_response')
    if value.get('isError')is True:return {'isError':True}
    if 'content'in value:
        content=value['content']
        if not isinstance(content,list)or any(not isinstance(x,dict)for x in content):fail('provider_response')
        texts=[x.get('text')for x in content if x.get('type')=='text']
        if len(texts)!=1 or not isinstance(texts[0],str):fail('provider_response')
        value=rr.parse(texts[0].encode('utf-8'))
    if not isinstance(value,dict):fail('provider_response')
    thread=value.get('thread');turns=value.get('turns');page=value.get('page',{})
    if not isinstance(thread,dict)or not isinstance(turns,list)or len(turns)>OBSERVER_TURN_LIMIT or not isinstance(page,dict):fail('provider_response')
    for key in ['id','cwd']:
        if not isinstance(thread.get(key),str)or not thread[key]or len(thread[key])>4096:fail('provider_response')
    selected=[]
    for turn in turns:
        if not isinstance(turn,dict):fail('provider_response')
        if any(not isinstance(turn.get(k),str)or not turn[k]or len(turn[k])>200 for k in ['id','status']):fail('provider_response')
        selected.append({k:turn[k]for k in ['id','status']})
    more=page.get('hasMore',False);cursor=page.get('nextCursor')if more else None
    if type(more)is not bool:fail('provider_pagination')
    if more and (not isinstance(cursor,str)or not cursor or len(cursor)>2048):fail('provider_pagination')
    return {'isError':False,'thread':{k:thread[k]for k in ['id','cwd']},'turns':selected,'page':{'hasMore':more,'nextCursor':cursor}}


class ProviderMetadataEnvelope:
    """Selected bridge's size attestation, not cryptographic provenance proof."""
    def __init__(self,metadata,original_response_bytes):
        if type(original_response_bytes)is not int or not 0<original_response_bytes<=OBSERVER_MAX_RESPONSE:fail('provider_response_limit')
        if metadata_page(metadata)!=metadata:fail('provider_metadata_projection')
        self.metadata=metadata;self.original_response_bytes=original_response_bytes

def completed(r):return r.get('schema')in {COMPLETED_SCHEMA,COMPLETED_HISTORY_SCHEMA}
def history_request(r):return r.get('schema')in {COMPLETED_HISTORY_SCHEMA,INTERRUPTED_HISTORY_SCHEMA}
def receipt_schema(r):
    if history_request(r):return 'agentos.completed-continuation-receipt/v2' if completed(r) else 'agentos.interrupted-continuation-receipt/v2'
    return COMPLETED_RECEIPT if completed(r) else RECEIPT
def authority_schema(r):return 'agentos.completed-continuation-authority/v1' if completed(r) else 'agentos.interrupted-continuation-authority/v1'


def fail(code):
    raise GateError('interrupted_continuation_'+code)


def encoded(value):
    return (json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode()


def read(path,limit=rr.MAX_METADATA):
    return rr._read(path,limit)


def stamp(value):
    return rr.stamp(value)


def age(value):
    seconds=(datetime.now(timezone.utc)-stamp(value)).total_seconds()
    if not 0<=seconds<=120:fail('stale_observation')


def marker(root):return within(root,'.agentos/interrupted-continuation-pending.json')


def require_clear(root):
    if marker(root).exists():fail('pending_reconcile_required')


def area(root,request):
    return within(root,f".agentos/tasks/{request['task_id']}/interrupted-continuation/{request['operation_id']}")


def validate_request(root,home,r):
    fields='schema operation_id root user_home project_id task_id revision session_id native_thread_id native_mapping previous_turn current_turn actor_id expected goal_sha256'
    if isinstance(r,dict)and history_request(r):fields+=' accepted_checkpoint_history_sha256'
    rr.keys(r,fields)
    if r['schema']not in {SCHEMA,INTERRUPTED_HISTORY_SCHEMA,COMPLETED_SCHEMA,COMPLETED_HISTORY_SCHEMA} or r['root']!=str(root.resolve()) or r['user_home']!=str(home.resolve()):fail('request_identity')
    if history_request(r):rr.digest(r['accepted_checkpoint_history_sha256'])
    rr.op(r['operation_id']);rr.ident(r['task_id'],r'task-[0-9a-f]{16}')
    for k in ['project_id','session_id','native_thread_id','previous_turn','current_turn','actor_id']:rr.short(r[k])
    if type(r['revision'])is not int or r['revision']<1 or r['previous_turn']==r['current_turn'] or r['actor_id']!=r['native_thread_id']:fail('actor_or_turn')
    rr.keys(r['native_mapping'],'native_cwd workflow_session_id bound_turn_id task_sha256 turn_sha256 evidence_ref')
    rr.canonical(r['native_mapping']['native_cwd']);rr.short(r['native_mapping']['evidence_ref'])
    rr.keys(r['expected'],'project_sha256 task_sha256 turn_sha256 events_sha256 source_sha256')
    for v in r['expected'].values():rr.digest(v)
    rr.digest(r['goal_sha256'])
    if len(encoded(r))>rr.MAX_DOCUMENT:fail('request_limit')


def validate_authority(r,a,*,reconciling=False):
    rr.keys(a,'schema request_sha256 actor_id session_id current_turn root task_id decision_ref decision_sha256 valid_from valid_until revoked')
    if a['schema']!=authority_schema(r) or a['revoked']is not False or a['request_sha256']!=sha(encoded(r)):fail('authority')
    for k in ['actor_id','session_id','root','task_id']:
        if a[k]!=r[k]:fail('authority_identity')
    rr.short(a['current_turn'])
    if not reconciling and a['current_turn']!=r['current_turn']:fail('authority_identity')
    rr.short(a['decision_ref']);rr.digest(a['decision_sha256'])
    now=datetime.now(timezone.utc)
    if not stamp(a['valid_from'])<=now<=stamp(a['valid_until']):fail('authority_expired')
    if (stamp(a['valid_until'])-stamp(a['valid_from'])).total_seconds()>900:fail('authority_window')


def validate_mapping(root,r):
    # No invented registry. The exact existing workflow task/binding previous
    # turn joins to the same old turn returned by the actual native provider.
    m=r['native_mapping']
    if (m['workflow_session_id']!=r['session_id']or m['bound_turn_id']!=r['previous_turn']
        or m['task_sha256']!=r['expected']['task_sha256']or m['turn_sha256']!=r['expected']['turn_sha256']):fail('mapping_identity')


def observe(r,observer,*,current_turn=None,bound_current=None):
    if observer is None or not callable(getattr(observer,'read_turn_metadata',None)):fail('supported_observer_unavailable')
    current_turn=current_turn or r['current_turn'];bound_current=bound_current or r['current_turn']
    v=observer.read_turn_metadata(copy.deepcopy(r),sha(encoded(r)),current_turn=current_turn,bound_current=bound_current)
    rr.keys(v,'schema source request_sha256 session_id native_thread_id native_cwd previous current bound_current observed_at observation_ref')
    if v['schema']!='agentos.provider-turn-metadata/v1' or v['source']!='supported_read_thread' or v['request_sha256']!=sha(encoded(r)) or v['session_id']!=r['session_id'] or v['native_thread_id']!=r['native_thread_id'] or v['native_cwd']!=r['native_mapping']['native_cwd']:fail('provider_identity')
    for k in ['previous','current','bound_current']:rr.keys(v[k],'id status')
    expected_status='completed' if completed(r) else 'interrupted'
    if v['previous']!={'id':r['previous_turn'],'status':expected_status}:fail('old_writer_not_'+expected_status)
    if v['current']!={'id':current_turn,'status':'inProgress'}:fail('current_writer_not_active')
    if v['bound_current']['id']!=bound_current:fail('reconcile_writer_identity')
    if bound_current!=current_turn and v['bound_current']['status']not in {'completed','interrupted'}:fail('previous_continuation_writer_not_inactive')
    if bound_current==current_turn and v['bound_current']['status']!='inProgress':fail('current_writer_not_active')
    age(v['observed_at']);rr.short(v['observation_ref'])
    return v


def paths(root,home,r):
    return {'project':within(root,'.agentos/project.json'),'task':within(root,f".agentos/tasks/{r['task_id']}/task.json"),'turn':turn_path(home,r['session_id']),'events':within(root,f".agentos/tasks/{r['task_id']}/events.jsonl")}


def source(root):
    from .project import source_snapshot
    return source_snapshot(root)['sha256']


def stable_history(home,r):
    if history_request(r):
        from .accepted_checkpoint_history import library_read_lock
        return library_read_lock(home)
    return nullcontext()


def guard_history(root,home,r):
    if history_request(r):
        from .accepted_checkpoint_history import qualify
        result=qualify(root,home,task_id=r['task_id'],project_id=r['project_id'],revision=r['revision'])
        if result['sha256']!=r['accepted_checkpoint_history_sha256']:fail('accepted_history_changed')
    else:rr._reject_handoff_journals(root,r['task_id'])


def guard(root,home,r):
    rr.require_clear(root)
    if within(root,'.agentos/entry-transaction.json').exists():fail('entry_pending')
    guard_history(root,home,r)


def validate_preimages(root,home,r,ps):
    validate_mapping(root,r)
    raw={k:read(p,task_metadata_limit(root) if k=='task' else rr.MAX_METADATA) for k,p in ps.items()}
    for k,v in raw.items():
        if sha(v)!=r['expected'][k+'_sha256']:fail('cas_'+k)
    p,t,b=[rr.parse(raw[k]) for k in ['project','task','turn']]
    if p.get('id')!=r['project_id'] or p.get('active_task')!=r['task_id'] or t.get('project_id')!=r['project_id'] or t.get('id')!=r['task_id'] or t.get('revision')!=r['revision']:fail('task_identity')
    if t.get('status') not in {'INTAKE','READY','VERIFYING'}:fail('task_state')
    if t.get('session_id')!=r['session_id'] or t.get('turn_id')!=r['previous_turn'] or t.get('handoff_user_home')!=str(home.resolve()):fail('task_actor')
    if b.get('schema')!='agentos.turn/v1' or b.get('session_id')!=r['session_id'] or b.get('turn_id')!=r['previous_turn'] or b.get('root')!=r['root'] or b.get('task_id')!=r['task_id'] or b.get('status')!='ENTERED':fail('binding')
    if sha(encoded(t['answers']))!=r['goal_sha256']:fail('goal_changed')
    if source(root)!=r['expected']['source_sha256']:fail('source_changed')
    return raw,p,t,b


def _receipt(r,a,observation,rows):
    return {'schema':receipt_schema(r),'operation_id':r['operation_id'],'task_id':r['task_id'],'revision':r['revision'],'request_sha256':sha(encoded(r)),
        'status':'FULL_ENTRY_REQUIRED','ready_granted':False,'semantic_acceptance':False,'original_goal':'OPEN',
        'authority_basis':'OWNER_ATTESTED_NOT_AUTHENTICATED_BY_CORE','authority_sha256':sha(encoded(a)),
        'current_turn':a['current_turn'],'provider_observation_sha256':sha(encoded(observation)),'preimages':{k:x['before_sha256'] for k,x in rows.items()},'postimages':{k:x['after_sha256'] for k,x in rows.items()}}


def _finish(root,home,r,j):
    if j.get('schema')!='agentos.interrupted-continuation-transaction/v1' or j.get('request')!=r:fail('journal_identity')
    ps=paths(root,home,r)
    rr.keys(j['rows'],'project task turn events')
    if j.get('receipt')!=_receipt(r,j['authority'],j['observation'],j['rows']):fail('journal_receipt_mismatch')
    # Validate every current image before writing any remaining image.
    post={}
    for k,row in j['rows'].items():
        rr.keys(row,'before after before_sha256 after_sha256 prior_after')
        before=base64.b64decode(row['before'],validate=True);after=base64.b64decode(row['after'],validate=True)
        cap=task_metadata_limit(root) if k=='task' else rr.MAX_METADATA
        if len(before)>cap or len(after)>cap:fail('metadata_limit')
        if sha(before)!=row['before_sha256'] or sha(after)!=row['after_sha256'] or row['before_sha256']!=r['expected'][k+'_sha256']:fail('journal_hash')
        if not isinstance(row['prior_after'],list)or len(row['prior_after'])>8:fail('journal_reconcile_limit')
        allowed={row['before_sha256'],row['after_sha256']}
        for prior in row['prior_after']:
            prior_raw=base64.b64decode(prior,validate=True)
            if len(prior_raw)>cap:fail('metadata_limit')
            allowed.add(sha(prior_raw))
        if sha(read(ps[k],task_metadata_limit(root) if k=='task' else rr.MAX_METADATA))not in allowed:fail('reconcile_conflict_'+k)
        post[k]=after
    if sha(read(ps['project']))!=r['expected']['project_sha256'] or source(root)!=r['expected']['source_sha256']:fail('reconcile_source_conflict')
    for k in ['task','turn','events']:
        if read(ps[k],task_metadata_limit(root) if k=='task' else rr.MAX_METADATA)!=post[k]:atomic_bytes(ps[k],post[k])
    for k in ['task','turn','events']:
        if read(ps[k],task_metadata_limit(root) if k=='task' else rr.MAX_METADATA)!=post[k]:fail('metadata_readback_failed')
    receipt=j['receipt'];destination=area(root,r)
    atomic_json(destination/'receipt.json',receipt)
    # Retain full preimages and initial observation, never replace old recovery.
    raw=read(marker(root),MAX_JOURNAL)
    historical=destination/'history'/ (sha(raw)+'.json')
    if not historical.exists():rr.write(historical,raw,root,only=True,readback_limit=MAX_JOURNAL)
    atomic_bytes(destination/'transaction.json',raw)
    marker(root).unlink();rr._sync(marker(root).parent)
    return receipt


def advance(root,home,r,a,*,observer=None):
    from .overlay import validate_roots
    root=root.resolve();home=home.resolve();validate_roots(home);validate_request(root,home,r);validate_authority(r,a)
    with lock(within(root,'.agentos/write.lock')),lock(within(home,'state/turns.lock')):
        require_clear(root);guard(root,home,r)
        if (area(root,r)/'receipt.json').exists():fail('operation_already_committed_reconcile_only')
        ps=paths(root,home,r);raw,p,t,b=validate_preimages(root,home,r,ps)
        observation=observe(r,observer)
        # Read again after provider roundtrip; no filesystem mutation was reserved yet.
        with stable_history(home,r):
            validate_authority(r,a);validate_preimages(root,home,r,ps);guard_history(root,home,r)
            t=copy.deepcopy(t);t['status']='CONTINUATION_REQUIRED';t.pop('ready',None);t['receipts']=[]
            t['interrupted_continuation']={'schema':receipt_schema(r),'state':'FULL_ENTRY_REQUIRED','operation_id':r['operation_id'],'request_sha256':sha(encoded(r)),
                'session_id':r['session_id'],'current_turn':r['current_turn'],'original_answers_sha256':r['goal_sha256'],'decision_ref':a['decision_ref']}
            b={'schema':'agentos.turn/v1','session_id':r['session_id'],'turn_id':r['current_turn'],'root':r['root'],'task_id':None,'status':'INTAKE_REQUIRED','at':datetime.now(timezone.utc).isoformat(),'hook_seen':False,'source':'standalone_cli'}
            event={'at':b['at'],'event':'COMPLETED_CONTINUATION' if completed(r) else 'INTERRUPTED_CONTINUATION','details':{'operation_id':r['operation_id'],'full_goal':'OPEN','ready_granted':False,'request_sha256':sha(encoded(r))}}
            after={'project':raw['project'],'task':encoded(t),'turn':encoded(b),'events':raw['events']+encoded(event)}
            if any(len(v)>(task_metadata_limit(root) if k=='task' else rr.MAX_METADATA) for k,v in after.items()):fail('metadata_limit')
            rows={k:{'before':base64.b64encode(raw[k]).decode(),'after':base64.b64encode(after[k]).decode(),'before_sha256':sha(raw[k]),'after_sha256':sha(after[k]),'prior_after':[]}for k in ps}
            j={'schema':'agentos.interrupted-continuation-transaction/v1','request':r,'authority':a,'observation':observation,'active_turn':r['current_turn'],'rows':rows,'receipt':_receipt(r,a,observation,rows)}
            if len(encoded(j))>MAX_JOURNAL:fail('journal_limit')
            atomic_bytes(marker(root),encoded(j))
            return _finish(root,home,r,j)


def reconcile(root,home,r,a,*,observer=None):
    from .overlay import validate_roots
    validate_roots(home)
    root=root.resolve();home=home.resolve();validate_request(root,home,r);validate_authority(r,a,reconciling=True)
    with lock(within(root,'.agentos/write.lock')),lock(within(home,'state/turns.lock')):
        guard(root,home,r);validate_mapping(root,r)
        destination=area(root,r)
        pending=marker(root).exists()
        j=rr.parse(read(marker(root)if pending else destination/'transaction.json',MAX_JOURNAL))
        if j.get('request')!=r:fail('journal_identity')
        bound_current=j['active_turn']
        observation=observe(r,observer,current_turn=a['current_turn'],bound_current=bound_current)
        with stable_history(home,r):
            validate_authority(r,a,reconciling=True);validate_mapping(root,r);guard_history(root,home,r)
            # All present images must be explained before any retarget preparation.
            for k,row in j['rows'].items():
                allowed={row['before_sha256'],row['after_sha256']}if pending else {row['after_sha256']}
                if pending:allowed.update(sha(base64.b64decode(v,validate=True))for v in row['prior_after'])
                if sha(read(paths(root,home,r)[k],task_metadata_limit(root) if k=='task' else rr.MAX_METADATA))not in allowed:fail('operation_consumed_or_state_changed')
            if source(root)!=r['expected']['source_sha256']:fail('source_changed')
            if a['current_turn']!=bound_current:
                # SAME operation and immutable original request; successor identity is
                # a separately authorized reconciliation, not another advance.
                saved=encoded(j);historical=destination/'history'/(sha(saved)+'.json')
                j=copy.deepcopy(j)
                for k in ['task','turn']:
                    row=j['rows'][k]
                    if len(row['prior_after'])>=8:fail('journal_reconcile_limit')
                    row['prior_after'].append(row['after'])
                    value=rr.parse(base64.b64decode(row['after'],validate=True))
                    if k=='task':value['interrupted_continuation']['current_turn']=a['current_turn']
                    else:value['turn_id']=a['current_turn']
                    raw=encoded(value)
                    if len(raw)>(task_metadata_limit(root) if k=='task' else rr.MAX_METADATA):fail('metadata_limit')
                    row['after']=base64.b64encode(raw).decode();row['after_sha256']=sha(raw)
                j['active_turn']=a['current_turn'];j['authority']=a;j['observation']=observation;j['receipt']=_receipt(r,a,observation,j['rows'])
                if len(encoded(j))>MAX_JOURNAL:fail('journal_limit')
                # No history/marker or target write until the new exact journal fits.
                if not historical.exists():rr.write(historical,saved,root,only=True,readback_limit=MAX_JOURNAL)
                atomic_bytes(marker(root),encoded(j));pending=True
            if pending:return _finish(root,home,r,j)
            receipt=rr.parse(read(destination/'receipt.json'))
            if receipt!=j['receipt']:fail('receipt_mismatch')
            return receipt


def validate_resume(root,home,task,session_id,turn_id,answers,*,reuse=False):
    c=task.get('interrupted_continuation',{})
    if reuse or c.get('state')!='FULL_ENTRY_REQUIRED' or c.get('session_id')!=session_id or c.get('current_turn')!=turn_id:fail('full_same_owner_entry_required')
    if answers['objective']!=task['answers']['objective'] or answers['outcome']!=task['answers']['outcome']:fail('original_goal_must_remain')
    if any(item not in answers['acceptance']for item in task['answers']['acceptance']):fail('original_acceptance_must_remain')
    if c['decision_ref']not in answers['authority']:fail('fresh_entry_authority_required')
    b=rr.parse(read(turn_path(home,session_id)))
    if b.get('turn_id')!=turn_id or b.get('root')!=str(root.resolve()) or b.get('status')!='INTAKE_REQUIRED' or b.get('task_id')is not None:fail('resume_binding')

class SupportedReadThreadObserver:
    """Owner-selected bridge to the EXISTING supported app tool, not a new RPC.

    The embedding integration supplies the actual tool callable and verifies its
    origin. This package neither authenticates a Python callable nor accepts a
    JSON file as proof of tool execution. No observer is selected by default.
    """
    def __init__(self,read_thread):
        if not callable(read_thread):fail('supported_observer_unavailable')
        self._read_thread=read_thread

    def read_turn_metadata(self,r,nonce,*,current_turn=None,bound_current=None):
        current_turn=current_turn or r['current_turn'];bound_current=bound_current or r['current_turn']
        required={r['previous_turn'],current_turn,bound_current};cursor=None;seen=set();found={};root=None
        deadline=time.monotonic()+OBSERVER_TOTAL_SECONDS;total_bytes=0;total_turns=0
        # Forty one-turn pages retain the old forty-turn horizon and 16 MiB
        # aggregate ceiling. Single oversized turns still fail; no fallback.
        for _ in range(OBSERVER_MAX_PAGES):
            call_started=time.monotonic()
            if call_started>=deadline:fail('provider_time_limit')
            if total_bytes>=OBSERVER_MAX_TOTAL_RESPONSE:fail('provider_response_limit')
            params={'threadId':r['native_thread_id'],'turnLimit':OBSERVER_TURN_LIMIT,'includeOutputs':False,'maxOutputCharsPerItem':80}
            if cursor is not None:params['cursor']=cursor
            result=self._read_thread(**params)
            now=time.monotonic()
            if now>=deadline or now-call_started>=OBSERVER_CALL_SECONDS:fail('provider_time_limit')
            if isinstance(result,ProviderMetadataEnvelope):
                envelope=ProviderMetadataEnvelope(result.metadata,result.original_response_bytes)
                response_bytes=envelope.original_response_bytes;result=envelope.metadata
            else:
                if not isinstance(result,dict):fail('provider_response')
                response_bytes=len(provider_encoded(result))
            total_bytes+=response_bytes
            if response_bytes>OBSERVER_MAX_RESPONSE or total_bytes>OBSERVER_MAX_TOTAL_RESPONSE:fail('provider_response_limit')
            # A tool error is technical UNKNOWN, never old-writer status proof.
            # Do not parse an error message as thread JSON or expose its payload.
            if 'isError'in result and type(result['isError'])is not bool:fail('provider_response')
            if result.get('isError')is True:fail('provider_tool_error')
            if 'content'in result:
                if not isinstance(result['content'],list) or any(not isinstance(x,dict)for x in result['content']):fail('provider_response')
                texts=[x.get('text')for x in result['content']if x.get('type')=='text']
                if len(texts)!=1 or not isinstance(texts[0],str) or len(texts[0].encode())>OBSERVER_MAX_RESPONSE:fail('provider_response')
                result=rr.parse(texts[0].encode())
                if not isinstance(result,dict):fail('provider_response')
            thread=result.get('thread',{})
            if not isinstance(thread,dict):fail('provider_response')
            if thread.get('id')!=r['native_thread_id'] or thread.get('cwd')!=r['native_mapping']['native_cwd']:fail('provider_identity')
            root=thread['cwd'];turns=result.get('turns')
            if not isinstance(turns,list)or len(turns)>OBSERVER_TURN_LIMIT or any(not isinstance(t,dict)for t in turns):fail('provider_response')
            total_turns+=len(turns)
            if total_turns>OBSERVER_MAX_TURNS:fail('provider_turn_limit')
            for t in turns:
                if t.get('id')in required:
                    current={'id':t['id'],'status':t.get('status')}
                    if t['id']in found and found[t['id']]!=current:fail('provider_conflicting_turn')
                    found[t['id']]=current
            if set(found)==required:break
            page=result.get('page',{})
            if not isinstance(page,dict):fail('provider_response')
            more=page.get('hasMore',False)
            if type(more)is not bool:fail('provider_pagination')
            cursor=page.get('nextCursor')if more else None
            if more and cursor is None:fail('provider_pagination')
            if cursor is None:break
            if not isinstance(cursor,str)or not cursor or len(cursor)>2048 or cursor in seen:fail('provider_pagination')
            seen.add(cursor)
        # Parsing/validation is part of the same non-resetting bounded operation.
        now=time.monotonic()
        if now>=deadline or now-call_started>=OBSERVER_CALL_SECONDS:fail('provider_time_limit')
        if set(found)!=required:fail('provider_turn_unavailable')
        return {'schema':'agentos.provider-turn-metadata/v1','source':'supported_read_thread','request_sha256':nonce,
            'session_id':r['session_id'],'native_thread_id':r['native_thread_id'],'native_cwd':root,'previous':found[r['previous_turn']],'current':found[current_turn],'bound_current':found[bound_current],
            'observed_at':datetime.now(timezone.utc).isoformat(),'observation_ref':'mcp__codex_app__read_thread:'+r['operation_id']}


def command(argv,home,*,read_thread=None):
    """Embedding entry point; standalone CLI without the selected tool denies."""
    import argparse
    parser=argparse.ArgumentParser(prog='agentos project interrupted-continuation')
    parser.add_argument('action',choices=['advance','reconcile'])
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--permit',type=Path,required=True)
    args=parser.parse_args(argv)
    if read_thread is None:fail('supported_observer_unavailable')
    observer=SupportedReadThreadObserver(read_thread)
    r=rr.document(args.request);a=rr.document(args.permit)
    fn=advance if args.action=='advance'else reconcile
    return fn(args.root,home,r,a,observer=observer),0
