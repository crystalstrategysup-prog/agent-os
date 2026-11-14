"""Scoped reader transitions are conservative and never inspect project roots."""
import base64
import csv
import hashlib
import io
import json
import zipfile

import pytest

from test_install_atlas_local import installer, snapshot, wheel


def extend_wheel(path, extra):
    with zipfile.ZipFile(path) as archive:
        payload = {n: archive.read(n) for n in archive.namelist()}
    payload.update(extra)
    record_name = next(n for n in payload if n.endswith('.dist-info/RECORD'))
    payload.pop(record_name)
    rows = io.StringIO(newline='')
    writer = csv.writer(rows, lineterminator='\n')
    for name, raw in sorted(payload.items()):
        encoded = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
        writer.writerow((name, 'sha256=' + encoded, str(len(raw))))
    writer.writerow((record_name, '', ''))
    payload[record_name] = rows.getvalue().encode()
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(payload.items()):
            archive.writestr(name, raw)
    return path


def scoped_wheel(folder, version):
    return extend_wheel(wheel(folder, version), {
        'agent_os/scoped_admission.py': b'# Synthetic installer capability fixture.\n',
        'agent_os/resources/contracts/scoped-install-v1.json':
            json.dumps(installer.SCOPED_INSTALL).encode(),
    })


def install_args(core, user, path, version, *, expected=None):
    argv = ['install', '--wheel', str(path), '--version', version,
            '--sha256', installer.digest(path), '--core-home', str(core),
            '--user-home', str(user)]
    if expected is not None:
        argv += ['--apply', '--expected-current', expected]
    return installer.parser().parse_args(argv)


def test_declared_scope_is_exact_and_presence_or_version_is_not_a_grant(tmp_path):
    plain = wheel(tmp_path, '99.0.0')
    assert installer.wheel_scoped_schemas(plain) == []
    extend_wheel(plain, {'agent_os/scoped_admission.py': b'unknown implementation'})
    assert installer.wheel_scoped_schemas(plain) is None
    declared = scoped_wheel(tmp_path, '99.0.1')
    assert installer.wheel_scoped_schemas(declared) == ['agentos.scoped-transaction/v1']
    changed = dict(installer.SCOPED_INSTALL, implicit_migration=True)
    extend_wheel(declared, {'agent_os/resources/contracts/scoped-install-v1.json':
                           json.dumps(changed).encode()})
    with pytest.raises(installer.InstallError, match='scoped_capabilities_invalid'):
        installer.wheel_scoped_schemas(declared)


def test_legacy_reader_requires_every_pinned_dependency(tmp_path, monkeypatch):
    payload = {'agent_os/scoped_admission.py': b'synthetic scoped reader',
               'agent_os/project.py': b'synthetic lifecycle guard',
               'agent_os/resources/schemas/project-task-v1.schema.json': b'{}'}
    path = extend_wheel(wheel(tmp_path, '1.0.0'), payload)
    monkeypatch.setattr(installer, 'LEGACY_SCOPED_MODULES', {
        hashlib.sha256(payload['agent_os/scoped_admission.py']).hexdigest()})
    monkeypatch.setattr(installer, 'LEGACY_SCOPED_DEPENDENCIES', {
        p: hashlib.sha256(raw).hexdigest() for p, raw in payload.items()
        if p != 'agent_os/scoped_admission.py'})
    assert installer.wheel_scoped_schemas(path) == ['agentos.scoped-transaction/v1']
    extend_wheel(path, {'agent_os/project.py': b'lifecycle guard removed'})
    assert installer.wheel_scoped_schemas(path) is None


@pytest.mark.parametrize('raw', [b'{}', b'{"schema":1,"schema":2}', b'x' * 4097])
def test_ambiguous_or_unbounded_scoped_declaration_is_refused(tmp_path, raw):
    path = scoped_wheel(tmp_path, '1.0.1')
    extend_wheel(path, {'agent_os/resources/contracts/scoped-install-v1.json': raw})
    with pytest.raises(installer.InstallError):
        installer.wheel_scoped_schemas(path)


def test_real_install_and_rollback_preserve_reader_and_owner_bytes(tmp_path):
    core, user = tmp_path / 'core', tmp_path / 'user'
    user.mkdir()
    (user / 'note').write_bytes(b'Owner bytes remain unchanged.')
    unrelated = tmp_path / 'unrelated-project'
    unrelated.mkdir()
    (unrelated / 'private-state').write_bytes(b'Never inventoried by installer.')
    owner_before, outside_before = snapshot(user), snapshot(unrelated)
    base = wheel(tmp_path, '1.0.0')
    first = installer.execute(install_args(core, user, base, '1.0.0', expected='none'))
    capable = scoped_wheel(tmp_path, '1.0.1')
    selected = installer.execute(install_args(core, user, capable, '1.0.1', expected=first['release_id']))
    before = snapshot(core)
    rollback = installer.parser().parse_args([
        'rollback', '--release-id', first['release_id'], '--core-home', str(core),
        '--user-home', str(user)])
    for apply in (False, True):
        rollback.apply = apply
        rollback.expected_current = selected['release_id']
        with pytest.raises(installer.InstallError, match='scoped_reader_incompatible_preserve_and_hold'):
            installer.execute(rollback)
        assert snapshot(core) == before
    newer_but_incapable = wheel(tmp_path, '99.0.0')
    for expected in (None, selected['release_id']):
        with pytest.raises(installer.InstallError, match='scoped_reader_incompatible_preserve_and_hold'):
            installer.execute(install_args(core, user, newer_but_incapable, '99.0.0', expected=expected))
        assert snapshot(core) == before
    assert installer.current_id(core) == selected['release_id']
    assert snapshot(user) == owner_before and snapshot(unrelated) == outside_before
    stored_path = installer.release(core, selected['release_id']) / 'INSTALL.json'
    original = stored_path.read_bytes()
    changed = json.loads(original)
    changed['scoped_transaction_schemas'] = []
    stored_path.write_text(json.dumps(changed))
    with pytest.raises(installer.InstallError, match='release_scoped_capabilities_mismatch'):
        installer.read_manifest(stored_path.parent)
    stored_path.write_bytes(original)
    successor = scoped_wheel(tmp_path, '1.0.2')
    result = installer.execute(install_args(core, user, successor, '1.0.2', expected=selected['release_id']))
    rollback.release_id = selected['release_id']
    rollback.expected_current = result['release_id']
    assert installer.execute(rollback)['status'] == 'ROLLED_BACK'
    assert installer.current_id(core) == selected['release_id']
    assert snapshot(user) == owner_before and snapshot(unrelated) == outside_before
    unknown = extend_wheel(wheel(tmp_path, '1.0.3'), {
        'agent_os/scoped_admission.py': b'# Custom pre-declaration implementation.\n'})
    result = installer.execute(install_args(core, user, unknown, '1.0.3', expected=selected['release_id']))
    assert result['status'] == 'INSTALLED'
    assert result['scoped_transaction_schemas'] is None
    assert result['scoped_reader_compatibility'] == 'UNKNOWN'
    assert snapshot(user) == owner_before and snapshot(unrelated) == outside_before
