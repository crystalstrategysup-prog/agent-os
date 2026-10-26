"""Hash-pinned trusted-source replay in a child with audit and syscall guards.

This is a fixture harness, not an adversarial native-code security sandbox.
No credentials or production inputs are required or inherited by the child.
"""
from __future__ import annotations

import datetime
import hashlib
import importlib
import importlib.abc
import importlib.util
import io
import inspect
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import sysconfig
import tempfile
import time
import uuid
import math


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _refused(reason):
    return {"schema": "route-probe.trace/v1", "status": "REFUSED", "reason": reason, "spans": [],
            "sandbox": {"seccomp": False, "audit": False}}


def _bounded_child(argv, env, timeout):
    """Bound pipes while running, not after an unbounded communicate()."""
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, close_fds=True)
    outputs = {"stdout": bytearray(), "stderr": bytearray()}
    selector = selectors.DefaultSelector()
    for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
        os.set_blocking(pipe.fileno(), False)
        selector.register(pipe, selectors.EVENT_READ, name)
    end = time.monotonic() + timeout
    failure = None
    try:
        while selector.get_map():
            remaining = end - time.monotonic()
            if remaining <= 0:
                failure = "whole_replay_deadline"; break
            for key, _ in selector.select(min(remaining, .1)):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj); continue
                name = key.data
                if len(outputs[name]) + len(data) > (2_000_000 if name == "stdout" else 65536):
                    failure = "child_output_bound"; break
                outputs[name].extend(data)
            if failure:
                break
        if failure:
            process.kill()  # This exact owned, network-denied fixture child only.
        try:
            process.wait(timeout=max(.1, end - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=2); failure = "whole_replay_deadline"
        return failure, process.returncode, bytes(outputs["stdout"]), bytes(outputs["stderr"])
    finally:
        selector.close()
        for pipe in (process.stdout, process.stderr):
            pipe.close()
        if process.poll() is None:
            process.kill(); process.wait(timeout=2)


def _read_public(path, cap):
    """Bounded regular file through a no-follow walk; no secret-path probing."""
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("bundle_path")
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory); directory = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > cap:
            raise ValueError("bundle_file_type_or_bound")
        data = stream.read(cap + 1)
        after = os.fstat(stream.fileno())
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")
    if len(data) > cap or any(getattr(before, f) != getattr(after, f) for f in fields):
        raise ValueError("bundle_file_changed")
    return data


def _verify(bundle, *, with_sources=False):
    bundle = Path(bundle).absolute()
    raw = _read_public(bundle / "manifest.json", 100_000)
    if hashlib.sha256(raw).hexdigest() != _read_public(bundle / "manifest.sha256", 100).decode().strip():
        raise ValueError("manifest_pin")
    m = json.loads(raw)
    if m.get("schema") != "route-probe.bundle/v1" or not 0 < len(m["files"]) <= 160:
        raise ValueError("manifest_schema")
    seen = set(); sources = {}; total = 0
    for row in m["files"]:
        rel = Path(row["path"])
        if rel.is_absolute() or ".." in rel.parts or str(rel) in seen:
            raise ValueError("bundle_path")
        seen.add(str(rel))
        p = bundle / "source" / rel
        if p.is_symlink() or not p.resolve().is_relative_to(bundle / "source"):
            raise ValueError("bundle_path")
        b = _read_public(p, 2_000_000)
        total += len(b)
        if total > 16_000_000:
            raise ValueError("source_total_bound")
        if len(b) != row["bytes"] or hashlib.sha256(b).hexdigest() != row["sha256"]:
            raise ValueError("source_pin")
        sources[str(rel)] = b
    graph_bytes = _read_public(bundle / "route_graph.json", 8_000_000)
    if hashlib.sha256(graph_bytes).hexdigest() != m["graph_sha256"]:
        raise ValueError("graph_pin")
    graph = json.loads(graph_bytes)
    def bound_entry(selected, evidence):
        if type(selected) is not str or selected.count(":") != 1:
            raise ValueError("entry_binding")
        module, symbol = selected.split(":")
        if not all(part.isidentifier() for part in (module + "." + symbol).split(".")):
            raise ValueError("entry_binding")
        possible = {module.replace(".", "/") + ".py", module.replace(".", "/") + "/__init__.py"}
        if not possible.intersection(seen) or not any(
            row.get("module") == module and row.get("symbol") == symbol for row in evidence
        ):
            raise ValueError("entry_not_pinned")
    bound_entry(m["entry"], [graph["entry"]])
    if m.get("adapter"):
        bound_entry(m["adapter"], graph.get("additional_entrypoints", []))
    return (m, sources) if with_sources else m


