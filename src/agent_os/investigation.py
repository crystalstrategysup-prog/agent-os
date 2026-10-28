"""Bounded engineering evidence and repeat decisions; never a side-effect cache."""
from __future__ import annotations
import platform
import re
import sys
import time
from contextlib import contextmanager
from .safeio import GateError, digest, nonempty, now

CLASSES = {'CURRENT_PROVEN', 'HISTORICAL_SUPPORTED', 'HYPOTHESIS', 'CONTRADICTED', 'UNKNOWN'}
OUTCOMES = {'PASS', 'FAIL', 'UNKNOWN', 'BLOCKED'}
IMPROVEMENTS = {'GENERAL', 'DOMAIN_SPECIFIC', 'CASE_ONLY'}
BOTTLENECKS = {'NECESSARY_DURATION', 'EXECUTOR_ERROR', 'CONTRACT_ERROR', 'DOCUMENTATION_GAP', 'ENVIRONMENT_LIMIT', 'PROGRAM_DEFECT', 'EXTERNAL_DEPENDENCY'}


def input_key(*, artifacts: dict, environment: dict, contract_sha: str, fixture_sha: str, hypothesis: str, tool: str):
    if not artifacts or not environment or not hypothesis or not tool:
        raise GateError('exact_inputs_required')
    for sha in [*artifacts.values(), contract_sha, fixture_sha]:
        if not isinstance(sha, str) or re.fullmatch('[a-f0-9]{64}', sha) is None:
            raise GateError('exact_sha256_required')
    return digest({'artifacts': artifacts, 'environment': environment, 'contract_sha': contract_sha, 'fixture_sha': fixture_sha, 'hypothesis': hypothesis, 'tool': tool})


def repeat_decision(history, key, *, reason=None, repeat_plan=None):
    same = [x for x in history if x['input_key'] == key]
    if not same:
        return {'status': 'RUN', 'reason': 'new_exact_inputs'}
    # Two identical failures with no new evidence require a new method/hypothesis.
    tail = same[-2:]
    if len(tail) == 2 and all(x['outcome'] == 'FAIL' and not x['new_evidence'] for x in tail):
        return {'status': 'REVISE_METHOD', 'reason': 'two_identical_failures_without_new_evidence'}
    if repeat_plan is not None:
        if not isinstance(repeat_plan, dict) or repeat_plan.get('purpose') not in {'flakiness', 'race', 'timing', 'reproducibility'} or type(repeat_plan.get('max_runs')) is not int or not 2 <= repeat_plan['max_runs'] <= 100:
            raise GateError('bounded_repeat_plan_required')
        nonempty(repeat_plan.get('declared_before_first_run'), 'repeat_plan_provenance')
        # Caller supplies a plan recorded before the first run; this function
        # does not authenticate that external provenance.
        if len(same) < repeat_plan['max_runs']:
            return {'status': 'RUN', 'reason': repeat_plan['purpose']}
        return {'status': 'REUSE', 'reason': 'declared_repetition_complete'}
    if reason:
        nonempty(reason, 'repeat_reason')
        return {'status': 'RUN', 'reason': reason}
    return {'status': 'REUSE', 'reason': 'unchanged_inputs_need_separate_justification'}


def cache_eligible(*, check_kind, immutable, key, saved_key, outcome):
    return (check_kind in {'static', 'artifact-validation'} and immutable is True
            and isinstance(key, str) and re.fullmatch('[a-f0-9]{64}', key) is not None
            and key == saved_key and outcome == 'PASS')


@contextmanager
def stage(*, tool, input_key, versions, repeat_reason=None, emit):
    """Emit once on exit, including exceptions; caller durably persists the event."""
    nonempty(tool, 'tool'); nonempty(input_key, 'input_key')
    if not isinstance(versions, dict) or not versions:
        raise GateError('versions_required')
    start_utc, start_ns = now(), time.monotonic_ns()
    row = {'schema': 'agentos.investigation-stage/v1', 'tool': tool, 'input_key': input_key,
           'versions': versions, 'repeat_reason': repeat_reason, 'new_evidence': [],
           'start_utc': start_utc, 'start_monotonic_ns': start_ns, 'outcome': 'UNKNOWN'}
    try:
        yield row
    except BaseException:
        row['outcome'] = 'FAIL'
        raise
    finally:
        row['end_monotonic_ns'] = time.monotonic_ns()
        row['end_utc'] = now()
        row['duration_ns'] = row['end_monotonic_ns'] - start_ns
        if row['outcome'] not in OUTCOMES:
            row['outcome'] = 'UNKNOWN'
        emit(row)


def current_environment():
    return {'python': sys.version, 'platform': platform.platform(), 'executable': sys.executable}
