"""Codex App Server stdio launch adapter, with inherited permissions only.

The existing native-daemon NativeRpc intentionally has a different allowlist.
This adapter opens its own stdio child and never connects to or reconfigures that
daemon. API fields are sourced in docs/SESSION_LAUNCH.md. Live compatibility is
checked against an explicitly approved local binary version and actual replies.
"""

from __future__ import annotations

import json
import math
import os
import re
import selectors
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .safeio import digest
from .session_launch import LaunchError, _observation as validate_observation

PROVIDER = "codex-app-server-stdio"
SUPPORTED_CAPABILITIES = {"filesystem_read", "filesystem_write", "network_http", "loopback_http"}
MAX_BYTES = 1024 * 1024
MODEL_PAGE_SIZE = 100
MAX_MODEL_PAGES = 4
MAX_MODEL_ENTRIES = 256


class StdioRpc:
    """Bounded JSONL connection; no auth, policy setters or approval replies."""

    def __init__(self, binary: Path, workspace: Path, environment: dict[str, str], approved_version: str, *, timeout: float = 20):
        if os.name == "nt":
            raise LaunchError("stdio_pipe_adapter_unavailable_on_windows", status="UNAVAILABLE")
        if not binary.is_absolute() or not binary.is_file() or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9.-]+)?", approved_version or "") or not 0 < timeout <= 45:
            raise LaunchError("approved_binary_version_and_timeout_required", status="UNKNOWN")
        actual = subprocess.run([str(binary), "--version"], capture_output=True, text=True,
                                check=True, timeout=timeout, env=environment).stdout.strip()
        if actual not in {"codex " + approved_version, "codex-cli " + approved_version}:
            raise LaunchError("approved_codex_version_mismatch")
        self.connection_id = str(uuid.uuid4())
        self.version = approved_version
        self.timeout = timeout
        self.sequence = 0
        self.buffer = b""
        self.pending: list[dict] = []
        self.process = subprocess.Popen([str(binary), "app-server"], cwd=str(workspace), env=environment,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, bufsize=0)
        self.readable = selectors.DefaultSelector()
        self.readable.register(self.process.stdout, selectors.EVENT_READ)
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        try:
            self._request("initialize", {"clientInfo": {"name": "agentos_launch", "version": "1"},
                                         "capabilities": {"experimentalApi": True}})
            self._send({"method": "initialized", "params": {}}, time.monotonic() + timeout)
        except BaseException:
            self.close()
            raise

    def _send(self, message: dict, deadline: float) -> None:
        raw = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        if len(raw) > MAX_BYTES:
            raise LaunchError("request_size_limit")
        with selectors.DefaultSelector() as writable:
            writable.register(self.process.stdin, selectors.EVENT_WRITE)
            offset = 0
            while offset < len(raw):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("codex_stdio_write_timeout")
                if not writable.select(min(remaining, .1)):
                    continue
                try:
                    count = os.write(self.process.stdin.fileno(), raw[offset:])
                except BlockingIOError:
                    continue
                if count <= 0:
                    raise OSError("codex_stdio_closed")
                offset += count

    def _receive(self, deadline: float) -> dict:
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("codex_stdio_read_timeout")
            if not self.readable.select(min(remaining, .1)):
                continue
            piece = os.read(self.process.stdout.fileno(), 65536)
            if not piece:
                raise OSError("codex_stdio_closed")
            self.buffer += piece
            if len(self.buffer) > MAX_BYTES:
                raise LaunchError("provider_response_limit", status="UNKNOWN")
        line, self.buffer = self.buffer.split(b"\n", 1)
        message = json.loads(line)
        if not isinstance(message, dict):
            raise LaunchError("provider_response_invalid", status="UNKNOWN")
        if "method" in message and "id" in message:
            # Never synthesize an approval, even for a harmless probe.
            raise LaunchError("provider_approval_or_input_pending", status="BLOCKED")
        return message

    def _request(self, method: str, params: dict, *, deadline: float | None = None) -> dict:
        self.sequence += 1
        deadline = min(deadline, time.monotonic() + self.timeout) if deadline is not None else time.monotonic() + self.timeout
        self._send({"id": self.sequence, "method": method, "params": params}, deadline)
        for _ in range(1024):
            message = self._receive(deadline)
            if message.get("id") != self.sequence:
                if "method" in message:
                    if len(self.pending) >= 256:
                        raise LaunchError("provider_event_limit", status="UNKNOWN")
                    self.pending.append(message)
                continue
            if "error" in message:
                # RPC errors may contain arbitrary provider text. Retain only
                # a protocol integer, never messages or a string posing as code.
                error = message["error"]
                code = error.get("code") if isinstance(error, dict) else None
                code = code if type(code) is int and -32768 <= code <= 32767 else None
                raise LaunchError("provider_rpc_error", status="UNAVAILABLE", receipt={"rpc_error_code": code})
            if not isinstance(message.get("result"), dict):
                raise LaunchError("provider_result_missing", status="UNKNOWN")
            return message["result"]
        raise LaunchError("provider_response_limit", status="UNKNOWN")

    def call(self, method: str, params: dict, *, deadline: float | None = None) -> dict:
        allowed = {"config/read": {"includeLayers", "cwd"}, "thread/start": {"cwd"},
                   "turn/start": {"threadId", "input"}, "model/list": {"cursor", "limit", "includeHidden"}}
        if method not in allowed or set(params) != allowed[method]:
            raise LaunchError("provider_method_or_override_refused")
        if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline)):
            raise LaunchError("bounded_rpc_deadline_required")
        if method == "config/read" and params["includeLayers"] is not False:
            raise LaunchError("config_layers_not_requested")
        if method == "model/list" and (params["includeHidden"] is not True or type(params["limit"]) is not int
                                       or params["limit"] != MODEL_PAGE_SIZE
                                       or params["cursor"] is not None and (not isinstance(params["cursor"], str)
                                                                          or not 1 <= len(params["cursor"]) <= 4096)):
            raise LaunchError("bounded_read_only_model_list_required")
        if method == "turn/start" and (not isinstance(params["input"], list) or len(params["input"]) != 1 or
                                      set(params["input"][0]) != {"type", "text"} or params["input"][0]["type"] != "text"):
            raise LaunchError("exact_text_turn_required")
        return self._request(method, params, deadline=deadline)

    def events_until_complete(self, session_id: str, turn_id: str, timeout: float) -> list[dict]:
        if not 0 < timeout <= 1800:
            raise LaunchError("bounded_turn_timeout_required")
        deadline = time.monotonic() + timeout
        selected: list[dict] = []
        size = 0
        for _ in range(4096):
            message = self.pending.pop(0) if self.pending else self._receive(deadline)
            params = message.get("params", {})
            if params.get("threadId") != session_id:
                continue
            event_turn = params.get("turnId") or params.get("turn", {}).get("id")
            if event_turn != turn_id:
                continue
            if message.get("method") in {"item/completed", "turn/completed"}:
                selected.append(message)
                size += len(json.dumps(message))
                if size > MAX_BYTES or len(selected) > 256:
                    raise LaunchError("bounded_turn_evidence_exceeded", status="UNKNOWN")
            if message.get("method") == "turn/completed":
                return selected
        raise LaunchError("provider_event_limit", status="UNKNOWN")

    def close(self) -> None:
        if getattr(self, "process", None) is None:
            return
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=.5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=.5)
        if self.process.stdout:
            self.process.stdout.close()
        self.readable.close()


