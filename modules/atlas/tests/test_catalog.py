import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/atlas/scripts"))
import catalog
import navigator as nav


class CatalogTests(unittest.TestCase):
    def test_openapi_inheritance_body_and_security_are_source_declarations(self):
        source = {"openapi": "3.1.0", "info": {"version": "7"}, "security": [{"scope": []}], "components": {"parameters": {"ID": {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}}},
                  "paths": {"/items/{id}": {"parameters": [{"$ref": "#/components/parameters/ID"}], "patch": {"tags": ["Items"], "security": [], "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}], "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"200": {"description": "Result"}, "404": {"description": "Missing"}}}}}}
        result = catalog.from_openapi(source, "DOC-API", "api.json")
        record = result["contracts"][0]
        self.assertEqual(len(result["contracts"]), 1)
        self.assertEqual(len(record["parameters"]), 2)
        self.assertEqual(record["parameters"][0]["type"], '{"type":"integer"}')
        self.assertIs(record["parameters"][1]["required"], True)
        self.assertIn("Explicit empty", record["auth"])
        self.assertEqual(record["errors"], [{"code": "404", "meaning": '{"description":"Missing"}'}])
        self.assertEqual(record["execution"], "NOT_RUN")
        self.assertIn("UNKNOWN", result["modules"][0]["state_owner"])

    def test_external_reference_is_not_fetched_or_interpreted_as_optional(self):
        source = {"openapi": "3.0.0", "paths": {"/x": {"get": {"parameters": [{"$ref": "https://example.invalid/private.json#/x"}], "responses": {"200": {"description": "OK"}}}}}}
        record = catalog.from_openapi(source, "DOC-API", "api.json")["contracts"][0]
        self.assertEqual(record["parameters"][0]["required"], "UNKNOWN")
        self.assertIn("UNKNOWN", record["parameters"][0]["type"])
        self.assertIn("https://example.invalid", record["input"])

    def test_unresolved_request_body_keeps_unknown_requiredness(self):
        for reference in ("external.json#/Body", "#/components/requestBodies/Missing"):
            with self.subTest(reference=reference):
                source = {"openapi": "3.1.1", "paths": {"/x": {"post": {
                    "requestBody": {"$ref": reference}, "responses": {"200": {"description": "OK"}}}}}}
                with mock.patch("builtins.open", side_effect=AssertionError("No external reference reads")):
                    record = catalog.from_openapi(source, "DOC-API", "api.json")["contracts"][0]
                self.assertEqual(record["parameters"][0]["required"], "UNKNOWN")
                self.assertIn(reference, record["input"])
                self.assertEqual(record["execution"], "NOT_RUN")

    def test_distinct_unknown_parameters_survive_known_override(self):
        first, second = {"$ref": "external.json#/A"}, {"$ref": "external.json#/B"}
        source = {"openapi": "3.1.0", "paths": {"/x": {
            "parameters": [first, {"name": "id", "in": "query", "schema": {"type": "string"}}],
            "get": {"parameters": [second, {"name": "id", "in": "query", "schema": {"type": "integer"}}],
                    "responses": {"200": {"description": "OK"}}}}}}
        record = catalog.from_openapi(source, "DOC-API", "api.json")["contracts"][0]
        values = json.loads(record["input"])["parameters"]
        self.assertEqual([p["$ref"] for p in values if "$ref" in p], [first["$ref"], second["$ref"]])
        self.assertEqual(len(values), 3)
        self.assertEqual(next(p for p in values if "name" in p)["schema"], {"type": "integer"})
        self.assertEqual([p["required"] for p in record["parameters"] if p["name"] == "UNKNOWN"], ["UNKNOWN", "UNKNOWN"])

    def test_local_path_item_reference_enumerates_actual_operations(self):
        operation = {"responses": {"200": {"description": "OK"}}}
        source = {"openapi": "3.1.0", "components": {"pathItems": {"Shared": {"get": operation}}},
                  "paths": {"/first": {"$ref": "#/components/pathItems/Shared"},
                            "/second": {"$ref": "#/components/pathItems/Shared", "post": operation}}}
        before = catalog.compact(source)
        result = catalog.from_openapi(source, "DOC-API", "api.json")
        self.assertEqual([c["title"].split(" · ")[0] for c in result["contracts"]], ["GET /first", "GET /second", "POST /second"])
        self.assertIn("api.json#/components/pathItems/Shared/get", result["contracts"][0]["usage"])
        self.assertIn("api.json#/paths/~1second/post", result["contracts"][2]["usage"])
        self.assertTrue(all(c["execution"] == "NOT_RUN" for c in result["contracts"]))
        self.assertEqual(catalog.compact(source), before)

    def test_unresolved_or_ambiguous_path_items_are_explicit_refusals(self):
        operation = {"responses": {"200": {"description": "OK"}}}
        for path_item, components, expected in (
            ({"$ref": "https://example.invalid/path.json"}, {}, "OPENAPI_PATH_ITEM_REF_UNRESOLVED"),
            ({"$ref": "#/components/pathItems/A"}, {"pathItems": {"A": {"$ref": "#/components/pathItems/A"}}}, "OPENAPI_PATH_ITEM_REF_UNRESOLVED"),
            ({"$ref": "#/components/pathItems/A", "get": operation}, {"pathItems": {"A": {"get": operation}}}, "OPENAPI_PATH_ITEM_REF_CONFLICT"),
        ):
            with self.subTest(path_item=path_item):
                with self.assertRaisesRegex(nav.Invalid, expected):
                    catalog.from_openapi({"openapi": "3.1.0", "paths": {"/x": path_item}, "components": components}, "DOC-API", "api.json")

    def test_error_ranges_are_retained_with_specific_responses(self):
        source = {"openapi": "3.0.3", "paths": {"/x": {"get": {"responses": {
            "2XX": {"description": "Success"}, "4XX": {"description": "Client error"},
            "404": {"description": "Not found"}, "5XX": {"description": "Server error"},
            "default": {"description": "Other response"}}}}}}
        record = catalog.from_openapi(source, "DOC-API", "api.json")["contracts"][0]
        self.assertEqual([error["code"] for error in record["errors"]], ["4XX", "404", "5XX", "default"])
        self.assertIn('"2XX"', record["output"])

    def test_boolean_and_empty_parameter_schemas_remain_declared(self):
        for schema in (False, True, {}):
            with self.subTest(schema=schema):
                source = {"openapi": "3.1.0", "paths": {"/x": {"get": {
                    "parameters": [{"name": "x", "in": "query", "schema": schema}],
                    "responses": {"200": {"description": "OK"}}}}}}
                record = catalog.from_openapi(source, "DOC-API", "api.json")["contracts"][0]
                self.assertEqual(record["parameters"][0]["type"], json.dumps(schema, separators=(",", ":")))

    def test_local_reference_chain_preserves_body_requiredness(self):
        source = {"openapi": "3.1.1", "components": {"requestBodies": {
            "First": {"$ref": "#/components/requestBodies/Second"},
            "Second": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}}},
            "paths": {"/x": {"post": {"requestBody": {"$ref": "#/components/requestBodies/First"},
                                       "responses": {"200": {"description": "OK"}}}}}}
        record = catalog.from_openapi(source, "DOC-API", "api.json")["contracts"][0]
        self.assertIs(record["parameters"][0]["required"], True)

    def test_local_reference_resolution_has_a_fixed_hop_limit(self):
        for hops in (64, 65):
            with self.subTest(hops=hops):
                bodies = {str(i): {"$ref": "#/components/requestBodies/" + str(i + 1)} for i in range(hops - 1)}
                bodies[str(hops - 1)] = {"required": True, "content": {"application/json": {"schema": {}}}}
                operation = {"requestBody": {"$ref": "#/components/requestBodies/0"}, "responses": {"200": {"description": "OK"}}}
                source = {"openapi": "3.1.0", "components": {"requestBodies": bodies}, "paths": {"/x": {"post": operation}}}
                record = catalog.from_openapi(source, "DOC-API", "api.json")["contracts"][0]
                self.assertEqual(record["parameters"][0]["required"], True if hops == 64 else "UNKNOWN")
                if hops == 65:
                    self.assertIn("#/components/requestBodies/0", record["input"])
                path_items = {str(i): {"$ref": "#/components/pathItems/" + str(i + 1)} for i in range(hops - 1)}
                path_items[str(hops - 1)] = {"get": {"responses": {"200": {"description": "OK"}}}}
                source = {"openapi": "3.1.0", "components": {"pathItems": path_items},
                          "paths": {"/x": {"$ref": "#/components/pathItems/0"}}}
                if hops == 64:
                    self.assertEqual(len(catalog.from_openapi(source, "DOC-API", "api.json")["contracts"]), 1)
                else:
                    with self.assertRaisesRegex(nav.Invalid, "OPENAPI_PATH_ITEM_REF_UNRESOLVED"):
                        catalog.from_openapi(source, "DOC-API", "api.json")

    def test_pointer_escaping_and_cyclic_body_references_preserve_source(self):
        reference = "#/components/parameters/a~1b~0%20c"
        source = {"openapi": "3.1.0", "components": {
            "parameters": {"a/b~ c": {"name": "limit", "in": "query", "schema": False}},
            "requestBodies": {"A": {"$ref": "#/components/requestBodies/B"}, "B": {"$ref": "#/components/requestBodies/A"}}},
            "paths": {"/x": {"post": {"parameters": [{"$ref": reference}],
                "requestBody": {"$ref": "#/components/requestBodies/A"}, "responses": {"200": {"description": "OK"}}}}}}
        record = catalog.from_openapi(source, "DOC-API", "api.json")["contracts"][0]
        self.assertEqual(record["parameters"][0]["name"], "limit")
        self.assertEqual(record["parameters"][0]["type"], "false")
        self.assertEqual(record["parameters"][1]["required"], "UNKNOWN")
        self.assertEqual(json.loads(record["input"])["requestBody"], {"$ref": "#/components/requestBodies/A"})

    def test_reference_descriptions_follow_version_and_nearest_override(self):
        schema = {"$ref": "#/components/schemas/Text", "description": "Schema annotation", "minLength": 2}
        for version in ("3.0.3", "3.1.1"):
            for outer in (False, True):
                with self.subTest(version=version, outer=outer):
                    components = {"schemas": {"Text": {"type": "string", "description": "Shared schema"}}}
                    references = {}
                    definitions = {
                        "parameters": {"name": "limit", "in": "query", "required": False, "schema": schema},
                        "requestBodies": {"required": False, "content": {"application/json": {"schema": schema}}},
                        "responses": {"content": {"application/json": {"schema": schema}}},
                    }
                    for kind, definition in definitions.items():
                        components[kind] = {
                            "Base": {**definition, "description": "Base " + kind},
                            "Middle": {"$ref": "#/components/" + kind + "/Base", "description": "Middle " + kind},
                        }
                        references[kind] = {"$ref": "#/components/" + kind + "/Middle",
                            "required": True, "summary": "Ignored for these object types", "schema": False}
                        if outer:
                            references[kind]["description"] = "Outer " + kind
                    source = {"openapi": version, "components": components, "paths": {"/x": {"post": {
                        "parameters": [references["parameters"]], "requestBody": references["requestBodies"],
                        "responses": {"4XX": references["responses"]}}}}}
                    before = catalog.compact(source)
                    record = catalog.from_openapi(source, "DOC-API", "api.json")["contracts"][0]
                    inputs = json.loads(record["input"])
                    meaning = json.loads(record["errors"][0]["meaning"])
                    prefix = ("Outer " if outer else "Middle ") if version.startswith("3.1.") else "Base "
                    self.assertEqual(inputs["parameters"][0]["description"], prefix + "parameters")
                    self.assertEqual(record["parameters"][0]["description"], "location=query; " + prefix + "parameters")
                    self.assertEqual(inputs["requestBody"]["description"], prefix + "requestBodies")
                    self.assertEqual(record["parameters"][1]["description"], prefix + "requestBodies")
                    self.assertEqual(meaning["description"], prefix + "responses")
                    # Reference Object siblings cannot replace arbitrary fields or
                    # apply Reference Object rules to a nested Schema Object.
                    self.assertIs(record["parameters"][0]["required"], False)
                    self.assertIs(record["parameters"][1]["required"], False)
                    self.assertEqual(json.loads(record["parameters"][0]["type"]), schema)
                    self.assertEqual(inputs["requestBody"]["content"]["application/json"]["schema"], schema)
                    self.assertEqual(meaning["content"]["application/json"]["schema"], schema)
                    self.assertNotIn("summary", inputs["parameters"][0])
                    self.assertNotIn("required", meaning)
                    self.assertEqual(catalog.compact(source), before)

    def test_unsupported_versions_are_not_reported_as_compiled(self):
        for version in ("2.0", "3.2.0", "4.0.0", "garbage", None):
            with self.subTest(version=version):
                with self.assertRaisesRegex(nav.Invalid, "OPENAPI_VERSION_UNSUPPORTED"):
                    catalog.from_openapi({"openapi": version, "paths": {}}, "DOC-API", "api.json")
        with self.assertRaisesRegex(nav.Invalid, "OPENAPI_SOURCE_REQUIRED"):
            catalog.from_openapi({"swagger": "2.0", "paths": {}}, "DOC-API", "api.json")

    def test_cli_reads_only_selected_source_and_reports_unsupported_versions(self):
        source = {"openapi": "3.1.1", "servers": [{"url": "http://127.0.0.1:1/never-connect"}],
                  "paths": {"/x": {"post": {"requestBody": {"$ref": "external.json#/Body"},
                      "responses": {"4XX": {"description": "Client error"}}}}}}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            spec = {"schema": "atlas.catalog-source/v1", "format": "openapi", "path": "api.json", "document_id": "DOC-API"}
            (root / "source.json").write_text(json.dumps(spec))
            for version, expected_status in (("3.1.1", 0), ("2.0", 1)):
                with self.subTest(version=version):
                    source["openapi"] = version
                    (root / "api.json").write_text(json.dumps(source))
                    before = {path.name: path.read_bytes() for path in root.iterdir()}
                    result = subprocess.run([sys.executable, "-B", str(Path(catalog.__file__).resolve()),
                        "--root", str(root), "--source", "source.json"], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, expected_status, result.stderr)
                    self.assertEqual(result.stderr, "")
                    output = json.loads(result.stdout)
                    if expected_status == 0:
                        record = output["contracts"][0]
                        self.assertEqual(record["parameters"][0]["required"], "UNKNOWN")
                        self.assertEqual(record["errors"][0]["code"], "4XX")
                        self.assertEqual(record["execution"], "NOT_RUN")
                    else:
                        self.assertEqual(output, {"status": "REFUSED", "code": "OPENAPI_VERSION_UNSUPPORTED"})
                    self.assertEqual({path.name: path.read_bytes() for path in root.iterdir()}, before)

    def test_record_unknowns_and_signature_requiredness_are_preserved(self):
        source = {"contracts": [{"id": "C1", "title": "receive", "component": "Inbox", "execution_status": "NOT_RUN", "authorization": {"state": "unknown", "reason": "No authority review"},
                  "parameters": [{"state": "known", "value": {"individual_parameters": [{"name": "item", "annotation": "str | None", "required_by_signature": True}]}}], "results": [{"state": "unknown", "reason": "Not inspected"}]}]}
        record = catalog.from_records(source, "DOC-API", "catalog.json")["contracts"][0]
        self.assertIs(record["parameters"][0]["required"], True)
        self.assertIn("No authority review", record["auth"])
        self.assertIn("Not inspected", record["output"])
        self.assertEqual(record["execution"], "NOT_RUN")

    def test_text_operation_inputs_are_retained_without_invented_parameters(self):
        source = {"operations": [{"id": "receive", "inputs": ["exact source prose"], "entry": "receive(value)"}], "workers": [{"module": "inbox.worker", "entry": "python -m inbox.worker", "inputs": "read configured source"}]}
        result = catalog.from_operations(source, "DOC-API", "operations.json")
        self.assertEqual(len(result["contracts"]), 2)
        self.assertIn("exact source prose", result["contracts"][0]["input"])
        self.assertEqual(result["contracts"][0]["parameters"], [])
        self.assertTrue(all(c["execution"] == "NOT_RUN" for c in result["contracts"]))

    def test_selected_source_does_not_allow_path_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            spec = {"schema": "atlas.catalog-source/v1", "format": "openapi", "path": "../outside.json", "document_id": "DOC-API"}
            with self.assertRaises(nav.Invalid):
                catalog.compile_catalog(Path(folder), spec)


if __name__ == "__main__":
    unittest.main()
