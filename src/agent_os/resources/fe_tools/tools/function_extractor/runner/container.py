"""Bounded exact-owned offline containers; no production or credential mounts."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid
from .bundle import canonical, pack_bundle
from .loader import load_engine

_DOCKER = ['/usr/bin/docker', '--host', 'unix:///var/run/docker.sock']
_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'TZ': 'UTC'}


def _command(argv, timeout):
    return load_engine('route_probe_replay')._bounded_child(argv, _ENV, timeout)


def _capsule(root, manifest, public_binary_pins=()):
    engine = load_engine('route_probe_replay')
    root = load_engine('route_probe_graph')._safe_path(Path(root))
    if not root.is_dir() or root == Path('/') or root.is_relative_to(Path('/srv/moy-gorod/current')):
        raise ValueError('capsule_root')
    if not 1 <= len(manifest) <= 3000:
        raise ValueError('capsule_files')
    # A selected, immutable public wheel may contain a native module larger
    # than the ordinary file budget. Admission is explicit and bound to its
    # exact existing manifest row; no source-file or overall budget changes.
    if type(public_binary_pins) not in (tuple, list) or len(public_binary_pins) > 8:
        raise ValueError('capsule_binary_pins')
    binary_paths = set()
    for pin in public_binary_pins:
        if type(pin) is not dict or set(pin) != {'path', 'bytes', 'sha256'}:
            raise ValueError('capsule_binary_pin_schema')
        rel = Path(pin['path']) if type(pin['path']) is str else Path('/')
        if (rel.is_absolute() or '..' in rel.parts or len(rel.parts) < 3
                or rel.parts[0] != 'site-packages'
                or not re.fullmatch(r'[A-Za-z0-9_.-]+\.so', rel.name)
                or pin['path'] in binary_paths or type(pin['bytes']) is not int
                or not 4_000_000 < pin['bytes'] <= 8_000_000
                or type(pin['sha256']) is not str or not re.fullmatch(r'[a-f0-9]{64}', pin['sha256'])
                or pin not in manifest):
            raise ValueError('capsule_binary_pin')
        binary_paths.add(pin['path'])
    actual = set()
    for directory, directories, files in os.walk(root, followlinks=False):
        if len(actual) + len(files) > 3000:
            raise ValueError('capsule_inventory_bound')
        for name in directories + files:
            candidate = Path(directory) / name
            if candidate.is_symlink():
                raise ValueError('capsule_symlink')
        actual.update(str((Path(directory) / name).relative_to(root)) for name in files)
    if actual != {row['path'] for row in manifest}:
        raise ValueError('capsule_unmanifested_file')
    total = 0
    for row in manifest:
        rel = Path(row['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('capsule_path')
        cap = 8_000_000 if row['path'] in binary_paths else 4_000_000
        data = engine._read_public(load_engine('route_probe_graph')._safe_path(root / rel), cap)
        total += len(data)
        if total > 64_000_000 or len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('capsule_pin')
    return root


def _lease(target):
    """Assert existing RU-01 own controls; never open, renew, or invent a grant."""
    script = Path('/srv/moy-gorod/current/scripts/live_mutation_window.py')
    if not script.is_file():
        return {'required': False, 'reason': 'canonical_ru_route_not_installed'}
    window = os.environ.get('LIVE_MUTATION_WINDOW_ID', '')
    actor = os.environ.get('FE_ACTOR_SESSION', '')
    if not re.fullmatch(r'[a-f0-9]{32}', window) or not actor:
        raise ValueError('own_container_lease_required')
    env = dict(_ENV, LIVE_MUTATION_WINDOW_ID=window)
    failure, code, output, _ = load_engine('route_probe_replay')._bounded_child([
        '/srv/moy-gorod/current/.venv/bin/python', str(script), 'assert-held',
        '--operation-class', 'container_mutation', '--target-scope', target], env, 45)
    if failure or code:
        raise ValueError('canonical_container_lease_refused')
    value = json.loads(output)
    row = value.get('window', {})
    if (value.get('status') != 'held' or row.get('window_id') != window
            or row.get('operation_class') != 'container_mutation' or row.get('target_scope') != target
            or row.get('actor_session') != actor):
        raise ValueError('container_lease_identity')
    return {'required': True, 'window_id': window, 'actor_session': actor, 'target_scope': target}


def _remove_owned(cidfile, name, image, nonce):
    """Remove on timeout only after exact CID/image/name/nonce ownership proof."""
    if not cidfile.is_file():
        return 'UNKNOWN_CREATION_NO_CID'
    cid = cidfile.read_text().strip()
    if not re.fullmatch(r'[a-f0-9]{64}', cid):
        return 'UNKNOWN_CID'
    fmt = '{{json .Id}} {{json .Name}} {{json .Image}} {{json (index .Config.Labels "function-extractor.nonce")}}'
    failure, code, output, _ = _command(_DOCKER + ['inspect', '--format', fmt, cid], 5)
    if failure or code:
        return 'UNKNOWN_INSPECT'
    try:
        values = [json.loads(field) for field in output.decode().split()]
    except Exception:
        return 'UNKNOWN_INSPECT'
    if values != [cid, '/' + name, image, nonce]:
        return 'REFUSED_NOT_EXACT_OWNED'
    failure, code, _, _ = _command(_DOCKER + ['rm', '--force', cid], 5)
    return 'OWNED_REMOVED' if not failure and code == 0 else 'UNKNOWN_REMOVE'


def execute_container(bundle, fixture, *, timeout=10, image=None, contract_plan=None, runner_sha256=None):
    repo = Path(__file__).resolve().parents[3]
    path = repo / '.agentos' / 'route-probe' / 'container' / 'IMAGE.json'
    if not path.is_file():
        return {'schema': 'route-probe.trace/v1', 'status': 'REFUSED', 'reason': 'qualified_test_image_missing', 'spans': []}
    from .environment_catalog import select_bound_profile
    if (repo / '.agentos/route-probe/container/ENVIRONMENTS.json').is_file():
        from .environment_catalog import discover
        selection = discover(repo)
        if selection["status"] != "EXISTING_QUALIFIED":
            return {'schema': 'route-probe.trace/v1', 'status': 'REFUSED',
                    'reason': 'qualified_environment_' + selection['status'].lower(), 'spans': []}
        try:
            selected = select_bound_profile(repo, selected_image=image)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else 'candidate_profile_not_bound'
            return {'schema': 'route-probe.trace/v1', 'status': 'REFUSED',
                    'reason': reason if reason.startswith('qualified_environment_') else 'candidate_profile_not_bound', 'spans': []}
    else:
        selected = json.loads(load_engine('route_probe_replay')._read_public(path, 1_000_000))
    selected_image = selected['image_id']
    if (type(selected_image) is not str or not re.fullmatch(r'sha256:[a-f0-9]{64}', selected_image)
            or image not in (None, selected_image) or not 0 < timeout <= 30):
        raise ValueError('container_image_or_budget')
    image = selected_image
    public = _capsule(selected['capsule_root'], selected['files'], selected.get('public_binary_pins', ()))
    assets = load_engine('route_probe_replay')._public_assets(fixture)
    asset_mounts = []
    for row in assets:
        asset = public / 'assets' / 'Asia_Vladivostok'
        if hashlib.sha256(load_engine('route_probe_replay')._read_public(asset, 16384)).hexdigest() != row['sha256']:
            raise ValueError('container_public_asset_pin')
        asset_mounts += ['--mount', f'type=bind,src={asset},dst={row["path"]},readonly']
    target = 'function-extractor:synthetic:' + image
    authority = _lease(target)
    nonce = uuid.uuid4().hex
    name = 'fe-replay-' + nonce
    with tempfile.TemporaryDirectory(prefix='fe-container-') as temp:
        temp = Path(temp); temp.chmod(0o755)
        inputs = temp / 'input'; inputs.mkdir(); inputs.chmod(0o755)
        portable = inputs / 'route_bundle.json'
        pack_bundle(bundle, portable); portable.chmod(0o644)
        request = inputs / 'fixture.json'; request.write_bytes(canonical(fixture)); request.chmod(0o644)
        observation_args = []
        if contract_plan is not None:
            from ..wire_contract import validate_contract_observation_plan
            manifest = load_engine('route_probe_replay')._verify(bundle)
            if (validate_contract_observation_plan(contract_plan, manifest).get('status') != 'VALID'
                    or type(runner_sha256) is not str or not re.fullmatch(r'[a-f0-9]{64}', runner_sha256)):
                raise ValueError('container_observation_plan')
            plan_path = inputs / 'contract_plan.json'
            plan_path.write_bytes(canonical(contract_plan)); plan_path.chmod(0o644)
            observation_args = ['/input/contract_plan.json', runner_sha256]
        cidfile = temp / 'cid'
        args = _DOCKER + ['run', '--pull=never', '--rm', '--name', name, '--cidfile', str(cidfile),
                '--label', 'function-extractor.owned=0.3.0', '--label', 'function-extractor.nonce=' + nonce,
                '--network=none', '--read-only', '--user', '65534:65534', '--cap-drop=ALL',
                '--security-opt=no-new-privileges:true', '--memory=512m', '--memory-swap=512m',
                '--cpus=1', '--pids-limit=24', '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m,mode=1777',
                '--mount', f'type=bind,src={public / "engine"},dst=/opt/fe,readonly',
                '--mount', f'type=bind,src={public / "site-packages"},dst=/usr/local/lib/python3.11/site-packages,readonly',
                '--mount', f'type=bind,src={public / "libseccomp.so.2"},dst=/usr/lib/x86_64-linux-gnu/libseccomp.so.2,readonly',
                '--mount', f'type=bind,src={inputs},dst=/input,readonly',
                *asset_mounts, '--entrypoint', 'python', image, '-I', '-B', '/opt/fe/tools/function_extractor/runner/container_entry.py',
                '/input/route_bundle.json', '/input/fixture.json', str(timeout), *observation_args]
        start = time.monotonic()
        failure, code, stdout, stderr = _command(args, timeout + 10)
        cleanup = 'AUTO_REMOVE_ON_EXIT'
        if failure:
            cleanup = _remove_owned(cidfile, name, image, nonce)
            result = {'schema': 'route-probe.trace/v1', 'status': 'TIMEOUT' if failure == 'whole_replay_deadline' else 'REFUSED',
                      'reason': failure, 'spans': []}
        else:
            try:
                result = json.loads(stdout)
                if code or result.get('schema') != 'route-probe.trace/v1':
                    raise ValueError('container_protocol')
            except Exception:
                cleanup = _remove_owned(cidfile, name, image, nonce)
                result = {'schema': 'route-probe.trace/v1', 'status': 'REFUSED', 'reason': 'container_protocol', 'spans': []}
        result['container'] = {'image_id': image, 'name': name, 'network': 'none', 'read_only': True,
            'user': '65534:65534', 'cap_drop': ['ALL'], 'no_new_privileges': True, 'memory_mb': 512, 'pids_limit': 24,
            'elapsed_seconds': time.monotonic() - start, 'cleanup': cleanup, 'client_exit_code': code,
            'stderr_bytes_suppressed': len(stderr), 'capsule_sha256': hashlib.sha256(canonical(selected['files'])).hexdigest(),
            'authority': authority}
        return result
