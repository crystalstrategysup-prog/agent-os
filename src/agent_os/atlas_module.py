"""Local Atlas CLI routing with explicit registry selection and bounded stdout.

The selected packaged Atlas workspace remains the method implementation. This
module neither discovers private projects nor initializes AgentOS configuration.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib
import io
import json
import sys
from pathlib import Path
from typing import Iterator

MAX_STDOUT_BYTES = 32 * 1024
_MODULE_NAMES = ('navigator', 'atlas', 'import_matrix', 'catalog', 'workspace', 'sync_docs', 'checkpoint', 'history_requalification', 'display_fields', 'work_profile', 'source_relocation')
_SCRIPTS = Path(__file__).resolve().parent / 'resources' / 'skills' / 'atlas' / 'scripts'


class AtlasModuleError(ValueError):
    """A facade prerequisite was refused before workspace execution."""


def default_registry() -> Path:
    return Path.home() / '.agentos-user' / 'knowledge' / 'atlas' / 'PROJECTS.json'


@contextlib.contextmanager
def _workspace() -> Iterator[object]:
    """Scope the standalone module's existing bare imports to this CLI call."""
    if not _SCRIPTS.is_dir() or any(p.is_symlink() for p in (_SCRIPTS, *_SCRIPTS.parents)):
        raise AtlasModuleError('ATLAS_PACKAGED_SCRIPTS_REQUIRED')
    for name in _MODULE_NAMES:
        if name in sys.modules:
            module = sys.modules[name]
            origin = getattr(module, '__file__', None)
            if origin is None or Path(origin).resolve() != _SCRIPTS / (name + '.py'):
                raise AtlasModuleError('ATLAS_MODULE_NAME_CONFLICT:' + name)
    previous_path = list(sys.path)
    previous_modules = {name: sys.modules[name] for name in _MODULE_NAMES if name in sys.modules}
    previous_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(_SCRIPTS))
        yield importlib.import_module('workspace')
    finally:
        sys.path[:] = previous_path
        sys.dont_write_bytecode = previous_bytecode
        for name in _MODULE_NAMES:
            if name in previous_modules:
                sys.modules[name] = previous_modules[name]
            else:
                sys.modules.pop(name, None)


def _small(value, *, depth=0):
    """An explicitly bounded sample; this never claims full row coverage."""
    if value is None or type(value) in (bool, int, float):
        return value
    if isinstance(value, str):
        if len(value.encode('utf-8')) <= 1024:
            return value
        return {'omitted_text_bytes': len(value.encode('utf-8')),
                'sha256': hashlib.sha256(value.encode('utf-8')).hexdigest()}
    if isinstance(value, list):
        return {'count': len(value), 'sample': [] if depth >= 3 else
                [_small(item, depth=depth + 1) for item in value[:3]],
                'omitted': max(0, len(value) - (0 if depth >= 3 else min(3, len(value))))}
    if isinstance(value, dict):
        keys = list(value)
        selected = keys[:10] if depth < 3 else []
        return {'fields': {key: _small(value[key], depth=depth + 1) for key in selected},
                'field_count': len(keys), 'omitted_fields': len(keys) - len(selected)}
    return {'omitted_type': type(value).__name__}


_CONTROL_FIELDS = frozenset({
    'schema', 'status', 'code', 'effect', 'effects', 'generation', 'fingerprint',
    'plan_sha256', 'manifest_sha256', 'source_sha256', 'project_sha256',
    'current_manifest_sha256', 'lock_present', 'has_more', 'next_cursor',
    'cursor_anchor', 'ancestry_to_current', 'source_validation', 'raw_source_reads',
    'orphan_scan', 'order', 'matrix_history_total', 'product_execution',
    'matrix_writes', 'source_step_count', 'source_event_count',
    'matrix_history_count', 'matrix_history_page_count',
    'operation_id', 'phase', 'source_effect', 'pending', 'record_sha256', 'replayed',
    'prepared_record', 'error', 'work_recording', 'document_changes', 'activity',
    'work_id', 'executor_id', 'next_action', 'event_id', 'recorded_status',
})
_CONTROL_BRANCHES = ('projection', 'refresh', 'cycle', 'state', 'pending',
                     'doc_sync_pending', 'output_current', 'current', 'readback',
                     'history_limit', 'capacity', 'semantic_counts', 'receipt',
                     'source_before', 'source_after', 'current_view')


