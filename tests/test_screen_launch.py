"""Real isolated subprocess lifecycle; GNU Screen and Codex are synthetic peers.

Only fixture-owned processes and files are created/cleaned. This is not a live
GNU Screen, Codex, approval-policy or host-adoption acceptance test.
"""
from __future__ import annotations

import copy
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agent_os.safeio import atomic_json, digest
from agent_os.screen_launch import ScreenLaunchProvider, continue_managed, create_screen, registry_session
from agent_os.session_launch import LaunchError

SCREEN = r'''
import json, os, pathlib, signal, subprocess, sys
root=pathlib.Path(os.environ['FIXTURE_SCREEN_REGISTRY'])
if sys.argv[1:]==['-ls']:
 count=0
 for path in root.glob('*.json'):
  item=json.loads(path.read_text())
  try: os.kill(item['pid'],0)
  except ProcessLookupError: continue
  print('\t'+str(item['pid'])+'.'+item['name']+'\t(10/03/2026 00:00:00)\t(Detached)'); count+=1
 sys.exit(0 if count else 1)
assert sys.argv[1:4]==['-D','-m','-S']
name=sys.argv[4]; assert sys.argv[5:7]==['-c',os.devnull]
assert os.environ['SYSSCREENRC']==os.devnull and os.environ['SYSTEM_SCREENRC']==os.devnull
assert sys.argv[7]==sys.executable
path=root/(name+'.json'); path.write_text(json.dumps({'pid':os.getpid(),'name':name}))
env=dict(os.environ); env['STY']=str(os.getpid())+'.'+name
worker=subprocess.Popen(sys.argv[7:],env=env)
def stop(*args):
 worker.terminate()
signal.signal(signal.SIGTERM,stop)
try: result=worker.wait()
finally: path.unlink(missing_ok=True)
sys.exit(result)
'''

