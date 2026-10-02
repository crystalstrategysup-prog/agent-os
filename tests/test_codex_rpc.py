"""Actual local pipe/WebSocket framing against a synthetic peer, no daemon."""
from __future__ import annotations

import subprocess
import sys
import time

import pytest

from agent_os import codex_rpc as r
from agent_os.safeio import GateError

PEER = r'''
import sys, json, struct, hashlib, base64
s=sys.stdin.buffer; o=sys.stdout.buffer
def read(n):
 b=b''
 while len(b)<n:
  x=s.read(n-len(b))
  if not x: raise EOFError()
  b+=x
 return b
header=b''
while not header.endswith(b'\r\n\r\n'): header+=read(1)
assert header.startswith(b'GET / HTTP/1.1\r\n')
key=next(x.split(b':',1)[1].strip() for x in header.split(b'\r\n') if x.startswith(b'Sec-WebSocket-Key:'))
accept=base64.b64encode(hashlib.sha1(key+b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
if sys.argv[1]=='bad-upgrade': accept=b'wrong'
o.write(b'HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: '+accept+b'\r\n\r\n');o.flush()
def frame(data, opcode=1):
 p=json.dumps(data).encode() if opcode==1 else data
 h=bytes([0x80|opcode,len(p)]) if len(p)<126 else bytes([0x80|opcode,126])+struct.pack('!H',len(p))
 o.write(h+p);o.flush()
def message():
 h=read(2);n=h[1]&127
 if n==126:n=struct.unpack('!H',read(2))[0]
 if n==127:n=struct.unpack('!Q',read(8))[0]
 assert h[1]&128,'client must mask'
 mask=read(4);p=read(n);p=bytes(x^mask[i%4] for i,x in enumerate(p))
 return h[0]&15, json.loads(p) if h[0]&15==1 else p
try:
 while True:
  opcode,m=message()
  if opcode==10:continue
  if m['method']=='initialized':continue
  if m['method']=='initialize':
   frame({'id':m['id'],'result':{'userAgent':'fixture-peer'}})
   if sys.argv[1]=='stalled-write':
    import time;time.sleep(20)
   continue
  if sys.argv[1]=='rpc-error':frame({'id':m['id'],'error':{'code':-32600,'message':'fixture thread not loaded'}});continue
  if sys.argv[1]=='server-request':frame({'id':900,'method':'item/commandExecution/requestApproval','params':{}});continue
  if sys.argv[1]=='oversize':o.write(bytes([129,127])+struct.pack('!Q',5000000));o.flush();continue
  frame(b'ping',9)
  frame({'method':'item/started','params':{'never_persist':'fixture-notification'}})
  if m['method']=='thread/read': result={'thread':{'id':m['params']['threadId']}}
  else:result={'echo':m['params']}
  frame({'id':m['id'],'result':result})
except EOFError:pass
'''


def client(tmp_path, monkeypatch, mode='normal'):
    peer = tmp_path / 'synthetic_peer.py'
    peer.write_text(PEER)
    binary = tmp_path / 'explicit-fixture-binary'
    binary.write_text('not executed; version/Popen are scoped below')
    actual_popen = subprocess.Popen
    commands = []

    def version(argv, **kwargs):
        if argv == [str(binary), '--version']:
            return subprocess.CompletedProcess(argv, 0, stdout='codex 0.159.3\n')
        assert argv == [str(binary), 'app-server', 'daemon', 'version']
        return subprocess.CompletedProcess(argv, 0, stdout='{"status":"running","appServerVersion":"0.159.3"}\n')

    def launch(argv, **kwargs):
        commands.append(argv)
        assert argv == [str(binary), 'app-server', 'proxy']
        return actual_popen([sys.executable, str(peer), mode], **kwargs)

    monkeypatch.setattr(r.subprocess, 'run', version)
    monkeypatch.setattr(r.subprocess, 'Popen', launch)
    return r.NativeRpc(binary, timeout=2), commands


def test_real_pipe_upgrade_initialize_ping_notification_and_rpc_roundtrip(tmp_path, monkeypatch):
    rpc, commands = client(tmp_path, monkeypatch)
    try:
        assert rpc.call('thread/read', {'threadId': 'fixture-thread', 'includeTurns': False}) == {'thread': {'id': 'fixture-thread'}}
        value = {'threadId': 'fixture-thread', 'clientUserMessageId': 'fixture-client-id',
                 'input': [{'type': 'text', 'text': 'fixture own envelope'}]}
        assert rpc.call('turn/start', value)['echo'] == value
    finally:
        rpc.close()
    assert len(commands) == 1 and rpc.process.poll() == 0


@pytest.mark.parametrize('mode,code', [('rpc-error', -32600), ('server-request', 'owner_server_request_pending'),
                                      ('oversize', 'frame_limit')])