def _contract_engine(expected_pins=None):
    """Load only the two maintained public evaluators, under a private package."""
    import types
    root = Path(__file__).resolve().parents[2] / "tools" / "function_extractor"
    names = ("contract_engine", "wire_contract")
    admitted = {name: _read_public(root / (name + ".py"), 1_000_000) for name in names}
    pins = [{"path": name + ".py", "sha256": hashlib.sha256(admitted[name]).hexdigest(),
             "bytes": len(admitted[name])} for name in names]
    if expected_pins is not None and pins != expected_pins:
        raise ValueError("contract_evaluator_pin")
    package = "_route_probe_witness_engine"
    existing = sys.modules.get(package)
    if existing is not None and getattr(existing, "file_pins", None) == pins:
        return sys.modules[package + ".wire_contract"], pins
    module = types.ModuleType(package)
    module.__path__ = []  # No source search path or tools namespace rebinding.
    module.file_pins = pins
    sys.modules[package] = module
    for name in names:
        selected = types.ModuleType(package + "." + name)
        selected.__file__ = str(root / (name + ".py"))
        selected.__package__ = package
        sys.modules[selected.__name__] = selected
        setattr(module, name, selected)
        exec(compile(admitted[name], selected.__file__, "exec"), selected.__dict__)
    return sys.modules[package + ".wire_contract"], pins


def replay_bundle(bundle, fixture, *, timeout=10, expected_fixture_sha256=None,
                  contract_plan=None, runner_sha256=None):
    try:
        if type(fixture) is not dict or not 0 < timeout <= 30:
            return _refused("fixture_or_timeout")
        fixture_bytes = _canonical(fixture)
        sha = hashlib.sha256(fixture_bytes).hexdigest()
        if len(fixture_bytes) > 65536 or expected_fixture_sha256 not in (None, sha):
            return _refused("fixture_pin_or_bound")
    except Exception:
        return _refused("bundle_integrity")
    try:
        assets = _public_assets(fixture)
    except Exception:
        return _refused("public_asset_integrity")
    try:
        manifest = _verify(bundle)
    except Exception:
        return _refused("bundle_integrity")
    try:
        _trace_modules(fixture, manifest)
    except Exception:
        return _refused("trace_selection")
    contract = {}
    if contract_plan is not None:
        try:
            if type(runner_sha256) is not str or not re.fullmatch(r"[a-f0-9]{64}", runner_sha256):
                raise ValueError("contract_runner_pin")
            engine, pins = _contract_engine()
            plan = json.loads(_canonical(contract_plan))
            if engine.validate_contract_observation_plan(plan, manifest)["status"] != "VALID":
                raise ValueError("contract_plan")
            contract = {"contract_plan": plan, "runner_sha256": runner_sha256,
                        "contract_evaluator_pins": pins}
        except Exception:
            return _refused("contract_plan_integrity")
    roots = []
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        root = str(Path(sysconfig.get_paths()[key]).resolve())
        if root not in roots:
            roots.append(root)
    with tempfile.TemporaryDirectory(prefix="route-probe-") as temp:
        request = Path(temp) / "request.json"
        progress_nonce = uuid.uuid4().hex
        request.write_bytes(_canonical({"bundle": str(Path(bundle).resolve()), "fixture": fixture,
                                       "fixture_sha256": sha, "library_roots": roots, "timeout": timeout,
                                       "progress_nonce": progress_nonce, "public_assets": assets, **contract}))
        argv = [sys.executable, "-I", "-S", "-B", str(Path(__file__).resolve()), "--child", str(request)]
        # Drop credential/proxy/environment configuration for the child only.
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC"}
        failure, returncode, stdout, stderr = _bounded_child(argv, env, timeout)
        progress = _read_progress(stderr, progress_nonce)
        if failure:
            value = _refused(failure)
            if failure == "whole_replay_deadline":
                value["status"] = "TIMEOUT"
            value["phase_progress"] = progress
            if any(p["phase"] == "GUARDS_ENFORCED" for p in progress):
                value["sandbox"] = {"audit": True, "seccomp": True}
            value["child_exit_code"] = returncode
            value["fixture_sha256"] = sha
            return value
        try:
            value = json.loads(stdout)
            if value.get("schema") != "route-probe.trace/v1":
                raise ValueError()
        except Exception:
            return _refused("child_protocol")
        value["child_exit_code"] = returncode
        value["fixture_sha256"] = sha
        value["stderr_bytes_suppressed"] = len(stderr)
        value["phase_progress"] = progress
        return value


