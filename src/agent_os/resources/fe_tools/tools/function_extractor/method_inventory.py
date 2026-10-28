"""Pure bounded lexical method inventory; never import or execute source bytes."""
from __future__ import annotations

import ast
import hashlib
import json
import math
import re

from .contract_engine import validate_contract_map

ENGINE = {'name': 'function-extractor.method-inventory', 'version': 1}
_LIMITS = {'max_files': 160, 'max_file_bytes': 2_000_000, 'max_source_bytes': 16_000_000,
           'max_policy_rules': 256, 'max_methods': 128, 'max_callsites': 2000, 'max_ast_nodes': 200_000}
_SHA = re.compile(r'[a-f0-9]{64}\Z')
_ID = re.compile(r'[A-Za-z_][A-Za-z0-9_.:-]{0,179}\Z')
_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\Z')
_SECRET = re.compile(r'(?:\.env(?:\..*)?|(?:credentials?|secrets?|sessions?|backups?)(?:[._-].*)?|id_rsa(?:\..*)?|id_ed25519(?:\..*)?|auth\.json)', re.I)


class _Refuse(ValueError):
    pass


def _require(condition, category):
    if not condition:
        raise _Refuse(category)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _json(value):
    remaining = [100000]
    def visit(v, depth=0):
        remaining[0] -= 1
        _require(remaining[0] >= 0 and depth <= 32, 'RESOURCE_BOUND')
        if v is None or type(v) in (str, bool, int): return
        if type(v) is float and math.isfinite(v): return
        if type(v) is list:
            for child in v: visit(child, depth + 1)
            return
        if type(v) is dict and all(type(k) is str and len(k) <= 256 for k in v):
            for child in v.values(): visit(child, depth + 1)
            return
        raise _Refuse('JSON_INPUT_INVALID')
    visit(value)
    data = _canonical(value)
    _require(len(data) <= 2_000_000, 'RESOURCE_BOUND')
    return json.loads(data)


def _ident(value, dotted=False):
    return type(value) is str and bool((_NAME if dotted else _ID).fullmatch(value))


def _path(value, *, prefix=False):
    _require(type(value) is str and 0 < len(value) <= 512, 'PATH_INVALID')
    if prefix: value = value[:-1] if value.endswith('/') else value
    parts = value.split('/')
    _require(all(parts) and all(p not in {'.', '..'} and not _SECRET.fullmatch(p)
        and re.fullmatch(r'[A-Za-z0-9_.-]+', p) for p in parts), 'PATH_INVALID')
    _require(prefix or value.endswith('.py'), 'PATH_INVALID')
    return value


def _budget(value):
    value = {} if value is None else _json(value)
    _require(type(value) is dict and not set(value) - set(_LIMITS), 'BUDGET_INVALID')
    for key, limit in _LIMITS.items():
        _require(type(value.get(key, limit)) is int and 1 <= value.get(key, limit) <= limit, 'BUDGET_INVALID')
    return {key: value.get(key, limit) for key, limit in _LIMITS.items()}


def _manifest(manifest, sources, limits):
    manifest = _json(manifest)
    required = {'schema', 'entry', 'adapter', 'files', 'graph_sha256', 'coverage', 'live_send_supported'}
    _require(type(manifest) is dict and required <= set(manifest)
        and not set(manifest) - required - {'capture_mode', 'opaque_modules', 'source_pin'}
        and manifest['schema'] == 'route-probe.bundle/v1'
        and type(manifest['graph_sha256']) is str and _SHA.fullmatch(manifest['graph_sha256'])
        and manifest['live_send_supported'] is False, 'MANIFEST_INVALID')
    _require(type(sources) is dict and len(sources) <= limits['max_files'] and type(manifest['files']) is list
        and 1 <= len(manifest['files']) <= limits['max_files'], 'MANIFEST_INVALID')
    pins = []; seen = set(); total = 0
    for row in manifest['files']:
        _require(type(row) is dict and set(row) == {'path', 'sha256', 'bytes'}, 'MANIFEST_INVALID')
        path = _path(row['path'])
        _require(path not in seen and type(row['sha256']) is str and _SHA.fullmatch(row['sha256'])
            and type(row['bytes']) is int and 0 <= row['bytes'] <= limits['max_file_bytes'], 'MANIFEST_INVALID')
        _require(path in sources and type(sources[path]) is bytes, 'SOURCE_SET_OR_TYPE')
        raw = sources[path]; total += len(raw)
        _require(total <= limits['max_source_bytes'], 'RESOURCE_BOUND')
        _require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'SOURCE_PIN_MISMATCH')
        seen.add(path); pins.append(dict(row))
    _require(set(sources) == seen, 'SOURCE_SET_OR_TYPE')
    return manifest, sorted(pins, key=lambda p: p['path'])