def _control(value, *, depth=0, all_scalars=False):
    """Keep operation outcomes, recovery identity and pagination separate from rows."""
    if not isinstance(value, dict):
        return value if value is None or type(value) in (str, bool, int, float) else None
    if depth > 3:
        return {'control_complete': False, 'omitted_reason': 'CONTROL_DEPTH_BOUND'}
    result = {}
    for key, item in value.items():
        if (all_scalars or key in _CONTROL_FIELDS) and (item is None or type(item) in (str, bool, int, float)):
            result[key] = _small(item)
    for key in _CONTROL_BRANCHES:
        if key in value:
            result[key] = _control(value[key], depth=depth + 1, all_scalars=True)
    for rows_key in ('files', 'observed'):
        rows = value.get(rows_key)
        if not isinstance(rows, list):
            continue
        counts = {}
        for row in rows:
            state = row.get('state', 'UNSPECIFIED') if isinstance(row, dict) else 'INVALID_ROW'
            state = state if isinstance(state, str) else 'INVALID_STATE'
            counts[state] = counts.get(state, 0) + 1
        # The document-sync API declares BEFORE/AFTER/CONFLICT. Count every
        # retained row; only the diagnostic path sample is partial.
        sample = [row for row in rows if isinstance(row, dict) and row.get('state') == 'CONFLICT'][:3]
        if not sample:
            sample = rows[:3]
        result[rows_key] = {'count': len(rows), 'state_counts': counts,
                            'all_states_counted': True, 'sample': _small(sample),
                            'paths_complete': len(rows) <= 3}
    return result


def _references(value):
    """Attach existing state pins; do not persist or relabel the CLI result."""
    view = value.get('view_path')
    current = value.get('current')
    if not (isinstance(view, str) and isinstance(current, dict)):
        return []
    current_view = value.get('current_view')
    immutable = current_view.get('immutable_path') if isinstance(current_view, dict) else None
    path = Path(immutable if isinstance(immutable, str) else view)
    if (not path.is_absolute() or path.name != 'index.html'
            or any(p.is_symlink() for p in (path, *path.parents))):
        return []
    manifest = path.parent / 'MANIFEST.json'
    try:
        if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 512 * 1024:
            return []
        raw = manifest.read_bytes()
        if hashlib.sha256(raw).hexdigest() != current.get('manifest_sha256'):
            return []
        record = json.loads(raw)
        if record.get('schema') != 'docs-navigator.output/v1' or record.get('release') != current.get('release'):
            return []
        return [{'kind': 'IMMUTABLE_STATE_ARTIFACT', 'path': str(path.parent / name),
                 **record['files'][name], 'qualification': 'STATE_NOT_IDENTICAL_CLI_RESPONSE'}
                for name in ('snapshot.json', 'index.html')]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return []


def _render(raw: str, exit_code: int, argv: list[str]) -> str:
    encoded = raw.encode('utf-8')
    if len(encoded) < MAX_STDOUT_BYTES:
        return raw
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        value = {'status': 'UNPARSEABLE_WORKSPACE_OUTPUT'}
    if not isinstance(value, dict):
        value = {'status': 'NON_OBJECT_WORKSPACE_OUTPUT'}
    result = {
        'schema': 'agent-os.atlas-cli-summary/v1',
        'status': value.get('status', 'RESULT_SUMMARIZED'),
        'upstream_schema': value.get('schema'), 'exit_code': exit_code,
        'output_complete': False,
        'full_result': {'bytes': len(encoded), 'sha256': hashlib.sha256(encoded).hexdigest(),
                        'format': 'UTF-8 workspace stdout', 'storage': 'NOT_PERSISTED_BY_FACADE'},
        'invocation': _small(argv),
        'counts': {key: len(item) for key, item in value.items() if isinstance(item, (list, dict))},
        'references': _references(value),
        'control': _control(value),
    }
    for key in ('project_key', 'current', 'view_path', 'source_sha256', 'as_of', 'next_cursor',
                'product_execution'):
        if key in value:
            result[key] = value[key]
    for key in ('summary', 'coverage', 'capacity', 'refresh', 'packet', 'projects', 'issues',
                'next_actions', 'releases'):
        if key in value:
            result[key + '_sample'] = _small(value[key])
    output = json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n'
    if len(output.encode('utf-8')) >= MAX_STDOUT_BYTES:
        # Keep the outcome and exact digest even for unusually long source text.
        for key in tuple(result):
            if key.endswith('_sample') or key in ('invocation', 'counts', 'references'):
                result.pop(key, None)
        for key in ('project_key', 'current', 'view_path', 'source_sha256', 'as_of', 'next_cursor'):
            if key in result:
                result[key] = _small(result[key])
        output = json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n'
    if len(output.encode('utf-8')) >= MAX_STDOUT_BYTES:
        result = {key: result[key] for key in ('schema', 'status', 'exit_code', 'output_complete', 'full_result', 'control')}
        output = json.dumps(result, separators=(',', ':')) + '\n'
    if len(output.encode('utf-8')) >= MAX_STDOUT_BYTES:
        # A result outside the declared control shapes is explicitly incomplete;
        # never turn an unknown composite outcome into an unqualified NO_CHANGE.
        result['status'] = 'CONTROL_OUTPUT_BOUND_REQUIRES_FULL_LOCAL_READ'
        result['control'] = {'control_complete': False,
                             'root_status': _small(value.get('status')),
                             'projection_status': _small(value.get('projection', {}).get('status'))
                             if isinstance(value.get('projection'), dict) else None}
        output = json.dumps(result, separators=(',', ':')) + '\n'
    return output


