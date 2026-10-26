"""New offline diagnostic comparisons only; no target/provider/container execution."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.function_extractor.diagnostics import compare_trace_paths

PRIVATE = 'PRIVATE_DIAGNOSTICS_CANARY resident-body https://invalid.example/token'


def trace():
    spans = [
        {'phase': 'call', 'event': 'call', 'evidence': 'REAL_CODE', 'symbol': 'run',
         'file': 'worker.py', 'line': 10, 'span_id': 1, 'parent_span_id': None},
        {'phase': 'call', 'event': 'call', 'evidence': 'REAL_CODE', 'symbol': 'send',
         'file': 'transport.py', 'line': 30, 'span_id': 2, 'parent_span_id': 1},
        {'phase': 'call', 'event': 'exception', 'evidence': 'REAL_CODE', 'symbol': 'send',
         'file': 'transport.py', 'line': 35, 'span_id': 2, 'parent_span_id': 1,
         'exception': {'class': 'ReadTimeout', 'family': 'EXCEPTION'}},
        {'phase': 'call', 'event': 'return', 'evidence': 'REAL_CODE', 'symbol': 'send',
         'file': 'transport.py', 'line': 36, 'span_id': 2, 'parent_span_id': 1},
        {'phase': 'call', 'event': 'return', 'evidence': 'REAL_CODE', 'symbol': 'run',
         'file': 'worker.py', 'line': 12, 'span_id': 1, 'parent_span_id': None},
    ]
    for index, span in enumerate(spans):
        span.update(utc='2026-10-22T00:00:00Z', monotonic=1.0 + index,
                    correlation_id='a' * 32, duration_seconds=0.01)
    return {'schema': 'route-probe.trace/v1', 'status': 'RETURNED', 'correlation_id': 'a' * 32,
            'sandbox': {'audit': True, 'seccomp': True}, 'spans': spans,
            'result_summary': {'type': 'dict', 'state': 'sent'},
            'target_outcome': {'status': 'RETURNED', 'result_summary': {'type': 'dict', 'state': 'sent'}},
            'result_matches_expected': True,
            'trace_recording': {'complete': True, 'recorded_events': len(spans), 'dropped_events': 0,
                                'selected_modules': ['transport', 'worker']}}


def test_only_clock_duration_and_correlation_changes_match():
    actual, baseline = trace(), trace()
    baseline['correlation_id'] = 'b' * 32
    for index, span in enumerate(baseline['spans']):
        span.update(utc='2027-11-23T12:34:56Z', monotonic=900.0 + index,
                    correlation_id='c' * 32, duration_seconds=4.25)
    result = compare_trace_paths(actual, baseline)
    assert result['status'] == 'MATCH'
    assert result['matching_prefix_events'] == 5
    assert result['recording_incomplete'] is False
    assert result['root_cause_proven'] is False
    assert 'first_difference' not in result


def test_first_concrete_unequal_event_reports_exception_class_and_both_source_anchors():
    actual, baseline = trace(), trace()
    baseline['spans'][2]['exception']['class'] = 'ConnectionError'
    baseline['spans'][2]['line'] = 38
    result = compare_trace_paths(actual, baseline)
    assert result['status'] == 'DIVERGED'
    assert result['matching_prefix_events'] == 2
    first = result['first_difference']
    assert first['event_index'] == 2
    assert first['actual']['exception']['class'] == 'ReadTimeout'
    assert first['baseline']['exception']['class'] == 'ConnectionError'
    assert first['actual_anchor'] == {'span_id': 2, 'file': 'transport.py', 'line': 35, 'symbol': 'send'}
    assert first['baseline_anchor'] == {'span_id': 2, 'file': 'transport.py', 'line': 38, 'symbol': 'send'}
    assert result['root_cause_proven'] is False
    # A real unequal shared event remains observed even if a later suffix is missing.
    actual['status'] = 'TRACE_LIMIT'
    actual['trace_recording']['complete'] = False
    partial = compare_trace_paths(actual, baseline)
    assert partial['status'] == 'DIVERGED' and partial['first_difference']['event_index'] == 2


def test_shared_prefix_with_unobserved_or_equal_incomplete_suffix_is_unknown():
    baseline = trace()
    for limit in (2, 5):
        actual = copy.deepcopy(baseline)
        actual['status'] = 'TRACE_LIMIT'
        actual['spans'] = actual['spans'][:limit]
        actual['trace_recording'].update(complete=False, recorded_events=limit, dropped_events=8)
        result = compare_trace_paths(actual, baseline)
        assert result['status'] == 'UNKNOWN'
        assert result['recording_incomplete'] is True
        assert 'first_difference' not in result
        assert 'outcome_difference' not in result
        assert result['root_cause_proven'] is False
        if limit < 5:
            assert result['reason'] == 'matching_prefix_unobserved_suffix'
        # Symmetric ordering must not turn absent evidence into a divergence.
        assert compare_trace_paths(baseline, actual)['status'] == 'UNKNOWN'


def test_different_module_recording_scope_is_unknown_not_event_mismatch():
    actual, baseline = trace(), trace()
    actual['trace_recording']['selected_modules'] = ['worker']
    result = compare_trace_paths(actual, baseline)
    assert result['status'] == 'UNKNOWN'
    assert result['reason'] == 'recording_scope_differs'
    assert result['root_cause_proven'] is False
    assert 'first_difference' not in result


def test_equal_event_paths_can_differ_in_closed_outcome_without_exporting_raw_summaries():
    actual, baseline = trace(), trace()
    actual['target_outcome']['result_summary']['state'] = 'unknown'
    actual['result_summary']['state'] = 'unknown'
    actual['result_matches_expected'] = False
    result = compare_trace_paths(actual, baseline)
    assert result['status'] == 'DIVERGED'
    assert result['matching_prefix_events'] == 5
    assert 'first_difference' not in result
    assert result['outcome_difference']['actual']['state'] == 'unknown'
    assert result['outcome_difference']['baseline']['state'] == 'sent'
    assert result['outcome_difference']['actual']['result_matches_expected'] is False
    assert result['root_cause_proven'] is False
    # Existing API permits opaque summary strings; this consumer must not reexport them.
    actual['target_outcome']['result_summary'].update(state=PRIVATE, type=PRIVATE, category=PRIVATE)
    actual['result_summary'].update(state=PRIVATE, type=PRIVATE, category=PRIVATE)
    private_result = compare_trace_paths(actual, baseline)
    assert PRIVATE not in json.dumps(private_result)
    assert 'resident-body' not in json.dumps(private_result)
    actual['trace_recording']['complete'] = False
    actual['status'] = 'TRACE_LIMIT'
    incomplete = compare_trace_paths(actual, baseline)
    assert incomplete['status'] == 'UNKNOWN'
    assert 'outcome_difference' not in incomplete


def test_unknown_secret_fields_and_unknown_status_refuse_without_raw_error_export():
    variants = []
    top = trace(); top['body'] = PRIVATE; variants.append(top)
    span = trace(); span['spans'][0]['token'] = PRIVATE; variants.append(span)
    exception = trace(); exception['spans'][2]['exception']['message'] = PRIVATE; variants.append(exception)
    summary = trace(); summary['target_outcome']['result_summary']['body'] = PRIVATE; variants.append(summary)
    status = trace(); status['status'] = PRIVATE; variants.append(status)
    for actual in variants:
        with pytest.raises(ValueError) as error:
            compare_trace_paths(actual, trace())
        assert PRIVATE not in str(error.value)
        assert 'resident-body' not in str(error.value)


def test_cli_baseline_compare_returns_exact_closed_json_and_exit_zero(tmp_path, capsys):
    from tools.function_extractor.cli import main
    actual, baseline = trace(), trace()
    baseline['spans'][2]['line'] = 38
    actual_path, baseline_path = tmp_path / 'actual.json', tmp_path / 'baseline.json'
    actual_path.write_text(json.dumps(actual))
    baseline_path.write_text(json.dumps(baseline))
    expected = compare_trace_paths(actual, baseline)
    assert main(['compare', '--actual', str(actual_path), '--baseline', str(baseline_path)]) == 0
    output = capsys.readouterr()
    assert output.err == ''
    assert json.loads(output.out) == expected
    assert json.loads(output.out)['schema'] == 'function-extractor.path-comparison/v1'
    assert json.loads(output.out)['status'] == 'DIVERGED'
    assert str(actual_path) not in output.out and str(baseline_path) not in output.out


def test_identical_blocked_live_empty_traces_are_unknown_not_successful_match():
    blocked = {'schema': 'route-probe.trace/v1', 'status': 'BLOCKED_LIVE_PROOF', 'spans': []}
    result = compare_trace_paths(blocked, copy.deepcopy(blocked))
    assert result['status'] == 'UNKNOWN'
    assert result['recording_incomplete'] is True
    assert result['matching_prefix_events'] == 0
    assert result['root_cause_proven'] is False
    assert 'first_difference' not in result
    assert 'outcome_difference' not in result