CODEX = r'''
import json, os, pathlib, shlex, subprocess, sys
root=pathlib.Path(os.environ['FIXTURE_SCREEN_REGISTRY'])
trace=root/'rpc.jsonl'
def log(message):
 with trace.open('a') as f: f.write(json.dumps(message)+'\n')
def send(value): print(json.dumps(value),flush=True)
if sys.argv[1:]==['--version']:
 print('codex-cli 9.99.1'); sys.exit(0)
assert sys.argv[1:]==['app-server']; log({'fixture_provider_pid':os.getpid()})
mode=os.environ.get('FIXTURE_MODE','normal'); count=0; cwd=str(pathlib.Path.cwd())
for line in sys.stdin:
 m=json.loads(line); log(m); method=m['method']
 if method=='initialized': continue
 if method=='initialize': result={'userAgent':'synthetic-screen-peer'}
 elif method=='config/read':
  if mode=='stall-config':
   import time
   time.sleep(1)
  result={'config':{'approval_policy':'untrusted' if mode=='interactive' else 'never','sandbox_mode':'workspace-write',
                   'sandbox_workspace_write':{'network_access':True},'model':'fixture-model',
                   'model_provider':'openai','model_reasoning_effort':'medium'}}
  if mode in {'default-provider','unavailable-model','continuation-provider-drift','missing-actual-provider','null-actual-provider'}:
   result['config']['model_provider']=None
  if mode=='unavailable-model': result['config']['model']='fixture-unavailable'
  if mode=='continuation-model-drift' and count>=2: result['config']['model']='fixture-alternate'
  if mode=='continuation-provider-drift' and count>=2: result['config']['model_provider']='fixture-other-provider'
 elif method=='model/list':
  assert set(m['params'])=={'cursor','limit','includeHidden'}
  assert m['params']['includeHidden'] is True and m['params']['cursor'] is None
  names=['fixture-model','fixture-alternate'] if mode=='continuation-model-drift' else ['fixture-model']
  result={'data':[{'id':name,'model':name,'displayName':'Synthetic model','description':'Fixture only',
                   'hidden':False,'isDefault':name=='fixture-model','defaultReasoningEffort':'medium',
                   'supportedReasoningEfforts':[{'reasoningEffort':'medium','description':'Fixture medium'}]}
                  for name in names],'nextCursor':None}
 elif method=='thread/start':
  result={'thread':{'id':'01a0a2b6-522a-7501-9a78-c093c781141e'},'cwd':cwd,'approvalPolicy':'never',
          'model':'fixture-model','modelProvider':'openai','reasoningEffort':'medium',
          'sandbox':{'type':'workspaceWrite','networkAccess':True}}
  if mode in {'default-provider','continuation-provider-drift'}: result['modelProvider']='fixture-inherited-provider'
  if mode=='missing-actual-provider': del result['modelProvider']
  if mode=='null-actual-provider': result['modelProvider']=None
 elif method=='turn/start':
  count+=1; turn='turn-'+str(count); result={'turn':{'id':turn,'status':'inProgress'}}
 else: raise AssertionError(method)
 send({'id':m['id'],'result':result})
 if method!='turn/start': continue
 prompt=m['params']['input'][0]['text']; thread=m['params']['threadId']
 def item(value): send({'method':'item/completed','params':{'threadId':thread,'turnId':turn,'item':value}})
 item({'id':'user-'+turn,'type':'userMessage','content':[{'type':'text','text':prompt}]})
 if prompt.startswith('Startup capability probe only.'):
  if mode=='approval':
   send({'id':900,'method':'item/commandExecution/requestApproval','params':{'threadId':thread,'turnId':turn}}); continue
  if mode!='ack':
   for idx, command in enumerate(prompt.split('\n',1)[1].split('\n\n')):
    argv=shlex.split(command); assert argv[:2]==['python3','-c']
    assert 'os.listdir' in argv[2] or 'NamedTemporaryFile' in argv[2]
    p=subprocess.run(argv,capture_output=True,text=True,timeout=5)
    item({'id':'command-'+turn+'-'+str(idx),'type':'commandExecution','cwd':cwd,'command':command,'status':'completed','exitCode':p.returncode,'aggregatedOutput':p.stdout})
  else: item({'id':'ack-'+turn,'type':'agentMessage','text':'I can run commands.'})
 else:
  with pathlib.Path('fixture-business.jsonl').open('a') as f: f.write(json.dumps({'turn':turn,'text':prompt})+'\n')
  item({'id':'result-'+turn,'type':'agentMessage','text':'Synthetic task turn completed; acceptance not evaluated.'})
 send({'method':'turn/completed','params':{'threadId':thread,'turn':{'id':turn,'status':'completed'}}})
'''


