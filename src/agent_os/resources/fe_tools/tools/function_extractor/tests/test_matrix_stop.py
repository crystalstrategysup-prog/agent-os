"""One new pure matrix orchestration regression; execution/report seams are inert."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_trace_limit_stops_dependent_matrix_and_persists_exact_issued_fixture(tmp_path, monkeypatch, capsys):
    from tools.function_extractor import cli
    from tools.function_extractor.runner.bundle import canonical

    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    (bundle / 'manifest.json').write_text(json.dumps({'entry': 'fixture:run'}))
    first_fixture = {'args': [2, 3], 'kwargs': {'mode': 'synthetic'},
                     'nested': {'unicode': 'Безопасно', 'flags': [True, False, None]}}
    fixture_source = tmp_path / 'input_fixture.json'
    fixture_source.write_text(json.dumps(first_fixture, indent=3, ensure_ascii=False))
    scenarios = tmp_path / 'scenarios.json'
    scenarios.write_text(json.dumps({'cases': [
        {'id': 'first', 'fixture': fixture_source.name,
         'expected': {'schema': 'function-extractor.contract/v1', 'version': 1,
                      'expected_status': 'TRACE_LIMIT', 'result_summary': {'state': 'sent'}}},
        {'id': 'dependent', 'baseline_case_id': 'first', 'fixture': {'args': ['must-not-execute']},
         'expected': {'schema': 'function-extractor.contract/v1', 'version': 1,
                      'expected_status': 'RETURNED'}},
    ]}))
    observed = {'schema': 'route-probe.trace/v1', 'status': 'TRACE_LIMIT',
                'spans': [], 'result_summary': {'type': 'dict', 'state': 'sent'},
                'target_outcome': {'status': 'RETURNED', 'result_summary': {'type': 'dict', 'state': 'sent'}},
                'trace_recording': {'complete': False, 'recorded_events': 0,
                                    'dropped_events': 1, 'selected_modules': []}}
    calls, reports = [], []

    def execute(runner, selected, fixture, timeout):
        calls.append((runner, selected, copy.deepcopy(fixture), timeout))
        assert len(calls) == 1, 'TRACE_LIMIT must stop all dependent execution'
        assert fixture == first_fixture
        return copy.deepcopy(observed)

    def report(node, graph, trace, metadata):
        reports.append(node)
        # The exact issued fixture is already durable before reporting/comparison.
        assert (node / 'fixture.json').read_bytes() == canonical(first_fixture) + b'\n'
        assert metadata['fixture_sha256'] == hashlib.sha256(canonical(first_fixture)).hexdigest()
        assert trace == observed
        (node / 'trace.json').write_bytes(canonical(trace) + b'\n')

    monkeypatch.setattr(cli, '_execute', execute)
    monkeypatch.setattr(cli, '_report', report)
    args = SimpleNamespace(scenarios=scenarios, bundle_map=None, runner='subprocess', timeout=2)
    output = tmp_path / 'out'
    output.mkdir()
    assert cli._matrix(args, bundle, {}, output) == 3
    assert len(calls) == len(reports) == 1
    assert not (output / '1').exists()
    assert (output / '0/fixture.json').read_bytes() == canonical(first_fixture) + b'\n'
    result = json.loads((output / 'scenario_results.json').read_bytes())
    partial = json.loads((output / 'partial_results.json').read_bytes())
    assert result['status'] == 'UNKNOWN'
    assert result['universal_or_live_acceptance'] is False
    assert len(result['cases']) == 1
    assert result['cases'] == partial
    assert result['cases'][0]['id'] == 'first'
    assert result['cases'][0]['outcome'] == 'TRACE_LIMIT'
    # Stop even when the issued case's explicit contract expected TRACE_LIMIT.
    assert result['cases'][0]['comparison']['status'] == 'MATCH'
    printed = capsys.readouterr()
    assert printed.err == ''
    summary = json.loads(printed.out)
    assert summary['status'] == 'UNKNOWN' and summary['cases'] == 1