def _public_assets(fixture):
    rows = fixture.get("public_assets", [])
    if type(rows) is not list or len(rows) > 1:
        raise ValueError("public_asset_schema")
    result = []
    for row in rows:
        if (type(row) is not dict or set(row) != {"name", "sha256"}
                or row["name"] != "timezone:Asia/Vladivostok"
                or type(row["sha256"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"])):
            raise ValueError("public_asset_not_allowlisted")
        path = Path("/usr/share/zoneinfo/Asia/Vladivostok")
        data = _read_public(path, 16384)
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("public_asset_pin")
        result.append({"name": row["name"], "path": str(path), "sha256": row["sha256"], "bytes": len(data)})
    return result


def _trace_modules(fixture, manifest):
    """Recording selection only; it never expands the source import allowlist."""
    rows = fixture.get("trace_modules", [])
    if (type(rows) is not list or len(rows) > 32
            or any(type(name) is not str or not name or len(name) > 180
                   or not all(part.isidentifier() for part in name.split(".")) for name in rows)
            or len(set(rows)) != len(rows)):
        raise ValueError("trace_selection")
    pinned = {row["path"][:-12].replace("/", ".") if row["path"].endswith("/__init__.py")
              else row["path"][:-3].replace("/", ".")
              for row in manifest["files"] if row["path"].endswith(".py")}
    if not set(rows) <= pinned:
        raise ValueError("trace_selection")
    return sorted(rows)


_PROGRESS_PHASES = frozenset({"REQUEST_LOADED", "VERIFY_BEGIN", "VERIFY_END", "GUARDS_ENFORCED",
    "IMPORT_ADAPTER_BEGIN", "BOOTSTRAP_BEGIN", "IMPORT_ENTRY_BEGIN", "PREPARE_FIXTURE_BEGIN",
    "TARGET_BEGIN", "TARGET_END", "HOOK_BEGIN", "RESULT_READY"})


def _read_progress(stderr, nonce):
    """Only trusted closed metadata; never return raw stderr or exception text."""
    rows = []
    for line in stderr.splitlines():
        if not line.startswith(b"FE_PHASE ") or len(line) > 512:
            continue
        try:
            value = json.loads(line[9:])
            if (set(value) == {"nonce", "phase", "monotonic"} and value["nonce"] == nonce
                    and value["phase"] in _PROGRESS_PHASES and type(value["monotonic"]) is float
                    and math.isfinite(value["monotonic"]) and len(rows) < 16):
                rows.append({"phase": value["phase"], "monotonic": value["monotonic"]})
        except (ValueError, TypeError, KeyError):
            pass
    return rows


def _progress(phase, request):
    if phase not in _PROGRESS_PHASES:
        return
    data = {"nonce": request["progress_nonce"], "phase": phase, "monotonic": time.monotonic()}
    os.write(2, b"FE_PHASE " + _canonical(data) + b"\n")


class SandboxDenied(RuntimeError):
    pass


class TraceLimit(RuntimeError):
    pass


class FrozenModules(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Execute the exact verified bytes; never reread a mutable module at import."""
    def __init__(self, source, sources):
        self.source, self.modules = source, {}
        for rel, data in sources.items():
            if not rel.endswith(".py"):
                continue
            package = rel.endswith("/__init__.py")
            name = rel[:-12].replace("/", ".") if package else rel[:-3].replace("/", ".")
            self.modules[name] = (rel, data, package)

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.modules:
            rel, _, package = self.modules[fullname]
            return importlib.util.spec_from_loader(fullname, self, origin=str(self.source / rel), is_package=package)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        rel, data, package = self.modules[module.__name__]
        module.__file__ = str(self.source / rel)
        if package:
            module.__path__ = [str((self.source / rel).parent)]
        exec(compile(data, module.__file__, "exec", dont_inherit=True), module.__dict__)


def _install_seccomp():
    # No subprocess/library search here: the selected Linux host has libseccomp.
    import ctypes as c
    lib = c.CDLL("libseccomp.so.2", use_errno=True)
    libc = c.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [c.c_int, c.c_ulong, c.c_ulong, c.c_ulong, c.c_ulong]
    libc.prctl.restype = c.c_int
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise RuntimeError("no_new_privs")
    class Cmp(c.Structure):
        _fields_ = [("arg", c.c_uint), ("op", c.c_uint), ("a", c.c_uint64), ("b", c.c_uint64)]
    lib.seccomp_init.argtypes = [c.c_uint32]; lib.seccomp_init.restype = c.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [c.c_char_p]; lib.seccomp_syscall_resolve_name.restype = c.c_int
    lib.seccomp_rule_add_array.argtypes = [c.c_void_p, c.c_uint32, c.c_int, c.c_uint, c.POINTER(Cmp)]
    lib.seccomp_load.argtypes = [c.c_void_p]; lib.seccomp_release.argtypes = [c.c_void_p]
    ctx = lib.seccomp_init(0x7FFF0000)
    if not ctx:
        raise RuntimeError("seccomp_init")
    try:
        denied = ("socket socketpair connect bind listen accept accept4 sendto sendmsg sendmmsg recvfrom recvmsg "
                  "execve execveat fork vfork clone clone3 ptrace process_vm_readv process_vm_writev "
                  "unlink unlinkat rename renameat renameat2 mkdir mkdirat rmdir link linkat symlink symlinkat "
                  "truncate ftruncate creat chmod fchmod fchmodat chown fchown lchown mount umount2 "
                  "kill tkill tgkill prctl").split()
        for name in denied:
            nr = lib.seccomp_syscall_resolve_name(name.encode())
            if nr >= 0 and lib.seccomp_rule_add_array(ctx, 0x50000 | 1, nr, 0, None) != 0:
                raise RuntimeError("seccomp_rule")
        for name, arg in (("open", 1), ("openat", 2)):
            nr = lib.seccomp_syscall_resolve_name(name.encode())
            if nr < 0:
                continue
            for bit in (os.O_WRONLY, os.O_RDWR, os.O_CREAT, os.O_TRUNC, os.O_APPEND):
                cmp = Cmp(arg, 7, bit, bit)
                if lib.seccomp_rule_add_array(ctx, 0x50000 | 1, nr, 1, c.byref(cmp)) != 0:
                    raise RuntimeError("seccomp_open_rule")
        nr = lib.seccomp_syscall_resolve_name(b"openat2")
        if nr >= 0:
            lib.seccomp_rule_add_array(ctx, 0x50000 | 1, nr, 0, None)
        if lib.seccomp_load(ctx) != 0:
            raise RuntimeError("seccomp_load")
    finally:
        lib.seccomp_release(ctx)


class _ObservedJSON:
    """Delegate decoding exactly; inspect the returned object without retaining it."""
    def __init__(self, original, context):
        self.original, self.context = original, context

    def __getattr__(self, name):
        return getattr(self.original, name)

    def loads(self, *args, **kwargs):
        value = self.original.loads(*args, **kwargs)
        self.context._contract_response(sys._getframe(1), value)
        return value


class Context:
    def __init__(self, source, files, roots, limit, assets=(), trace_modules=(), *,
                 contract_plan=None, contract_engine=None, contract_manifest=None,
                 fixture_sha256=None, runner_sha256=None):
        self.source, self.files, self.roots = source, files, roots
        self.limit, self.spans, self.module = limit, [], None
        self.correlation_id = uuid.uuid4().hex
        self.in_trace = False
        self.sequence, self.frames, self.stack = 0, {}, []
        self.file_labels = {name: str(Path(name).relative_to(source)) for name in files}
        self.assets = {row["path"] for row in assets}
        self.selected_modules = list(trace_modules)
        self.trace_files = {name for name, rel in self.file_labels.items()
                            if not trace_modules or (rel[:-12].replace("/", ".") if rel.endswith("/__init__.py")
                                                     else rel[:-3].replace("/", ".")) in trace_modules}
        self.trace_complete, self.dropped_events = True, 0
        self.contract_plan, self.contract_engine = contract_plan, contract_engine
        self.contract_manifest = contract_manifest
        self.fixture_sha256, self.runner_sha256 = fixture_sha256, runner_sha256
        self.observations, self.dropped_observations = [], 0
        self.observations_complete = True
        self._contract_native = None
        self._contract_pending, self._contract_sessions, self._contract_restore = {}, set(), []
        self._contract_sequence = 0
        if contract_plan is not None:
            if (contract_engine is None or contract_manifest is None
                    or contract_engine.validate_contract_observation_plan(contract_plan, contract_manifest)["status"] != "VALID"
                    or any(type(v) is not str or not re.fullmatch(r"[a-f0-9]{64}", v)
                           for v in (fixture_sha256, runner_sha256))):
                raise ValueError("contract_context_admission")

    def _contract_incomplete(self):
        self.observations_complete = False
        self.dropped_observations = min(10_000_000, self.dropped_observations + 1)

    def observe_native_transport(self, native):
        """Optional fixture instrumentation; never patch the product callable."""
        if self.contract_plan is None:
            return
        try:
            if self._contract_native is native:
                return
            if (self._contract_native is not None
                    or native.__name__ != "app.ingest.telegram_basic_native_transport"
                    or native.__file__ not in self.files or native.json is not json):
                raise ValueError("contract_native_binding")
            original = native.json
            native.json = _ObservedJSON(original, self)
            self._contract_native = native
            self._contract_restore.append((native, "json", True, original))
        except Exception:
            self._contract_incomplete()

    def observe_http_session(self, session):
        if self.contract_plan is None or id(session) in self._contract_sessions:
            return
        try:
            original = session.post
            owned = "post" in vars(session)
            previous = vars(session).get("post")
            def intercepted_post(*args, **kwargs):
                self._contract_request(sys._getframe(1), args, kwargs)
                return original(*args, **kwargs)
            session.post = intercepted_post
            self._contract_sessions.add(id(session))
            self._contract_restore.append((session, "post", owned, previous))
        except Exception:
            self._contract_incomplete()

    def _contract_binding(self, frame, phase):
        if (self._contract_native is None or frame.f_globals is not self._contract_native.__dict__
                or frame.f_code.co_qualname != "BasicNativeTransport._request_once"
                or frame.f_locals.get("method") != "sendMessage"):
            return None
        path = self.file_labels.get(frame.f_code.co_filename)
        matches = [b for b in self.contract_plan["bindings"] if b["phase"] == phase
                   and b["file"] == path and b["symbol"] == frame.f_code.co_qualname
                   and b["line"] == frame.f_lineno]
        if len(matches) != 1:
            return None
        binding = matches[0]
        return binding, {key: binding[key] for key in ("file", "sha256", "symbol", "line")}

    def _contract_evaluate(self, selected, value, invocation):
        if len(self.observations) >= 128:
            self._contract_incomplete()
            return
        binding, anchor = selected
        result = self.contract_engine.evaluate_contract_observation(self.contract_plan,
            binding_id=binding["binding_id"], value=value, phase=binding["phase"],
            anchor=anchor, invocation_id=invocation)
        if result.get("status") != "EVALUATED":
            self._contract_incomplete()
            return
        # Store only helper-validated redacted metadata, never the transient value.
        self.observations.append(result)
        if len(_canonical(self.contract_observations())) > 262144:
            self.observations.pop()
            self._contract_incomplete()

    def _contract_request(self, frame, args, kwargs):
        try:
            selected = self._contract_binding(frame, "REQUEST")
            if selected is None:
                return
            token = frame.f_locals.get("token")
            if (len(args) != 1 or type(args[0]) is not str or type(token) is not str
                    or args[0] != "https://api.telegram.org/bot" + token + "/sendMessage"
                    or type(kwargs.get("data")) is not bytes or len(kwargs["data"]) > 256 * 1024):
                self._contract_incomplete()
                return
            if self._contract_sequence >= 128:
                self._contract_incomplete()
                return
            self._contract_sequence += 1
            invocation = self._contract_sequence
            self._contract_pending[id(frame)] = invocation
            value = json.loads(kwargs["data"].decode("utf-8"))
            self._contract_evaluate(selected, value, invocation)
        except Exception:
            self._contract_incomplete()

    def _contract_response(self, frame, value):
        try:
            selected = self._contract_binding(frame, "RESPONSE")
            if selected is None:
                return
            invocation = self._contract_pending.pop(id(frame), None)
            if invocation is None:
                if (any(b["direction"] == "input" for b in self.contract_plan["bindings"])
                        or self._contract_sequence >= 128):
                    self._contract_incomplete()
                    return
                self._contract_sequence += 1
                invocation = self._contract_sequence
            self._contract_evaluate(selected, value, invocation)
        except Exception:
            self._contract_incomplete()

    def contract_observations(self):
        value = {"schema": "function-extractor.contract-observations/v1", "version": 1,
                 "plan": self.contract_plan, "fixture_sha256": self.fixture_sha256,
                 "runner_sha256": self.runner_sha256, "observations": list(self.observations),
                 "complete": self.observations_complete, "dropped_observations": self.dropped_observations}
        value["content_digest"] = hashlib.sha256(_canonical(value)).hexdigest()
        return value

    def restore_contract_observers(self):
        for owner, name, owned, previous in reversed(self._contract_restore):
            try:
                if owned:
                    setattr(owner, name, previous)
                else:
                    delattr(owner, name)
            except Exception:
                self._contract_incomplete()
        self._contract_restore.clear()
        self._contract_pending.clear()

    def next_span(self):
        self.sequence += 1
        return self.sequence

    def emit(self, phase, result, evidence="SIMULATED", **fields):
        if len(self.spans) >= self.limit:
            # Instrumentation must never inject an exception into a subject's
            # broad exception handler. Keep the bounded prefix and report the
            # incomplete observation after the original call has completed.
            self.trace_complete = False
            self.dropped_events = min(10_000_000, self.dropped_events + 1)
            return False
        span = {"phase": phase if re.fullmatch(r"[\w.:-]{1,80}", str(phase)) else "UNCLASSIFIED",
                "event": result if re.fullmatch(r"[\w.:-]{1,80}", str(result)) else "UNCLASSIFIED",
                "evidence": evidence if evidence in {"SIMULATED", "REAL_CODE", "GUARD"} else "SIMULATED",
                "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "monotonic": time.monotonic(), "correlation_id": self.correlation_id}
        selected_id = fields.get("span_id")
        span["span_id"] = selected_id if type(selected_id) is int and 1 <= selected_id <= 20000 else self.next_span()
        parent = fields.get("parent_span_id", self.frames[self.stack[-1]][0] if self.stack else None)
        span["parent_span_id"] = parent if type(parent) is int and 1 <= parent <= 20000 else None
        if type(fields.get("duration_seconds")) is float and math.isfinite(fields["duration_seconds"]):
            span["duration_seconds"] = max(0., fields["duration_seconds"])
        shape = fields.get("input_shape")
        if (type(shape) is dict and set(shape) == {"positional_parameters", "keyword_only_parameters", "varargs", "varkw"}
                and all(type(shape[k]) is int and 0 <= shape[k] <= 5000 for k in ("positional_parameters", "keyword_only_parameters"))
                and all(type(shape[k]) is bool for k in ("varargs", "varkw"))):
            span["input_shape"] = dict(shape)
        for key in ("symbol", "file", "line", "exception", "errno", "status_code", "attempts", "effect_started", "count"):
            if key in fields:
                value = fields[key]
                if key in {"line", "errno", "status_code", "attempts", "count"}:
                    if type(value) is int and -1 <= value <= 10_000_000:
                        span[key] = value
                elif key == "effect_started":
                    if type(value) is bool:
                        span[key] = value
                elif key == "exception" and type(value) is dict:
                    safe = {k: v for k, v in value.items() if k in {"class", "family"}
                            and type(v) is str and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", v)}
                    if type(value.get("errno")) is int:
                        safe["errno"] = value["errno"]
                    span[key] = safe
                elif key == "file" and type(value) is str and str(self.source / value) in self.files:
                    span[key] = value
                elif key == "symbol" and type(value) is str and re.fullmatch(r"[A-Za-z_0-9.<>]{1,180}", value):
                    span[key] = value
        self.spans.append(span)
        return True

    def load_module(self, name):
        return importlib.import_module(name)

    def audit(self, event, args):
        denied = event.startswith(("socket.", "subprocess.", "ctypes.")) or event in {
            "os.system", "os.fork", "os.posix_spawn", "os.exec", "os.remove", "os.rename", "os.mkdir",
            "os.rmdir", "os.link", "os.symlink", "os.truncate", "os.chmod", "os.chown", "os.kill"}
        if event == "sqlite3.connect":
            denied = args[0] != ":memory:"
        if event == "open":
            name, mode, flags = args
            if isinstance(name, int):
                denied = name not in (0, 1, 2)
            else:
                path = Path(os.fsdecode(name)).resolve()
                writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                missing_bytecode_probe = (path.is_relative_to(self.source) and path.suffix == ".pyc"
                                          and not path.exists())
                denied = writing or not (str(path) in self.files or str(path) in self.assets or missing_bytecode_probe
                                          or any(path.is_relative_to(r) for r in self.roots))
        if denied:
            self.emit("guard", "DENIED", evidence="GUARD")
            raise SandboxDenied()

    def trace(self, frame, event, arg):
        if event not in {"call", "return", "exception"}:
            return self.trace
        filename = frame.f_code.co_filename
        if filename not in self.trace_files:
            return None
        if not self.trace_complete:
            self.dropped_events = min(10_000_000, self.dropped_events + 1)
            self.frames.clear(); self.stack.clear()
            return None
        if event == "call":
            # Only calls/returns/exceptions are part of the contract. Avoid a
            # filesystem Path construction on every unrelated Python event.
            frame.f_trace_lines = False
        key = id(frame)
        if event == "call":
            parent = self.frames[self.stack[-1]][0] if self.stack else None
            self.frames[key] = (self.next_span(), parent, time.monotonic())
            self.stack.append(key)
        selected = self.frames.get(key)
        identity, parent, started = selected if selected else (self.next_span(), None, time.monotonic())
        fields = {"symbol": frame.f_code.co_qualname, "span_id": identity, "parent_span_id": parent,
                  "file": self.file_labels[filename], "line": frame.f_lineno}
        if event == "call":
            fields["input_shape"] = {"positional_parameters": frame.f_code.co_argcount,
                                     "keyword_only_parameters": frame.f_code.co_kwonlyargcount,
                                     "varargs": bool(frame.f_code.co_flags & 4),
                                     "varkw": bool(frame.f_code.co_flags & 8)}
        if event == "return":
            fields["duration_seconds"] = time.monotonic() - started
        if event == "exception":
            fields["exception"] = _exception(arg[1])
        recorded = self.emit("call", event, evidence="REAL_CODE", **fields)
        if not recorded:
            self.frames.clear(); self.stack.clear()
            return None
        if event == "return":
            self.frames.pop(key, None)
            if key in self.stack:
                self.stack.remove(key)
        return self.trace


def _exception(exc):
    name = type(exc).__name__
    name = name if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", name) else "UNKNOWN"
    value = {"class": name, "family": "DENIED" if isinstance(exc, SandboxDenied) else "EXCEPTION"}
    if isinstance(exc, OSError) and type(exc.errno) is int:
        value["errno"] = exc.errno
    return value


def _summary(value):
    if value is None or type(value) in (bool, int, float):
        return {"type": type(value).__name__}
    data = value if type(value) is dict else getattr(value, "__dict__", {})
    result = {"type": type(value).__name__}
    if type(data) is dict:
        for key in ("state", "category", "error_category"):
            v = data.get(key)
            if type(v) is str and v in {"sent", "unknown", "failed", "retry_wait", "queued", "transport_or_receipt_unknown", "telegram_rejected"}:
                result[key] = v
        for key in ("ok", "effect_started", "retry_after"):
            if type(data.get(key)) in (bool, int):
                result[key] = data[key]
    return result


def _child(request_path):
    request = json.loads(Path(request_path).read_bytes())
    _progress("REQUEST_LOADED", request)
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (max(1, math.ceil(request["timeout"])),) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    bundle = Path(request["bundle"]).resolve()
    _progress("VERIFY_BEGIN", request)
    m, frozen_sources = _verify(bundle, with_sources=True)
    _progress("VERIFY_END", request)
    fixture = request["fixture"]
    if hashlib.sha256(_canonical(fixture)).hexdigest() != request["fixture_sha256"]:
        return _refused("fixture_pin")
    contract = {}
    if "contract_plan" in request:
        try:
            engine, _ = _contract_engine(request["contract_evaluator_pins"])
            if engine.validate_contract_observation_plan(request["contract_plan"], m)["status"] != "VALID":
                raise ValueError("contract_plan")
            contract = {"contract_plan": request["contract_plan"], "contract_engine": engine,
                        "contract_manifest": m, "fixture_sha256": request["fixture_sha256"],
                        "runner_sha256": request["runner_sha256"]}
        except Exception:
            return _refused("contract_plan_integrity")
    assets = _public_assets(fixture)
    if assets != request.get("public_assets", []):
        return _refused("public_asset_readback")
    roots = [Path(p).resolve() for p in request["library_roots"]]
    for p in roots:
        if str(p) not in sys.path:
            sys.path.append(str(p))
    source = bundle / "source"
    files = {str((source / row["path"]).absolute()) for row in m["files"]}
    limit = fixture.get("max_trace_events", 3000)
    if type(limit) is not int or not 1 <= limit <= 5000:
        return _refused("trace_bound")
    selected_modules = _trace_modules(fixture, m)
    context = Context(source, files, roots, limit, assets, selected_modules, **contract)
    sys.dont_write_bytecode = True
    # Load the filter before the audit hook denies ctypes access. No subject
    # module or fixture is imported/executed before both protections are active.
    try:
        _install_seccomp()
    except Exception:
        return _refused("seccomp_unavailable")
    sys.addaudithook(context.audit)
    sys.meta_path.insert(0, FrozenModules(source, frozen_sources))
    sys.path.insert(0, str(source))
    _progress("GUARDS_ENFORCED", request)
    original_stdout, original_stderr = sys.stdout, sys.stderr
    class Sink(io.TextIOBase):
        count = 0
        truncated = False
        def write(self, data):
            self.count = min(10_000_000, self.count + len(data))
            self.truncated = self.count > 65536
            return len(data)
    sink = Sink()
    sys.stdout = sys.stderr = sink
    result = {"schema": "route-probe.trace/v1", "status": "REFUSED", "correlation_id": context.correlation_id,
              "sandbox": {"audit": True, "seccomp": True, "memory_mb": 256, "max_fds": 128,
                          "cpu_seconds": max(1, math.ceil(request["timeout"]))}, "source_entry": m["entry"]}
    if assets:
        result["public_assets"] = [{k: row[k] for k in ("name", "sha256", "bytes")} for row in assets]
    try:
        sys.settrace(context.trace)
        adapter = None
        if m.get("adapter"):
            _progress("IMPORT_ADAPTER_BEGIN", request)
            module, function = m["adapter"].split(":", 1)
            adapter = context.load_module(module)
            bootstrap = getattr(adapter, "bootstrap", None)
            _progress("BOOTSTRAP_BEGIN", request)
            stubs = bootstrap(fixture, context) if bootstrap else {}
            if set(stubs) != set(m.get("opaque_modules", [])):
                raise SandboxDenied()
            for name, module_value in stubs.items():
                sys.modules[name] = module_value
        module, symbol = m["entry"].split(":", 1)
        _progress("IMPORT_ENTRY_BEGIN", request)
        context.module = context.load_module(module)
        target = context.module
        for part in symbol.split("."):
            target = getattr(target, part)
        if (not inspect.isfunction(target) or target.__code__.co_filename not in files
                or target.__code__.co_qualname != symbol):
            raise SandboxDenied()
        if inspect.iscoroutinefunction(target) or inspect.isgeneratorfunction(target):
            result.update(status="REFUSED", reason="async_or_generator_runner_not_supported")
            return result
        _progress("PREPARE_FIXTURE_BEGIN", request)
        args = adapter.prepare(target, fixture, context) if adapter else {"args": fixture.get("args", []), "kwargs": fixture.get("kwargs", {})}
        if set(args) != {"args", "kwargs"} or type(args["args"]) not in (tuple, list) or type(args["kwargs"]) is not dict:
            raise SandboxDenied()
        context.emit("entry", "ENTER", evidence="REAL_CODE")
        value = None; failure = None
        _progress("TARGET_BEGIN", request)
        try:
            value = target(*args["args"], **args["kwargs"])
        except BaseException as exc:
            failure = exc
        _progress("TARGET_END", request)
        result["target_outcome"] = ({"status": "RETURNED", "result_summary": _summary(value)} if failure is None
                                    else {"status": "RAISED", "exception": _exception(failure)})
        if failure is None and "expected_result" in fixture:
            result["result_matches_expected"] = value == fixture["expected_result"]
        if adapter and callable(getattr(adapter, "observe_outcome", None)):
            _progress("HOOK_BEGIN", request)
            try:
                adapter.observe_outcome(value, failure, fixture, context)
            except TraceLimit:
                raise
            except BaseException as exc:
                result["outcome_hook_error"] = {**_exception(exc), "evidence": "SIMULATED"}
        if failure is not None:
            raise failure
        # The diagnostic posthook may expire/rollback an ORM fixture. Keep the
        # already observed target return separate from that later simulation.
        result.update(status="RETURNED", result_summary=result["target_outcome"]["result_summary"])
    except SandboxDenied as exc:
        result.update(status="DENIED", exception=_exception(exc))
    except TraceLimit:
        result.update(status="TRACE_LIMIT", reason="trace_or_output_cap")
    except BaseException as exc:
        result.update(status="RAISED", exception=_exception(exc))
    finally:
        sys.settrace(None)
        context.restore_contract_observers()
        sys.stdout, sys.stderr = original_stdout, original_stderr
        result["spans"] = context.spans
        if contract:
            result["contract_observations"] = context.contract_observations()
    result["trace_recording"] = {"complete": context.trace_complete,
                                 "recorded_events": len(context.spans),
                                 "dropped_events": context.dropped_events,
                                 "selected_modules": context.selected_modules}
    if (not context.trace_complete or sink.truncated) and result["status"] in {"RETURNED", "RAISED"}:
        result.update(status="TRACE_LIMIT", reason="trace_or_output_cap")
    result["spans"] = context.spans
    result["suppressed_text_characters"] = sink.count
    _progress("RESULT_READY", request)
    return result


if __name__ == "__main__":
    try:
        value = _child(sys.argv[2]) if len(sys.argv) == 3 and sys.argv[1] == "--child" else _refused("child_arguments")
    except BaseException:
        value = _refused("child_bootstrap")
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
