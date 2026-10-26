"""One new inert native-public-file size-profile regression; no binary is loaded."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_only_exact_declared_public_native_binary_gets_bounded_8mb_read(tmp_path, monkeypatch):
    from tools.function_extractor.runner import container
    replay = container.load_engine('route_probe_replay')
    public = tmp_path / 'public_capsule'
    relative = 'site-packages/pydantic_core/_pydantic_core.cpython-311-x86_64-linux-gnu.so'
    binary = public / relative
    binary.parent.mkdir(parents=True)
    # Harmless bytes over the ordinary cap; neither an ELF nor imported.
    binary.write_bytes(b'X' * 4_000_001)
    manifest = []
    for rel, data in [('engine/tools/function_extractor/runner/container_entry.py', b'pass\n'),
                      ('libseccomp.so.2', b'inert-public-test-file')]:
        path = public / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest.append({'path': rel, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    pin = {'path': relative, 'bytes': binary.stat().st_size,
           'sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    manifest.append(dict(pin))
    real_read = replay._read_public
    reads = []

    def bounded_read(path, cap):
        reads.append((Path(path), cap))
        return real_read(path, cap)

    monkeypatch.setattr(replay, '_read_public', bounded_read)
    assert container._capsule(public, manifest, [pin]) == public
    assert (binary, 8_000_000) in reads
    assert all(cap == 4_000_000 for path, cap in reads if path != binary)
    reads.clear()
    with pytest.raises(ValueError):
        container._capsule(public, manifest)  # Original ordinary 4MB limit remains.
    assert (binary, 4_000_000) in reads

    repo = tmp_path / 'repo'
    selected_path = repo / '.agentos/route-probe/container/IMAGE.json'
    selected_path.parent.mkdir(parents=True)
    monkeypatch.setattr(container, '__file__', str(repo / 'tools/function_extractor/runner/container.py'))
    image = 'sha256:' + 'a' * 64
    leases, commands = [], []

    def lease(target):
        leases.append(target)
        return {'required': True, 'window_id': 'b' * 32, 'actor_session': 'unit-only'}

    def command(argv, timeout):
        commands.append(argv)
        return None, 0, b'{"schema":"route-probe.trace/v1","status":"RETURNED","spans":[]}', b''

    def select(pins, rows=None):
        value = {'image_id': image, 'capsule_root': str(public), 'files': manifest if rows is None else rows,
                 'public_binary_pins': pins}
        selected_path.write_text(json.dumps(value))

    monkeypatch.setattr(container, '_lease', lease)
    monkeypatch.setattr(container, '_command', command)
    monkeypatch.setattr(container, 'pack_bundle', lambda bundle, output: output.write_text('{}'))
    select([pin])
    assert container.execute_container(tmp_path / 'unused_bundle', {}, timeout=2)['status'] == 'RETURNED'
    assert len(leases) == len(commands) == 1  # Only these inert callbacks; no RPC/Docker.
    invalid = [
        [],  # Undeclared oversize file must not inherit the positive 8MB allowance.
        [{**pin, 'sha256': '0' * 64}],
        [{**pin, 'bytes': pin['bytes'] + 1}],
        [{**pin, 'bytes': 8_000_001}],
        [{**pin, 'bytes': True}],
        [pin, pin],
        [pin] * 9,
        [{**pin, 'path': '../private.so'}],
        [{**pin, 'cap': 8_000_000}],
    ]
    for pins in invalid:
        select(pins)
        with pytest.raises(ValueError):
            container.execute_container(tmp_path / 'unused_bundle', {})
        assert len(leases) == len(commands) == 1

    # An over8MB declaration is rejected even if it exactly matches the
    # manifest row: no attempt to read that native file may occur.
    oversized_pin = {**pin, 'bytes': 8_000_001}
    select([oversized_pin], manifest[:-1] + [dict(oversized_pin)])
    native_reads_before = sum(path == binary for path, _ in reads)
    with pytest.raises(ValueError):
        container.execute_container(tmp_path / 'unused_bundle', {})
    assert sum(path == binary for path, _ in reads) == native_reads_before
    assert len(leases) == len(commands) == 1

    # Matching manifest+bytes+hash are insufficient for non-site/native paths.
    # Move only our harmless file and bind the corresponding exact row.
    for forbidden in ('assets/private.so', 'site-packages/pydantic_core/large.py',
                      'site-packages/pydantic_core/large.so.1'):
        alternate = public / forbidden
        alternate.parent.mkdir(parents=True, exist_ok=True)
        binary.rename(alternate)
        alternate_pin = {**pin, 'path': forbidden}
        alternate_manifest = manifest[:-1] + [dict(alternate_pin)]
        select([alternate_pin], alternate_manifest)
        try:
            with pytest.raises(ValueError):
                container.execute_container(tmp_path / 'unused_bundle', {})
            assert len(leases) == len(commands) == 1
        finally:
            alternate.rename(binary)
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == pin['sha256']
