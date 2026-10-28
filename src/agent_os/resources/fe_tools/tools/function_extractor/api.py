"""Versioned offline API over the maintained extractor and guarded replay engine."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from .adapters.policy import classify_boundary

_SCHEMA = "function-extractor.result/v1"
_VOLATILE = frozenset({"utc", "timestamp", "timestamp_utc", "monotonic", "monotonic_ns",
    "correlation_id", "request_id", "nonce", "uuid", "elapsed_seconds", "elapsed_ms",
    "duration", "duration_ms", "duration_seconds", "timing", "timings"})
_UUID = re.compile(r"(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})\Z")
_CONTRACT_KEYS = {"schema", "version", "expected_status", "result_summary", "phase_events", "guards"}


def _engine(name):
    from .runner.loader import load_engine
    return load_engine(name)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _json(value, *, cap=2_000_000, item_budget=50_000):
    remaining = [item_budget]
    def check(item, depth=0):
        remaining[0] -= 1
        if remaining[0] < 0 or depth > 40:
            raise ValueError("json_bound")
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                check(child, depth + 1)
            return
        if type(item) is dict and all(type(k) is str and len(k) <= 256 for k in item):
            for child in item.values():
                check(child, depth + 1)
            return
        raise ValueError("json_type")
    check(value)
    encoded = _canonical(value)
    if len(encoded) > cap:
        raise ValueError("json_bound")
    return json.loads(encoded)


def _result(operation, status, data=None, errors=()):
    return {"schema": _SCHEMA, "version": 1, "operation": operation,
            "status": status, "data": {} if data is None else data, "errors": list(errors)}


def _call(operation, function):
    try:
        return function()
    except (ImportError, ModuleNotFoundError):
        return _result(operation, "UNKNOWN", errors=("ENGINE_UNAVAILABLE",))
    except TimeoutError:
        return _result(operation, "UNKNOWN", errors=("DEADLINE_EXCEEDED",))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, OverflowError, RecursionError):
        return _result(operation, "REFUSED", errors=("INVALID_OR_UNSAFE_INPUT",))
    except Exception:
        return _result(operation, "UNKNOWN", errors=("ENGINE_FAILURE",))


def _graph(value):
    value = _json(value, cap=8_000_000, item_budget=250_000)
    if value.get("schema") == _SCHEMA:
        value = value["data"]["graph"]
    if (type(value) is not dict or value.get("schema") != "route-probe.graph/v1"
            or type(value.get("entry")) is not dict
            or any(type(value.get(k)) is not list for k in ("files", "nodes", "edges", "branches", "unresolved_caps"))):
        raise ValueError("graph_schema")
    if set(value) - {"schema", "entry", "files", "nodes", "edges", "branches", "unresolved", "unresolved_caps", "complete", "limits", "semantics", "opaque_modules", "additional_entrypoints"}:
        raise ValueError("graph_fields")
    node_keys = {"id", "module", "symbol", "kind", "file", "line", "end_line"}
    edge_keys = {"source", "target", "file", "line", "expression", "resolution", "reason", "kind"}
    groups = [(value["files"], {"path", "sha256", "bytes"}),
              (value["nodes"] + [value["entry"]] + value.get("additional_entrypoints", []), node_keys),
              (value["edges"] + value.get("unresolved", []), edge_keys),
              (value["branches"], {"source", "file", "line", "kind", "expression", "execution"}),
              (value["unresolved_caps"], {"kind", "source", "line", "target"})]
    for rows, allowed in groups:
        if type(rows) is not list or any(type(row) is not dict or set(row) != allowed for row in rows):
            raise ValueError("graph_row_fields")
    for item in value["files"]:
        path = Path(item["path"])
        if (path.is_absolute() or ".." in path.parts or path.suffix != ".py"
                or type(item["bytes"]) is not int or not 0 <= item["bytes"] <= 2_097_152
                or type(item["sha256"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])):
            raise ValueError("graph_file")
    if type(value.get("complete")) is not bool:
        raise ValueError("graph_complete")
    return value


def _trace(value):
    value = _json(value, item_budget=150_000)
    if value.get("schema") == _SCHEMA:
        value = value["data"]["trace"]
    if type(value) is not dict or value.get("schema") != "route-probe.trace/v1" or type(value.get("status")) is not str:
        raise ValueError("trace_schema")
    if type(value.get("spans", [])) is not list or len(value.get("spans", [])) > 10000:
        raise ValueError("trace_bound")
    allowed = {"schema", "status", "correlation_id", "sandbox", "source_entry", "reason", "result_summary",
        "exception", "spans", "suppressed_text_characters", "child_exit_code", "fixture_sha256",
        "stderr_bytes_suppressed", "result_matches_expected", "target_outcome", "outcome_hook_error",
        "container", "container_effective", "phase_progress", "public_assets", "trace_recording", "contract_observations"} | _VOLATILE
    if set(value) - allowed:
        raise ValueError("trace_fields")
    if 'contract_observations' in value:
        from .wire_contract import validate_contract_observations
        observed = value['contract_observations']
        if type(observed) is not dict:
            raise ValueError('trace_contract_observations')
        admitted = validate_contract_observations(observed, observed.get('plan'), manifest=None,
            fixture_sha256=value.get('fixture_sha256'), runner_sha256=observed.get('runner_sha256'), structural_only=True)
        if admitted.get('status') != 'VALID':
            raise ValueError('trace_contract_observations')
    if "trace_recording" in value:
        recording = value["trace_recording"]
        if (type(recording) is not dict or set(recording) != {"complete", "recorded_events", "dropped_events", "selected_modules"}
                or type(recording["complete"]) is not bool
                or type(recording["recorded_events"]) is not int or not 0 <= recording["recorded_events"] <= 5000
                or type(recording["dropped_events"]) is not int or not 0 <= recording["dropped_events"] <= 10_000_000):
            raise ValueError("trace_recording_fields")
        modules = recording["selected_modules"]
        if (type(modules) is not list or len(modules) > 32
                or any(type(name) is not str or not 1 <= len(name) <= 180
                       or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*", name)
                       for name in modules) or modules != sorted(set(modules))):
            raise ValueError("trace_recording_modules")
    if "public_assets" in value:
        assets = value["public_assets"]
        if (type(assets) is not list or len(assets) > 1
                or any(type(row) is not dict or set(row) != {"name", "sha256", "bytes"}
                       or row["name"] != "timezone:Asia/Vladivostok"
                       or type(row["sha256"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"])
                       or type(row["bytes"]) is not int or not 0 <= row["bytes"] <= 16384
                       for row in assets)):
            raise ValueError("trace_public_assets")
    phases = {"REQUEST_LOADED", "VERIFY_BEGIN", "VERIFY_END", "GUARDS_ENFORCED", "IMPORT_ADAPTER_BEGIN",
              "BOOTSTRAP_BEGIN", "IMPORT_ENTRY_BEGIN", "PREPARE_FIXTURE_BEGIN", "TARGET_BEGIN", "TARGET_END",
              "HOOK_BEGIN", "RESULT_READY"}
    if "phase_progress" in value:
        progress = value["phase_progress"]
        if (type(progress) is not list or len(progress) > 16
                or any(type(row) is not dict or set(row) != {"phase", "monotonic"}
                       or type(row["phase"]) is not str or row["phase"] not in phases
                       or type(row["monotonic"]) is not float or not math.isfinite(row["monotonic"])
                       for row in progress)):
            raise ValueError("trace_phase_progress")
    span_keys = {"phase", "event", "evidence", "symbol", "file", "line", "exception", "errno", "status_code",
                 "attempts", "effect_started", "count", "span_id", "parent_span_id", "input_shape"} | _VOLATILE
    for span in value.get("spans", []):
        if type(span) is not dict or not {"phase", "event", "evidence"} <= set(span) or set(span) - span_keys:
            raise ValueError("trace_span_fields")
        for key in ("phase", "event", "symbol"):
            if key in span and (type(span[key]) is not str or not re.fullmatch(r"[A-Za-z_0-9.<>:-]{1,180}", span[key])):
                raise ValueError("trace_symbol")
        if span.get("evidence", "SIMULATED") not in {"SIMULATED", "REAL_CODE", "GUARD"}:
            raise ValueError("trace_evidence")
        if any(k in span and (type(span[k]) is not int or not -1 <= span[k] <= 10_000_000) for k in ("line", "errno", "status_code", "attempts", "count")):
            raise ValueError("trace_scalar_type")
        if "effect_started" in span and type(span["effect_started"]) is not bool:
            raise ValueError("trace_effect_type")
        if ("span_id" in span and (type(span["span_id"]) is not int or not 1 <= span["span_id"] <= 20000)
                or "parent_span_id" in span and span["parent_span_id"] is not None
                and (type(span["parent_span_id"]) is not int or not 1 <= span["parent_span_id"] <= 20000)):
            raise ValueError("trace_span_identity")
        if "duration_seconds" in span and (type(span["duration_seconds"]) not in (int, float)
                or not math.isfinite(span["duration_seconds"]) or span["duration_seconds"] < 0):
            raise ValueError("trace_span_duration")
        if "input_shape" in span:
            shape = span["input_shape"]
            if (type(shape) is not dict or set(shape) != {"positional_parameters", "keyword_only_parameters", "varargs", "varkw"}
                    or any(type(shape[k]) is not int or not 0 <= shape[k] <= 5000
                           for k in ("positional_parameters", "keyword_only_parameters"))
                    or any(type(shape[k]) is not bool for k in ("varargs", "varkw"))):
                raise ValueError("trace_input_shape")
        if "file" in span and (type(span["file"]) is not str or len(span["file"]) > 512 or Path(span["file"]).is_absolute() or ".." in Path(span["file"]).parts):
            raise ValueError("trace_file")
    target_outcome = value.get("target_outcome")
    if target_outcome is not None and (type(target_outcome) is not dict
            or set(target_outcome) - {"status", "result_summary", "exception"}
            or target_outcome.get("status") not in {"RETURNED", "RAISED"}):
        raise ValueError("target_outcome")
    if target_outcome is not None and set(target_outcome) != ({"status", "result_summary"} if target_outcome["status"] == "RETURNED" else {"status", "exception"}):
        raise ValueError("target_outcome_shape")
    hook = value.get("outcome_hook_error")
    if hook is not None and (type(hook) is not dict or hook.get("evidence") != "SIMULATED"
                            or set(hook) - {"class", "family", "errno", "evidence"}):
        raise ValueError("outcome_hook_error")
    exceptions = [value.get("exception"), None if target_outcome is None else target_outcome.get("exception"),
                  None if hook is None else {k: v for k, v in hook.items() if k != "evidence"}]
    for exception in exceptions + [s.get("exception") for s in value.get("spans", [])]:
        if exception is not None and (type(exception) is not dict or not {"class", "family"} <= set(exception) or set(exception) - {"class", "family", "errno"}
                or ("errno" in exception and type(exception["errno"]) is not int)
                or any(k in exception and (type(exception[k]) is not str or not re.fullmatch(r"[A-Za-z_0-9]{1,64}", exception[k])) for k in ("class", "family"))):
            raise ValueError("exception_fields")
    guards = value.get("sandbox", {})
    if type(guards) is not dict or set(guards) - {"audit", "seccomp", "memory_mb", "max_fds", "cpu_seconds"}:
        raise ValueError("guard_fields")
    if any(k in guards and type(guards[k]) is not bool for k in ("audit", "seccomp")) or any(k in guards and (type(guards[k]) is not int or not 1 <= guards[k] <= 4096) for k in ("memory_mb", "max_fds", "cpu_seconds")):
        raise ValueError("guard_types")
    summaries = [value.get("result_summary", {})] + ([] if target_outcome is None else [target_outcome.get("result_summary", {})])
    for summary in summaries:
        if type(summary) is not dict or set(summary) - {"type", "state", "category", "error_category", "ok", "effect_started", "retry_after"}:
            raise ValueError("summary_fields")
    _container_evidence(value)
    return value


def _container_evidence(trace):
    container = trace.get("container")
    if container is not None:
        keys = {"image_id", "name", "network", "read_only", "user", "cap_drop", "no_new_privileges",
                "memory_mb", "pids_limit", "elapsed_seconds", "cleanup", "client_exit_code",
                "stderr_bytes_suppressed", "capsule_sha256", "authority"}
        if type(container) is not dict or set(container) != keys:
            raise ValueError("container_fields")
        if (type(container["image_id"]) is not str or not re.fullmatch(r"sha256:[a-f0-9]{64}", container["image_id"])
                or type(container["name"]) is not str or not re.fullmatch(r"fe-replay-[a-f0-9]{32}", container["name"])
                or container["network"] != "none" or container["user"] != "65534:65534"
                or container["cap_drop"] != ["ALL"] or container["read_only"] is not True
                or container["no_new_privileges"] is not True
                or type(container["memory_mb"]) is not int or container["memory_mb"] != 512
                or type(container["pids_limit"]) is not int or container["pids_limit"] != 24
                or type(container["elapsed_seconds"]) not in (int, float) or not 0 <= container["elapsed_seconds"] <= 3600
                or type(container["capsule_sha256"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", container["capsule_sha256"])
                or type(container["stderr_bytes_suppressed"]) is not int or not 0 <= container["stderr_bytes_suppressed"] <= 2_000_000):
            raise ValueError("container_values")
        cleanup = {"AUTO_REMOVE_ON_EXIT", "UNKNOWN_CREATION_NO_CID", "UNKNOWN_CID", "NOT_FOUND_AFTER_OWN_CLIENT_EXIT",
                   "UNKNOWN_INSPECT", "REFUSED_NOT_EXACT_OWNED", "OWNED_REMOVED", "UNKNOWN_REMOVE"}
        if container["cleanup"] not in cleanup or (container["client_exit_code"] is not None and
                (type(container["client_exit_code"]) is not int or not -255 <= container["client_exit_code"] <= 255)):
            raise ValueError("container_lifecycle")
        authority = container["authority"]
        if type(authority) is not dict or type(authority.get("required")) is not bool:
            raise ValueError("container_authority")
        if authority["required"]:
            if (set(authority) != {"required", "window_id", "actor_session", "target_scope"}
                    or type(authority["window_id"]) is not str or not re.fullmatch(r"[a-f0-9]{32}", authority["window_id"])
                    or type(authority["actor_session"]) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", authority["actor_session"])
                    or authority["target_scope"] != "function-extractor:synthetic:" + container["image_id"]):
                raise ValueError("container_authority_identity")
        elif set(authority) != {"required", "reason"} or authority["reason"] != "canonical_ru_route_not_installed":
            raise ValueError("container_authority_reason")
    effective = trace.get("container_effective")
    if effective is not None:
        keys = {"uid", "gid", "cap_eff", "no_new_privs", "seccomp", "interfaces", "root_readonly"}
        if (type(effective) is not dict or set(effective) != keys
                or any(type(effective[k]) is not int or not 0 <= effective[k] <= 2**32-1 for k in ("uid", "gid"))
                or type(effective["cap_eff"]) is not str or not re.fullmatch(r"[A-Fa-f0-9]{1,32}", effective["cap_eff"])
                or type(effective["no_new_privs"]) is not int or effective["no_new_privs"] not in {0, 1}
                or type(effective["seccomp"]) is not int or effective["seccomp"] not in {0, 1, 2}
                or type(effective["root_readonly"]) is not bool or type(effective["interfaces"]) is not list
                or len(effective["interfaces"]) > 64 or any(type(v) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", v) for v in effective["interfaces"])):
            raise ValueError("container_effective_values")


def _normalize(value, path=()):
    if type(value) is dict:
        return {k: "<owned_container>" if path == ("container",) and k == "name" else _normalize(v, path + (k,))
                for k, v in sorted(value.items()) if k not in _VOLATILE
                # This top-level count includes variable-width progress clock
                # formatting; it is not a route result or provider receipt.
                and not (path == () and k == "stderr_bytes_suppressed")}
    if type(value) is list:
        return [_normalize(v, path) for v in value]
    if type(value) is str and _UUID.fullmatch(value):
        return "<uuid>"
    return value


def _directory_pins(root, graph):
    """Pin lookup directories too: adding a previously absent module invalidates cache."""
    engine = _engine("route_probe_graph")
    relative = {"."}
    for item in graph["files"]:
        path = Path(item["path"])
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("cache_path")
        relative.update(p.as_posix() for p in path.parents)
    for edge in graph["edges"]:
        target = edge.get("target")
        if type(target) is str:
            parts = target.replace(":", ".").split(".")
            if all(part.isidentifier() for part in parts):
                for length in range(1, len(parts) + 1):
                    candidate = Path(*parts[:length])
                    if (root / candidate).is_dir():
                        relative.add(candidate.as_posix())
    if len(relative) > 4096:
        raise ValueError("cache_directory_bound")
    result = []
    for name in sorted(relative):
        path = engine._safe_path(root / name)
        info = path.stat(follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("cache_directory")
        result.append({"path": name, "dev": info.st_dev, "ino": info.st_ino,
                       "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns})
    return result


def _cache_valid(root, graph, cache, options):
    descriptor = cache.get("cache")
    if (set(cache) != {"graph", "cache"} or type(descriptor) is not dict
            or set(descriptor) != {"schema", "version", "options", "directories", "graph_sha256"}
            or descriptor.get("schema") != "function-extractor.cache/v1" or type(descriptor.get("version")) is not int
            or descriptor["version"] != 1 or descriptor.get("options") != options or graph["unresolved_caps"]
            or descriptor["graph_sha256"] != hashlib.sha256(_canonical(graph)).hexdigest()):
        return False
    engine = _engine("route_probe_graph")
    for item in graph["files"]:
        path = Path(item["path"])
        if path.is_absolute() or ".." in path.parts or path.suffix != ".py":
            return False
        fd = engine._open_source(engine._safe_path(root / path))
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                return False
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(2_097_153)
            if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                return False
        finally:
            os.close(fd)
    return descriptor.get("directories") == _directory_pins(root, graph)


def resolve_entry(source_root: Path, entry: str) -> dict:
    def run():
        graph = _engine("route_probe_graph").extract_route(Path(source_root), entry)
        source = next(item for item in graph["files"] if item["path"] == graph["entry"]["file"])
        return _result("resolve_entry", "RESOLVED", {"entry": graph["entry"], "source": source})
    return _call("resolve_entry", run)


def extract_route(source_root: Path, entry: str, *, max_files=80, max_nodes=1200, max_depth=8,
                  opaque_modules=(), cache=None) -> dict:
    def run():
        root = Path(source_root).absolute()
        graph_engine = _engine("route_probe_graph")
        if type(entry) is not str or not graph_engine._ENTRY.fullmatch(entry):
            raise ValueError("entry_invalid")
        for value, ceiling in ((max_files, 1000), (max_nodes, 20000), (max_depth, 64)):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("graph_limit")
        if type(opaque_modules) not in (list, tuple) or any(type(v) is not str for v in opaque_modules):
            raise ValueError("opaque_modules")
        options = {"entry": entry, "max_files": max_files, "max_nodes": max_nodes,
                   "max_depth": max_depth, "opaque_modules": sorted(set(opaque_modules))}
        if cache is not None:
            prior = _json(cache)
            prior = prior["data"] if prior.get("schema") == _SCHEMA else prior
            graph = _graph(prior["graph"])
            if _cache_valid(root, graph, prior, options):
                return _result("extract_route", "CACHED", prior)
        graph = graph_engine.extract_route(root, entry, max_files=max_files,
            max_nodes=max_nodes, max_depth=max_depth, opaque_modules=opaque_modules)
        descriptor = {"schema": "function-extractor.cache/v1", "version": 1,
                      "options": options, "directories": _directory_pins(root, graph),
                      "graph_sha256": hashlib.sha256(_canonical(graph)).hexdigest()}
        return _result("extract_route", "UNRESOLVED" if graph["unresolved_caps"] else "EXTRACTED",
                       {"graph": graph, "cache": descriptor}, ("GRAPH_CAP",) if graph["unresolved_caps"] else ())
    return _call("extract_route", run)


def freeze_source(source_root: Path, entry: str, output: Path, *, adapter=None, include_modules=(),
                  opaque_modules=(), include_entries=(), capture_mode="STRICT") -> dict:
    def run():
        if type(capture_mode) is not str or capture_mode not in {"STRICT", "PARTIAL_STATIC"}:
            raise ValueError("capture_mode")
        manifest = _engine("route_probe").freeze_bundle(Path(source_root), entry, Path(output),
            adapter=adapter, include_modules=include_modules, opaque_modules=opaque_modules, include_entries=include_entries,
            capture_mode=capture_mode)
        return _result("freeze_source", "FROZEN" if capture_mode == "STRICT" else "FROZEN_PARTIAL_STATIC",
                       {"bundle": str(Path(output).absolute()), "manifest": manifest})
    return _call("freeze_source", run)


def discover_boundaries(graph: dict) -> dict:
    def run():
        selected = _graph(graph)
        values = [classify_boundary(e) for e in selected["edges"] if e.get("resolution") in {"external", "dynamic"}]
        unique = {value["id"]: value for value in values}
        return _result("discover_boundaries", "PLANNED", {"schema": "function-extractor.boundaries/v1", "version": 1,
            "boundaries": [unique[k] for k in sorted(unique)], "executed": False, "unresolved_caps": selected["unresolved_caps"]})
    return _call("discover_boundaries", run)


def _fixture(spec):
    spec = _json(spec, cap=65536)
    if type(spec) is not dict:
        raise ValueError("fixture_type")
    if "schema" in spec:
        if set(spec) != {"schema", "version", "payload"} or spec["schema"] != "function-extractor.fixture/v1" or type(spec["version"]) is not int or spec["version"] != 1:
            raise ValueError("fixture_schema")
        spec = spec["payload"]
    if type(spec) is not dict or ("args" in spec and type(spec["args"]) is not list) or ("kwargs" in spec and type(spec["kwargs"]) is not dict):
        raise ValueError("fixture_shape")
    return spec


def compile_fixture(spec: dict, *, graph=None) -> dict:
    def run():
        payload = _fixture(spec)
        if graph is not None and _graph(graph)["unresolved_caps"]:
            return _result("compile_fixture", "UNRESOLVED", errors=("GRAPH_CAP",))
        compiled = {"schema": "function-extractor.fixture/v1", "version": 1, "payload": payload}
        return _result("compile_fixture", "COMPILED", {"fixture": compiled, "payload_sha256": hashlib.sha256(_canonical(payload)).hexdigest()})
    return _call("compile_fixture", run)


def _timeout(timeout):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError("timeout_bound")


def build_sandbox(bundle: Path, *, timeout=10) -> dict:
    def run():
        _timeout(timeout)
        manifest = _engine("route_probe_replay")._verify(Path(bundle))
        if type(manifest) is tuple:
            manifest = manifest[0]
        return _result("build_sandbox", "PLANNED", {"schema": "function-extractor.sandbox/v1", "version": 1,
            "bundle": str(Path(bundle).absolute()), "entry": manifest["entry"], "timeout_seconds": timeout,
            "requirements": {"audit": True, "seccomp": True, "network": "DENY", "credentials": "NONE"},
            "enforcement_proven": False, "container_proven": False})
    return _call("build_sandbox", run)


def execute_route(bundle: Path, fixture: dict, *, timeout=10) -> dict:
    def run():
        _timeout(timeout)
        payload = _fixture(fixture["data"]["fixture"] if fixture.get("schema") == _SCHEMA else fixture)
        trace = _engine("route_probe_replay").replay_bundle(Path(bundle), payload, timeout=timeout)
        return _result("execute_route", "EXECUTED" if trace.get("status") in {"RETURNED", "RAISED", "DENIED"} else "UNKNOWN",
                       {"trace": _trace(trace)}, () if trace.get("status") in {"RETURNED", "RAISED", "DENIED"} else ("REPLAY_NOT_COMPLETED",))
    return _call("execute_route", run)


def inject_fault(fixture: dict, fault: dict) -> dict:
    def run():
        payload = _fixture(fixture["data"]["fixture"] if fixture.get("schema") == _SCHEMA else fixture)
        selected = _json(fault, cap=4096)
        if type(selected) is not dict or set(selected) != {"kind", "adapter"} or type(selected["kind"]) is not str:
            raise ValueError("fault_schema")
        cases = {"read_timeout": "timeout", "connect": "connect", "proxy": "proxy", "tls": "tls",
                 "invalid_json": "malformed_json", "provider_400": "telegram400",
                 "bridge_failure": "bridge_only_failure", "db_guard": "db_exception", "db_commit": "db_commit_exception"}
        if selected["adapter"] != "tools.route_probe_avl:prepare" or selected["kind"] not in cases:
            return _result("inject_fault", "UNRESOLVED", {"applied": False}, ("UNSUPPORTED_FAULT_ADAPTER",))
        payload["case"] = cases[selected["kind"]]
        return _result("inject_fault", "PROPOSED", {"applied": False, "fixture": {"schema": "function-extractor.fixture/v1",
            "version": 1, "payload": payload}, "evidence": "SIMULATED_ON_EXECUTION_ONLY"})
    return _call("inject_fault", run)


def _contract(contract):
    contract = _json(contract, cap=65536)
    if (type(contract) is not dict or not {"schema", "version"} <= set(contract)
            or set(contract) - _CONTRACT_KEYS or contract["schema"] != "function-extractor.contract/v1"
            or type(contract["version"]) is not int or contract["version"] != 1):
        raise ValueError("contract_schema")
    if "expected_status" in contract and contract["expected_status"] not in {"RETURNED", "RAISED", "DENIED", "REFUSED", "TIMEOUT", "TRACE_LIMIT"}:
        raise ValueError("contract_status")
    if any(key in contract and type(contract[key]) is not dict for key in ("result_summary", "guards")):
        raise ValueError("contract_mapping")
    if "guards" in contract and (set(contract["guards"]) - {"audit", "seccomp"} or any(type(v) is not bool for v in contract["guards"].values())):
        raise ValueError("contract_guards")
    if "phase_events" in contract:
        if type(contract["phase_events"]) is not list or any(type(v) is not dict or set(v) != {"phase", "event"} or any(type(s) is not str for s in v.values()) for v in contract["phase_events"]):
            raise ValueError("contract_events")
    return contract


def compare_contract(trace: dict, contract: dict) -> dict:
    def run():
        selected, expected = _normalize(_trace(trace)), _contract(contract)
        mismatch = []
        if "expected_status" in expected and selected["status"] != expected["expected_status"]:
            mismatch.append("STATUS")
        for key, actual in (("result_summary", selected.get("result_summary", {})), ("guards", selected.get("sandbox", {}))):
            if key in expected and any(k not in actual or _canonical(actual[k]) != _canonical(v) for k, v in expected[key].items()):
                mismatch.append(key.upper())
        if "phase_events" in expected:
            events = [{"phase": s.get("phase"), "event": s.get("event")} for s in selected.get("spans", [])]
            cursor = iter(events)
            if not all(any(item == want for item in cursor) for want in expected["phase_events"]):
                mismatch.append("PHASE_ORDER")
        return _result("compare_contract", "MATCH" if not mismatch else "MISMATCH", {"comparison": {
            "schema": "function-extractor.comparison/v1", "version": 1, "mismatches": mismatch,
            "normalized_trace_sha256": hashlib.sha256(_canonical(selected)).hexdigest(), "production_acceptance": False}})
    return _call("compare_contract", run)


def render_route_report(graph: dict, trace=None) -> dict:
    def run():
        selected = _graph(graph)
        lines = ["# Function Extractor route", "", "Evidence: static source; production acceptance absent.",
                 f"Files: {len(selected['files'])}; nodes: {len(selected['nodes'])}; edges: {len(selected['edges'])}.",
                 f"Unresolved caps: {len(selected['unresolved_caps'])}."]
        if trace is not None:
            observation = _trace(trace)
            status = observation["status"] if observation["status"] in {"RETURNED", "RAISED", "DENIED", "REFUSED", "TIMEOUT", "TRACE_LIMIT"} else "UNKNOWN"
            lines += [f"Replay status: {status}; spans: {len(observation.get('spans', []))}.",
                      "Fixture boundaries are simulated; no historical cause inferred."]
        return _result("render_route_report", "RENDERED", {"report": "\n".join(lines) + "\n"})
    return _call("render_route_report", run)


def propose_contract_update(contract: dict, trace: dict) -> dict:
    def run():
        previous, observed = _contract(contract), _normalize(_trace(trace))
        if observed["status"] not in {"RETURNED", "RAISED", "DENIED", "REFUSED", "TIMEOUT", "TRACE_LIMIT"}:
            return _result("propose_contract_update", "UNRESOLVED", errors=("UNSUPPORTED_TRACE_STATUS",))
        proposal = {"schema": "function-extractor.contract-proposal/v1", "version": 1, "status": "PROPOSED",
                    "base_contract_sha256": hashlib.sha256(_canonical(previous)).hexdigest(),
                    "observation_sha256": hashlib.sha256(_canonical(observed)).hexdigest(),
                    "overlay": {"expected_status": observed["status"], "result_summary": observed.get("result_summary", {})},
                    "accepted": False, "canonical_registry_mutated": False}
        return _result("propose_contract_update", "PROPOSED", {"proposal": proposal})
    return _call("propose_contract_update", run)


def verify_repeatability(traces: list) -> dict:
    def run():
        if type(traces) is not list or not 2 <= len(traces) <= 100:
            raise ValueError("repeatability_bound")
        normalized = [_normalize(_trace(value)) for value in traces]
        digests = [hashlib.sha256(_canonical(value)).hexdigest() for value in normalized]
        return _result("verify_repeatability", "REPEATABLE" if len(set(digests)) == 1 else "MISMATCH", {"repeatability": {
            "schema": "function-extractor.repeatability/v1", "version": 1, "runs": len(digests), "digests": digests,
            "normalized_equal": len(set(digests)) == 1, "production_acceptance": False}})
    return _call("verify_repeatability", run)
