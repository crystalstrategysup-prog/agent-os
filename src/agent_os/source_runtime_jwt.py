"""Bounded static JWT-source grammar; no imports, execution or secret values.

This identifies call AST nodes, not credentials or runtime package identity.
The caller still scans original bytes and only masks its public prefix span.
"""
from __future__ import annotations

import ast
from collections import defaultdict

MAX_IMPORTS = 64
MAX_CALLS = 64
MAX_REFLECTIVE_TARGETS = 256
ALGORITHMS = frozenset({"HS256", "HS384", "HS512", "RS256", "RS384", "RS512",
                        "ES256", "ES384", "ES512", "PS256", "PS384", "PS512", "EdDSA"})
META_NAMES = frozenset({"globals", "locals", "vars", "eval", "exec", "__import__", "__builtins__"})
META_ATTRIBUTES = META_NAMES | {"__dict__", "__globals__", "f_globals", "f_locals", "_getframe", "currentframe"}
META_MODULES = ("builtins", "importlib", "unittest.mock", "mock")


def root_name(node):
    for _ in range(64):
        if isinstance(node, ast.Name):
            return node.id
        if not isinstance(node, (ast.Attribute, ast.Subscript)):
            return None
        node = node.value
    return None


class RuntimeJWTSource:
    """Conservative source-wide import/readonly proof, not module authentication.

    Ambiguous rebindings in any lexical scope decline this new form. Existing
    source forms remain the caller's responsibility; no file is exempted.
    """
    def __init__(self, nodes):
        self.parents = {}
        self.imports = defaultdict(list)
        self.names = defaultdict(list)
        self.rebound = set()
        self.mutated = set()
        self.reflective_strings = []
        self.namespace_strings = []
        self.unknown = False
        self.calls = []
        self.cache = {}
        self._candidates = None
        for node in nodes:
            for child in ast.iter_child_nodes(node):
                self.parents[child] = node
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.imports[alias.asname or alias.name.split(".")[0]].append(("module", alias.name))
                    if any(alias.name == m or alias.name.startswith(m + ".") for m in META_MODULES):
                        self.unknown = True
            elif isinstance(node, ast.ImportFrom):
                if node.level or not node.module or any(a.name == "*" for a in node.names):
                    self.unknown = True
                if node.module and any(node.module == m or node.module.startswith(m + ".") for m in META_MODULES):
                    self.unknown = True
                for alias in node.names:
                    self.imports[alias.asname or alias.name].append(("member", (node.module or "") + "." + alias.name))
            elif isinstance(node, ast.Name):
                self.names[node.id].append(node)
                if node.id in META_NAMES:
                    self.unknown = True
                if isinstance(node.ctx, (ast.Store, ast.Del)):
                    self.rebound.add(node.id)
            elif isinstance(node, ast.arg):
                self.rebound.add(node.arg)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.rebound.add(node.name)
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                self.rebound.update(node.names)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                self.rebound.add(node.name)
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
                self.rebound.add(node.name)
            elif isinstance(node, ast.MatchMapping) and node.rest:
                self.rebound.add(node.rest)
            elif type(node).__name__ in {"TypeVar", "ParamSpec", "TypeVarTuple"}:
                # Python 3.12+ type parameters bind names without Name.Store.
                self.rebound.add(node.name)
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.namespace_strings.append(node.value)
            if isinstance(node, ast.Attribute) and node.attr in META_ATTRIBUTES:
                self.unknown = True
            if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
                self.mutated.add(root_name(node))
            if isinstance(node, ast.Call):
                self.calls.append(node)
        if sum(map(len, self.imports.values())) > MAX_IMPORTS:
            self.unknown = True
        for call in self.calls:
            func = call.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if isinstance(func, ast.Name) and name in {"globals", "locals", "vars", "eval", "exec", "__import__"}:
                self.unknown = True
            if name in {"patch", "import_module", "reload"}:
                # Runtime namespace replacement cannot certify an encoder.
                self.unknown = True
            if name in {"setattr", "delattr", "__setattr__", "__delattr__"}:
                target = call.args[0] if call.args else None
                if isinstance(target, ast.Constant) and isinstance(target.value, str):
                    self.reflective_strings.append(target.value)
                else:
                    root = root_name(target)
                    if root is None or len(self.imports.get(root, [])) != 1:
                        self.unknown = True
                    self.mutated.add(root)
            if isinstance(func, ast.Attribute):
                root = root_name(func.value)
                # Encoder calls are considered separately. Other methods on an
                # imported configuration object can mutate its key source.
                if not (isinstance(func.value, ast.Name) and func.attr == "encode"
                        and self.imports.get(root) == [("module", "jwt")]):
                    self.mutated.add(root)
        if len(self.reflective_strings) > MAX_REFLECTIVE_TARGETS:
            self.unknown = True

    def readonly_import(self, name, *, encoder=False):
        key = (name, encoder)
        if key in self.cache:
            return self.cache[key]
        records = self.imports.get(name, [])
        safe = (not self.unknown and len(records) == 1 and name not in self.rebound
                and name not in self.mutated)
        if safe and encoder:
            safe = records[0] == ("module", "jwt")
        elif safe:
            # A signing configuration source is distinct from the encoder
            # namespace; another alias of jwt cannot certify its own key.
            safe = not (records[0][1] == "jwt" or records[0][1].startswith("jwt."))
        if safe:
            prefixes = (name + ".", records[0][1] + ".")
            safe = not any(s == name or s == records[0][1] or s.startswith(prefixes)
                           for s in self.reflective_strings + self.namespace_strings)
        if safe:
            for node in self.names[name]:
                parent = self.parents.get(node)
                if not isinstance(parent, (ast.Attribute, ast.Subscript)) or parent.value is not node:
                    safe = False
                    break
                if encoder:
                    outer = self.parents.get(parent)
                    if not (isinstance(parent, ast.Attribute) and parent.attr == "encode"
                            and isinstance(outer, ast.Call) and outer.func is parent):
                        safe = False
                        break
        self.cache[key] = safe
        return safe

    def claims_encoder(self, call):
        return (isinstance(call.func, ast.Attribute) and call.func.attr == "encode"
                and isinstance(call.func.value, ast.Name)
                and ("module", "jwt") in self.imports.get(call.func.value.id, []))

    def candidates(self):
        if self._candidates is not None:
            return self._candidates
        result = [call for call in self.calls if self.claims_encoder(call)
                  and self.readonly_import(call.func.value.id, encoder=True)]
        self._candidates = tuple(result) if len(result) <= MAX_CALLS else ()
        return self._candidates

    def allows(self, call, runtime_lookup):
        if call not in self.candidates():
            return False
        if not (len(call.args) == 2 and isinstance(call.args[0], ast.Dict)
                and all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in call.args[0].keys)
                and len(call.keywords) == 1 and call.keywords[0].arg == "algorithm"):
            return False
        key = call.args[1]
        root = root_name(key)
        if not (isinstance(key, ast.Attribute) and root and self.readonly_import(root)
                and runtime_lookup(key)):
            return False
        algorithm = call.keywords[0].value
        if isinstance(algorithm, ast.Constant):
            return isinstance(algorithm.value, str) and algorithm.value in ALGORITHMS
        root = root_name(algorithm)
        return (isinstance(algorithm, ast.Attribute) and bool(root)
                and self.readonly_import(root) and runtime_lookup(algorithm))