def _policy(policy, limits):
    policy = _json(policy)
    _require(type(policy) is dict and set(policy) == {'schema', 'version', 'include_prefixes', 'dispatches', 'declarations'}
        and policy['schema'] == 'function-extractor.method-policy/v1'
        and type(policy['version']) is int and policy['version'] == 1, 'POLICY_INVALID')
    _require(type(policy['include_prefixes']) is list and 1 <= len(policy['include_prefixes']) <= 160
        and type(policy['dispatches']) is list and type(policy['declarations']) is list
        and len(policy['dispatches']) + len(policy['declarations']) <= limits['max_policy_rules'], 'POLICY_INVALID')
    prefixes = [_path(v, prefix=True) for v in policy['include_prefixes']]
    _require(len(set(prefixes)) == len(prefixes), 'POLICY_INVALID')
    ids = set()
    for kind in ('dispatches', 'declarations'):
        for row in policy[kind]:
            expected = {'id', 'provider', 'protocol', 'paths'} | ({'callee', 'method_arg', 'method_kw', 'fixed_method'} if kind == 'dispatches' else {'symbol'})
            _require(type(row) is dict and set(row) == expected and _ident(row['id']) and all(_ident(row[k], True) for k in ('provider', 'protocol'))
                and row['id'] not in ids and type(row['paths']) is list and 1 <= len(row['paths']) <= 160, 'POLICY_INVALID')
            ids.add(row['id']); paths = [_path(v) for v in row['paths']]
            _require(len(set(paths)) == len(paths), 'POLICY_INVALID')
            if kind == 'declarations':
                _require(_ident(row['symbol'], True), 'POLICY_INVALID')
                continue
            arg, kw, fixed = row['method_arg'], row['method_kw'], row['fixed_method']
            _require(_ident(row['callee'], True) and (arg is None or type(arg) is int and 0 <= arg <= 64)
                and (kw is None or _ident(kw, True) and '.' not in kw)
                and (fixed is None or _ident(fixed, True))
                and ((fixed is not None and arg is None and kw is None) or (fixed is None and (arg is not None or kw is not None))), 'POLICY_INVALID')
    return policy, prefixes


