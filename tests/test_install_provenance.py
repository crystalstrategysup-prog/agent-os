"""Install receipts retain bound source/build identity without retrofitting history."""
import copy
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from test_install_atlas_local import installer, snapshot, wheel
from test_scoped_install_compat import install_args, scoped_wheel


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def public_manifest(path, version):
    return {'schema': 'agentos.public-release/v1', 'version': version,
            'source_commit': 'a' * 40, 'source_date_epoch': 1794614400,
            'build_versions': {'build': '1.6.1', 'setuptools': '84.2.1', 'wheel': '0.48.0'},
            'artifacts': {path.name: {'sha256': installer.digest(path), 'size': path.stat().st_size}},
            'verification_scope': 'Synthetic provenance fixture, no publication claim.'}


def local_manifest(path, version):
    with zipfile.ZipFile(path) as archive:
        source = {'src/' + n: {'bytes': len(archive.read(n)),
                              'sha256': hashlib.sha256(archive.read(n)).hexdigest()}
                  for n in archive.namelist() if n.startswith('agent_os/')}
    return {'schema': 'agent-os.atlas-candidate-build/v1', 'version': version,
            'status': 'BUILD_SUCCEEDED', 'qualification': 'LOCAL_CANDIDATE_ONLY',
            'wheel': {'name': path.name, 'bytes': path.stat().st_size, 'sha256': installer.digest(path)},
            'source_files': source,
            'source_identity': {'schema': 'agentos.build-source-identity/v1',
                                'status': 'COMMITTED', 'source_commit': 'b' * 40,
                                'git_tree': 'c' * 40, 'dirty': False,
                                'dirty_scope': 'SELECTED_PACKAGE_INPUTS',
                                'source_files_sha256': hashlib.sha256(encoded(source)).hexdigest(),
                                'selected_files': len(source), 'changed_files': 0,
                                'untracked_files': 0, 'deleted_files': 0},
            'interpreter': {'build_versions': {'build': '1.6.1', 'setuptools': '84.2.1', 'wheel': '0.48.0'}},
            'source_date_epoch': 1794614400}


@pytest.mark.parametrize('make', [public_manifest, local_manifest])
def test_existing_build_formats_bind_exact_wheel_and_source(tmp_path, make):
    path = wheel(tmp_path, '1.0.0')
    value = make(path, '1.0.0')
    observed = installer.build_provenance(encoded(value), path, '1.0.0')
    assert observed['status'] == 'RECORDED'
    assert observed['source_commit'] == ('a' if make is public_manifest else 'b') * 40
    assert observed['source_dirty'] is False
    assert observed['build_manifest_sha256'] == hashlib.sha256(encoded(value)).hexdigest()
    changed = copy.deepcopy(value)
    changed['version'] = '1.0.1'
    with pytest.raises(installer.InstallError, match='identity_mismatch'):
        installer.build_provenance(encoded(changed), path, '1.0.0')
    changed = copy.deepcopy(value)
    if make is public_manifest:
        changed['artifacts'][path.name]['sha256'] = '0' * 64
    else:
        changed['wheel']['sha256'] = '0' * 64
    with pytest.raises(installer.InstallError, match='wheel_mismatch'):
        installer.build_provenance(encoded(changed), path, '1.0.0')


def test_dirty_local_inputs_are_never_labelled_as_committed_source(tmp_path):
    path = wheel(tmp_path, '1.0.0')
    value = local_manifest(path, '1.0.0')
    value['source_identity'].update(status='DIRTY', dirty=True, changed_files=1)
    observed = installer.build_provenance(encoded(value), path, '1.0.0')
    assert observed['source_identity_status'] == 'DIRTY' and observed['source_dirty'] is True
    value['source_identity']['status'] = 'COMMITTED'
    with pytest.raises(installer.InstallError, match='source_identity_invalid'):
        installer.build_provenance(encoded(value), path, '1.0.0')


@pytest.mark.parametrize('invalid', [[], {}, None, 'unsupported-status'])
def test_malformed_source_identity_is_a_controlled_refusal(tmp_path, invalid):
    path = wheel(tmp_path, '1.0.0')
    value = local_manifest(path, '1.0.0')
    value['source_identity']['status'] = invalid
    with pytest.raises(installer.InstallError, match='source_identity_invalid'):
        installer.build_provenance(encoded(value), path, '1.0.0')


