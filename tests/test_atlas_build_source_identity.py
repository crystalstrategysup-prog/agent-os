"""The source commit is distinct from the actual selected package bytes."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

SPEC = importlib.util.spec_from_file_location(
    'build_identity_verifier', Path(__file__).resolve().parents[1] / 'tools/verify_atlas_package.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'source'
    (root / 'src/agent_os').mkdir(parents=True)
    (root / 'src/agent_os/__init__.py').write_bytes(b'__version__="1.0.0"\n')
    (root / 'src/agent_os/feature.py').write_bytes(b'FEATURE=True\n')
    (root / 'pyproject.toml').write_bytes(b'[project]\nversion="1.0.0"\n')
    (root / 'README.md').write_bytes(b'Synthetic source identity fixture.\n')
    git(root, 'init', '-q')
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Synthetic baseline')
    return root


def test_committed_dirty_untracked_and_deleted_inputs_are_distinct(project):
    source = builder.sources(project)
    clean = builder.source_identity(project, source)
    assert clean['status'] == 'COMMITTED' and clean['dirty'] is False
    assert clean['source_commit'] == git(project, 'rev-parse', 'HEAD')
    assert clean['selected_files'] == len(source)
    # Git status can hide this mutation; direct blob comparison must not.
    git(project, 'update-index', '--assume-unchanged', 'src/agent_os/feature.py')
    (project / 'src/agent_os/feature.py').write_bytes(b'FEATURE=False\n')
    dirty = builder.source_identity(project, builder.sources(project))
    assert dirty['status'] == 'DIRTY' and dirty['changed_files'] == 1
    assert dirty['source_commit'] == clean['source_commit']
    assert dirty['source_files_sha256'] != clean['source_files_sha256']
    (project / 'src/agent_os/untracked.py').write_bytes(b'NEW=True\n')
    assert builder.source_identity(project, builder.sources(project))['untracked_files'] == 1
    (project / 'src/agent_os/feature.py').unlink()
    assert builder.source_identity(project, builder.sources(project))['deleted_files'] == 1


def test_no_repository_does_not_invent_a_commit(tmp_path):
    observed = builder.source_identity(tmp_path, {'README.md': b'synthetic'})
    assert observed['status'] == 'UNKNOWN'
    assert observed['source_commit'] is None and observed['dirty'] is None
    assert len(observed['source_files_sha256']) == 64


def test_recorded_commit_survives_later_head_when_package_bytes_match(project):
    source = builder.sources(project)
    identity = builder.source_identity(project, source)
    (project / 'outside-package.txt').write_bytes(b'Synthetic new source commit.')
    git(project, 'add', 'outside-package.txt')
    git(project, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'New exact commit')
    assert builder.source_identity(project, source)['source_commit'] != identity['source_commit']
    assert builder.source_identity(project, source, identity['source_commit']) == identity
