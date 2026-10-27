"""Synthetic finite admission and interrupted-effect regressions; no live hosts."""
import copy
import json
import os
from pathlib import Path

import pytest
from test_foundation import setup, prepared
from agent_os import project as p, scoped_admission as s
from agent_os.safeio import GateError, sha
from agent_os.turns import turn_path


def fixture(setup):
    root, home, _ = setup
    task = prepared(setup)
    (root / "staged").mkdir()
    for n in range(4):
        (root / "staged" / str(n)).write_bytes(f"reviewed {n}\n".encode())
    (root / "old.txt").write_bytes(b"old\n")
    (root / "forbidden").mkdir()
    (root / "forbidden/secret").write_bytes(b"must never read\n")
    req = {"schema": s.SCHEMA, "operation": "op1", "task": task,
           "session_id": "s", "turn_id": "t", "actor": "existing-writer",
           "authority": "explicit synthetic owner instruction", "reviewer": "fixture reviewer",
           "expected": {"project": sha((root/'.agentos/project.json').read_bytes()),
                        "task": sha((root/f'.agentos/tasks/{task}/task.json').read_bytes()),
                        "events": sha((root/f'.agentos/tasks/{task}/events.jsonl').read_bytes()),
                        "binding": sha(turn_path(home,'s').read_bytes())},
           "held_paths": ["forbidden"], "create_directories": ["evidence"],
           "files": [{"source": f"staged/{i}", "target": "old.txt" if i == 0 else f"evidence/{i}.json",
                      "before": sha(b"old\n") if i == 0 else None,
                      "after": sha(f"reviewed {i}\n".encode())} for i in range(4)]}
    return root, home, req


def deny_broad_reads(monkeypatch, root):
    monkeypatch.setattr(p, "source_snapshot", lambda *a, **k: pytest.fail("whole source read"))
    original = s._bytes
    def read(r, rel, *a, **k):
        assert not (r == root and str(rel).startswith("forbidden")), "held source read"
        return original(r, rel, *a, **k)
    monkeypatch.setattr(s, "_bytes", read)


def test_exact_apply_history_and_idempotency(setup, monkeypatch):
    root, home, req = fixture(setup)
    prior = p.load_task(root, req['task'])
    binding = turn_path(home,'s').read_bytes()
    deny_broad_reads(monkeypatch, root)
    plan = s.apply(root, home, req, plan=True)
    assert plan['status'] == 'SCOPED_PLAN'
    assert not (root/'evidence').exists()
    result = s.apply(root, home, req)
    assert result['status'] == 'SCOPED_APPLIED' and not result['replayed']
    task = p.load_task(root, req['task'])
    assert task['revision'] == prior['revision'] + 1
    assert task['ready'] == prior['ready'] and task['receipts'] == prior['receipts']
    assert task['answers']['objective'] == prior['answers']['objective']
    import jsonschema
    schema = json.loads((Path(__file__).parents[1]/'schemas/project-task-v1.schema.json').read_text())
    jsonschema.validate(task, schema)
    assert turn_path(home,'s').read_bytes() == binding
    for row in req['files']:
        assert sha((root/row['target']).read_bytes()) == row['after']
    assert p.check_ready(root, req['task'])['status'] == 'BLOCKED'
    assert p.assess(root, req['task'])['status'] == 'BLOCKED'
    assert p.run_check(root, req['task'], 'unit')['status'] == 'BLOCKED'
    before = (root/f".agentos/tasks/{req['task']}/events.jsonl").read_bytes()
    assert s.apply(root, home, req)['replayed']
    assert (root/f".agentos/tasks/{req['task']}/events.jsonl").read_bytes() == before


@pytest.mark.parametrize('field', ['project','task','events','binding'])
def test_stale_metadata_no_product_effect(setup, field):
    root, home, req = fixture(setup)
    req['expected'][field] = '0'*64
    with pytest.raises(GateError, match='cas'):
        s.apply(root,home,req)
    assert (root/'old.txt').read_bytes() == b'old\n' and not (root/'evidence').exists()
    assert not (root/'.agentos/scoped-transaction.json').exists()


@pytest.mark.parametrize('kind', ['held-source','held-target','escape','symlink-source','symlink-parent','hardlink','wrong-source','wrong-target','missing-parent','overlap','control','bad-field','binding','document-held'])
def test_preflight_refusals(setup, monkeypatch, kind):
    root,home,req=fixture(setup)
    if kind=='held-source': req['files'][0]['source']='forbidden/secret'
    elif kind=='held-target': req['files'][0]['target']='forbidden/secret'
    elif kind=='escape': req['files'][0]['target']='../escape'
    elif kind=='symlink-source': (root/'staged/0').unlink(); (root/'staged/0').symlink_to(root/'forbidden/secret')
    elif kind=='symlink-parent': (root/'evidence').symlink_to(root/'forbidden')
    elif kind=='hardlink': (root/'staged/0').unlink(); os.link(root/'forbidden/secret',root/'staged/0')
    elif kind=='wrong-source': req['files'][0]['after']='0'*64
    elif kind=='wrong-target': req['files'][0]['before']='0'*64
    elif kind=='missing-parent': req['create_directories']=[]
    elif kind=='overlap': req['files'][1]['target']='old.txt'
    elif kind=='control': req['files'][0]['target']='.agentos/project.json'
    elif kind=='bad-field': req['shell']='echo nope'
    elif kind=='binding': req['turn_id']='other'
    elif kind=='document-held': req['held_paths']=['docs/agentos']
    deny_broad_reads(monkeypatch,root)
    with pytest.raises(GateError): s.apply(root,home,req)
    assert (root/'old.txt').read_bytes()==b'old\n'
    assert not (root/'.agentos/scoped-transaction.json').exists()