def _catalog(catalog, limits):
    catalog = _json(catalog)
    _require(type(catalog) is dict and set(catalog) == {'schema', 'version', 'sources', 'methods'}
        and catalog['schema'] == 'function-extractor.method-catalog/v1' and type(catalog['version']) is int
        and catalog['version'] == 1 and type(catalog['sources']) is list and len(catalog['sources']) <= 128
        and type(catalog['methods']) is list and len(catalog['methods']) <= limits['max_methods'], 'CATALOG_INVALID')
    ids = set()
    for row in catalog['sources']:
        _require(type(row) is dict and set(row) == {'id', 'primary_ref', 'version', 'retrieved_at', 'representation_sha256', 'representation_kind', 'trust'}
            and _ident(row['id']) and row['id'] not in ids
            and type(row['representation_sha256']) is str and _SHA.fullmatch(row['representation_sha256'])
            and all(type(row[k]) is str and 0 < len(row[k]) <= 2048 for k in ('primary_ref', 'version', 'retrieved_at', 'representation_kind', 'trust')), 'CATALOG_INVALID')
        ids.add(row['id'])
    keys = set()
    for row in catalog['methods']:
        expected = {'provider', 'protocol', 'method', 'source_ids', 'contract_source_ids', 'boundary_ids', 'scope', 'status', 'gaps'}
        _require(type(row) is dict and set(row) == expected and all(_ident(row[k], True) for k in ('provider', 'protocol', 'method'))
            and row['status'] in {'PARTIAL', 'CONTRACT_GAP', 'PROFILE_PRESENT'}
            and type(row['scope']) is str and 0 < len(row['scope']) <= 2048, 'CATALOG_INVALID')
        key = (row['provider'], row['protocol'], row['method'])
        _require(key not in keys, 'CATALOG_INVALID'); keys.add(key)
        for field in ('source_ids', 'contract_source_ids', 'boundary_ids', 'gaps'):
            values = row[field]
            _require(type(values) is list and len(values) <= 128 and len(set(values)) == len(values)
                and all((type(v) is str and 0 < len(v) <= 2048) if field == 'gaps' else _ident(v) for v in values), 'CATALOG_INVALID')
        _require(all(v in ids for v in row['source_ids']), 'CATALOG_SOURCE_MISSING')
    return catalog


def _name(node):
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute):
        base = _name(node.value)
        return base + '.' + node.attr if base else None
    return None


def _selector(node, rule):
    if rule['fixed_method'] is not None: return rule['fixed_method'], None
    arg, kw = rule['method_arg'], rule['method_kw']
    if any(k.arg is None for k in node.keywords): return None, 'KEYWORD_EXPANSION_UNRESOLVED'
    if arg is not None and any(isinstance(n, ast.Starred) for n in node.args[:arg + 1]): return None, 'POSITIONAL_EXPANSION_UNRESOLVED'
    pos = node.args[arg] if arg is not None and len(node.args) > arg else None
    keys = [k.value for k in node.keywords if kw is not None and k.arg == kw]
    if len(keys) > 1 or pos is not None and keys: return None, 'METHOD_SELECTOR_AMBIGUOUS'
    selected = pos if pos is not None else keys[0] if keys else None
    if selected is None: return None, 'METHOD_SELECTOR_ABSENT'
    if not isinstance(selected, ast.Constant) or type(selected.value) is not str: return None, 'DYNAMIC_METHOD_SELECTOR'
    if not _ident(selected.value, True): return None, 'METHOD_IDENTIFIER_UNSAFE'
    return selected.value, None


def _literal_methods(node):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'frozenset' and len(node.args) == 1 and not node.keywords:
        node = node.args[0]
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)): return None
    if any(not isinstance(n, ast.Constant) or not _ident(n.value, True) for n in node.elts): return None
    return sorted({n.value for n in node.elts})


