"""New source-only contract engine tests. No product import, provider or DB."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.function_extractor import contract_engine as ce


class ContractEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ce-public-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.route = {"route_id": "route.one", "entry": "sample:run", "graph_sha256": "a" * 64,
                      "source_pins": [{"path": "sample.py", "sha256": "b" * 64}]}

    def source(self, name, document, kind="rules", **kwargs):
        raw = document.encode() if type(document) is str else ce.canonical(document)
        path = self.root / (name + (".py" if kind == "python" else ".md" if kind == "local_doc" else ".json"))
        path.write_bytes(raw)
        return {"source_id": name, "kind": kind, "path": path.name,
                "sha256": hashlib.sha256(raw).hexdigest(), **kwargs}

    def declared(self, state="sent", *, boundary="send", rule_id=None):
        rule = {"boundary_id": boundary, "kind": "delivery_state", "constraint": {"state": state}}
        if rule_id:
            rule["rule_id"] = rule_id
        return {"schema": "function-extractor.rule-declarations/v1", "rules": [rule]}

    def revision(self, sources, level="APPROVED_INTERNAL"):
        return {"id": "rev-one", "source_root": str(self.root), "authority_bindings": [
            {"source_id": x["source_id"], "sha256": x["sha256"], "provenance": level,
             "authority_ref": "explicit-caller-reviewed-snapshot"} for x in sources]}

    def resolve(self, sources, revision=None):
        return ce.resolve_contracts(self.route, sources, revision or self.revision(sources))

    def official(self, source):
        return {**source, "metadata": {"retrieved_at": "2026-10-22T01:00:00Z", "version": "pinned-v1",
            "primary_ref": "https://core.telegram.org/bots/api", "primary_sha256": "c" * 64,
            "official_schema": False, "machine_adapter": True}}

    def test_deterministic_explicit_rules_digest_and_declared_ids(self):
        a = self.source("a", self.declared(rule_id="send.state"))
        b = self.source("b", self.declared(boundary="other"))
        first = self.resolve([a, b]); second = self.resolve([b, a])
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "RESOLVED")
        self.assertEqual(ce.validate_contract_map(first)["status"], "VALID")
        self.assertEqual(first["content_digest"], ce.content_digest(first))
        self.assertIn("send.state", {x["rule_id"] for x in first["rules"]})

    def test_self_label_does_not_promote_authority(self):
        a = self.source("a", self.declared(), provenance="OFFICIAL", authority_ref="filename-says-official")
        r = self.resolve([a], {"id": "revision", "source_root": str(self.root), "authority_bindings": []})
        self.assertEqual(r["status"], "PARTIAL")
        self.assertEqual(r["sources"][0]["provenance"], "UNSPECIFIED")
        self.assertEqual(r["rules"][0]["provenance"], "UNSPECIFIED")
        self.assertEqual(ce.validate_contract_map(r)["status"], "VALID")

    def test_official_primary_metadata_retained_not_official_machine_schema(self):
        a = self.official(self.source("a", self.declared()))
        r = self.resolve([a], self.revision([a], "OFFICIAL"))
        self.assertEqual(r["status"], "RESOLVED")
        self.assertEqual(r["sources"][0]["metadata"], a["metadata"])
        self.assertFalse(r["sources"][0]["metadata"]["official_schema"])
        self.assertTrue(r["sources"][0]["metadata"]["machine_adapter"])
        self.assertEqual(ce.validate_contract_map(r)["status"], "VALID")
        b = self.source("b", self.declared())
        self.assertEqual(self.resolve([b], self.revision([b], "OFFICIAL"))["status"], "REFUSED")

    def test_bad_trust_label_and_mismatched_authority_hash_refuse(self):
        a = self.source("a", self.declared())
        for mutation in ("provenance", "sha256", "source_id"):
            rev = self.revision([a]);rev["authority_bindings"][0][mutation] = {"provenance": "TRUST_ME", "sha256": "f" * 64, "source_id": "unresolved"}[mutation]
            with self.subTest(mutation=mutation):
                self.assertEqual(self.resolve([a], rev)["status"], "REFUSED")

    def test_competing_normative_rules_preserved_without_winner_rewrite(self):
        a = self.official(self.source("a", self.declared("sent")))
        b = self.official(self.source("b", self.declared("unknown")))
        r = self.resolve([a, b], self.revision([a, b], "OFFICIAL"))
        self.assertEqual(r["status"], "PARTIAL")
        self.assertEqual({x["constraint"]["state"] for x in r["rules"]}, {"sent", "unknown"})
        self.assertTrue(all(len(x["conflicts"]) == 1 for x in r["rules"]))
        self.assertIn("NORMATIVE_RULES_COMPETE", {x["code"] for x in r["unresolved"]})
        self.assertEqual(ce.validate_contract_map(r)["status"], "VALID")

    def test_observed_difference_does_not_override_official_expected(self):
        a = self.official(self.source("a", self.declared("sent")))
        b = self.source("b", self.declared("unknown"))
        revision = self.revision([a], "OFFICIAL")
        revision["authority_bindings"] += self.revision([b], "OBSERVED")["authority_bindings"]
        r = self.resolve([a, b], revision)
        self.assertEqual([(x["provenance"], x["constraint"]["state"]) for x in sorted(r["rules"], key=lambda x: x["source_id"])], [("OFFICIAL", "sent"), ("OBSERVED", "unknown")])
        self.assertIn("OBSERVED_OR_UNSPECIFIED_DIFFERENCE", {x["code"] for x in r["unresolved"]})

    def test_selected_digest_excludes_unrelated_rules_but_tracks_conflict_sources(self):
        a = self.source("a", self.declared("sent", rule_id="primary"))
        first = self.resolve([a]); digest = ce.selected_rule_digest(first, ["primary"])
        b = self.source("b", self.declared("failed", boundary="other"))
        other = self.resolve([a, b]); self.assertEqual(digest, ce.selected_rule_digest(other, ["primary"]))
        c = self.source("c", self.declared("unknown"))
        competing = self.resolve([a, c]); self.assertNotEqual(digest, ce.selected_rule_digest(competing, ["primary"]))
        with self.assertRaises(ValueError):
            ce.selected_rule_digest(first, ["missing"])

    def test_changed_selected_snapshot_invalidates_even_same_rule_text(self):
        a = self.source("a", self.declared(rule_id="primary")); r = self.resolve([a])
        (self.root / a["path"]).write_bytes((self.root / a["path"]).read_bytes() + b"\n")
        self.assertEqual(self.resolve([a])["status"], "REFUSED")
        a["sha256"] = hashlib.sha256((self.root / a["path"]).read_bytes()).hexdigest()
        self.assertNotEqual(ce.selected_rule_digest(r, ["primary"]), ce.selected_rule_digest(self.resolve([a]), ["primary"]))

    def test_escaping_symlink_secret_hardlink_and_root_alias_refuse(self):
        a = self.source("a", self.declared())
        for path in ("../outside.json", "/tmp/public.json", ".env", "secrets/a.json", "sub/../a.json"):
            with self.subTest(path=path):
                self.assertEqual(self.resolve([{**a, "path": path}])["status"], "REFUSED")
        alias = self.root / "alias.json";alias.symlink_to(self.root / a["path"])
        self.assertEqual(self.resolve([{**a, "path": alias.name}])["status"], "REFUSED")
        alias.unlink();os.link(self.root / a["path"], alias)
        self.assertEqual(self.resolve([a])["status"], "REFUSED")
        alias.unlink()
        root_alias = self.root / "rootlink";root_alias.symlink_to(self.root, target_is_directory=True)
        rev = self.revision([a]);rev["source_root"] = str(root_alias)
        self.assertEqual(self.resolve([a], rev)["status"], "REFUSED")

    def test_descriptor_and_source_caps_refuse_without_echoing_error(self):
        a = self.source("a", self.declared())
        self.assertEqual(self.resolve([a] * 17)["status"], "REFUSED")
        (self.root / a["path"]).write_bytes(b" " * 524289)
        r = self.resolve([a]);self.assertEqual(r["status"], "REFUSED")
        self.assertNotIn("Traceback", json.dumps(r));self.assertNotIn(str(self.root), json.dumps(r))

    def test_json_schema_local_reference_and_strict_types(self):
        s = {"$defs": {"number": {"type": "integer", "minimum": 1, "maximum": 10}},
             "type": "object", "properties": {"count": {"$ref": "#/$defs/number"}}, "required": ["count"], "additionalProperties": False}
        for value, expected in (({"count": 2}, "VALID"), ({"count": True}, "INVALID"), ({"count": 0}, "INVALID"), ({}, "INVALID"), ({"count": 2, "extra": 1}, "INVALID")):
            with self.subTest(value=value):self.assertEqual(ce.validate_schema(value, s)["status"], expected)

    def test_unsupported_external_refs_regex_composition_and_cycles_unknown(self):
        cases = [{"$ref": "https://example.invalid/schema.json"}, {"pattern": "(a+)+$"}, {"anyOf": [{"type": "string"}]},
                 {"$defs": {"loop": {"$ref": "#/$defs/loop"}}, "$ref": "#/$defs/loop"}, {"$ref": "#/missing"}, {"format": "email"}, {"type": "object", "default": {"x": 1}, "customCode": "print('never')"}]
        for schema in cases:
            with self.subTest(schema=schema):self.assertEqual(ce.validate_schema("aaaa", schema)["status"], "UNKNOWN")

    def test_deep_large_nonfinite_and_nonjson_schema_inputs_unknown(self):
        s = {"type": "string"}
        for _ in range(25):s = {"type": "array", "items": s}
        for value, schema in ((None, s), (float("nan"), {}), ("x" * 524289, {}), (object(), {}), (None, {"minimum": True})):
            with self.subTest(case=type(value).__name__):self.assertEqual(ce.validate_schema(value, schema)["status"], "UNKNOWN")

    def test_schema_adapter_keeps_unsupported_rule_gap(self):
        a = self.source("schema", {"type": "string", "pattern": "(a+)+$"}, kind="json_schema")
        r = self.resolve([a]);self.assertEqual(r["status"], "PARTIAL")
        self.assertIn("SCHEMA_UNSUPPORTED", {x["code"] for x in r["unresolved"]})
        self.assertEqual(ce.validate_schema("x", r["rules"][0]["constraint"])["status"], "UNKNOWN")

    def test_python_annotations_are_source_observed_never_execute_module(self):
        code = "raise RuntimeError('DO NOT EXECUTE')\nclass Service:\n    def run(self, count: int, note: str = 'x') -> bool:\n        return count > 0\n"
        a = self.official(self.source("code", code, kind="python", selector={"symbol": "Service.run"}))
        r = self.resolve([a], self.revision([a], "OFFICIAL"))
        self.assertEqual(r["status"], "RESOLVED")
        self.assertEqual({x["provenance"] for x in r["rules"]}, {"OBSERVED"})
        input_rule = next(x for x in r["rules"] if x["kind"] == "input_schema")
        self.assertEqual(ce.validate_schema({"count": 1}, input_rule["constraint"])["status"], "VALID")
        self.assertEqual(ce.validate_schema({"count": "x"}, input_rule["constraint"])["status"], "INVALID")

    def test_python_missing_annotations_remain_gap_not_fabricated_schema(self):
        a = self.source("code", "def run(value):\n return value\n", kind="python")
        r = self.resolve([a]);self.assertEqual(r["status"], "PARTIAL");self.assertEqual(r["rules"], [])
        self.assertIn("PYTHON_ANNOTATION_UNSPECIFIED", {x["code"] for x in r["unresolved"]})

    def test_openapi_local_refs_and_selected_operation_only(self):
        doc = {"openapi": "3.1.0", "components": {"schemas": {"Request": {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}}}, "paths": {"/send": {"post": {
            "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Request"}}}},
            "responses": {"200": {"content": {"application/json": {"schema": {"type": "boolean"}}}}}}}}}
        a = self.source("http", doc, kind="openapi", selector={"path": "/send", "method": "post"})
        r = self.resolve([a]);self.assertEqual(r["status"], "RESOLVED");self.assertEqual(len(r["rules"]), 2)
        doc["paths"]["/send"]["post"]["requestBody"]["content"]["application/json"]["schema"] = {"$ref": "https://example.invalid/remote"}
        a = self.source("http", doc, kind="openapi", selector={"path": "/send", "method": "post"})
        r = self.resolve([a]);self.assertEqual(r["status"], "PARTIAL");self.assertEqual(len(r["rules"]), 1)

    def test_local_doc_only_explicit_json_rule_blocks_not_natural_language(self):
        a = self.source("doc", "Always retry until delivered.\n", kind="local_doc")
        r = self.resolve([a]);self.assertEqual(r["status"], "PARTIAL");self.assertFalse(r["rules"])
        a = self.source("doc", "# Public contract\n```contract-rules\n" + json.dumps(self.declared("unknown")) + "\n```\n", kind="local_doc")
        self.assertEqual(self.resolve([a])["status"], "RESOLVED")

    def test_duplicate_rule_id_and_unknown_boundary_refuse(self):
        a = self.source("a", self.declared("sent", rule_id="same"));b = self.source("b", self.declared("failed", rule_id="same"))
        self.assertEqual(self.resolve([a, b])["status"], "REFUSED")
        a = self.source("a", {"boundaries": [], "rules": [{"boundary_id": "absent", "kind": "no_retry", "constraint": {"enabled": True}}]})
        self.assertEqual(self.resolve([a])["status"], "REFUSED")

    def test_map_digest_references_and_hidden_conflict_tamper_refuse(self):
        a = self.source("a", self.declared("sent"));b = self.source("b", self.declared("failed"));m = self.resolve([a, b])
        for kind in ("digest", "source", "boundary", "conflict", "provenance", "extra"):
            bad = copy.deepcopy(m)
            if kind == "digest":bad["content_digest"] = "0" * 64
            elif kind == "source":bad["rules"][0]["source_id"] = "missing"
            elif kind == "boundary":bad["rules"][0]["boundary_id"] = "missing"
            elif kind == "conflict":
                for x in bad["rules"]:x["conflicts"] = []
            elif kind == "provenance":bad["rules"][0]["provenance"] = "OFFICIAL"
            else:bad["canonical_accepted"] = True
            if kind != "digest":bad["content_digest"] = ce.content_digest(bad)
            with self.subTest(kind=kind):self.assertEqual(ce.validate_contract_map(bad)["status"], "INVALID")

    def test_all_rule_kinds_preserve_constraints_without_inference(self):
        doc = self.declared();doc["rules"] = [{"boundary_id": "send", "kind": kind, "constraint": {"type": "object"} if kind.endswith("schema") else {"declared": True}} for kind in ce.RULE_KINDS]
        r = self.resolve([self.source("a", doc)])
        self.assertEqual(r["status"], "RESOLVED");self.assertEqual({x["kind"] for x in r["rules"]}, set(ce.RULE_KINDS))

    def test_new_ce_schemas_validate_only_new_actual_instances_offline(self):
        from jsonschema import Draft202012Validator, ValidationError
        directory = Path(__file__).resolve().parents[1] / "contracts"
        a = self.official(self.source("a", self.declared()))
        revision = self.revision([a], "OFFICIAL")
        result = self.resolve([a], revision)
        values = {"ce_contract_map.schema.json": result,
            "ce_resolution_input.schema.json": {"schema": "function-extractor.contract-resolution/v1", "version": 1, "route": self.route, "sources": [a], "revision": revision},
            "ce_schema_validation.schema.json": ce.validate_schema(True, {"type": "boolean"})}
        for name, value in values.items():
            schema = json.loads((directory / name).read_text())
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            validator.validate(value)
            with self.subTest(schema=name), self.assertRaises(ValidationError):
                validator.validate({**value, "unrecognized_authority": True})

    def test_secret_extensions_refuse_and_enum_value_encoded_once(self):
        a = self.source("a", self.declared())
        for name in ("credentials.json", "secrets.txt", "session_token.json", "backup-2026/rules.json", "id_rsa.pub"):
            with self.subTest(path=name):
                # The path is refused before any attempt to open its leaf.
                with patch.object(ce.os, "open", side_effect=AssertionError("must not open")):
                    self.assertEqual(self.resolve([{**a, "path": name}])["status"], "REFUSED")
        value = "public-value" * 1000
        original = ce.canonical
        count = [0]
        def observed(item):
            if type(item) is str and item == value:
                count[0] += 1
            return original(item)
        with patch.object(ce, "canonical", side_effect=observed):
            result = ce.validate_schema(value, {"enum": ["alternative-" + str(i) for i in range(1000)]})
        self.assertEqual(result["status"], "INVALID")
        self.assertEqual(count[0], 2)  # input budget encoding + single comparison encoding

    def test_numeric_schema_semantics_preserve_boolean_distinction(self):
        checks = [(1.0, {"type": "integer"}, "VALID"), (1.5, {"type": "integer"}, "INVALID"),
            (True, {"type": "integer"}, "INVALID"), (1, {"const": 1.0}, "VALID"),
            (1.0, {"enum": [1]}, "VALID"), (True, {"enum": [1]}, "INVALID"),
            (False, {"const": 0.0}, "INVALID"), ({"n": [1.0, -0.0]}, {"const": {"n": [1, 0]}}, "VALID"),
            ({"n": True}, {"enum": [{"n": 1}]}, "INVALID"),
            ([1, 1.0], {"type": "array", "uniqueItems": True}, "INVALID"),
            ([1, True], {"type": "array", "uniqueItems": True}, "VALID"),
            (9007199254740993, {"const": 9007199254740992.0}, "INVALID"),
            (float("inf"), {"type": "integer"}, "UNKNOWN")]
        for value, schema, expected in checks:
            with self.subTest(value=value, schema=schema):
                self.assertEqual(ce.validate_schema(value, schema)["status"], expected)


if __name__ == "__main__":
    unittest.main()
