"""Bounded observational evidence. Expected contracts are never edited or inferred."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

_HASH = re.compile(r'[0-9a-f]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9_.:<>/-]{1,180}\Z')
_STATES = {'queued', 'sending', 'sent', 'delivered', 'failed', 'unknown', 'partial', 'retry_wait', 'not_started', 'not_requested', 'disabled'}
_CLASSES = {'CODE_BUG', 'CONTRACT_GAP', 'DOCUMENTATION_DRIFT', 'ENVIRONMENT_DEPENDENT', 'EXPECTED_FAILURE', 'UNDETERMINED'}
_INCOMPLETE = {'TIMEOUT', 'REFUSED', 'TRACE_LIMIT', 'BLOCKED_LIVE_PROOF'}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _content(value):
    return _digest({k: v for k, v in value.items() if k != 'content_digest'})


def _bounded(value):
    if len(_canonical(value)) > 2_000_000:
        raise ValueError('evidence_bound')
    def visit(v, depth=0):
        if depth > 40:
            raise ValueError('evidence_depth')
        if isinstance(v, dict):
            if any(type(k) is not str for k in v):
                raise ValueError('evidence_key')
            for item in v.values():
                visit(item, depth + 1)
        elif isinstance(v, list):
            for item in v:
                visit(item, depth + 1)
        elif type(v) not in (str, int, float, bool, type(None)):
            raise ValueError('evidence_type')
    visit(value)


def _identifier(value):
    if type(value) is not str or not _ID.fullmatch(value) or '..' in value or '://' in value:
        raise ValueError('evidence_identifier')
    return value


def _hash(value):
    if type(value) is not str or not _HASH.fullmatch(value):
        raise ValueError('evidence_hash')
    return value


def _path(value):
    _identifier(value)
    p = Path(value)
    if p.is_absolute() or any(part.lower() in {'credentials', 'secrets', 'tokens', '.env', 'backups'} for part in p.parts):
        raise ValueError('evidence_path')
    return value


def source_digest(contract_map):
    """Stable source identity; contract revision is deliberately independent."""
    return _digest(contract_map['route']['source_pins'])


def fixture_digest(scenarios):
    return scenarios['content_digest']


def _anchor(span):
    out = {}
    try:
        for key in ('file', 'symbol'):
            if key in span:
                out[key] = _path(span[key]) if key == 'file' else _identifier(span[key])
        if type(span.get('line')) is int and 0 <= span['line'] <= 10_000_000:
            out['line'] = span['line']
    except ValueError:
        return None
    return out or None


def _matches_boundary(span, symbol, source_pins):
    """Match exact qualified identity, never a suffix or a same-name callable."""
    if span.get('symbol') == symbol:
        return True  # Preserve the existing direct full-symbol comparison.
    if type(symbol) is not str or len(symbol)>256 or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*',symbol):
        return False
    module,qualname=symbol.split(':')
    path=module.replace('.','/')
    candidates={path+'.py',path+'/__init__.py'}
    pinned={row['path'] for row in source_pins}
    return span.get('symbol')==qualname and span.get('file') in candidates & pinned


def _wire_verdict(rule, trace, contract_map, environment):
    """Use only a runner-created transient-value observation, never a fixture.

    These comparisons bind reviewed offline artifacts. JSON digests do not
    authenticate arbitrary traces or prove provider/live execution.
    """
    from .contract_engine import selected_rule_digest
    packet = trace.get('contract_observations')
    if packet is None:
        return 'UNKNOWN', 'wire_value_unobserved'
    guards = trace.get('sandbox', {})
    if guards.get('audit') is not True or guards.get('seccomp') is not True:
        return 'UNKNOWN', 'wire_guards_unverified'
    if packet['complete'] is not True or packet['dropped_observations'] != 0:
        return 'UNKNOWN', 'wire_recording_incomplete'
    plan = packet['plan']
    expected_pins = [(p['path'],p['sha256']) for p in contract_map['route']['source_pins']]
    actual_pins = [(p['path'],p['sha256']) for p in plan['source_pins']]
    if (plan['contract_map_sha256'] != contract_map['content_digest']
            or plan['route_entry'] != contract_map['route']['entry']
            or plan['route_entry'] != trace.get('source_entry')
            or plan['graph_sha256'] != contract_map['route']['graph_sha256']
            or actual_pins != expected_pins):
        return 'UNKNOWN', 'wire_source_unbound'
    if (packet['fixture_sha256'] != trace.get('fixture_sha256')
            or not environment or packet['runner_sha256'] != environment.get('runner_sha256')):
        return 'UNKNOWN', 'wire_environment_unbound'
    ids = plan['rule_ids']
    if any(rid not in {r['rule_id'] for r in contract_map['rules']} for rid in ids):
        return 'UNKNOWN', 'wire_rule_unbound'
    if plan['selected_rule_digest'] != selected_rule_digest(contract_map, ids):
        return 'UNKNOWN', 'wire_rule_unbound'
    checks = []
    for observation in packet['observations']:
        anchor = observation['anchor']
        reached = any(s.get('evidence') == 'REAL_CODE' and s.get('file') == anchor['file']
                      and s.get('symbol') == anchor['symbol'] for s in trace['spans'])
        if not reached:
            return 'UNKNOWN', 'wire_anchor_unobserved'
        for check in observation['checks']:
            if check['rule_id'] != rule['rule_id']:
                continue
            if (check['source_id'] != rule['source_id']
                    or check['schema_sha256'] != _digest(rule['constraint'])
                    or check['provenance'] != rule['provenance']
                    or check['source_sha256'] != next(s['sha256'] for s in contract_map['sources'] if s['source_id'] == rule['source_id'])
                    or observation['boundary_id'] != rule['boundary_id']
                    or observation['direction'] != ('input' if rule['kind'] == 'input_schema' else 'output')):
                return 'UNKNOWN', 'wire_rule_unbound'
            checks.append(check['test_verdict'])
    if not checks:
        return 'UNKNOWN', 'wire_value_unobserved'
    if 'FAIL' in checks:
        return 'FAIL', 'wire_schema_invalid'
    if 'UNKNOWN' in checks:
        return 'UNKNOWN', 'wire_schema_unsupported'
    return 'PASS', 'wire_schema_valid'


def _evaluate(rule, trace, delivery, fixture, contract_map=None, environment=None):
    from .contract_engine import validate_schema
    from .api import compare_contract
    kind, constraint = rule['kind'], rule['constraint']
    if type(constraint) is not dict and kind not in {'input_schema','output_schema'}:
        return 'UNKNOWN', 'unsupported_rule'
    if kind in {'input_schema','output_schema'}:
        return (_wire_verdict(rule, trace, contract_map, environment)
                if contract_map is not None else ('UNKNOWN', 'wire_value_unobserved'))
    if kind == 'delivery_state':
        expected = constraint.get('expected', constraint.get('state'))
        if expected not in _STATES or delivery == 'unobserved':
            return 'UNKNOWN', 'delivery_unobserved'
        return ('PASS', 'rule_match') if delivery == expected else ('FAIL', 'delivery_difference')
    if kind == 'trace_match':
        result = compare_contract(trace, constraint)
        return {'MATCH': ('PASS', 'rule_match'), 'MISMATCH': ('FAIL', 'trace_difference')}.get(result['status'], ('UNKNOWN', 'unsupported_rule'))
    if kind == 'no_retry':
        if set(constraint) == {'phase','event','max_count'}:
            if any(type(constraint[k]) is not str or not _ID.fullmatch(constraint[k]) for k in ('phase','event')):
                return 'UNKNOWN','unsupported_rule'
            maximum=constraint['max_count']
            counts=[span['count'] for span in trace['spans'] if span.get('phase')==constraint['phase'] and span.get('event')==constraint['event'] and type(span.get('count')) is int]
            if type(maximum) is not int or not 0<=maximum<=100 or not counts or any(v<0 for v in counts):return 'UNKNOWN','attempts_unobserved'
            return ('PASS','rule_match') if sum(counts)<=maximum else ('FAIL','retry_difference')
        if set(constraint)-{'max_attempts'}:return 'UNKNOWN','unsupported_rule'
        maximum = constraint.get('max_attempts', 1)
        attempts = [span['attempts'] for span in trace['spans'] if type(span.get('attempts')) is int]
        if type(maximum) is not int or not 0 <= maximum <= 100 or not attempts or any(v<0 for v in attempts):
            return 'UNKNOWN', 'attempts_unobserved'
        return ('PASS', 'rule_match') if max(attempts) <= maximum else ('FAIL', 'retry_difference')
    return 'UNKNOWN', 'unsupported_rule'


def validate_run(run, contract_map, scenarios):
    """Pure bounded comparison. A run may omit cases; omissions stay UNKNOWN.

    run={schema:'contract-run/v1',source_sha256,contract_sha256,fixture_sha256,
         cases:[{case_id,trace,delivery_state?}]}. Hashes bind independent inputs.
    """
    try:
        from .contract_engine import validate_contract_map, selected_rule_digest
        from .api import _trace, compare_contract
        _bounded(contract_map);_bounded(scenarios)
        if type(run) is not dict or type(run.get('cases')) is not list or len(run['cases'])>40:raise ValueError('run_case_bound')
        _bounded({**run,'cases':[{k:v for k,v in row.items() if k!='trace'} if type(row) is dict else None for row in run['cases']]})
        if validate_contract_map(contract_map)['status'] != 'VALID':
            raise ValueError('contract_map_invalid')
        if type(run) is not dict or set(run) - {'schema', 'source_sha256', 'contract_sha256', 'fixture_sha256', 'cases', 'branch_inventory', 'branch_observations'} or not {'schema', 'source_sha256', 'contract_sha256', 'fixture_sha256', 'cases'} <= set(run) or run['schema'] != 'contract-run/v1':
            raise ValueError('run_schema')
        if scenarios.get('schema') != 'function-extractor.generated-scenarios/v1' or scenarios.get('version') != 1 or scenarios.get('content_digest') != _content(scenarios):
            raise ValueError('scenario_digest')
        if scenarios['contract_digest'] != contract_map['content_digest'] or contract_map['content_digest'] != _content(contract_map):
            raise ValueError('contract_digest')
        if contract_map['route']['source_pins'] != sorted(contract_map['route']['source_pins'], key=lambda x: x['path']):
            raise ValueError('source_pin_order')
        identities = {'source_sha256': source_digest(contract_map), 'contract_sha256': contract_map['content_digest'], 'fixture_sha256': fixture_digest(scenarios)}
        if any(run[k] != v for k, v in identities.items()):
            raise ValueError('run_identity')
        planned = scenarios['cases']
        if type(planned) is not list or not 1 <= len(planned) <= 1000 or len({c['id'] for c in planned}) != len(planned):
            raise ValueError('scenario_cases')
        for c in planned:
            _identifier(c['id'])
            if c['fixture_digest'] != _digest(c['fixture']):
                raise ValueError('fixture_digest')
            expectations = c.get('observation_expectations', {})
            allowed = {r['rule_id'] for r in contract_map['rules'] if r['kind'] in {'input_schema','output_schema'}} & set(c['rule_ids'])
            if (type(expectations) is not dict or not set(expectations) <= allowed
                    or any(type(v) is not str or v not in {'PASS','FAIL'} for v in expectations.values())):
                raise ValueError('observation_expectations')
        if type(run['cases']) is not list or len(run['cases']) > len(planned):
            raise ValueError('run_cases')
        actual = {}
        for row in run['cases']:
            if type(row) is not dict or set(row) - {'case_id', 'trace', 'delivery_state', 'environment'} or set(row) < {'case_id', 'trace'} or row['case_id'] in actual or row['case_id'] not in {c['id'] for c in planned}:
                raise ValueError('run_case')
            _trace(row['trace'])
            planned_case=next(c for c in planned if c['id']==row['case_id'])
            if row['trace'].get('status') not in {'RETURNED','RAISED','DENIED','TIMEOUT','REFUSED','TRACE_LIMIT','BLOCKED_LIVE_PROOF'}:
                raise ValueError('trace_status')
            source_entry=row['trace'].get('source_entry')
            if source_entry is not None and source_entry!=planned_case['entry']:raise ValueError('trace_entry_mismatch')
            trace_pin=row['trace'].get('fixture_sha256')
            if trace_pin is not None and _hash(trace_pin)!=planned_case['fixture_digest']:
                raise ValueError('trace_fixture_mismatch')
            if row.get('delivery_state', 'unobserved') not in _STATES | {'unobserved'}:
                raise ValueError('delivery_state')
            environment = row.get('environment', {})
            if type(environment) is not dict or set(environment) - {'source_sha256','bundle_sha256','manifest_source_sha256','runner_sha256','profile_sha256','runner'}:
                raise ValueError('environment_shape')
            for key, value in environment.items():
                if key == 'runner':
                    if value not in {'subprocess','container'}:raise ValueError('environment_runner')
                else:_hash(value)
            actual[row['case_id']] = row
        rules = {r['rule_id']: r for r in contract_map['rules']}
        sources = {s['source_id']: s for s in contract_map['sources']}
        boundaries = {b['boundary_id']: b for b in contract_map['boundaries']}
        branches = {}
        for key in ('branch_inventory','branch_observations'):
            values = run.get(key)
            if values is not None:
                if type(values) is not list or len(values)>10000 or len(set(values)) != len(values):raise ValueError('branches_shape')
                branches[key] = {_identifier(v) for v in values}
        if 'branch_inventory' in branches and not branches.get('branch_observations',set()) <= branches['branch_inventory']:
            raise ValueError('branch_unknown')
        cases, observed_boundaries = [], set()
        for case in planned:
            row = actual.get(case['id'])
            trace = row['trace'] if row else None
            delivery = row.get('delivery_state', trace.get('result_summary', {}).get('state', 'unobserved')) if row else 'unobserved'
            if delivery not in _STATES:
                delivery = 'unobserved'
            recording=trace.get('trace_recording',{}) if trace else {}
            complete = bool(trace and trace['status'] in {'RETURNED','RAISED','DENIED'} and trace.get('source_entry')==case['entry'] and recording.get('complete') is True and recording.get('dropped_events')==0 and type(recording.get('recorded_events')) is int and recording['recorded_events']==len(trace['spans']))
            fixture_bound = bool(trace and trace.get('fixture_sha256')==case['fixture_digest'])
            checks = []
            if any(rid not in rules for rid in case['rule_ids']):
                raise ValueError('scenario_rule')
            for rid in case['rule_ids']:
                rule = rules[rid];source = sources[rule['source_id']]
                schema_fact = None
                anchors = [] if not trace else [a for s in trace['spans'] if _matches_boundary(s,boundaries[rule['boundary_id']]['symbol'],contract_map['route']['source_pins']) and (a := _anchor(s))]
                if anchors:
                    observed_boundaries.add(rule['boundary_id'])
                if not row or case['execution_mode'] != 'REPLAY':
                    verdict, reason = 'UNKNOWN', 'case_not_executed'
                elif any(rules[other]['provenance'] == rule['provenance'] for other in rule.get('conflicts', [])):
                    verdict, reason = 'UNKNOWN', 'contract_conflict'
                elif rule['provenance'] == 'UNSPECIFIED':
                    verdict, reason = 'UNKNOWN', 'unspecified_contract'
                else:
                    verdict, reason = _evaluate(rule, trace, delivery, case['fixture'], contract_map, row.get('environment'))
                    if rule['kind'] in {'input_schema','output_schema'}:
                        schema_fact = verdict
                        if schema_fact in {'PASS','FAIL'}:
                            anchors = [_anchor(obs['anchor']) for obs in trace['contract_observations']['observations']
                                       if any(c['rule_id'] == rid for c in obs['checks'])]
                            anchors = [a for a in anchors if a is not None]
                            if anchors:
                                observed_boundaries.add(rule['boundary_id'])
                    if not fixture_bound and verdict == 'PASS':
                        verdict, reason = 'UNKNOWN','fixture_unbound'
                    if not complete and verdict == 'PASS':
                        verdict, reason = 'UNKNOWN', 'incomplete_recording'
                    if schema_fact is not None and (not fixture_bound or not complete):
                        verdict, reason = 'UNKNOWN', 'fixture_unbound' if not fixture_bound else 'incomplete_recording'
                    expectation = case.get('observation_expectations', {}).get(rid)
                    if expectation is not None and verdict != 'UNKNOWN':
                        if not fixture_bound or not complete:
                            verdict, reason = 'UNKNOWN', 'incomplete_recording'
                        else:
                            verdict, reason = (('PASS','expected_schema_violation') if schema_fact == expectation == 'FAIL' else
                                               ('PASS','wire_schema_valid') if schema_fact == expectation == 'PASS' else
                                               ('FAIL','schema_observation_difference'))
                provenance = rule['provenance']
                classification = ('CONTRACT_GAP' if reason in {'unsupported_rule','unspecified_contract','contract_conflict','wire_value_unobserved','wire_schema_unsupported'} else
                                  'UNDETERMINED' if verdict == 'UNKNOWN' else
                                  'DOCUMENTATION_DRIFT' if verdict == 'FAIL' and provenance == 'OBSERVED' else
                                  'ENVIRONMENT_DEPENDENT' if verdict == 'FAIL' and trace['status'] in {'DENIED','REFUSED','TIMEOUT'} else
                                  'EXPECTED_FAILURE' if reason == 'expected_schema_violation' else
                                  'ENVIRONMENT_DEPENDENT' if verdict == 'FAIL' and rule['kind'] == 'output_schema' else
                                  'CODE_BUG' if verdict == 'FAIL' else
                                  'EXPECTED_FAILURE' if delivery in {'failed','unknown','retry_wait','not_started'} else 'UNDETERMINED')
                peers = [r for r in rules.values() if (r['boundary_id'],r['kind']) == (rule['boundary_id'],rule['kind'])]
                order = {'OFFICIAL':0,'APPROVED_INTERNAL':1,'OBSERVED':2,'UNSPECIFIED':3}
                highest = min(order[r['provenance']] for r in peers)
                role = 'NORMATIVE' if order[provenance] == highest and highest < 2 else 'OBSERVATIONAL'
                if role == 'OBSERVATIONAL' and verdict == 'FAIL':classification='DOCUMENTATION_DRIFT'
                check_row = {'comparison_role':role, 'rule_id': _identifier(rid), 'boundary_id': _identifier(rule['boundary_id']), 'source_id': _identifier(rule['source_id']),
                               'source_sha256': _hash(source['sha256']), 'provenance': provenance,
                               'test_verdict': verdict, 'classification': classification, 'reason_code': reason, 'trace_anchors': anchors[:8]}
                if schema_fact is not None:
                    check_row['observed_schema_verdict'] = schema_fact
                    check_row['expected_schema_verdict'] = case.get('observation_expectations', {}).get(rid, 'PASS')
                checks.append(check_row)
            normative = [x for x in checks if x['comparison_role']=='NORMATIVE']
            expected_result = compare_contract(trace,case['expected'])['status'] if row and case['execution_mode']=='REPLAY' and case['expected'] is not None else 'UNKNOWN'
            expected_verdict = {'MATCH':'PASS','MISMATCH':'FAIL'}.get(expected_result,'UNKNOWN')
            if trace and trace.get('result_matches_expected') is False:
                expected_verdict='FAIL'
            elif trace and 'expected_result' in case['fixture'] and trace.get('result_matches_expected') is not True:
                expected_verdict='UNKNOWN'
            verdict = 'FAIL' if expected_verdict=='FAIL' or any(x['test_verdict']=='FAIL' for x in normative) else 'UNKNOWN' if not normative or expected_verdict=='UNKNOWN' or any(x['test_verdict']=='UNKNOWN' for x in normative) else 'PASS'
            selected_rules = [rules[rid] for rid in sorted(case['rule_ids'])]
            selected_sources = [sources[sid] for sid in sorted({r['source_id'] for r in selected_rules})]
            selected_digest = selected_rule_digest(contract_map,case['rule_ids'])
            if case.get('selected_rule_digest',selected_digest) != selected_digest:raise ValueError('selected_rule_digest')
            case_pins = case.get('source_pins',contract_map['route']['source_pins'])
            if case_pins != contract_map['route']['source_pins']:raise ValueError('case_source_pins')
            environment = row.get('environment',{}) if row else {}
            cache_eligible = complete and fixture_bound and verdict=='PASS' and set(environment)=={'source_sha256','bundle_sha256','manifest_source_sha256','runner_sha256','profile_sha256','runner'}
            cache_identity = {'source_pins':case_pins,'selected_rule_digest':selected_digest,'fixture_digest':case['fixture_digest'],'expected':case['expected'],
                              'observation_expectations':case.get('observation_expectations',{}),'environment':row.get('environment',{}) if row else {}}
            cases.append({'case_id': case['id'], 'cache_key':_digest(cache_identity), 'cache_eligible':cache_eligible, 'expected_contract_verdict':expected_verdict, 'delivery_state': delivery, 'test_verdict': verdict,
                          'diagnostic_status': 'DRIFT' if any(x['test_verdict']=='FAIL' for x in checks) or verdict=='FAIL' else 'CONFORMANT' if verdict == 'PASS' else 'INCOMPLETE', 'rules': checks})
        result = {'schema': 'ce-evidence.validation/v1', 'version': 1, 'status': 'VALIDATED', **identities,
                  'scenario_sha256': scenarios['content_digest'], 'cases': cases,
                  'coverage': {'boundaries': {'declared':len(boundaries),'observed':len(observed_boundaries),'observed_ids':sorted(observed_boundaries)},
                               'branches':{'total':len(branches['branch_inventory']) if 'branch_inventory' in branches else None,'observed':len(branches['branch_observations']) if 'branch_observations' in branches else None,'denominator_known':'branch_inventory' in branches},
                               'variants':{'planned':len(planned),'executed':len(actual),'unexecuted':len(planned)-len(actual)}},
                  'normative_modified': False, 'production_acceptance': False}
        result['content_digest'] = _content(result)
        return result
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError, OverflowError):
        return {'schema':'ce-evidence.validation/v1','version':1,'status':'REFUSED','reason_code':'evidence_input_invalid'}


def _validated(value):
    from .contract_engine import validate_schema
    schema_path = Path(__file__).with_name('contracts') / 'ce_evidence_validation.schema.json'
    if validate_schema(value,json.loads(schema_path.read_text()))['status']!='VALID':
        raise ValueError('validation_schema')
    if value.get('status') != 'VALIDATED' or value.get('content_digest') != _content(value):
        raise ValueError('validation_digest')
    for key in ('source_sha256','contract_sha256','fixture_sha256','scenario_sha256','content_digest'):_hash(value[key])
    for case in value['cases']:
        _identifier(case['case_id']);_hash(case['cache_key'])
        for rule in case['rules']:
            for key in ('rule_id','boundary_id','source_id'):_identifier(rule[key])
            _hash(rule['source_sha256'])
            for anchor in rule['trace_anchors']:
                if 'file' in anchor:_path(anchor['file'])
                if 'symbol' in anchor:_identifier(anchor['symbol'])


def _passport(validated):
    return {'schema':'ce-evidence.passport/v1','version':1,'status':'OBSERVED','evidence_digest':validated['content_digest'],
            'source_sha256':validated['source_sha256'],'contract_sha256':validated['contract_sha256'],'fixture_sha256':validated['fixture_sha256'],
            'observed':[{'case_id':c['case_id'],'delivery_state':c['delivery_state'],'test_verdict':c['test_verdict'],'diagnostic_status':c['diagnostic_status']} for c in validated['cases']],
            'drift':[{'case_id':c['case_id'],'rule_id':r['rule_id'],'classification':r['classification']} for c in validated['cases'] for r in c['rules'] if r['test_verdict']=='FAIL'],
            'proposed':[{'status':'PROPOSED','rule_id':r['rule_id'],'action':'REVIEW_CONTRACT_GAP'} for c in validated['cases'] for r in c['rules'] if r['classification']=='CONTRACT_GAP'],
            'normative_modified':False,'production_acceptance':False}


@contextmanager
def _root(root, create):
    path = Path(root).absolute()
    if path.name != 'generated' or any(p.lower() in {'canonical','contracts','deploy','app','current','tenants','knowledge','credentials','secrets','.env'} for p in path.parts):
        raise ValueError('generated_path_required')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if part in {'.','..'}:
                raise ValueError('generated_path')
            try:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:pass
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd);fd=nxt
        lock = os.open('.sync.lock',(os.O_RDWR|os.O_CREAT if create else os.O_RDONLY)|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=fd)
        try:
            s=os.fstat(lock)
            if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_uid != os.getuid():
                raise ValueError('generated_lock')
            fcntl.flock(lock,(fcntl.LOCK_EX if create else fcntl.LOCK_SH)|fcntl.LOCK_NB)
            yield fd
        finally:
            os.close(lock)
    finally:
        os.close(fd)


def _read(fd, name):
    f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    try:
        s=os.fstat(f)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_uid != os.getuid() or s.st_size>2_000_000:
            raise ValueError('generated_file')
        data=b''
        while chunk:=os.read(f,65536):
            data+=chunk
            if len(data)>2_000_000:raise ValueError('generated_bound')
        if tuple(os.fstat(f)[i] for i in (0,1,2,3,4,5,6,8,9))!=tuple(s[i] for i in (0,1,2,3,4,5,6,8,9)):raise ValueError('generated_changed')
        return json.loads(data)
    finally:os.close(f)


def _atomic(fd,name,value):
    temporary='.tmp-'+uuid.uuid4().hex
    f=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
    try:
        data=_canonical(value);offset=0
        while offset<len(data):offset+=os.write(f,data[offset:])
        os.fsync(f)
    finally:os.close(f)
    try:
        os.replace(temporary,name,src_dir_fd=fd,dst_dir_fd=fd);os.fsync(fd)
    finally:
        try:os.unlink(temporary,dir_fd=fd)
        except FileNotFoundError:pass


def sync_docs(validated, registry_root):
    """One atomic generated record contains both evidence and diagnostic passport."""
    try:
        _validated(validated)
        key=_digest({k:validated[k] for k in ('source_sha256','contract_sha256','fixture_sha256')})
        passport=_passport(validated)
        from .contract_engine import validate_schema
        if validate_schema(passport,json.loads((Path(__file__).with_name('contracts')/'ce_evidence_passport.schema.json').read_text()))['status']!='VALID':raise ValueError('passport_schema')
        document={'schema':'ce-evidence.record/v1','version':1,'key':key,'validation':validated,'passport':passport}
        document['content_digest']=_content(document)
        with _root(registry_root,True) as fd:
            name=key+'.json'
            try:
                index=_read(fd,'index.json')
                _check_index(index)
            except FileNotFoundError:
                index={'schema':'ce-evidence.index/v1','version':1,'records':{},'cases':{}}
            try:
                current=_read(fd,name)
                if current!=document:raise ValueError('evidence_key_conflict')
                existing=True
            except FileNotFoundError:existing=False
            if existing and index['records'].get(key)==document['content_digest'] and all(not c['cache_eligible'] or index['cases'].get(c['cache_key'])=={'record_key':key,'case_id':c['case_id']} for c in validated['cases']):
                return {'schema':'ce-evidence.sync/v1','status':'UNCHANGED','key':key,'content_digest':document['content_digest'],'normative_modified':False}
            if not existing:_atomic(fd,name,document)
            index['records'][key]=document['content_digest']
            for case in validated['cases']:
                if not case['cache_eligible']:continue
                index['cases'][case['cache_key']]={'record_key':key,'case_id':case['case_id']}
            _check_index(index)
            _atomic(fd,'index.json',index)
        return {'schema':'ce-evidence.sync/v1','status':'WRITTEN','key':key,'content_digest':document['content_digest'],'normative_modified':False}
    except Exception:
        return {'schema':'ce-evidence.sync/v1','status':'REFUSED','reason_code':'generated_sync_refused','normative_modified':False}


def load_registry(registry_root, source_sha256, contract_sha256, fixture_sha256):
    """Identity changes miss only that key; unrelated evidence is retained."""
    try:
        identity={k:_hash(v) for k,v in zip(('source_sha256','contract_sha256','fixture_sha256'),(source_sha256,contract_sha256,fixture_sha256))}
        key=_digest(identity)
        with _root(registry_root,False) as fd:
            index=_read(fd,'index.json');_check_index(index)
            if key not in index['records']:raise FileNotFoundError
            record=_read(fd,key+'.json')
            if index['records'][key]!=record.get('content_digest'):raise ValueError('index_binding')
        if set(record)!={'schema','version','key','validation','passport','content_digest'} or record['schema']!='ce-evidence.record/v1' or record['version']!=1 or record['key']!=key or record['content_digest']!=_content(record):raise ValueError('record_digest')
        _validated(record['validation'])
        if any(record['validation'][k]!=v for k,v in identity.items()) or record['passport']!=_passport(record['validation']):raise ValueError('record_binding')
        return {'schema':'ce-evidence.cache/v1','status':'HIT','key':key,'record':record}
    except FileNotFoundError:return {'schema':'ce-evidence.cache/v1','status':'MISS'}
    except Exception:return {'schema':'ce-evidence.cache/v1','status':'REFUSED','reason_code':'generated_cache_refused'}


def _check_index(value):
    if type(value) is not dict or set(value)!={'schema','version','records','cases'} or value['schema']!='ce-evidence.index/v1' or type(value['version']) is not int or value['version']!=1:
        raise ValueError('index_shape')
    if type(value['records']) is not dict or type(value['cases']) is not dict or len(value['records'])>10000 or len(value['cases'])>10000:raise ValueError('index_bound')
    for k,v in value['records'].items():_hash(k);_hash(v)
    for k,v in value['cases'].items():
        _hash(k)
        if type(v) is not dict or set(v)!={'record_key','case_id'} or v['record_key'] not in value['records']:raise ValueError('index_ref')
        _identifier(v['case_id'])


def load_case_registry(registry_root, cache_key):
    """Lookup unaffected case evidence without requiring the full matrix identity."""
    try:
        _hash(cache_key)
        with _root(registry_root,False) as fd:
            index=_read(fd,'index.json');_check_index(index)
            if cache_key not in index['cases']:raise FileNotFoundError
            ref=index['cases'][cache_key];record=_read(fd,ref['record_key']+'.json')
        validation=record['validation'];_validated(validation)
        if record.get('content_digest')!=_content(record) or index['records'][ref['record_key']]!=record['content_digest'] or record['passport']!=_passport(validation):raise ValueError('case_record')
        matches=[c for c in validation['cases'] if c['cache_key']==cache_key and c['case_id']==ref['case_id']]
        if len(matches)!=1:raise ValueError('case_reference')
        return {'schema':'ce-evidence.case-cache/v1','status':'HIT','case':matches[0],'evidence_digest':validation['content_digest']}
    except FileNotFoundError:return {'schema':'ce-evidence.case-cache/v1','status':'MISS'}
    except Exception:return {'schema':'ce-evidence.case-cache/v1','status':'REFUSED','reason_code':'case_cache_refused'}
