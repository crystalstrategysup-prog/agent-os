import json
from pathlib import Path
import sys
import tempfile
import unittest

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