@pytest.fixture
def screen_fixture(tmp_path, monkeypatch):
    root = tmp_path / "fixture-registry"
    root.mkdir()
    binaries = tmp_path / "binaries"
    binaries.mkdir()
    for name, source in (("screen", SCREEN), ("codex", CODEX)):
        path = binaries / name
        path.write_text("#!" + sys.executable + "\n" + source)
        path.chmod(0o700)
    # The production probe invokes python3. Pin that real command's executable
    # in this fixture without substituting provider evidence after execution.
    (binaries / "python3").symlink_to(sys.executable)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    home = tmp_path / "user"
    env = dict(os.environ, FIXTURE_SCREEN_REGISTRY=str(root),
               PATH=str(binaries) + os.pathsep + os.environ.get("PATH", ""),
               PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    req = {"schema": "agentos.session-launch/v1", "launch_id": "screen-fixture-launch",
           "original_goal": "Use the retained kilogram unit in the isolated fixture.",
           "scope": "fixture files", "authority": "synthetic owner-approved fixture",
           "context": {"accepted_answers": {"unit": "kg"}}, "acceptance": ["Keep the kg unit"],
           "workspace": str(workspace), "required_capabilities": ["filesystem_read", "filesystem_write"],
           "autonomous_ordinary_work": True, "target_gates": [],
           "executor": {"id": "fixture-host", "provider": "codex-app-server-stdio", "transport": "gnu-screen",
                        "owner_approved_ref": "fixture-existing-mode", "approved_version": "9.99.1",
                        "approved_sandbox": "workspace-write", "approved_approval_policy": "never"}}
    fixture = dict(home=home, name="fixture", request=req, screen_binary=binaries / "screen",
                   codex_binary=binaries / "codex", environment=env, timeout=10, work_timeout=10)
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def interrupted(_signum, _frame):
        # An outer bounded runner signals this pytest process. Convert that
        # signal into normal unwinding so detached fixture children are reaped.
        raise KeyboardInterrupt("Synthetic Screen fixture interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        yield fixture
    finally:
        # A second cooperative signal must not interrupt the bounded cleanup.
        # The outer runner retains its final hard timeout; restore on every exit.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            # Terminate exactly the explicitly synthetic Screen processes this
            # fixture created. Screen reaps worker; worker reaps its stdio child.
            for path in root.glob("*.json"):
                pid = json.loads(path.read_text())["pid"]
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            deadline = time.monotonic() + 5
            while list(root.glob("*.json")) and time.monotonic() < deadline:
                time.sleep(.025)
            assert not list(root.glob("*.json")), "fixture-owned Screen/worker cleanup did not finish"
            trace = root / "rpc.jsonl"
            if trace.exists():
                for item in map(json.loads, trace.read_text().splitlines()):
                    pid = item.get("fixture_provider_pid")
                    if pid:
                        with pytest.raises(ProcessLookupError):
                            os.kill(pid, 0)
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)


def _events(fixture):
    trace = Path(fixture["environment"]["FIXTURE_SCREEN_REGISTRY"]) / "rpc.jsonl"
    return list(map(json.loads, trace.read_text().splitlines())) if trace.exists() else []


@pytest.mark.parametrize("mode", ["normal", "default-provider"])
def test_screen_persists_after_caller_exit_and_continues_with_exact_provider_proof(screen_fixture, mode):
    fixture = screen_fixture
    fixture["environment"]["FIXTURE_MODE"] = mode
    config_path = Path(fixture["environment"]["FIXTURE_SCREEN_REGISTRY"]) / "invoke-input.json"
    # Store outside the Screen registry's *.json inventory.
    config_path = config_path.with_suffix(".input")
    atomic_json(config_path, {key: str(value) if isinstance(value, Path) else value for key, value in fixture.items()})
    child = r'''
import json,sys
from pathlib import Path
from agent_os.screen_launch import create_screen
args=json.loads(Path(sys.argv[1]).read_text())
for key in ('home','screen_binary','codex_binary'): args[key]=Path(args[key])
receipt=create_screen(**args,dispatch_claim=lambda:None)
print(json.dumps(receipt))
'''
    result = subprocess.run([sys.executable, "-c", child, str(config_path)], env=fixture["environment"],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["probe"]["status"] == "PASS"
    assert receipt["work"]["status"] == "completed" and receipt["work"]["delivery"] == "accepted"
    assert receipt["work_accepted"] is False
    socket = receipt["screen"]["socket"]
    assert registry_session(fixture["home"], socket) == receipt["session_id"]
    continuation = continue_managed(fixture["home"], socket, "Review the fixture result and retain kg.",
                                    screen_binary=fixture["screen_binary"], environment=fixture["environment"],
                                    dispatch_claim=lambda request, session_id: None)
    assert continuation["probe"]["status"] == "PASS"
    assert continuation["work"]["delivery"] == "accepted"
    assert continuation["work_accepted"] is False
    if mode == "default-provider":
        startup = receipt["startup"]
        assert startup["model_provider"] == "fixture-inherited-provider"
        assert startup["model_preflight"]["configured_provider"] is None
        assert startup["model_preflight"]["configured_provider_present"] is True
        assert startup["model_binding"]["provider_resolution"] == "startup_resolved"
        assert continuation["current_preflight"]["model_provider"] is None
        assert continuation["original_startup"] == startup
        assert continuation["session_id"] == startup["session_id"] == receipt["session_id"]
        assert continuation["current_preflight"]["connection_id"] == startup["connection_id"]
        assert continuation["model_binding"]["provider_resolution"] == "startup_resolved"
    methods = [event["method"] for event in _events(fixture) if "method" in event]
    assert methods == ["initialize", "initialized", "config/read", "model/list", "thread/start", "turn/start", "turn/start",
                       "config/read", "model/list", "turn/start", "turn/start"]
    work = list(map(json.loads, (Path(fixture["request"]["workspace"]) / "fixture-business.jsonl").read_text().splitlines()))
    assert len(work) == 2 and all("kg" in item["text"] for item in work)
    with pytest.raises(LaunchError, match="screen_continuation_requires_reconciliation"):
        continue_managed(fixture["home"], socket, "Review the fixture result and retain kg.",
                         screen_binary=fixture["screen_binary"], environment=fixture["environment"],
                         dispatch_claim=lambda *args: None)


@pytest.mark.parametrize("mode,expected", [("interactive", "inherited_approval_policy_not_owner_selected"),
                                           ("ack", "harmless_probe_failed"),
                                           ("approval", "provider_approval_or_input_pending")])
def test_screen_rejects_without_business_dispatch(screen_fixture, mode, expected):
    fixture = screen_fixture
    fixture["environment"]["FIXTURE_MODE"] = mode
    with pytest.raises(LaunchError, match=expected):
        create_screen(**fixture, dispatch_claim=lambda: pytest.fail("claim before admission"))
    methods = [event.get("method") for event in _events(fixture)]
    if mode == "interactive":
        assert "thread/start" not in methods
    assert not (Path(fixture["request"]["workspace"]) / "fixture-business.jsonl").exists()


def test_screen_duplicate_name_and_unprobed_dispatch_are_rejected(screen_fixture):
    fixture = screen_fixture
    provider = ScreenLaunchProvider.start(**fixture)
    with pytest.raises(LaunchError, match="screen_name_exists_reconciliation_required"):
        ScreenLaunchProvider.start(**fixture)
    provider.describe(fixture["request"], "bound-attempt")
    startup = provider.create(fixture["request"], "bound-attempt")
    with pytest.raises(LaunchError, match="screen_dispatch_without_successful_probe"):
        provider.dispatch(fixture["request"], startup, fixture["request"]["original_goal"])
    assert not (Path(fixture["request"]["workspace"]) / "fixture-business.jsonl").exists()


def test_screen_pending_operation_requires_reconciliation(screen_fixture):
    provider = ScreenLaunchProvider.start(**screen_fixture)
    atomic_json(provider.root / "pending.json", {"operation_id": "fixture-uncertain", "status": "PENDING"})
    with pytest.raises(LaunchError, match="screen_previous_operation_requires_reconciliation"):
        provider.describe(screen_fixture["request"], "next-attempt")
    assert provider.status()["pending"]["operation_id"] == "fixture-uncertain"
    assert not any(item.get("method") == "config/read" for item in _events(screen_fixture))


def test_screen_requires_explicit_transport_without_starting(screen_fixture):
    fixture = copy.deepcopy(screen_fixture)
    del fixture["request"]["executor"]["transport"]
    with pytest.raises(LaunchError, match="owner_selected_screen_transport_required"):
        create_screen(**fixture, dispatch_claim=lambda: None)
    assert _events(fixture) == []


def test_actual_mailbox_timeout_preserves_pending_and_refuses_replay(screen_fixture):
    screen_fixture["environment"]["FIXTURE_MODE"] = "stall-config"
    provider = ScreenLaunchProvider.start(**screen_fixture)
    provider.timeout = .05  # Only after the actual worker/stdio READY handshake.
    with pytest.raises(LaunchError, match="screen_operation_timeout_reconciliation_required"):
        provider.describe(screen_fixture["request"], "stalled-attempt")
    with pytest.raises(LaunchError, match="screen_previous_operation_requires_reconciliation"):
        provider.describe(screen_fixture["request"], "accidental-retry")
    pending = provider.status()["pending"]
    assert pending["status"] == "PENDING" and pending["operation"] == "describe"


def test_reused_launch_journal_refuses_even_a_new_screen_name(screen_fixture):
    first = create_screen(**screen_fixture, dispatch_claim=lambda: None)
    changed = dict(screen_fixture, name="second-screen")
    with pytest.raises(LaunchError, match="previous_launch_requires_reconciliation"):
        create_screen(**changed, dispatch_claim=lambda: None)
    assert not (screen_fixture["home"] / "state/screen-workers/second-screen").exists()
    assert first["screen"]["status"] == "READY"


def test_multiline_original_goal_and_independent_continuation_gate(screen_fixture):
    fixture = screen_fixture
    fixture["request"]["original_goal"] = 'Retain "kg" unit.\nUse the original comparison goal.'
    fixture["request"]["target_gates"] = ["fixture-financial-gate"]
    allowed = True

    def guard(request, phase):
        attempt = request.pop("_launch_attempt_id")
        return {"source": "target_readback", "attempt_id": attempt, "observed_at": time.time(),
                "request_sha256": digest(request), "phase": phase,
                "gates": {"fixture-financial-gate": {"status": "PASS" if allowed else "BLOCKED", "evidence_ref": "fixture-target-receipt"}}}

    result = create_screen(**fixture, dispatch_claim=lambda: None, target_guard=guard)
    socket = result["screen"]["socket"]
    ok = continue_managed(fixture["home"], socket, "Review existing results.",
                          screen_binary=fixture["screen_binary"], environment=fixture["environment"],
                          dispatch_claim=lambda *args: None, target_guard=guard)
    assert ok["work"]["status"] == "completed"
    allowed = False
    with pytest.raises(LaunchError, match="target_gate_unsatisfied") as error:
        continue_managed(fixture["home"], socket, "A later gated step.",
                         screen_binary=fixture["screen_binary"], environment=fixture["environment"],
                         dispatch_claim=lambda *args: pytest.fail("blocked target must not claim"), target_guard=guard)
    assert error.value.status == "BLOCKED"
    journals = list((fixture["home"] / "state/screen-workers/fixture/continuations").glob("*.json"))
    assert "BLOCKED" in {json.loads(path.read_text())["status"] for path in journals}
    assert len((Path(fixture["request"]["workspace"]) / "fixture-business.jsonl").read_text().splitlines()) == 2


def test_screen_unavailable_inherited_model_stops_before_thread_creation(screen_fixture):
    fixture = screen_fixture
    fixture["environment"]["FIXTURE_MODE"] = "unavailable-model"
    with pytest.raises(LaunchError) as error:
        create_screen(**fixture, dispatch_claim=lambda: pytest.fail("Unqualified model must not claim"))
    assert error.value.status == "UNKNOWN"
    assert error.value.code == "inherited_model_not_advertised"
    methods = [event["method"] for event in _events(fixture) if "method" in event]
    assert methods == ["initialize", "initialized", "config/read", "model/list"]
    assert not (Path(fixture["request"]["workspace"]) / "fixture-business.jsonl").exists()


@pytest.mark.parametrize("mode", ["missing-actual-provider", "null-actual-provider"])
def test_screen_unconfigured_provider_requires_actual_startup_before_probe_and_keeps_thread(screen_fixture, mode):
    fixture = screen_fixture
    fixture["environment"]["FIXTURE_MODE"] = mode
    with pytest.raises(LaunchError) as error:
        create_screen(**fixture, dispatch_claim=lambda: pytest.fail("Missing actual provider cannot claim"))
    assert error.value.status == "UNKNOWN" and error.value.code == "startup_model_provider_unknown"
    methods = [event["method"] for event in _events(fixture) if "method" in event]
    assert methods == ["initialize", "initialized", "config/read", "model/list", "thread/start"]
    root = fixture["home"] / "state/screen-workers/fixture"
    rejected = json.loads((root / "rejected-startup.json").read_text())
    assert rejected["session_id"] == "01a0a2b6-522a-7501-9a78-c093c781141e"
    assert rejected["model_provider"] is None
    assert rejected["model_preflight"]["configured_provider"] is None
    retained_worker = error.value.receipt["screen"]["worker"]
    assert retained_worker["session_id"] == rejected["session_id"]
    assert retained_worker["connection_id"] == rejected["connection_id"]
    assert registry_session(fixture["home"], retained_worker["socket"]) == rejected["session_id"]
    assert not (Path(fixture["request"]["workspace"]) / "fixture-business.jsonl").exists()


def test_screen_continuation_requalifies_catalog_and_blocks_changed_model_before_probe(screen_fixture):
    fixture = screen_fixture
    fixture["environment"]["FIXTURE_MODE"] = "continuation-model-drift"
    result = create_screen(**fixture, dispatch_claim=lambda: None)
    assert result["startup"]["model"] == "fixture-model"
    with pytest.raises(LaunchError) as error:
        continue_managed(fixture["home"], result["screen"]["socket"], "Review the prior fixture result.",
                         screen_binary=fixture["screen_binary"], environment=fixture["environment"],
                         dispatch_claim=lambda *args: pytest.fail("Changed model cannot claim a continuation"))
    assert error.value.status == "MISMATCH"
    assert error.value.code == "startup_changed:model"
    methods = [event["method"] for event in _events(fixture) if "method" in event]
    assert methods == ["initialize", "initialized", "config/read", "model/list", "thread/start", "turn/start", "turn/start",
                       "config/read", "model/list"]
    assert len((Path(fixture["request"]["workspace"]) / "fixture-business.jsonl").read_text().splitlines()) == 1
    journals = list((fixture["home"] / "state/screen-workers/fixture/continuations").glob("*.json"))
    assert len(journals) == 1
    stopped = json.loads(journals[0].read_text())
    assert stopped["status"] == "MISMATCH" and stopped["error"] == "startup_changed:model"
    assert stopped["current_preflight"]["model"] == "fixture-alternate"
    assert stopped["original_startup"]["model"] == "fixture-model"


def test_screen_continuation_retains_actual_default_provider_and_refuses_explicit_drift(screen_fixture):
    fixture = screen_fixture
    fixture["environment"]["FIXTURE_MODE"] = "continuation-provider-drift"
    result = create_screen(**fixture, dispatch_claim=lambda: None)
    assert result["startup"]["model_provider"] == "fixture-inherited-provider"
    assert result["startup"]["model_preflight"]["configured_provider"] is None
    with pytest.raises(LaunchError) as error:
        continue_managed(fixture["home"], result["screen"]["socket"], "Review the prior fixture result.",
                         screen_binary=fixture["screen_binary"], environment=fixture["environment"],
                         dispatch_claim=lambda *args: pytest.fail("Changed provider cannot claim a continuation"))
    assert error.value.status == "MISMATCH" and error.value.code == "startup_changed:model_provider"
    methods = [event["method"] for event in _events(fixture) if "method" in event]
    assert methods == ["initialize", "initialized", "config/read", "model/list", "thread/start", "turn/start", "turn/start",
                       "config/read", "model/list"]
    assert len((Path(fixture["request"]["workspace"]) / "fixture-business.jsonl").read_text().splitlines()) == 1
    journals = list((fixture["home"] / "state/screen-workers/fixture/continuations").glob("*.json"))
    assert len(journals) == 1
    stopped = json.loads(journals[0].read_text())
    assert stopped["status"] == "MISMATCH" and stopped["error"] == "startup_changed:model_provider"
    assert stopped["current_preflight"]["model_provider"] == "fixture-other-provider"
    assert stopped["original_startup"] == result["startup"]
