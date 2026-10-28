#!/usr/bin/env python3
"""Check selected Atlas source and packaged mirrors; write only with --apply."""
import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

MAX_FILES = 1000
MAX_BYTES = 32 * 1024 * 1024


def require(condition, code):
    if not condition:
        raise ValueError(code)


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def safe(root, relative):
    require(isinstance(relative, str) and relative and not relative.startswith('/')
            and all(p not in ('', '.', '..') for p in relative.split('/')), 'ATLAS_SYNC_PATH')
    path = root / relative
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'ATLAS_SYNC_SYMLINK')
    return path


def tree(root):
    require(root.is_dir() and not root.is_symlink(), 'ATLAS_SOURCE_REQUIRED')
    result = {}
    total = 0
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        safe(root, relative)
        if path.is_dir():
            continue
        require(path.is_file(), 'ATLAS_SOURCE_ENTRY')
        total += path.stat().st_size
        require(len(result) < MAX_FILES and total <= MAX_BYTES, 'ATLAS_SOURCE_BOUND')
        result[relative] = path.read_bytes()
    require(result, 'ATLAS_SOURCE_EMPTY')
    return result


def source_model(root):
    provenance_path = safe(root, 'src/agent_os/resources/docs/ATLAS_SOURCE.json')
    require(provenance_path.is_file() and provenance_path.stat().st_size <= 512 * 1024,
            'ATLAS_PROVENANCE_REQUIRED')
    provenance = json.loads(provenance_path.read_bytes())
    require(provenance.get('schema') == 'agent-os.atlas-source/v1', 'ATLAS_PROVENANCE_SCHEMA')
    rows = provenance.get('files')
    require(isinstance(rows, list) and 0 < len(rows) <= MAX_FILES, 'ATLAS_PROVENANCE_MEMBERS')
    expected = {}
    for row in rows:
        require(isinstance(row, dict) and set(row) ==
                {'path', 'bytes', 'sha256', 'source_bytes', 'source_sha256'}, 'ATLAS_PROVENANCE_ROW')
        safe(root, row['path'])
        require(row['path'] not in expected, 'ATLAS_PROVENANCE_DUPLICATE')
        expected[row['path']] = {'bytes': row['bytes'], 'sha256': row['sha256']}
    source = tree(safe(root, 'modules/atlas'))
    actual = {p: pin(raw) for p, raw in source.items()}
    require(actual == expected, 'ATLAS_SELECTED_SOURCE_MISMATCH')
    actual_digest = hashlib.sha256(json.dumps(actual, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    require(actual_digest == provenance.get('selected_tree_sha256'), 'ATLAS_PROVENANCE_DIGEST')
    return source, provenance


def synchronize(root, *, apply=False):
    root = Path(root).resolve()
    source, provenance = source_model(root)
    targets = {'src/agent_os/resources/' + relative: raw for relative, raw in source.items()
               if relative.startswith('skills/atlas/')}
    require(targets, 'ATLAS_SKILL_EMPTY')
    targets['src/agent_os/resources/docs/ATLAS.md'] = safe(root, 'docs/ATLAS.md').read_bytes()
    skill = safe(root, 'src/agent_os/resources/skills/atlas')
    if skill.exists():
        require(skill.is_dir(), 'ATLAS_RESOURCE_DIRECTORY')
        for path in skill.rglob('*'):
            relative = path.relative_to(root).as_posix()
            safe(root, relative)
            if path.is_file():
                require(relative in targets, 'ATLAS_RESOURCE_EXTRA_MEMBER')
            else:
                require(path.is_dir(), 'ATLAS_RESOURCE_ENTRY')
    changed = []
    for relative, raw in sorted(targets.items()):
        path = safe(root, relative)
        require(not path.exists() or path.is_file(), 'ATLAS_RESOURCE_CONFLICT')
        if not path.exists() or path.read_bytes() != raw:
            changed.append(relative)
    if apply:
        for relative in changed:
            path = safe(root, relative)
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.parent / ('.' + path.name + '.atlas-sync-' + str(os.getpid()))
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), mode)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(targets[relative])
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, mode)
                safe(root, relative)
                os.replace(temporary, path)
            finally:
                if temporary.exists():
                    temporary.unlink()
            require(path.read_bytes() == targets[relative], 'ATLAS_SYNC_READBACK')
    return {'schema': 'agent-os.atlas-sync/v1',
            'status': 'SYNCED' if apply and changed else 'PASS' if not changed else 'FAIL',
            'apply': apply, 'source_files': len(source), 'skill_files': len(targets) - 1,
            'selected_tree_sha256': provenance['selected_tree_sha256'],
            'changed_file_count': len(changed), 'changed_files': changed,
            'effects': 'SELECTED_MIRRORS_ONLY' if apply and changed else 'NONE'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = synchronize(Path(__file__).resolve().parents[1], apply=args.apply)
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
        result = {'schema': 'agent-os.atlas-sync/v1', 'status': 'REFUSED', 'code': str(exc)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] in ('PASS', 'SYNCED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
