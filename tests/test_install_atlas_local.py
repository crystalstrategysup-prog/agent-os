"""Focused managed-installer tests using synthetic wheels and real offline venvs.

All effects are confined to disposable temporary core/user roots. No external
dependency, network, actual project, existing runtime or official release pin is
used. The wheel is an explicitly synthetic minimal installer fixture, not Atlas
runtime acceptance. The existing installer subprocess/payload/probe gates run.
"""
from pathlib import Path
import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
INSTALLER = HERE / 'install.py'
if not INSTALLER.is_file():
    INSTALLER = HERE.parent / 'tools/install.py'
SPEC = importlib.util.spec_from_file_location('selected_installer_local_test', INSTALLER)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def snapshot(root):
    if not root.exists():
        return None
    rows = {}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            rows[name] = ('link', os.readlink(path))
        elif path.is_file():
            rows[name] = ('file', path.stat().st_mode & 0o777,
                          hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            rows[name] = ('directory', path.stat().st_mode & 0o777)
    return rows


def wheel(directory, version):
    """Construct a minimal correct wheel entirely from synthetic fixture text."""
    dist = 'crystal_agent_os-' + version + '.dist-info'
    members = {
        'agent_os/__init__.py': ('__version__ = ' + repr(version) + '\n').encode(),
        'agent_os/mcp_server.py': b'TOOLS = {str(i): {} for i in range(6)}\n',
        'agent_os/cli.py': b'def main():\n    return 0\n',
        'agent_os/hooks.py': b'def main():\n    return 0\n',
        'agent_os/atlas_module.py': b'def main():\n    return 0\n',
        'agent_os/resources/skills/agentos-project-entry/SKILL.md': b'# Synthetic installer fixture\n',
        'agent_os/resources/skills/atlas/SKILL.md': b'# Synthetic Atlas resource\n',
        'agent_os/resources/schemas/project.schema.json': b'{"type":"object"}\n',
        dist + '/METADATA': ('Metadata-Version: 2.4\nName: crystal-agent-os\nVersion: '
                            + version + '\nRequires-Python: >=3.11\n\nSynthetic installer fixture.\n').encode(),
        dist + '/WHEEL': b'Wheel-Version: 1.0\nGenerator: synthetic-installer-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
        dist + '/entry_points.txt': b'[console_scripts]\nagentos = agent_os.cli:main\nagentos-hook = agent_os.hooks:main\natlasctl = agent_os.atlas_module:main\n',
    }
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for name, raw in sorted(members.items()):
        encoded = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
        writer.writerow((name, 'sha256=' + encoded, str(len(raw))))
    writer.writerow((dist + '/RECORD', '', ''))
    members[dist + '/RECORD'] = record.getvalue().encode()
    path = directory / ('crystal_agent_os-' + version + '-py3-none-any.whl')
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(members.items()):
            archive.writestr(name, raw)
    return path


class InstallerLocalVersionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='agentos-local-version-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.core = self.root / 'managed-core'
        self.user = self.root / 'user-overlay'
        self.user.mkdir()
        (self.user / 'owner-note.txt').write_bytes(b'Synthetic owner bytes must survive unchanged.\n')
        self.base = wheel(self.root, '0.8.0rc2')
        self.local = wheel(self.root, '0.8.0rc2+atlas.1')

    def args(self, selected=None, version=None, *, apply=False, expected=None):
        selected = selected or self.local
        version = version or '0.8.0rc2+atlas.1'
        argv = ['install', '--wheel', str(selected), '--sha256', installer.digest(selected),
                '--version', version, '--core-home', str(self.core), '--user-home', str(self.user)]
        if apply:
            argv += ['--apply', '--expected-current', expected]
        return installer.parser().parse_args(argv)

    def test_local_candidate_upgrade_long_trampoline_and_rollback_preserve_predecessor(self):
        # A path longer than both Linux and macOS distlib shebang limits makes
        # the actual pip-generated unquoted POSIX trampoline unavoidable.
        for index in range(6):
            self.core = self.core / ('segment-' + str(index) + '-' + 'x' * 64)
        owner_before = snapshot(self.user)
        before_plan = snapshot(self.root)
        plan = installer.execute(self.args())
        self.assertEqual(plan['status'], 'PLANNED')
        self.assertEqual(plan['expected_current'], 'none')
        self.assertEqual(plan['release_id'], '0.8.0rc2+atlas.1-' + installer.digest(self.local)[:12])
        self.assertEqual(snapshot(self.root), before_plan)
        base_result = installer.execute(self.args(self.base, '0.8.0rc2', apply=True, expected='none'))
        predecessor = installer.release(self.core, base_result['release_id'])
        predecessor_before = snapshot(predecessor)
        result = installer.execute(self.args(apply=True, expected=base_result['release_id']))
        self.assertEqual(result['status'], 'INSTALLED')
        self.assertTrue(result['activation_proven'])
        selected = installer.release(self.core, result['release_id'])
        manifest = installer.read_manifest(selected)
        self.assertEqual(manifest['version'], '0.8.0rc2+atlas.1')
        self.assertEqual(manifest['wheel_name'], self.local.name)
        self.assertEqual(set(manifest['script_sha256']), {'agentos', 'agentos-hook', 'atlasctl'})
        launcher = selected / '.venv/bin/atlasctl'
        interpreter = str(selected / '.venv/bin/python')
        self.assertGreater(len(interpreter.encode()), 512)
        self.assertIn('+atlas.1', interpreter)
        self.assertTrue(launcher.read_text().startswith("#!/bin/sh\n'''exec' " + interpreter + ' "$0" "$@"\n'))
        invoked = subprocess.run([str(launcher)], capture_output=True, timeout=15,
                                 env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        self.assertEqual(invoked.returncode, 0, invoked.stderr.decode(errors='replace'))
        previous = json.loads((self.core / 'PREVIOUS.json').read_text())
        self.assertEqual((previous['previous'], previous['selected']),
                         (base_result['release_id'], result['release_id']))
        self.assertEqual(snapshot(predecessor), predecessor_before)
        rollback = installer.parser().parse_args([
            'rollback', '--release-id', predecessor.name,
            '--core-home', str(self.core), '--user-home', str(self.user)])
        self.assertEqual(installer.execute(rollback)['status'], 'PLANNED')
        rollback.apply = True
        rollback.expected_current = result['release_id']
        self.assertEqual(installer.execute(rollback)['status'], 'ROLLED_BACK')
        self.assertEqual(installer.current_id(self.core), predecessor.name)
        self.assertEqual(snapshot(predecessor), predecessor_before)
        self.assertTrue(selected.is_dir())
        self.assertEqual(snapshot(self.user), owner_before)

    def test_invalid_local_labels_hash_current_and_path_traversal_refuse_before_effects(self):
        before = snapshot(self.root)
        for version in ['0.8.0rc2+', '0.8.0rc2+atlas..1', '0.8.0rc2+atlas+1',
                        '0.8.0rc2+../escape', '0.8.0rc2+atlas/escape', '0.8.0rc2+atlas\\escape']:
            with self.subTest(version=version), self.assertRaisesRegex(installer.InstallError, '^invalid_version$'):
                installer.execute(self.args(version=version, apply=True, expected='none'))
            self.assertEqual(snapshot(self.root), before)
        args = self.args(apply=True, expected='none')
        args.sha256 = '0' * 64
        with self.assertRaisesRegex(installer.InstallError, '^wheel_sha256_mismatch$'):
            installer.execute(args)
        with self.assertRaisesRegex(installer.InstallError, '^explicit_matching_expected_current_required$'):
            installer.execute(self.args(apply=True, expected='unobserved-release'))
        for identifier in ['../escape', '0.8.0rc2+atlas.1/escape', '0.8.0rc2+atlas.1\\escape']:
            with self.subTest(identifier=identifier), self.assertRaisesRegex(installer.InstallError, '^invalid_release_id$'):
                installer.release(self.core, identifier)
        self.assertEqual(snapshot(self.root), before)
        fake = self.root / 'synthetic-invalid-manifest'
        fake.mkdir()
        (fake / 'INSTALL.json').write_text(json.dumps({
            'schema': 'agentos.install/v2', 'overlay_schema': 1, 'version': '0.8.0rc2+atlas.1',
            'wheel_name': '../' + self.local.name, 'wheel_sha256': installer.digest(self.local)}))
        before = snapshot(self.root)
        with self.assertRaisesRegex(installer.InstallError, '^release_manifest_invalid$'):
            installer.read_manifest(fake, verify_payload=False)
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse(self.core.exists())

    def test_wrong_local_version_preserves_current_and_retains_incomplete_evidence(self):
        initial = installer.execute(self.args(self.base, '0.8.0rc2', apply=True, expected='none'))
        predecessor = installer.release(self.core, initial['release_id'])
        predecessor_before = snapshot(predecessor)
        owner_before = snapshot(self.user)
        previous_before = (self.core / 'PREVIOUS.json').read_bytes()
        args = self.args(version='0.8.0rc2+atlas.2', apply=True, expected=initial['release_id'])
        with self.assertRaisesRegex(installer.InstallError, '^installed_version_mismatch$'):
            installer.execute(args)
        self.assertEqual(installer.current_id(self.core), initial['release_id'])
        self.assertEqual((self.core / 'PREVIOUS.json').read_bytes(), previous_before)
        self.assertEqual(snapshot(predecessor), predecessor_before)
        self.assertEqual(snapshot(self.user), owner_before)
        failed = installer.release(self.core, '0.8.0rc2+atlas.2-' + installer.digest(self.local)[:12])
        self.assertTrue((failed / 'INCOMPLETE').is_file())
        self.assertFalse((failed / 'INSTALL.json').exists())
        with self.assertRaisesRegex(installer.InstallError, '^release_not_complete:'):
            installer.read_manifest(failed)
        self.assertFalse((self.core / '.install.lock').exists())


if __name__ == '__main__':
    unittest.main()
