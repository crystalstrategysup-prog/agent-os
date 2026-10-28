"""Pure bounded witnesses for independently pinned offline boundary schemas.

A valid document binds data, not authenticity: trusted parent/Context and exact
reviewed capture code remain prerequisites. No observed values or their hashes
are retained. Subject code is never imported or executed here.
"""
from __future__ import annotations

import hashlib
import json
import re

from . import contract_engine as ce

PLAN_SCHEMA = 'function-extractor.contract-observation-plan/v1'
OBSERVATION_SCHEMA = 'function-extractor.contract-observation/v1'
OBSERVATIONS_SCHEMA = 'function-extractor.contract-observations/v1'
ADMISSION_SCHEMA = 'function-extractor.contract-observation-admission/v1'
EVIDENCE_SCOPE = 'OFFLINE_INTERCEPTED_TRANSIENT_VALUE_NOT_PROVIDER_PROOF'
PLAN_LIMIT = 65536
PACKET_LIMIT = 262144
_SHA = re.compile(r'[a-f0-9]{64}\Z')
_SYMBOL = re.compile(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*\Z')
_ENTRY = re.compile(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*:[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*\Z')
_ERRORS = (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError)
_PLAN_KEYS = {'schema','version','status','route_entry','graph_sha256','manifest_sha256','contract_map_sha256',
              'selected_rule_digest','rule_ids','source_pins','rules','bindings','content_digest'}
_BINDING_KEYS = {'binding_id','boundary_id','direction','phase','file','sha256','symbol','line'}
_RULE_KEYS = {'rule_id','boundary_id','kind','source_id','source_sha256','provenance','schema_sha256','constraint','conflicts'}
_CHECK_KEYS = {'rule_id','source_id','source_sha256','schema_sha256','provenance','test_verdict','reason_code'}
_OBSERVATION_KEYS = {'schema','version','status','plan_sha256','binding_id','boundary_id','direction','phase',
                     'anchor','invocation_id','checks','evidence_scope'}
_PACKET_KEYS = {'schema','version','plan','fixture_sha256','runner_sha256','observations','complete','dropped_observations','content_digest'}
_REASONS = {'PASS': {'SCHEMA_MATCH'}, 'FAIL': {'SCHEMA_INVALID'},
            'UNKNOWN': {'SCHEMA_UNSUPPORTED_OR_BOUNDED','CONTRACT_CONFLICT','CONTRACT_UNSPECIFIED','EVALUATOR_FAILURE',
                        'CONTRACT_SCOPE_UNSUPPORTED'}}


def _require(condition):
    if not condition:
        raise ValueError('INVALID_CONTRACT_OBSERVATION')


def _json(value, *, size=PLAN_LIMIT, items=30000):
    # Exact builtin types only; no user repr/iteration/encoder callbacks.
    return ce._bounded(value, items=items, depth=24, size=size)


def _sha(value):
    return type(value) is str and bool(_SHA.fullmatch(value))


def _id(value):
    return ce._identifier(value)


def _digest(value):
    return hashlib.sha256(ce.canonical(value)).hexdigest()


def observation_content_digest(value):
    """Canonical identity excluding content_digest; only already public metadata."""
    value = _json(value, size=PACKET_LIMIT, items=60000)
    _require(type(value) is dict)
    return _digest({k: v for k, v in value.items() if k != 'content_digest'})


def _refused(schema, reason):
    return {'schema': schema, 'version': 1, 'status': 'REFUSED', 'reason_code': reason}


def _admission(status, reason, scope='NONE'):
    return {'schema': ADMISSION_SCHEMA, 'version': 1, 'status': status,
            'reason_code': reason, 'admission_scope': scope}


def _manifest(manifest):
    manifest = _json(manifest, size=100000)
    _require(type(manifest) is dict and manifest.get('schema') == 'route-probe.bundle/v1')
    _require(type(manifest.get('entry')) is str and bool(_ENTRY.fullmatch(manifest['entry'])))
    _require(_sha(manifest.get('graph_sha256')))
    rows = manifest.get('files')
    _require(type(rows) is list and 0 < len(rows) <= 160)
    total, seen, pins = 0, set(), []
    for row in rows:
        _require(type(row) is dict and set(row) == {'path','sha256','bytes'})
        path = ce._relative(row['path']).as_posix()
        _require(path == row['path'] and path not in seen and _sha(row['sha256']))
        _require(type(row['bytes']) is int and 0 <= row['bytes'] <= 2000000)
        seen.add(path); total += row['bytes']; pins.append(dict(row))
    _require(total <= 16000000 and pins == sorted(pins, key=lambda r: r['path']))
    return manifest, pins


def _binding(value, pins):
    _require(type(value) is dict and set(value) in (_BINDING_KEYS, _BINDING_KEYS | {'applicability'}))
    _require(_id(value['binding_id']) and _id(value['boundary_id']))
    _require((value['direction'], value['phase']) in {('input','REQUEST'), ('output','RESPONSE')})
    path = ce._relative(value['file']).as_posix()
    _require(path == value['file'] and _sha(value['sha256']) and pins.get(path) == value['sha256'])
    _require(type(value['symbol']) is str and 0 < len(value['symbol']) <= 180 and bool(_SYMBOL.fullmatch(value['symbol'])))
    _require(type(value['line']) is int and 1 <= value['line'] <= 10000000)
    if 'applicability' in value:
        _require((_plain_input(value) and value['applicability'] == 'PLAIN_TEXT_ONLY')
                 or (_html_input(value) and value['applicability'] == 'HTML_BOLD_TEXT_V1'))
    return value


def _plain_input(binding):
    return (binding['boundary_id'], binding['direction'], binding['phase']) == ('telegram.sendMessage.plain', 'input', 'REQUEST')


def _html_input(binding):
    return (binding['boundary_id'], binding['direction'], binding['phase']) == ('telegram.sendMessage.html.bold', 'input', 'REQUEST')


def _html_schema_value(value):
    """Transient projection for the emitted bold-label subset, never a wire edit.

    No permissive browser parser: exact nonnested <b>, escaped text and numeric
    Unicode scalar references only. Other HTML stays explicitly unsupported.
    Return verdict/reason separately from the projected value. All input bytes
    are bounded JSON before scanning; no value or value hash leaves the witness.
    """
    try:
        value = _json(value, size=524288, items=10000)
    except _ERRORS:
        return None, 'UNKNOWN', 'SCHEMA_UNSUPPORTED_OR_BOUNDED'
    if type(value) is not dict:
        return value, None, None  # ordinary object schema failure
    if value.get('parse_mode') != 'HTML' or 'entities' in value:
        return None, 'UNKNOWN', 'CONTRACT_SCOPE_UNSUPPORTED'
    text = value.get('text')
    if type(text) is not str:
        return value, None, None  # ordinary required/type schema failure
    parts, opened, position = [], False, 0
    token = re.compile(r'<b>|</b>|&(?:lt|gt|amp|quot|#[0-9]{1,8}|#x[0-9a-fA-F]{1,6});|[^<>&]+')
    named = {'&lt;':'<', '&gt;':'>', '&amp;':'&', '&quot;':'"'}
    for match in token.finditer(text):
        if match.start() != position:
            # Unsupported tags/entities may be valid Telegram; do not call
            # them invalid just because this selected profile cannot parse.
            tail = text[position:]
            if tail.startswith('>') or tail.startswith('& ') or tail == '&':
                return None, 'FAIL', 'SCHEMA_INVALID'
            return None, 'UNKNOWN', 'CONTRACT_SCOPE_UNSUPPORTED'
        part = match.group()
        position = match.end()
        if part == '<b>':
            if opened:
                return None, 'UNKNOWN', 'CONTRACT_SCOPE_UNSUPPORTED'
            opened = True
        elif part == '</b>':
            if not opened:
                return None, 'FAIL', 'SCHEMA_INVALID'
            opened = False
        elif part in named:
            parts.append(named[part])
        elif part.startswith('&#'):
            number = int(part[3:-1], 16) if part.startswith('&#x') else int(part[2:-1])
            if not 1 <= number <= 0x10ffff or 0xd800 <= number <= 0xdfff:
                return None, 'UNKNOWN', 'CONTRACT_SCOPE_UNSUPPORTED'
            parts.append(chr(number))
        else:
            if any(0xd800 <= ord(char) <= 0xdfff or ord(char) == 0 for char in part):
                return None, 'UNKNOWN', 'CONTRACT_SCOPE_UNSUPPORTED'
            parts.append(part)
    if position != len(text):
        return None, 'UNKNOWN', 'CONTRACT_SCOPE_UNSUPPORTED'
    if opened:
        return None, 'FAIL', 'SCHEMA_INVALID'
    return {**value, 'text': ''.join(parts)}, None, None


def _applicability_reason(binding, value):
    if not _plain_input(binding):
        return None
    if binding.get('applicability') != 'PLAIN_TEXT_ONLY':
        return 'CONTRACT_SCOPE_UNSUPPORTED'
    if type(value) is dict:
        # Inspect bounded exact builtin keys only, never text or formatting values.
        if len(value) > 10000 or any(type(key) is not str or len(key) > 256 for key in value):
            return 'SCHEMA_UNSUPPORTED_OR_BOUNDED'
        if 'parse_mode' in value or 'entities' in value:
            return 'CONTRACT_SCOPE_UNSUPPORTED'
    return None


def _anchor(value):
    value = _json(value)
    _require(type(value) is dict and set(value) == {'file','sha256','symbol','line'})
    _require(ce._relative(value['file']).as_posix() == value['file'] and _sha(value['sha256']))
    _require(type(value['symbol']) is str and 0 < len(value['symbol']) <= 180 and bool(_SYMBOL.fullmatch(value['symbol'])))
    _require(type(value['line']) is int and 1 <= value['line'] <= 10000000)
    return value


def _rule_rows(contract_map, rule_ids):
    originals = {r['rule_id']: r for r in contract_map['rules']}
    _require(type(rule_ids) is list and 0 < len(rule_ids) <= 64 and len(rule_ids) == len(set(rule_ids)))
    _require(all(_id(rid) and rid in originals for rid in rule_ids))
    ids = set(rule_ids)
    while True:
        expanded = ids | {peer for rid in ids for peer in originals[rid]['conflicts']}
        if expanded == ids:
            break
        ids = expanded
    _require(len(ids) <= 64)
    sources = {s['source_id']: s for s in contract_map['sources']}
    rows = []
    for rid in sorted(ids):
        rule = originals[rid]
        _require(rule['kind'] in {'input_schema','output_schema'})
        rows.append({'rule_id':rid, 'boundary_id':rule['boundary_id'], 'kind':rule['kind'],
                     'source_id':rule['source_id'], 'source_sha256':sources[rule['source_id']]['sha256'],
                     'provenance':rule['provenance'], 'schema_sha256':_digest(rule['constraint']),
                     'constraint':rule['constraint'], 'conflicts':sorted(rule['conflicts'])})
    return rows


def compile_contract_observation_plan(contract_map, manifest, *, rule_ids, bindings):
    """Compile independent CE rules, never fixture expectations or observations."""
    try:
        contract_map = _json(contract_map, size=2000000)
        _require(ce.validate_contract_map(contract_map)['status'] == 'VALID' and contract_map['status'] != 'REFUSED')
        manifest, pins = _manifest(manifest)
        route = contract_map['route']
        _require(route['entry'] == manifest['entry'] and route['graph_sha256'] == manifest['graph_sha256'])
        _require(route['source_pins'] == [{'path':p['path'],'sha256':p['sha256']} for p in pins])
        bindings = _json(bindings)
        _require(type(bindings) is list and 0 < len(bindings) <= 32)
        by_path = {p['path']:p['sha256'] for p in pins}
        rows = _rule_rows(contract_map, _json(rule_ids))
        for binding in bindings:
            _binding(binding, by_path)
            _require(not _plain_input(binding) or binding.get('applicability') == 'PLAIN_TEXT_ONLY')
            _require(not _html_input(binding) or binding.get('applicability') == 'HTML_BOLD_TEXT_V1')
            _require(any(r['boundary_id'] == binding['boundary_id'] and r['kind'] == binding['direction']+'_schema' for r in rows))
        _require(len({b['binding_id'] for b in bindings}) == len(bindings))
        _require(all(any(b['boundary_id'] == r['boundary_id'] and b['direction']+'_schema' == r['kind'] for b in bindings) for r in rows))
        plan = {'schema':PLAN_SCHEMA,'version':1,'status':'COMPILED', 'route_entry':route['entry'],
                'graph_sha256':route['graph_sha256'],'manifest_sha256':_digest(manifest),
                'contract_map_sha256':contract_map['content_digest'],
                'selected_rule_digest':ce.selected_rule_digest(contract_map, sorted(rule_ids)),
                'rule_ids':sorted(rule_ids),'source_pins':pins,'rules':rows,
                'bindings':sorted(bindings,key=lambda b:b['binding_id'])}
        plan['content_digest'] = observation_content_digest(plan)
        _plan(plan, manifest, structural_only=False)
        return plan
    except _ERRORS:
        return _refused(PLAN_SCHEMA, 'PLAN_INPUT_INVALID')


def _plan(value, manifest, *, structural_only):
    plan = _json(value)
    _require(type(plan) is dict and set(plan) == _PLAN_KEYS and plan['schema'] == PLAN_SCHEMA)
    _require(type(plan['version']) is int and plan['version'] == 1 and plan['status'] == 'COMPILED')
    _require(_sha(plan['content_digest']) and observation_content_digest(plan) == plan['content_digest'])
    _require(type(plan['route_entry']) is str and bool(_ENTRY.fullmatch(plan['route_entry'])))
    _require(all(_sha(plan[k]) for k in ('graph_sha256','manifest_sha256','contract_map_sha256','selected_rule_digest')))
    pins = plan['source_pins']; _require(type(pins) is list and 0 < len(pins) <= 160)
    by_path, total = {}, 0
    for pin in pins:
        _require(type(pin) is dict and set(pin) == {'path','sha256','bytes'})
        path = ce._relative(pin['path']).as_posix()
        _require(path == pin['path'] and path not in by_path and _sha(pin['sha256']))
        _require(type(pin['bytes']) is int and 0 <= pin['bytes'] <= 2000000)
        total += pin['bytes']; by_path[path] = pin['sha256']
    _require(total <= 16000000 and pins == sorted(pins,key=lambda p:p['path']))
    rules = plan['rules']; _require(type(rules) is list and 0 < len(rules) <= 64)
    ids = set()
    for rule in rules:
        _require(type(rule) is dict and set(rule) == _RULE_KEYS)
        _require(all(_id(rule[k]) for k in ('rule_id','source_id','boundary_id')) and rule['rule_id'] not in ids)
        ids.add(rule['rule_id'])
        _require(rule['kind'] in {'input_schema','output_schema'} and rule['provenance'] in ce.LEVELS)
        _require(_sha(rule['source_sha256']) and _sha(rule['schema_sha256']) and type(rule['constraint']) in (dict,bool))
        _require(_digest(rule['constraint']) == rule['schema_sha256'])
        _require(type(rule['conflicts']) is list and len(rule['conflicts']) <= 64 and all(_id(x) for x in rule['conflicts']))
        _require(rule['conflicts'] == sorted(set(rule['conflicts'])))
    _require([r['rule_id'] for r in rules] == sorted(ids))
    for rule in rules:
        expected = {other['rule_id'] for other in rules if other['rule_id'] != rule['rule_id']
                    and (other['boundary_id'],other['kind']) == (rule['boundary_id'],rule['kind'])
                    and ce.canonical(other['constraint']) != ce.canonical(rule['constraint'])}
        _require(set(rule['conflicts']) == expected)
    _require(type(plan['rule_ids']) is list and 0 < len(plan['rule_ids']) <= 64)
    _require(all(_id(x) and x in ids for x in plan['rule_ids']) and plan['rule_ids'] == sorted(set(plan['rule_ids'])))
    selected = set(plan['rule_ids'])
    by_id = {r['rule_id']:r for r in rules}
    while True:
        expanded = selected | {peer for rid in selected for peer in by_id[rid]['conflicts']}
        if expanded == selected:
            break
        selected = expanded
    _require(selected == ids)  # No unrelated unselected rule injection.
    bindings = plan['bindings']; _require(type(bindings) is list and 0 < len(bindings) <= 32)
    for binding in bindings:
        _binding(binding, by_path)
        _require(any(r['boundary_id'] == binding['boundary_id'] and r['kind'] == binding['direction']+'_schema' for r in rules))
    _require([b['binding_id'] for b in bindings] == sorted({b['binding_id'] for b in bindings}))
    _require(all(any(b['boundary_id'] == r['boundary_id'] and b['direction']+'_schema' == r['kind'] for b in bindings) for r in rules))
    if manifest is None:
        _require(structural_only is True)
    else:
        actual, actual_pins = _manifest(manifest)
        _require(actual_pins == pins and actual['entry'] == plan['route_entry']
                 and actual['graph_sha256'] == plan['graph_sha256'] and _digest(actual) == plan['manifest_sha256'])
    return plan


def validate_contract_observation_plan(plan, manifest=None, *, structural_only=False):
    """Structural validity is explicitly weaker than verified-manifest binding."""
    try:
        _require(type(structural_only) is bool)
        _plan(plan, manifest, structural_only=structural_only)
        return _admission('VALID', None, 'STRUCTURAL_ONLY' if manifest is None else 'VERIFIED_MANIFEST_BINDING')
    except _ERRORS:
        return _admission('REFUSED', 'PLAN_INVALID')


def _expected_rules(plan, binding):
    return [r for r in plan['rules'] if r['boundary_id'] == binding['boundary_id'] and r['kind'] == binding['direction']+'_schema']


def _check_identity(rule):
    return {k:rule[k] for k in ('rule_id','source_id','source_sha256','schema_sha256','provenance')}


def _unknown_reason(rule, plan):
    if rule['provenance'] == 'UNSPECIFIED':
        return 'CONTRACT_UNSPECIFIED'
    peers = {r['rule_id']:r for r in plan['rules']}
    if any(peers[x]['provenance'] == rule['provenance'] for x in rule['conflicts']):
        return 'CONTRACT_CONFLICT'
    return None


def evaluate_contract_observation(plan, *, binding_id, value, phase, anchor, invocation_id):
    """Evaluate a transient value; never return it, hash it or include error paths."""
    try:
        plan = _plan(plan, None, structural_only=True)
        _require(_id(binding_id) and type(invocation_id) is int and 1 <= invocation_id <= 128)
        bindings = [b for b in plan['bindings'] if b['binding_id'] == binding_id]
        _require(len(bindings) == 1)
        binding = bindings[0]
        expected_anchor = {k:binding[k] for k in ('file','sha256','symbol','line')}
        _require(type(phase) is str and phase == binding['phase'] and _anchor(anchor) == expected_anchor)
        checks = []
        for rule in _expected_rules(plan, binding):
            reason = _unknown_reason(rule, plan)
            if reason is None:
                reason = _applicability_reason(binding, value)
            verdict = 'UNKNOWN'
            schema_value = value
            if reason is None and _html_input(binding):
                if binding.get('applicability') != 'HTML_BOLD_TEXT_V1':
                    reason = 'CONTRACT_SCOPE_UNSUPPORTED'
                else:
                    schema_value, early_verdict, reason = _html_schema_value(value)
                    if early_verdict is not None:
                        verdict = early_verdict
            if reason is None:
                try:
                    result = ce.validate_schema(schema_value, rule['constraint'])
                    if result.get('status') == 'VALID':
                        verdict, reason = 'PASS', 'SCHEMA_MATCH'
                    elif result.get('status') == 'INVALID':
                        verdict, reason = 'FAIL', 'SCHEMA_INVALID'
                    else:
                        reason = 'SCHEMA_UNSUPPORTED_OR_BOUNDED'
                except Exception:
                    reason = 'EVALUATOR_FAILURE'
            checks.append({**_check_identity(rule), 'test_verdict':verdict,'reason_code':reason})
        return {'schema':OBSERVATION_SCHEMA,'version':1,'status':'EVALUATED',
                'plan_sha256':plan['content_digest'],'binding_id':binding_id,
                'boundary_id':binding['boundary_id'],'direction':binding['direction'],'phase':phase,
                'anchor':expected_anchor,'invocation_id':invocation_id,'checks':checks,'evidence_scope':EVIDENCE_SCOPE}
    except _ERRORS:
        return _refused(OBSERVATION_SCHEMA, 'OBSERVATION_INPUT_INVALID')


def _observation(value, plan):
    _require(type(value) is dict and set(value) == _OBSERVATION_KEYS and value['schema'] == OBSERVATION_SCHEMA)
    _require(type(value['version']) is int and value['version'] == 1 and value['status'] == 'EVALUATED')
    _require(value['plan_sha256'] == plan['content_digest'] and value['evidence_scope'] == EVIDENCE_SCOPE)
    bindings = [b for b in plan['bindings'] if b['binding_id'] == value['binding_id']]
    _require(len(bindings) == 1)
    binding = bindings[0]
    _require(all(value[k] == binding[k] for k in ('boundary_id','direction','phase')))
    _require(_anchor(value['anchor']) == {k:binding[k] for k in ('file','sha256','symbol','line')})
    _require(type(value['invocation_id']) is int and 1 <= value['invocation_id'] <= 128)
    checks, expected = value['checks'], _expected_rules(plan,binding)
    _require(type(checks) is list and len(checks) == len(expected))
    for check, rule in zip(checks, expected):
        _require(type(check) is dict and set(check) == _CHECK_KEYS)
        _require(all(check[k] == v for k,v in _check_identity(rule).items()))
        _require(type(check['test_verdict']) is str and check['test_verdict'] in _REASONS
                 and check['reason_code'] in _REASONS[check['test_verdict']])
        if check['reason_code'] == 'CONTRACT_SCOPE_UNSUPPORTED':
            _require(_plain_input(binding) or _html_input(binding))
        unknown = _unknown_reason(rule,plan)
        if unknown:
            _require(check['test_verdict'] == 'UNKNOWN' and check['reason_code'] == unknown)
    return value


def validate_contract_observations(observations, plan, *, manifest=None, fixture_sha256, runner_sha256, structural_only=False):
    """Admit metadata only. Authentic origin and runtime anchors need parent proof."""
    try:
        _require(type(structural_only) is bool)
        plan = _plan(plan,manifest,structural_only=structural_only)
        _require(_sha(fixture_sha256) and _sha(runner_sha256))
        if observations is None:
            return _admission('UNKNOWN','OBSERVATIONS_ABSENT')
        packet = _json(observations,size=PACKET_LIMIT,items=60000)
        _require(type(packet) is dict and set(packet) == _PACKET_KEYS and packet['schema'] == OBSERVATIONS_SCHEMA)
        _require(type(packet['version']) is int and packet['version'] == 1 and packet['plan'] == plan)
        _require(packet['fixture_sha256'] == fixture_sha256 and packet['runner_sha256'] == runner_sha256)
        _require(type(packet['complete']) is bool and type(packet['dropped_observations']) is int
                 and 0 <= packet['dropped_observations'] <= 10000000)
        _require(not packet['complete'] or packet['dropped_observations'] == 0)
        _require(_sha(packet['content_digest']) and observation_content_digest(packet) == packet['content_digest'])
        rows = packet['observations']; _require(type(rows) is list and len(rows) <= 128)
        seen = set(); invocations = {}
        for row in rows:
            row = _observation(row,plan)
            key = (row['binding_id'],row['invocation_id'])
            _require(key not in seen); seen.add(key)
            invocation = invocations.setdefault(row['invocation_id'],{})
            _require(row['direction'] not in invocation)
            invocation[row['direction']] = row
            if row['direction'] == 'output' and any(b['direction'] == 'input' for b in plan['bindings']):
                _require('input' in invocation or not packet['complete'])
        return _admission('VALID',None,'STRUCTURAL_ONLY' if manifest is None else 'VERIFIED_MANIFEST_BINDING')
    except _ERRORS:
        return _admission('REFUSED','OBSERVATIONS_INVALID')