def test_adjacent_receipts_need_no_extra_flag_and_conflicts_are_exact(tmp_path):
    path = wheel(tmp_path, '1.0.0')
    local = local_manifest(path, '1.0.0')
    receipt = tmp_path / 'BUILD_RECEIPT.json'
    receipt.write_bytes(encoded(local))
    raw, observed, selection = installer.select_build_manifest(None, path, '1.0.0')
    assert raw == encoded(local) and observed['source_commit'] == 'b' * 40
    assert selection == 'ADJACENT:BUILD_RECEIPT.json'
    public = public_manifest(path, '1.0.0')
    public['source_commit'] = 'b' * 40
    manifest = tmp_path / 'MANIFEST.json'
    manifest.write_bytes(encoded(public))
    assert installer.select_build_manifest(None, path, '1.0.0')[2] == selection
    public['source_commit'] = 'd' * 40
    manifest.write_bytes(encoded(public))
    with pytest.raises(installer.InstallError, match='adjacent_build_manifest_identity_conflict'):
        installer.select_build_manifest(None, path, '1.0.0')
    assert installer.select_build_manifest(receipt, path, '1.0.0')[2] == 'EXPLICIT'
    receipt.unlink()
    manifest.write_bytes(b'Unrelated old packaging metadata.\n')
    assert installer.select_build_manifest(None, path, '1.0.0')[1]['status'] == 'UNKNOWN'
    public = public_manifest(path, '1.0.0')
    public['artifacts'][path.name]['sha256'] = '0' * 64
    manifest.write_bytes(encoded(public))
    with pytest.raises(installer.InstallError, match='build_manifest_wheel_mismatch'):
        installer.select_build_manifest(None, path, '1.0.0')


def test_missing_historical_identity_stays_unknown_and_source_mismatch_refuses(tmp_path):
    path = wheel(tmp_path, '1.0.0')
    value = local_manifest(path, '1.0.0')
    value.pop('source_identity')
    result = installer.build_provenance(encoded(value), path, '1.0.0')
    assert result['status'] == 'UNKNOWN' and result['source_commit'] is None
    source = value['source_files']
    source[next(iter(source))]['sha256'] = '0' * 64
    with pytest.raises(installer.InstallError, match='package_source_mismatch'):
        installer.build_provenance(encoded(value), path, '1.0.0')
    assert installer.build_provenance(None, path, '1.0.0')['status'] == 'UNKNOWN'


@pytest.mark.parametrize('field,value', [
    ('source_commit', 'not-a-commit'), ('build_versions', []),
    ('artifacts', []), ('source_date_epoch', True), ('schema', 'untrusted/v99')])
def test_invalid_provenance_does_not_reach_installation(tmp_path, field, value):
    path = wheel(tmp_path, '1.0.0')
    metadata = public_manifest(path, '1.0.0')
    metadata[field] = value
    before = snapshot(tmp_path)
    with pytest.raises(installer.InstallError):
        installer.build_provenance(encoded(metadata), path, '1.0.0')
    assert snapshot(tmp_path) == before


def test_duplicate_keys_and_symlink_inputs_are_refused(tmp_path):
    path = wheel(tmp_path, '1.0.0')
    with pytest.raises(installer.InstallError, match='metadata_duplicate_key'):
        installer.build_provenance(b'{"version":"1.0.0","version":"1.0.0"}', path, '1.0.0')
    metadata = tmp_path / 'real.json'
    metadata.write_bytes(encoded(public_manifest(path, '1.0.0')))
    link = tmp_path / 'linked.json'
    link.symlink_to(metadata)
    with pytest.raises(installer.InstallError, match='regular_bounded_file'):
        installer.bounded_file(link, 8 * 1024 * 1024)


