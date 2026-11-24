"""Bounded static provenance for response-derived header prefixes.

No source execution or credential values. Only standard HTTP response reads,
JSON decoding and SimpleCookie parsing can establish a runtime origin.
All definitions, assignments and return branches must agree; unknown fails.
"""
import ast
import re


class RuntimeHTTPSource:
    def __init__(self, tree):
        self.nodes = list(ast.walk(tree))
        self.ok = len(self.nodes) <= 100_000 and not any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id in {"exec", "eval", "setattr", "delattr", "__import__", "globals", "vars"} for n in self.nodes)
        self.parents = {c: n for n in self.nodes for c in ast.iter_child_nodes(n)}
        if any(isinstance(n, ast.Attribute) and n.attr == "modules" for n in self.nodes):
            self.ok = False
        for n in self.nodes:
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "locals":
                parent = self.parents.get(n)
                if not isinstance(parent, ast.Attribute) or parent.attr != "get":
                    self.ok = False
        self.scopes = {tree: {"parent": None, "defs": {}, "values": {}}}
        self.at = {}
        self.imports = {}
        self.classes = {}
        self.writes = set()
        stack = [(tree, tree)]
        while stack:
            n, scope = stack.pop()
            self.at[n] = scope
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.scopes[scope]["defs"].setdefault(n.name, []).append(n)
                if isinstance(n, ast.ClassDef):
                    self.classes.setdefault(n.name, []).append(n)
                self.scopes[n] = {"parent": scope, "defs": {}, "values": {}}
                scope = n
                self.at[n] = scope
            if isinstance(n, ast.Import):
                for a in n.names:
                    self.imports.setdefault(a.asname or a.name, []).append(a.name)
            if isinstance(n, ast.ImportFrom):
                for a in n.names:
                    self.imports.setdefault(a.asname or a.name, []).append((n.module or "") + "." + a.name)
            if isinstance(n, (ast.Assign, ast.AnnAssign, ast.NamedExpr, ast.AugAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for t in targets:
                    if isinstance(t, ast.Name):
                        self.scopes[scope]["values"].setdefault(t.id, []).append((n.value, None))
                    elif isinstance(t, (ast.Tuple, ast.List)):
                        for i, item in enumerate(t.elts):
                            if isinstance(item, ast.Name):
                                self.scopes[scope]["values"].setdefault(item.id, []).append((n.value, i))
                    else:
                        self.writes.add(ast.unparse(t))
            if isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension, ast.Delete)):
                targets = n.targets if isinstance(n, ast.Delete) else [n.target]
                for target in targets:
                    for item in ast.walk(target):
                        if isinstance(item, ast.Name):
                            self.scopes[scope]["values"].setdefault(item.id, []).append((None, None))
            if isinstance(n, (ast.With, ast.AsyncWith)):
                for item in n.items:
                    if isinstance(item.optional_vars, ast.Name):
                        self.scopes[scope]["values"].setdefault(item.optional_vars.id, []).append((item.context_expr, None))
            stack.extend((c, scope) for c in ast.iter_child_nodes(n))

        # Track object aliases and local-argument aliases before certifying a
        # response-derived value. Mutating an alias invalidates its whole origin.
        self.aliases = {}
        def root_name(n):
            while isinstance(n, (ast.Attribute, ast.Subscript)):
                n = n.value
            return n if isinstance(n, ast.Name) else None
        def slot(n, scope):
            owner = self.binding(n.id, scope)[1]
            return (owner or scope, n.id)
        def find(v):
            while self.aliases.get(v, v) != v:
                v = self.aliases[v]
            return v
        def join(a, b):
            a, b = find(a), find(b)
            if a != b:
                self.aliases[a] = b
        for n in self.nodes:
            scope = self.at[n]
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Name):
                for target in n.targets:
                    if isinstance(target, ast.Name):
                        join(slot(target, scope), slot(n.value, scope))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                defs, _ = self.binding(n.func.id, scope, "defs")
                if len(defs) == 1:
                    fn = defs[0]
                    args = [*fn.args.posonlyargs, *fn.args.args]
                    supplied = {a.arg: v for a, v in zip(args, n.args)}
                    supplied.update({x.arg: x.value for x in n.keywords if x.arg})
                    for name, value in supplied.items():
                        root = root_name(value)
                        if root is not None:
                            join((fn, name), slot(root, scope))
        self.mutated = set()
        for n in self.nodes:
            scope = self.at[n]
            targets = []
            if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                targets = [x for x in targets if isinstance(x, (ast.Attribute, ast.Subscript))]
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in {"update", "clear", "pop", "setdefault", "append", "extend", "insert", "remove", "__setitem__"}:
                targets.append(n.func.value)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in {"setitem", "delitem"} and n.args:
                targets.append(n.args[0])
            for target in targets:
                root = root_name(target)
                if root is not None:
                    self.mutated.add(find(slot(root, scope)))
        self.alias_root = find

    def binding(self, name, scope, kind="values"):
        while scope is not None:
            found = self.scopes[scope][kind].get(name)
            if found is not None:
                return found, scope
            # Parameters are binding boundaries, not implicit external data.
            if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                args = [*scope.args.posonlyargs, *scope.args.args, *scope.args.kwonlyargs]
                if any(a.arg == name for a in args):
                    return [], scope
            scope = self.scopes[scope]["parent"]
        return [], None

    def imported(self, n, exact, scope):
        if isinstance(n, ast.Name):
            return self.imports.get(n.id) == [exact] and self.binding(n.id, scope)[1] is None and not self.binding(n.id, scope, "defs")[0] and n.id not in self.classes
        if isinstance(n, ast.Attribute):
            if any(p.endswith("." + n.attr) for p in self.writes):
                return False
            return exact.endswith("." + n.attr) and self.imported(n.value, exact[:-(len(n.attr) + 1)], scope) and ast.unparse(n) not in self.writes
        return False

    def http_constructor(self, n, scope):
        if self.imported(n, "http.client.HTTPConnection", scope) or self.imported(n, "http.client.HTTPSConnection", scope):
            return True
        if not isinstance(n, ast.Name) or self.binding(n.id, scope)[0]:
            return False
        classes = self.classes.get(n.id, [])
        if len(classes) != 1:
            return False
        cls = classes[0]
        allowed_calls = {"super", "super().__init__", "socket.socket", "self.sock.settimeout", "self.sock.connect", "os.fspath", "os.path.relpath", "os.fsencode", "min", "len"}
        for item in ast.walk(cls):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and item.decorator_list:
                return False
            if isinstance(item, ast.Call):
                path = ast.unparse(item.func)
                if path not in allowed_calls:
                    return False
                if path.startswith("socket.") and not self.imported(item.func, "socket.socket", self.at[item]):
                    return False
                if path.startswith("os.") and not self.imported(item.func, path, self.at[item]):
                    return False
                if path in {"super", "min", "len"} and (self.binding(path, self.at[item])[1] is not None or self.binding(path, self.at[item], "defs")[0]):
                    return False
            if isinstance(item, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                for target in targets:
                    if isinstance(target, ast.Attribute):
                        path = ast.unparse(target)
                        if path not in {"self.socket_path", "self.sock"}:
                            return False
                        if path == "self.sock" and not (isinstance(item.value, ast.Call) and self.imported(item.value.func, "socket.socket", self.at[item])):
                            return False
        return (len(cls.bases) == 1 and self.imported(cls.bases[0], "http.client.HTTPConnection", self.at[cls])
                and all(not isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) or x.name in {"__init__", "connect"} for x in cls.body)
                and all(not isinstance(x, (ast.Assign, ast.AnnAssign, ast.AugAssign)) for x in cls.body)
                and not any(p.endswith(".getresponse") or p.endswith(".getheaders") or p.endswith(".read") for p in self.writes))

    def kind(self, n, scope=None, env=None, position=None, seen=frozenset(), budget=None):
        if budget is None:
            budget = [4096]
        budget[0] -= 1
        if budget[0] < 0 or len(seen) > 64 or n is None or not self.ok:
            return None
        scope = scope or self.at.get(n)
        env = env or {}
        mark = (id(n), id(scope), position)
        if mark in seen:
            return None
        seen = seen | {mark}
        def k(value, pos=None, sc=scope, en=env):
            return self.kind(value, sc, en, pos, seen, budget)
        if ast.unparse(n) in self.writes:
            return None
        if isinstance(n, ast.Constant):
            return "null" if n.value is None else None
        if isinstance(n, ast.Name):
            vals, owner = self.binding(n.id, scope)
            if self.alias_root((owner or scope, n.id)) in self.mutated:
                return None
            if (owner, n.id) in env:
                if vals:
                    return None
                value, caller, outer = env[(owner, n.id)]
                return self.kind(value, caller, outer, position, seen, budget)
            if not vals:
                return None
            origins = []
            for value, pos in vals:
                transform = (isinstance(value, ast.Call) and len(value.args) == 1 and not value.keywords
                             and isinstance(value.args[0], ast.Name) and value.args[0].id == n.id
                             and (self.imported(value.func, "gzip.decompress", owner) or self.imported(value.func, "json.loads", owner)))
                if not transform:
                    origins.append((value, pos))
            if not origins:
                return None
            kinds = [self.kind(v, owner, env, pos if position is None else position, seen, budget) for v, pos in origins]
            active = set(kinds) - {"null"}
            return active.pop() if None not in active and len(active) == 1 else None
        if isinstance(n, (ast.Tuple, ast.List)):
            return k(n.elts[position]) if position is not None and 0 <= position < len(n.elts) else None
        if isinstance(n, ast.IfExp):
            a, b = k(n.body, position), k(n.orelse, position)
            return b if a == "null" else a if b == "null" or a == b else None
        if isinstance(n, ast.Subscript):
            if isinstance(n.slice, ast.Slice):
                sl = n.slice
                if position is None or sl.step is not None or sl.lower is not None:
                    return None
                if sl.upper is not None and not (isinstance(sl.upper, ast.Constant) and type(sl.upper.value) is int and position < sl.upper.value):
                    return None
                return k(n.value, position)
            if not isinstance(n.slice, ast.Constant) or not isinstance(n.slice.value, (str, int)):
                return None
            base = k(n.value)
            return "morsel" if base == "cookie" else "runtime" if base == "runtime" else None
        if isinstance(n, ast.Attribute):
            base = k(n.value)
            return "runtime" if (base == "response" and n.attr == "status") or (base == "morsel" and n.attr == "value") else None
        if isinstance(n, ast.Call):
            if self.http_constructor(n.func, scope):
                return "connection"
            if isinstance(n.func, ast.Attribute):
                receiver = k(n.func.value)
                if receiver == "connection" and n.func.attr == "getresponse" and not n.args and not n.keywords:
                    return "response"
                if receiver == "response" and n.func.attr in {"read", "getheaders"}:
                    return "runtime"
            if self.imported(n.func, "json.loads", scope) or self.imported(n.func, "gzip.decompress", scope):
                return "runtime" if len(n.args) == 1 and not n.keywords and k(n.args[0]) == "runtime" else None
            if self.imported(n.func, "http.cookies.SimpleCookie", scope) and not n.args and not n.keywords:
                return self.cookie_kind(n, scope, env, seen, budget)
            if isinstance(n.func, ast.Name) and n.func.id == "dict" and not self.binding("dict", scope)[0] and not self.binding("dict", scope, "defs")[0] and len(n.args) == 1:
                g = n.args[0]
                if isinstance(g, ast.GeneratorExp) and len(g.generators) == 1:
                    it = g.generators[0]
                    # Exact header-pair normalization; no constants can enter values.
                    if isinstance(it.target, ast.Tuple) and len(it.target.elts) == 2 and all(isinstance(x, ast.Name) for x in it.target.elts) and isinstance(g.elt, ast.Tuple) and len(g.elt.elts) == 2:
                        a, b = it.target.elts
                        key, value = g.elt.elts
                        if isinstance(key, ast.Call) and not key.args and not key.keywords and isinstance(key.func, ast.Attribute) and key.func.attr == "lower" and isinstance(key.func.value, ast.Name) and key.func.value.id == a.id and isinstance(value, ast.Name) and value.id == b.id and not it.ifs and not it.is_async and k(it.iter) == "runtime":
                            return "runtime"
            if isinstance(n.func, ast.Name):
                defs, owner = self.binding(n.func.id, scope, "defs")
                if len(defs) != 1 or self.binding(n.func.id, scope)[0]:
                    return None
                fn = defs[0]
                args = [*fn.args.posonlyargs, *fn.args.args]
                if fn.decorator_list or fn.args.kwonlyargs or fn.args.vararg or fn.args.kwarg or len(n.args) > len(args) or any(x.arg is None for x in n.keywords):
                    return None
                supplied = {a.arg: v for a, v in zip(args, n.args)}
                for kw in n.keywords:
                    if kw.arg in supplied:
                        return None
                    supplied[kw.arg] = kw.value
                defaults = {a.arg: d for a, d in zip(args[-len(fn.args.defaults):], fn.args.defaults)} if fn.args.defaults else {}
                inner = dict(env)
                for arg in args:
                    if arg.arg in supplied:
                        inner[(fn, arg.arg)] = (supplied[arg.arg], scope, env)
                    elif arg.arg in defaults:
                        inner[(fn, arg.arg)] = (defaults[arg.arg], owner, env)
                    else:
                        return None
                outputs = [x.value for x in ast.walk(fn) if isinstance(x, (ast.Return, ast.Yield, ast.YieldFrom)) and self.at.get(x) is fn]
                if not outputs:
                    return None
                kinds = {self.kind(x, fn, inner, position, seen, budget) for x in outputs}
                kinds.discard("null")
                return kinds.pop() if None not in kinds and len(kinds) == 1 else None
        return None

    def cookie_kind(self, call, scope, env, seen, budget):
        parent = self.parents.get(call)
        if not isinstance(parent, ast.Assign) or len(parent.targets) != 1 or not isinstance(parent.targets[0], ast.Name):
            return None
        name = parent.targets[0].id
        values, _ = self.binding(name, scope)
        if len(values) != 1:
            return None
        loads = []
        for node in self.nodes:
            if not isinstance(node, ast.Name) or node.id != name or self.binding(name, self.at.get(node))[1] is not scope or isinstance(node.ctx, ast.Store):
                continue
            p = self.parents.get(node)
            if isinstance(p, ast.Attribute) and p.attr == "load":
                c = self.parents.get(p)
                if not isinstance(c, ast.Call) or c.func is not p or len(c.args) != 1 or c.keywords:
                    return None
                loads.append(c)
            elif not (isinstance(p, ast.Subscript) and p.value is node and isinstance(p.ctx, ast.Load)):
                return None
        if len(loads) != 1 or self.kind(loads[0].args[0], scope, env, None, seen, budget) != "runtime":
            return None
        return "cookie"


def _runtime_prefix_nodes(tree):
    proof = RuntimeHTTPSource(tree)
    safe = set()
    for n in proof.nodes:
        if not isinstance(n, ast.Dict):
            continue
        for key, value in zip(n.keys, n.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value.casefold() in {"authorization", "cookie"} and isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add) and isinstance(value.left, ast.Constant) and isinstance(value.left.value, str)):
                continue
            prefix = value.left.value
            if ((key.value.casefold() == "authorization" and prefix == "Bearer ") or (key.value.casefold() == "cookie" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*=", prefix))) and proof.kind(value.right) == "runtime":
                safe.add(value.left)
    return safe


def runtime_prefix_nodes(tree):
    try:
        return _runtime_prefix_nodes(tree)
    except (RecursionError, ValueError, TypeError):
        return set()
