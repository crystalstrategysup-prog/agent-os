"""Meaningful checks against the shipped portable microscope, not a test copy."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

RESOURCE = Path(__file__).resolve().parents[1] / "src/agent_os/resources/skills/crystal-microscope"
SPEC = importlib.util.spec_from_file_location("shipped_crystal_microscope", RESOURCE / "scripts/microscope.py")
assert SPEC and SPEC.loader
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


@pytest.fixture
def example():
    return json.loads((RESOURCE / "references/example.json").read_text())


def encoded(document):
    return json.dumps(document, ensure_ascii=False, indent=2).encode()


def test_synthetic_example_is_structurally_valid_not_truth(example, tmp_path, capsys):
    source = tmp_path / "map.json"
    source.write_bytes(encoded(example))
    assert TOOL.main(["validate", str(source)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["structural_valid"] is True
    assert report["claims_verified"] is False
    assert "no system or profiler was run" in example["metadata"]["environment"]


@pytest.mark.parametrize("section,field,value", [
    ("nodes", "parent", "missing-node"),
    ("nodes", "evidence", ["missing-evidence"]),
    ("edges", "to", "missing-node"),
    ("evidence", "run", "missing-run"),
    ("metrics", "run", "missing-run"),
    ("metrics", "node", "missing-node"),
])
def test_broken_references_are_rejected(example, section, field, value):
    example[section][0][field] = value
    assert any("unknown" in e for e in TOOL.validate(example))


def test_containment_cycle_rejected_but_wait_cycle_retained(example):
    example["nodes"][0]["parent"] = "worker"
    assert any("parent cycle" in e for e in TOOL.validate(example))
    example["nodes"][0]["parent"] = None
    example["edges"].append({"id": "reverse-wait", "from": "dependency", "to": "worker", "kind": "wait", "status": "hypothesis", "evidence": []})
    assert TOOL.validate(example) == []
    assert TOOL.extract_payload(TOOL.render_html(encoded(example))) == encoded(example)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_nonfinite_values_rejected_in_extensions(example, token):
    raw = encoded(example).rstrip()[:-1] + b', "x_bad": ' + token.encode() + b'}'
    with pytest.raises(TOOL.DocumentError, match="finite"):
        TOOL.parse_document(raw)


def test_duplicate_json_key_is_not_silently_overwritten():
    with pytest.raises(TOOL.DocumentError, match="Duplicate"):
        TOOL.parse_document(b'{"x": 0, "x": 1}')


def test_static_reference_cannot_establish_runtime_or_experiment(example):
    example["nodes"][1]["status"] = "runtime"
    assert any("source alone is insufficient" in e for e in TOOL.validate(example))
    example["nodes"][1]["status"] = "experiment"
    assert any("experiment claims need experiment evidence" in e for e in TOOL.validate(example))


@pytest.mark.parametrize("section,field,value", [
    ("nodes", "status", {}),
    ("evidence", "kind", []),
])
def test_unhashable_classifications_report_errors_not_tracebacks(example, section, field, value, tmp_path, capsys):
    example[section][0][field] = value
    source = tmp_path / "invalid-classification.json"
    source.write_bytes(encoded(example))
    assert TOOL.main(["validate", str(source)]) == 2
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["structural_valid"] is False
    assert any(f"{section}.{example[section][0]['id']}.{field}: expected one of" in error
               for error in report["errors"])
    assert "Traceback" not in output.err


def test_null_metric_checks_supplied_references_and_claim_status(example):
    metric = example["metrics"][1]
    metric.update(status="runtime", run="missing-run", evidence=["missing-evidence"])
    errors = TOOL.validate(example)
    assert any("metrics.dependency-latency.run: unknown runs ID" in error for error in errors)
    assert any("metrics.dependency-latency.evidence[0]: unknown evidence ID" in error for error in errors)
    assert any("null measurements require unknown status" in error for error in errors)

    metric.update(run="illustration", evidence=["design"])
    assert any("runtime claims need runtime or experiment evidence" in error
               for error in TOOL.validate(example))
    metric["status"] = "unknown"
    assert TOOL.validate(example) == []


def test_runtime_zero_and_unknown_remain_valid_with_existing_provenance(example):
    example["metrics"][0]["status"] = "runtime"
    example["evidence"][1]["kind"] = "runtime"
    assert example["metrics"][0]["value"] == 0
    assert example["metrics"][1]["value"] is None
    assert TOOL.validate(example) == []


@pytest.mark.parametrize(("status", "insufficient_kind", "qualifying_kind"), [
    ("runtime", "source", "runtime"),
    ("runtime", "declared", "experiment"),
    ("experiment", "runtime", "experiment"),
])
def test_numeric_claim_needs_qualifying_evidence_from_its_run(
        example, status, insufficient_kind, qualifying_kind):
    metric = example["metrics"][0]
    metric.update(status=status, run="candidate")
    example["runs"].append(dict(example["runs"][0], id="candidate", revision="candidate-2"))
    baseline_evidence = example["evidence"][1]
    baseline_evidence["kind"] = qualifying_kind

    # The baseline was measured. The candidate has a different revision.
    assert any("metric's run" in error for error in TOOL.validate(example))
    candidate_evidence = dict(baseline_evidence, id="candidate-record",
                              run="candidate", kind=insufficient_kind)
    example["evidence"].append(candidate_evidence)
    metric["evidence"].append(candidate_evidence["id"])
    assert any("metric's run" in error for error in TOOL.validate(example))

    # One matching record suffices; the baseline can remain for comparison.
    candidate_evidence["kind"] = qualifying_kind
    assert TOOL.validate(example) == []


@pytest.mark.parametrize("field", ["run", "scenario", "method", "clock", "time_basis", "overlap", "overhead", "limits", "sample", "evidence"])
def test_numeric_measurement_needs_passport(example, field):
    del example["metrics"][0][field]
    assert TOOL.validate(example)


def test_zero_unknown_and_false_are_not_conflated(example):
    raw = encoded(example)
    assert TOOL.validate(example) == []
    restored = json.loads(TOOL.extract_payload(TOOL.render_html(raw)))
    assert restored["metrics"][0]["value"] == 0
    assert restored["metrics"][1]["value"] is None
    assert restored["x_preserved_example"]["custom"][1] is False
    example["metrics"][0]["value"] = False
    assert any("not boolean" in e for e in TOOL.validate(example))
    example["metrics"][0]["value"] = 0
    example["metrics"][0]["status"] = "unknown"
    assert any("numeric placeholder" in e for e in TOOL.validate(example))
    del example["metrics"][1]["unknown_reason"]
    assert any("unknown_reason" in e for e in TOOL.validate(example))


def test_export_retains_unknown_extensions_and_original_numeric_tokens(example):
    example["nodes"][1]["x_future"] = {"zero": 0, "nested": [False, None, "line\nnext"], "large": 10**40}
    raw = encoded(example).replace(b'"zero": 0,', b'"zero": 0.000,') + b'\n\n'
    html = TOOL.render_html(raw)
    assert TOOL.extract_payload(html) == raw
    assert json.loads(TOOL.extract_payload(html)) == json.loads(raw)
    assert b"new Blob([bytes]" in html


def test_xss_data_remains_data_and_view_has_no_network_or_eval(example):
    attack = '</script><script>window.PWNED=1</script><img src=x onerror="alert(1)">&\u2028'
    example["nodes"][0]["title"] = attack
    example["nodes"][1]["source"]["code"] = attack
    example["evidence"][0]["locator"] = "javascript:alert(1)"
    raw = encoded(example)
    html = TOOL.render_html(raw)
    assert attack.encode() not in html
    assert TOOL.extract_payload(html) == raw
    assert b"textContent" in html
    assert b"innerHTML" not in html and b"eval(" not in html
    assert b"fetch(" not in html and b"XMLHttpRequest" not in html
    assert b"connect-src 'none'" in html and b"base-uri 'none'" in html
    assert html.count(b"<script") == 2


def test_cli_render_extract_roundtrip_and_refuse_overwrite(example, tmp_path, capsys):
    source, view, recovered = (tmp_path / n for n in ("input.json", "view.html", "recovered.json"))
    raw = encoded(example)
    source.write_bytes(raw)
    assert TOOL.main(["render", str(source), "--output", str(view)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["export_roundtrip"] == "byte_identical"
    before = view.read_bytes()
    assert TOOL.main(["render", str(source), "--output", str(view)]) == 2
    assert view.read_bytes() == before
    capsys.readouterr()
    assert TOOL.main(["extract", str(view), "--output", str(recovered)]) == 0
    assert recovered.read_bytes() == raw


def test_existing_output_symlink_not_followed(example, tmp_path):
    target, link = tmp_path / "keep", tmp_path / "view"
    target.write_bytes(b"retained")
    link.symlink_to(target)
    with pytest.raises(FileExistsError):
        TOOL.write_new(link, TOOL.render_html(encoded(example)))
    assert target.read_bytes() == b"retained"


def test_render_refuses_invalid_input_without_creating_output(example, tmp_path, capsys):
    example["metrics"][0].pop("method")
    source, output = tmp_path / "bad.json", tmp_path / "never.html"
    source.write_bytes(encoded(example))
    assert TOOL.main(["render", str(source), "--output", str(output)]) == 2
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)["claims_verified"] is False


def test_multiple_payloads_and_deep_json_refused(example):
    html = TOOL.render_html(encoded(example))
    assert b'id="microscope-data"' in html
    duplicate = b'<script type="application/octet-stream" id="microscope-data">e30=</script>'
    with pytest.raises(TOOL.DocumentError, match="exactly one"):
        TOOL.extract_payload(html + duplicate)
    depth = {"leaf": 0}
    for _ in range(TOOL.MAX_JSON_DEPTH + 1):
        depth = {"nested": depth}
    with pytest.raises(TOOL.DocumentError, match="nesting"):
        TOOL.parse_document(encoded(depth))


def test_known_numeric_measurement_cannot_silently_round_in_browser(example):
    example["metrics"][0]["value"] = 10**80
    assert any("exact browser numeric range" in e for e in TOOL.validate(example))
