"""Current loaded-thread readback, independent of new-thread defaults. No live RPC."""
import copy
import json

import pytest

from agent_os.codex_launch import (CodexLaunchProvider, StdioRpc,
                                  _continuation_model_binding)
from agent_os.session_launch import LaunchError
from test_codex_launch import CatalogRpc, catalog_row, fixture

SID = '01a0a2b6-522a-7501-9a78-c093c781141e'


class ExistingRpc(CatalogRpc):
    def __init__(self, request):
        super().__init__(request, config={'model': 'fixture-default', 'model_reasoning_effort': 'high'},
                         pages={None: {'data': [catalog_row(default=False), catalog_row('fixture-default')],
                                       'nextCursor': None}})
        self.thread = {'id': SID, 'cwd': request['workspace'], 'status': {'type': 'idle'},
                       'model': 'fixture-model', 'modelProvider': 'openai', 'reasoningEffort': 'medium',
                       'preview': 'PRIVATE_FIXTURE_PREVIEW', 'turns': ['PRIVATE_FIXTURE_TURN']}

    def call(self, method, params, *, deadline=None):
        if method == 'thread/read':
            self.calls.append((method, copy.deepcopy(params)))
            assert params == {'threadId': SID, 'includeTurns': False}
            return {'thread': copy.deepcopy(self.thread)}
        return super().call(method, params, deadline=deadline)


def existing_fixture(tmp_path):
    req, _, _ = fixture(tmp_path)
    rpc = ExistingRpc(req)
    startup = {'session_id': SID, 'workspace': req['workspace'], 'connection_id': rpc.connection_id,
               'model': 'fixture-model', 'model_provider': 'openai', 'reasoning_effort': 'medium'}
    return req, rpc, startup


def observe(req, rpc, startup):
    provider = CodexLaunchProvider(rpc)
    observed = provider.describe_existing(req, startup, 'continuation-attempt')
    return observed, _continuation_model_binding(observed, startup), provider


def test_continuation_model_reads_current_thread_not_defaults(tmp_path):
    req, rpc, startup = existing_fixture(tmp_path)
    observed, binding, provider = observe(req, rpc, startup)
    assert observed['model'] == 'fixture-model' and observed['reasoning_effort'] == 'medium'
    assert observed['model_preflight']['current_config_defaults'] == {'model': 'fixture-default', 'reasoning_effort': 'high'}
    metadata = observed['model_preflight']
    assert metadata['configured_model'] == 'fixture-default'
    assert metadata['configured_reasoning_effort'] == 'high'
    assert metadata['selected_model'] == 'fixture-model'
    assert metadata['selected_reasoning_effort'] == 'medium'
    assert metadata['model_source'] == metadata['reasoning_effort_source'] == 'thread_read_response'
    assert binding['source'] == 'thread_read_response' and binding['execution_telemetry'] == 'NOT_PROVEN'
    assert 'PRIVATE_FIXTURE' not in json.dumps(observed)
    assert [m for m, _ in rpc.calls] == ['config/read', 'thread/read', 'model/list']
    with pytest.raises(LaunchError, match='current_model_preflight_required'):
        provider.create(req, 'continuation-attempt')
    assert all(m not in {'thread/start', 'thread/resume', 'turn/start'} for m, _ in rpc.calls)


@pytest.mark.parametrize('key,value,code', [('id', 'another-thread', 'continuation_thread_identity_mismatch'),
    ('model', 'fixture-default', 'startup_changed:model'),
    ('modelProvider', 'different-provider', 'startup_changed:model_provider'),
    ('reasoningEffort', 'high', 'startup_changed:reasoning_effort'),
    ('cwd', '/different-fixture-workspace', 'screen_continuation_environment_changed')])
def test_continuation_model_actual_drift_never_starts_work(tmp_path, key, value, code):
    req, rpc, startup = existing_fixture(tmp_path)
    rpc.thread[key] = value
    if key == 'reasoningEffort':
        rpc.pages[None]['data'][0]['supportedReasoningEfforts'].append({'reasoningEffort': 'high'})
    with pytest.raises(LaunchError) as error:
        observe(req, rpc, startup)
    assert error.value.code == code
    assert all(m not in {'thread/start', 'thread/resume', 'turn/start'} for m, _ in rpc.calls)


@pytest.mark.parametrize('key', ['model', 'modelProvider', 'reasoningEffort'])
@pytest.mark.parametrize('missing', [True, False])
def test_continuation_model_missing_actual_is_unknown(tmp_path, key, missing):
    req, rpc, startup = existing_fixture(tmp_path)
    if missing: del rpc.thread[key]
    else: rpc.thread[key] = None
    with pytest.raises(LaunchError) as error:
        observe(req, rpc, startup)
    assert error.value.status == 'UNKNOWN'
    assert all(m not in {'thread/start', 'thread/resume', 'turn/start'} for m, _ in rpc.calls)


