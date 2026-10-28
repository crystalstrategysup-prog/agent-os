"""Fixed, versioned offline CLI. No free-text execution or live-send command."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from . import __version__
from .runner.bundle import canonical, materialize_bundle, pack_bundle
from .runner.loader import load_engine


# Reviewed machine codes only. Never forward arbitrary exception text.
_SAFE_REFUSAL_CODES = frozenset({"graph_expansion_cap"})


def _read(path, cap=2_000_000):
    from .workflow import public_path
    path = public_path(path)
    return json.loads(load_engine("route_probe_replay")._read_public(path, cap))


def _out(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _repeatability(args):
    """Compare saved public traces; never dispatch or strip evidence fields."""
    from .api import verify_repeatability
    from .workflow import write_new
    if not 2 <= len(args.trace) <= 100:
        raise ValueError("repeatability_trace_count")
    traces = []
    total = 0
    for path in args.trace:
        value = _read(path)
        total += len(canonical(value))
        if total > 8_000_000:
            raise ValueError("repeatability_total_bytes")
        traces.append(value)
    value = verify_repeatability(traces)
    write_new(args.out, value)
    _out(value)
    return {"REPEATABLE": 0, "MISMATCH": 3}.get(value["status"], 2)


def _new_output(path):
    path = Path(path)
    path.mkdir(parents=True, mode=0o700, exist_ok=False)
    return path


def _method_inventory(args):
    """Inspect verified source bytes only; never import the selected application."""
    from . import method_inventory
    from .contract_engine import content_digest
    from .workflow import public_path, write_new
    policy, catalog = _read(args.policy), _read(args.catalog)
    contracts = _read(args.contracts) if args.contracts else None
    with materialize_bundle(public_path(args.bundle)) as bundle:
        manifest, sources = load_engine("route_probe_replay")._verify(bundle, with_sources=True)
        value = method_inventory.inventory_methods(manifest, sources, policy, catalog, contracts)
    commit = manifest.get("source_pin", {}).get("commit")
    value["source_ref"] = {
        "commit": commit if type(commit) is str and re.fullmatch(r"[a-f0-9]{40}", commit) else None,
        "proof": "FROZEN_MANIFEST_DECLARATION_NOT_CURRENT_GIT_OR_RUNTIME",
    }
    # Pure core identity is complemented by exact maintained tool source pins.
    # These are tool-file observations, never a production loaded-module proof.
    selected = [Path(__file__), Path(method_inventory.__file__),
                Path(__file__).with_name("contract_engine.py")]
    value.setdefault("engine", dict(method_inventory.ENGINE))["file_pins"] = {
        path.name: hashlib.sha256(load_engine("route_probe_replay")._read_public(
            public_path(path), 1_000_000)).hexdigest() for path in selected
    }
    value["content_digest"] = content_digest(value)
    write_new(args.out, value)
    _out({"schema": "function-extractor.cli/v1", "status": value["status"],
          "path": str(args.out), "methods": len(value.get("methods", [])),
          "callsites": len(value.get("callsites", [])), "unresolved": len(value.get("unresolved", [])),
          "runtime_acceptance": False, "live_provider_observed": False})
    return 2 if value["status"] == "REFUSED" else 0


def _dot(graph):
    # JSON string quoting prevents labels from becoming DOT syntax.
    lines = ["digraph route {"]
    for node in graph.get("nodes", []):
        lines.append("  " + json.dumps(node["id"]) + " [label=" + json.dumps(node["id"] + ":" + str(node["line"])) + "];")
    for edge in graph.get("edges", []):
        if edge.get("target"):
            lines.append("  " + json.dumps(edge["source"]) + " -> " + json.dumps(edge["target"]) + ";")
    return "\n".join(lines + ["}"]) + "\n"


def _source_pin(source_root, reference, bundle):
    """Compare frozen public bytes with actual local Git objects, without fetch."""
    if reference is None:
        return {"status": "FILE_HASH_ONLY", "commit": None}
    if not re.fullmatch(r"[0-9a-f]{40}", reference):
        raise ValueError("exact_source_commit_required")
    root = Path(source_root).absolute()
    def git(*args, directory=None):
        failure, code, data, _ = load_engine("route_probe_replay")._bounded_child(
            ["/usr/bin/git", "-C", str(directory or root), *args], {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, 5)
        if failure or code:
            raise ValueError("local_git_source_unavailable")
        return data
    top = Path(git("rev-parse", "--show-toplevel").decode().strip())
    prefix = root.relative_to(top)
    commit = git("rev-parse", "--verify", reference + "^{commit}").decode().strip()
    if commit != reference:
        raise ValueError("source_ref_is_not_exact_commit")
    manifest, sources = load_engine("route_probe_replay")._verify(bundle, with_sources=True)
    paths = {str(prefix / row["path"]): row["path"] for row in manifest["files"]}
    tree = git("ls-tree", "-z", "-r", commit, "--", *sorted(paths), directory=top)
    pinned = set()
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t", 1)
        mode, kind, sha = meta.split()
        path = name.decode()
        if path not in paths or kind != b"blob" or mode not in {b"100644", b"100755"}:
            raise ValueError("source_git_object")
        data = sources[paths[path]]
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest().encode()
        if actual != sha:
            raise ValueError("source_commit_bytes_differ")
        pinned.add(paths[path])
    return {"status": "GIT_OBJECTS_VERIFIED", "commit": commit, "git_files": sorted(pinned),
            "file_hash_only_additions": sorted(set(sources) - pinned), "loaded_runtime_proof": False}


def _automatic_diagnosis(trace, scenario, internal_path=None, provider_path=None):
    """Use only maintained local contract pins; no network or silent invention."""
    from .diagnostic_attribution import attribute_unknown
    if trace.get('status') != 'RETURNED' or trace.get('result_summary', {}).get('state') != 'unknown':
        return {'status': 'NOT_APPLICABLE'}
    if (internal_path is None) != (provider_path is None):
        return {'status': 'CONTRACT_BINDING_REQUIRED', 'receipt_state': 'unknown'}
    if internal_path is None and scenario != 'AVL-H06':
        return {'status': 'CONTRACT_BINDING_REQUIRED', 'receipt_state': 'unknown'}
    repo = Path(__file__).resolve().parents[2]
    # Maintained defaults must survive a clean checkout. Ignored historical
    # owner packets are evidence, never installation dependencies.
    root = repo / 'tools/function_extractor/contracts'
    internal = internal_path or (root / 'telegram_unknown.diagnostic-contract.json')
    provider = provider_path or (root / 'telegram_sendmessage.current-primary.json')
    if not internal.is_file() or not provider.is_file():
        return {'status': 'CONTRACT_BINDING_REQUIRED', 'receipt_state': 'unknown'}
    try:
        return attribute_unknown(trace, _read(internal), _read(provider), boundary_id=scenario)
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        return {'status': 'CONTRACT_INVALID', 'receipt_state': 'unknown'}


def _report(output, graph, trace, metadata):
    output = Path(output)
    (output / "trace.json").write_bytes(canonical(trace) + b"\n")
    with (output / "trace.jsonl").open("w") as stream:
        for span in trace.get("spans", []):
            stream.write(canonical(span).decode() + "\n")
    (output / "route_graph.json").write_bytes(canonical(graph) + b"\n")
    (output / "route_graph.dot").write_text(_dot(graph))
    from .api import discover_boundaries, propose_contract_update
    (output / "boundary_manifest.json").write_bytes(canonical(discover_boundaries(graph)) + b"\n")
    seed = {"schema": "function-extractor.contract/v1", "version": 1}
    (output / "contract_patch.json").write_bytes(canonical(propose_contract_update(seed, trace)) + b"\n")
    (output / "evidence_manifest.json").write_bytes(canonical(metadata) + b"\n")
    failure = next((s for s in trace.get("spans", []) if s.get("event") == "exception"), None)
    lines = ["# Function Extractor replay", "", "Outcome: **" + trace["status"] + "**", "",
             "Historical cause: **NOT REPRODUCED**. Injected faults exercise exact frozen code against explicit fixtures.",
             "Static possibility, executed calls, simulated boundaries and live delivery are separate evidence.",
             "", "First recorded exception (may be caught control flow, not a cause verdict): " + (str({k: failure.get(k) for k in ("file", "line", "symbol", "exception")}) if failure else "none recorded"),
             "Use fe compare --actual trace.json --baseline SUCCESS/trace.json for the first differing recorded boundary.",
             "", "Source checkout is not required after freezing; the single portable bundle and pinned runtime dependencies are required.",
             "Full worker/PG/concurrency/provider/SSE results must be read from their individual scenario proof scope."]
    (output / "ROUTE_REPORT.md").write_text("\n".join(lines) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="fe", description=__doc__)
    parser.add_argument("--version", action="version", version="function-extractor " + __version__)
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("discover", "extract"):
        p = subs.add_parser(name)
        p.add_argument("--source-root", type=Path, required=True)
        p.add_argument("--source-ref")
        p.add_argument("--entry", required=True)
        p.add_argument("--adapter")
        p.add_argument("--include-entry", action="append", default=[])
        p.add_argument("--include-module", action="append", default=[])
        p.add_argument("--capture-mode", choices=("STRICT", "PARTIAL_STATIC"), default="STRICT")
        p.add_argument("--opaque-module", action="append", default=[])
        p.add_argument("--out", type=Path, required=True)
    for name in ("inspect", "verify", "replay", "matrix"):
        p = subs.add_parser(name); p.add_argument("--bundle", type=Path, required=True)
        if name in {"replay", "matrix"}:
            p.add_argument("--fixture" if name == "replay" else "--scenarios", type=Path, required=True)
            p.add_argument("--runner", choices=("subprocess", "container"), default="container")
            p.add_argument("--mode", choices=("offline", "synthetic", "recorded-replay", "read-only", "controlled-live", "allowlisted-integration"), default="offline")
            p.add_argument("--scope", default="{}")
            p.add_argument("--scenario", default="explicit-fixture")
            p.add_argument("--diagnostic-internal", type=Path, help="versioned internal route contract JSON")
            p.add_argument("--diagnostic-provider", type=Path, help="versioned external provider source snapshot JSON")
            p.add_argument("--observation-bindings", type=Path, help="pinned offline capture bindings; requires --contracts")
            if name == "replay":
                p.add_argument("--contracts", type=Path, help="exact route-bound contract map for transient observations")
            if name == "matrix":
                p.add_argument("--bundle-map", type=Path, help="role -> {path, sha256} for separately frozen transactions")
                p.add_argument("--contracts", type=Path, help="versioned contract map; generated scenarios required")
                p.add_argument("--registry", type=Path, help="isolated evidence directory ending generated")
                p.add_argument("--budget-seconds", type=float, default=600)
            p.add_argument("--target-checkpoint", action="append", default=[])
            p.add_argument("--timeout", type=float, default=10)
            p.add_argument("--out", type=Path, required=True)
    p = subs.add_parser("compare"); p.add_argument("--actual", type=Path, required=True)
    comparison = p.add_mutually_exclusive_group(required=True)
    comparison.add_argument("--expected", type=Path)
    comparison.add_argument("--baseline", type=Path)
    p = subs.add_parser("repeatability", help="full normalized saved-trace equality; no target execution")
    p.add_argument("--trace", type=Path, action="append", required=True,
                   help="explicit saved trace; 2–100, each <=2MB, compact JSON total <=8MB")
    p.add_argument("--out", type=Path, required=True)
    p = subs.add_parser("contracts"); p.add_argument("--graph", type=Path)
    cp = p.add_subparsers(dest="contract_command").add_parser("resolve")
    cp.add_argument("--inputs", type=Path, required=True, help="{route,sources,revision} exact local snapshot inputs")
    cp.add_argument("--out", type=Path, required=True)
    mp = subs.add_parser("methods").add_subparsers(dest="method_command", required=True).add_parser("inventory")
    mp.add_argument("--bundle", type=Path, required=True)
    mp.add_argument("--policy", type=Path, required=True)
    mp.add_argument("--catalog", type=Path, required=True)
    mp.add_argument("--contracts", type=Path)
    mp.add_argument("--out", type=Path, required=True)
    sp = subs.add_parser("scenarios").add_subparsers(dest="scenario_command", required=True).add_parser("generate")
    sp.add_argument("--contracts", type=Path, required=True); sp.add_argument("--profile", type=Path, required=True)
    sp.add_argument("--seed", type=int, default=0); sp.add_argument("--max-cases", type=int, default=40)
    sp.add_argument("--max-input-variants", type=int, default=0); sp.add_argument("--out", type=Path, required=True)
    for command in ("validate", "docs"):
        p = subs.add_parser(command)
        if command == "docs":
            p.add_argument("operation", choices=("sync",)); p.add_argument("--target", choices=("generated",), required=True)
            p.add_argument("--registry", type=Path, required=True)
        p.add_argument("--run", type=Path, required=True); p.add_argument("--contracts", type=Path, required=True)
        p.add_argument("--scenarios", type=Path, required=True); p.add_argument("--out", type=Path, required=True)
    p = subs.add_parser("report"); rg = p.add_mutually_exclusive_group(required=True)
    rg.add_argument("--evidence", type=Path); rg.add_argument("--run", type=Path, help="validated evidence JSON")
    args = parser.parse_args(argv)
    start = time.monotonic()
    try:
        if args.command == "repeatability":
            return _repeatability(args)
        if args.command == "methods":
            return _method_inventory(args)
        if args.command == "contracts" and args.contract_command == "resolve":
            from .contract_engine import resolve_contracts
            from .workflow import write_new
            spec = _read(args.inputs)
            if type(spec) is not dict or set(spec) != {"route", "sources", "revision"}:
                raise ValueError("contract_resolution_input")
            value = resolve_contracts(**spec); write_new(args.out, value)
            _out({"schema": "function-extractor.cli/v1", "status": value["status"], "path": str(args.out),
                  "rules": len(value.get("rules", [])), "unresolved": len(value.get("unresolved", []))})
            return 2 if value["status"] == "REFUSED" else 0
        if args.command == "scenarios":
            from .scenario_engine import generate_scenarios
            from .workflow import write_new
            value = generate_scenarios(_read(args.contracts), _read(args.profile), args.seed,
                                      {"max_cases": args.max_cases, "max_input_variants": args.max_input_variants})
            write_new(args.out, value)
            _out({"schema": "function-extractor.cli/v1", "status": value["status"], "cases": len(value["cases"]), "path": str(args.out)})
            return 2 if value["status"] == "REFUSED" else 0
        if args.command in {"validate", "docs"}:
            from .evidence_registry import validate_run, sync_docs
            from .workflow import write_new
            value = validate_run(_read(args.run, 64_000_000), _read(args.contracts), _read(args.scenarios))
            if args.command == "docs":
                value = sync_docs(value, args.registry)
            write_new(args.out, value)
            _out({"schema": "function-extractor.cli/v1", "status": value["status"], "path": str(args.out)})
            return 2 if value["status"] == "REFUSED" else 0
        if args.command == "matrix" and args.contracts:
            from .workflow import contract_matrix
            if not args.registry:
                raise ValueError("generated_registry_required")
            roles = _read(args.bundle_map) if args.bundle_map else {}
            for item in roles.values():
                if not Path(item["path"]).is_absolute():
                    item["path"] = str(args.bundle_map.parent / item["path"])
            value = contract_matrix(contract_map=_read(args.contracts), scenarios=_read(args.scenarios),
                bundle_path=args.bundle, bundle_roles=roles, runner=args.runner, timeout=args.timeout,
                output=args.out, registry=args.registry, execute=_execute, mode=args.mode, budget_seconds=args.budget_seconds,
                observation_bindings=_read_observation_bindings(args.observation_bindings) if args.observation_bindings else None)
            _out({k: v for k, v in value.items() if k != "cases"})
            return 0 if value["status"] == "PASS" else 3 if value["status"] in {"FAIL", "UNKNOWN"} else 2
        if args.command == "discover":
            graph = load_engine("route_probe_graph").extract_route(args.source_root, args.entry,
                                                                     opaque_modules=args.opaque_module)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("xb") as stream:
                stream.write(canonical(graph) + b"\n")
            _out({"schema": "function-extractor.cli/v1", "status": "SOURCE_OBSERVED", "entry": graph["entry"],
                  "nodes": len(graph["nodes"]), "unresolved": len(graph.get("unresolved", [])), "path": str(args.out)})
            return 0
        if args.command == "extract":
            manifest = load_engine("route_probe").freeze_bundle(args.source_root, args.entry, args.out,
                adapter=args.adapter, include_modules=args.include_module, opaque_modules=args.opaque_module,
                include_entries=args.include_entry, capture_mode=args.capture_mode)
            pin = _source_pin(args.source_root, args.source_ref, args.out)
            manifest["source_pin"] = pin
            manifest_bytes = canonical(manifest) + b"\n"
            (args.out / "manifest.json").write_bytes(manifest_bytes)
            (args.out / "manifest.sha256").write_text(hashlib.sha256(manifest_bytes).hexdigest() + "\n")
            portable = pack_bundle(args.out, args.out / "route_bundle.json")
            graph = _read(args.out / "route_graph.json", 8_000_000)
            (args.out / "route_graph.dot").write_text(_dot(graph))
            meta = {"schema": "function-extractor.evidence/v1", "tool_version": __version__, "source_ref": args.source_ref,
                    "source_ref_proof": pin, "capture_mode": args.capture_mode, "portable": portable,
                    "elapsed_seconds": time.monotonic() - start, "production_effects": 0}
            (args.out / "evidence_manifest.json").write_bytes(canonical(meta) + b"\n")
            _out({"schema": "function-extractor.cli/v1", "status": "FROZEN" if args.capture_mode == "STRICT" else "FROZEN_PARTIAL_STATIC",
                  "files": len(manifest["files"]), **meta})
            return 0
        if args.command in {"compare", "contracts", "report"}:
            from . import api
            if args.command == "compare":
                if args.baseline:
                    from .diagnostics import compare_trace_paths
                    value = compare_trace_paths(_read(args.actual), _read(args.baseline))
                else:
                    value = api.compare_contract(_read(args.actual), _read(args.expected))
            elif args.command == "contracts":
                if not args.graph: raise ValueError("graph_or_resolve_required")
                value = api.discover_boundaries(_read(args.graph, 8_000_000))
            else:
                if args.run:
                    from .workflow import report_value
                    value = report_value(_read(args.run))
                else: value = {"schema": "function-extractor.report-index/v1", "status": "SOURCE_OBSERVED",
                         "report": str(args.evidence / "ROUTE_REPORT.md"), "exists": (args.evidence / "ROUTE_REPORT.md").is_file()}
            _out(value); return 2 if args.command == "report" and value.get("status") == "REFUSED" else 0
        with materialize_bundle(args.bundle) as bundle:
            manifest = _read(bundle / "manifest.json"); graph = _read(bundle / "route_graph.json", 8_000_000)
            if args.command in {"verify", "inspect"}:
                _out({"schema": "function-extractor.cli/v1", "status": "PINS_VERIFIED", "manifest": manifest,
                      "dynamic_gaps": graph.get("unresolved", []), "runtime_acceptance": False})
                return 0
            output = _new_output(args.out)
            scope = json.loads(args.scope)
            if type(scope) is not dict or set(scope) - {"tenant", "bot", "vertical"}:
                raise ValueError("unsupported_scope_policy")
            if args.mode not in {"offline", "synthetic", "recorded-replay"}:
                value = {"schema": "route-probe.trace/v1", "status": "BLOCKED_LIVE_PROOF",
                         "reason": "no_independently_verified_single_target_broker_and_lease", "spans": []}
                _report(output, graph, value, {"production_effects": 0, "mode": args.mode})
                _out(value); return 2
            if args.command == "matrix":
                if args.observation_bindings:
                    raise ValueError("observation_contracts_required")
                return _matrix(args, bundle, graph, output)
            fixture = _read(args.fixture)
            plan = None
            if args.observation_bindings:
                if not args.contracts:
                    raise ValueError("observation_contracts_required")
                from .wire_contract import compile_contract_observation_plan
                cmap = _read(args.contracts)
                plan = compile_contract_observation_plan(cmap, manifest,
                    rule_ids=[r['rule_id'] for r in cmap['rules'] if r['kind'] in {'input_schema','output_schema'}],
                    bindings=_read_observation_bindings(args.observation_bindings))
                if plan.get('status') != 'COMPILED':
                    raise ValueError("observation_plan_refused")
            elif args.contracts:
                raise ValueError("observation_bindings_required")
            trace = _execute(args.runner, bundle, fixture, args.timeout, contract_plan=plan)
            metadata = {"schema": "function-extractor.evidence/v1", "tool_version": __version__, "mode": args.mode,
                        "runner": args.runner, "bundle_sha256": hashlib.sha256(args.bundle.read_bytes()).hexdigest() if args.bundle.is_file() else None,
                        "fixture_sha256": hashlib.sha256(canonical(fixture)).hexdigest(), "scenario": args.scenario,
                        "elapsed_seconds": time.monotonic() - start, "live_provider_observed": False,
                        "production_effects": 0, "scope_labels_not_authority": scope,
                        "target_checkpoints": {name: "REACHED" if any(s.get("symbol") == name for s in trace.get("spans", []))
                                               else "UNREACHED_OR_UNRESOLVED" for name in args.target_checkpoint}}
            (output / "fixture.json").write_bytes(canonical(fixture) + b"\n")
            _report(output, graph, trace, metadata)
            diagnosis = _automatic_diagnosis(trace, args.scenario, args.diagnostic_internal, args.diagnostic_provider)
            (output / 'diagnosis.json').write_bytes(canonical(diagnosis) + b'\n')
            _out({"schema": "function-extractor.cli/v1", "status": trace["status"], "path": str(output),
                  "diagnosis": diagnosis, **metadata})
            return 0 if trace["status"] in {"RETURNED", "RAISED", "DENIED"} else 2
    except Exception as exc:
        refusal = {"schema": "function-extractor.cli/v1", "status": "REFUSED", "error_class": type(exc).__name__}
        if (type(exc) is ValueError and len(exc.args) == 1
                and type(exc.args[0]) is str and exc.args[0] in _SAFE_REFUSAL_CODES):
            refusal["error_code"] = exc.args[0]
        _out(refusal)
        return 2


def _read_observation_bindings(path):
    value = _read(path)
    if (type(value) is not dict or set(value) != {'schema','version','bindings'}
            or value['schema'] != 'function-extractor.contract-capture-bindings/v1'
            or type(value['version']) is not int or value['version'] != 1
            or type(value['bindings']) is not list or not 1 <= len(value['bindings']) <= 32):
        raise ValueError('observation_bindings_shape')
    return value['bindings']


def _execute(runner, bundle, fixture, timeout, *, contract_plan=None, runner_sha256=None):
    extra = {}
    if contract_plan is not None:
        from .workflow import _runner_pin
        extra = {'contract_plan': contract_plan, 'runner_sha256': runner_sha256 or _runner_pin()}
    if runner == "subprocess":
        return load_engine("route_probe_replay").replay_bundle(bundle, fixture, timeout=timeout, **extra)
    from .runner.container import execute_container
    return execute_container(bundle, fixture, timeout=timeout, **extra)


def _matrix(args, bundle, graph, output):
    spec = _read(args.scenarios)
    cases = spec.get("cases", spec.get("scenarios", []))
    if type(cases) is not list or not 1 <= len(cases) <= 40:
        raise ValueError("matrix_bound")
    identifiers = [case.get("id", str(index)) if type(case) is dict else None
                   for index, case in enumerate(cases)]
    if (any(type(name) is not str or not re.fullmatch(r"[A-Za-z_0-9.-]{1,80}", name) for name in identifiers)
            or len(set(identifiers)) != len(identifiers)
            or any(case.get("baseline_case_id") is not None
                   and (type(case["baseline_case_id"]) is not str or case["baseline_case_id"] not in identifiers)
                   for case in cases)):
        raise ValueError("matrix_identifiers")
    roles = _read(args.bundle_map) if args.bundle_map else {}
    if type(roles) is not dict or len(roles) > 10:
        raise ValueError("bundle_roles")
    rows = []; completed_paths = {}
    for index, case in enumerate(cases):
        fixture = case.get("fixture")
        if type(fixture) is str:
            fixture = _read(args.scenarios.parent / fixture)
        if type(fixture) is not dict:
            rows.append({"id": case.get("id", str(index)), "status": "UNKNOWN", "reason": "no_fixture"}); continue
        role = case.get("bundle_role")
        selected = roles.get(role)
        if role and selected is None:
            rows.append({"id": case.get("id", str(index)), "status": "UNKNOWN", "reason": "separate_bundle_not_qualified"})
            continue
        if selected is not None:
            if type(selected) is not dict or set(selected) != {"path", "sha256"}:
                raise ValueError("bundle_role_schema")
            path = Path(selected["path"])
            if not path.is_absolute():
                path = args.bundle_map.parent / path
            path = load_engine("route_probe_graph")._safe_path(path)
            raw = load_engine("route_probe_replay")._read_public(path, 32_000_000)
            if hashlib.sha256(raw).hexdigest() != selected["sha256"]:
                raise ValueError("bundle_role_pin")
            with materialize_bundle(path) as chosen:
                manifest = _read(chosen / "manifest.json")
                if manifest["entry"] != case.get("entry"):
                    raise ValueError("bundle_role_entry")
                trace = _execute(args.runner, chosen, fixture, args.timeout)
                selected_graph = _read(chosen / "route_graph.json", 8_000_000)
        else:
            manifest = _read(bundle / "manifest.json")
            if case.get("entry", manifest["entry"]) != manifest["entry"]:
                rows.append({"id": case.get("id", str(index)), "status": "UNKNOWN", "reason": "entry_not_in_selected_bundle"})
                continue
            trace = _execute(args.runner, bundle, fixture, args.timeout)
            selected_graph = graph
        node = output / str(index); node.mkdir()
        (node / "fixture.json").write_bytes(canonical(fixture) + b"\n")
        _report(node, selected_graph, trace, {"runner": args.runner, "fixture_sha256": hashlib.sha256(canonical(fixture)).hexdigest()})
        baseline_id = case.get("baseline_case_id")
        divergence = None
        if baseline_id is not None:
            from .diagnostics import compare_trace_paths
            reference = completed_paths.get(baseline_id)
            divergence = (compare_trace_paths(trace, _read(reference)) if reference else
                          {"status": "UNKNOWN", "reason": "baseline_not_yet_executed", "root_cause_proven": False})
            (node / "first_divergence.json").write_bytes(canonical(divergence) + b"\n")
        completed_paths[case.get("id", str(index))] = node / "trace.json"
        expected = case.get("expected", {})
        from .api import compare_contract
        comparison = compare_contract(trace, expected)
        status = {"MATCH": "PASS", "MISMATCH": "FAIL"}.get(comparison["status"], "UNKNOWN")
        if trace.get("result_matches_expected") is False:
            status = "FAIL"
        rows.append({"id": case.get("id", str(index)), "status": status, "outcome": trace["status"], "comparison": comparison,
                     "proof_scope": case.get("proof_scope", "SYNTHETIC_BOUNDARIES_ONLY"),
                     **({"path_comparison": divergence} if divergence is not None else {})})
        (output / "partial_results.json").write_bytes(canonical(rows) + b"\n")
        if trace["status"] in {"TIMEOUT", "REFUSED", "TRACE_LIMIT"}:
            break  # Preserve unknown creation/readback; never blind retry.
    status = ("FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS"
              if len(rows) == len(cases) and all(r["status"] == "PASS" for r in rows) else "UNKNOWN")
    result = {"schema": "function-extractor.matrix/v1", "status": status, "cases": rows,
              "universal_or_live_acceptance": False}
    (output / "scenario_results.json").write_bytes(canonical(result) + b"\n")
    _out({"schema": result["schema"], "status": result["status"], "cases": len(rows), "path": str(output)})
    return 0 if status == "PASS" else 3
