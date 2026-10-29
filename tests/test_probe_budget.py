"""Finite probe deadlines; local synthetic transports only, no live workers."""
import copy
import json
import pytest

from agent_os.codex_launch import CodexLaunchProvider, StdioRpc, _commands
from agent_os.safeio import atomic_json, digest
from agent_os.screen_launch import ScreenLaunchProvider, FINITE_PROBE_CAPABILITY
from agent_os.session_launch import LaunchError, validate_request, probe_budget_seconds
from test_session_launch import request
from test_screen_launch import screen_fixture
from test_screen_pre_resume import case, OwnerReview, RecoveryGuard
from agent_os.screen_pre_resume import reconcile_pre_resume, select_pre_resume
from agent_os.screen_adoption import adopt_screen


@pytest.mark.parametrize('value', [None, True, False, 0, -1, 241, 1.5, '180', float('inf')])
def test_invalid_budget_refuses_before_effect(tmp_path, value):
    req = request(tmp_path); req['probe_budget_seconds'] = value
    with pytest.raises(LaunchError, match='bounded_probe_budget_required'):
        validate_request(req)


@pytest.mark.parametrize('value', [1, 45, 180, 240])
def test_valid_request_bound_budget(tmp_path, value):
    req = request(tmp_path); before = digest(req)
    req['probe_budget_seconds'] = value
    validate_request(req)
    assert probe_budget_seconds(req) == value and digest(req) != before


def delayed_rpc(req, monkeypatch, elapsed):
    """Drive real event selection with synthetic monotonic arrival deadlines."""
    monkeypatch.setattr('agent_os.codex_launch.time.monotonic', lambda: 1000)
    rpc = object.__new__(StdioRpc); rpc.pending = []
    rpc.call = lambda *args: {'turn': {'id': 'probe-turn'}}
    events = [{'method': 'item/completed', 'params': {'threadId': 'sid', 'turnId': 'probe-turn', 'item': {
        'id': cap, 'type': 'commandExecution', 'command': script, 'cwd': req['workspace'],
        'status': 'completed', 'exitCode': 0, 'aggregatedOutput': output}}}
        for cap, (script, output) in _commands(req, 'nonce').items()]
    events.append({'method': 'turn/completed', 'params': {'threadId': 'sid', 'turn': {'id': 'probe-turn', 'status': 'completed'}}})
    source = iter(events)
    def receive(deadline):
        if deadline < 1000 + elapsed:
            raise LaunchError('provider_timeout', status='UNKNOWN')
        return next(source)
    rpc._receive = receive
    return rpc


def test_compaction_sized_delay_needs_explicit_finite_budget(tmp_path, monkeypatch):
    req = request(tmp_path)
    with pytest.raises(LaunchError, match='provider_timeout'):
        CodexLaunchProvider(delayed_rpc(req, monkeypatch, 115)).probe(req, {'session_id': 'sid'}, 'nonce')
    req['probe_budget_seconds'] = 180
    result = CodexLaunchProvider(delayed_rpc(req, monkeypatch, 115)).probe(req, {'session_id': 'sid'}, 'nonce')
    assert result['status'] == 'PASS' and result['proofs']
    assert result['turn_id'] == 'probe-turn'


def test_legacy_direct_constructor_timeout_preserved(tmp_path, monkeypatch):
    req = request(tmp_path)
    assert probe_budget_seconds(req) == 45
    result = CodexLaunchProvider(delayed_rpc(req, monkeypatch, 2), probe_timeout=3).probe(req, {'session_id': 'sid'}, 'nonce')
    assert result['status'] == 'PASS'


@pytest.mark.parametrize('kind', ['ok', 'default', 'unsupported', 'state', 'bootstrap', 'request', 'malformed_capability'])
def test_parent_rpc_deadline_and_worker_binding(tmp_path, kind):
    req = request(tmp_path)
    if kind != 'default': req['probe_budget_seconds'] = 180
    boot = {'request': req, 'probe_budget_seconds': 180 if kind != 'default' else 45}
    atomic_json(tmp_path / 'bootstrap.json', boot)
    provider = object.__new__(ScreenLaunchProvider); provider.root = tmp_path
    provider.identity = {'bootstrap_sha256': digest(boot), 'request_sha256': digest(req)}
    state = {'probe_budget_seconds': 180, 'protocol_capabilities': [FINITE_PROBE_CAPABILITY]}
    if kind == 'unsupported': state['protocol_capabilities'] = []
    if kind == 'malformed_capability': state['protocol_capabilities'] = None
    if kind == 'state': state['probe_budget_seconds'] = 45
    if kind == 'bootstrap': boot['probe_budget_seconds'] = 45; atomic_json(tmp_path / 'bootstrap.json', boot)
    if kind == 'request': req['scope'] = 'changed'
    provider._state = lambda: state
    calls = []
    provider._call = lambda *args, **kwargs: calls.append((args, kwargs)) or {'status': 'PASS'}
    if kind in ['ok', 'default']:
        provider.probe(req, {}, 'nonce')
        assert calls[0][1]['timeout'] == (185 if kind == 'ok' else 50)
    else:
        with pytest.raises(LaunchError, match='screen_probe_budget_not_bound_or_unsupported'):
            provider.probe(req, {}, 'nonce')
        assert calls == []


def test_budget_replacement_real_mailbox_keeps_history(screen_fixture):
    f = screen_fixture
    plan, adoption, root, oldlaunch, worker, _ = case(f)
    oldbytes = {p: p.read_bytes() for p in [root, oldlaunch, *worker.rglob('*.json')]}
    plan['replacement_request']['probe_budget_seconds'] = 180
    ref = reconcile_pre_resume(f['home'], plan, owning_guard=OwnerReview())
    current = dict(adoption, pre_resume_recovery=ref)
    selected = select_pre_resume(f['home'], f['name'], plan['replacement_request'], current)
    claims = []
    result = adopt_screen(**dict(f, request=plan['replacement_request']), adoption=current,
        adoption_guard=RecoveryGuard(adoption['pending_reconciliation']), dispatch_claim=lambda: claims.append(True))
    assert result['work']['status'] == 'completed' and claims == [True]
    newroot = f['home'] / 'state/screen-workers' / f['name']
    boot = json.loads((newroot / 'bootstrap.json').read_text()); state = json.loads((newroot / 'state.json').read_text())
    assert boot['probe_budget_seconds'] == state['probe_budget_seconds'] == 180
    assert FINITE_PROBE_CAPABILITY in state['protocol_capabilities']
    assert all(p.read_bytes() == raw for p, raw in oldbytes.items())


@pytest.mark.parametrize('kind', ['invalid', 'authority', 'settings', 'post_review_change'])
def test_replacement_budget_does_not_relax_other_bindings(screen_fixture, kind):
    f = screen_fixture; plan, adoption, *_ = case(f)
    replacement = plan['replacement_request']; replacement['probe_budget_seconds'] = 180
    if kind == 'invalid': replacement['probe_budget_seconds'] = 241
    if kind == 'authority': replacement['authority'] = 'foreign'
    if kind == 'settings': replacement['executor']['provider'] = 'foreign'
    if kind == 'post_review_change':
        ref = reconcile_pre_resume(f['home'], plan, owning_guard=OwnerReview())
        replacement['probe_budget_seconds'] = 181
        with pytest.raises(LaunchError):
            select_pre_resume(f['home'], f['name'], replacement, dict(adoption, pre_resume_recovery=ref))
    else:
        with pytest.raises(LaunchError): reconcile_pre_resume(f['home'], plan, owning_guard=OwnerReview())
