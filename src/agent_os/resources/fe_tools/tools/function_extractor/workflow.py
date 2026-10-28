"""Contract-bound offline workflow. Cached evidence is never fresh live proof."""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from . import evidence_registry as er
from .api import _trace
from .contract_engine import content_digest, selected_rule_digest, validate_contract_map
from .runner.bundle import canonical, materialize_bundle
from .runner.loader import load_engine

VERSION = "0.4.0"
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def public_path(path):
    from .contract_engine import _relative
    path = load_engine("route_probe_graph")._safe_path(Path(path))
    # The graph's original Python-source filter alone does not cover secret
    # JSON extensions. Reuse the reviewed Contract Engine's closed path policy.
    _relative(path.as_posix().lstrip("/"))
    return path


def read_json(path, cap=2_000_000):
    safe = public_path(path)
    return json.loads(load_engine("route_probe_replay")._read_public(safe, cap))


def write_new(path, value):
    """Only new public artifacts; refuse links and existing files."""
    path = public_path(path)
    data = canonical(value) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(fd, data[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)


def _new_dir(path):
    path = load_engine("route_probe_graph")._safe_path(Path(path))
    # The caller selects an isolated evidence parent, never the active checkout.
    if any(p.lower() in {"current", "secrets", "credentials", "backups", "tenants"} for p in path.parts):
        raise ValueError("isolated_output_required")
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    return path


def _runner_pin():
    root = Path(__file__).parent
    selected = [root / n for n in ("workflow.py", "cli.py", "api.py", "contract_engine.py", "evidence_registry.py", "scenario_engine.py",
                                 "wire_contract.py", "runner/container.py", "runner/bundle.py", "runner/loader.py", "runner/container_entry.py")]
    selected += [Path(load_engine(n).__file__) for n in ("route_probe", "route_probe_graph", "route_probe_replay")]
    return digest({"files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in selected},
                   "python": sys.version, "executable": str(Path(sys.executable).resolve())})


def _runtime_profile(runner):
    if runner == "container":
        # Existing driver verifies the entire dependency capsule before dispatch.
        from .runner.container import _capsule
        from .runner.environment_catalog import discover
        root = Path(__file__).resolve().parents[2]
        configuration = read_json(root / ".agentos/route-probe/container/IMAGE.json", 1_000_000)
        catalog = root / ".agentos/route-probe/container/ENVIRONMENTS.json"
        if catalog.exists() or catalog.is_symlink():
            selection = discover(root)
            if selection["status"] != "EXISTING_QUALIFIED":
                raise ValueError("qualified_environment_" + selection["status"].lower())
            if selection["image_id"] != configuration["image_id"]:
                raise ValueError("candidate_profile_not_bound")
        _capsule(configuration["capsule_root"], configuration["files"], configuration.get("public_binary_pins", ()))
        return digest(configuration)
    return digest({"runner": runner, "python": sys.version, "executable": str(Path(sys.executable).resolve())})


def _case_key(case, environment):
    return digest({"source_pins": case["source_pins"], "selected_rule_digest": case["selected_rule_digest"],
                   "fixture_digest": case["fixture_digest"], "expected": case["expected"],
                   "observation_expectations":case.get('observation_expectations',{}), "environment": environment})


def _cached_trace(root, key):
    try:
        with er._root(root, False) as fd:
            row = er._read(fd, "trace-" + key + ".json")
        if set(row) != {"schema", "key", "trace", "content_digest"} or row["schema"] != "function-extractor.cached-trace/v1" or row["key"] != key or content_digest(row) != row["content_digest"]:
            raise ValueError("trace_cache_integrity")
        _trace(row["trace"])
        return row["trace"]
    except FileNotFoundError:
        return None


def _save_trace(root, key, trace):
    # Existing trace validator admits only safe, bounded fields. No raw fixtures.
    _trace(trace)
    row = {"schema": "function-extractor.cached-trace/v1", "key": key, "trace": trace}
    row["content_digest"] = content_digest(row)
    if len(canonical(row)) > 2_000_000:
        return False
    with er._root(root, True) as fd:
        try:
            prior = er._read(fd, "trace-" + key + ".json")
            if prior != row:
                raise ValueError("trace_cache_conflict")
        except FileNotFoundError:
            er._atomic(fd, "trace-" + key + ".json", row)
    return True


def report_value(validation):
    try:
        er._validated(validation)
    except (ValueError, TypeError, KeyError, AttributeError):
        return {"schema": "function-extractor.contract-report/v1", "status": "REFUSED"}
    cases = validation["cases"]
    counts = {v: sum(c["test_verdict"] == v for c in cases) for v in ("PASS", "FAIL", "UNKNOWN")}
    return {"schema": "function-extractor.contract-report/v1", "status": "FAIL" if counts["FAIL"] else "UNKNOWN" if counts["UNKNOWN"] else "PASS",
            "counts": counts, "cases": cases, "coverage": validation["coverage"], "historical_cause": "NOT_REPRODUCED",
            "live_provider_observed": False, "production_acceptance": False}


def contract_matrix(*, contract_map, scenarios, bundle_path, bundle_roles, runner, timeout, output, registry,
                    execute, mode="offline", budget_seconds=600, observation_bindings=None):
    """Execute verified original bundles, validate, atomically publish evidence.

    Only explicit REPLAY cases reach a child. Shape-only/unknown cases stay
    unexecuted. Reusing a trace means reusing prior offline evidence, not a new
    send or a current authority receipt. All actual effects stay in the driver.
    """
    started = time.monotonic()
    if mode not in {"offline", "synthetic", "recorded-replay"}:
        return {"schema": "function-extractor.contract-workflow/v1", "status": "BLOCKED_LIVE_PROOF", "production_effects": 0}
    if validate_contract_map(contract_map)["status"] != "VALID" or scenarios.get("content_digest") != content_digest(scenarios) or scenarios.get("contract_digest") != contract_map["content_digest"]:
        raise ValueError("workflow_contract_identity")
    cases = scenarios["cases"]
    if not 1 <= len(cases) <= 40 or len({c["id"] for c in cases}) != len(cases) or any(not _ID.fullmatch(c["id"]) for c in cases):
        raise ValueError("workflow_cases_bound")
    if runner not in {"subprocess", "container"} or not 0 < timeout <= 30 or not 1 <= budget_seconds <= 3600:
        raise ValueError("workflow_execution_policy")
    if type(bundle_roles) is not dict or len(bundle_roles) > 10:
        raise ValueError("workflow_bundle_roles")
    if observation_bindings is not None and (type(observation_bindings) is not list or not 1 <= len(observation_bindings) <= 32):
        raise ValueError("workflow_observation_bindings")
    source = er.source_digest(contract_map)
    run = {"schema": "contract-run/v1", "source_sha256": source, "contract_sha256": contract_map["content_digest"],
           "fixture_sha256": scenarios["content_digest"], "cases": []}
    # Validate planned metadata before any dispatch; absent actuals remain UNKNOWN.
    if er.validate_run(run, contract_map, scenarios).get("status") != "VALIDATED":
        raise ValueError("workflow_plan_invalid")
    out = _new_dir(output)
    runtime_sha = _runner_pin(); profile_sha = _runtime_profile(runner)
    timing = {"bundle_verification_seconds": 0.0, "execution_seconds": 0.0, "validation_seconds": 0.0}
    cache_rows = []; bundles = {}; union = {}
    with ExitStack() as stack:
        snapshot_root = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="fe-contract-pins-")))
        requested = {c.get("bundle_role") for c in cases if c["execution_mode"] == "REPLAY"} | {None}
        verify_start = time.monotonic()
        for role in sorted(requested, key=lambda r: r or ""):
            item = bundle_roles.get(role) if role else {"path": str(bundle_path), "sha256": None}
            if not item or set(item) != {"path", "sha256"}:
                raise ValueError("workflow_role_missing")
            path = public_path(item["path"])
            raw = load_engine("route_probe_replay")._read_public(path, 32_000_000)
            bundle_sha = hashlib.sha256(raw).hexdigest()
            if role and bundle_sha != item["sha256"]:
                raise ValueError("workflow_role_pin")
            # Materialize the exact bytes whose SHA was admitted, never reopen
            # a mutable caller path between role admission and extraction.
            snapshot = snapshot_root / (bundle_sha + ".json")
            if not snapshot.exists():
                with snapshot.open("xb") as stream:
                    stream.write(raw)
                snapshot.chmod(0o600)
            directory = stack.enter_context(materialize_bundle(snapshot))
            manifest = read_json(directory / "manifest.json")
            graph = read_json(directory / "route_graph.json", 8_000_000)
            pins = {r["path"]: r["sha256"] for r in manifest["files"]}
            for p, sha in pins.items():
                if p in union and union[p] != sha:
                    raise ValueError("workflow_mixed_source_generations")
                union[p] = sha
            bundles[role] = (directory, manifest, graph, bundle_sha, digest(sorted(pins.items())))
        if sorted(union.items()) != [(p["path"], p["sha256"]) for p in contract_map["route"]["source_pins"]]:
            raise ValueError("workflow_route_source_closure")
        primary = bundles[None]
        if primary[1]["entry"] != scenarios["entry"] or primary[1]["graph_sha256"] != contract_map["route"]["graph_sha256"]:
            raise ValueError("workflow_primary_route")
        plans = {}
        if observation_bindings is not None:
            from .wire_contract import compile_contract_observation_plan
            rules_by_id = {r['rule_id']:r for r in contract_map['rules']}
            # Qualify every requested capture before the first child dispatch.
            # Other transaction roots need their own exact route-bound map.
            for case in cases:
                if case['execution_mode'] != 'REPLAY':
                    continue
                selected = [rules_by_id[rid] for rid in case['rule_ids'] if rules_by_id[rid]['kind'] in {'input_schema','output_schema'}]
                if not selected:
                    continue
                scopes = {(r['boundary_id'],r['kind']) for r in selected}
                bindings = [b for b in observation_bindings if (b.get('boundary_id'), b.get('direction','')+'_schema') in scopes]
                plan = compile_contract_observation_plan(contract_map, bundles[case.get('bundle_role')][1],
                    rule_ids=[r['rule_id'] for r in selected], bindings=bindings)
                if plan.get('status') != 'COMPILED':
                    raise ValueError('workflow_observation_plan_refused')
                plans[case['id']] = plan
        timing["bundle_verification_seconds"] = time.monotonic() - verify_start
        write_new(out / "route_graph.json", primary[2])
        # Reuse the established DOT serializer without changing source semantics.
        from .cli import _dot
        (out / "route_graph.dot").write_text(_dot(primary[2]))
        halted = False
        for case in cases:
            if time.monotonic() - started >= budget_seconds:
                halted = True
            if case["execution_mode"] != "REPLAY" or halted:
                cache_rows.append({"case_id": case["id"], "executed_this_run": False, "cache_hit": False, "scope": case["execution_mode"] if not halted else "AFTER_INCOMPLETE_STOP"})
                continue
            if case["fixture_digest"] != digest(case["fixture"]) or case["selected_rule_digest"] != selected_rule_digest(contract_map, case["rule_ids"]):
                raise ValueError("workflow_case_identity")
            directory, manifest, graph, bundle_sha, manifest_sha = bundles[case.get("bundle_role")]
            if manifest["entry"] != case["entry"]:
                raise ValueError("workflow_case_entry")
            plan = plans.get(case['id'])
            environment = {"source_sha256": source, "bundle_sha256": bundle_sha, "manifest_source_sha256": manifest_sha,
                           "runner_sha256": runtime_sha, "profile_sha256": digest({'runtime':profile_sha,'observation_plan':plan['content_digest']}) if plan else profile_sha, "runner": runner}
            key = _case_key(case, environment)
            trace = _cached_trace(registry, key)
            hit = trace is not None
            then = time.monotonic()
            if not hit:
                remaining = budget_seconds - (time.monotonic() - started)
                if remaining < 1:
                    halted = True
                    cache_rows.append({"case_id": case["id"], "executed_this_run": False, "cache_hit": False, "scope": "WHOLE_BUDGET_EXHAUSTED"})
                    continue
                trace = (execute(runner, directory, case["fixture"], min(timeout, remaining), contract_plan=plan, runner_sha256=runtime_sha)
                         if plan is not None else execute(runner, directory, case["fixture"], min(timeout, remaining)))
            _trace(trace)
            # Actual child records the exact fixture, not a label supplied by us.
            if trace.get("fixture_sha256") != case["fixture_digest"] or trace.get("source_entry") != case["entry"]:
                raise ValueError("workflow_trace_fixture_pin")
            timing["execution_seconds"] += time.monotonic() - then
            run["cases"].append({"case_id": case["id"], "trace": trace, "environment": environment})
            recording = trace.get("trace_recording", {})
            complete = (trace["status"] in {"RETURNED", "RAISED", "DENIED"} and recording.get("complete") is True
                        and recording.get("dropped_events") == 0 and recording.get("recorded_events") == len(trace["spans"])
                        and ("expected_result" not in case["fixture"] or type(trace.get("result_matches_expected")) is bool))
            if complete and not hit:
                _save_trace(registry, key, trace)
            write_new(out / (case["id"] + ".trace.json"), trace)
            cache_rows.append({"case_id": case["id"], "executed_this_run": not hit, "cache_hit": hit, "cache_key": key,
                               "fixture_sha256": case["fixture_digest"], "entry": case["entry"], "bundle_sha256": bundle_sha})
            # Preserve incomplete attempts. No automatic retry/cleanup/rollback.
            halted = not complete
    then = time.monotonic()
    validated = er.validate_run(run, contract_map, scenarios)
    if validated.get("status") != "VALIDATED":
        write_new(out / "run.json", run)
        write_new(out / "validation.json", validated)
        raise ValueError("workflow_validation_refused")
    synced = er.sync_docs(validated, registry)
    if synced["status"] == "REFUSED":
        raise ValueError("workflow_registry_refused")
    timing["validation_seconds"] = time.monotonic() - then
    report = report_value(validated)
    from .diagnostics import compare_trace_paths
    # Different entrypoints are independent transactions; never splice them.
    baselines = {}
    for case in cases:
        row = next((r for r in run["cases"] if r["case_id"] == case["id"]), None)
        if row and case.get("expected_delivery_state") == "sent":
            family = (case["entry"], case["fixture"].get("stack_variant", "direct"))
            baselines.setdefault(family, row)
    divergences = []
    for case in cases:
        row = next((r for r in run["cases"] if r["case_id"] == case["id"]), None)
        baseline = baselines.get((case["entry"], case["fixture"].get("stack_variant", "direct")))
        if row and baseline:
            divergences.append({"case_id": case["id"], "baseline_id": baseline["case_id"],
                                "comparison": compare_trace_paths(row["trace"], baseline["trace"])})
    write_new(out / "first_divergences.json", {"schema": "function-extractor.divergences/v1", "cases": divergences,
                                             "historical_cause_proven": False})
    write_new(out / "run.json", run)
    write_new(out / "validation.json", validated)
    write_new(out / "report.json", report)
    write_new(out / "contract_patch.json", {"schema": "function-extractor.proposals/v1", "status": "PROPOSED", "normative_modified": False,
                                            "items": er._passport(validated)["proposed"], "drift": er._passport(validated)["drift"]})
    timing["total_seconds"] = time.monotonic() - started
    summary = {"schema": "function-extractor.contract-workflow/v1", "version": 1, "status": report["status"], "counts": report["counts"],
               "cases": cache_rows, "timing": timing, "registry": synced, "source_sha256": source,
               "contract_sha256": contract_map["content_digest"], "runner_sha256": runtime_sha, "profile_sha256": profile_sha,
               "production_effects": 0, "live_provider_observed": False, "historical_cause": "NOT_REPRODUCED"}
    write_new(out / "workflow.json", summary)
    lines = ["# Contract-bound replay", "", "Status: **" + report["status"] + "**", "",
             "Historical AVL incident: **NOT REPRODUCED**. All replay provider boundaries are synthetic.",
             "Expected compatibility, normative checks and delivery_state are separate fields in validation.json.",
             "Cached traces are prior offline evidence; they are not new execution or current runtime/authority proof.",
             "Wire-schema variants without an actual adapter remain UNKNOWN and are not target execution.",
             "Branch denominator is UNKNOWN unless a complete inventory was supplied.", "",
             "| Case | Test | Delivery |", "|---|---|---|"]
    lines += ["| " + c["case_id"] + " | " + c["test_verdict"] + " | " + c["delivery_state"] + " |" for c in validated["cases"]]
    (out / "ROUTE_REPORT.md").write_text("\n".join(lines) + "\n")
    return summary