def _join(key, catalog, contract_map):
    row = next((r for r in catalog['methods'] if (r['provider'], r['protocol'], r['method']) == key), None)
    if row is None:
        return {'catalog_status': 'CONTRACT_GAP', 'contract_status': 'CONTRACT_GAP', 'source_ids': [], 'contract_source_ids': [],
                'boundary_ids': [], 'scope': None, 'scope_sha256': None, 'gap_text_digest': None,
                'rule_refs': [], 'gaps': ['CATALOG_METHOD_MISSING']}
    gaps = ['CATALOG_DECLARED_GAPS'] if row['gaps'] else []; refs = []
    if not row['contract_source_ids']: gaps.append('CONTRACT_SOURCE_MAPPING_MISSING')
    if not row['boundary_ids']: gaps.append('METHOD_BOUNDARY_MAPPING_MISSING')
    if contract_map is None: gaps.append('CONTRACT_MAP_MISSING')
    else:
        sources = {r['source_id']: r for r in contract_map['sources']}
        boundaries = {r['boundary_id'] for r in contract_map['boundaries']}
        for sid in row['contract_source_ids']:
            if sid not in sources: gaps.append('CONTRACT_SOURCE_MISSING')
        for bid in row['boundary_ids']:
            if bid not in boundaries: gaps.append('CONTRACT_BOUNDARY_MISSING')
            selected = [r for r in contract_map['rules'] if r['boundary_id'] == bid and r['source_id'] in row['contract_source_ids']]
            if not selected: gaps.append('CONTRACT_RULE_MISSING')
            for rule in selected:
                _require(all(_ident(rule[k]) for k in ('rule_id', 'source_id', 'boundary_id')), 'CONTRACT_IDENTIFIER_INVALID')
                refs.append({k: rule[k] for k in ('rule_id', 'source_id', 'boundary_id', 'provenance')})
                if rule['provenance'] == 'UNSPECIFIED': gaps.append('CONTRACT_AUTHORITY_UNSPECIFIED')
                if rule['conflicts']: gaps.append('CONTRACT_RULE_CONFLICT')
    missing = any(g.startswith(('CONTRACT_', 'METHOD_BOUNDARY_')) for g in gaps)
    status = 'CONTRACT_GAP' if missing or row['status'] == 'CONTRACT_GAP' else 'PARTIAL' if row['status'] != 'PROFILE_PRESENT' or bool(row['gaps']) or contract_map['status'] == 'PARTIAL' or any(r['provenance'] == 'OBSERVED' for r in refs) else 'PROFILE_PRESENT'
    return {'catalog_status': row['status'], 'contract_status': status, 'source_ids': row['source_ids'],
            'contract_source_ids': row['contract_source_ids'], 'boundary_ids': row['boundary_ids'],
            'scope': 'CATALOG_SCOPE_RECORDED_BY_DIGEST', 'scope_sha256': _digest(row['scope']),
            'gap_text_digest': _digest(row['gaps']),
            'rule_refs': sorted(refs, key=lambda r: r['rule_id']), 'gaps': sorted(set(gaps))}