@pytest.mark.parametrize('fail_at',range(1,9))
def test_crash_resume_same_operation(setup,monkeypatch,fail_at):
    root,home,req=fixture(setup)
    real=s.atomic_bytes
    calls=0
    def crash(*a,**k):
        nonlocal calls
        calls+=1
        real(*a,**k)
        if calls==fail_at: raise RuntimeError('simulated crash after durable write')
    monkeypatch.setattr(s,'atomic_bytes',crash)
    with pytest.raises(RuntimeError): s.apply(root,home,req)
    assert (root/'.agentos/scoped-transaction.json').exists()
    with pytest.raises(GateError,match='reconciliation'): p.check_ready(root,req['task'])
    with pytest.raises(GateError,match='reconciliation'):
        p.enter(root,setup[2],session_id='s',turn_id='t',user_home=home,resume_task=req['task'])
    monkeypatch.setattr(s,'atomic_bytes',real)
    deny_broad_reads(monkeypatch,root)
    assert s.apply(root,home,req)['status']=='SCOPED_APPLIED'
    assert not (root/'.agentos/scoped-transaction.json').exists()
    assert p.load_task(root,req['task'])['revision']==2


def test_unknown_foreign_write_and_changed_request_are_not_replayed(setup,monkeypatch):
    root,home,req=fixture(setup);real=s.atomic_bytes
    def crash(path,*a,**k):
        real(path,*a,**k)
        if path.name=='old.txt': raise RuntimeError('crash')
    monkeypatch.setattr(s,'atomic_bytes',crash)
    with pytest.raises(RuntimeError): s.apply(root,home,req)
    monkeypatch.setattr(s,'atomic_bytes',real)
    other=copy.deepcopy(req);other['operation']='op2'
    with pytest.raises(GateError,match='operation_conflict'): s.apply(root,home,other)
    (root/'old.txt').write_bytes(b'foreign edit')
    with pytest.raises(GateError,match='unknown_effect'): s.apply(root,home,req)
    assert (root/'old.txt').read_bytes()==b'foreign edit'


def test_receipt_postimage_drift_refuses_replay(setup):
    root,home,req=fixture(setup);s.apply(root,home,req)
    (root/'old.txt').write_bytes(b'changed after completion')
    with pytest.raises(GateError,match='unknown_effect'):s.apply(root,home,req)


def test_cli_routes_to_canonical_module(setup):
    root,home,req=fixture(setup);path=root/'request.json';path.write_text(json.dumps(req))
    result,code=p.command(['scoped-apply','--root',str(root),'--request',str(path),'--plan'],home)
    assert code==0 and result['status']=='SCOPED_PLAN'


@pytest.mark.parametrize('mode', [0o600, 0o644, 0o664])
def test_existing_modes_preserved_without_permission_changes(setup, mode):
    root,home,req=fixture(setup)
    target=root/'old.txt';target.chmod(mode)
    assert s.apply(root,home,req,plan=True)['status']=='SCOPED_PLAN'
    assert target.stat().st_mode & 0o7777 == mode
    s.apply(root,home,req)
    assert target.stat().st_mode & 0o7777 == mode
    assert s.apply(root,home,req)['replayed']
    assert target.stat().st_mode & 0o7777 == mode
    assert (root/'evidence/1.json').stat().st_mode & 0o7777 == 0o644


@pytest.mark.parametrize('mode', [0o755, 0o666, 0o777, 0o2644, 0o4644])
def test_unsupported_modes_refused_before_journal(setup, mode):
    root,home,req=fixture(setup)
    target=root/'old.txt';target.chmod(mode)
    with pytest.raises(GateError,match='file_mode'):s.apply(root,home,req)
    assert target.read_bytes()==b'old\n'
    assert target.stat().st_mode & 0o7777 == mode
    assert not (root/'.agentos/scoped-transaction.json').exists()


def test_group_writable_mode_survives_interrupted_apply(setup,monkeypatch):
    root,home,req=fixture(setup);target=root/'old.txt';target.chmod(0o664)
    real=s.atomic_bytes
    def crash(path,*args,**kwargs):
        real(path,*args,**kwargs)
        if path.name=='old.txt':raise RuntimeError('interrupted after product write')
    monkeypatch.setattr(s,'atomic_bytes',crash)
    with pytest.raises(RuntimeError):s.apply(root,home,req)
    assert target.stat().st_mode & 0o7777 == 0o664
    monkeypatch.setattr(s,'atomic_bytes',real)
    assert s.apply(root,home,req)['status']=='SCOPED_APPLIED'
    assert target.stat().st_mode & 0o7777 == 0o664
    assert not (root/'.agentos/scoped-transaction.json').exists()
