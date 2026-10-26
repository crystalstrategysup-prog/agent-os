"""New pure lexical inventory tests. No product import, replay, provider or DB."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.function_extractor import contract_engine as ce
from tools.function_extractor import method_inventory as mi


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class MethodInventoryTests(unittest.TestCase):
    def setUp(self):
        self.sources = {'app/sample.py': b'def run():\n    api("sendMessage", {"text": "PRIVATE_NOT_OUTPUT"})\n'}
        self.policy = {'schema': 'function-extractor.method-policy/v1', 'version': 1,
            'include_prefixes': ['app'], 'dispatches': [self.dispatch()], 'declarations': []}
        self.catalog = {'schema': 'function-extractor.method-catalog/v1', 'version': 1,
            'sources': [{'id': 'facts.primary', 'primary_ref': 'https://example.invalid/PRIVATE_REF',
                'version': 'v1', 'retrieved_at': '2026-10-22', 'representation_sha256': 'e'*64,
                'representation_kind': 'selected_facts', 'trust': 'CALLER_SUPPLIED'}],
            'methods': [self.profile()]}

    def dispatch(self, **changes):
        return {'id': 'api.method', 'provider': 'telegram', 'protocol': 'BotAPI',
            'paths': ['app/sample.py'], 'callee': 'api', 'method_arg': 0,
            'method_kw': 'method', 'fixed_method': None, **changes}

    def profile(self, **changes):
        return {'provider': 'telegram', 'protocol': 'BotAPI', 'method': 'sendMessage',
            'source_ids': ['facts.primary'], 'contract_source_ids': ['ce.rules'],
            'boundary_ids': ['send.plain'], 'scope': 'PRIVATE_SCOPE https://example.invalid/user',
            'status': 'PARTIAL', 'gaps': [], **changes}

    def manifest(self):
        return {'schema': 'route-probe.bundle/v1', 'entry': 'app.sample:run', 'adapter': None,
            'files': [{'path': path, 'sha256': digest(raw), 'bytes': len(raw)} for path, raw in sorted(self.sources.items())],
            'graph_sha256': 'a'*64, 'coverage': 'BOUNDED_STATIC', 'capture_mode': 'STRICT',
            'live_send_supported': False}

    def inventory(self, **kwargs):
        return mi.inventory_methods(kwargs.pop('manifest', self.manifest()),
            kwargs.pop('sources', self.sources), kwargs.pop('policy', self.policy),
            kwargs.pop('catalog', self.catalog), **kwargs)

    def contract(self, *, provenance='APPROVED_INTERNAL', extra_rule=False):
        # Resolver is real, and filesystem preparation is test-only; inventory never reads it.
        with tempfile.TemporaryDirectory(prefix='method-contract-') as directory:
            raw = ce.canonical({'schema': 'function-extractor.rule-declarations/v1',
                'rules': [{'rule_id': 'send.rule', 'boundary_id': 'send.plain',
                    'kind': 'no_retry', 'constraint': {'max_attempts': 1}}]})
            Path(directory, 'rules.json').write_bytes(raw)
            source = {'source_id': 'ce.rules', 'kind': 'rules', 'path': 'rules.json', 'sha256': digest(raw)}
            route = {'route_id': 'route.synthetic', 'entry': self.manifest()['entry'],
                'graph_sha256': self.manifest()['graph_sha256'],
                'source_pins': [{k: p[k] for k in ('path', 'sha256')} for p in self.manifest()['files']]}
            revision = {'id': 'revision.synthetic', 'source_root': directory, 'authority_bindings': []}
            if provenance != 'UNSPECIFIED':
                revision['authority_bindings'] = [{'source_id': 'ce.rules', 'sha256': digest(raw),
                    'provenance': provenance, 'authority_ref': 'explicit-test-attestation'}]
            result = ce.resolve_contracts(route, [source], revision)
            self.assertEqual(ce.validate_contract_map(result)['status'], 'VALID')
            return result

    def assert_refused(self, value, error=None):
        self.assertEqual(value['status'], 'REFUSED', value)
        if error:
            self.assertEqual(value['errors'], [error])
        self.assertEqual(value['production_effects'], 0)
        self.assertIs(value['live_provider_observed'], False)
        self.assertIs(value['runtime_acceptance'], False)

    def test_literal_keyword_fixed_and_referential_callsites(self):
        self.sources['app/sample.py'] = b'class Client:\n def run(self):\n  api("sendMessage")\n  api(method="getWebhookInfo")\n  SendMessageRequest(peer="PRIVATE")\n'
        self.policy['dispatches'].append(self.dispatch(id='mt.fixed', protocol='MTProto',
            callee='SendMessageRequest', method_arg=None, method_kw=None, fixed_method='messages.sendMessage'))
        out = self.inventory()
        self.assertEqual([(m['protocol'], m['method']) for m in out['methods']],
            [('BotAPI', 'getWebhookInfo'), ('BotAPI', 'sendMessage'), ('MTProto', 'messages.sendMessage')])
        self.assertEqual(len({r['id'] for r in out['callsites']}), 3)
        self.assertTrue(all(r['symbol'] == 'Client.run' for r in out['callsites']))
        ids = {r['id'] for r in out['callsites']}
        self.assertTrue(all(set(m['callsite_ids']) <= ids for m in out['methods']))
        self.assertEqual(len(out['proposals']), 2)
        self.assertTrue(all(p['expected'] is None and p['status'] == 'PROPOSED' for p in out['proposals']))
        self.assertNotIn('PRIVATE', json.dumps(out))

    def test_dynamic_and_ambiguous_never_export_source_expressions(self):
        self.sources['app/sample.py'] = b'api(secret_method)\napi("send"+"Message")\napi(*args)\napi(**kwargs)\napi("sendMessage",method="getMe")\napi()\napi("https://SECRET.invalid")\n'
        out = self.inventory()
        self.assertEqual(out['methods'], [])
        self.assertEqual(len(out['unresolved']), 7)
        self.assertTrue(all(c['status'] == 'UNRESOLVED' for c in out['callsites']))
        for text in ('secret_method', 'SECRET', 'https://', 'args', 'kwargs'):
            self.assertNotIn(text, json.dumps(out))

    def test_declarations_are_not_dispatch_or_profile_requests(self):
        self.sources['app/sample.py'] = b'METHODS=frozenset({"sendMessage","getMe"})\n'
        self.policy['declarations'] = [{'id': 'caps', 'provider': 'telegram', 'protocol': 'BotAPI',
            'paths': ['app/sample.py'], 'symbol': 'METHODS'}]
        out = self.inventory()
        self.assertEqual(out['methods'], [])
        self.assertEqual(out['callsites'], [])
        self.assertEqual(out['capabilities'][0]['methods'], ['getMe', 'sendMessage'])
        self.assertEqual(out['capabilities'][0]['status'], 'STATIC_POSSIBLE_NOT_DISPATCH')
        self.sources['app/sample.py'] += b'METHODS += supplied\n'
        self.assertEqual(self.inventory()['capabilities'], [])
        self.assertEqual(self.inventory()['unresolved'][0]['kind'], 'DECLARATION')

    def test_lexical_defaults_and_decorators_are_discovered_not_executed(self):
        self.sources['app/sample.py'] = b'@api("getMe")\ndef run(arg=api("sendMessage")):\n pass\n'
        out = self.inventory()
        self.assertEqual({m['method'] for m in out['methods']}, {'sendMessage', 'getMe'})

    def test_protocol_and_provider_keep_same_method_separate(self):
        self.sources['app/sample.py'] = b'api("sendMessage")\nother("sendMessage")\n'
        self.policy['dispatches'].append(self.dispatch(id='other', provider='other', protocol='MTProto', callee='other'))
        self.assertEqual(len(self.inventory()['methods']), 2)

    def test_duplicate_rule_ids_refuse_overlap_is_unresolved(self):
        self.policy['dispatches'].append(copy.deepcopy(self.policy['dispatches'][0]))
        self.assert_refused(self.inventory(), 'POLICY_INVALID')
        self.policy['dispatches'][1]['id'] = 'other'
        out = self.inventory()
        self.assertEqual(out['callsites'][0]['reason'], 'DISPATCH_POLICY_AMBIGUOUS')
        self.assertEqual(out['methods'], [])

    def test_manifest_pin_type_hash_size_and_source_set_refuse(self):
        for kind in ('hash', 'size', 'missing', 'extra', 'bytearray', 'duplicate'):
            manifest = self.manifest(); sources = dict(self.sources)
            if kind == 'hash': manifest['files'][0]['sha256'] = '0'*64
            if kind == 'size': manifest['files'][0]['bytes'] += 1
            if kind == 'missing': sources.clear()
            if kind == 'extra': sources['app/extra.py'] = b''
            if kind == 'bytearray': sources['app/sample.py'] = bytearray(sources['app/sample.py'])
            if kind == 'duplicate': manifest['files'].append(dict(manifest['files'][0]))
            with self.subTest(kind=kind): self.assert_refused(self.inventory(manifest=manifest, sources=sources))

    def test_unsafe_paths_and_identifiers_refuse_without_echo(self):
        for path in ('../escape.py', '/app/file.py', 'app//file.py', 'app/credentials.json/file.py', 'app/.env/file.py', 'app/session-data.py'):
            self.sources = {path: b'api("sendMessage")'}
            with self.subTest(path=path): self.assert_refused(self.inventory())
        self.setUp()
        for field in ('callee', 'fixed_method', 'provider'):
            policy = copy.deepcopy(self.policy); policy['dispatches'][0][field] = 'https://PRIVATE.invalid'
            with self.subTest(field=field):
                out = self.inventory(policy=policy); self.assert_refused(out); self.assertNotIn('PRIVATE', json.dumps(out))

    def test_parse_failure_does_not_echo_source_or_exception(self):
        self.sources['app/sample.py'] = b'api("PRIVATE_SYNTAX"\n'
        out = self.inventory(); self.assert_refused(out, 'SOURCE_PARSE_FAILED')
        self.assertNotIn('PRIVATE_SYNTAX', json.dumps(out))

    def test_resource_bounds_refuse_without_partial_truncation_or_widening(self):
        for budget in ({'max_callsites': 1}, {'max_ast_nodes': 1}, {'max_source_bytes': 1}, {'max_file_bytes': 1}):
            self.sources['app/sample.py'] = b'api("sendMessage")\napi("getMe")\n'
            with self.subTest(budget=budget): self.assert_refused(self.inventory(budget=budget))
        for budget in ({'max_callsites': 2001}, {'max_ast_nodes': True}, {'unknown': 1}, {'max_files': 0}):
            with self.subTest(budget=budget): self.assert_refused(self.inventory(budget=budget), 'BUDGET_INVALID')

    def test_no_fs_import_execution_eval_or_product_expression(self):
        self.sources['app/sample.py'] = b'import never_import_this_product\nraise RuntimeError("NEVER")\napi(build_method())\n'
        with patch('builtins.open', side_effect=AssertionError('FS forbidden')), \
             patch('builtins.__import__', side_effect=AssertionError('import forbidden')), \
             patch('builtins.eval', side_effect=AssertionError('eval forbidden')), \
             patch('builtins.exec', side_effect=AssertionError('exec forbidden')):
            out = self.inventory()
        self.assertEqual(out['callsites'][0]['reason'], 'DYNAMIC_METHOD_SELECTOR')

    def test_explicit_catalog_ce_namespaces_partial_and_observation_not_upgrade(self):
        for provenance in ('APPROVED_INTERNAL', 'OBSERVED', 'UNSPECIFIED'):
            contract = self.contract(provenance=provenance)
            out = self.inventory(contract_map=contract)
            method = out['methods'][0]
            with self.subTest(provenance=provenance):
                self.assertNotEqual(method['contract_status'], 'PROFILE_PRESENT')
                self.assertEqual(method['source_ids'], ['facts.primary'])
                self.assertEqual(method['contract_source_ids'], ['ce.rules'])
                self.assertEqual(method['rule_refs'][0]['source_id'], 'ce.rules')
                self.assertEqual(method['rule_refs'][0]['provenance'], provenance)
        self.assertEqual(self.inventory()['methods'][0]['contract_status'], 'CONTRACT_GAP')

    def test_declared_catalog_gap_never_upgrades_even_with_rules(self):
        self.catalog['methods'][0].update(status='CONTRACT_GAP', gaps=['wire_not_observed'])
        method = self.inventory(contract_map=self.contract())['methods'][0]
        self.assertEqual(method['contract_status'], 'CONTRACT_GAP')
        self.assertEqual(len(method['rule_refs']), 1)
        self.assertIn('CATALOG_DECLARED_GAPS', method['gaps'])

    def test_foreign_entry_graph_and_full_source_pin_set_refuse(self):
        self.sources['app/unmatched.py'] = b'value=1\n'
        contract = self.contract()
        for kind in ('entry', 'graph', 'sha', 'missing', 'extra'):
            other = copy.deepcopy(contract)
            if kind == 'entry': other['route']['entry'] = 'other:run'
            if kind == 'graph': other['route']['graph_sha256'] = 'f'*64
            if kind == 'sha': other['route']['source_pins'][0]['sha256'] = 'f'*64
            if kind == 'missing': other['route']['source_pins'].pop()
            if kind == 'extra': other['route']['source_pins'].append({'path': 'extra.py', 'sha256': 'f'*64})
            other['content_digest'] = ce.content_digest(other)
            self.assertEqual(ce.validate_contract_map(other)['status'], 'VALID')
            with self.subTest(kind=kind): self.assert_refused(self.inventory(contract_map=other), 'MAP_SOURCE_BINDING')

    def test_contract_source_and_boundary_mappings_are_exact(self):
        contract = self.contract()
        for changes in ({'contract_source_ids': []}, {'contract_source_ids': ['facts.primary']}, {'boundary_ids': []}, {'boundary_ids': ['different']}):
            catalog = copy.deepcopy(self.catalog); catalog['methods'][0].update(changes)
            with self.subTest(changes=changes):
                method = self.inventory(catalog=catalog, contract_map=contract)['methods'][0]
                self.assertEqual(method['contract_status'], 'CONTRACT_GAP')
        bad = copy.deepcopy(contract); bad['rules'][0]['source_id'] = 'missing'; bad['content_digest'] = ce.content_digest(bad)
        self.assert_refused(self.inventory(contract_map=bad), 'CONTRACT_MAP_INVALID')

    def test_catalog_reference_duplicates_and_strict_version_refuse(self):
        for kind in ('missing', 'duplicate', 'version', 'source_identifier'):
            catalog = copy.deepcopy(self.catalog)
            if kind == 'missing': catalog['methods'][0]['source_ids'] = ['absent']
            if kind == 'duplicate': catalog['methods'].append(dict(catalog['methods'][0]))
            if kind == 'version': catalog['version'] = True
            if kind == 'source_identifier': catalog['methods'][0]['contract_source_ids'] = ['https://PRIVATE']
            with self.subTest(kind=kind): self.assert_refused(self.inventory(catalog=catalog))

    def test_free_scope_gaps_urls_arguments_and_ce_constraints_are_redacted(self):
        self.catalog['methods'][0]['gaps'] = ['PRIVATE_GAP https://PRIVATE.invalid/resident']
        out = self.inventory(contract_map=self.contract())
        encoded = json.dumps(out)
        for text in ('PRIVATE', 'https://', 'max_attempts', 'primary_ref', 'representation_kind'):
            self.assertNotIn(text, encoded)
        self.assertEqual(out['methods'][0]['scope'], 'CATALOG_SCOPE_RECORDED_BY_DIGEST')
        self.assertEqual(len(out['methods'][0]['scope_sha256']), 64)
        self.assertEqual(len(out['methods'][0]['gap_text_digest']), 64)

    def test_deterministic_digests_and_pin_bound_callsite_identity(self):
        before = copy.deepcopy(self.sources); first = self.inventory(); self.assertEqual(first, self.inventory())
        self.assertEqual(before, self.sources)
        self.assertEqual(first['content_digest'], mi._digest({k:v for k,v in first.items() if k != 'content_digest'}))
        self.sources['app/sample.py'] += b'# source revision\n'
        second = self.inventory()
        self.assertNotEqual(first['input_digests']['source_pins'], second['input_digests']['source_pins'])
        self.assertNotEqual(first['callsites'][0]['id'], second['callsites'][0]['id'])
        self.catalog['methods'][0]['scope'] += ' changed'
        third = self.inventory(); self.assertNotEqual(second['content_digest'], third['content_digest'])

    def test_map_digest_change_invalidates_and_partial_capture_never_complete(self):
        contract = self.contract(); first = self.inventory(contract_map=contract)
        contract['revision'] = 'revision.two'; contract['content_digest'] = ce.content_digest(contract)
        second = self.inventory(contract_map=contract)
        self.assertNotEqual(first['input_digests']['contract_map'], second['input_digests']['contract_map'])
        manifest = self.manifest(); manifest['capture_mode'] = 'PARTIAL_STATIC'
        self.assertEqual(self.inventory(manifest=manifest, contract_map=contract)['status'], 'PARTIAL')
        self.assertIsNone(second['coverage']['whole_program_denominator'])
        self.assertEqual(second['coverage']['whole_program_status'], 'UNKNOWN')
        self.assertEqual(second['production_effects'], 0)
        self.assertIs(second['live_provider_observed'], False)
        self.assertIs(second['runtime_acceptance'], False)

    def test_exact_path_namespaces_not_implicitly_aliased(self):
        self.policy['dispatches'][0]['paths'] = ['backend/app/sample.py']
        out = self.inventory()
        self.assertEqual(out['methods'], [])
        self.assertEqual(out['unresolved'][0]['reason'], 'SOURCE_NOT_IN_SELECTED_MANIFEST')
        self.policy['dispatches'][0]['paths'].append('app/sample.py')
        self.assertEqual(self.inventory()['methods'][0]['method'], 'sendMessage')

    def test_profile_present_with_declared_gaps_remains_partial(self):
        self.catalog['methods'][0].update(status='PROFILE_PRESENT', gaps=['not_yet_observed'])
        out = self.inventory(contract_map=self.contract())
        self.assertEqual(out['methods'][0]['catalog_status'], 'PROFILE_PRESENT')
        self.assertEqual(out['methods'][0]['contract_status'], 'PARTIAL')
        self.assertIn('CATALOG_DECLARED_GAPS', out['methods'][0]['gaps'])
        self.assertEqual(out['status'], 'PARTIAL')
        self.assertEqual(out['coverage']['selected_policy_file_count'], 1)
        self.catalog['methods'][0]['status'] = 'CONTRACT_GAP'
        self.assertEqual(self.inventory(contract_map=self.contract())['methods'][0]['contract_status'], 'CONTRACT_GAP')

    def test_zero_selected_policy_files_is_partial_not_method_absence_proof(self):
        self.policy.update(dispatches=[], declarations=[])
        out = self.inventory()
        self.assertEqual(out['status'], 'PARTIAL')
        self.assertEqual(out['coverage']['selected_policy_file_count'], 0)
        self.assertEqual(out['coverage']['parsed_files'], [])
        self.assertEqual(out['coverage']['excluded_files'], ['app/sample.py'])
        self.assertEqual(out['methods'], [])
        self.assertIsNone(out['coverage']['whole_program_denominator'])
        self.assertEqual(out['coverage']['whole_program_status'], 'UNKNOWN')

    def test_policy_provider_and_protocol_must_match_catalog_dotted_names(self):
        for field in ('provider', 'protocol'):
            policy = copy.deepcopy(self.policy)
            policy['dispatches'][0][field] = 'vendor:alpha'
            with self.subTest(field=field):
                self.assert_refused(self.inventory(policy=policy), 'POLICY_INVALID')
        self.policy['dispatches'][0]['id'] = 'rule:allowed'
        self.policy['dispatches'][0]['provider'] = 'vendor.alpha'
        out = self.inventory()
        self.assertEqual(out['methods'][0]['provider'], 'vendor.alpha')
        self.assertEqual(out['callsites'][0]['policy_ids'], ['rule:allowed'])

    def test_capability_method_count_refuses_129_and_shrunken_budget_without_truncation(self):
        self.policy['declarations'] = [{'id': 'caps', 'provider': 'telegram', 'protocol': 'BotAPI',
            'paths': ['app/sample.py'], 'symbol': 'METHODS'}]
        self.sources['app/sample.py'] = ('METHODS=' + repr(['method' + str(i) for i in range(129)])).encode()
        self.assert_refused(self.inventory(), 'RESOURCE_BOUND')
        self.sources['app/sample.py'] = b'METHODS=["getMe","sendMessage"]'
        self.assert_refused(self.inventory(budget={'max_methods': 1}), 'RESOURCE_BOUND')
        out = self.inventory(budget={'max_methods': 2})
        self.assertEqual(out['capabilities'][0]['methods'], ['getMe', 'sendMessage'])
        self.assertEqual(out['coverage']['requested_method_count'], 0)
