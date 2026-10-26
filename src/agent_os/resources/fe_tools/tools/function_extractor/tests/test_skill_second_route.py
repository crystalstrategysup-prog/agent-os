"""Second, non-Telegram route through the documented reusable workflow.

Only synthetic source/fixtures and host subprocess runner; never container or
production application/credentials. Root owns package, CLI and Skill files.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def order_source(tmp_path):
    source = tmp_path / 'source'
    package = source / 'orders'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('')
    (package / 'maths.py').write_text(textwrap.dedent("""\
        def line_total(unit_cents, quantity):
            if type(unit_cents) is not int or type(quantity) is not int:
                raise TypeError('integer_amounts_required')
            if unit_cents < 0 or not 1 <= quantity <= 100:
                raise ValueError('amount_outside_scope')
            return unit_cents * quantity
    """))
    (package / 'quote.py').write_text(textwrap.dedent("""\
        from .maths import line_total

        def calculate_quote(unit_cents, quantity, member=False):
            subtotal = line_total(unit_cents, quantity)
            discount = subtotal // 10 if member is True else 0
            return {'subtotal': subtotal, 'discount': discount,
                    'total': subtotal - discount}
    """))
    return source


def cli(*args, cwd, timeout=15):
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'TZ': 'UTC',
           'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-B', '-m', 'tools.function_extractor', *map(str, args)],
                            cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout)
    return result, json.loads(result.stdout)


def test_second_non_telegram_route_portable_cli_roundtrip(order_source, tmp_path):
    original_sources = {p.relative_to(order_source).as_posix(): p.read_bytes()
                        for p in order_source.rglob('*.py')}
    extract_dir = tmp_path / 'extract'
    command, frozen = cli('extract', '--source-root', order_source,
                          '--entry', 'orders.quote:calculate_quote', '--out', extract_dir,
                          cwd=tmp_path)
    assert command.returncode == 0, frozen
    assert frozen['status'] == 'FROZEN'
    portable = tmp_path / 'portable'
    portable.mkdir()
    bundle = portable / 'route_bundle.json'
    shutil.copyfile(extract_dir / 'route_bundle.json', bundle)
    packed = json.loads(bundle.read_text())
    assert packed['schema'] == 'function-extractor.portable-bundle/v1'
    assert packed['manifest']['entry'] == 'orders.quote:calculate_quote'
    assert packed['manifest']['adapter'] is None
    assert set(packed['sources_base64']) == set(original_sources)
    assert {name: base64.b64decode(value, validate=True)
            for name, value in packed['sources_base64'].items()} == original_sources
    # Retain only the portable bundle: neither original checkout nor legacy
    # extracted source directory may be used by the second CLI invocation.
    shutil.rmtree(order_source)
    shutil.rmtree(extract_dir)
    fixture = portable / 'fixture.json'
    fixture.write_text(json.dumps({'args': [1200, 3], 'kwargs': {'member': True},
                                  'expected_result': {'subtotal': 3600, 'discount': 360, 'total': 3240}}))
    output = tmp_path / 'replay'
    command, value = cli('replay', '--bundle', bundle, '--fixture', fixture,
                         '--runner', 'subprocess', '--out', output, cwd=tmp_path)
    assert command.returncode == 0, value
    assert value['status'] == 'RETURNED'
    assert value['production_effects'] == 0 and value['live_provider_observed'] is False
    trace = json.loads((output / 'trace.json').read_text())
    assert trace['target_outcome']['status'] == 'RETURNED'
    assert trace['result_matches_expected'] is True
    assert trace['sandbox']['seccomp'] is True and trace['sandbox']['audit'] is True
    assert trace['sandbox']['memory_mb'] == 256
    for symbol, source_file in [('calculate_quote', 'orders/quote.py'), ('line_total', 'orders/maths.py')]:
        assert any(span.get('symbol') == symbol and span.get('file') == source_file
                   and span.get('line', 0) > 0 and span['event'] == 'call'
                   and span['evidence'] == 'REAL_CODE' for span in trace['spans'])
    assert not any('telegram' in span.get('file', '').lower() for span in trace['spans'])
    jsonl = [json.loads(line) for line in (output / 'trace.jsonl').read_text().splitlines()]
    assert jsonl == trace['spans']
    graph = json.loads((output / 'route_graph.json').read_text())
    assert graph['entry']['module'] == 'orders.quote'
    assert {item['path'] for item in graph['files']} == set(original_sources)
    assert (output / 'route_graph.dot').is_file()
    assert 'NOT REPRODUCED' in (output / 'ROUTE_REPORT.md').read_text()
    proposed = json.loads((output / 'contract_patch.json').read_text())
    assert proposed['status'] == 'PROPOSED'


def test_workspace_skill_has_reusable_cli_handoff_without_live_authority(tmp_path):
    skill = ROOT / '.agents/skills/function-extractor/SKILL.md'
    text = skill.read_text()
    assert text.startswith('---\n')
    assert 'name: function-extractor' in text
    assert 'scripts/fe' in text
    entrypoint = skill.parent / 'scripts/fe'
    assert entrypoint.is_file() and os.access(entrypoint, os.X_OK)
    result = subprocess.run([sys.executable, '-B', str(entrypoint), '--help'],
                            cwd=tmp_path, env={'PATH': os.defpath, 'LANG': 'C.UTF-8'},
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    assert result.returncode == 0
    help_text = result.stdout.decode()
    for command in ['discover', 'extract', 'inspect', 'replay', 'matrix', 'compare', 'contracts', 'report', 'verify']:
        assert command in help_text
    # Existence + actual documented CLI workflow proves workspace packaging;
    # it does not prove a new Codex session dynamically discovered this Skill.


def test_container_policy_builds_only_guarded_public_mounts_and_exact_image(tmp_path, monkeypatch):
    import hashlib
    from tools.function_extractor.runner import container
    repo = tmp_path / 'repo'
    selected_path = repo / '.agentos/route-probe/container/IMAGE.json'
    selected_path.parent.mkdir(parents=True)
    public = tmp_path / 'public_capsule'
    files = []
    for rel, data in [('engine/tools/function_extractor/runner/container_entry.py', b'pass\n'),
                      ('site-packages/fixture_dependency.py', b'VALUE = 1\n'),
                      ('libseccomp.so.2', b'notexecuted-unit-fixture')]:
        path = public / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files.append({'path': rel, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    image = 'sha256:' + 'a' * 64
    selected_path.write_text(json.dumps({'image_id': image, 'capsule_root': str(public), 'files': files}))
    monkeypatch.setattr(container, '__file__', str(repo / 'tools/function_extractor/runner/container.py'))
    authorities, commands = [], []
    def fake_lease(target):
        authorities.append(target)
        return {'required': True, 'window_id': 'b' * 32, 'actor_session': 'fixture-only'}
    def fake_command(argv, timeout):
        commands.append((argv, timeout))
        return None, 0, json.dumps({'schema': 'route-probe.trace/v1', 'status': 'RETURNED', 'spans': []}).encode(), b''
    def fake_pack(_bundle, output):
        output.write_text('{}')
    monkeypatch.setattr(container, '_lease', fake_lease)
    monkeypatch.setattr(container, '_command', fake_command)
    monkeypatch.setattr(container, 'pack_bundle', fake_pack)
    result = container.execute_container(tmp_path / 'unused-bundle', {}, timeout=2)
    assert result['status'] == 'RETURNED'
    assert authorities == ['function-extractor:synthetic:' + image]
    assert len(commands) == 1
    argv, budget = commands[0]
    assert argv[:4] == ['/usr/bin/docker', '--host', 'unix:///var/run/docker.sock', 'run']
    assert budget <= 12
    for flag in ['--network=none', '--read-only', '--cap-drop=ALL',
                 '--security-opt=no-new-privileges:true', '--memory=512m',
                 '--memory-swap=512m', '--cpus=1', '--pids-limit=24']:
        assert flag in argv
    assert argv[argv.index('--user') + 1] == '65534:65534'
    assert '--privileged' not in argv and '--cidfile' in argv
    mounts = [argv[i + 1] for i, arg in enumerate(argv) if arg == '--mount']
    assert len(mounts) == 4 and all(item.endswith(',readonly') for item in mounts)
    assert all('docker.sock' not in item and '/srv/moy-gorod/current' not in item
               and str(repo) not in item for item in mounts)
    assert any('src=' + str(public / 'engine') + ',' in item for item in mounts)
    assert any('src=' + str(public / 'site-packages') + ',' in item for item in mounts)
    assert result['container']['authority']['required'] is True
    with pytest.raises(ValueError):
        container.execute_container(tmp_path / 'unused-bundle', {}, image='sha256:' + 'd' * 64)
    assert len(commands) == 1
    (public / files[0]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError):
        container.execute_container(tmp_path / 'unused-bundle', {})
    assert len(commands) == 1


def test_container_lease_requires_real_matching_scope_before_rpc(monkeypatch):
    from types import SimpleNamespace
    from tools.function_extractor.runner import container
    class ExistingCanonicalPath:
        def __init__(self, value): self.value = value
        def is_file(self): return True
        def __str__(self): return self.value
    monkeypatch.setattr(container, 'Path', ExistingCanonicalPath)
    monkeypatch.delenv('LIVE_MUTATION_WINDOW_ID', raising=False)
    monkeypatch.delenv('FE_ACTOR_SESSION', raising=False)
    calls = []
    window, actor = 'a' * 32, 'fixture-session'
    current_actor = ['foreign-session']
    def bounded(argv, env, timeout):
        calls.append(argv)
        assert 'assert-held' in argv and 'open' not in argv and 'renew' not in argv
        assert argv[argv.index('--operation-class') + 1] == 'container_mutation'
        assert argv[argv.index('--target-scope') + 1] == 'fixture-target'
        row = {'window_id': window, 'operation_class': 'container_mutation',
               'target_scope': 'fixture-target', 'actor_session': current_actor[0]}
        return None, 0, json.dumps({'status': 'held', 'window': row}).encode(), b''
    monkeypatch.setattr(container, 'load_engine', lambda _: SimpleNamespace(_bounded_child=bounded))
    with pytest.raises(ValueError):
        container._lease('fixture-target')
    assert calls == []
    monkeypatch.setenv('LIVE_MUTATION_WINDOW_ID', window)
    monkeypatch.setenv('FE_ACTOR_SESSION', actor)
    with pytest.raises(ValueError):
        container._lease('fixture-target')
    current_actor[0] = actor
    assert container._lease('fixture-target')['window_id'] == window
    assert len(calls) == 2


@pytest.mark.parametrize('state', ['no_cid', 'foreign_name', 'exact_owned'])
def test_container_cleanup_is_exact_cid_and_proved_owner_only(tmp_path, monkeypatch, state):
    from tools.function_extractor.runner import container
    cidfile = tmp_path / 'cid'
    cid, name, image, nonce = 'c' * 64, 'fe-replay-' + 'b' * 32, 'sha256:' + 'a' * 64, 'b' * 32
    if state != 'no_cid':
        cidfile.write_text(cid)
    calls = []
    def fake_command(argv, timeout):
        calls.append(argv)
        if 'inspect' in argv:
            observed_name = '/foreign' if state == 'foreign_name' else '/' + name
            data = ' '.join(json.dumps(x) for x in [cid, observed_name, image, nonce]).encode()
            return None, 0, data, b''
        assert argv[-3:] == ['rm', '--force', cid]
        return None, 0, b'', b''
    monkeypatch.setattr(container, '_command', fake_command)
    result = container._remove_owned(cidfile, name, image, nonce)
    if state == 'no_cid':
        assert result == 'UNKNOWN_CREATION_NO_CID' and calls == []
    elif state == 'foreign_name':
        assert result == 'REFUSED_NOT_EXACT_OWNED' and len(calls) == 1
    else:
        assert result == 'OWNED_REMOVED' and len(calls) == 2
        assert calls[-1][-1] == cid and name not in calls[-1]


def test_capsule_extra_or_symlink_refused_before_any_hash_read(tmp_path, monkeypatch):
    import hashlib
    from tools.function_extractor.runner import container
    public = tmp_path / 'public'
    public.mkdir()
    path = public / 'module.py'
    data = b'VALUE = 1\n'
    path.write_bytes(data)
    manifest = [{'path': 'module.py', 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}]
    assert container._capsule(public, manifest) == public
    engine = container.load_engine('route_probe_replay')
    reads = []
    def forbidden_read(*args, **kwargs):
        reads.append(args)
        raise AssertionError('capsule_hash_read_before_inventory_admission')
    monkeypatch.setattr(engine, '_read_public', forbidden_read)
    extra = public / 'extra.py'
    extra.write_text('REPLAY_PRIVATE_CANARY_4bb0')
    with pytest.raises(ValueError):
        container._capsule(public, manifest)
    assert reads == []
    extra.unlink()
    path.unlink()
    outside = tmp_path / 'outside.py'
    outside.write_bytes(data)
    path.symlink_to(outside)
    with pytest.raises(ValueError):
        container._capsule(public, manifest)
    assert reads == []
