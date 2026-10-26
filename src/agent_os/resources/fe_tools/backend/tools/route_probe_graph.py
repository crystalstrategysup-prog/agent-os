"""Bounded Python source graph extraction. Selected modules are never imported."""
from __future__ import annotations

import ast
import builtins
import hashlib
import keyword
import os
import re
import stat
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path


_IDENT = r"[A-Za-z_]\w*"
_ENTRY = re.compile(rf"({_IDENT}(?:\.{_IDENT})*):({_IDENT}(?:\.{_IDENT})*)\Z", re.ASCII)
_SECRET = {"secrets", "secret", "credentials", "credential", ".ssh", ".aws", ".gnupg", ".git", "__pycache__"}
_MAX_SOURCE = 2 * 1024 * 1024
_MAX_TOTAL_SOURCE = 16 * 1024 * 1024


def _open_source(path: Path) -> int:
    """Open every ancestor through its FD so a replacement symlink cannot win."""
    directory = None
    try:
        directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        return os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                       dir_fd=directory)
    except OSError:
        raise ValueError("source_open_refused") from None
    finally:
        if directory is not None:
            os.close(directory)


def _safe_path(path: Path) -> Path:
    """Reject symlink components before any source read, including root ancestors."""
    path = path.absolute()
    if ".." in path.parts:
        raise ValueError("source_path_escape")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        if part.lower() in _SECRET or (part.endswith(".py") and part[:-3].lower() in _SECRET) or part.lower().startswith(".env"):
            raise ValueError("source_secret_path")
        current /= part
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                raise ValueError("source_symlink")
        except FileNotFoundError:
            break
    return path


def _expression(node: ast.AST | None) -> str:
    """Structural source expression, without string/number literal contents."""
    if node is None:
        return ""
    class Redact(ast.NodeTransformer):
        def visit_Constant(self, value):
            if value.value is None or type(value.value) is bool:
                return value
            return ast.copy_location(ast.Constant(value="<literal>"), value)
    try:
        # unparse a separate tree: never mutate the indexed source AST.
        text = ast.unparse(Redact().visit(ast.parse(ast.unparse(node), mode="eval").body))
    except (ValueError, SyntaxError, RecursionError):
        text = type(node).__name__
    return text if len(text) <= 240 else text[:237] + "..."


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return prefix + "." + node.attr if prefix else None
    return None


def _scope_nodes(body):
    """Walk one executable scope; nested definitions are indexed separately."""
    for node in body:
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        for child in ast.iter_child_nodes(node):
            yield from _scope_nodes([child])


@dataclass
class _Module:
    name: str
    path: str
    tree: ast.Module
    package: str
    symbols: dict = field(default_factory=dict)
    owners: dict = field(default_factory=dict)
    imports: dict = field(default_factory=dict)