def inventory_methods(manifest, sources, policy, catalog, contract_map=None, budget=None):
    """Inventory only exact supplied source bytes; all evidence is STATIC_POSSIBLE."""
    try:
        limits = _budget(budget); manifest, pins = _manifest(manifest, sources, limits)
        policy, prefixes = _policy(policy, limits); catalog = _catalog(catalog, limits)
        if contract_map is not None:
            contract_map = _json(contract_map)
            _require(validate_contract_map(contract_map)['status'] == 'VALID' and contract_map['status'] != 'REFUSED', 'CONTRACT_MAP_INVALID')
            route = contract_map['route']
            _require(route['entry'] == manifest['entry'] and route['graph_sha256'] == manifest['graph_sha256']
                and sorted(route['source_pins'], key=lambda r: r['path']) == [{'path': p['path'], 'sha256': p['sha256']} for p in pins],
                'MAP_SOURCE_BINDING')
        by_path = {p['path']: p for p in pins}; calls = []; caps = []; unresolved = []; parsed = []; excluded = []; nodes = 0
        for pin in pins:
            path = pin['path']
            if not any(path == p or path.startswith(p + '/') for p in prefixes):
                excluded.append(path); continue
            dispatches = [r for r in policy['dispatches'] if path in r['paths']]
            declarations = [r for r in policy['declarations'] if path in r['paths']]
            if not dispatches and not declarations:
                excluded.append(path); continue
            try: tree = ast.parse(sources[path], filename='<selected-source>')
            except (SyntaxError, ValueError): raise _Refuse('SOURCE_PARSE_FAILED')
            pending = [tree]
            while pending:
                node = pending.pop(); nodes += 1
                _require(nodes <= limits['max_ast_nodes'], 'RESOURCE_BOUND')
                pending.extend(ast.iter_child_nodes(node))
            parsed.append(path)
            assignments = {}
            class Visitor(ast.NodeVisitor):
                scope = []
                def visit_ClassDef(self, n):
                    self.scope.append(n.name); self.generic_visit(n); self.scope.pop()
                def visit_FunctionDef(self, n):
                    self.scope.append(n.name)
                    self.generic_visit(n)
                    self.scope.pop()
                visit_AsyncFunctionDef = visit_FunctionDef
                def visit_Call(self, n):
                    name = _name(n.func); matches = [r for r in dispatches if r['callee'] == name]
                    if matches:
                        _require(len(calls) < limits['max_callsites'], 'RESOURCE_BOUND')
                        rule = matches[0]; method, reason = _selector(n, rule) if len(matches) == 1 else (None, 'DISPATCH_POLICY_AMBIGUOUS')
                        symbol = '.'.join(self.scope) or '<module>'
                        if symbol != '<module>' and not _ident(symbol, True): symbol, method, reason = None, None, 'ENCLOSING_SYMBOL_UNSUPPORTED'
                        row = {'id': 'call-' + _digest([path, pin['sha256'], n.lineno, n.col_offset, name, [[r['id'], r['provider'], r['protocol']] for r in matches]])[:24],
                            'file': path, 'line': n.lineno, 'symbol': symbol, 'source_sha256': pin['sha256'],
                            'callee': name, 'policy_ids': sorted(r['id'] for r in matches),
                            'provider': rule['provider'] if len(matches) == 1 else None,
                            'protocol': rule['protocol'] if len(matches) == 1 else None, 'method': method,
                            'status': 'UNRESOLVED' if reason else 'STATIC_POSSIBLE', 'reason': reason}
                        calls.append(row)
                        if reason: unresolved.append({'kind': 'CALLSITE', 'callsite_id': row['id'], 'file': path, 'line': n.lineno, 'reason': reason})
                    self.generic_visit(n)
                def _assignment(self, target, value, line):
                    name = _name(target)
                    if name:
                        symbol = '.'.join(self.scope + [name])
                        assignments.setdefault(symbol, []).append((value, line))
                def visit_Assign(self, n):
                    for target in n.targets: self._assignment(target, n.value, n.lineno)
                    self.generic_visit(n)
                def visit_AnnAssign(self, n):
                    self._assignment(n.target, n.value, n.lineno); self.generic_visit(n)
                def visit_AugAssign(self, n):
                    self._assignment(n.target, None, n.lineno); self.generic_visit(n)
            Visitor().visit(tree)
            for rule in declarations:
                rows = assignments.get(rule['symbol'], [])
                methods = _literal_methods(rows[0][0]) if len(rows) == 1 else None
                if methods is None:
                    unresolved.append({'kind': 'DECLARATION', 'policy_id': rule['id'], 'file': path,
                        'line': rows[0][1] if rows else None, 'reason': 'DECLARATION_ABSENT_OR_DYNAMIC_OR_REASSIGNED'})
                else:
                    _require(len(methods) <= limits['max_methods'], 'RESOURCE_BOUND')
                    caps.append({'policy_id': rule['id'], 'provider': rule['provider'], 'protocol': rule['protocol'],
                        'file': path, 'line': rows[0][1], 'symbol': rule['symbol'], 'source_sha256': pin['sha256'],
                        'methods': methods, 'status': 'STATIC_POSSIBLE_NOT_DISPATCH'})
        for rule in policy['dispatches'] + policy['declarations']:
            for path in rule['paths']:
                if path not in by_path: unresolved.append({'kind': 'POLICY_PATH', 'policy_id': rule['id'], 'file': path, 'line': None, 'reason': 'SOURCE_NOT_IN_SELECTED_MANIFEST'})
                elif path in excluded: unresolved.append({'kind': 'POLICY_PATH', 'policy_id': rule['id'], 'file': path, 'line': None, 'reason': 'SOURCE_EXCLUDED_BY_POLICY'})
        groups = {}
        for row in calls:
            if row['method'] is not None: groups.setdefault((row['provider'], row['protocol'], row['method']), []).append(row['id'])
        _require(len(groups) <= limits['max_methods'], 'RESOURCE_BOUND')
        methods = []; proposals = []
        for key, call_ids in sorted(groups.items()):
            coverage = _join(key, catalog, contract_map)
            methods.append({'provider': key[0], 'protocol': key[1], 'method': key[2], 'callsite_ids': sorted(call_ids),
                **coverage, 'wire_proof': 'UNKNOWN', 'runtime_adoption': 'UNKNOWN', 'evidence': 'STATIC_POSSIBLE'})
            if coverage['catalog_status'] == 'CONTRACT_GAP' and 'CATALOG_METHOD_MISSING' in coverage['gaps']:
                proposals.append({'status': 'PROPOSED', 'provider': key[0], 'protocol': key[1], 'method': key[2],
                    'source_ids': [], 'contract_source_ids': [], 'boundary_ids': [], 'scope': 'UNSPECIFIED',
                    'expected': None, 'reason': 'NEW_STATIC_METHOD_NEEDS_EXPLICIT_PROFILE'})
        output = {'schema': 'function-extractor.method-inventory/v1', 'version': 1,
            'status': 'PARTIAL' if not parsed or unresolved or any(r['contract_status'] != 'PROFILE_PRESENT' for r in methods) or manifest.get('capture_mode') == 'PARTIAL_STATIC' else 'INVENTORIED',
            'engine': dict(ENGINE), 'input_digests': {'manifest': _digest(manifest), 'source_pins': _digest(pins),
                'policy': _digest(policy), 'catalog': _digest(catalog),
                'contract_map': contract_map['content_digest'] if contract_map is not None else None,
                'budget': _digest(limits), 'engine_identity': _digest(ENGINE)}, 'source_pins': pins,
            'callsites': sorted(calls, key=lambda r: (r['file'], r['line'], r['id'])), 'methods': methods,
            'capabilities': sorted(caps, key=lambda r: (r['file'], r['line'], r['policy_id'])),
            'unresolved': sorted(unresolved, key=lambda r: (r['file'], r['line'] or 0, r.get('policy_id', r.get('callsite_id', '')))),
            'proposals': proposals, 'coverage': {'selected_files': len(pins), 'selected_policy_file_count': len(parsed), 'parsed_files': parsed, 'excluded_files': excluded,
                'matched_callsites': len(calls), 'resolved_callsites': sum(r['status'] == 'STATIC_POSSIBLE' for r in calls),
                'unresolved_callsites': sum(r['status'] == 'UNRESOLVED' for r in calls), 'requested_method_count': len(methods),
                'declared_capability_groups': len(caps), 'ast_nodes': nodes,
                'whole_program_denominator': None, 'whole_program_status': 'UNKNOWN'},
            'scope': 'SELECTED_FROZEN_SOURCE_ONLY_NO_EXECUTION_OR_WIRE_PROOF',
            'production_effects': 0, 'live_provider_observed': False, 'runtime_acceptance': False}
        output['content_digest'] = _digest(output)
        _require(len(_canonical(output)) <= 4_000_000, 'RESOURCE_BOUND')
        return output
    except _Refuse as exc:
        return {'schema': 'function-extractor.method-inventory/v1', 'version': 1, 'status': 'REFUSED', 'errors': [str(exc)],
                'production_effects': 0, 'live_provider_observed': False, 'runtime_acceptance': False}
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError, MemoryError, OverflowError):
        return {'schema': 'function-extractor.method-inventory/v1', 'version': 1, 'status': 'REFUSED', 'errors': ['INVENTORY_INPUT_INVALID'],
                'production_effects': 0, 'live_provider_observed': False, 'runtime_acceptance': False}
