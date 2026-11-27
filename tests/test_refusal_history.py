import json
from pathlib import Path

import pytest
from test_foundation import documents, setup
from test_recovery_workflow_turn_v3 import factory, permit, CURRENT, SESSION

from agent_os import accepted_checkpoint_history as hist, project, refusal_recovery as rr
from agent_os.safeio import GateError, sha
from agent_os.turns import advance_standalone_turn


@pytest.fixture
def previous(factory, monkeypatch):
    enter = project.enter
    def enter_after_checkpoint(root, answers, *, session_id, turn_id, user_home):
        result = enter(root, answers, session_id=session_id, turn_id='old', user_home=user_home)
        task = result['task_id']
        project.checkpoint(root, task, "Completed prior stage", "Continue with remaining work")
        advance_standalone_turn(user_home, session_id, 'old', turn_id, root, task)
        return enter(root, answers, session_id=session_id, turn_id=turn_id, user_home=user_home, resume_task=task)
    monkeypatch.setattr(project, 'enter', enter_after_checkpoint)
    case = factory(rr.MODERN_REQUEST)
    monkeypatch.undo()
    root, home, task, _, request, _ = case
    request['accepted_checkpoint_history_sha256'] = hist.qualify(root, home, task_id=task,
        project_id=request['project_id'], revision=request['revision'], reuse_verified_objects=True)['sha256']
    return case


def test_accepted_history_survives_recovery_and_same_task_resume(previous):
    root, home, task, answers, r, paths = previous
    before = project.load_task(root, task)['checkpoint']
    evidence = {p:p.read_bytes() for p in paths['task'].parent.glob('handoff-*.json')}
    witness = root / r['witness']['diagnostic']['path']
    evidence[witness] = witness.read_bytes()
    assert rr.acknowledge(root, home, task, r, permit(r))['status'] == 'ACKNOWLEDGED'
    ack = rr.area(root, task, r['operation_id']) / 'ack.json'
    assert rr.advance(root, home, task, r, permit(r,'advance',CURRENT,ack=sha(ack.read_bytes())))['status'] == 'ADVANCED'
    assert project.enter(root, answers, session_id=SESSION, turn_id=CURRENT, user_home=home, resume_task=task)['task_id'] == task
    after = project.load_task(root, task)
    assert after['checkpoint'] == before and after['revision'] == r['revision'] + 1
    assert all(p.read_bytes() == content for p,content in evidence.items())


@pytest.mark.parametrize('fault',['missing','unknown','foreign','duplicate','receipt','current','changed','default'])
def test_unqualified_history_is_refused_without_writes(previous, fault):
    root, home, task, _, r, paths = previous
    journal = next(paths['task'].parent.glob('handoff-*.json'))
    if fault == 'missing':
        journal.unlink()
    elif fault == 'unknown':
        (journal.parent/'handoff-completion-unknown.json').write_text('{}')
    elif fault == 'foreign':
        value=json.loads(journal.read_bytes());value['library_root']=str(root);journal.write_bytes(rr.enc(value))
    elif fault in ('duplicate','receipt','current'):
        events=[json.loads(line) for line in paths['events'].read_bytes().splitlines()]
        event=next(e for e in events if e['event']=='CHECKPOINT')
        if fault=='receipt': event['details']['handoff']['receipt']['accepted_count']=0
        elif fault=='current':events.remove(event);events.append(event)
        else:events.insert(events.index(event),event)
        paths['events'].write_bytes(b''.join(map(rr.enc,events)))
    elif fault=='changed':
        r['accepted_checkpoint_history_sha256']='f'*64
    else:
        del r['accepted_checkpoint_history_sha256']
    prior={p:p.read_bytes() for p in paths.values()}
    with pytest.raises(GateError):
        rr.acknowledge(root,home,task,r,permit(r))
    assert all(p.read_bytes()==raw for p,raw in prior.items())
    assert not rr.pending(root).exists()
