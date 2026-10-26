#!/usr/bin/env python3
"""Verify a local Atlas candidate wheel; build only from explicit selection.

Default: read the candidate in dist/atlas-candidate and run an isolated temporary
wheel probe. --output selects a separate dist/<name> without moving old receipts.
--build-selection selects an already installed offline build
interpreter and the declared setuptools backend. This qualified candidate path
does not modify or bypass the repository's stable release pins or publisher.
"""
import argparse
import base64
import configparser
import csv
import hashlib
import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MAX_SOURCE_BYTES = 128 * 1024 * 1024


def require(condition, code):
    if not condition:
        raise ValueError(code)


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def safe_file(path, *, limit=MAX_SOURCE_BYTES):
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
            'PACKAGE_REGULAR_FILE_REQUIRED')
    require(path.stat().st_size <= limit, 'PACKAGE_FILE_BOUND')
    raw = path.read_bytes()
    require(len(raw) <= limit, 'PACKAGE_FILE_BOUND')
    return raw


def sources(root):
    result = {}
    source = root / 'src/agent_os'
    require(source.is_dir(), 'PACKAGE_SOURCE_REQUIRED')
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if '__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo'):
            continue
        require(not path.is_symlink(), 'PACKAGE_SOURCE_SYMLINK')
        if path.is_dir():
            continue
        require(len(result) < 100_000, 'PACKAGE_SOURCE_MEMBER_BOUND')
        result[relative] = safe_file(path)
    for relative in ('pyproject.toml', 'README.md', 'LICENSE', 'LICENSE.txt', 'LICENSE.md', 'NOTICE'):
        path = root / relative
        if path.exists():
            result[relative] = safe_file(path)
    require('pyproject.toml' in result and 'README.md' in result
            and sum(map(len, result.values())) <= MAX_SOURCE_BYTES, 'PACKAGE_SOURCE_BOUND')
    return result


def selected_sync(root):
    spec = importlib.util.spec_from_file_location('_atlas_selected_sync', root / 'tools/sync_atlas.py')
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
        result = module.synchronize(root)
    finally:
        sys.dont_write_bytecode = previous
    require(result['status'] == 'PASS', 'ATLAS_RESOURCE_SYNC_REQUIRED')
    return result


def candidate_output(root, output=None, *, for_build=False):
    """Select exactly one dist child; never redirect or replace an old build."""
    root = Path(root).absolute()
    require(root.is_dir() and not any(p.is_symlink() for p in (root, *root.parents)),
            'CANDIDATE_ROOT_REQUIRED')
    value = 'dist/atlas-candidate' if output is None else os.fspath(output)
    require(isinstance(value, str) and 0 < len(value) <= 4096 and '\x00' not in value
            and '\\' not in value and all(p not in ('.', '..') for p in value.split('/')),
            'CANDIDATE_OUTPUT_PATH')
    selected = Path(value)
    require(selected.as_posix() == value, 'CANDIDATE_OUTPUT_PATH')
    if selected.is_absolute():
        try:
            selected = selected.relative_to(root)
        except ValueError as exc:
            raise ValueError('CANDIDATE_OUTPUT_SCOPE') from exc
    require(len(selected.parts) == 2 and selected.parts[0] == 'dist'
            and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', selected.parts[1]),
            'CANDIDATE_OUTPUT_SCOPE')
    target = root / selected
    require(not any(p.is_symlink() for p in (target, *target.parents)),
            'CANDIDATE_OUTPUT_SYMLINK')
    require(not target.parent.exists() or target.parent.is_dir(), 'CANDIDATE_OUTPUT_PARENT')
    if for_build:
        require(not target.exists(), 'CANDIDATE_EXISTS_RECONCILE')
    else:
        require(target.is_dir(), 'CANDIDATE_OUTPUT_REQUIRED')
    return target


