"""Bounded local CLI tests. All project roots and registry data are synthetic."""
import argparse
import ast
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from agent_os import atlas_module


def files(root):
    return {p.relative_to(root).as_posix():
            (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mode, p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


class AtlasModuleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='atlas-facade-synthetic-')
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve()
        self.environment = patch.dict(os.environ, {'HOME': str(self.home)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def registry(self, path=None, *, count=1):
        path = path or self.home / '.agentos-user/knowledge/atlas/PROJECTS.json'
        rows = []
        for index in range(count):
            project = self.home / ('synthetic-project-' + str(index).zfill(4))
            project.mkdir(exist_ok=True)
            rows.append({'key': 'project-' + str(index).zfill(4), 'root': str(project),
                         'binding': '.atlas/UPSTREAM.json'})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'schema': 'atlas.workspace/v1', 'projects': rows}))
        return path, rows

    def invoke(self, argv, *, function=atlas_module.main):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = function(argv)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_default_registry_actual_list_has_no_configuration_effects(self):
        _, rows = self.registry()
        before = files(self.home)
        code, output, error = self.invoke(['list'])
        self.assertEqual((code, error), (0, ''))
        self.assertEqual(json.loads(output), {'schema': 'atlas.workspace.list/v1', 'projects': rows})
        self.assertEqual(files(self.home), before)
        self.assertFalse((self.home / '.agentos').exists())

    def test_explicit_registry_does_not_fall_back_to_default(self):
        default = self.home / '.agentos-user/knowledge/atlas/PROJECTS.json'
        default.parent.mkdir(parents=True)
        default.write_text('not-json')
        selected, rows = self.registry(self.home / 'selected.json')
        before = files(self.home)
        code, output, _ = self.invoke(['--registry', str(selected), 'list'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)['projects'], rows)
        self.assertEqual(files(self.home), before)
        code, output, _ = self.invoke(['--registry', str(self.home / 'missing.json'), 'list'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)['status'], 'REFUSED')
        self.assertEqual(files(self.home), before)

    def test_missing_default_refuses_without_creating_home_state(self):
        before = list(self.home.iterdir())
        code, output, _ = self.invoke(['list'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)['status'], 'REFUSED')
        self.assertEqual(list(self.home.iterdir()), before)

    def test_malformed_and_symlinked_registries_fail_closed(self):
        selected, rows = self.registry(self.home / 'selected.json')
        for value in ('bad-json', json.dumps({'schema': 'other/v1', 'projects': rows}),
                      json.dumps({'schema': 'atlas.workspace/v1', 'projects': rows + rows})):
            with self.subTest(value=value[:30]):
                selected.write_text(value)
                before = files(self.home)
                code, output, _ = self.invoke(['--registry', str(selected), 'list'])
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(output)['status'], 'REFUSED')
                self.assertEqual(files(self.home), before)
        self.registry(selected)
        alias = self.home / 'alias.json'
        alias.symlink_to(selected)
        code, output, _ = self.invoke(['--registry', str(alias), 'list'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)['code'], 'WORKSPACE_SYMLINK')

    def test_unknown_project_refuses_before_source_or_binding_creation(self):
        _, rows = self.registry()
        before = files(self.home)
        code, output, _ = self.invoke(['packet', 'not-registered', '--work', 'W-1'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)['code'], 'WORKSPACE_UNKNOWN_PROJECT')
        self.assertEqual(files(self.home), before)
        self.assertFalse((Path(rows[0]['root']) / '.atlas').exists())

    def test_scoped_imports_restore_path_modules_and_bytecode_setting(self):
        self.registry()
        previous_path = list(sys.path)
        previous_modules = {name: sys.modules.get(name) for name in atlas_module._MODULE_NAMES}
        previous_setting = sys.dont_write_bytecode
        package_before = files(atlas_module._SCRIPTS)
        code, _, _ = self.invoke(['list'])
        self.assertEqual(code, 0)
        self.assertEqual(sys.path, previous_path)
        self.assertEqual({name: sys.modules.get(name) for name in atlas_module._MODULE_NAMES}, previous_modules)
        self.assertEqual(sys.dont_write_bytecode, previous_setting)
        self.assertEqual(files(atlas_module._SCRIPTS), package_before)

    def test_foreign_loaded_module_is_not_replaced(self):
        self.registry()
        foreign = types.ModuleType('workspace')
        foreign.__file__ = str(self.home / 'unrelated-workspace.py')
        before = list(sys.path)
        with patch.dict(sys.modules, {'workspace': foreign}):
            code, output, _ = self.invoke(['list'])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output)['code'], 'ATLAS_MODULE_NAME_CONFLICT:workspace')
            self.assertIs(sys.modules['workspace'], foreign)
        self.assertEqual(sys.path, before)

    def test_help_and_argument_error_preserve_cli_outcomes(self):
        code, output, error = self.invoke(['--help'])
        self.assertEqual((code, error), (0, ''))
        self.assertIn('--registry', output)
        self.assertIn('docs-reconcile', output)
        code, output, error = self.invoke(['not-a-method'])
        self.assertEqual((code, output), (2, ''))
        self.assertIn('invalid choice', error)

    def test_early_main_body_routes_before_foundation_and_preserves_other_argv(self):
        # Execute the actual main function body while excluding unrelated module
        # imports. The synthetic foundation sentinel catches early side effects.
        self.registry()
        source = ROOT / 'src/agent_os/cli.py'
        parsed = ast.parse(source.read_text())
        main = next(item for item in parsed.body if isinstance(item, ast.FunctionDef) and item.name == 'main')
        namespace = {'__name__': 'agent_os.cli', '__package__': 'agent_os', 'sys': sys}
        exec(compile(ast.Module(body=[main], type_ignores=[]), str(source), 'exec'), namespace)
        observed = []
        foundation = types.ModuleType('agent_os.foundation_cli')
        foundation.dispatch = lambda argv: observed.append(argv) or 17
        with patch.dict(sys.modules, {'agent_os.foundation_cli': foundation}):
            code, output, _ = self.invoke(['atlas', 'list'], function=namespace['main'])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)['schema'], 'atlas.workspace.list/v1')
            self.assertEqual(observed, [])
            self.assertEqual(namespace['main'](['project', 'status', '--exact']), 17)
            self.assertEqual(observed, [['project', 'status', '--exact']])
            code, output, _ = self.invoke(['--home', str(self.home), 'atlas', 'list'],
                                          function=namespace['main'])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output)['code'], 'ATLAS_USE_EXPLICIT_REGISTRY')
            self.assertEqual(len(observed), 1)

    def test_root_parser_advertises_new_namespace(self):
        source = ROOT / 'src/agent_os/cli.py'
        parsed = ast.parse(source.read_text())
        node = next(item for item in parsed.body if isinstance(item, ast.FunctionDef) and item.name == 'parser')
        namespace = {'argparse': argparse, 'Path': Path, '__version__': 'synthetic-test',
                     'full_inventory': types.SimpleNamespace(DEFAULT_MAX_FILES=1, DEFAULT_MAX_BYTES=1,
                                                              CLASSES=('source', 'all'))}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
        help_text = namespace['parser']().format_help()
        self.assertIn('atlas', help_text)
        self.assertIn('session-capabilities', help_text)
        self.assertIn('--user-home', help_text)

    def test_oversized_composite_outcome_recovery_and_pagination_are_retained(self):
        changed = ['W-' + str(index) + '-' + 'x' * 50 for index in range(999)]
        docs = {'status': 'NO_CHANGE', 'changed_paths': [], 'matrix_writes': 0,
                'projection': {'status': 'IMPORTED_PARTIAL', 'generation': '.atlas/imports/synthetic',
                               'changed_work_ids': changed, 'cycle': {'status': 'BUILT_LOCAL',
                               'release': 'synthetic-release', 'manifest_sha256': 'a' * 64}}}
        files = [{'path': 'docs/' + str(index) + '-' + 'x' * 60, 'state': 'AFTER'} for index in range(900)]
        files[-1]['state'] = 'CONFLICT'
        reconcile = {'status': 'DOCUMENT_SYNC_RECONCILE_REQUIRED', 'generation': '.atlas/doc-sync/synthetic',
                     'lock_present': False, 'effect': 'READ_ONLY', 'files': files}
        history = {'schema': 'atlas.history/v1', 'status': 'VERIFIED_PAGE', 'has_more': True,
                   'next_cursor': 'synthetic-cursor', 'matrix_history_total': 4000,
                   'readback': {'raw_source_read_now': False,
                                'ancestry_to_current': 'NOT_RETRAVERSED_FOR_CALLER_SUPPLIED_CURSOR'},
                   'revisions': [{'id': str(i), 'details': 'x' * 500} for i in range(100)]}
        outputs = []
        for value in (docs, reconcile, history):
            with self.subTest(status=value['status']):
                raw = json.dumps(value) + '\n'
                self.assertGreater(len(raw.encode()), 32 * 1024)
                rendered = atlas_module._render(raw, 0, ['synthetic-control-probe'])
                self.assertLess(len(rendered.encode()), 32 * 1024)
                result = json.loads(rendered)
                self.assertEqual(result['full_result']['sha256'], hashlib.sha256(raw.encode()).hexdigest())
                self.assertEqual(result['control']['status'], value['status'])
                outputs.append(result['control'])
        self.assertEqual(outputs[0]['projection']['status'], 'IMPORTED_PARTIAL')
        self.assertEqual(outputs[0]['projection']['cycle']['status'], 'BUILT_LOCAL')
        self.assertEqual(outputs[0]['projection']['generation'], '.atlas/imports/synthetic')
        self.assertEqual(outputs[1]['generation'], '.atlas/doc-sync/synthetic')
        self.assertIs(outputs[1]['lock_present'], False)
        self.assertEqual(outputs[1]['files']['state_counts'], {'AFTER': 899, 'CONFLICT': 1})
        self.assertTrue(outputs[1]['files']['all_states_counted'])
        self.assertTrue(outputs[2]['has_more'])
        self.assertEqual(outputs[2]['next_cursor'], 'synthetic-cursor')
        self.assertIs(outputs[2]['readback']['raw_source_read_now'], False)
        self.assertEqual(outputs[2]['readback']['ancestry_to_current'],
                         'NOT_RETRAVERSED_FOR_CALLER_SUPPLIED_CURSOR')

    def test_oversized_actual_list_is_bounded_hashed_and_read_only(self):
        _, rows = self.registry(count=900)
        expected_raw = (json.dumps({'schema': 'atlas.workspace.list/v1', 'projects': rows},
                                   ensure_ascii=False) + '\n').encode('utf-8')
        self.assertGreater(len(expected_raw), 64 * 1024)
        before = files(self.home)
        code, output, error = self.invoke(['list'])
        self.assertEqual((code, error), (0, ''))
        self.assertLess(len(output.encode('utf-8')), 32 * 1024)
        result = json.loads(output)
        self.assertEqual(result['schema'], 'agent-os.atlas-cli-summary/v1')
        self.assertFalse(result['output_complete'])
        self.assertEqual(result['full_result']['bytes'], len(expected_raw))
        self.assertEqual(result['full_result']['sha256'], hashlib.sha256(expected_raw).hexdigest())
        self.assertEqual(result['full_result']['storage'], 'NOT_PERSISTED_BY_FACADE')
        self.assertEqual(result['counts']['projects'], 900)
        self.assertEqual(result['projects_sample']['count'], 900)
        self.assertEqual(files(self.home), before)


if __name__ == '__main__':
    unittest.main()
