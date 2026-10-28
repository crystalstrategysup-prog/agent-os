"""Finite public profile data checks; product modules are parsed, never imported."""
import ast
import json
import re
import unittest
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / 'tools/function_extractor/contracts'
CATALOG = json.loads((CONTRACTS / 'telegram_methods.catalog.json').read_text())
POLICY = json.loads((CONTRACTS / 'method_discovery.policy.json').read_text())


@lru_cache(None)
def source_tree(relative):
    path = ROOT / ('backend/' + relative if relative.startswith('app/') else relative)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
        raise AssertionError('unsafe_selected_source')
    data = path.read_bytes()
    if len(data) > 1_000_000:
        raise AssertionError('selected_source_bound')
    return ast.parse(data)


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + '.' + node.attr if base else None
    return None


def selected_method(rule, call):
    if rule['fixed_method'] is not None:
        return rule['fixed_method']
    arguments = []
    pos = rule['method_arg']
    if pos is not None and len(call.args) > pos:
        arguments.append(call.args[pos])
    arguments.extend(k.value for k in call.keywords if k.arg == rule['method_kw'])
    if len(arguments) != 1:
        return None
    value = arguments[0]
    return value.value if isinstance(value, ast.Constant) and type(value.value) is str else None


class MethodCatalogTests(unittest.TestCase):
    def test_closed_catalog_and_unique_protocol_identity(self):
        self.assertEqual(set(CATALOG), {'schema', 'version', 'sources', 'methods'})
        self.assertEqual(CATALOG['schema'], 'function-extractor.method-catalog/v1')
        self.assertEqual(CATALOG['version'], 1)
        self.assertEqual(len(CATALOG['methods']), 22)
        identities = []
        for row in CATALOG['methods']:
            self.assertEqual(set(row), {'provider','protocol','method','source_ids','contract_source_ids','boundary_ids','scope','status','gaps'})
            self.assertEqual(row['provider'], 'telegram')
            self.assertIn(row['protocol'], {'BotAPI', 'MTProto'})
            self.assertRegex(row['method'], r'^[A-Za-z][A-Za-z0-9_.]*$')
            self.assertTrue(row['source_ids'])
            self.assertTrue(row['gaps'])
            identities.append((row['provider'], row['protocol'], row['method']))
        self.assertEqual(len(set(identities)), len(identities))

    def test_exact_finite_bnt_union_is_not_delivery_allowlist(self):
        tree = source_tree('backend/app/ingest/telegram_basic_native_transport.py')
        declarations = {}
        arguments = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name in {'_DELIVERY_METHODS', '_PROBE_METHODS'}:
                    self.assertIsInstance(node.value, ast.Call)
                    self.assertEqual(dotted(node.value.func), 'frozenset')
                    declarations[name] = set(ast.literal_eval(node.value.args[0]))
                if name == '_ARGUMENTS':
                    self.assertIsInstance(node.value, ast.Dict)
                    arguments = {x.value for x in node.value.keys}
        # Later top-level literal assignments and the finite media loop extend
        # the initial dict. Read only syntax; never evaluate product expressions.
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Subscript) and dotted(target.value) == '_ARGUMENTS' and isinstance(target.slice, ast.Constant):
                        self.assertIs(type(target.slice.value), str)
                        arguments.add(target.slice.value)
            if isinstance(node, ast.For) and isinstance(node.target, ast.Tuple):
                if [dotted(x) for x in node.target.elts] == ['_method', '_media']:
                    self.assertTrue(any(isinstance(x, ast.Assign) and any(isinstance(t, ast.Subscript) and dotted(t.value) == '_ARGUMENTS' and dotted(t.slice) == '_method' for t in x.targets) for x in node.body))
                    pairs = ast.literal_eval(node.iter)
                    self.assertTrue(all(type(x) is tuple and len(x) == 2 and all(type(v) is str for v in x) for x in pairs))
                    arguments.update(x[0] for x in pairs)
        methods = {x['method'] for x in CATALOG['methods'] if x['protocol'] == 'BotAPI'}
        self.assertEqual(len(declarations['_DELIVERY_METHODS']), 15)
        self.assertEqual(len(declarations['_PROBE_METHODS']), 4)
        self.assertEqual(methods, declarations['_DELIVERY_METHODS'] | declarations['_PROBE_METHODS'] | {'getFile','setWebhook'})
        self.assertEqual(methods, arguments)
        self.assertNotIn('setWebhook', declarations['_PROBE_METHODS'])
        self.assertNotIn('deleteMessages', methods)
        self.assertNotEqual(methods, declarations['_DELIVERY_METHODS'])

    def test_sources_bind_reviewed_representation_not_html(self):
        # Reviewed selected-facts representation pin, not raw official HTML.
        # The audit sidecar is external evidence, not a checkout test dependency.
        representation_sha256 = '0ec158fb3a43a7cbf413585fe69d4be7837698a4020b7adba2120e7198b87fc6'
        sources = {x['id']: x for x in CATALOG['sources']}
        self.assertEqual(len(sources), 2)
        for source in sources.values():
            self.assertEqual(set(source), {'id','primary_ref','version','retrieved_at','representation_sha256','representation_kind','trust'})
            self.assertEqual(source['representation_sha256'], representation_sha256)
            self.assertEqual(source['retrieved_at'], '2026-10-22')
            self.assertIn('NOT-raw-HTML', source['representation_kind'])
            self.assertEqual(source['trust'], 'OFFICIAL')
        for row in CATALOG['methods']:
            self.assertTrue(set(row['source_ids']) <= sources.keys())
            for source_id in row['source_ids']:
                expected = 'https://core.telegram.org/bots/api' if row['protocol'] == 'BotAPI' else 'https://core.telegram.org/method/messages.sendMessage'
                self.assertEqual(sources[source_id]['primary_ref'], expected)

    def test_only_existing_scoped_sendmessage_is_partial(self):
        existing = json.loads((CONTRACTS / 'telegram_sendmessage.rules.json').read_text())
        boundaries = {x['boundary_id'] for x in existing['boundaries']}
        rule_boundaries = {x['boundary_id'] for x in existing['rules']}
        for row in CATALOG['methods']:
            if row['protocol'] == 'BotAPI' and row['method'] == 'sendMessage':
                self.assertEqual(row['status'], 'PARTIAL')
                self.assertEqual(row['contract_source_ids'], ['telegram-sendmessage-subset'])
                self.assertNotIn('telegram-sendmessage-subset', row['source_ids'])
                self.assertEqual(set(row['boundary_ids']), boundaries)
                self.assertTrue(set(row['boundary_ids']) <= rule_boundaries)
            else:
                self.assertEqual(row['status'], 'CONTRACT_GAP')
                self.assertEqual(row['contract_source_ids'], [])
                self.assertEqual(row['boundary_ids'], [])
        self.assertNotIn('PROFILE_PRESENT', {x['status'] for x in CATALOG['methods']})

    def test_closed_selectors_and_selected_paths(self):
        self.assertEqual(set(POLICY), {'schema','version','include_prefixes','dispatches','declarations'})
        self.assertEqual(POLICY['schema'], 'function-extractor.method-policy/v1')
        self.assertEqual(POLICY['version'], 1)
        ids = []
        for rule in POLICY['dispatches']:
            self.assertEqual(set(rule), {'id','provider','protocol','paths','callee','method_arg','method_kw','fixed_method'})
            ids.append(rule['id'])
            self.assertRegex(rule['callee'], r'^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$')
            selector = rule['method_arg'] is not None or rule['method_kw'] is not None
            self.assertNotEqual(rule['fixed_method'] is not None, selector)
            if rule['method_arg'] is not None:
                self.assertIs(type(rule['method_arg']), int)
                self.assertGreaterEqual(rule['method_arg'], 0)
            if rule['method_kw'] is not None:
                self.assertTrue(rule['method_kw'].isidentifier())
            for relative in rule['paths']:
                self.assertTrue(relative.startswith(tuple(POLICY['include_prefixes'])))
                self.assertEqual(Path(relative).suffix, '.py')
                self.assertNotIn('..', Path(relative).parts)
                source_tree(relative)
            repository_paths = {x for x in rule['paths'] if x.startswith('backend/')}
            bundle_paths = {x for x in rule['paths'] if x.startswith('app/')}
            self.assertEqual({x.removeprefix('backend/') for x in repository_paths}, bundle_paths)
        self.assertEqual(POLICY['include_prefixes'], ['backend/app/', 'app/'])
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_selector_matches_real_ast_without_executing(self):
        static = set()
        dynamic = 0
        for rule in POLICY['dispatches']:
            matches = []
            for relative in rule['paths']:
                matches.extend(n for n in ast.walk(source_tree(relative)) if isinstance(n, ast.Call) and dotted(n.func) == rule['callee'])
            self.assertTrue(matches, rule['id'])
            for call in matches:
                value = selected_method(rule, call)
                if value is None:
                    dynamic += 1
                else:
                    static.add((rule['protocol'], value))
        self.assertGreater(dynamic, 0)
        self.assertIn(('BotAPI','getWebhookInfo'), static)
        self.assertIn(('BotAPI','setWebhook'), static)
        self.assertIn(('BotAPI','sendMediaGroup'), static)
        self.assertIn(('MTProto','messages.sendMessage'), static)
        self.assertNotIn(('BotAPI','messages.sendMessage'), static)
        self.assertNotIn(('BotAPI','deleteMessages'), static)

    def test_declarations_only_exact_capabilities(self):
        self.assertEqual({x['symbol'] for x in POLICY['declarations']}, {'_DELIVERY_METHODS','_PROBE_METHODS'})
        for declaration in POLICY['declarations']:
            self.assertEqual(set(declaration), {'id','provider','protocol','paths','symbol'})
            self.assertEqual(declaration['paths'], ['app/ingest/telegram_basic_native_transport.py', 'backend/app/ingest/telegram_basic_native_transport.py'])
            self.assertFalse(any(x['callee'] == declaration['symbol'] for x in POLICY['dispatches']))

    def test_selector_keyword_and_dynamic_ambiguity(self):
        rule = next(x for x in POLICY['dispatches'] if x['id'] == 'bnt-request')
        cases = [("self._request(token, 'sendMessage', args)", 'sendMessage'),
                 ("self._request(token, method='getWebhookInfo', arguments=args)", 'getWebhookInfo'),
                 ("self._request(token, method, args)", None),
                 ("self._request(token, 'sendMessage', args, method='getMe')", None)]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(selected_method(rule, ast.parse(source, mode='eval').body), expected)


if __name__ == '__main__':
    unittest.main()