def build_candidate(root, selected, source, version, output=None):
    output = candidate_output(root, output, for_build=True)
    selection_raw = safe_file(Path(selected).absolute(), limit=64 * 1024)
    selection = json.loads(selection_raw)
    require(set(selection) == {'schema', 'interpreter', 'python_version', 'build_versions',
                               'source_date_epoch', 'qualification'}, 'BUILD_SELECTION_FIELDS')
    require(selection['schema'] == 'agent-os.atlas-local-build/v1'
            and selection['qualification'] == 'LOCAL_CANDIDATE_ONLY', 'BUILD_SELECTION_SCOPE')
    interpreter = Path(selection['interpreter'])
    require(interpreter.is_absolute() and interpreter.is_file(), 'BUILD_INTERPRETER_REQUIRED')
    require(type(selection['source_date_epoch']) is int
            and selection['source_date_epoch'] >= 315532800, 'BUILD_EPOCH')
    require(set(selection['build_versions']) == {'build', 'setuptools', 'wheel'}, 'BUILD_TOOL_SELECTION')
    observation = subprocess.run(
        [str(interpreter), '-I', '-B', '-c',
         "import importlib.metadata,json,platform;print(json.dumps({'python_version':platform.python_version(),"
         "'build_versions':{p:importlib.metadata.version(p) for p in ('build','setuptools','wheel')}}))"],
        check=True, capture_output=True, timeout=15)
    observed = json.loads(observation.stdout)
    require(observed['python_version'] == selection['python_version']
            and observed['build_versions'] == selection['build_versions'], 'BUILD_TOOL_IDENTITY_CHANGED')
    # Recheck after interpreter qualification, then create the selected directory
    # exclusively. No cleanup or overwrite is performed after an interrupted build.
    output = candidate_output(root, output, for_build=True)
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'schema': 'agent-os.atlas-candidate-build/v1', 'status': 'BUILD_STARTED',
               'qualification': 'LOCAL_CANDIDATE_ONLY', 'version': version,
               'selection': {'path': str(Path(selected).absolute()), **pin(selection_raw)},
               'interpreter': {'selected': str(interpreter), 'resolved': str(interpreter.resolve()),
                               **pin(interpreter.resolve().read_bytes()), **observed},
               'source_date_epoch': selection['source_date_epoch'],
               'source_files': {p: pin(raw) for p, raw in source.items()},
               'dependency_installation': 'NOT_PERFORMED', 'publication': 'NOT_PERFORMED'}
    try:
        with tempfile.TemporaryDirectory(prefix='agentos-atlas-candidate-source-') as name:
            clean = Path(name).resolve()
            for relative, raw in source.items():
                path = clean / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            environment = os.environ.copy()
            environment.update({'SOURCE_DATE_EPOCH': str(selection['source_date_epoch']),
                                'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1',
                                'PIP_NO_INDEX': '1', 'PIP_DISABLE_PIP_VERSION_CHECK': '1'})
            result = subprocess.run([str(interpreter), '-I', '-B', '-m', 'build', '--wheel',
                                     '--no-isolation', '--outdir', str(output)], cwd=clean,
                                    env=environment, capture_output=True, timeout=95)
            (output / 'BUILD_STDOUT.txt').write_bytes(result.stdout)
            (output / 'BUILD_STDERR.txt').write_bytes(result.stderr)
            receipt['builder_exit_code'] = result.returncode
            receipt['stdout'] = pin(result.stdout)
            receipt['stderr'] = pin(result.stderr)
            require(result.returncode == 0, 'LOCAL_CANDIDATE_BUILD_FAILED')
        wheels = list(output.glob('*.whl'))
        require(len(wheels) == 1, 'CANDIDATE_WHEEL_COUNT')
        receipt['wheel'] = {'name': wheels[0].name, **pin(wheels[0].read_bytes())}
        receipt['status'] = 'BUILD_SUCCEEDED'
    except Exception as exc:
        receipt['status'] = 'BUILD_FAILED'
        receipt['failure'] = type(exc).__name__ + ':' + str(exc)
        if isinstance(exc, subprocess.TimeoutExpired):
            (output / 'BUILD_STDOUT.txt').write_bytes(exc.stdout or b'')
            (output / 'BUILD_STDERR.txt').write_bytes(exc.stderr or b'')
        raise
    finally:
        (output / 'BUILD_RECEIPT.json').write_bytes(canonical(receipt))
    return output


PROBE = r'''
import contextlib,importlib,io,json,os,sys
from pathlib import Path
root,home,version=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
sys.path.insert(0,str(root))
os.environ['HOME']=str(home)
project=home/'synthetic-project';project.mkdir()
registry=home/'registry.json'
rows=[{'key':'synthetic','root':str(project),'binding':'.atlas/UPSTREAM.json'}]
registry.write_text(json.dumps({'schema':'atlas.workspace/v1','projects':rows}))
import agent_os
from agent_os import atlas_module,cli
assert agent_os.__version__==version
assert Path(atlas_module.__file__).resolve().is_relative_to(root.resolve())
expected={'schema':'atlas.workspace.list/v1','projects':rows}
for function,args in ((cli.main,['atlas','--registry',str(registry),'list']),
                      (atlas_module.main,['--registry',str(registry),'list'])):
    output=io.StringIO()
    with contextlib.redirect_stdout(output): code=function(args)
    assert code==0 and json.loads(output.getvalue())==expected
assert not (home/'.agentos').exists() and not (home/'.agentos-user').exists()
assert not (project/'.atlas').exists()
print(json.dumps({'status':'PASS','scope':'UNPACKED_WHEEL_SYNTHETIC_HOME',
                  'entry_routes':['agentos atlas','atlasctl'], 'configuration_effects':'NONE',
                  'runtime_installation':'NOT_PERFORMED'}))
'''