def main(argv: list[str] | None = None) -> int:
    selected = list(sys.argv[1:] if argv is None else argv)
    if not selected:
        print(json.dumps({'schema': 'agentos.atlas-help/v1', 'status': 'HELP',
                          'commands': ['list', 'views', 'refresh', 'work', 'checkpoint'],
                          'registry': 'EXPLICIT_FOR_PROJECT_OPERATIONS'}))
        return 0
    if selected and selected[0] == 'source-relocate':
        # Explicit native route. No registry lookup or implicit project choice.
        try:
            with _workspace():
                return importlib.import_module('source_relocation').main(selected[1:])
        except (AtlasModuleError, ImportError, OSError) as exc:
            print(json.dumps({'status': 'REFUSED', 'code': str(exc) if isinstance(exc, AtlasModuleError) else type(exc).__name__}))
            return 1
    if selected and selected[0] == 'profile':
        # Optional local classification; no project registry or user-home read.
        import argparse
        from .workflow import route, KINDS, EFFECTS
        parser = argparse.ArgumentParser(prog='agentos atlas profile', allow_abbrev=False)
        parser.add_argument('--kind', choices=KINDS, required=True)
        parser.add_argument('--effect', choices=EFFECTS, action='append', default=[])
        parser.add_argument('--change', action='append', default=[])
        parser.add_argument('--bounded', action='store_true')
        parser.add_argument('--full', action='store_true')
        parser.add_argument('--context', default='UNKNOWN')
        parser.add_argument('--writer', default='UNKNOWN')
        args = parser.parse_args(selected[1:])
        try:
            with _workspace():
                function = importlib.import_module('work_profile')
                result = function.select_profile(route(args.kind, args.effect),
                    changes=args.change, bounded=args.bounded, context=args.context,
                    writer=args.writer, full=args.full)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 2 if result['status'] in {'BLOCKED', 'UNKNOWN'} else 0
        except (AtlasModuleError, ImportError, OSError, ValueError) as exc:
            print(json.dumps({'status': 'REFUSED', 'code': str(exc)}))
            return 1
    if not any(arg == '--registry' or arg.startswith('--registry=') for arg in selected):
        selected = ['--registry', str(default_registry()), *selected]
    captured = io.StringIO()
    try:
        with _workspace() as workspace, contextlib.redirect_stdout(captured):
            try:
                result = workspace.main(selected)
                code = int(result) if result is not None else 0
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
    except (AtlasModuleError, ImportError, OSError) as exc:
        print(json.dumps({'status': 'REFUSED', 'code': str(exc) if isinstance(exc, AtlasModuleError)
                          else type(exc).__name__}, sort_keys=True))
        return 1
    sys.stdout.write(_render(captured.getvalue(), code, selected))
    return code


def dispatch(argv: list[str]) -> int | None:
    """Handle only Atlas, before foundation/config/update processing."""
    if argv and argv[0] == 'atlas':
        return main(argv[1:])
    index = 0
    while index < len(argv):
        item = argv[index]
        if item in ('--home', '--user-home'):
            index += 2
        elif item.startswith(('--home=', '--user-home=')):
            index += 1
        else:
            break
    if index and index < len(argv) and argv[index] == 'atlas':
        print(json.dumps({'status': 'REFUSED', 'code': 'ATLAS_USE_EXPLICIT_REGISTRY'}))
        return 1
    return None


if __name__ == '__main__':
    raise SystemExit(main())