@pytest.mark.parametrize('status,expected', [('notLoaded', 'UNKNOWN'), ('systemError', 'UNKNOWN'), ('active', 'BLOCKED')])
def test_continuation_model_persisted_only_or_busy_does_not_authorize_probe(tmp_path, status, expected):
    req, rpc, startup = existing_fixture(tmp_path)
    rpc.thread['status'] = {'type': status, 'activeFlags': []}
    with pytest.raises(LaunchError) as error:
        observe(req, rpc, startup)
    assert error.value.status == expected
    assert [m for m, _ in rpc.calls] == ['config/read', 'thread/read']


def test_continuation_model_wrong_connection_and_stale_receipt_refuse(tmp_path):
    req, rpc, startup = existing_fixture(tmp_path)
    other = dict(startup, connection_id='another-connection')
    with pytest.raises(LaunchError): observe(req, rpc, other)
    assert [m for m, _ in rpc.calls] == ['config/read']
    observed = CodexLaunchProvider(rpc).describe_existing(req, startup, 'fresh-attempt')
    with pytest.raises(LaunchError, match='current_thread_readback_required'):
        _continuation_model_binding(observed, startup, clock=lambda: observed['observed_at'] + 61)


@pytest.mark.parametrize('kind', ['missing-model', 'cursor', 'effort'])
def test_continuation_model_current_catalog_still_required(tmp_path, kind):
    req, rpc, startup = existing_fixture(tmp_path)
    if kind == 'missing-model': rpc.pages[None]['data'] = [catalog_row('fixture-default')]
    elif kind == 'cursor': rpc.pages[None]['nextCursor'] = ''
    else: rpc.pages[None]['data'][0]['supportedReasoningEfforts'] = [{'reasoningEffort': 'high'}]
    with pytest.raises(LaunchError) as error: observe(req, rpc, startup)
    assert error.value.status == 'UNKNOWN'
    assert all(m not in {'thread/start', 'thread/resume', 'turn/start'} for m, _ in rpc.calls)


def test_continuation_model_config_policy_and_explicit_provider_guard_retained(tmp_path):
    req, rpc, startup = existing_fixture(tmp_path)
    rpc.config['approval_policy'] = 'untrusted'
    with pytest.raises(LaunchError): observe(req, rpc, startup)
    assert [m for m, _ in rpc.calls] == ['config/read']
    rpc.config['approval_policy'] = 'never'; rpc.config['model_provider'] = 'different-provider'
    with pytest.raises(LaunchError, match='startup_changed:model_provider'):
        observe(req, rpc, startup)


@pytest.mark.parametrize('params', [{'threadId': SID, 'includeTurns': True},
    {'threadId': SID, 'includeTurns': False, 'model': 'override'},
    {'threadId': 'not-a-thread-id', 'includeTurns': False}])
def test_continuation_model_rpc_surface_rejects_history_or_overrides(params):
    rpc = object.__new__(StdioRpc)
    rpc._request = lambda *a, **k: pytest.fail('Unqualified request reached transport')
    with pytest.raises(LaunchError): rpc.call('thread/read', params)


def test_continuation_model_unsupported_readback_is_unknown(tmp_path):
    req, rpc, startup = existing_fixture(tmp_path)
    call = rpc.call
    def unsupported(method, params, **kwargs):
        if method == 'thread/read':
            raise LaunchError('provider_rpc_error', status='UNAVAILABLE', receipt={'rpc_error_code': -32601})
        return call(method, params, **kwargs)
    rpc.call = unsupported
    with pytest.raises(LaunchError) as error:
        observe(req, rpc, startup)
    assert error.value.code == 'current_thread_readback_unavailable' and error.value.status == 'UNKNOWN'


def test_continuation_model_release_mirrors_and_actual_mcp_reader():
    from pathlib import Path
    import tomllib
    from agent_os import __version__
    from agent_os.mcp_server import response
    root = Path(__file__).resolve().parents[1]
    assert tomllib.loads((root/'pyproject.toml').read_text())['project']['version'] == __version__
    for name in ['cli-contract-v1.json', 'mcp-tools-v1.json']:
        first = json.loads((root/'schemas'/name).read_text())
        assert first == json.loads((root/'src/agent_os/resources/contracts'/name).read_text())
        assert (first['release'] if name.startswith('cli-') else first['serverInfo']['version']) == __version__
    assert response({'jsonrpc':'2.0','id':1,'method':'initialize'})['result']['serverInfo']['version'] == __version__


def test_continuation_model_invalid_defaults_are_not_retained_raw(tmp_path):
    req, rpc, startup = existing_fixture(tmp_path)
    rpc.config.update(model={"PRIVATE_FIXTURE": "payload"}, model_reasoning_effort="PRIVATE_FIXTURE " * 100)
    observed, _, _ = observe(req, rpc, startup)
    metadata = observed['model_preflight']
    assert metadata['configured_model'] is None
    assert metadata['configured_reasoning_effort'] is None
    assert 'PRIVATE_FIXTURE' not in json.dumps(observed)