def verify(root, source, version, project, output=None):
    output = candidate_output(root, output)
    receipt_raw = safe_file(output / 'BUILD_RECEIPT.json', limit=8 * 1024 * 1024)
    receipt = json.loads(receipt_raw)
    require(receipt.get('schema') == 'agent-os.atlas-candidate-build/v1'
            and receipt.get('status') == 'BUILD_SUCCEEDED' and receipt.get('version') == version,
            'CANDIDATE_BUILD_RECEIPT_REQUIRED')
    expected_source = {p: pin(raw) for p, raw in source.items()}
    require(receipt.get('source_files') == expected_source, 'CANDIDATE_SOURCE_CHANGED')
    wheels = list(output.glob('*.whl'))
    require(len(wheels) == 1, 'CANDIDATE_WHEEL_COUNT')
    wheel = wheels[0]
    raw_wheel = safe_file(wheel)
    require({'name': wheel.name, **pin(raw_wheel)} == receipt['wheel'], 'CANDIDATE_WHEEL_CHANGED')
    with zipfile.ZipFile(io.BytesIO(raw_wheel)) as archive:
        infos = archive.infolist()
        require(len(infos) <= 100_000 and sum(i.file_size for i in infos) <= MAX_SOURCE_BYTES,
                'WHEEL_BOUND')
        names = [i.filename for i in infos]
        require(len(names) == len(set(names)), 'WHEEL_DUPLICATE_MEMBER')
        payload = {}
        for info in infos:
            rel = PurePosixPath(info.filename)
            require(not rel.is_absolute() and rel.parts and all(p not in ('', '.', '..') for p in rel.parts)
                    and '\\' not in info.filename and not stat.S_ISLNK(info.external_attr >> 16)
                    and not (info.flag_bits & 1), 'WHEEL_UNSAFE_MEMBER')
            if info.is_dir():
                continue
            payload[info.filename] = archive.read(info)
    dist_info = [name.rsplit('/', 1)[0] for name in payload if name.endswith('.dist-info/METADATA')]
    require(len(dist_info) == 1, 'WHEEL_METADATA_COUNT')
    dist = dist_info[0]
    metadata = BytesParser().parsebytes(payload[dist + '/METADATA'])
    require(metadata['Name'] == project['name'] and metadata['Version'] == version, 'WHEEL_IDENTITY')
    require(metadata['Requires-Python'] == project['requires-python'], 'WHEEL_PYTHON_CONTRACT')
    record_name = dist + '/RECORD'
    records = list(csv.reader(io.StringIO(payload[record_name].decode())))
    require(all(len(row) == 3 for row in records) and len(records) == len(payload)
            and {row[0] for row in records} == set(payload), 'WHEEL_RECORD_MEMBERS')
    for name, digest, size in records:
        if name == record_name:
            require(digest == size == '', 'WHEEL_RECORD_SELF')
        else:
            encoded = base64.urlsafe_b64encode(hashlib.sha256(payload[name]).digest()).rstrip(b'=').decode()
            require(digest == 'sha256=' + encoded and size == str(len(payload[name])), 'WHEEL_RECORD_HASH')
    expected_package = {relative.removeprefix('src/'): raw for relative, raw in source.items()
                        if relative.startswith('src/agent_os/')}
    actual_package = {name: raw for name, raw in payload.items() if name.startswith('agent_os/')}
    require(actual_package == expected_package, 'WHEEL_PACKAGE_SOURCE_MISMATCH')
    generated = {dist + '/' + name for name in
                 ('METADATA', 'WHEEL', 'entry_points.txt', 'top_level.txt', 'RECORD')}
    licenses = {dist + '/licenses/' + name: source[name] for name in
                ('LICENSE', 'LICENSE.txt', 'LICENSE.md', 'NOTICE') if name in source}
    require(set(payload) <= set(expected_package) | generated | set(licenses),
            'WHEEL_UNREVIEWED_MEMBER')
    require({dist + '/' + name for name in ('METADATA', 'WHEEL', 'entry_points.txt', 'RECORD')}
            <= set(payload), 'WHEEL_GENERATED_MEMBER_MISSING')
    for name, raw in licenses.items():
        if name in payload:
            require(payload[name] == raw, 'WHEEL_LICENSE_SOURCE_MISMATCH')
    for name in metadata.get_all('License-File', []):
        target = dist + '/licenses/' + name
        require(target in licenses and target in payload, 'WHEEL_LICENSE_DECLARATION')
    wheel_metadata = BytesParser().parsebytes(payload[dist + '/WHEEL'])
    require(wheel_metadata['Wheel-Version'] == '1.0'
            and wheel_metadata['Root-Is-Purelib'] == 'true'
            and wheel_metadata.get_all('Tag') == ['py3-none-any'], 'WHEEL_PLATFORM_CONTRACT')
    if dist + '/top_level.txt' in payload:
        require(payload[dist + '/top_level.txt'].decode().split() == ['agent_os'], 'WHEEL_TOP_LEVEL')
    entries = configparser.ConfigParser(interpolation=None)
    entries.optionxform = str
    entries.read_string(payload[dist + '/entry_points.txt'].decode())
    require(dict(entries['console_scripts']) == project['scripts'], 'WHEEL_ENTRY_POINTS')
    require(project['scripts'].get('atlasctl') == 'agent_os.atlas_module:main'
            and project['scripts'].get('agentos') == 'agent_os.cli:main', 'ATLAS_ENTRY_POINT_CONTRACT')
    with tempfile.TemporaryDirectory(prefix='agentos-atlas-wheel-probe-') as name:
        temporary = Path(name).resolve()
        extracted = temporary / 'wheel'
        home = temporary / 'synthetic-home'
        extracted.mkdir(); home.mkdir()
        for relative, raw in payload.items():
            path = extracted / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        result = subprocess.run([sys.executable, '-I', '-B', '-c', PROBE, str(extracted), str(home), version],
                                cwd=home, capture_output=True, timeout=15)
        require(result.returncode == 0, 'WHEEL_PROBE_FAILED:' + result.stderr.decode(errors='replace')[-3000:])
        probe = json.loads(result.stdout)
    require({p: pin(raw) for p, raw in sources(root).items()} == expected_source,
            'SOURCE_CHANGED_DURING_VERIFICATION')
    return {'schema': 'agent-os.atlas-package-verification/v1', 'status': 'PASS',
            'qualification': 'LOCAL_CANDIDATE_ONLY', 'version': version,
            'wheel': {'path': str(wheel), **pin(raw_wheel)},
            'build_receipt': {'path': str(output / 'BUILD_RECEIPT.json'), **pin(receipt_raw)},
            'source_files': len(source), 'source_files_sha256': hashlib.sha256(canonical(expected_source)).hexdigest(),
            'wheel_members': len(payload), 'record_rows': len(records),
            'packaged_source_files': len(expected_package), 'entry_points': project['scripts'],
            'probe': probe, 'runtime_installation': 'NOT_PERFORMED', 'publication': 'NOT_PERFORMED'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--build-selection', help='Explicit recorded existing offline build interpreter JSON')
    parser.add_argument('--output', default='dist/atlas-candidate',
                        help='Selected dist/<name> candidate directory; default: dist/atlas-candidate')
    args = parser.parse_args(argv)
    try:
        sync = selected_sync(ROOT)
        source = sources(ROOT)
        project = tomllib.loads(source['pyproject.toml'].decode())['project']
        version = project['version']
        require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:rc[0-9]+)?\+atlas\.[0-9]+', version),
                'LOCAL_ATLAS_CANDIDATE_VERSION_REQUIRED')
        if args.build_selection:
            build_candidate(ROOT, args.build_selection, source, version, output=args.output)
        result = verify(ROOT, source, version, project, output=args.output)
        result['selected_tree_sha256'] = sync['selected_tree_sha256']
    except (ValueError, OSError, UnicodeError, KeyError, TypeError, subprocess.SubprocessError,
            zipfile.BadZipFile, configparser.Error, csv.Error) as exc:
        result = {'schema': 'agent-os.atlas-package-verification/v1', 'status': 'REFUSED',
                  'code': str(exc), 'qualification': 'LOCAL_CANDIDATE_ONLY',
                  'candidate_readback': str(ROOT / args.output),
                  'runtime_installation': 'NOT_PERFORMED', 'publication': 'NOT_PERFORMED'}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
