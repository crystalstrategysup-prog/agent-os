"""Adapter qualification on disposable synthetic metadata, never native targets."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys

import pytest

from agent_os import interrupted_bridge as bridge
from agent_os import interrupted_continuation as continuation
from agent_os import refusal_recovery as recovery
from agent_os import refusal_recovery_bridge as adapter
from agent_os.safeio import GateError, sha
from test_recovery_workflow_turn_v3 import (
    CURRENT, ORIGIN, THREAD, factory, images, permit, setup,
)


def argv(case, action, authority):
    root, home, task, _, request, _ = case
    request_file = root / 'adapter-request.json'
    permit_file = root / 'adapter-permit.json'
    request_file.write_bytes(recovery.enc(request))
    permit_file.write_bytes(recovery.enc(authority))
    return [action, '--root', str(root), '--home', str(home), '--task', task,
            '--request', str(request_file), '--permit', str(permit_file)]


def tool(case, current=ORIGIN, *, change=None, effect=None, gap=False):
    request = case[-2]
    calls = []

    def read_thread(**params):
        index = len(calls)
        assert params == {'threadId': THREAD, 'turnLimit': 1,
                          'includeOutputs': False, 'maxOutputCharsPerItem': 80,
                          **({'cursor': 'synthetic-page:' + str(index)} if index else {})}
        calls.append(params)
        if effect:
            effect()
        if gap and index:
            selected = {'id': f'{index:08x}-0000-4000-8000-000000000000', 'status': 'completed'}
        else:
            selected = {'id': ORIGIN, 'status': 'interrupted'} if index else {'id': current, 'status': 'inProgress'}
        value = {'thread': {'id': THREAD, 'cwd': request['root']}, 'turns': [selected],
                 'page': {'hasMore': gap or (current != ORIGIN and not index),
                          'nextCursor': 'synthetic-page:' + str(index + 1)}}
        if change == 'thread': value['thread']['id'] = CURRENT
        if change == 'cwd': value['thread']['cwd'] += '/foreign'
        if change == 'current': value['turns'][0]['status'] = 'completed'
        if change == 'origin' and index: value['turns'][0]['status'] = 'inProgress'
        return value

    return read_thread, calls


def ack(case):
    selected, calls = tool(case)
    result = adapter.command(argv(case, 'acknowledge', permit(case[-2])), read_thread=selected)
    assert len(calls) == 1 and result['status'] == 'ACKNOWLEDGED'
    return sha((recovery.area(case[0], case[2], case[-2]['operation_id']) / 'ack.json').read_bytes())


def test_adapter_reuses_exact_existing_bridge_helpers():
    assert adapter.StdioToolBridge is bridge.StdioToolBridge
    assert adapter.MetadataResponseAccounting is bridge.MetadataResponseAccounting
    assert adapter.prepare_metadata_response is bridge.prepare_metadata_response


def test_embedding_current_ack_then_supported_historical_advance(factory):
    case = factory(); root, home, task, answers, request, _ = case
    ack_sha = ack(case)
    selected, calls = tool(case, CURRENT)
    result = adapter.command(argv(case, 'advance', permit(request, 'advance', CURRENT, ack=ack_sha)),
                             read_thread=selected)
    assert result['status'] == 'ADVANCED' and len(calls) == 2
    assert result['ready_granted'] is result['semantic_acceptance'] is False
    assert recovery.parse(case[-1]['task'].read_bytes())['turn_id'] == request['expected']['bound_turn_id']
    assert recovery.parse(case[-1]['turn'].read_bytes())['turn_id'] == CURRENT


def test_missing_selected_tool_denies_before_reservation(factory):
    case = factory(); before = images(case)
    with pytest.raises(GateError, match='recovery_supported_observer_unavailable'):
        adapter.command(argv(case, 'acknowledge', permit(case[-2])))
    assert images(case) == before and not recovery.pending(case[0]).exists()


@pytest.mark.parametrize('change', ['thread', 'cwd', 'current', 'origin'])
def test_foreign_or_inactive_metadata_denies_without_recovery_writes(factory, change):
    case = factory(); before = images(case); selected, calls = tool(case, CURRENT, change=change)
    with pytest.raises(GateError):
        adapter.command(argv(case, 'acknowledge', permit(case[-2], current=CURRENT)), read_thread=selected)
    assert images(case) == before and not recovery.pending(case[0]).exists()


def test_historical_origin_beyond_forty_pages_is_exact_capability_gap(factory):
    case = factory(); before = images(case); selected, calls = tool(case, CURRENT, gap=True)
    with pytest.raises(GateError, match='provider_turn_unavailable'):
        adapter.command(argv(case, 'acknowledge', permit(case[-2], current=CURRENT)), read_thread=selected)
    assert len(calls) == 40
    assert images(case) == before and not recovery.pending(case[0]).exists()


def test_deadline_is_not_reset_by_adapter(factory, monkeypatch):
    case = factory(); before = images(case); clock = [0.0]
    monkeypatch.setattr(continuation.time, 'monotonic', lambda: clock[0])
    selected, _ = tool(case, effect=lambda: clock.__setitem__(0, 121.0))
    with pytest.raises(GateError, match='provider_time_limit'):
        adapter.command(argv(case, 'acknowledge', permit(case[-2])), read_thread=selected)
    assert images(case) == before and not recovery.pending(case[0]).exists()


def test_adapter_rechecks_metadata_cas_after_tool_return(factory):
    case = factory(); before = images(case)
    def drift():
        value = recovery.parse(case[-1]['project'].read_bytes())
        value['synthetic_drift'] = True
        case[-1]['project'].write_bytes(recovery.enc(value))
    selected, _ = tool(case, effect=drift)
    with pytest.raises(GateError, match='recovery_cas_mismatch'):
        adapter.command(argv(case, 'acknowledge', permit(case[-2])), read_thread=selected)
    assert {k: v for k, v in images(case).items() if k != 'project'} == {k: v for k, v in before.items() if k != 'project'}
    assert not recovery.pending(case[0]).exists()


def test_adapter_unknown_finishes_exact_prepared_metadata_without_replay(factory, monkeypatch):
    case = factory(); root, home, task, _, request, paths = case
    original = recovery.write
    def interrupted(path, *args, **kwargs):
        if path == paths['task']: raise OSError('synthetic adapter interrupted write')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(recovery, 'write', interrupted)
    selected, _ = tool(case)
    with pytest.raises(GateError, match='recovery_operation_unknown'):
        adapter.command(argv(case, 'acknowledge', permit(request)), read_thread=selected)
    assert recovery.status(root, home, task, request['operation_id'])['status'] == 'PREPARED'
    monkeypatch.setattr(recovery, 'write', original)
    authority = permit(request, 'reconcile', journal=sha(recovery.marker(root).read_bytes()))
    selected, _ = tool(case)
    result = adapter.command(argv(case, 'reconcile', authority), read_thread=selected)
    assert result['status'] == 'ACKNOWLEDGED' and not recovery.pending(root).exists()
    assert sum(json.loads(line)['event'] == 'REFUSAL_ACKNOWLEDGED' for line in paths['events'].read_text().splitlines()) == 1


@pytest.mark.parametrize('wrong_nonce', [False, True])
def test_stdio_entry_uses_actual_challenge_and_existing_accounting(factory, wrong_nonce):
    case = factory(); request = case[-2]; before = images(case)
    args = argv(case, 'acknowledge', permit(request))
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'), PYTHONDONTWRITEBYTECODE='1')
    child = subprocess.Popen([sys.executable, '-B', '-u', '-m', 'agent_os.refusal_recovery_bridge', *args],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    assert select.select([child.stdout], [], [], 5)[0]
    challenge = json.loads(child.stdout.readline())
    assert challenge['request_sha256'] == sha(recovery.enc(request))
    selected, calls = tool(case)
    actual = selected(**challenge['params'])
    actual['turns'][0]['items'] = [{'type': 'agentMessage', 'text': 'synthetic body must be stripped'}]
    accounting = adapter.MetadataResponseAccounting(challenge['request_sha256'], THREAD)
    response = adapter.prepare_metadata_response(challenge, actual, accounting=accounting)
    assert accounting.calls == 1 and accounting.total_original_bytes == len(continuation.provider_encoded(actual))
    assert 'items' not in response['result']['turns'][0]
    if wrong_nonce: response['nonce'] = '0' * 32
    stdout, stderr = child.communicate((json.dumps(response) + '\n').encode(), timeout=5)
    result = json.loads(stdout)
    assert not stderr
    if wrong_nonce:
        assert child.returncode == 2 and 'bridge_response_binding' in result['error']
        assert images(case) == before and not recovery.pending(case[0]).exists()
    else:
        assert child.returncode == 0 and result['result']['status'] == 'ACKNOWLEDGED'
        assert result['result']['ready_granted'] is False
