"""Concrete adapter fixtures: real local stdio, no Codex/auth/network calls."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import shlex
import time

import pytest

from agent_os.codex_launch import CodexLaunchProvider, StdioRpc, _commands
from agent_os.config import default_config
from agent_os.session_hub import CodexRunner, discover_sessions
from agent_os.session_launch import LaunchError, launch

PEER = r'''
import json, pathlib, shlex, subprocess, sys
mode = MODE
trace = pathlib.Path(TRACE)
def log(value):
 with trace.open('a') as f: f.write(json.dumps(value)+'\n')
if sys.argv[1:] == ['--version']:
 print('codex-cli 9.99.1'); sys.exit(0)
assert sys.argv[1:] == ['app-server']
def send(value): print(json.dumps(value),flush=True)
turns=0
cwd=str(pathlib.Path.cwd())
for line in sys.stdin:
 m=json.loads(line); log(m)
 if m['method']=='initialized': continue
 method=m['method']
 if method=='initialize': result={'userAgent':'synthetic-peer/9.99.1'}
 elif method=='config/read':
  assert m['params']=={'includeLayers':False,'cwd':cwd}
  result={'config':{'approval_policy': 'untrusted' if mode=='interactive' else 'never',
                    'sandbox_mode':'workspace-write','sandbox_workspace_write':{'network_access':True},
                    'model':'fixture-model','model_provider':'openai','model_reasoning_effort':'medium',
                    'unrelated_private_key':'SYNTHETIC_NOT_TO_RETAIN'}}
  if mode=='missing-policy': del result['config']['approval_policy']
  if mode in {'default-provider','unavailable-model'}: result['config']['model_provider']=None
  if mode=='unavailable-model': result['config']['model']='fixture-unavailable'
 elif method=='model/list':
  assert set(m['params'])=={'cursor','limit','includeHidden'}
  assert m['params']['includeHidden'] is True and m['params']['cursor'] is None
  result={'data':[{'id':'fixture-model','model':'fixture-model','displayName':'Fixture model',
                   'description':'Synthetic test model only','hidden':False,'isDefault':True,
                   'defaultReasoningEffort':'medium',
                   'supportedReasoningEfforts':[{'reasoningEffort':'medium','description':'Fixture medium'}]}],
          'nextCursor':None}
 elif method=='thread/start':
  assert m['params']=={'cwd':cwd}
  result={'thread':{'id':'fixture-thread'},'cwd':cwd,'approvalPolicy':'never',
          'model':'fixture-model','modelProvider':'openai','reasoningEffort':'medium',
          'sandbox':{'type':'workspaceWrite','writableRoots':[cwd],'networkAccess':True}}
  if mode=='default-provider': result['modelProvider']='fixture-inherited-provider'
  if mode=='changed-startup': result['sandbox']['type']='readOnly'
 elif method=='turn/start':
  assert set(m['params'])=={'threadId','input'}
  turns+=1; turn='fixture-turn-'+str(turns)
  result={'turn':{'id':turn,'status':'inProgress','items':[],'error':None}}
 else: raise AssertionError(method)
 send({'id':m['id'],'result':result})
 if method!='turn/start': continue
 if mode=='manual-approval':
  send({'id':900,'method':'item/commandExecution/requestApproval','params':{'threadId':'fixture-thread','turnId':turn}})
  continue
 text=m['params']['input'][0]['text']
 if turns==1 and mode!='ack-only':
  commands=text.split('\n',1)[1].split('\n\n')
  for idx,command in enumerate(commands):
   if mode=='network-failure':
    code,output=28,'synthetic network failure'
   else:
    # Execute only the known generated fixture probes in this isolated cwd.
    argv=shlex.split(command)
    assert argv[:2]==[sys.executable,'-c']
    assert ('os.listdir' in argv[2] or 'NamedTemporaryFile' in argv[2])
    p=subprocess.run(argv,capture_output=True,text=True,timeout=3)
    code,output=p.returncode,p.stdout
   item={'type':'commandExecution','id':'fixture-tool-'+str(idx),'command':command,
         'cwd':cwd if mode!='wrong-cwd' else '/wrong-fixture-workspace',
         'status':'completed' if code==0 else 'failed','exitCode':code,'aggregatedOutput':output}
   if mode=='missing-cwd': del item['cwd']
   send({'method':'item/completed','params':{'threadId':'fixture-thread','turnId':turn,'item':item}})
 elif turns==2:
  pathlib.Path('fixture-business-dispatched.txt').write_text(text)
  send({'method':'item/completed','params':{'threadId':'fixture-thread','turnId':turn,
       'item':{'type':'agentMessage','id':'fixture-work-ack','text':'Synthetic turn acknowledged; not semantic acceptance.'}}})
 else:
  send({'method':'item/completed','params':{'threadId':'fixture-thread','turnId':turn,
       'item':{'type':'agentMessage','id':'fixture-startup-ack','text':'I can run all commands.'}}})
 send({'method':'turn/completed','params':{'threadId':'fixture-thread','turn':{'id':turn,'status':'completed'}}})
'''


def fixture_python_commands(request, attempt):
    """Keep generated probe code/evidence intact; pin this synthetic runtime."""
    commands = _commands(request, attempt)
    result = {}
    for capability, (command, marker) in commands.items():
        argv = shlex.split(command)
        assert argv[:2] == ["python3", "-c"]
        result[capability] = (shlex.join([sys.executable, *argv[1:]]), marker)
    return result


@pytest.fixture(autouse=True)
def pin_synthetic_probe_interpreter(monkeypatch):
    # These peers execute real local Python, not a real Codex tool. Record the
    # exact executable actually launched rather than relying on the user's PATH.
    monkeypatch.setattr("agent_os.codex_launch._commands", fixture_python_commands)


def fixture(tmp_path, mode="normal"):
    binary, trace = tmp_path / "fixture-codex", tmp_path / "fixture-rpc-trace.jsonl"
    source = "#!" + sys.executable + "\n" + PEER.replace("MODE", repr(mode)).replace("TRACE", repr(str(trace)))
    binary.write_text(source)
    binary.chmod(0o700)
    req = {"schema": "agentos.session-launch/v1", "launch_id": "fixture-launch",
           "original_goal": "Continue the isolated fixture comparison per kilogram.", "scope": "fixture files only",
           "authority": "fixture preparation", "context": {"accepted_answers": {"unit": "kg"}},
           "acceptance": ["Use the retained kg unit."], "workspace": str(tmp_path),
           "autonomous_ordinary_work": True, "required_capabilities": ["filesystem_read", "filesystem_write"],
           "target_gates": [], "executor": {"id": "fixture-executor", "provider": "codex-app-server-stdio",
                                            "owner_approved_ref": "fixture-owner-mode", "approved_version": "9.99.1",
                                            "approved_sandbox": "workspace-write", "approved_approval_policy": "never"}}
    return req, binary, trace


def methods(trace):
    return [json.loads(line)["method"] for line in trace.read_text().splitlines()]


@pytest.mark.parametrize("mode", ["normal", "default-provider"])
def test_real_stdio_supported_sequence_current_readback_and_actual_probe_commands(tmp_path, mode):
    req, binary, trace = fixture(tmp_path, mode)
    rpc = StdioRpc(binary, tmp_path, dict(os.environ), "9.99.1", timeout=3)
    claims = []
    try:
        receipt = launch(req, CodexLaunchProvider(rpc, work_timeout=3), dispatch_claim=lambda: claims.append("claimed"))
    finally:
        rpc.close()
    assert methods(trace) == ["initialize", "initialized", "config/read", "model/list", "thread/start", "turn/start", "turn/start"]
    assert receipt["probe"]["status"] == "PASS"
    assert len(receipt["probe"]["proofs"]) == 2
    assert claims == ["claimed"]
    assert receipt["work"]["status"] == "completed" and receipt["work_accepted"] is False
    assert receipt["work"]["completed_tool_items"] == 0
    if mode == "default-provider":
        assert receipt["startup"]["model_preflight"]["configured_provider"] is None
        assert receipt["startup"]["model_preflight"]["configured_provider_present"] is True
        assert receipt["startup"]["model_provider"] == "fixture-inherited-provider"
        assert receipt["startup"]["model_binding"]["provider_resolution"] == "startup_resolved"
    assert '"unit": "kg"' in (tmp_path / "fixture-business-dispatched.txt").read_text()
    assert "SYNTHETIC_NOT_TO_RETAIN" not in json.dumps(receipt)
    assert not list(tmp_path.glob(".agentos-probe-*"))
    assert rpc.process.returncode == 0


@pytest.mark.parametrize("mode,expected_methods", [
    ("interactive", ["initialize", "initialized", "config/read"]),
    ("missing-policy", ["initialize", "initialized", "config/read"]),
    ("changed-startup", ["initialize", "initialized", "config/read", "model/list", "thread/start"]),
    ("ack-only", ["initialize", "initialized", "config/read", "model/list", "thread/start", "turn/start"]),
    ("wrong-cwd", ["initialize", "initialized", "config/read", "model/list", "thread/start", "turn/start"]),
    ("missing-cwd", ["initialize", "initialized", "config/read", "model/list", "thread/start", "turn/start"]),
    ("network-failure", ["initialize", "initialized", "config/read", "model/list", "thread/start", "turn/start"]),
    ("manual-approval", ["initialize", "initialized", "config/read", "model/list", "thread/start", "turn/start"]),
])
def test_concrete_negative_paths_never_send_business_task_or_approval(tmp_path, mode, expected_methods):
    req, binary, trace = fixture(tmp_path, mode)
    if mode == "interactive":
        req["executor"]["approved_approval_policy"] = "untrusted"
    rpc = StdioRpc(binary, tmp_path, dict(os.environ), "9.99.1", timeout=3)
    try:
        with pytest.raises(LaunchError):
            launch(req, CodexLaunchProvider(rpc, work_timeout=3), dispatch_claim=lambda: pytest.fail("must not claim"))
    finally:
        rpc.close()
    assert methods(trace) == expected_methods
    assert not (tmp_path / "fixture-business-dispatched.txt").exists()
    assert all("method" in json.loads(line) for line in trace.read_text().splitlines())


def test_approved_version_mismatch_never_starts_provider(tmp_path):
    _, binary, trace = fixture(tmp_path)
    with pytest.raises(LaunchError, match="version_mismatch"):
        StdioRpc(binary, tmp_path, dict(os.environ), "9.99.2", timeout=2)
    assert not trace.exists()


@pytest.mark.parametrize("method,params", [
    ("thread/start", {"cwd": "/fixture", "approvalPolicy": "never"}),
    ("config/value/write", {"keyPath": "approval_policy", "value": "never"}),
    ("turn/start", {"threadId": "fixture", "input": [], "sandboxPolicy": {}}),
    ("account/login/start", {}),
])
def test_policy_auth_or_unknown_methods_have_no_transport_surface(method, params):
    rpc = object.__new__(StdioRpc)
    with pytest.raises(LaunchError, match="method_or_override_refused"):
        rpc.call(method, params)


def test_default_codexrunner_route_uses_admission_and_persistent_receipt(tmp_path, monkeypatch):
    req, binary, trace = fixture(tmp_path)
    monkeypatch.setenv("AGENTOS_USER_HOME", str(tmp_path / "agentos-state"))
    monkeypatch.delenv("AGENT_OS_HOME", raising=False)
    claimed = []
    monkeypatch.setattr("agent_os.dispatch_gate.claim", lambda *a, **k: claimed.append(a[0]))
    config = default_config()
    config["codex"].update({"executable": str(binary), "default_workspace": str(tmp_path),
                            "allowed_workspaces": [str(tmp_path)], "launch_request": req, "turn_timeout_seconds": 3})
    result = CodexRunner(config).create_session(req["original_goal"])
    assert result.status == "turn_completed_unaccepted"
    assert result.session_id == "fixture-thread"
    assert claimed == [req["original_goal"]]
    assert methods(trace).count("thread/start") == 1
    receipts = list((tmp_path / "agentos-state/state/session-launch").glob("*.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text())["phase"] == "DISPATCH_OBSERVED"


def test_missing_request_never_launches_but_discovery_stays_read_only(tmp_path, monkeypatch):
    config = default_config()
    config["codex"].update({"default_workspace": str(tmp_path), "allowed_workspaces": [str(tmp_path)],
                            "session_roots": [str(tmp_path / "empty-sessions")]})
    monkeypatch.setattr("agent_os.codex_launch.subprocess.Popen", lambda *a, **k: pytest.fail("no process launch"))
    with pytest.raises(LaunchError, match="request_required"):
        CodexRunner(config).create_session("hello")
    assert discover_sessions(config) == []


@pytest.mark.parametrize("url", ["http://example.test", "https://user:password@example.test", "https://example.test/?token=x", "https://example.test/#secret"])
def test_network_probe_does_not_accept_credentials_or_unbound_url(tmp_path, url):
    req, _, _ = fixture(tmp_path)
    req["required_capabilities"] = ["network_http"]
    req["probe_url"] = url
    with pytest.raises(LaunchError, match="harmless_https_probe_url_required"):
        _commands(req, "fixture-attempt")


def test_browser_capability_is_unknown_in_this_narrow_adapter(tmp_path):
    req, _, _ = fixture(tmp_path)
    req["required_capabilities"] = ["browser"]
    with pytest.raises(LaunchError, match="capability_unsupported:browser"):
        _commands(req, "fixture-attempt")


def test_read_timeout_is_bounded_and_reaps_only_fixture_child(tmp_path):
    _, binary, trace = fixture(tmp_path)
    peer = r'''
import json, os, pathlib, sys, threading
trace = pathlib.Path(TRACE)
def log(value):
    with trace.open('a') as stream:
        stream.write(json.dumps(value) + '\n')
def send(value):
    print(json.dumps(value), flush=True)
if sys.argv[1:] == ['--version']:
    log({'stage': 'version', 'python': sys.executable})
    print('codex-cli 9.99.1')
    raise SystemExit(0)
assert sys.argv[1:] == ['app-server']
log({'stage': 'app-server', 'pid': os.getpid(), 'python': sys.executable})
for line in sys.stdin:
    message = json.loads(line)
    log({'stage': message['method']})
    if message['method'] == 'initialize':
        send({'id': message['id'], 'result': {'userAgent': 'synthetic-stalled-peer'}})
    elif message['method'] == 'initialized':
        # The test observes this marker with its startup budget before it starts
        # the short read deadline. No child or worker process is spawned here.
        send({'method': 'fixture/stall-ready', 'params': {'pid': os.getpid()}})
        threading.Event().wait()
    else:
        raise AssertionError(message['method'])
'''
    binary.write_text("#!" + sys.executable + "\n" + peer.replace("TRACE", repr(str(trace))))
    # Python startup and the initialize/initialized exchange have their own
    # realistic bounded budget. The deliberately stalled operation is separate.
    rpc = StdioRpc(binary, tmp_path, dict(os.environ), "9.99.1", timeout=10)
    process = rpc.process
    try:
        ready = rpc._receive(time.monotonic() + 10)
        assert ready == {"method": "fixture/stall-ready", "params": {"pid": process.pid}}
        assert process.poll() is None
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        assert [row["stage"] for row in rows] == ["version", "app-server", "initialize", "initialized"]
        assert rows[0]["python"] == sys.executable == rows[1]["python"]
        rpc.timeout = .05
        started = time.monotonic()
        with pytest.raises(TimeoutError, match="codex_stdio_read_timeout"):
            rpc.call("config/read", {"includeLayers": False, "cwd": str(tmp_path)})
        assert time.monotonic() - started < 5
    finally:
        rpc.close()
    assert process.returncode is not None
    assert process.wait(timeout=1) == process.returncode
    # waitpid proves this exact real child is already reaped. The stalled peer
    # never spawns children, so it cannot leave an orphan fixture subprocess.
    with pytest.raises(ChildProcessError):
        os.waitpid(process.pid, os.WNOHANG)
    assert process.stdin.closed and process.stdout.closed


def test_probe_rejects_shell_startup_changing_actual_cwd(tmp_path):
    req, _, _ = fixture(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    script, _ = fixture_python_commands(req, "fixture-attempt")["filesystem_read"]
    completed = subprocess.run(shlex.split(script), cwd=other, capture_output=True, text=True, timeout=3)
    assert completed.returncode != 0
    assert "AssertionError" in completed.stderr


def catalog_row(name="fixture-model", *, identifier=None, default=True):
    """Only fields present in both supplied generated ModelListResponse schemas."""
    return {"id": identifier or name, "model": name, "displayName": "Synthetic model",
            "description": "Isolated fixture only", "hidden": False, "isDefault": default,
            "defaultReasoningEffort": "medium",
            "supportedReasoningEfforts": [{"reasoningEffort": "medium", "description": "Fixture medium"}]}


class CatalogRpc:
    """In-memory protocol responses; no real provider or model acceptance claim."""
    connection_id = "fixture-catalog-connection"
    version = "9.99.1"
    timeout = 3

    def __init__(self, request, *, config=None, pages=None, startup=None):
        self.calls = []
        self.config = {"approval_policy": "never", "sandbox_mode": "workspace-write",
                       "sandbox_workspace_write": {"network_access": True}, "model": "fixture-model",
                       "model_provider": "openai", "model_reasoning_effort": "medium"}
        if config:
            self.config.update(config)
        self.pages = pages or {None: {"data": [catalog_row()], "nextCursor": None}}
        self.startup = {"thread": {"id": "fixture-catalog-thread"}, "cwd": request["workspace"],
                        "approvalPolicy": "never", "sandbox": {"type": "workspaceWrite", "networkAccess": True},
                        "model": "fixture-model", "modelProvider": "openai", "reasoningEffort": "medium"}
        if startup:
            self.startup.update(startup)

    def call(self, method, params, *, deadline=None):
        self.calls.append((method, copy.deepcopy(params)))
        if method == "config/read":
            return {"config": copy.deepcopy(self.config)}
        if method == "model/list":
            assert deadline is not None and 0 < deadline - time.monotonic() <= self.timeout
            assert set(params) == {"cursor", "limit", "includeHidden"}
            assert params["limit"] == 100 and params["includeHidden"] is True
            return copy.deepcopy(self.pages[params["cursor"]])
        if method == "thread/start":
            assert set(params) == {"cwd"}
            return copy.deepcopy(self.startup)
        pytest.fail("Unexpected task, setter or transport operation: " + method)


def test_real_stdio_unavailable_inherited_model_refuses_thread_and_business_task(tmp_path):
    req, binary, trace = fixture(tmp_path, "unavailable-model")
    rpc = StdioRpc(binary, tmp_path, dict(os.environ), "9.99.1", timeout=3)
    try:
        with pytest.raises(LaunchError) as error:
            launch(req, CodexLaunchProvider(rpc), dispatch_claim=lambda: pytest.fail("Unqualified model cannot claim"))
    finally:
        rpc.close()
    # The protocol catalog has no provider namespace. Absence blocks creation
    # without claiming that an unqualified custom-provider model cannot exist.
    assert error.value.status == "UNKNOWN"
    assert error.value.code == "inherited_model_not_advertised"
    assert methods(trace) == ["initialize", "initialized", "config/read", "model/list"]
    assert not error.value.receipt["provider_mutation_started"]
    assert not (tmp_path / "fixture-business-dispatched.txt").exists()
    assert rpc.process.returncode == 0


@pytest.mark.parametrize("terminal_cursor_present", [True, False])
def test_catalog_pagination_is_complete_on_same_connection_before_startup(tmp_path, terminal_cursor_present):
    req, _, _ = fixture(tmp_path)
    terminal = {"data": [catalog_row()]}
    if terminal_cursor_present:
        terminal["nextCursor"] = None
    rpc = CatalogRpc(req, pages={None: {"data": [catalog_row("fixture-other", default=False)], "nextCursor": "second"},
                                "second": terminal})
    provider = CodexLaunchProvider(rpc)
    before = provider.describe(req, "catalog-attempt")
    assert [method for method, _ in rpc.calls] == ["config/read", "model/list", "model/list"]
    assert [params["cursor"] for method, params in rpc.calls if method == "model/list"] == [None, "second"]
    assert before["model"] == "fixture-model" and before["model_provider"] == "openai"
    assert before["model_preflight"]["catalog_complete"] is True
    startup = provider.create(req, "catalog-attempt")
    assert startup["model"] == "fixture-model" and startup["model_provider"] == "openai"
    assert startup["reasoning_effort"] == "medium"
    assert before["connection_id"] == startup["connection_id"] == rpc.connection_id
    assert rpc.calls[-1][0] == "thread/start"


def test_catalog_with_pending_cursor_cannot_claim_compatibility_even_when_model_is_listed(tmp_path):
    req, _, _ = fixture(tmp_path)
    rpc = CatalogRpc(req, pages={None: {"data": [catalog_row()], "nextCursor": "repeat"},
                                "repeat": {"data": [], "nextCursor": "repeat"}})
    provider = CodexLaunchProvider(rpc)
    with pytest.raises(LaunchError) as error:
        provider.describe(req, "catalog-attempt")
    assert error.value.status == "UNKNOWN"
    assert 1 < sum(method == "model/list" for method, _ in rpc.calls) <= 4
    assert all(method != "thread/start" for method, _ in rpc.calls)


@pytest.mark.parametrize("cursor", ["", False, 42, [], "x" * 4097])
def test_invalid_non_null_cursor_is_unknown_even_when_model_is_listed(tmp_path, cursor):
    req, _, _ = fixture(tmp_path)
    rpc = CatalogRpc(req, config={"model_provider": None},
                     pages={None: {"data": [catalog_row()], "nextCursor": cursor}})
    with pytest.raises(LaunchError) as error:
        CodexLaunchProvider(rpc).describe(req, "catalog-attempt")
    assert error.value.status == "UNKNOWN"
    assert error.value.code == "model_catalog_cursor_invalid"
    assert [method for method, _ in rpc.calls] == ["config/read", "model/list"]


@pytest.mark.parametrize("limit", ["pages", "entries"])
def test_pending_catalog_limits_refuse_before_thread_even_with_retained_model(tmp_path, limit):
    req, _, _ = fixture(tmp_path)
    if limit == "pages":
        pages = {None: {"data": [catalog_row()], "nextCursor": "page-2"},
                 "page-2": {"data": [], "nextCursor": "page-3"},
                 "page-3": {"data": [], "nextCursor": "page-4"},
                 "page-4": {"data": [], "nextCursor": "page-5"}}
        expected_calls, code = 4, "model_catalog_page_limit"
    else:
        rows = [catalog_row()] + [catalog_row("fixture-model-" + str(i), default=False) for i in range(256)]
        pages = {None: {"data": rows[:100], "nextCursor": "page-2"},
                 "page-2": {"data": rows[100:200], "nextCursor": "page-3"},
                 "page-3": {"data": rows[200:]}}  # Omitted cursor does not waive the entry limit.
        expected_calls, code = 3, "model_catalog_entry_limit"
    rpc = CatalogRpc(req, config={"model_provider": None}, pages=pages)
    with pytest.raises(LaunchError) as error:
        CodexLaunchProvider(rpc).describe(req, "catalog-attempt")
    assert error.value.status == "UNKNOWN" and error.value.code == code
    assert [method for method, _ in rpc.calls] == ["config/read"] + ["model/list"] * expected_calls


def test_missing_configured_model_uses_only_unique_catalog_default_and_records_provenance(tmp_path):
    req, _, _ = fixture(tmp_path)
    rpc = CatalogRpc(req, config={"model": None, "model_reasoning_effort": None},
                     startup={"reasoningEffort": None})
    provider = CodexLaunchProvider(rpc)
    observed = provider.describe(req, "catalog-attempt")
    assert observed["model"] == "fixture-model"
    assert observed["model_preflight"]["model_source"] == "catalog_default"
    assert observed["model_preflight"]["configured_model"] is None
    startup = provider.create(req, "catalog-attempt")
    assert startup["model"] == "fixture-model"
    # A catalog default does not establish the actual thread's effort.
    assert startup["reasoning_effort"] is None


@pytest.mark.parametrize("rows", [
    [catalog_row(default=False)],
    [catalog_row(), catalog_row("fixture-second-default")],
])
def test_missing_model_without_unique_default_is_unknown(tmp_path, rows):
    req, _, _ = fixture(tmp_path)
    rpc = CatalogRpc(req, config={"model": None}, pages={None: {"data": rows, "nextCursor": None}})
    with pytest.raises(LaunchError) as error:
        CodexLaunchProvider(rpc).describe(req, "catalog-attempt")
    assert error.value.status == "UNKNOWN"
    assert all(method != "thread/start" for method, _ in rpc.calls)


def test_id_only_alias_is_unknown_and_never_rewrites_selected_model(tmp_path):
    req, _, _ = fixture(tmp_path)
    rpc = CatalogRpc(req, config={"model": "fixture-picker-id"},
                     pages={None: {"data": [catalog_row(identifier="fixture-picker-id")], "nextCursor": None}})
    with pytest.raises(LaunchError) as error:
        CodexLaunchProvider(rpc).describe(req, "catalog-attempt")
    assert error.value.status == "UNKNOWN"
    assert rpc.config["model"] == "fixture-picker-id"
    assert all(method != "thread/start" for method, _ in rpc.calls)


def test_display_name_and_upgrade_metadata_are_not_model_aliases(tmp_path):
    req, _, _ = fixture(tmp_path)
    row = catalog_row("fixture-other")
    row.update(displayName="fixture-model", upgrade="fixture-model", upgradeInfo={"model": "fixture-model"})
    rpc = CatalogRpc(req, pages={None: {"data": [row], "nextCursor": None}})
    with pytest.raises(LaunchError) as error:
        CodexLaunchProvider(rpc).describe(req, "catalog-attempt")
    assert error.value.status == "UNKNOWN"
    assert error.value.code == "inherited_model_not_advertised"
    assert all(method != "thread/start" for method, _ in rpc.calls)


@pytest.mark.parametrize("configured_present,actual_provider", [
    (True, "fixture-inherited-alpha"), (False, "fixture-inherited-beta"),
])
def test_unconfigured_provider_is_provisional_until_required_actual_startup(tmp_path, configured_present, actual_provider):
    req, _, _ = fixture(tmp_path)
    rpc = CatalogRpc(req, config={"model_provider": None},
                     pages={None: {"data": [catalog_row()]}}, startup={"modelProvider": actual_provider})
    if not configured_present:
        del rpc.config["model_provider"]
    unchanged_config = copy.deepcopy(rpc.config)
    provider = CodexLaunchProvider(rpc)
    before = provider.describe(req, "catalog-attempt")
    assert [method for method, _ in rpc.calls] == ["config/read", "model/list"]
    assert before["model_provider"] is None
    assert before["model_preflight"]["configured_provider"] is None
    assert before["model_preflight"]["configured_provider_present"] is configured_present
    assert before["model_preflight"]["provider_source"] == "unconfigured"
    assert actual_provider not in json.dumps(before)
    startup = provider.create(req, "catalog-attempt")
    assert startup["model_provider"] == actual_provider
    assert startup["model_preflight"]["configured_provider"] is None
    assert startup["model_preflight"]["configured_provider_present"] is configured_present
    assert startup["model_metadata_source"] == "thread_start_response"
    assert startup["model_binding"]["provider_resolution"] == "startup_resolved"
    assert before["connection_id"] == startup["connection_id"] == rpc.connection_id
    assert rpc.config == unchanged_config
    assert [method for method, _ in rpc.calls] == ["config/read", "model/list", "thread/start"]


@pytest.mark.parametrize("value", ["", False, 42])
def test_invalid_explicit_provider_is_not_treated_as_unconfigured(tmp_path, value):
    req, _, _ = fixture(tmp_path)
    rpc = CatalogRpc(req, config={"model_provider": value})
    with pytest.raises(LaunchError) as error:
        CodexLaunchProvider(rpc).describe(req, "catalog-attempt")
    assert error.value.status == "UNKNOWN" and error.value.code == "inherited_model_provider_unknown"
    assert [method for method, _ in rpc.calls] == ["config/read"]


@pytest.mark.parametrize("changes", [{"model": "fixture-other"}, {"modelProvider": "fixture-other-provider"},
                                    {"reasoningEffort": "high"}])
def test_startup_model_provider_or_explicit_effort_drift_blocks_probe(tmp_path, changes):
    req, _, _ = fixture(tmp_path)
    rpc = CatalogRpc(req, startup=changes)
    provider = CodexLaunchProvider(rpc)
    provider.describe(req, "catalog-attempt")
    with pytest.raises(LaunchError) as error:
        provider.create(req, "catalog-attempt")
    assert error.value.status == "MISMATCH"
    assert error.value.receipt["startup"]["session_id"] == "fixture-catalog-thread"
    assert error.value.receipt["startup"]["connection_id"] == rpc.connection_id
    assert error.value.receipt["startup"]["model_preflight"]["configured_provider"] == "openai"
    with pytest.raises(LaunchError, match="thread_start_requires_reconciliation"):
        provider.create(req, "catalog-attempt")
    assert [method for method, _ in rpc.calls] == ["config/read", "model/list", "thread/start"]


@pytest.mark.parametrize("field,present", [("model", False), ("modelProvider", False), ("modelProvider", True)])
def test_missing_actual_startup_model_metadata_is_unknown(tmp_path, field, present):
    req, _, _ = fixture(tmp_path)
    rpc = CatalogRpc(req, config={"model_provider": None})
    if present:
        rpc.startup[field] = None
    else:
        del rpc.startup[field]
    provider = CodexLaunchProvider(rpc)
    provider.describe(req, "catalog-attempt")
    with pytest.raises(LaunchError) as error:
        provider.create(req, "catalog-attempt")
    assert error.value.status == "UNKNOWN"
    assert error.value.receipt["startup"]["session_id"] == "fixture-catalog-thread"
    assert error.value.receipt["startup"]["model_preflight"]["configured_provider"] is None
    expected_provider = None if field == "modelProvider" else "openai"
    assert error.value.receipt["startup"]["model_provider"] == expected_provider
    with pytest.raises(LaunchError, match="thread_start_requires_reconciliation"):
        provider.create(req, "catalog-attempt")
    assert [method for method, _ in rpc.calls] == ["config/read", "model/list", "thread/start"]


def test_model_list_has_no_provider_model_or_auth_override_surface():
    rpc = object.__new__(StdioRpc)
    with pytest.raises(LaunchError, match="method_or_override_refused"):
        rpc.call("model/list", {"cursor": None, "limit": 100, "includeHidden": True,
                                "modelProvider": "unapproved-provider"})


def test_failed_probe_retains_safe_http_category_without_raw_provider_error(tmp_path):
    req, _, _ = fixture(tmp_path)
    provider = CodexLaunchProvider(CatalogRpc(req))
    secret = "SYNTHETIC_SECRET_MUST_NOT_BE_RETAINED"
    failure = {"message": json.dumps({"type": "error", "status": 400,
                                     "error": {"type": "invalid_request_error",
                                               "message": "The selected model is not supported. " + secret}}),
               "codexErrorInfo": "other", "additionalDetails": "https://invalid.test/?token=" + secret}
    provider._turn = lambda session, prompt, timeout: ("failed-fixture-turn", [
        {"method": "turn/completed", "params": {"threadId": session,
         "turn": {"id": "failed-fixture-turn", "status": "failed", "error": failure}}}])
    result = provider.probe(req, {"session_id": "fixture-catalog-thread"}, "catalog-attempt")
    assert result["status"] == "FAIL" and not result["proofs"]
    assert result["failure"]["http_status"] == 400
    assert result["failure"]["category"] == "invalid_request"
    assert result["failure"]["codex_error_info"] == "other"
    assert secret not in json.dumps(result)
    assert "https://" not in json.dumps(result)
    assert result["turn_id"] == "failed-fixture-turn"


def test_unrecognized_failed_turn_fields_remain_unknown_without_copying_strings(tmp_path):
    req, _, _ = fixture(tmp_path)
    provider = CodexLaunchProvider(CatalogRpc(req))
    secret = "SYNTHETIC_UNRECOGNIZED_SECRET"
    provider._turn = lambda session, prompt, timeout: ("failed-work-turn", [
        {"method": "turn/completed", "params": {"threadId": session,
         "turn": {"id": "failed-work-turn", "status": "failed",
                  "error": {"message": secret, "codexErrorInfo": secret}}}}])
    result = provider.dispatch(req, {"session_id": "fixture-catalog-thread"}, "Fixture-only original goal")
    assert result["status"] == "failed"
    assert result["failure"]["category"] == "provider_error"
    assert result["failure"]["codex_error_info"] == "unknown"
    assert secret not in json.dumps(result)
    assert result["semantic_acceptance"] == "NOT_EVALUATED"
