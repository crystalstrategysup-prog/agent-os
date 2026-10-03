"""Guarded, persistent GNU Screen workers over the Codex stdio adapter.

The Screen window owns the App Server connection. File mailboxes are a bounded
same-user transport, not an authorization or security boundary. No command is
sent through Screen keystrokes and no existing Screen is stopped or replaced.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .codex_launch import CodexLaunchProvider, StdioRpc, _model_binding, _safe_turn_failure
from .safeio import GateError, atomic_json, digest, lock, read_json, within
from .session_launch import LaunchError, LaunchJournal, _observation, _targets, launch, validate_request

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,47}\Z")
SOCKET = re.compile(r"(?P<pid>[1-9][0-9]*)\.(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]{0,47})\Z")
LIMIT = 128 * 1024


def _read(path: Path) -> dict:
    if path.stat().st_size > LIMIT:
        raise LaunchError("screen_record_size_limit", status="UNKNOWN")
    value = read_json(path)
    if not isinstance(value, dict):
        raise LaunchError("screen_record_invalid", status="UNKNOWN")
    return value


def worker_root(home: Path, name: str) -> Path:
    if not NAME.fullmatch(name):
        raise LaunchError("screen_name_invalid")
    return within(home, "state/screen-workers/" + name)


def _screen_sockets(binary: Path, environment: dict[str, str]) -> set[str]:
    result = subprocess.run([str(binary), "-ls"], env=environment, capture_output=True,
                            text=True, timeout=5, check=False)
    # GNU Screen returns 1 when no session exists; the output is metadata only.
    if result.returncode not in (0, 1):
        raise LaunchError("screen_inventory_unavailable", status="UNKNOWN")
    text = result.stdout + result.stderr
    if len(text) > LIMIT:
        raise LaunchError("screen_inventory_size_limit", status="UNKNOWN")
    return {line.split()[0] for line in text.splitlines()
            if line.split() and SOCKET.fullmatch(line.split()[0])}


def registry_session(home: Path, socket: str) -> str | None:
    """Read a single bounded managed-worker identity, never transcript text."""
    match = SOCKET.fullmatch(socket)
    if not match:
        return None
    path = worker_root(home, match["name"]) / "state.json"
    if not path.exists():
        return None
    try:
        state = _read(path)
        if state.get("socket") == socket and state.get("status") != "EXITED":
            return state.get("session_id")
    except (OSError, ValueError):
        pass
    return None


class ScreenLaunchProvider:
    """Typed parent transport for exactly one persistent Screen-owned provider."""

    def __init__(self, root: Path, screen_binary: Path, environment: dict[str, str], *, timeout: float = 30):
        if not 0 < timeout <= 1805:
            raise LaunchError("bounded_screen_timeout_required")
        self.root, self.screen_binary, self.environment = root, screen_binary, environment
        self.timeout = timeout
        self.identity = _read(root / "identity.json")
        if digest(_read(root / "bootstrap.json")) != self.identity.get("bootstrap_sha256"):
            raise LaunchError("screen_bootstrap_not_bound", status="UNKNOWN")

    @classmethod
    def start(cls, home: Path, name: str, request: dict, *, screen_binary: Path,
              codex_binary: Path, environment: dict[str, str], timeout: float = 30,
              work_timeout: float = 1800) -> "ScreenLaunchProvider":
        validate_request(request)
        if os.name == "nt":
            raise LaunchError("screen_not_supported_on_windows", status="UNAVAILABLE")
        if request["executor"].get("transport") != "gnu-screen":
            raise LaunchError("owner_selected_screen_transport_required", status="UNKNOWN")
        if not 0 < timeout <= 45 or not 0 < work_timeout <= 1800:
            raise LaunchError("bounded_screen_timeout_required")
        root = worker_root(home, name)
        for binary in (screen_binary, codex_binary):
            if not binary.is_absolute() or not binary.is_file():
                raise LaunchError("screen_or_codex_binary_unavailable", status="UNAVAILABLE")
        if root.exists() or any(socket.split(".", 1)[1] == name for socket in _screen_sockets(screen_binary, environment)):
            raise LaunchError("screen_name_exists_reconciliation_required", status="UNKNOWN")
        # Creation is exclusive, including concurrent callers. Never reuse an old
        # registry directory, even if its old Screen is no longer visible.
        root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            root.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise LaunchError("screen_name_exists_reconciliation_required", status="UNKNOWN") from exc
        bootstrap = {"request": request, "codex_binary": str(codex_binary),
                     "work_timeout": work_timeout, "codex_home": environment.get("CODEX_HOME")}
        identity = {"schema": "agentos.screen-worker/v1", "worker_id": str(uuid.uuid4()),
                    "name": name, "request_sha256": digest(request), "created_at": time.time()}
        identity["bootstrap_sha256"] = digest(bootstrap)
        atomic_json(root / "identity.json", identity)
        atomic_json(root / "bootstrap.json", bootstrap)
        child_env = dict(environment)
        # Terminal-only startup isolation; no Codex option, auth value or
        # permission policy is written or overridden.
        child_env["SYSSCREENRC"] = os.devnull
        child_env["SYSTEM_SCREENRC"] = os.devnull
        command = [str(screen_binary), "-D", "-m", "-S", name, "-c", os.devnull,
                   sys.executable, "-m", "agent_os.screen_launch", "worker", str(root)]
        process = subprocess.Popen(command, cwd=request["workspace"], env=child_env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
        identity["screen_pid"] = process.pid
        atomic_json(root / "identity.json", identity)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            path = root / "state.json"
            if path.exists():
                state = _read(path)
                if state.get("error"):
                    raise LaunchError(state["error"], status=state.get("error_status", "UNKNOWN"), receipt=state)
                if state.get("status") == "READY":
                    client = cls(root, screen_binary, environment, timeout=timeout)
                    client._state()
                    return client
            if process.poll() is not None:
                raise LaunchError("screen_worker_exited_before_ready", status="UNKNOWN", receipt=identity)
            time.sleep(.025)
        # Keep the exact owned identity; never kill or retry an uncertain start.
        raise LaunchError("screen_startup_timeout_reconciliation_required", status="UNKNOWN", receipt=identity)

    def _state(self, *, require_running: bool = True) -> dict:
        state = _read(self.root / "state.json")
        expected = self.identity
        if (state.get("worker_id") != expected["worker_id"] or state.get("request_sha256") != expected["request_sha256"]
                or state.get("socket") != str(expected["screen_pid"]) + "." + expected["name"]):
            raise LaunchError("screen_worker_identity_mismatch", status="UNKNOWN")
        try:
            state["screen_socket_observed"] = state["socket"] in _screen_sockets(self.screen_binary, self.environment)
        except (LaunchError, OSError, subprocess.TimeoutExpired) as exc:
            if require_running:
                raise
            state["screen_socket_observed"] = None
            state["screen_inventory_error"] = type(exc).__name__
        if not state["screen_socket_observed"] and require_running:
            raise LaunchError("screen_socket_not_observed", status="UNKNOWN", receipt=state)
        if state.get("status") in {"FAILED", "EXITED"} and require_running:
            raise LaunchError("screen_worker_unavailable", status="UNKNOWN", receipt=state)
        return state

    def status(self) -> dict:
        """A bounded read; it never retries an operation or clears uncertainty."""
        state = self._state(require_running=False)
        pending = self.root / "pending.json"
        return {"worker": state, "pending": _read(pending) if pending.exists() else None,
                "work_accepted": False}

    def _call(self, operation: str, payload: dict, *, timeout: float | None = None) -> dict:
        if operation not in {"describe", "create", "probe", "dispatch"}:
            raise LaunchError("screen_operation_refused")
        raw = json.dumps(payload, ensure_ascii=False)
        if len(raw.encode()) > LIMIT:
            raise LaunchError("screen_request_size_limit")
        with lock(self.root / "control.lock"):
            state = self._state()
            pending = self.root / "pending.json"
            if pending.exists():
                raise LaunchError("screen_previous_operation_requires_reconciliation", status="UNKNOWN", receipt=_read(pending))
            operation_id = str(uuid.uuid4())
            message = {"id": operation_id, "worker_id": self.identity["worker_id"], "operation": operation,
                       "connection_id": state["connection_id"], "payload": payload}
            atomic_json(pending, {"operation_id": operation_id, "operation": operation,
                                  "request_sha256": digest(message), "status": "PENDING"})
            atomic_json(self.root / "request.json", message)
            deadline = time.monotonic() + (timeout or self.timeout)
            response_path = self.root / "responses" / (operation_id + ".json")
            while time.monotonic() < deadline:
                if response_path.exists():
                    response = _read(response_path)
                    if (response.get("id") != operation_id or response.get("worker_id") != self.identity["worker_id"]
                            or response.get("connection_id") != state["connection_id"] or response.get("request_sha256") != digest(message)):
                        raise LaunchError("screen_response_not_bound", status="UNKNOWN")
                    # Unknown provider effects remain a persistent no-retry gate.
                    if response.get("error"):
                        if response.get("status") != "UNKNOWN":
                            pending.unlink()
                        raise LaunchError(response["error"], status=response.get("status", "UNKNOWN"), receipt=response)
                    pending.unlink()
                    return response["result"]
                time.sleep(.025)
            raise LaunchError("screen_operation_timeout_reconciliation_required", status="UNKNOWN", receipt=_read(pending))

    def describe(self, request: dict, attempt: str) -> dict:
        return self._call("describe", {"request": request, "attempt": attempt})

    def create(self, request: dict, attempt: str) -> dict:
        return self._call("create", {"request": request, "attempt": attempt})

    def probe(self, request: dict, startup: dict, attempt: str) -> dict:
        return self._call("probe", {"request": request, "startup": startup, "attempt": attempt}, timeout=50)

    def dispatch(self, request: dict, startup: dict, envelope: str) -> dict:
        work_timeout = _read(self.root / "bootstrap.json")["work_timeout"]
        return self._call("dispatch", {"request": request, "startup": startup, "envelope": envelope}, timeout=work_timeout + 5)


class _PersistentProvider(CodexLaunchProvider):
    def dispatch(self, request: dict, startup: dict, envelope: str) -> dict:
        turn_id, events = self._turn(startup["session_id"], envelope, self.work_timeout)
        saw_user, saw_reply = False, False
        evidence = []
        for event in events:
            item = event.get("params", {}).get("item", {})
            if item.get("type") == "userMessage":
                content = item.get("content")
                saw_user = (isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict)
                            and content[0].get("type") == "text" and content[0].get("text") == envelope)
            elif saw_user and item.get("type") in {"agentMessage", "commandExecution", "fileChange", "mcpToolCall"}:
                saw_reply = True
            if item:
                evidence.append({"id": item.get("id"), "type": item.get("type"), "sha256": digest(item)})
        completed = events[-1].get("params", {}).get("turn", {}) if events else {}
        return {"session_id": startup["session_id"], "turn_id": turn_id,
                "status": completed.get("status", "unknown"), "items": evidence,
                "failure": _safe_turn_failure(completed),
                "delivery": "accepted" if saw_user and saw_reply else "delivery_not_proven",
                "proof_source": "same_connection_provider_events", "semantic_acceptance": "NOT_EVALUATED"}


def _worker(root: Path) -> int:
    with lock(root / "worker.lock"):
        return _worker_locked(root)


def _worker_locked(root: Path) -> int:
    identity = _read(root / "identity.json")
    bootstrap = _read(root / "bootstrap.json")
    request = bootstrap["request"]
    validate_request(request)
    socket = os.environ.get("STY", "")
    state = {**identity, "socket": socket, "worker_pid": os.getpid(), "status": "STARTING", "session_id": None}
    rpc = None
    try:
        if digest(bootstrap) != identity.get("bootstrap_sha256") or digest(request) != identity["request_sha256"]:
            raise LaunchError("screen_bootstrap_not_bound", status="UNKNOWN")
        match = SOCKET.fullmatch(socket)
        if (not match or match["name"] != identity["name"] or not os.path.samefile(os.getcwd(), request["workspace"])
                or os.environ.get("CODEX_HOME") != bootstrap.get("codex_home")):
            raise LaunchError("screen_worker_startup_identity_or_cwd_mismatch", status="UNKNOWN")
        rpc = StdioRpc(Path(bootstrap["codex_binary"]), Path(request["workspace"]), os.environ.copy(),
                       request["executor"].get("approved_version", ""))
        provider = _PersistentProvider(rpc, work_timeout=bootstrap["work_timeout"])
        state.update(connection_id=rpc.connection_id, provider_version=rpc.version, status="READY")
        atomic_json(root / "state.json", state)
        previous_id, startup, last_attempt, probe_passed, thread_start_attempted = None, None, None, False, False
        while True:
            path = root / "request.json"
            if not path.exists():
                time.sleep(.025)
                continue
            message = _read(path)
            if message.get("id") == previous_id:
                time.sleep(.025)
                continue
            operation = message.get("operation")
            payload = message.get("payload", {})
            operation_id = message.get("id")
            if not isinstance(operation_id, str) or not re.fullmatch(r"[a-f0-9-]{36}", operation_id):
                raise LaunchError("screen_operation_identity_invalid", status="UNKNOWN")
            response = {"id": operation_id, "worker_id": identity["worker_id"], "connection_id": rpc.connection_id,
                        "request_sha256": digest(message), "observed_at": time.time()}
            state.update(status="BUSY", operation=operation, operation_id=operation_id)
            atomic_json(root / "state.json", state)
            try:
                if (message.get("worker_id") != identity["worker_id"] or message.get("connection_id") != rpc.connection_id
                        or digest(payload.get("request")) != identity["request_sha256"]):
                    raise LaunchError("screen_request_not_bound")
                if operation == "describe":
                    last_attempt, probe_passed = payload["attempt"], False
                    result = provider.describe(request, last_attempt)
                elif operation == "create":
                    if thread_start_attempted or startup is not None or payload.get("attempt") != last_attempt:
                        raise LaunchError("screen_duplicate_or_unadmitted_thread_start", status="UNKNOWN")
                    thread_start_attempted = True
                    result = provider.create(request, last_attempt)
                    startup = result
                    state["session_id"] = result.get("session_id")
                    atomic_json(root / "startup.json", result)
                elif operation == "probe":
                    if startup is None or payload.get("startup") != startup or payload.get("attempt") != last_attempt:
                        raise LaunchError("screen_probe_not_bound")
                    result = provider.probe(request, startup, last_attempt)
                    probe_passed = result.get("status") == "PASS"
                elif operation == "dispatch":
                    if not probe_passed or startup is None or payload.get("startup") != startup:
                        raise LaunchError("screen_dispatch_without_successful_probe")
                    envelope = payload.get("envelope")
                    # The typed request's exact digest has already bound the
                    # original goal/context/authority. JSON escaping in a
                    # continuation envelope must not change that binding.
                    if not isinstance(envelope, str) or not envelope.strip():
                        raise LaunchError("screen_task_envelope_missing")
                    probe_passed = False
                    result = provider.dispatch(request, startup, envelope)
                else:
                    raise LaunchError("screen_operation_refused")
                response["result"] = result
                state["status"] = "READY"
            except LaunchError as exc:
                response.update(error=exc.code, status=exc.status)
                if exc.receipt:
                    response["provider_failure"] = exc.receipt
                    rejected_startup = exc.receipt.get("startup")
                    if operation == "create" and isinstance(rejected_startup, dict):
                        # A rejected startup may still have created a thread.
                        # Persist that identity without admitting it for work.
                        state["session_id"] = rejected_startup.get("session_id")
                        atomic_json(root / "rejected-startup.json", rejected_startup)
                state["status"] = "FAILED" if exc.status == "UNKNOWN" else "READY"
            except (OSError, TimeoutError, ValueError, KeyError) as exc:
                response.update(error="screen_provider_" + type(exc).__name__, status="UNKNOWN")
                state["status"] = "FAILED"
            atomic_json(root / "responses" / (operation_id + ".json"), response)
            atomic_json(root / "state.json", state)
            previous_id = operation_id
            # Failed uncertain provider state remains present for read-only
            # reconciliation; never restart or replay a work turn.
            if state["status"] == "FAILED":
                while True:
                    time.sleep(.5)
    except (LaunchError, OSError, ValueError) as exc:
        state.update(status="FAILED", error=exc.code if isinstance(exc, LaunchError) else type(exc).__name__,
                     error_status=exc.status if isinstance(exc, LaunchError) else "UNKNOWN")
        atomic_json(root / "state.json", state)
        return 3
    finally:
        if rpc:
            rpc.close()


def create_screen(home: Path, name: str, request: dict, *, screen_binary: Path, codex_binary: Path,
                  environment: dict[str, str], dispatch_claim, target_guard=None,
                  timeout: float = 30, work_timeout: float = 1800) -> dict:
    class LazyScreen:
        # LaunchJournal reserves before starting even a provisional transport.
        # A reused launch ID cannot cause a second Screen or App Server process.
        inner = None
        startup_error_receipt = None

        def describe(self, bound_request, attempt):
            try:
                self.inner = ScreenLaunchProvider.start(home, name, bound_request, screen_binary=screen_binary,
                                                       codex_binary=codex_binary, environment=environment,
                                                       timeout=timeout, work_timeout=work_timeout)
            except LaunchError as exc:
                self.startup_error_receipt = exc.receipt
                raise
            return self.inner.describe(bound_request, attempt)

        def create(self, bound_request, attempt):
            return self.inner.create(bound_request, attempt)

        def probe(self, bound_request, startup, attempt):
            return self.inner.probe(bound_request, startup, attempt)

        def dispatch(self, bound_request, startup, envelope):
            return self.inner.dispatch(bound_request, startup, envelope)

    provider = LazyScreen()
    journal = LaunchJournal(home, request["launch_id"])
    try:
        receipt = launch(request, provider, target_guard=target_guard, dispatch_claim=dispatch_claim, journal=journal)
    except LaunchError as exc:
        if provider.inner is not None:
            exc.receipt["screen"] = provider.inner.status()
            journal.save(exc.receipt)
        elif provider.startup_error_receipt:
            exc.receipt["provisional_screen"] = provider.startup_error_receipt
            journal.save(exc.receipt)
        raise
    receipt["screen"] = provider.inner._state()
    atomic_json(provider.inner.root / "launch.json", receipt)
    return receipt


def continue_managed(home: Path, socket: str, prompt: str, *, screen_binary: Path,
                     environment: dict[str, str], dispatch_claim, target_guard=None,
                     continuation_id: str | None = None) -> dict | None:
    match = SOCKET.fullmatch(socket)
    if not match:
        # Existing GNU Screen names may exceed this adapter's narrower creation
        # grammar. They remain discoverable TUI sessions with the original proof
        # route; this adapter never turns such a name into a filesystem path.
        return None
    root = worker_root(home, match["name"])
    if not root.exists():
        return None  # Legacy TUI continuation retains its existing proof route.
    if not 1 <= len(prompt.strip()) <= 20000:
        raise LaunchError("prompt_length_invalid")
    provider = ScreenLaunchProvider(root, screen_binary, environment)
    state = provider._state()
    if state["socket"] != socket:
        raise LaunchError("screen_socket_identity_mismatch", status="UNKNOWN")
    request = _read(root / "bootstrap.json")["request"]
    initial = _read(root / "launch.json")
    if initial.get("phase") != "DISPATCH_OBSERVED" or initial.get("work", {}).get("status") != "completed":
        raise LaunchError("screen_initial_work_requires_reconciliation", status="UNKNOWN")
    startup = _read(root / "startup.json")
    attempt = str(uuid.uuid4())
    # The caller can intentionally repeat a prompt with a new explicit identity;
    # the default refuses an accidental repeated delivery of the same prompt.
    key = continuation_id or digest([socket, prompt])
    journal = root / "continuations" / (digest(key) + ".json")
    with lock(root / "continuation.lock"):
        if journal.exists():
            raise LaunchError("screen_continuation_requires_reconciliation", status="UNKNOWN", receipt=_read(journal))
        receipt = {"schema": "agentos.screen-continuation/v1", "attempt_id": attempt,
                   "request_sha256": digest(request), "prompt_sha256": digest(prompt),
                   "session_id": startup["session_id"], "work_accepted": False, "status": "PREFLIGHT"}
        atomic_json(journal, receipt)
        try:
            observed = provider.describe(request, attempt)
            _observation(request, observed, attempt, startup=False, clock=time.time)
            receipt["current_preflight"] = observed
            receipt["original_startup"] = startup
            if any(observed[key] != startup[key] for key in ("connection_id", "sandbox", "approval_policy", "workspace")):
                raise LaunchError("screen_continuation_environment_changed", status="UNKNOWN")
            # A current catalog/config read cannot relabel the original startup
            # as fresh actual runtime. Compare it with the retained readback.
            receipt["model_binding"] = _model_binding(observed, startup)
            def guard(bound_request, phase):
                bound_request["_launch_attempt_id"] = attempt
                return target_guard(bound_request, phase)
            _targets(request, guard if target_guard else None, "before_create", attempt, time.time)
            probe = provider.probe(request, startup, attempt)
            receipt["probe"] = probe
            if probe.get("status") != "PASS":
                raise LaunchError("screen_continuation_probe_failed", status="BLOCKED")
            _targets(request, guard if target_guard else None, "before_dispatch", attempt, time.time)
            dispatch_claim(request, startup["session_id"])
            receipt["status"] = "DISPATCHING"
            atomic_json(journal, receipt)
            envelope = prompt + "\n\nRetained original task contract (no additional authority):\n" + json.dumps(request, sort_keys=True, ensure_ascii=False)
            receipt["work"] = provider.dispatch(request, startup, envelope)
            receipt["status"] = "DISPATCH_OBSERVED"
        except (LaunchError, GateError, OSError, TimeoutError) as exc:
            receipt.update(status=exc.status if isinstance(exc, LaunchError) else "BLOCKED" if isinstance(exc, GateError) else "UNKNOWN",
                           error=exc.code if isinstance(exc, LaunchError) else str(exc))
            atomic_json(journal, receipt)
            raise
        atomic_json(journal, receipt)
        return receipt


if __name__ == "__main__":
    import signal

    def _terminated(signum, _frame):
        raise SystemExit(128 + signum)

    # A caller returning never signals this worker. An operator ending this
    # exact Screen can still let its own stdio child close and reap cleanly.
    signal.signal(signal.SIGTERM, _terminated)
    signal.signal(signal.SIGHUP, _terminated)
    if len(sys.argv) != 3 or sys.argv[1] != "worker":
        raise SystemExit("supported invocation: python -m agent_os.screen_launch worker <exact-worker-directory>")
    raise SystemExit(_worker(Path(sys.argv[2]).resolve()))
