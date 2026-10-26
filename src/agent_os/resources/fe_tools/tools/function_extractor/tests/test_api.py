"""New offline public API tests; selected target functions run only in the child."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.function_extractor import api


class FunctionExtractorAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="function-extractor-api-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        self.source.mkdir()
        (self.source / "pricing.py").write_text("def tax(value):\n    return value * 2\ndef total(value):\n    return tax(value) + 1\n")

    def bundle(self):
        result = api.freeze_source(self.source, "pricing:total", self.base / "bundle")
        self.assertEqual(result["status"], "FROZEN", result)
        return Path(result["data"]["bundle"])

    def trace(self):
        return {"schema": "route-probe.trace/v1", "status": "RETURNED",
            "correlation_id": "d34ed9e847c14101831d041105baae30", "sandbox": {"audit": True, "seccomp": True},
            "result_summary": {"type": "DeliveryReceipt", "state": "sent", "effect_started": True},
            "spans": [{"phase": "entry", "event": "ENTER", "evidence": "REAL_CODE", "utc": "2026-01-01T00:00:00Z", "monotonic": 1.0},
                      {"phase": "guard", "event": "CHECKED", "evidence": "GUARD", "utc": "2026-01-01T00:00:01Z", "monotonic": 2.0}]}

    def test_all_twelve_exports_are_lazy_and_uniform(self):
        import tools.function_extractor as package
        self.assertEqual(len(package.__all__), 12)
        for name in package.__all__:
            self.assertTrue(callable(getattr(package, name)))
        old_path = list(sys.path)
        result = api.resolve_entry(self.source, "pricing:total")
        self.assertEqual(result["status"], "RESOLVED")
        self.assertEqual(result["version"], 1)
        self.assertEqual(set(result), {"schema", "version", "operation", "status", "data", "errors"})
        self.assertEqual(sys.path, old_path)
        self.assertNotIn("pricing", sys.modules)
        self.assertNotIn("tools.route_probe_graph", sys.modules)

    def test_graph_cache_reuses_only_matching_pins(self):
        first = api.extract_route(self.source, "pricing:total")
        self.assertEqual(first["status"], "EXTRACTED")
        cached = api.extract_route(self.source, "pricing:total", cache=first)
        self.assertEqual(cached["status"], "CACHED")
        self.assertEqual(first["data"], cached["data"])
        (self.source / "pricing.py").write_text("def total(value):\n    return value + 10\n")
        changed = api.extract_route(self.source, "pricing:total", cache=first)
        self.assertEqual(changed["status"], "EXTRACTED")
        self.assertNotEqual(first["data"]["graph"]["files"], changed["data"]["graph"]["files"])

    def test_cache_invalidates_new_import_resolution_and_never_bypasses_limits(self):
        (self.source / "pricing.py").write_text("import optional_dependency\ndef total(value):\n    return optional_dependency.run(value)\n")
        first = api.extract_route(self.source, "pricing:total")
        (self.source / "optional_dependency.py").write_text("def run(value):\n    return value\n")
        changed = api.extract_route(self.source, "pricing:total", cache=first)
        self.assertEqual(changed["status"], "EXTRACTED")
        self.assertIn("optional_dependency.py", [f["path"] for f in changed["data"]["graph"]["files"]])
        invalid = api.extract_route(self.source, "pricing:total", max_files=True, cache=first)
        self.assertEqual(invalid["status"], "REFUSED")

    def test_bad_entry_secret_and_caps_fail_closed(self):
        self.assertEqual(api.resolve_entry(self.source, "../pricing:total")["status"], "REFUSED")
        secret = self.source / "credentials"
        secret.mkdir()
        (secret / "fixture.py").write_text("def total():\n    return 1\n")
        self.assertEqual(api.resolve_entry(self.source, "credentials.fixture:total")["status"], "REFUSED")
        (self.source / "pricing.py").write_text("from more import next_step\ndef total(value):\n    return next_step(value)\n")
        (self.source / "more.py").write_text("def next_step(value):\n    return value\n")
        capped = api.extract_route(self.source, "pricing:total", max_files=1)
        self.assertEqual(capped["status"], "UNRESOLVED")
        self.assertEqual(api.compile_fixture({"args": [1]}, graph=capped)["status"], "UNRESOLVED")

    def test_explicit_partial_static_preserves_caps_and_executes_whole_module(self):
        # Real complete source is pinned, even where bounded call discovery stops.
        (self.source / "pricing.py").write_text("".join(
            f"def f{i}(value):\n    return " + (f"f{i+1}(value)\n" if i < 11 else "value + 1\n")
            for i in range(12)))
        strict = api.freeze_source(self.source, "pricing:f0", self.base / "strict")
        self.assertEqual(strict["status"], "REFUSED", strict)
        self.assertFalse((self.base / "strict").exists())
        partial = api.freeze_source(self.source, "pricing:f0", self.base / "partial",
                                    capture_mode="PARTIAL_STATIC")
        self.assertEqual(partial["status"], "FROZEN_PARTIAL_STATIC", partial)
        bundle = Path(partial["data"]["bundle"])
        self.assertEqual(partial["data"]["manifest"]["capture_mode"], "PARTIAL_STATIC")
        graph = json.loads((bundle / "route_graph.json").read_text())
        self.assertFalse(graph["complete"])
        self.assertTrue(graph["unresolved_caps"])
        self.assertEqual({x["kind"] for x in graph["unresolved_caps"]}, {"max_depth"})
        self.assertEqual(graph["limits"], {"max_files": 80, "max_nodes": 1200, "max_depth": 8})
        replay = api.execute_route(bundle, {"args": [4], "expected_result": 5}, timeout=5)
        self.assertEqual(replay["status"], "EXECUTED", replay)
        trace = replay["data"]["trace"]
        self.assertTrue(trace["result_matches_expected"])
        self.assertTrue(trace["sandbox"]["audit"] and trace["sandbox"]["seccomp"])
        self.assertTrue(any(x.get("symbol") == "f11" for x in trace["spans"]))
        engine = api._engine("route_probe_graph")
        original = engine.extract_route
        for kind in ("max_files", "max_nodes", "max_edges_or_branches"):
            def capped(*args, _kind=kind, **kwargs):
                value = original(*args, **kwargs)
                value["unresolved_caps"].append({"kind": _kind, "source": "pricing:f0", "line": 1, "target": "pricing:f1"})
                return value
            with self.subTest(kind=kind), patch.object(engine, "extract_route", capped):
                refused = api.freeze_source(self.source, "pricing:f0", self.base / kind,
                                            capture_mode="PARTIAL_STATIC")
                self.assertEqual(refused["status"], "REFUSED", refused)
                self.assertFalse((self.base / kind).exists())
        for bad in (True, "partial_static", [], None):
            with self.subTest(mode=bad):
                self.assertEqual(api.freeze_source(self.source, "pricing:f0", self.base / "invalid",
                                                  capture_mode=bad)["status"], "REFUSED")
        import jsonschema
        schema = json.loads((Path(__file__).parents[1] / "contracts/manifest.schema.json").read_text())
        jsonschema.validate(partial["data"]["manifest"], schema)
        legacy = dict(partial["data"]["manifest"])
        legacy.pop("capture_mode")
        jsonschema.validate(legacy, schema)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate({**legacy, "capture_mode": "RELAXED"}, schema)

    def test_saved_actual_graph_uses_graph_only_json_budgets(self):
        # Optional large public evidence is supplied by the selected route run;
        # absence is an explicit skip, never a synthetic actual-graph PASS.
        path = Path(__file__).parents[3] / ".agentos/route-probe/vl_routes/CANONICAL_V2_GUARDED_FIRST/bundle/route_graph.json"
        if not path.exists():
            self.skipTest("selected actual graph evidence not present")
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "2442723c39f106f5e1b1e3cfb3f9d452d6bafa2aa5a22daa843c44bf7b5b6b5a")
        self.assertGreater(len(raw), 2_000_000)
        graph = json.loads(raw)
        plan = api.discover_boundaries(graph)
        self.assertEqual(plan["status"], "PLANNED", plan)
        self.assertFalse(plan["data"]["executed"])
        self.assertEqual(plan["data"]["unresolved_caps"], graph["unresolved_caps"])
        report = api.render_route_report(graph)
        self.assertEqual(report["status"], "RENDERED", report)
        self.assertIn(f"Files: {len(graph['files'])}", report["data"]["report"])
        too_large = dict(graph, semantics="x" * 8_000_000)
        self.assertEqual(api.discover_boundaries(too_large)["status"], "REFUSED")
        too_many = dict(graph, unresolved_caps=[{"kind": "", "source": "", "line": 0, "target": ""}] * 50001)
        self.assertLess(len(api._canonical(too_many)), 8_000_000)
        self.assertEqual(api.render_route_report(too_many)["status"], "REFUSED")
        # Non-graph callers retain their original 50k-item/2MB defaults.
        with self.assertRaises(ValueError):
            api._json([0] * 50001)
        with self.assertRaises(ValueError):
            api._json("x" * 2_000_000)

    def test_closed_trace_recording_and_repeatability_preserve_incompleteness(self):
        trace = self.trace()
        trace["status"] = "TRACE_LIMIT"
        trace["target_outcome"] = {"status": "RETURNED", "result_summary": {"type": "str"}}
        trace["trace_recording"] = {"complete": False, "recorded_events": 2,
                                    "dropped_events": 4, "selected_modules": ["pkg.core", "pkg.worker"]}
        timed = copy.deepcopy(trace)
        timed["spans"][0]["monotonic"] = 99.0
        timed["spans"][0]["utc"] = "2026-10-23T00:00:00Z"
        self.assertEqual(api.verify_repeatability([trace, timed])["status"], "REPEATABLE")
        for key, value in (("complete", True), ("recorded_events", 1), ("dropped_events", 5),
                           ("selected_modules", [])):
            changed = copy.deepcopy(trace)
            changed["trace_recording"][key] = value
            self.assertEqual(api.verify_repeatability([trace, changed])["status"], "MISMATCH")
        old = self.trace()
        self.assertEqual(api.verify_repeatability([old, copy.deepcopy(old)])["status"], "REPEATABLE")
        recording = trace["trace_recording"]
        invalid = [None, {}, {**recording, "raw": "NOT_EXPORTED"},
            {**recording, "complete": 0}, {**recording, "recorded_events": True},
            {**recording, "recorded_events": 5001}, {**recording, "recorded_events": -1},
            {**recording, "dropped_events": 1.0}, {**recording, "dropped_events": 10000001},
            {**recording, "dropped_events": -1}]
        for modules in (None, ["pkg.worker", "pkg.core"], ["pkg.core", "pkg.core"],
                        ["pkg.*"], ["../pkg"], ["pkg\n"], ["a" * 181], [True],
                        [f"pkg.n{i:02d}" for i in range(33)]):
            invalid.append({**recording, "selected_modules": modules})
        for bad in invalid:
            with self.subTest(recording=bad):
                malformed = {**trace, "trace_recording": bad}
                self.assertEqual(api.verify_repeatability([malformed, malformed])["status"], "REFUSED")
        from jsonschema import Draft202012Validator, RefResolver
        directory = Path(__file__).parents[1] / "contracts"
        schemas = [json.loads(p.read_text()) for p in directory.glob("*.schema.json")]
        store = {s["$id"]: s for s in schemas if "$id" in s}
        schema = store["https://function-extractor.invalid/contracts/v1/trace.schema.json"]
        def deny_remote(_):
            raise AssertionError("schema_network_not_allowed")
        validator = Draft202012Validator(schema, resolver=RefResolver.from_schema(schema, store=store,
            handlers={"http": deny_remote, "https": deny_remote}))
        validator.validate(trace)
        validator.validate(old)
        for bad in (None, {}, {**recording, "raw": "NOT_EXPORTED"},
                    {**recording, "selected_modules": ["pkg.*"]}, {**recording, "dropped_events": 10000001}):
            self.assertTrue(list(validator.iter_errors({**trace, "trace_recording": bad})))

    def test_actual_complete_canonical_trace_and_trace_only_item_budget(self):
        path = Path(__file__).parents[3] / ".agentos/route-probe/vl_routes/CANONICAL_V2_OBSERVER_SUCCESSOR/FINAL_SOURCE_971362_BATCH/1_group_success/trace.json"
        if not path.exists():
            self.skipTest("selected complete canonical trace evidence not present")
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "059ed133066bfa70acad6319898fd66796a284449d64f17c40e4c7f987145470")
        trace = json.loads(raw)
        self.assertEqual(len(trace["spans"]), 3834)
        self.assertTrue(trace["trace_recording"]["complete"])
        self.assertEqual(trace["trace_recording"]["dropped_events"], 0)
        self.assertEqual(api._trace(trace)["status"], "RETURNED")
        expected = {"schema": "function-extractor.contract/v1", "version": 1, "expected_status": "RETURNED"}
        self.assertEqual(api.compare_contract(trace, expected)["status"], "MATCH")
        spans = [{"phase": "call", "event": "call", "evidence": "REAL_CODE", "symbol": "worker",
                  "file": "worker.py", "line": 1, "span_id": index + 1, "parent_span_id": None,
                  "duration_seconds": 0.0, "input_shape": {"positional_parameters": 2,
                      "keyword_only_parameters": 1, "varargs": False, "varkw": False}}
                 for index in range(5000)]
        maximum = {"schema": "route-probe.trace/v1", "status": "RETURNED", "spans": spans,
                   "trace_recording": {"complete": True, "recorded_events": 5000,
                                       "dropped_events": 0, "selected_modules": []}}
        self.assertLess(len(api._canonical(maximum)), 2_000_000)
        self.assertEqual(len(api._trace(maximum)["spans"]), 5000)
        too_many = dict(trace, timings=[0] * 150001)
        self.assertLess(len(api._canonical(too_many)), 2_000_000)
        with self.assertRaisesRegex(ValueError, "^json_bound$"):
            api._trace(too_many)
        with self.assertRaisesRegex(ValueError, "^json_bound$"):
            api._trace(dict(trace, timings="x" * 2_000_000))
        # Existing generic JSON and fixed span ceilings remain independent.
        with self.assertRaisesRegex(ValueError, "^json_bound$"):
            api._json([0] * 50001)
        with self.assertRaisesRegex(ValueError, "^trace_bound$"):
            api._trace({"schema": "route-probe.trace/v1", "status": "RETURNED",
                        "spans": [{"phase": "x", "event": "x", "evidence": "REAL_CODE"}] * 10001})

    def test_boundary_planner_is_static_not_permission(self):
        (self.source / "pricing.py").write_text("import requests\ndef total(value):\n    return requests.get(value)\n")
        graph = api.extract_route(self.source, "pricing:total")
        result = api.discover_boundaries(graph)
        self.assertEqual(result["status"], "PLANNED")
        self.assertFalse(result["data"]["executed"])
        self.assertIn("network", {b["kind"] for b in result["data"]["boundaries"]})
        self.assertTrue(all(b["evidence"] == "STATIC_NOT_EXECUTED" for b in result["data"]["boundaries"]))

    def test_fixture_version_json_bounds_and_hash(self):
        result = api.compile_fixture({"args": [5], "kwargs": {}})
        self.assertEqual(result["status"], "COMPILED")
        payload = result["data"]["fixture"]["payload"]
        self.assertEqual(result["data"]["payload_sha256"], hashlib.sha256(api._canonical(payload)).hexdigest())
        for bad in ({"schema": "function-extractor.fixture/v1", "version": True, "payload": {}},
                    {"args": "no"}, {"args": [float("nan")]}, {"args": [object()]}, {"args": ["x" * 65536]}):
            with self.subTest(bad_type=type(bad)):
                self.assertEqual(api.compile_fixture(bad)["status"], "REFUSED")

    def test_sandbox_plan_and_real_pure_child_execution_are_separate(self):
        bundle = self.bundle()
        planned = api.build_sandbox(bundle)
        self.assertEqual(planned["status"], "PLANNED")
        self.assertFalse(planned["data"]["enforcement_proven"])
        self.assertFalse(planned["data"]["container_proven"])
        result = api.execute_route(bundle, api.compile_fixture({"args": [4], "expected_result": 9}), timeout=5)
        self.assertEqual(result["status"], "EXECUTED", result)
        trace = result["data"]["trace"]
        self.assertEqual(trace["status"], "RETURNED")
        self.assertTrue(trace["result_matches_expected"])
        self.assertEqual(trace["target_outcome"]["status"], "RETURNED")
        self.assertTrue(trace["sandbox"]["audit"])
        self.assertTrue(trace["sandbox"]["seccomp"])
        self.assertTrue(any(s.get("symbol") == "tax" for s in trace["spans"]))
        self.assertNotIn("pricing", sys.modules)

    def test_tamper_and_timeout_requests_are_not_executed(self):
        bundle = self.bundle()
        (bundle / "source/pricing.py").write_text("def total(value):\n    return 0\n")
        self.assertEqual(api.build_sandbox(bundle)["status"], "REFUSED")
        result = api.execute_route(bundle, {"args": [4]})
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["data"]["trace"]["status"], "REFUSED")
        for bad in (True, 0, 31, float("nan")):
            self.assertEqual(api.execute_route(bundle, {}, timeout=bad)["status"], "REFUSED")

    def test_fault_injection_only_proposes_explicit_synthetic_adapter(self):
        source = {"case": "success", "route": "platform_group"}
        result = api.inject_fault(source, {"kind": "read_timeout", "adapter": "tools.route_probe_avl:prepare"})
        self.assertEqual(result["status"], "PROPOSED")
        self.assertFalse(result["data"]["applied"])
        self.assertEqual(result["data"]["fixture"]["payload"]["case"], "timeout")
        self.assertEqual(source["case"], "success")
        unknown = api.inject_fault(source, {"kind": "provider_live", "adapter": "foreign:prepare"})
        self.assertEqual(unknown["status"], "UNRESOLVED")
        self.assertFalse(unknown["data"]["applied"])

    def test_comparison_preserves_order_results_exceptions_and_guards(self):
        trace = self.trace()
        contract = {"schema": "function-extractor.contract/v1", "version": 1, "expected_status": "RETURNED",
            "result_summary": {"state": "sent"}, "guards": {"audit": True, "seccomp": True},
            "phase_events": [{"phase": "entry", "event": "ENTER"}, {"phase": "guard", "event": "CHECKED"}]}
        self.assertEqual(api.compare_contract(trace, contract)["status"], "MATCH")
        trace["spans"].reverse()
        self.assertEqual(api.compare_contract(trace, contract)["status"], "MISMATCH")
        trace = self.trace(); trace["sandbox"]["seccomp"] = False
        self.assertIn("GUARDS", api.compare_contract(trace, contract)["data"]["comparison"]["mismatches"])
        bad = dict(contract, version=True)
        self.assertEqual(api.compare_contract(trace, bad)["status"], "REFUSED")

    def test_repeatability_excludes_only_volatile_data(self):
        first, second = self.trace(), self.trace()
        second["correlation_id"] = "ab5e405b7dec4a20b61e20996118238d"
        second["spans"][0].update(utc="2027-02-02T12:34:56Z", monotonic=999.0)
        self.assertEqual(api.verify_repeatability([first, second])["status"], "REPEATABLE")
        for field in ("order", "result", "guard", "exception"):
            changed = copy.deepcopy(second)
            if field == "order": changed["spans"].reverse()
            if field == "result": changed["result_summary"]["state"] = "unknown"
            if field == "guard": changed["sandbox"]["audit"] = False
            if field == "exception": changed["exception"] = {"class": "TimeoutError", "family": "EXCEPTION"}
            with self.subTest(field=field):
                self.assertEqual(api.verify_repeatability([first, changed])["status"], "MISMATCH")

    def test_proposal_never_mutates_or_accepts_contract(self):
        contract = {"schema": "function-extractor.contract/v1", "version": 1, "expected_status": "RAISED"}
        original = copy.deepcopy(contract)
        result = api.propose_contract_update(contract, self.trace())
        self.assertEqual(result["status"], "PROPOSED")
        proposal = result["data"]["proposal"]
        self.assertFalse(proposal["accepted"])
        self.assertFalse(proposal["canonical_registry_mutated"])
        self.assertEqual(contract, original)

    def test_report_never_exports_arguments_or_exception_text(self):
        graph = api.extract_route(self.source, "pricing:total")
        result = api.render_route_report(graph, self.trace())
        self.assertEqual(result["status"], "RENDERED")
        self.assertIn("production acceptance absent", result["data"]["report"])
        bad = self.trace(); bad["exception"] = {"class": "ValueError", "message": "SECRET_RAW_TEXT"}
        refusal = api.render_route_report(graph, bad)
        self.assertEqual(refusal["status"], "REFUSED")
        self.assertNotIn("SECRET_RAW_TEXT", json.dumps(refusal))

    def test_original_resource_and_target_outcome_fields_are_accepted_strictly(self):
        trace = self.trace()
        trace["sandbox"].update(memory_mb=256, max_fds=128, cpu_seconds=5)
        trace["target_outcome"] = {"status": "RETURNED", "result_summary": {"type": "int"}}
        trace["outcome_hook_error"] = {"class": "RuntimeError", "family": "EXCEPTION", "evidence": "SIMULATED"}
        self.assertEqual(api.verify_repeatability([trace, trace])["status"], "REPEATABLE")
        bad = copy.deepcopy(trace); bad["sandbox"]["allow_network"] = True
        self.assertEqual(api.verify_repeatability([bad, trace])["status"], "REFUSED")

    def test_fixed_error_codes_and_no_failure_strings(self):
        with patch.object(api, "_engine", side_effect=RuntimeError("SECRET_RAW_TEXT")):
            result = api.resolve_entry(self.source, "pricing:total")
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["errors"], ["ENGINE_FAILURE"])
        self.assertNotIn("SECRET_RAW_TEXT", json.dumps(result))

    def test_schema_assets_are_versioned_closed_and_parseable(self):
        folder = Path(api.__file__).parent / "contracts"
        schemas = {p.name: json.loads(p.read_bytes()) for p in folder.glob("*.schema.json")}
        self.assertGreaterEqual(len(schemas), 10)
        # Rules, provenance and method catalogs are data, not JSON Schemas.
        # The original core API keeps its closed-root invariant. Later CE
        # combination schemas have their own positive/negative shape tests.
        core = {name + ".schema.json" for name in (
            "boundaries", "cache", "comparison", "contract-proposal", "contract",
            "fault", "fixture", "graph", "json-value", "manifest", "result", "sandbox", "trace")}
        self.assertTrue(core <= schemas.keys())
        for name, schema in schemas.items():
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            if name in core and name != "json-value.schema.json":
                self.assertFalse(schema["additionalProperties"])
        result_schema = schemas["result.schema.json"]
        self.assertEqual(result_schema["properties"]["version"], {"const": 1})
        self.assertEqual(len(result_schema["properties"]["operation"]["enum"]), 12)

    def test_strict_cache_trace_schema_and_typed_comparison_successor(self):
        first = api.extract_route(self.source, "pricing:total")
        self.assertEqual(api.extract_route(self.source, "pricing:total", cache=first)["status"], "CACHED")
        extra = copy.deepcopy(first); extra["data"]["injected"] = "PRIVATE_LITERAL"
        result = api.extract_route(self.source, "pricing:total", cache=extra)
        self.assertEqual(result["status"], "EXTRACTED")
        self.assertNotIn("PRIVATE_LITERAL", json.dumps(result))
        tampered = copy.deepcopy(first); tampered["data"]["graph"]["nodes"][0]["line"] += 100
        fresh = api.extract_route(self.source, "pricing:total", cache=tampered)
        self.assertEqual(fresh["status"], "EXTRACTED")
        self.assertEqual(fresh["data"]["graph"], first["data"]["graph"])
        invalid = copy.deepcopy(first); invalid["data"]["graph"]["nodes"][0]["body"] = "PRIVATE_LITERAL"
        refusal = api.extract_route(self.source, "pricing:total", cache=invalid)
        self.assertEqual(refusal["status"], "REFUSED")
        self.assertNotIn("PRIVATE_LITERAL", json.dumps(refusal))
        trace = self.trace(); trace["result_summary"]["ok"] = False
        contract = {"schema": "function-extractor.contract/v1", "version": 1, "result_summary": {"ok": 0}}
        self.assertEqual(api.compare_contract(trace, contract)["status"], "MISMATCH")
        contract["result_summary"]["ok"] = False
        self.assertEqual(api.compare_contract(trace, contract)["status"], "MATCH")
        blocked = {"schema": "route-probe.trace/v1", "status": "BLOCKED_LIVE_PROOF", "spans": []}
        self.assertEqual(api.propose_contract_update(contract, blocked)["status"], "UNRESOLVED")

    def test_offline_jsonschema_validates_all_twelve_actual_api_outputs(self):
        from jsonschema import Draft202012Validator, RefResolver
        folder = Path(api.__file__).parent / "contracts"
        schemas = {p.name: json.loads(p.read_bytes()) for p in folder.glob("*.schema.json")}
        def no_retrieval(uri):
            raise AssertionError("schema_network_retrieval_forbidden")
        resolver = RefResolver.from_schema(schemas["result.schema.json"],
            store={schema["$id"]: schema for schema in schemas.values() if "$id" in schema},
            handlers={"http": no_retrieval, "https": no_retrieval})
        for schema in schemas.values():
            Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schemas["result.schema.json"], resolver=resolver)
        resolved = api.resolve_entry(self.source, "pricing:total")
        graph = api.extract_route(self.source, "pricing:total")
        frozen = api.freeze_source(self.source, "pricing:total", self.base / "bundle")
        self.assertEqual(frozen["status"], "FROZEN")
        fixture = api.compile_fixture({"args": [4], "expected_result": 9})
        executed = api.execute_route(Path(frozen["data"]["bundle"]), fixture, timeout=5)
        self.assertEqual(executed["status"], "EXECUTED", executed)
        contract = {"schema": "function-extractor.contract/v1", "version": 1, "expected_status": "RETURNED"}
        values = [resolved, graph, frozen, api.discover_boundaries(graph), fixture,
            api.build_sandbox(Path(frozen["data"]["bundle"])), executed,
            api.inject_fault({"case": "success"}, {"kind": "read_timeout", "adapter": "tools.route_probe_avl:prepare"}),
            api.compare_contract(executed, contract), api.render_route_report(graph, executed),
            api.propose_contract_update(contract, executed), api.verify_repeatability([executed, executed])]
        for value in values:
            with self.subTest(operation=value["operation"]):
                validator.validate(value)
        cached = api.extract_route(self.source, "pricing:total", cache=graph)
        self.assertEqual(cached["status"], "CACHED")
        validator.validate(cached)
        bad_result = copy.deepcopy(resolved); bad_result["data"]["extra"] = "not_allowed"
        self.assertTrue(list(validator.iter_errors(bad_result)))
        bad_trace = self.trace(); bad_trace["spans"][0]["line"] = True
        self.assertEqual(api.verify_repeatability([bad_trace, self.trace()])["status"], "REFUSED")

    def test_closed_container_evidence_and_repeatability_boundary(self):
        from jsonschema import Draft202012Validator, RefResolver
        folder = Path(api.__file__).parent / "contracts"
        schemas = {p.name: json.loads(p.read_bytes()) for p in folder.glob("*.schema.json")}
        def no_retrieval(uri):
            raise AssertionError("schema_network_retrieval_forbidden")
        resolver = RefResolver.from_schema(schemas["trace.schema.json"],
            store={s["$id"]: s for s in schemas.values() if "$id" in s}, handlers={"http": no_retrieval, "https": no_retrieval})
        validator = Draft202012Validator(schemas["trace.schema.json"], resolver=resolver)
        first = self.trace()
        first["container"] = {"image_id": "sha256:" + "a"*64, "name": "fe-replay-" + "b"*32,
            "network": "none", "read_only": True, "user": "65534:65534", "cap_drop": ["ALL"],
            "no_new_privileges": True, "memory_mb": 512, "pids_limit": 24, "elapsed_seconds": 1.5,
            "cleanup": "AUTO_REMOVE_ON_EXIT", "client_exit_code": 0, "stderr_bytes_suppressed": 0,
            "capsule_sha256": "c"*64, "authority": {"required": False, "reason": "canonical_ru_route_not_installed"}}
        first["container_effective"] = {"uid": 65534, "gid": 65534, "cap_eff": "0000000000000000",
            "no_new_privs": 1, "seccomp": 2, "interfaces": ["lo"], "root_readonly": True}
        validator.validate(first)
        owned = copy.deepcopy(first)
        owned["container"]["authority"] = {"required": True, "window_id": "e"*32,
            "actor_session": "fixture-actor", "target_scope": "function-extractor:synthetic:" + owned["container"]["image_id"]}
        validator.validate(owned)
        self.assertEqual(api.verify_repeatability([owned, owned])["status"], "REPEATABLE")
        second = copy.deepcopy(first); second["container"]["name"] = "fe-replay-" + "d"*32
        second["container"]["elapsed_seconds"] = 3.5
        self.assertEqual(api.verify_repeatability([first, second])["status"], "REPEATABLE")
        second["container_effective"]["uid"] = 0
        self.assertEqual(api.verify_repeatability([first, second])["status"], "MISMATCH")
        for edit in ("extra", "wrong_scope", "typed_uid", "network"):
            invalid = copy.deepcopy(first)
            if edit == "extra": invalid["container"]["raw_env"] = "SECRET_RAW_TEXT"
            if edit == "wrong_scope": invalid["container"]["authority"] = {"required": True, "window_id": "e"*32,
                "actor_session": "fixture-actor", "target_scope": "foreign"}
            if edit == "typed_uid": invalid["container_effective"]["uid"] = True
            if edit == "network": invalid["container"]["network"] = "host"
            with self.subTest(edit=edit):
                result = api.verify_repeatability([first, invalid])
                self.assertEqual(result["status"], "REFUSED")
                self.assertNotIn("SECRET_RAW_TEXT", json.dumps(result))
                self.assertTrue(list(validator.iter_errors(invalid)))

    def test_optional_manifest_git_source_pin_is_closed_not_runtime_proof(self):
        from jsonschema import Draft202012Validator, RefResolver
        folder = Path(api.__file__).parent / "contracts"
        schemas = {p.name: json.loads(p.read_bytes()) for p in folder.glob("*.schema.json")}
        def no_retrieval(uri):
            raise AssertionError("schema_network_retrieval_forbidden")
        resolver = RefResolver.from_schema(schemas["manifest.schema.json"],
            store={s["$id"]: s for s in schemas.values() if "$id" in s}, handlers={"http": no_retrieval, "https": no_retrieval})
        validator = Draft202012Validator(schemas["manifest.schema.json"], resolver=resolver)
        frozen = api.freeze_source(self.source, "pricing:total", self.base / "bundle")
        self.assertEqual(frozen["status"], "FROZEN")
        manifest = frozen["data"]["manifest"]
        validator.validate(manifest)
        for source_pin in ({"status": "FILE_HASH_ONLY", "commit": None},
            {"status": "GIT_OBJECTS_VERIFIED", "commit": "a"*40, "git_files": ["pricing.py"],
             "file_hash_only_additions": [], "loaded_runtime_proof": False}):
            selected = copy.deepcopy(manifest); selected["source_pin"] = source_pin
            validator.validate(selected)
        for edit in ("runtime_claim", "path", "extra"):
            invalid = copy.deepcopy(selected)
            if edit == "runtime_claim": invalid["source_pin"]["loaded_runtime_proof"] = True
            if edit == "path": invalid["source_pin"]["git_files"] = ["../outside.py"]
            if edit == "extra": invalid["source_pin"]["raw_commit_message"] = "PRIVATE_LITERAL"
            with self.subTest(edit=edit):
                self.assertTrue(list(validator.iter_errors(invalid)))


if __name__ == "__main__":
    unittest.main()