def _policy(value: object) -> str | dict | None:
    # Config uses kebab case; documented legacy thread responses may use aliases.
    if value in ("never", "untrusted", "on-request"):
        return value
    if value == "unlessTrusted":
        return "untrusted"
    if value == "onRequest":
        return "on-request"
    if isinstance(value, dict) and isinstance(value.get("granular"), dict):
        return value
    return None


def _sandbox(value: object) -> str | None:
    aliases = {"read-only": "read-only", "readOnly": "read-only", "workspace-write": "workspace-write",
               "workspaceWrite": "workspace-write", "danger-full-access": "danger-full-access", "dangerFullAccess": "danger-full-access"}
    return aliases.get(value) if isinstance(value, str) else None


def _commands(request: dict, attempt: str) -> dict[str, tuple[str, str]]:
    result = {}
    for capability in request["required_capabilities"]:
        marker = "AGENTOS_PROBE_" + attempt.replace("-", "") + "_" + capability
        if capability == "filesystem_read":
            code = "import os; os.listdir('.'); print(" + repr(marker) + ")"
        elif capability == "filesystem_write":
            code = ("import os,tempfile; f=tempfile.NamedTemporaryFile(prefix='.agentos-probe-',dir='.',delete=False); "
                    "p=f.name; f.write(b'probe'); f.close(); assert open(p,'rb').read()==b'probe'; os.unlink(p); print(" + repr(marker) + ")")
        elif capability == "loopback_http":
            code = ("import http.server,threading,urllib.request; s=http.server.HTTPServer(('127.0.0.1',0),http.server.BaseHTTPRequestHandler); "
                    "s.RequestHandlerClass.do_HEAD=lambda self:(self.send_response(200),self.end_headers()); "
                    "s.RequestHandlerClass.log_message=lambda *args:None; t=threading.Thread(target=s.serve_forever,daemon=True); t.start(); "
                    "r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:'+str(s.server_port),method='HEAD'),timeout=3); "
                    "assert r.status==200; r.close(); s.shutdown(); s.server_close(); t.join(timeout=1); print(" + repr(marker) + ")")
        elif capability == "network_http":
            url = request.get("probe_url")
            parsed = urlsplit(url or "")
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise LaunchError("explicit_harmless_https_probe_url_required", status="UNKNOWN")
            # The destination belongs to the task's accepted read scope. Do not
            # follow redirects into an unreviewed destination or send auth.
            code = ("import urllib.request;\nclass NoRedirect(urllib.request.HTTPRedirectHandler):\n"
                    " def redirect_request(self,*args): return None\n"
                    "r=urllib.request.build_opener(NoRedirect()).open(urllib.request.Request(" + repr(url) + ",method='HEAD'),timeout=5)\n"
                    "assert 200<=r.status<300\nr.close()\nprint(" + repr(marker) + ")")
        else:
            raise LaunchError("codex_probe_capability_unsupported:" + capability, status="UNKNOWN")
        # A shell startup file may change directories after the provider records
        # its spawn cwd. Bind the actual Python process to the requested root too.
        code = "import os; assert os.path.samefile(os.getcwd(), " + repr(request["workspace"]) + "); " + code
        result[capability] = (shlex.join(["python3", "-c", code]), marker)
    return result