class _Extractor:
    def __init__(self, root, max_files, max_nodes, max_depth, opaque_modules):
        self.root = _safe_path(Path(root))
        if not self.root.is_dir():
            raise ValueError("source_root_not_directory")
        self.max_files, self.max_nodes, self.max_depth = max_files, max_nodes, max_depth
        self.modules, self.files, self.nodes = {}, {}, {}
        self.edges, self.branches, self.unresolved, self.caps = {}, {}, {}, {}
        self.queue, self.expanded = deque(), set()
        self.total_bytes = 0
        self.opaque_modules = opaque_modules

    def opaque(self, name):
        return any(name == item or name.startswith(item + ".") for item in self.opaque_modules)

    def cap(self, kind, source, line=0, target=None):
        record = {"kind": kind, "source": source, "line": line, "target": target}
        self.caps[(kind, source, line, target)] = record

    def module_path(self, name):
        if self.opaque(name):
            return None
        parts = name.split(".")
        if not all(re.fullmatch(_IDENT, x, re.ASCII) and not keyword.iskeyword(x) for x in parts):
            raise ValueError("source_module_invalid")
        parent = self.root
        for part in parts[:-1]:
            candidate = parent / part
            _safe_path(parent)
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                return None
            parent = _safe_path(candidate)
            if not stat.S_ISDIR(info.st_mode):
                return None
        base = self.root.joinpath(*parts)
        for path in (base.with_suffix(".py"), base / "__init__.py"):
            # An absent local candidate is external. Do not reject an ordinary
            # stdlib import (e.g. secrets) for a nonexistent sensitive directory.
            probe = path.parent if path.name == "__init__.py" else path
            _safe_path(probe.parent)
            try:
                probe.lstat()
            except FileNotFoundError:
                continue
            path = _safe_path(path)
            if not path.is_relative_to(self.root):
                raise ValueError("source_path_escape")
            if path.exists():
                if not path.is_file():
                    raise ValueError("source_not_regular")
                return path
        return None

    def add_node(self, module, symbol, depth, source=None, line=0):
        ident = module.name + ":" + symbol
        if ident in self.nodes:
            return ident
        if depth > self.max_depth:
            self.cap("max_depth", source or ident, line, ident)
            return None
        if ident not in self.nodes:
            if len(self.nodes) >= self.max_nodes:
                self.cap("max_nodes", source or ident, line, ident)
                return None
            node = module.tree if symbol == "<module>" else module.symbols.get(symbol)
            if node is None:
                return None
            self.nodes[ident] = {"id": ident, "module": module.name, "symbol": symbol,
                "kind": "module" if symbol == "<module>" else type(node).__name__,
                "file": module.path, "line": getattr(node, "lineno", 1),
                "end_line": getattr(node, "end_lineno", len(module.tree.body) and module.tree.body[-1].end_lineno or 1)}
            self.queue.append((ident, depth))
        return ident

    def load(self, name, depth, source=None, line=0):
        if name in self.modules:
            self.add_node(self.modules[name], "<module>", depth, source, line)
            return self.modules[name]
        path = self.module_path(name)
        if path is None:
            return None
        if depth > self.max_depth:
            self.cap("max_depth", source or name, line, name)
            return None
        if len(self.files) >= self.max_files:
            self.cap("max_files", source or name, line, name)
            return None
        before = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("source_not_single_regular_file")
        if before.st_size > _MAX_SOURCE or self.total_bytes + before.st_size > _MAX_TOTAL_SOURCE:
            self.cap("source_bytes", source or name, line, name)
            return None
        # Open with O_NOFOLLOW and compare the named FD to both path snapshots.
        fd = _open_source(path)
        try:
            actual = os.fstat(fd)
            if (actual.st_dev, actual.st_ino, actual.st_size) != (before.st_dev, before.st_ino, before.st_size):
                raise ValueError("source_changed")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(_MAX_SOURCE + 1)
            after = os.fstat(fd)
            named = path.stat(follow_symlinks=False)
            fields = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if fields(before) != fields(after) or fields(after) != fields(named) or len(data) != actual.st_size:
                raise ValueError("source_changed")
        finally:
            os.close(fd)
        relative = path.relative_to(self.root).as_posix()
        try:
            tree = ast.parse(data, filename=relative)
        except (SyntaxError, ValueError, RecursionError) as exc:
            raise ValueError("source_syntax_invalid:" + relative) from None
        module = _Module(name, relative, tree, name if path.name == "__init__.py" else name.rpartition(".")[0])
        self.modules[name] = module
        self.files[relative] = {"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        self.total_bytes += len(data)
        self.index(module, tree.body)
        module.imports = self.import_bindings(module, tree.body)
        self.add_node(module, "<module>", depth, source, line)
        for count in range(1, len(name.split("."))):
            parent_name = ".".join(name.split(".")[:count])
            parent_path = self.module_path(parent_name)
            if parent_path is not None and parent_path.name == "__init__.py":
                parent = self.load(parent_name, depth, source, line)
                if parent is not None:
                    key = (name + ":<module>", 1, 0, "package", parent_name, parent_name)
                    self.edges[key] = {"source": name + ":<module>", "target": parent_name + ":<module>",
                        "file": relative, "line": 1, "expression": parent_name, "resolution": "staticlocal",
                        "reason": "package_initializer", "kind": "import"}
        return module

    def index(self, module, body, prefix="", owner=None):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbol = prefix + node.name
                module.symbols[symbol] = node
                module.owners[symbol] = owner
                if isinstance(node, ast.ClassDef):
                    self.index(module, node.body, symbol + ".", symbol)
                else:
                    self.index(module, node.body, symbol + ".<locals>.", owner)

    def absolute_import(self, module, node):
        if not node.level:
            return node.module or ""
        package = module.package.split(".") if module.package else []
        if node.level > len(package):
            return None
        base = package[:len(package) - node.level + 1]
        return ".".join(base + ((node.module or "").split(".") if node.module else []))

    def import_bindings(self, module, body):
        bindings = {}
        for node in _scope_nodes(body):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bindings[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom):
                base = self.absolute_import(module, node)
                if base is not None:
                    for alias in node.names:
                        if alias.name != "*":
                            bindings[alias.asname or alias.name] = ".".join(x for x in (base, alias.name) if x)
        return bindings

    def qualified(self, name, depth, source, line, seen=()):
        if self.opaque(name):
            return name, "external", "opaque_module"
        if name in seen or len(seen) >= 16:
            return None, "dynamic", "reexport_cycle"
        parts = name.split(".")
        for count in range(len(parts), 0, -1):
            module_name = ".".join(parts[:count])
            if any(not re.fullmatch(_IDENT, part, re.ASCII) for part in parts[:count]):
                continue  # Internal nested-symbol marker is not a filesystem module.
            if self.module_path(module_name) is None:
                continue
            module = self.load(module_name, depth, source, line)
            if module is None:
                return None, "dynamic", "expansion_cap"
            symbol = ".".join(parts[count:])
            if not symbol:
                return module.name + ":<module>", "staticlocal", "local_module"
            if symbol in module.symbols:
                target = self.add_node(module, symbol, depth, source, line)
                return target, "staticlocal" if target else "dynamic", "local_symbol" if target else "expansion_cap"
            first, _, suffix = symbol.partition(".")
            if first in module.imports:
                return self.qualified(module.imports[first] + ("." + suffix if suffix else ""), depth, source, line, seen + (name,))
            return None, "dynamic", "local_symbol_not_defined"
        return name, "external", "outside_source_root"

    def resolve(self, module, symbol, bindings, instances, shadowed, call, depth, source):
        dotted = _dotted(call.func)
        if dotted is None:
            return None, "dynamic", "computed_callable"
        first, _, suffix = dotted.partition(".")
        owner = module.owners.get(symbol)
        if first in {"self", "cls"} and owner and suffix:
            candidate = owner + "." + suffix
            if candidate in module.symbols:
                return self.qualified(module.name + "." + candidate, depth, source, call.lineno)
            return None, "dynamic", "receiver_method_not_defined"
        if first in instances and suffix:
            return self.qualified(instances[first] + "." + suffix, depth, source, call.lineno)
        if first in shadowed:
            return None, "dynamic", "rebound_or_parameter"
        if first in bindings:
            result = self.qualified(bindings[first] + ("." + suffix if suffix else ""), depth, source, call.lineno)
        elif dotted in module.symbols:
            result = self.qualified(module.name + "." + dotted, depth, source, call.lineno)
        else:
            local = symbol + ".<locals>." + dotted
            if local in module.symbols:
                result = self.qualified(module.name + "." + local, depth, source, call.lineno)
            elif first in vars(builtins):
                return "builtins." + dotted, "external", "builtin"
            else:
                return None, "dynamic", "unresolved_name_or_callback"
        target, resolution, reason = result
        if resolution == "staticlocal" and target:
            target_module, _, target_symbol = target.partition(":")
            selected = self.modules[target_module]
            if isinstance(selected.symbols.get(target_symbol), ast.ClassDef):
                init = target_symbol + ".__init__"
                if init in selected.symbols:
                    target = self.add_node(selected, init, depth, source, call.lineno)
                    return target, "staticlocal" if target else "dynamic", "constructor" if target else "expansion_cap"
        return target, resolution, reason

    def edge(self, source, target, node, module, resolution, reason, kind="call"):
        expression = _expression(node.func if isinstance(node, ast.Call) else node)
        record = {"source": source, "target": target, "file": module.path, "line": node.lineno,
                  "expression": expression, "resolution": resolution, "reason": reason, "kind": kind}
        key = (source, node.lineno, getattr(node, "col_offset", 0), kind, expression, target or "")
        self.edges[key] = record
        if resolution == "dynamic":
            self.unresolved[key] = record.copy()

    def expand(self, ident, depth):
        if ident in self.expanded:
            return
        self.expanded.add(ident)
        name, _, symbol = ident.partition(":")
        module = self.modules[name]
        selected = module.tree if symbol == "<module>" else module.symbols[symbol]
        body = selected.body
        bindings = dict(module.imports)
        bindings.update(self.import_bindings(module, body))
        instances = {}
        nodes = list(_scope_nodes(body))
        shadowed = set()
        if isinstance(selected, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = selected.args
            shadowed.update(a.arg for a in args.posonlyargs + args.args + args.kwonlyargs)
            shadowed.update(a.arg for a in (args.vararg, args.kwarg) if a is not None)
        for item in nodes:
            if isinstance(item, (ast.Assign, ast.AnnAssign, ast.NamedExpr, ast.AugAssign)):
                targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                shadowed.update(n.id for target in targets for n in ast.walk(target) if isinstance(n, ast.Name))
        for node in nodes:
            if len(self.edges) >= self.max_nodes * 8 or len(self.branches) >= self.max_nodes * 8:
                self.cap("max_edges_or_branches", ident, getattr(node, "lineno", 0))
                break
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if isinstance(value, ast.Call) and _dotted(value.func):
                    dotted = _dotted(value.func)
                    first, _, suffix = dotted.partition(".")
                    qualified = bindings.get(first, module.name + "." + first) + ("." + suffix if suffix else "")
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            instances[target.id] = qualified
            if isinstance(node, ast.Call):
                target, resolution, reason = self.resolve(module, symbol, bindings, instances, shadowed, node, depth + 1, ident)
                self.edge(ident, target, node, module, resolution, reason)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    targets = [alias.name for alias in node.names]
                else:
                    base = self.absolute_import(module, node)
                    targets = [] if base is None else [".".join(x for x in (base, alias.name) if x) if alias.name != "*" else base for alias in node.names]
                for target_name in targets:
                    target, resolution, reason = self.qualified(target_name, depth + 1, ident, node.lineno)
                    self.edge(ident, target, node, module, resolution, reason, "import")
                if isinstance(node, ast.ImportFrom) and (base is None or any(a.name == "*" for a in node.names)):
                    self.edge(ident, None, node, module, "dynamic", "relative_import_outside_root" if base is None else "star_import", "import_gap")
            branch = None
            if isinstance(node, (ast.If, ast.While, ast.IfExp)):
                branch = node.test
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
                branch = node.iter
            elif isinstance(node, (ast.Try, ast.TryStar, ast.Match, ast.ExceptHandler)):
                branch = node.subject if isinstance(node, ast.Match) else getattr(node, "type", None)
            else:
                continue
            if hasattr(node, "lineno"):
                key = (ident, node.lineno, getattr(node, "col_offset", 0), type(node).__name__)
                self.branches[key] = {"source": ident, "file": module.path, "line": node.lineno,
                    "kind": type(node).__name__, "expression": _expression(branch), "execution": "not_evaluated"}

    def run(self, name, symbol):
        module = self.load(name, 0)
        if module is None or symbol not in module.symbols or not isinstance(module.symbols[symbol], (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise ValueError("entry_function_not_found")
        ident = self.add_node(module, symbol, 0)
        if ident is None:
            raise ValueError("entry_node_cap")
        while self.queue:
            current, depth = self.queue.popleft()
            self.expand(current, depth)
        return {"schema": "route-probe.graph/v1", "entry": dict(self.nodes[ident]),
                "files": [self.files[k] for k in sorted(self.files)],
                "nodes": [self.nodes[k] for k in sorted(self.nodes)],
                "edges": [self.edges[k] for k in sorted(self.edges)],
                "branches": [self.branches[k] for k in sorted(self.branches)],
                "unresolved": [self.unresolved[k] for k in sorted(self.unresolved)],
                "unresolved_caps": [self.caps[k] for k in sorted(self.caps, key=str)],
                "complete": not bool(self.caps),
                "opaque_modules": list(self.opaque_modules),
                "limits": {"max_files": self.max_files, "max_nodes": self.max_nodes, "max_depth": self.max_depth},
                "semantics": "Static source graph only; branches unevaluated, external and dynamic calls not executed or authorized."}


def extract_route(source_root: Path, entry: str, *, max_files=80, max_nodes=1200, max_depth=8, opaque_modules=()) -> dict:
    """Extract deterministic local call/import closure and explicit unresolved gaps.

    Invalid inputs and unsafe source paths raise ValueError. Expansion limits return
    complete=False/unresolved_caps; consumers must refuse such graphs for replay.
    External/dynamic calls remain visible and require explicit replay mocks/denials.
    """
    if not isinstance(entry, str) or len(entry) > 512:
        raise ValueError("entry_invalid")
    match = _ENTRY.fullmatch(entry)
    if not match or any(keyword.iskeyword(x) for x in re.split(r"[.:]", entry)):
        raise ValueError("entry_invalid")
    if not isinstance(opaque_modules, (tuple, list)) or len(opaque_modules) > 100:
        raise ValueError("opaque_modules_invalid")
    for item in opaque_modules:
        if (not isinstance(item, str) or len(item) > 256
                or not re.fullmatch(rf"{_IDENT}(?:\.{_IDENT})*", item, re.ASCII)
                or any(keyword.iskeyword(x) for x in item.split("."))):
            raise ValueError("opaque_modules_invalid")
    opaque_modules = tuple(sorted(set(opaque_modules)))
    if any(match.group(1) == item or match.group(1).startswith(item + ".") for item in opaque_modules):
        raise ValueError("entry_module_opaque")
    for value, ceiling, label in ((max_files, 1000, "max_files"), (max_nodes, 20000, "max_nodes"), (max_depth, 64, "max_depth")):
        if type(value) is not int or not 1 <= value <= ceiling:
            raise ValueError("limit_invalid:" + label)
    return _Extractor(source_root, max_files, max_nodes, max_depth, opaque_modules).run(*match.groups())
