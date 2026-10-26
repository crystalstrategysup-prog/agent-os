"""Deterministic contract-bound scenarios; no execution or learned expectations."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re

_SCHEMA = 'function-extractor.generated-scenarios/v1'
_PROFILE = 'function-extractor.scenario-profile/v1'
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
_CREDENTIAL_FIELDS = {'token', 'bot_token', 'access_token', 'refresh_token',
    'authorization', 'proxy_authorization', 'password', 'passwd', 'secret',
    'api_key', 'client_secret', 'cookie', 'cookies', 'set_cookie', 'credentials',
    'credential', 'session_key', 'session_string', 'session_file', 'private_key'}
_TOKEN_VALUE = re.compile(r'(?:[0-9]{6,14}:[A-Za-z0-9_-]{30,}|eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|Bearer\s+\S+|-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----|https?://[^/\s:@]+:[^/\s@]+@)', re.IGNORECASE)
_DELIVERY = {None, 'sent', 'delivered', 'queued', 'pending', 'sending', 'unknown',
             'failed', 'partial', 'retry_wait', 'not_applicable'}


def _json(value):
    remaining = [50000]
    def visit(item, depth=0):
        remaining[0] -= 1
        if remaining[0] < 0 or depth > 30:
            raise ValueError('SCENARIO_BOUND')
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                visit(child, depth + 1)
            return
        if type(item) is dict and all(type(k) is str and len(k) <= 256 for k in item):
            for child in item.values():
                visit(child, depth + 1)
            return
        raise ValueError('SCENARIO_JSON')
    visit(value)
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode()
    if len(data) > 1_000_000:
        raise ValueError('SCENARIO_BOUND')
    return json.loads(data)



def _reject_credentials(value):
    """Closed credential-field/token-pattern refusal, not a general PII detector."""
    if type(value) is dict:
        for key, child in value.items():
            if key.lower().replace('-', '_') in _CREDENTIAL_FIELDS:
                raise ValueError('SCENARIO_CREDENTIAL_INPUT')
            _reject_credentials(child)
    elif type(value) is list:
        for child in value:
            _reject_credentials(child)
    elif type(value) is str and _TOKEN_VALUE.search(value):
        raise ValueError('SCENARIO_CREDENTIAL_INPUT')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _profile(value, route):
    required = {'schema', 'version', 'profile_id', 'route_id', 'entry', 'bindings'}
    if (type(value) is not dict or set(value) - required - {'input_seed'}
            or not required <= set(value) or value['schema'] != _PROFILE
            or type(value['version']) is not int or value['version'] != 1
            or not _ID.fullmatch(value['profile_id'])
            or value['route_id'] != route['route_id'] or value['entry'] != route['entry']
            or type(value['bindings']) is not list or not 1 <= len(value['bindings']) <= 128):
        raise ValueError('SCENARIO_PROFILE')
    seen = set()
    for row in value['bindings']:
        keys = {'binding_id', 'variant', 'rule_ids', 'fixture', 'expected',
                'expected_delivery_state', 'evidence_scope'}
        if (type(row) is not dict or not keys <= set(row)
                or set(row) - keys - {'bundle_role', 'entry', 'observation_expectations'}
                or type(row['binding_id']) is not str or not _ID.fullmatch(row['binding_id'])
                or row['binding_id'] in seen or type(row['variant']) is not str
                or not _ID.fullmatch(row['variant']) or type(row['fixture']) is not dict
                or type(row['expected']) is not dict
                or row['expected'].get('schema') != 'function-extractor.contract/v1'
                or type(row['expected'].get('version')) is not int or row['expected']['version'] != 1
                or ('entry' in row and (type(row['entry']) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_.]*', row['entry'])))
                or row['expected_delivery_state'] not in _DELIVERY
                or type(row['rule_ids']) is not list or not 1 <= len(row['rule_ids']) <= 32
                or any(type(x) is not str for x in row['rule_ids'])
                or len(set(row['rule_ids'])) != len(row['rule_ids'])
                or type(row['evidence_scope']) is not str or not 1 <= len(row['evidence_scope']) <= 512
                or ('bundle_role' in row and (type(row['bundle_role']) is not str
                    or not _ID.fullmatch(row['bundle_role'])))):
            raise ValueError('SCENARIO_BINDING')
        from .api import _contract
        _contract(row['expected'])
        seen.add(row['binding_id'])


def _input_variants(value):
    """Closed shape mutations; not a substitute for a callable binding."""
    variants = [('null', None), ('wrong_container', []), ('empty_object', {})]
    if type(value) is dict:
        for key in sorted(value)[:16]:
            missing = deepcopy(value); missing.pop(key)
            wrong = deepcopy(value); wrong[key] = [] if type(value[key]) is not list else {}
            variants.extend([('missing_' + key, missing), ('wrong_type_' + key, wrong)])
    return variants



def _schema_expectation(value, schema, depth=0):
    """Independent narrow mutation oracle, never an observed validator result.

    Only elementary type/object/enum semantics are proved. Richer schemas stay
    UNSPECIFIED rather than learning an expectation from validate_schema().
    """
    if type(schema) is bool:
        return 'VALID' if schema else 'INVALID'
    if (depth > 16 or type(schema) is not dict
            or set(schema) - {'type', 'enum', 'properties', 'required', 'additionalProperties'}):
        return 'UNSPECIFIED'
    kinds = {'object': type(value) is dict, 'array': type(value) is list,
             'string': type(value) is str, 'boolean': type(value) is bool,
             'null': value is None, 'integer': type(value) is int or (type(value) is float and value.is_integer()),
             'number': type(value) in (int, float)}
    declared = schema.get('type')
    if declared is not None:
        allowed = [declared] if type(declared) is str else declared
        if type(allowed) is not list or not allowed or any(type(k) is not str or k not in kinds for k in allowed):
            return 'UNSPECIFIED'
        if not any(kinds[k] for k in allowed):
            return 'INVALID'
    if 'enum' in schema:
        choices = schema['enum']
        if type(choices) is not list or not choices or any(type(x) not in (str, bool, type(None)) for x in choices):
            return 'UNSPECIFIED'
        if not any(type(value) is type(x) and value == x for x in choices):
            return 'INVALID'
    if type(value) is dict:
        properties = schema.get('properties', {})
        required = schema.get('required', [])
        additional = schema.get('additionalProperties', True)
        if (type(properties) is not dict or type(required) is not list
                or any(type(x) is not str for x in required) or type(additional) is not bool):
            return 'UNSPECIFIED'
        if any(key not in value for key in required) or (not additional and set(value) - set(properties)):
            return 'INVALID'
        states = [_schema_expectation(v, properties[k], depth + 1)
                  for k, v in value.items() if k in properties]
        if 'INVALID' in states:
            return 'INVALID'
        if 'UNSPECIFIED' in states:
            return 'UNSPECIFIED'
    return 'VALID'


def generate_scenarios(contract_map, profile, seed=0, budget=None):
    """Return deterministic fixtures plus honest validation-only shape variants.

    REPLAY is a binding classification, not a successful execution. The caller
    must run each fixture through its separately verified original-source bundle.
    """
    try:
        from .contract_engine import validate_contract_map, validate_schema, selected_rule_digest
        contract_map, profile = _json(contract_map), _json(profile)
        _reject_credentials(contract_map)
        _reject_credentials(profile)
        checked = validate_contract_map(contract_map)
        if checked.get('status') != 'VALID' or contract_map.get('status') == 'REFUSED':
            raise ValueError('SCENARIO_CONTRACT')
        if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
            raise ValueError('SCENARIO_SEED')
        budget = _json({'max_cases': 64, 'max_input_variants': 16} if budget is None else budget)
        if (type(budget) is not dict or set(budget) != {'max_cases', 'max_input_variants'}
                or type(budget['max_cases']) is not int or not 1 <= budget['max_cases'] <= 128
                or type(budget['max_input_variants']) is not int
                or not 0 <= budget['max_input_variants'] <= 32):
            raise ValueError('SCENARIO_BUDGET')
        route = contract_map['route']; _profile(profile, route)
        rules = {r['rule_id']: r for r in contract_map['rules']}
        rows = []
        for binding in profile['bindings']:
            if any(key not in rules for key in binding['rule_ids']):
                raise ValueError('SCENARIO_RULE_REFERENCE')
            selected = [rules[key] for key in binding['rule_ids']]
            observations = binding.get('observation_expectations', {})
            eligible = {r['rule_id'] for r in selected if r['kind'] in {'input_schema','output_schema'}}
            if (type(observations) is not dict or not set(observations) <= eligible
                    or any(type(v) is not str or v not in {'PASS','FAIL'} for v in observations.values())):
                raise ValueError('SCENARIO_OBSERVATION_EXPECTATION')
            unknown = any(r['conflicts'] or r['provenance'] == 'UNSPECIFIED' for r in selected)
            row = {'id': binding['binding_id'], 'entry': binding.get('entry', route['entry']),
                'binding_id': binding['binding_id'], 'variant': binding['variant'],
                'rule_ids': binding['rule_ids'], 'provenance': [
                    {k: r[k] for k in ('rule_id', 'source_id', 'provenance')} for r in selected],
                'execution_mode': 'UNKNOWN' if unknown else 'REPLAY',
                'fixture': binding['fixture'], 'fixture_digest': _digest(binding['fixture']),
                'expected': binding['expected'],
                'expected_delivery_state': binding['expected_delivery_state'],
                'evidence_scope': binding['evidence_scope']}
            if 'bundle_role' in binding:
                row['bundle_role'] = binding['bundle_role']
            if 'observation_expectations' in binding:
                row['observation_expectations'] = deepcopy(observations)
            rows.append(row)
        if 'input_seed' in profile:
            remaining_variants = budget['max_input_variants']
            for rule in contract_map['rules']:
                if remaining_variants <= 0:
                    break
                if rule['kind'] != 'input_schema':
                    continue
                schema = rule['constraint']
                for variant, value in _input_variants(profile['input_seed'])[:remaining_variants]:
                    remaining_variants -= 1
                    # These boundary schemas describe a qualified transient
                    # value. A schema-only fixture has no captured formatting
                    # applicability/projection proof; raw HTML length is not
                    # Telegram's after-parsing length. Never manufacture an
                    # INVALID (or PASS) by bypassing the observation evaluator.
                    scope_missing = (rule['boundary_id'] == 'telegram.sendMessage.html.bold'
                        or (rule['boundary_id'] == 'telegram.sendMessage.plain'
                            and type(value) is dict and ('parse_mode' in value or 'entities' in value)))
                    check = ({'status':'UNKNOWN','errors':[],
                              'unsupported':['CONTRACT_CAPTURE_APPLICABILITY_REQUIRED']}
                             if scope_missing else validate_schema(value, schema))
                    rows.append({'id': 'shape-' + _digest([rule['rule_id'], variant])[:16],
                        'entry': route['entry'], 'binding_id': None, 'variant': variant,
                        'rule_ids': [rule['rule_id']], 'provenance': [
                            {k: rule[k] for k in ('rule_id', 'source_id', 'provenance')}],
                        'execution_mode': 'VALIDATION_ONLY' if check.get('status') in ('VALID', 'INVALID') else 'UNKNOWN',
                        'fixture': {'input': value}, 'fixture_digest': _digest({'input': value}),
                        'expected': None, 'expected_delivery_state': None,
                        'expected_schema_status': 'UNSPECIFIED' if scope_missing else _schema_expectation(value, schema),
                        'validation_result': check, 'evidence_scope': 'SCHEMA_VALIDATION_ONLY_NO_TARGET_EXECUTION'})
        for row in rows:
            row['selected_rule_digest'] = selected_rule_digest(contract_map, row['rule_ids'])
            row['source_pins'] = deepcopy(route['source_pins'])
            row['case_digest'] = _digest(row)
        rows.sort(key=lambda r: (_digest([seed, r['id']]), r['id']))
        total = len(rows); selected_rows = rows[:budget['max_cases']]
        output = {'schema': _SCHEMA, 'version': 1,
            'status': 'PARTIAL' if total > len(selected_rows) or any(r['execution_mode'] == 'UNKNOWN' for r in selected_rows) else 'GENERATED',
            'route_id': route['route_id'], 'entry': route['entry'],
            'contract_digest': contract_map['content_digest'], 'profile_digest': _digest(profile),
            'seed': seed, 'budget': budget, 'cases': selected_rows,
            'coverage': {'generated_candidates': total, 'selected_cases': len(selected_rows),
                'omitted_by_budget': total - len(selected_rows),
                'rule_ids': sorted({k for row in selected_rows for k in row['rule_ids']}),
                'branch_total': None, 'business_execution_proven': False}}
        output['content_digest'] = _digest(output)
        return _json(output)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        return {'schema': _SCHEMA, 'version': 1, 'status': 'REFUSED',
                'cases': [], 'errors': ['SCENARIO_INPUT_INVALID']}