def _command_script(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parts = shlex.split(value)
    except ValueError:
        return None
    if len(parts) == 3 and Path(parts[0]).name in {"bash", "zsh", "sh"} and parts[1] in {"-c", "-lc"}:
        return parts[2]
    return value


def _model_scalar(value: object) -> bool:
    """Bounded protocol identifiers, not descriptions or provider messages."""
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", value))


def _model_binding(preflight: dict, startup: dict) -> dict:
    """Compare provisional catalog/config metadata with actual thread readback.

    Model-list rows carry no provider namespace. An unconfigured provider is
    provisional until the required actual startup identity is returned. Catalog
    membership is only connection-local advertisement; it never proves access.
    A null startup effort stays null, including when a catalog default exists.
    """
    for key in ("model", "model_provider"):
        if not _model_scalar(startup.get(key)):
            raise LaunchError("startup_" + key + "_unknown", status="UNKNOWN")
    if startup["model"] != preflight["model"]:
        raise LaunchError("startup_changed:model")
    configured_provider = preflight["model_provider"]
    if configured_provider is not None and startup["model_provider"] != configured_provider:
        raise LaunchError("startup_changed:model_provider")
    actual_effort = startup.get("reasoning_effort")
    if actual_effort is not None and not _model_scalar(actual_effort):
        raise LaunchError("startup_reasoning_effort_unknown", status="UNKNOWN")
    metadata = preflight.get("model_preflight", {})
    configured_effort = metadata.get("configured_reasoning_effort")
    if configured_effort is not None:
        if actual_effort is None:
            raise LaunchError("startup_reasoning_effort_unknown", status="UNKNOWN")
        if actual_effort != configured_effort:
            raise LaunchError("startup_changed:reasoning_effort")
    if actual_effort is not None and actual_effort not in metadata.get("supported_reasoning_efforts", []):
        raise LaunchError("startup_reasoning_effort_not_advertised", status="UNKNOWN")
    return {"model": "PASS", "model_provider": "PASS",
            "provider_resolution": "startup_resolved" if configured_provider is None else "configured_match",
            "reasoning_effort": "UNKNOWN" if actual_effort is None else "PASS",
            "source": "thread_start_response", "provider_compatibility": "NOT_PROVEN"}


def _safe_turn_failure(turn: dict) -> dict | None:
    """Finite diagnostic metadata only; never copy raw provider error text."""
    status = turn.get("status")
    if status == "completed":
        return None
    categories = {"contextWindowExceeded": "context_limit", "sessionBudgetExceeded": "budget_limit",
                  "usageLimitExceeded": "usage_limit", "rateLimitExceeded": "rate_limit",
                  "flexUnavailable": "service_unavailable", "serverOverloaded": "service_unavailable",
                  "cyberPolicy": "policy_block", "misalignmentPolicyViolation": "policy_block",
                  "tooManyDenials": "policy_block", "internalServerError": "provider_server_error",
                  "unauthorized": "authentication", "badRequest": "invalid_request",
                  "threadRollbackFailed": "thread_rollback_failed", "sandboxError": "sandbox_error",
                  "other": "provider_error", "httpConnectionFailed": "connection_error",
                  "responseStreamConnectionFailed": "connection_error", "responseStreamDisconnected": "connection_error",
                  "responseTooManyFailedAttempts": "retry_limit", "activeTurnNotSteerable": "active_turn_not_steerable"}
    error = turn.get("error")
    error = error if isinstance(error, dict) else {}
    info = error.get("codexErrorInfo")
    name = info if isinstance(info, str) and info in categories else "unknown"
    http_status = None
    if isinstance(info, dict) and len(info) == 1:
        key = next(iter(info))
        if key in categories and isinstance(info[key], dict):
            name = key
            http_status = info[key].get("httpStatusCode")
    category = categories.get(name, "provider_error")
    # Some supported binaries serialize the upstream JSON error as message.
    # Parse only a bounded object and retain whitelisted type/status metadata.
    message = error.get("message")
    if isinstance(message, str) and len(message) <= 16384:
        try:
            upstream = json.loads(message)
        except (ValueError, RecursionError):
            upstream = None
        if isinstance(upstream, dict):
            nested = upstream.get("error")
            nested = nested if isinstance(nested, dict) else {}
            upstream_categories = {"invalid_request_error": "invalid_request", "authentication_error": "authentication",
                                   "permission_error": "permission_denied", "rate_limit_error": "rate_limit",
                                   "server_error": "provider_server_error"}
            if name in {"unknown", "other"}:
                candidate = nested.get("type")
                if isinstance(candidate, str) and candidate in upstream_categories:
                    category = upstream_categories[candidate]
            if http_status is None:
                http_status = upstream.get("status")
    if type(http_status) is not int or not 100 <= http_status <= 599:
        http_status = None
    return {"category": category, "codex_error_info": name, "http_status": http_status,
            "turn_status": status if isinstance(status, str) and status in {"failed", "interrupted", "inProgress"} else "unknown"}


class CodexLaunchProvider:
    def __init__(self, rpc: StdioRpc, *, clock=time.time, probe_timeout: float = 45, work_timeout: float = 1800):
        self.rpc, self.clock = rpc, clock
        self.probe_timeout, self.work_timeout = probe_timeout, work_timeout
        self._model_admission = None
        self._thread_start_attempted = False

    def _observation(self, request: dict, attempt: str, *, source: str, policy: object, mode: object,
                     network: object, workspace: object, session_id: str | None = None) -> dict:
        approval, sandbox = _policy(policy), _sandbox(mode)
        if approval == "untrusted":
            ordinary = "interactive"
        elif approval == "never":
            ordinary = "noninteractive"
        elif approval == "on-request":
            ordinary = "within_policy"
        elif isinstance(approval, dict) and approval["granular"].get("sandbox_approval") is False and approval["granular"].get("rules") is False:
            ordinary = "within_policy"
        else:
            ordinary = "unknown"
        net = True if sandbox == "danger-full-access" else network if isinstance(network, bool) else None
        capabilities = {"filesystem_read": True if sandbox else None,
                        "filesystem_write": sandbox in {"workspace-write", "danger-full-access"} if sandbox else None,
                        "network_http": net, "loopback_http": net}
        return {"source": source, "attempt_id": attempt, "observed_at": self.clock(),
                "executor_id": request["executor"]["id"], "provider": PROVIDER,
                "connection_id": self.rpc.connection_id, "provider_version": self.rpc.version,
                "workspace": workspace, "sandbox": sandbox, "approval_policy": approval,
                "ordinary_commands": ordinary, "capabilities": capabilities, "session_id": session_id}

    def _model_description(self, config: dict) -> dict:
        configured_model, configured_provider = config.get("model"), config.get("model_provider")
        configured_effort = config.get("model_reasoning_effort")
        if configured_provider is not None and not _model_scalar(configured_provider):
            raise LaunchError("inherited_model_provider_unknown", status="UNKNOWN")
        # Missing/null is the supported absence of an explicit override. Keep
        # it provisional; only thread/start may supply the actual identity.
        if configured_model is not None and not _model_scalar(configured_model):
            raise LaunchError("inherited_model_unknown", status="UNKNOWN")
        if configured_effort is not None and not _model_scalar(configured_effort):
            raise LaunchError("inherited_reasoning_effort_unknown", status="UNKNOWN")
        timeout = getattr(self.rpc, "timeout", 20)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 45:
            raise LaunchError("bounded_model_catalog_timeout_required", status="UNKNOWN")
        deadline = time.monotonic() + min(timeout, 20)
        rows, seen_cursors, cursor = [], set(), None
        for page in range(1, MAX_MODEL_PAGES + 1):
            if time.monotonic() >= deadline:
                raise LaunchError("model_catalog_timeout", status="UNKNOWN")
            try:
                response = self.rpc.call("model/list", {"cursor": cursor, "limit": MODEL_PAGE_SIZE, "includeHidden": True},
                                         deadline=deadline)
            except (OSError, TimeoutError) as exc:
                raise LaunchError("model_catalog_unavailable", status="UNKNOWN") from exc
            if time.monotonic() >= deadline:
                raise LaunchError("model_catalog_timeout", status="UNKNOWN")
            if not isinstance(response, dict) or not isinstance(response.get("data"), list):
                raise LaunchError("model_catalog_invalid", status="UNKNOWN")
            if len(response["data"]) > MODEL_PAGE_SIZE or len(rows) + len(response["data"]) > MAX_MODEL_ENTRIES:
                raise LaunchError("model_catalog_entry_limit", status="UNKNOWN")
            for row in response["data"]:
                if (not isinstance(row, dict) or not _model_scalar(row.get("id")) or not _model_scalar(row.get("model"))
                        or type(row.get("isDefault")) is not bool or not _model_scalar(row.get("defaultReasoningEffort"))
                        or not isinstance(row.get("supportedReasoningEfforts"), list) or len(row["supportedReasoningEfforts"]) > 32):
                    raise LaunchError("model_catalog_metadata_unknown", status="UNKNOWN")
                efforts = [item.get("reasoningEffort") if isinstance(item, dict) else None for item in row["supportedReasoningEfforts"]]
                if any(not _model_scalar(effort) for effort in efforts) or len(set(efforts)) != len(efforts):
                    raise LaunchError("model_catalog_metadata_unknown", status="UNKNOWN")
                rows.append({"id": row["id"], "model": row["model"], "is_default": row["isDefault"],
                             "default_reasoning_effort": row["defaultReasoningEffort"], "supported_reasoning_efforts": efforts})
            # This optional protocol field represents None when omitted;
            # None is documented as terminal. A non-null cursor is never ignored.
            cursor = response.get("nextCursor")
            if cursor is None:
                break
            if not isinstance(cursor, str) or not 1 <= len(cursor) <= 4096 or cursor in seen_cursors:
                raise LaunchError("model_catalog_cursor_invalid", status="UNKNOWN")
            seen_cursors.add(cursor)
        else:
            raise LaunchError("model_catalog_page_limit", status="UNKNOWN")
        if len({row["id"] for row in rows}) != len(rows) or len({row["model"] for row in rows}) != len(rows):
            raise LaunchError("model_catalog_ambiguous", status="UNKNOWN")
        if configured_model is None:
            defaults = [row for row in rows if row["is_default"]]
            if len(defaults) != 1:
                raise LaunchError("inherited_model_default_unknown", status="UNKNOWN")
            selected, model_source = defaults[0], "catalog_default"
        else:
            if any(row["id"] == configured_model and row["model"] != configured_model for row in rows):
                raise LaunchError("inherited_model_alias_unresolved", status="UNKNOWN")
            matches = [row for row in rows if row["model"] == configured_model]
            if len(matches) != 1:
                # Absence is a refusal, not a claim that a custom provider's
                # unqualified catalog proves its model cannot exist.
                raise LaunchError("inherited_model_not_advertised", status="UNKNOWN")
            selected, model_source = matches[0], "configured_exact"
        default_effort = selected["default_reasoning_effort"]
        supported_efforts = selected["supported_reasoning_efforts"]
        if default_effort not in supported_efforts:
            raise LaunchError("model_catalog_default_effort_unknown", status="UNKNOWN")
        if configured_effort is not None and configured_effort not in supported_efforts:
            raise LaunchError("inherited_reasoning_effort_not_advertised", status="UNKNOWN")
        metadata = {"source": "same_connection_model_list", "catalog_scope": "connection_advertised_models",
                    "provider_compatibility": "NOT_PROVEN", "configured_model": configured_model,
                    "configured_provider": configured_provider, "configured_provider_present": "model_provider" in config,
                    "provider_source": "unconfigured" if configured_provider is None else "configured_exact",
                    "configured_reasoning_effort": configured_effort,
                    "model_source": model_source, "reasoning_effort_source": "configured_exact" if configured_effort is not None else "catalog_default",
                    "catalog_default_reasoning_effort": default_effort, "supported_reasoning_efforts": supported_efforts,
                    "matched_catalog_id": selected["id"], "catalog_complete": True, "catalog_pages": page,
                    "catalog_model_count": len(rows), "catalog_sha256": digest(rows)}
        return {"model": selected["model"], "model_provider": configured_provider,
                "reasoning_effort": configured_effort if configured_effort is not None else default_effort,
                "model_preflight": metadata}

    def describe(self, request: dict, attempt: str) -> dict:
        self._model_admission = None
        if request["executor"]["provider"] != PROVIDER:
            raise LaunchError("codex_provider_selection_mismatch")
        _commands(request, attempt)  # Validate unsupported tools/URLs before creation.
        response = self.rpc.call("config/read", {"includeLayers": False, "cwd": request["workspace"]})
        config = response.get("config", {})
        if not isinstance(config, dict):
            raise LaunchError("effective_config_missing", status="UNKNOWN")
        # Retain only these non-secret scalars, never raw config/layers/auth data.
        observed = self._observation(request, attempt, source="provider_effective", policy=config.get("approval_policy"),
                                     mode=config.get("sandbox_mode"), workspace=request["workspace"],
                                     network=(config.get("sandbox_workspace_write") or {}).get("network_access"))
        executor = request["executor"]
        if "approved_sandbox" not in executor or "approved_approval_policy" not in executor:
            raise LaunchError("owner_approved_mode_reference_required", status="UNKNOWN")
        if observed["sandbox"] is not None and observed["sandbox"] != _sandbox(executor["approved_sandbox"]):
            raise LaunchError("inherited_sandbox_not_owner_selected")
        if observed["approval_policy"] is not None and observed["approval_policy"] != _policy(executor["approved_approval_policy"]):
            raise LaunchError("inherited_approval_policy_not_owner_selected")
        # Existing mode/capability admission still fails first. An unknown mode
        # or a known interactive mismatch does not require further discovery.
        validate_observation(request, observed, attempt, startup=False, clock=self.clock)
        observed.update(self._model_description(config))
        self._model_admission = {"attempt": attempt, "request_sha256": digest(request),
                                 "observed": json.loads(json.dumps(observed)), "read_at": time.monotonic()}
        return observed

    def create(self, request: dict, attempt: str) -> dict:
        admitted = self._model_admission
        if (not admitted or admitted["attempt"] != attempt or admitted["request_sha256"] != digest(request)
                or admitted["observed"]["connection_id"] != self.rpc.connection_id
                or not 0 <= time.monotonic() - admitted["read_at"] <= 60):
            raise LaunchError("current_model_preflight_required", status="UNKNOWN")
        if self._thread_start_attempted:
            raise LaunchError("thread_start_requires_reconciliation", status="UNKNOWN")
        self._thread_start_attempted = True
        response = self.rpc.call("thread/start", {"cwd": request["workspace"]})
        sandbox = response.get("sandbox") or {}
        thread = response.get("thread") or {}
        observed = self._observation(request, attempt, source="provider_startup", policy=response.get("approvalPolicy"),
                                     mode=sandbox.get("type"), network=sandbox.get("networkAccess"),
                                     workspace=response.get("cwd"), session_id=thread.get("id"))
        observed.update(model=response.get("model"), model_provider=response.get("modelProvider"),
                        reasoning_effort=response.get("reasoningEffort"), model_metadata_source="thread_start_response")
        # Keep only normalized scalar metadata even when a malformed response
        # causes refusal; the actual thread identity is needed for reconciliation.
        for key in ("model", "model_provider", "reasoning_effort"):
            if not _model_scalar(observed[key]):
                observed[key] = None
        observed["model_preflight"] = admitted["observed"]["model_preflight"]
        try:
            observed["model_binding"] = _model_binding(admitted["observed"], observed)
        except LaunchError as exc:
            exc.receipt = {"startup": observed}
            raise
        return observed

    def _turn(self, session_id: str, prompt: str, timeout: float) -> tuple[str, list[dict]]:
        response = self.rpc.call("turn/start", {"threadId": session_id, "input": [{"type": "text", "text": prompt}]})
        turn_id = response.get("turn", {}).get("id")
        if not isinstance(turn_id, str) or not turn_id:
            raise LaunchError("turn_id_missing", status="UNKNOWN")
        return turn_id, self.rpc.events_until_complete(session_id, turn_id, timeout)

    def probe(self, request: dict, startup: dict, attempt: str) -> dict:
        commands = _commands(request, attempt)
        prompt = ("Startup capability probe only. Run each exact command below through the ordinary command-execution tool in "
                  + request["workspace"] + ". Do not escalate permissions, change settings, access credentials or perform business work. "
                  "Do not substitute an acknowledgement for command execution. Stop on failure.\n"
                  + "\n\n".join(command for command, _ in commands.values()))
        turn_id, events = self._turn(startup["session_id"], prompt, self.probe_timeout)
        proven, evidence, unexpected = set(), [], False
        for event in events:
            item = event.get("params", {}).get("item", {})
            if item.get("type") == "commandExecution":
                command = _command_script(item.get("command"))
                matched = next((cap for cap, (script, _) in commands.items() if command == script), None)
                cwd = item.get("cwd")
                cwd_matches = isinstance(cwd, str) and Path(cwd).is_absolute() and Path(cwd).resolve() == Path(request["workspace"]).resolve()
                ok = matched is not None and cwd_matches and item.get("status") == "completed" and item.get("exitCode") == 0 and commands[matched][1] in item.get("aggregatedOutput", "")
                if ok:
                    proven.add(matched)
                else:
                    unexpected = True
                evidence.append({"item_id": item.get("id"), "command_sha256": digest(item.get("command")),
                                 "output_sha256": digest(item.get("aggregatedOutput")), "exit_code": item.get("exitCode"), "matched": matched})
            elif item.get("type") == "userMessage":
                # App Server emits the submitted user input in item/completed.
                # It is neither a tool nor execution proof. Accept only this
                # exact probe input; unrelated input still invalidates the turn.
                content = item.get("content")
                if not (isinstance(content, list) and len(content) == 1
                        and isinstance(content[0], dict) and content[0].get("type") == "text"
                        and content[0].get("text") == prompt):
                    unexpected = True
            elif item.get("type") not in {None, "agentMessage", "reasoning", "plan"}:
                unexpected = True
        completed_turn = events[-1].get("params", {}).get("turn", {}) if events else {}
        completed = completed_turn.get("status") == "completed"
        return {"source": "provider_tool_evidence", "attempt_id": attempt, "session_id": startup["session_id"],
                "turn_id": turn_id, "status": "PASS" if completed and not unexpected and proven == set(commands) else "FAIL",
                "capabilities": sorted(proven), "items": evidence, "unexpected_tool_use": unexpected,
                "failure": _safe_turn_failure(completed_turn),
                "proofs": [{"capability": cap, "status": "PASS", "evidence_ref": startup["session_id"] + "/" + turn_id + "/" + str(item["item_id"])}
                           for cap in sorted(proven) for item in evidence if item["matched"] == cap and item.get("item_id")]}

    def dispatch(self, request: dict, startup: dict, envelope: str) -> dict:
        turn_id, events = self._turn(startup["session_id"], envelope, self.work_timeout)
        completed = events[-1].get("params", {}).get("turn", {}) if events else {}
        items = [event["params"]["item"] for event in events if event["method"] == "item/completed"]
        return {"session_id": startup["session_id"], "turn_id": turn_id, "status": completed.get("status", "unknown"),
                "completed_tool_items": sum(item.get("type") in {"commandExecution", "fileChange", "mcpToolCall"} for item in items),
                "failure": _safe_turn_failure(completed),
                "semantic_acceptance": "NOT_EVALUATED"}
