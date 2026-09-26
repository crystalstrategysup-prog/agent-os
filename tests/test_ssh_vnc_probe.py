"""The exact-alias probe returns layered proof and closes its SSH channel."""

from __future__ import annotations

import json
import os
from pathlib import Path

import jsonschema
import pytest

from agent_os import cli
from agent_os import ssh_vnc_probe as p
from agent_os.safeio import GateError

ROOT = Path(__file__).resolve().parents[1]
FAKE_SSH = """#!/usr/bin/env python3
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
mode = os.environ.get("FAKE_SSH_MODE", "pass")
Path(os.environ["FAKE_SSH_PID_FILE"]).write_text(str(os.getpid()))
if "-W" not in args:
    if mode == "ssh-fail":
        sys.exit(255)
    if mode == "ssh-hang":
        time.sleep(30)
    print(args[-1].split()[-1])
    sys.exit(0)
if "ClearAllForwardings=yes" not in args:
    sys.exit(3)
if mode in ("forward-fail", "rfb-closed"):
    sys.exit(4)
if mode == "rfb-hang":
    time.sleep(30)
banner = b"RFB 003.003\\n" if mode == "rfb33" else b"RFB 003.008\\n"
sys.stdout.buffer.write(b"bad greeting" if mode == "bad-rfb" else banner)
sys.stdout.buffer.flush()
if mode == "bad-rfb":
    time.sleep(30)
sys.stdin.buffer.read(12)
sys.stdout.buffer.write((2).to_bytes(4, "big") if mode == "rfb33" else bytes([2, 2, 30]))
sys.stdout.buffer.flush()
time.sleep(30)
"""


@pytest.fixture
def fake_ssh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    script = tmp_path / "ssh"
    script.write_text(FAKE_SSH)
    script.chmod(0o700)
    pid_file = tmp_path / "pid"
    monkeypatch.setenv("FAKE_SSH_PID_FILE", str(pid_file))
    return str(script), pid_file


def _validate(value: dict) -> None:
    path = ROOT / "schemas/ssh-vnc-probe-v1.schema.json"
    assert (
        ROOT / "src/agent_os/resources/schemas/ssh-vnc-probe-v1.schema.json"
    ).read_bytes() == path.read_bytes()
    jsonschema.validate(value, json.loads(path.read_text()))


def _process_gone(pid: int) -> None:
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_plan_is_network_free_and_id_is_bounded(monkeypatch, capsys) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("plan must not start a process")

    monkeypatch.setattr(p.subprocess, "Popen", forbidden)
    assert cli.main(["setup", "probe", "ssh-vnc", "--host", "known-alias"]) == 0
    result = json.loads(capsys.readouterr().out)
    _validate(result)
    assert result["status"] == "PLANNED"
    assert "known-alias" not in json.dumps(result)
    for alias in ("-oProxyCommand=bad", "user@host", "../host", "192.0.2.1"):
        with pytest.raises(GateError, match="invalid_ssh_alias"):
            p.probe(alias)
    with pytest.raises(GateError, match="invalid_vnc_port"):
        p.probe("known-alias", vnc_port=0)


@pytest.mark.parametrize(
    "mode,protocol,security",
    [
        ("pass", "RFB 003.008", [2, 30]),
        ("rfb33", "RFB 003.003", [2]),
    ],
)
def test_authenticated_ssh_and_rfb_transport_with_cleanup(
    fake_ssh, monkeypatch, mode, protocol, security
) -> None:
    script, pid_file = fake_ssh
    monkeypatch.setenv("FAKE_SSH_MODE", mode)
    result = p.probe("known-alias", apply=True, ssh_binary=script)
    _validate(result)
    assert result["status"] == "TRANSPORT_VERIFIED"
    assert result["proof_level"] == "rfb_transport"
    assert result["ssh_authenticated"] and result["rfb_transport"]
    assert not result["vnc_authenticated"] and not result["desktop_frame_verified"]
    assert result["rfb_protocol"] == protocol
    assert result["security_types"] == security
    assert result["forward_closed"]
    _process_gone(int(pid_file.read_text()))


def test_ssh_only_and_failed_auth(fake_ssh, monkeypatch) -> None:
    script, pid_file = fake_ssh
    result = p.probe("known-alias", ssh_only=True, apply=True, ssh_binary=script)
    _validate(result)
    assert result["status"] == "SSH_VERIFIED"
    _process_gone(int(pid_file.read_text()))
    monkeypatch.setenv("FAKE_SSH_MODE", "ssh-fail")
    result = p.probe("known-alias", apply=True, ssh_binary=script)
    _validate(result)
    assert result["status"] == "FAIL" and result["error_code"] == "ssh_failed"
    _process_gone(int(pid_file.read_text()))


@pytest.mark.parametrize(
    "mode,code",
    [
        ("forward-fail", "rfb_closed"),
        ("rfb-closed", "rfb_closed"),
        ("bad-rfb", "invalid_rfb_greeting"),
    ],
)
def test_failed_forward_or_rfb_still_closes(fake_ssh, monkeypatch, mode, code) -> None:
    script, pid_file = fake_ssh
    monkeypatch.setenv("FAKE_SSH_MODE", mode)
    result = p.probe("known-alias", apply=True, ssh_binary=script)
    _validate(result)
    assert result["status"] == "FAIL" and result["error_code"] == code
    assert result["forward_closed"]
    _process_gone(int(pid_file.read_text()))


@pytest.mark.parametrize(
    "mode,constant,code",
    [
        ("ssh-hang", "SSH_IDENTITY_TIMEOUT", "ssh_timeout"),
        ("rfb-hang", "FORWARD_TIMEOUT", "rfb_unavailable"),
    ],
)
def test_timeouts_are_bounded(fake_ssh, monkeypatch, mode, constant, code) -> None:
    script, _ = fake_ssh
    seen_pid = []
    original_stop = p._stop

    def stopped(proc):
        seen_pid.append(proc.pid)
        return original_stop(proc)

    monkeypatch.setattr(p, "_stop", stopped)
    monkeypatch.setenv("FAKE_SSH_MODE", mode)
    monkeypatch.setattr(p, constant, 0.2)
    result = p.probe("known-alias", apply=True, ssh_binary=script)
    assert result["status"] == "FAIL" and result["error_code"] == code
    assert seen_pid
    for pid in seen_pid:
        _process_gone(pid)


def test_cli_failed_probe_has_nonzero_exit(monkeypatch, capsys) -> None:
    monkeypatch.setattr(p, "probe", lambda *_args, **_kwargs: {"status": "FAIL"})
    assert (
        cli.main(["setup", "probe", "ssh-vnc", "--host", "known-alias", "--apply"]) == 1
    )
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"


def test_interruption_stops_forward(fake_ssh, monkeypatch) -> None:
    script, _ = fake_ssh
    seen_pid = []

    def interrupted(stream):
        seen_pid.append(stream.proc.pid)
        raise KeyboardInterrupt

    monkeypatch.setattr(p, "_rfb_offer", interrupted)
    with pytest.raises(KeyboardInterrupt):
        p.probe("known-alias", apply=True, ssh_binary=script)
    _process_gone(seen_pid[0])
