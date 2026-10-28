"""Only new deterministic contract/profile checks; no historical replay/live IO."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from tools.function_extractor.contract_engine import resolve_contracts, content_digest
from tools.function_extractor.scenario_engine import generate_scenarios

ROOT = Path(__file__).resolve().parents[3]
PROFILES = ROOT / 'tools/function_extractor/profiles'


def load_profile(name):
    return json.loads((PROFILES / ('newcontract_' + name + '.profile.json')).read_text())


def resolve_profile(name, *, authority=True):
    profile = load_profile(name)
    path = PROFILES / ('newcontract_' + name + '.rules.json')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    source = {'source_id': name + '-observations', 'kind': 'rules',
              'path': str(path.relative_to(ROOT)), 'sha256': digest}
    route = {'route_id': profile['route_id'], 'entry': profile['entry'],
             'graph_sha256': 'a' * 64,
             'source_pins': [{'path': 'backend/app/core/tenant_labels.py',
                 'sha256': hashlib.sha256((ROOT / 'backend/app/core/tenant_labels.py').read_bytes()).hexdigest()}]}
    revision = {'id': 'synthetic-unit-profile-v1', 'source_root': str(ROOT),
        'authority_bindings': [{'source_id': source['source_id'], 'sha256': digest,
           'provenance': 'OBSERVED', 'authority_ref': 'Unit test explicit code-derived observation, no normative approval'}] if authority else []}
    owner_path = ROOT / 'tools/function_extractor/contracts/owner_offline.rules.json'
    owner_sha = hashlib.sha256(owner_path.read_bytes()).hexdigest()
    owner = {'source_id': 'owner-offline', 'kind': 'rules',
        'path': str(owner_path.relative_to(ROOT)), 'sha256': owner_sha}
    revision['authority_bindings'].append({'source_id': owner['source_id'],
        'sha256': owner_sha, 'provenance': 'APPROVED_INTERNAL',
        'authority_ref': 'Direct parent-owned offline audit+seccomp invariant'})
    contract = resolve_contracts(route, [source, owner], revision)
    assert contract['status'] in ('RESOLVED', 'PARTIAL'), contract['unresolved']
    return contract, profile


def test_generation_deterministic_budget_and_no_input_mutation():
    contract, profile = resolve_profile('avl')
    before = deepcopy((contract, profile))
    budget = {'max_cases': 8, 'max_input_variants': 4}
    first = generate_scenarios(contract, profile, 1234, budget)
    assert first == generate_scenarios(contract, profile, 1234, budget)
    assert first['status'] == 'PARTIAL'
    assert len(first['cases']) == 8 and first['coverage']['omitted_by_budget'] > 0
    other = generate_scenarios(contract, profile, 4321, budget)
    assert [r['id'] for r in first['cases']] != [r['id'] for r in other['cases']]
    assert (contract, profile) == before
    assert first['coverage']['branch_total'] is None
    assert first['coverage']['business_execution_proven'] is False


def test_avl_original_role_fixtures_and_expected_values_unchanged():
    contract, profile = resolve_profile('avl')
    result = generate_scenarios(contract, profile, 0, {'max_cases': 128, 'max_input_variants': 8})
    assert result['status'] == 'GENERATED', result
    cases = {r['binding_id']: r for r in result['cases'] if r['execution_mode'] == 'REPLAY'}
    assert len(cases) == 21
    assert {'requests_http', 'canonical_v2'} <= {r['fixture'].get('stack_variant') for r in cases.values()}
    for binding in profile['bindings']:
        row = cases[binding['binding_id']]
        assert row['fixture'] == binding['fixture']
        assert row['expected'] == binding['expected']
        assert row['entry'] == binding['entry'] and row['bundle_role'] == binding['bundle_role']
        assert all(p['provenance'] == ('APPROVED_INTERNAL' if p['rule_id'] == 'owner.offline.guards' else 'OBSERVED') for p in row['provenance'])
        for key in ['fixture_digest', 'selected_rule_digest', 'case_digest']:
            assert len(row[key]) == 64


def test_unbound_schema_mutations_never_claim_target_replay():
    contract, profile = resolve_profile('tenant_labels')
    result = generate_scenarios(contract, profile, 0, {'max_cases': 128, 'max_input_variants': 8})
    shapes = [r for r in result['cases'] if r['binding_id'] is None]
    assert shapes and any(r['validation_result']['status'] == 'INVALID' for r in shapes)
    assert all(r['execution_mode'] == 'VALIDATION_ONLY' and r['expected'] is None
               and r['expected_delivery_state'] is None for r in shapes)
    assert all(r['evidence_scope'] == 'SCHEMA_VALIDATION_ONLY_NO_TARGET_EXECUTION' for r in shapes)


def test_unspecified_provenance_and_conflict_remain_unknown():
    contract, profile = resolve_profile('tenant_labels', authority=False)
    result = generate_scenarios(contract, profile)
    assert result['status'] == 'PARTIAL'
    assert all(r['execution_mode'] == 'UNKNOWN' for r in result['cases'] if r['binding_id'])
    contract, profile = resolve_profile('tenant_labels')
    # Synthetic IR conflict uses the same semantic boundary/kind.
    a = next(r for r in contract['rules'] if r['kind'] == 'semantic')
    b = deepcopy(a); b['rule_id'] = 'labels.conflicting-observation'
    b['constraint'] = {'description': 'Conflicting synthetic observation'}
    a['conflicts'], b['conflicts'] = [b['rule_id']], [a['rule_id']]
    contract['rules'].append(b)
    contract['status'] = 'PARTIAL'
    contract['unresolved'].append({'code': 'OBSERVED_OR_UNSPECIFIED_DIFFERENCE',
        'source_id': a['source_id'], 'boundary_id': a['boundary_id'], 'rule_id': a['rule_id']})
    contract['content_digest'] = content_digest(contract)
    result = generate_scenarios(contract, profile)
    assert all(r['execution_mode'] == 'UNKNOWN' for r in result['cases'] if r['binding_id'])


def test_selected_rule_and_profile_changes_invalidate_cases():
    contract, profile = resolve_profile('tenant_labels')
    first = generate_scenarios(contract, profile)
    changed = deepcopy(contract)
    changed['sources'][0]['sha256'] = 'b' * 64
    changed['content_digest'] = content_digest(changed)
    second = generate_scenarios(changed, profile)
    first_cases = {r['id']: r for r in first['cases']}
    assert first['contract_digest'] != second['contract_digest']
    changed_source = changed['sources'][0]['source_id']
    dependent = [r for r in second['cases'] if any(p['source_id'] == changed_source for p in r['provenance'])]
    unrelated = [r for r in second['cases'] if not any(p['source_id'] == changed_source for p in r['provenance'])]
    assert dependent and unrelated
    assert all(r['selected_rule_digest'] != first_cases[r['id']]['selected_rule_digest'] for r in dependent)
    assert all(r['selected_rule_digest'] == first_cases[r['id']]['selected_rule_digest'] for r in unrelated)
    altered = deepcopy(profile)
    altered['bindings'][0]['fixture']['args'] = ['artem']
    third = generate_scenarios(contract, altered)
    assert third['profile_digest'] != first['profile_digest']
    assert next(r for r in third['cases'] if r['id'] == altered['bindings'][0]['binding_id'])['case_digest'] != first_cases[altered['bindings'][0]['binding_id']]['case_digest']


@pytest.mark.parametrize('change', ['digest', 'unknown_rule', 'route', 'extra', 'seed_bool', 'budget_bool', 'expected'])
def test_invalid_inputs_refuse_closed(change):
    contract, profile = resolve_profile('tenant_labels')
    seed, budget = 0, None
    if change == 'digest': contract['content_digest'] = 'f' * 64
    elif change == 'unknown_rule': profile['bindings'][0]['rule_ids'] = ['missing']
    elif change == 'route': profile['entry'] = 'other.module:call'
    elif change == 'extra': profile['bindings'][0]['accept_anything'] = True
    elif change == 'seed_bool': seed = True
    elif change == 'budget_bool': budget = {'max_cases': True, 'max_input_variants': 1}
    elif change == 'expected': profile['bindings'][0]['expected']['guards'] = {'audit': 'yes'}
    result = generate_scenarios(contract, profile, seed, budget)
    assert result['status'] == 'REFUSED' and result['cases'] == []
    assert result['errors'] == ['SCENARIO_INPUT_INVALID']


def test_real_second_platform_function_whole_source_and_observed_expectations(tmp_path):
    from tools.function_extractor.api import freeze_source
    path = ROOT / 'backend/app/core/tenant_labels.py'
    before = path.read_bytes()
    frozen = freeze_source(ROOT / 'backend', 'app.core.tenant_labels:tenant_display_label', tmp_path / 'frozen')
    assert frozen['status'] == 'FROZEN', frozen
    import base64
    from tools.function_extractor.runner.bundle import pack_bundle
    pack_bundle(tmp_path / 'frozen', tmp_path / 'frozen/route_bundle.json')
    # Freeze creates a portable whole source bundle via the same generic engine.
    portable = json.loads((tmp_path / 'frozen/route_bundle.json').read_text())
    assert base64.b64decode(portable['sources_base64']['app/core/tenant_labels.py']) == before
    assert portable['manifest']['adapter'] is None
    spec = importlib.util.spec_from_file_location('actual_tenant_labels_unit', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract, profile = resolve_profile('tenant_labels')
    result = generate_scenarios(contract, profile)
    for case in result['cases']:
        if case['execution_mode'] != 'REPLAY': continue
        fixture = case['fixture']
        assert module.tenant_display_label(*fixture['args'], **fixture['kwargs']) == fixture['expected_result']
        assert all(p['provenance'] == ('APPROVED_INTERNAL' if p['rule_id'] == 'owner.offline.guards' else 'OBSERVED') for p in case['provenance'])
    assert path.read_bytes() == before


def test_trace_expectation_is_separate_from_independent_rules():
    contract, profile = resolve_profile('avl')
    profile['bindings'][0]['expected']['expected_status'] = 'RAISED'
    result = generate_scenarios(contract, profile, 0, {'max_cases': 128, 'max_input_variants': 0})
    row = next(r for r in result['cases'] if r['id'] == profile['bindings'][0]['binding_id'])
    assert row['execution_mode'] == 'REPLAY'
    assert row['expected']['expected_status'] == 'RAISED'
    original = next(r for r in contract['rules'] if r['rule_id'] == row['rule_ids'][0])
    assert original['constraint']['expected_status'] == 'RETURNED'


def test_schema_mutation_expectation_does_not_learn_broken_validator(monkeypatch):
    contract, profile = resolve_profile('tenant_labels')
    import tools.function_extractor.contract_engine as engine
    monkeypatch.setattr(engine, 'validate_schema', lambda value, schema: {
        'status': 'VALID', 'errors': [], 'unsupported': []})
    result = generate_scenarios(contract, profile, 0, {'max_cases': 128, 'max_input_variants': 16})
    row = next(r for r in result['cases'] if r['variant'] == 'missing_tenant_id')
    assert row['expected_schema_status'] == 'INVALID'
    assert row['validation_result']['status'] == 'VALID'
    assert row['execution_mode'] == 'VALIDATION_ONLY'
    optional = next(r for r in result['cases'] if r['variant'] == 'missing_metadata')
    assert optional['expected_schema_status'] == 'VALID'
    # Unsupported schema semantics cannot be promoted to a learned expectation.
    from tools.function_extractor.scenario_engine import _schema_expectation
    assert _schema_expectation({}, {'allOf': [{'required': ['x']}]}) == 'UNSPECIFIED'


def test_zero_shape_budget_performs_no_mutation_work(monkeypatch):
    contract, profile = resolve_profile('tenant_labels')
    import tools.function_extractor.scenario_engine as engine
    def forbidden(_):
        raise AssertionError('zero budget must not materialize shape copies')
    monkeypatch.setattr(engine, '_input_variants', forbidden)
    result = generate_scenarios(contract, profile, 0, {'max_cases': 128, 'max_input_variants': 0})
    assert result['status'] == 'GENERATED'
    assert len(result['cases']) == 7
    assert all(r['execution_mode'] == 'REPLAY' for r in result['cases'])


def test_approved_guard_subset_does_not_disable_real_bindings():
    for name in ['avl', 'tenant_labels']:
        contract, profile = resolve_profile(name)
        result = generate_scenarios(contract, profile, 0, {'max_cases': 128, 'max_input_variants': 0})
        assert result['status'] == 'GENERATED', result
        assert len(result['cases']) == len(profile['bindings'])
        guard = next(r for r in contract['rules'] if r['rule_id'] == 'owner.offline.guards')
        assert guard['provenance'] == 'APPROVED_INTERNAL'
        for case in result['cases']:
            assert case['execution_mode'] == 'REPLAY'
            assert 'owner.offline.guards' in case['rule_ids']
            assert case['expected'] != guard['constraint']  # independent subset, no equality shortcut
        assert all(r['provenance'] == 'OBSERVED' for r in contract['rules'] if r['rule_id'] != 'owner.offline.guards')


def test_credential_fields_and_known_token_patterns_refuse_before_fixture_output():
    contract, profile = resolve_profile('tenant_labels')
    samples = [(dict(authorization='synthetic'), None), (dict(bot_token='synthetic'), None),
               ({}, '123456789:' + 'A' * 35), ({}, 'Bearer synthetic-value'),
               ({}, 'https://synthetic:password@example.invalid/path')]
    for fields, value in samples:
        changed = deepcopy(profile)
        changed['bindings'][0]['fixture'].update(fields)
        if value is not None: changed['bindings'][0]['fixture']['args'] = [value]
        result = generate_scenarios(contract, changed)
        assert result == {'schema': 'function-extractor.generated-scenarios/v1',
            'version': 1, 'status': 'REFUSED', 'cases': [], 'errors': ['SCENARIO_INPUT_INVALID']}
        assert 'synthetic-value' not in json.dumps(result)