def test_apply_retains_provenance_and_rejects_drift_without_rewriting_history(tmp_path):
    path = wheel(tmp_path, '1.0.0')
    core, user = tmp_path / 'core', tmp_path / 'user'
    user.mkdir()
    (user / 'owner-note').write_bytes(b'Unchanged owner bytes.')
    metadata = tmp_path / 'BUILD_RECEIPT.json'
    raw = encoded(local_manifest(path, '1.0.0'))
    metadata.write_bytes(raw)
    args = install_args(core, user, path, '1.0.0')
    before = snapshot(tmp_path)
    plan = installer.execute(args)
    assert plan['provenance']['source_commit'] == 'b' * 40
    assert plan['build_manifest_selection'] == 'ADJACENT:BUILD_RECEIPT.json'
    assert snapshot(tmp_path) == before
    owner_before = snapshot(user)
    args.apply, args.expected_current = True, 'none'
    result = installer.execute(args)
    release = installer.release(core, result['release_id'])
    manifest = installer.read_manifest(release)
    assert manifest['provenance']['installer_sha256'] == installer.digest(Path(installer.__file__))
    assert (release / 'BUILD_MANIFEST.json').read_bytes() == raw
    assert installer.digest(release / 'INSTALLER.py') == manifest['provenance']['installer_sha256']
    assert snapshot(user) == owner_before
    stored_before = snapshot(release)
    altered = local_manifest(path, '1.0.0')
    altered['source_identity']['source_commit'] = 'd' * 40
    metadata.write_bytes(encoded(altered))
    args.expected_current = result['release_id']
    with pytest.raises(installer.InstallError, match='immutable_release_provenance_conflict'):
        installer.execute(args)
    assert snapshot(release) == stored_before
    assert installer.current_id(core) == result['release_id']
    (release / 'BUILD_MANIFEST.json').write_bytes(raw + b' ')
    with pytest.raises(installer.InstallError, match='release_build_provenance_mismatch'):
        installer.read_manifest(release)
    (release / 'BUILD_MANIFEST.json').write_bytes(raw)
    # Explicitly model a historical v2 record in this disposable fixture only.
    old = json.loads((release / 'INSTALL.json').read_bytes())
    old.pop('provenance')
    old.pop('scoped_transaction_schemas')
    (release / 'INSTALL.json').write_bytes(encoded(old))
    (release / 'INSTALLER.py').unlink()
    (release / 'BUILD_MANIFEST.json').unlink()
    observed = installer.read_manifest(release)
    assert 'provenance' not in observed
    assert observed['scoped_transaction_schemas'] == []
    legacy_before = snapshot(release)
    repeated = installer.execute(args)
    assert repeated['status'] == 'INSTALLED'
    assert repeated['provenance']['status'] == 'UNKNOWN'
    assert repeated['build_manifest_selection'] == 'EXISTING_RELEASE_UNCHANGED'
    assert snapshot(release) == legacy_before


def test_verified_rollback_recovers_from_corrupt_current_payload_and_provenance(tmp_path):
    core, user = tmp_path / 'core', tmp_path / 'user'
    user.mkdir()
    (user / 'owner-note').write_bytes(b'Owner bytes survive recovery.')
    owner_before = snapshot(user)
    target_wheel = scoped_wheel(tmp_path, '1.0.0')
    first = installer.execute(install_args(core, user, target_wheel, '1.0.0', expected='none'))
    target = installer.release(core, first['release_id'])
    current_wheel = scoped_wheel(tmp_path, '1.0.1')
    (tmp_path / 'BUILD_RECEIPT.json').write_bytes(encoded(local_manifest(current_wheel, '1.0.1')))
    latest = installer.execute(install_args(core, user, current_wheel, '1.0.1',
                                            expected=first['release_id']))
    current = installer.release(core, latest['release_id'])
    rollback = installer.parser().parse_args([
        'rollback', '--release-id', first['release_id'], '--core-home', str(core),
        '--user-home', str(user)])
    # Current wheel and INSTALL identity remain trustworthy even when the
    # installed runtime and provenance sidecars can no longer pass readback.
    damaged = [installer._site_packages(current) / 'agent_os/cli.py',
               current / 'INSTALLER.py', current / 'BUILD_MANIFEST.json']
    for index, path in enumerate(damaged):
        if index == 1:
            path.unlink()
        else:
            path.write_bytes(b'Corrupted installed bytes.\n')
        with pytest.raises(installer.InstallError):
            installer.read_manifest(current)
        before_plan = snapshot(core)
        plan = installer.execute(rollback)
        assert plan['status'] == 'PLANNED'
        assert plan['scoped_reader_compatibility'] == 'PRESERVED'
        assert snapshot(core) == before_plan
    # Corrupt current files do not weaken either known reader protection or
    # the full integrity check of the release that will actually be activated.
    plain = wheel(tmp_path, '1.0.2')
    with pytest.raises(installer.InstallError, match='scoped_reader_incompatible_preserve_and_hold'):
        installer.execute(install_args(core, user, plain, '1.0.2'))
    target_payload = installer._site_packages(target) / 'agent_os/cli.py'
    target_bytes = target_payload.read_bytes()
    target_payload.unlink()
    with pytest.raises(installer.InstallError, match='installed_payload_mismatch'):
        installer.execute(rollback)
    target_payload.write_bytes(target_bytes)
    before_current, before_target = snapshot(current), snapshot(target)
    rollback.apply, rollback.expected_current = True, latest['release_id']
    recovered = installer.execute(rollback)
    assert recovered['status'] == 'ROLLED_BACK' and recovered['activation_proven'] is True
    assert recovered['scoped_reader_compatibility'] == 'PRESERVED'
    assert installer.current_id(core) == first['release_id']
    assert installer.read_manifest(target)['scoped_transaction_schemas'] == ['agentos.scoped-transaction/v1']
    assert snapshot(current) == before_current and snapshot(target) == before_target
    assert snapshot(user) == owner_before
