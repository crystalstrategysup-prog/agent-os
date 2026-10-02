"""Bounded client for an existing native daemon. Never starts/resumes a thread.

Connection selection and target authority belong to the owner. No auth files,
daemon start, permission overrides, approval replies or session files are used.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import selectors
import struct
import subprocess
import time
from pathlib import Path

from .safeio import GateError

VERSION = '0.159.3'
NAMESPACE = 'codex.app-server/v2@0.159.3'
SCHEMA_SHA256 = 'e77b7d1436a78f431a74b2cb263a862e92ae40d70411bc63835b47ab2168827c'
MAX_BYTES = 4 * 1024 * 1024


class NativeRpcError(RuntimeError):
    def __init__(self, code: int | str):
        self.code = code
        super().__init__('native_rpc_unavailable:' + str(code))


class NativeRpc:
    """An owner-selected local proxy connection, not provider authorization."""

    @property
    def identity(self) -> dict:
        return {'provider': NAMESPACE, 'version': VERSION, 'schema_sha256': SCHEMA_SHA256}

    def __init__(self, binary: Path, *, timeout: float = 20):
        if not 0 < timeout <= 20 or not binary.is_absolute() or not binary.is_file():
            raise GateError('explicit_native_binary_and_bounded_timeout_required')
        version = subprocess.run([str(binary), '--version'], check=True, capture_output=True,
                                 text=True, timeout=timeout).stdout.strip()
        if version != 'codex ' + VERSION:
            raise GateError('native_protocol_version_mismatch')
        daemon = json.loads(subprocess.run([str(binary), 'app-server', 'daemon', 'version'],
                                          check=True, capture_output=True, text=True,
                                          timeout=timeout).stdout)
        if daemon.get('status') != 'running' or daemon.get('appServerVersion') != VERSION:
            raise GateError('existing_native_daemon_version_mismatch')
        self.timeout = timeout
        self.process = subprocess.Popen([str(binary), 'app-server', 'proxy'],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, bufsize=0)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.buffer = b''
        self.sequence = 0
        try:
            self._upgrade()
            self._request('initialize', {'clientInfo': {'name': 'agentos_native_provider', 'version': '1'},
                                         'capabilities': {'experimentalApi': True}})
            self._send(json.dumps({'method': 'initialized', 'params': {}}))
        except BaseException:
            self.close()
            raise

    def _write(self, data: bytes, deadline: float | None = None) -> None:
        deadline = deadline if deadline is not None else time.monotonic() + self.timeout
        descriptor = self.process.stdin.fileno()
        os.set_blocking(descriptor, False)
        remaining = memoryview(data)
        with selectors.DefaultSelector() as writable:
            writable.register(descriptor, selectors.EVENT_WRITE)
            while remaining:
                budget = deadline - time.monotonic()
                if budget <= 0:
                    raise TimeoutError('native_rpc_write_timeout')
                try:
                    count = os.write(descriptor, remaining)
                except BlockingIOError:
                    writable.select(timeout=min(budget, .1))
                    continue
                if count <= 0:
                    raise NativeRpcError('proxy_write_closed')
                remaining = remaining[count:]

    def _bytes(self, count: int, deadline: float) -> bytes:
        while len(self.buffer) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('native_rpc_timeout')
            if not self.selector.select(timeout=min(remaining, 1)):
                continue
            piece = os.read(self.process.stdout.fileno(), 65536)
            if not piece:
                raise NativeRpcError('proxy_closed')
            self.buffer += piece
            if len(self.buffer) > MAX_BYTES + 65536:
                raise NativeRpcError('response_limit')
        result, self.buffer = self.buffer[:count], self.buffer[count:]
        return result

    def _upgrade(self) -> None:
        deadline = time.monotonic() + self.timeout
        key = base64.b64encode(os.urandom(16)).decode()
        self._write(('GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n'
                     'Connection: Upgrade\r\nSec-WebSocket-Key: ' + key +
                     '\r\nSec-WebSocket-Version: 13\r\n\r\n').encode(), deadline)
        head = b''
        while not head.endswith(b'\r\n\r\n'):
            head += self._bytes(1, deadline)
            if len(head) > 16384:
                raise NativeRpcError('http_header_limit')
        lines = head.decode().split('\r\n')
        if not lines[0].startswith('HTTP/1.1 101 '):
            raise NativeRpcError('upgrade_refused')
        headers = {line.split(':', 1)[0].lower(): line.split(':', 1)[1].strip()
                   for line in lines[1:] if ':' in line}
        expected = base64.b64encode(hashlib.sha1(
            (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        if headers.get('sec-websocket-accept') != expected:
            raise NativeRpcError('upgrade_origin_mismatch')

    def _send(self, value: str | bytes, opcode: int = 1, *, deadline: float | None = None) -> None:
        deadline = deadline if deadline is not None else time.monotonic() + self.timeout
        raw = value.encode() if isinstance(value, str) else value
        if len(raw) > MAX_BYTES:
            raise GateError('native_request_limit')
        mask = os.urandom(4)
        if len(raw) < 126:
            size = bytes([0x80 | len(raw)])
        elif len(raw) < 65536:
            size = bytes([0x80 | 126]) + struct.pack('!H', len(raw))
        else:
            size = bytes([0x80 | 127]) + struct.pack('!Q', len(raw))
        self._write(bytes([0x80 | opcode]) + size + mask, deadline)
        for offset in range(0, len(raw), 65536):
            if time.monotonic() >= deadline:
                raise TimeoutError('native_rpc_encode_timeout')
            piece = raw[offset:offset + 65536]
            self._write(bytes(x ^ mask[(offset + i) % 4] for i, x in enumerate(piece)), deadline)

    def _receive(self, deadline: float) -> dict | None:
        header = self._bytes(2, deadline)
        opcode, count = header[0] & 15, header[1] & 127
        if count == 126:
            count = struct.unpack('!H', self._bytes(2, deadline))[0]
        elif count == 127:
            count = struct.unpack('!Q', self._bytes(8, deadline))[0]
        if count > MAX_BYTES:
            raise NativeRpcError('frame_limit')
        if header[1] & 128 or not header[0] & 128:
            raise NativeRpcError('unsupported_server_frame')
        payload = self._bytes(count, deadline)
        if opcode == 9:
            if count > 125:
                raise NativeRpcError('invalid_ping')
            self._send(payload, 10, deadline=deadline)
            return None
        if opcode != 1:
            raise NativeRpcError('closed_or_unsupported_frame')
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise NativeRpcError('invalid_rpc_object')
        return result

    def _request(self, method: str, params: dict) -> dict:
        self.sequence += 1
        deadline = time.monotonic() + self.timeout
        try:
            self._send(json.dumps({'id': self.sequence, 'method': method, 'params': params}), deadline=deadline)
            while time.monotonic() < deadline:
                response = self._receive(deadline)
                if response is None:
                    continue
                if 'method' in response and 'id' in response:
                    raise NativeRpcError('owner_server_request_pending')
                if response.get('id') != self.sequence:
                    continue
                if 'error' in response:
                    raise NativeRpcError(response['error'].get('code', 'unspecified'))
                if not isinstance(response.get('result'), dict):
                    raise NativeRpcError('invalid_rpc_result')
                return response['result']
            raise TimeoutError('native_rpc_timeout')
        except (TimeoutError, OSError):
            self._abort()
            raise

    def _abort(self) -> None:
        """Partial I/O may have reached the daemon. Close only our proxy; no retry."""
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=.25)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=.25)
        if self.process.stdin:
            self.process.stdin.close()
        if self.process.stdout:
            self.process.stdout.close()
        self.selector.close()

    def call(self, method: str, params: dict) -> dict:
        permitted = {
            'thread/read': {'threadId', 'includeTurns'},
            'thread/items/list': {'threadId', 'limit', 'sortDirection', 'cursor'},
            'turn/start': {'threadId', 'clientUserMessageId', 'input'},
        }
        if method not in permitted or set(params) - permitted[method]:
            raise GateError('native_method_or_override_refused')
        if method == 'thread/read' and params.get('includeTurns') is not False:
            raise GateError('metadata_only_native_read_required')
        if method == 'thread/items/list' and (params.get('limit') != 50 or params.get('sortDirection') != 'desc'):
            raise GateError('bounded_native_item_read_required')
        if method == 'turn/start' and (set(params) != permitted[method]
                                    or not isinstance(params.get('input'), list)
                                    or len(params['input']) != 1
                                    or set(params['input'][0]) != {'type', 'text'}
                                    or params['input'][0]['type'] != 'text'):
            raise GateError('exact_native_text_input_required')
        return self._request(method, params)

    def close(self) -> None:
        """Close only this proxy child. The existing daemon/worker is untouched."""
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=3)
        if self.process.stdout:
            self.process.stdout.close()
        self.selector.close()
