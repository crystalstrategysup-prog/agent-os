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


_FRESH_UPDATE_CHECKS = {'artifact-integrity', 'compatibility', 'post-install-smoke'}
_OFFLINE_UPDATE_CHECKS = {'regression', 'installer-rehearsal'}


def verification_plan(value):
    """Plan bounded update checks, never execute them or authorize a switch.

    Caller verifies receipt bytes and the COMPLETE transitive dependency scope.
    These declarations and hashes are not authenticated provenance. Evidence is
    ordered oldest first; the latest record for a check supersedes an old PASS.
    Reuse covers an isolated offline check, never current target or side effects.
    """
    def require(condition):
        if not condition:
            raise GateError('invalid_update_verification_plan')

    def text(value, maximum=256):
        return type(value) is str and 0 < len(value) <= maximum and '\x00' not in value

    def sha(value):
        return type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None

    def pins(value):
        return (type(value) is dict and len(value) <= 128
                and all(text(k) and sha(v) for k, v in value.items()))

    require(type(value) is dict and set(value) == {'checks', 'evidence'})
    checks, evidence = value['checks'], value['evidence']
    require(type(checks) is list and 1 <= len(checks) <= 64)
    require(type(evidence) is list and len(evidence) <= 256)
    latest = {}
    for row in evidence:
        require(type(row) is dict and set(row) == {
            'check_id', 'input_key', 'outcome', 'receipt_ref', 'receipt_sha256'})
        require(text(row['check_id'], 80) and sha(row['input_key'])
                and text(row['outcome']) and row['outcome'] in OUTCOMES
                and text(row['receipt_ref'], 512) and sha(row['receipt_sha256']))
        latest[row['check_id']] = row
    result, ids, kinds = [], set(), set()
    for check in checks:
        require(type(check) is dict and set(check) == {
            'id', 'kind', 'dependency_pins', 'environment_pins', 'coverage'})
        require(text(check['id'], 80) and check['id'] not in ids)
        require(text(check['kind']) and check['kind'] in _FRESH_UPDATE_CHECKS | _OFFLINE_UPDATE_CHECKS)
        require(pins(check['dependency_pins']) and pins(check['environment_pins']))
        require(text(check['coverage']) and check['coverage'] in {'COMPLETE', 'PARTIAL', 'UNKNOWN'})
        ids.add(check['id'])
        kinds.add(check['kind'])
        key = digest(check)
        prior = latest.get(check['id'])
        action, reason = 'RUN', 'no_matching_pass'
        if check['kind'] in _FRESH_UPDATE_CHECKS:
            reason = 'current_target_requires_fresh_check'
        elif (check['coverage'] != 'COMPLETE' or not check['dependency_pins']
              or not check['environment_pins']):
            reason = 'dependency_scope_unproven'
        elif prior and prior['outcome'] == 'PASS' and prior['input_key'] == key:
            action, reason = 'REUSE', 'verified_offline_scope_unchanged'
        row = {'id': check['id'], 'action': action, 'reason': reason, 'input_key': key}
        if action == 'REUSE':
            row.update(receipt_ref=prior['receipt_ref'], receipt_sha256=prior['receipt_sha256'])
        result.append(row)
    require(_FRESH_UPDATE_CHECKS <= kinds)
    return {'schema': 'agentos.update-verification-plan/v1', 'checks': result,
            'execution_authorized': False}


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


def main(argv=None):
    """Explicit JSON planning entry; no private profiles, discovery or writes."""
    import argparse
    import json
    from pathlib import Path
    from .safeio import read_json_input

    parser = argparse.ArgumentParser(description='Plan dependency-scoped update verification; no execution.')
    parser.add_argument('--update-plan', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = verification_plan(read_json_input(args.update_plan))
    except (GateError, ValueError, OSError):
        print(json.dumps({'status': 'BLOCKED', 'error': 'invalid_update_verification_plan'}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
