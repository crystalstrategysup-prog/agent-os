"""Bounded proof of an existing SSH route and optional VNC transport.

The probe neither configures a host nor authenticates to its desktop.
"""

from __future__ import annotations

import os
import re
import secrets
import select
import shutil
import signal
import subprocess
import time
from typing import Any

from .safeio import GateError

ALIAS = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,127}\Z")
RFB_VERSION = re.compile(rb"RFB ([0-9]{3})\.([0-9]{3})\n\Z")
SSH_IDENTITY_TIMEOUT = 18
FORWARD_TIMEOUT = 12
SSH_OPTIONS = (
    "-T",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectionAttempts=1",
    "-o",
    "ConnectTimeout=8",
    "-o",
    "NumberOfPasswordPrompts=0",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "UpdateHostKeys=no",
    "-o",
    "ForwardAgent=no",
    "-o",
    "ForwardX11=no",
    "-o",
    "PermitLocalCommand=no",
    "-o",
    "ControlMaster=no",
    "-o",
    "ControlPath=none",
    "-o",
    "LogLevel=ERROR",
)


def _stop(proc: subprocess.Popen[bytes]) -> bool:
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=2)
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        if stream is not None:
            stream.close()
    return proc.poll() is not None


def _ssh_identity(ssh: str, alias: str) -> str | None:
    marker = "AGENTOS_SSH_PROBE_" + secrets.token_hex(16)
    argv = [ssh, *SSH_OPTIONS, "-o", "ClearAllForwardings=yes", alias, "echo " + marker]
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        assert proc.stdout is not None
        output = bytearray()
        deadline = time.monotonic() + SSH_IDENTITY_TIMEOUT
        while time.monotonic() < deadline:
            ready, _, _ = select.select(
                [proc.stdout], [], [], max(0.0, min(0.2, deadline - time.monotonic()))
            )
            if ready:
                part = os.read(proc.stdout.fileno(), 257 - len(output))
                if not part:
                    break
                output.extend(part)
                if len(output) > 256:
                    return "ssh_unexpected_response"
            if proc.poll() is not None and not ready:
                break
        else:
            return "ssh_timeout"
        proc.wait(timeout=max(0.1, deadline - time.monotonic()))
        if proc.returncode != 0:
            return "ssh_failed"
        if bytes(output).strip() != marker.encode("ascii"):
            return "ssh_unexpected_response"
        return None
    except subprocess.TimeoutExpired:
        return "ssh_timeout"
    finally:
        _stop(proc)


class _SSHStream:
    def __init__(self, proc: subprocess.Popen[bytes]):
        self.proc = proc
        self.deadline = time.monotonic() + FORWARD_TIMEOUT

    def recv(self, length: int) -> bytes:
        assert self.proc.stdout is not None
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        ready, _, _ = select.select([self.proc.stdout], [], [], remaining)
        if not ready:
            raise TimeoutError
        return os.read(self.proc.stdout.fileno(), length)

    def sendall(self, data: bytes) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(data)
        self.proc.stdin.flush()


def _recv_exact(sock: _SSHStream, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        part = sock.recv(length - len(data))
        if not part:
            raise OSError("rfb_closed")
        data.extend(part)
    return bytes(data)


def _rfb_offer(sock: _SSHStream) -> tuple[str, list[int]]:
    banner = _recv_exact(sock, 12)
    match = RFB_VERSION.fullmatch(banner)
    if match is None:
        raise ValueError("invalid_rfb_greeting")
    major, minor = int(match[1]), int(match[2])
    if major != 3 or minor < 3:
        raise ValueError("unsupported_rfb_version")
    if minor not in (3, 7) and minor < 8:
        raise ValueError("unsupported_rfb_version")
    client_minor = 3 if minor == 3 else 7 if minor == 7 else 8
    sock.sendall(f"RFB 003.{client_minor:03d}\n".encode("ascii"))
    if client_minor == 3:
        security = int.from_bytes(_recv_exact(sock, 4), "big")
        if security == 0:
            raise ValueError("rfb_offer_rejected")
        if security > 255:
            raise ValueError("unsupported_rfb_security")
        return banner.decode("ascii").strip(), [security]
    count = _recv_exact(sock, 1)[0]
    if count == 0:
        raise ValueError("rfb_offer_rejected")
    return banner.decode("ascii").strip(), list(_recv_exact(sock, count))


def probe(
    alias: str,
    *,
    vnc_port: int = 5900,
    ssh_only: bool = False,
    apply: bool = False,
    ssh_binary: str | None = None,
) -> dict[str, Any]:
    if not ALIAS.fullmatch(alias):
        raise GateError("invalid_ssh_alias")
    if not 1 <= vnc_port <= 65535:
        raise GateError("invalid_vnc_port")
    result: dict[str, Any] = {
        "schema": "agentos.ssh-vnc-probe/v1",
        "status": "PLANNED",
        "proof_level": "not_run",
        "requested_vnc": not ssh_only,
        "ssh_authenticated": False,
        "rfb_transport": False,
        "vnc_authenticated": False,
        "desktop_frame_verified": False,
        "rfb_protocol": None,
        "security_types": [],
        "forward_closed": True,
        "host_key_policy": "strict",
    }
    if not apply:
        return result
    if os.name != "posix":
        raise GateError("ssh_vnc_probe_requires_posix")
    ssh = ssh_binary or shutil.which("ssh")
    if ssh is None:
        raise GateError("ssh_client_unavailable")
    error = _ssh_identity(ssh, alias)
    if error is not None:
        result.update(status="FAIL", error_code=error)
        return result
    result.update(
        status="SSH_VERIFIED", proof_level="ssh_authenticated", ssh_authenticated=True
    )
    if ssh_only:
        return result
    argv = [
        ssh,
        *SSH_OPTIONS,
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ClearAllForwardings=yes",
        "-W",
        f"127.0.0.1:{vnc_port}",
        alias,
    ]
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        protocol, security = _rfb_offer(_SSHStream(proc))
        result.update(
            status="TRANSPORT_VERIFIED",
            proof_level="rfb_transport",
            rfb_transport=True,
            rfb_protocol=protocol,
            security_types=security,
        )
    except (OSError, ValueError, TimeoutError) as exc:
        code = str(exc)
        if code not in {
            "invalid_rfb_greeting",
            "unsupported_rfb_version",
            "unsupported_rfb_security",
            "rfb_offer_rejected",
            "rfb_closed",
        }:
            code = "rfb_unavailable"
        result.update(status="FAIL", error_code=code)
    finally:
        result["forward_closed"] = _stop(proc)
    return result