def test_native_error_approval_request_and_frame_limit_never_reply_or_ack(tmp_path, monkeypatch, mode, code):
    rpc, _ = client(tmp_path, monkeypatch, mode)
    try:
        with pytest.raises(r.NativeRpcError) as error:
            rpc.call('thread/read', {'threadId': 'fixture-thread', 'includeTurns': False})
        assert error.value.code == code
    finally:
        rpc.close()


def test_upgrade_mismatch_closes_only_proxy_child(tmp_path, monkeypatch):
    with pytest.raises(r.NativeRpcError, match='upgrade_origin_mismatch'):
        client(tmp_path, monkeypatch, 'bad-upgrade')


@pytest.mark.parametrize('method,params', [
    ('thread/start', {}), ('thread/resume', {}), ('account/login/start', {}),
    ('thread/read', {'threadId': 'x', 'includeTurns': True}),
    ('turn/start', {'threadId': 'x', 'input': [], 'approvalPolicy': 'never'}),
    ('thread/items/list', {'threadId': 'x', 'limit': 1000, 'sortDirection': 'desc'}),
])
def test_unsupported_operations_and_unsafe_overrides_are_refused_before_transport(method, params):
    rpc = object.__new__(r.NativeRpc)
    with pytest.raises(GateError):
        rpc.call(method, params)


def test_unreviewed_native_version_never_launches_proxy(tmp_path, monkeypatch):
    binary = tmp_path / 'fixture'
    binary.write_text('fixture')
    monkeypatch.setattr(r.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, stdout='codex 0.160.0\n'))
    monkeypatch.setattr(r.subprocess, 'Popen', lambda *a, **kw: pytest.fail('version mismatch must not launch'))
    with pytest.raises(GateError, match='protocol_version_mismatch'):
        r.NativeRpc(binary)


def test_missing_or_mismatched_existing_daemon_never_launches_proxy(tmp_path, monkeypatch):
    binary = tmp_path / 'fixture'
    binary.write_text('fixture')

    def mismatch(argv, **kwargs):
        text = 'codex 0.159.3\n' if argv[-1] == '--version' else '{"status":"running","appServerVersion":"0.158.0"}'
        return subprocess.CompletedProcess(argv, 0, stdout=text)

    monkeypatch.setattr(r.subprocess, 'run', mismatch)
    monkeypatch.setattr(r.subprocess, 'Popen', lambda *a, **kw: pytest.fail('daemon mismatch must not launch'))
    with pytest.raises(GateError, match='daemon_version_mismatch'):
        r.NativeRpc(binary)


def test_nonreading_peer_write_times_out_before_fixture_cleanup(tmp_path):
    rpc = object.__new__(r.NativeRpc)
    rpc.timeout = .05
    rpc.process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match='write_timeout'):
            rpc._write(b'x' * (1024 * 1024))
        assert time.monotonic() - started < .5
        assert rpc.process.poll() is None
    finally:
        rpc.process.terminate()
        rpc.process.wait(timeout=1)
        rpc.process.stdin.close()
        rpc.process.stdout.close()


def test_stalled_rpc_send_is_bounded_and_reaps_only_its_proxy(tmp_path, monkeypatch):
    rpc, _ = client(tmp_path, monkeypatch, 'stalled-write')
    rpc.timeout = .05
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match='write_timeout'):
            rpc.call('turn/start', {'threadId': 'fixture-thread', 'clientUserMessageId': 'fixture-message',
                                    'input': [{'type': 'text', 'text': 'x' * (1024 * 1024)}]})
        assert time.monotonic() - started < .6
        assert rpc.process.poll() is not None
    finally:
        rpc.close()


def test_short_pipe_writes_complete_the_actual_rpc_frame(tmp_path, monkeypatch):
    rpc, _ = client(tmp_path, monkeypatch)
    write = r.os.write
    monkeypatch.setattr(r.os, 'write', lambda fd, data: write(fd, data[:7]))
    try:
        assert rpc.call('thread/read', {'threadId': 'fixture-thread', 'includeTurns': False}) == {'thread': {'id': 'fixture-thread'}}
    finally:
        rpc.close()


def test_response_uses_remaining_send_deadline_not_a_new_timeout(tmp_path, monkeypatch):
    rpc, _ = client(tmp_path, monkeypatch)
    rpc.timeout = .1
    send = rpc._send

    def slow_send(value, opcode=1, *, deadline=None):
        time.sleep(.06)
        send(value, opcode, deadline=deadline)

    def receive(deadline):
        assert 0 < deadline - time.monotonic() < .06
        raise TimeoutError('synthetic exhausted shared response budget')

    monkeypatch.setattr(rpc, '_send', slow_send)
    monkeypatch.setattr(rpc, '_receive', receive)
    with pytest.raises(TimeoutError):
        rpc.call('thread/read', {'threadId': 'fixture-thread', 'includeTurns': False})
    assert rpc.process.poll() is not None
