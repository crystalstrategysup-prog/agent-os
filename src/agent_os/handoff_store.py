"""POSIX fsync storage for immutable handoff objects and conditional ROOT publication.

Trusted adapters supply principals. This format is portable; this disk adapter
does not claim isolation from a malicious process with the same UID.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from .safeio import _parse_json, within

MAX_OBJECT = 16 * 1024 * 1024
MAX_ROOT = 16 * 1024
PAGE_BYTES = 64 * 1024
NORMALIZER = "unicode-nfc-casefold-separators/v1"
SERIALIZER = "utf8-sorted-keys-integer-json/v1"


class HandoffError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def require(condition, code="INTEGRITY_FAILED"):
    if not condition:
        raise HandoffError(code)


def encoded(value) -> bytes:
    def check(v):
        if isinstance(v, float):
            raise HandoffError("UNSUPPORTED_NUMBER")
        if isinstance(v, dict):
            require(all(isinstance(k, str) for k in v), "INVALID_INPUT")
            for item in v.values():
                check(item)
        elif isinstance(v, list):
            for item in v:
                check(item)

    check(value)
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse(data: bytes):
    try:
        return _parse_json(data)
    except (ValueError, UnicodeError) as exc:
        raise HandoffError("INTEGRITY_FAILED") from exc


def stable_id() -> str:
    return "urn:uuid:" + str(uuid.uuid4())


def valid_id(value):
    require(
        isinstance(value, str)
        and len(value) <= 160
        and re.fullmatch(r"[\w:.@-]+", value),
        "INVALID_ID",
    )
    return value


_UNKNOWN_LITERAL = object()
_SENSITIVE_FIELDS = {
    "password",
    "access_token",
    "refresh_token",
    "api_key",
    "cookie",
    "authorization",
}


def _literal_value(node, bindings, seen=frozenset(), depth=0, budget=None):
    """Conservative static origin check; never execute source or resolve calls."""
    if budget is None:
        budget = [4096]
    budget[0] -= 1
    require(budget[0] >= 0, "SECRET_DETECTED")
    if depth > 64:
        return _UNKNOWN_LITERAL
    if isinstance(node, ast.Name):
        if node.id in seen:
            return _UNKNOWN_LITERAL
        for value in bindings.get(node.id, []):
            found = _literal_value(value, bindings, seen | {node.id}, depth + 1, budget)
            if found is not _UNKNOWN_LITERAL:
                return found
        return _UNKNOWN_LITERAL
    if isinstance(node, ast.JoinedStr) and all(
        isinstance(item, ast.Constant) and isinstance(item.value, str)
        for item in node.values
    ):
        return "".join(item.value for item in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal_value(node.left, bindings, seen, depth + 1, budget)
        right = _literal_value(node.right, bindings, seen, depth + 1, budget)
        if isinstance(left, str) and isinstance(right, str):
            require(len(left) + len(right) <= 2 * 1024 * 1024, "SECRET_DETECTED")
            return left + right
        return _UNKNOWN_LITERAL
    if isinstance(node, ast.Subscript):
        value = _literal_value(node.value, bindings, seen, depth + 1, budget)
        key = _literal_value(node.slice, bindings, seen, depth + 1, budget)
        if isinstance(value, dict) and isinstance(key, (str, int)):
            return value.get(key, _UNKNOWN_LITERAL)
        return _UNKNOWN_LITERAL
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, RecursionError):
        return _UNKNOWN_LITERAL


def _expression_path(node, depth=0):
    if depth > 64:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _expression_path(node.value, depth + 1)
        return base + "." + node.attr if base else None
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        base = _expression_path(node.value, depth + 1)
        if base and isinstance(node.slice.value, (str, int)):
            return base + "[" + repr(node.slice.value) + "]"
    return None


def _dynamic_credential_expression(
    node,
    bindings,
    assigned_paths,
    runtime_unpack,
    seen=frozenset(),
    depth=0,
    budget=None,
):
    """Bounded lookup grammar; calls/literals and ambiguous local origins fail."""
    if budget is None:
        budget = [4096]
    budget[0] -= 1
    if budget[0] < 0 or depth > 64:
        return False
    if isinstance(node, ast.Name):
        if node.id in seen:
            return False
        values = bindings.get(node.id, [])
        if node.id in runtime_unpack:
            return not values
        return all(
            _dynamic_credential_expression(
                value,
                bindings,
                assigned_paths,
                runtime_unpack,
                seen | {node.id},
                depth + 1,
                budget,
            )
            for value in values
        )
    if isinstance(node, ast.Attribute):
        return _expression_path(
            node
        ) not in assigned_paths and _dynamic_credential_expression(
            node.value,
            bindings,
            assigned_paths,
            runtime_unpack,
            seen,
            depth + 1,
            budget,
        )
    if isinstance(node, ast.Subscript):
        key = node.slice
        return (
            _expression_path(node) not in assigned_paths
            and _dynamic_credential_expression(
                node.value,
                bindings,
                assigned_paths,
                runtime_unpack,
                seen,
                depth + 1,
                budget,
            )
            and (
                isinstance(key, ast.Name)
                or isinstance(key, ast.Constant)
                and isinstance(key.value, (str, int))
            )
        )
    return False


def _source_literal_spans(data: bytes) -> set[tuple[int, int]]:
    """Prove two non-credential source forms, never exempt a file or field."""
    spans = set()
    # A type ternary contains the words password/text as input-type enums.
    # Require the complete same-identifier conditional; mask only its operands.
    identifier = rb"[A-Za-z_$][A-Za-z0-9_$]*"
    enum = re.compile(
        rb"\btype\s*:\s*(?P<name>"
        + identifier
        + rb")\s*&&\s*([\"'])password\2\s*===\s*(?P=name)\s*\?\s*"
        + rb"(?P<choice>([\"'])password\4\s*:\s*([\"'])text\5)"
        + rb"(?=\s*[,}])"
    )
    spans.update(match.span("choice") for match in enum.finditer(data))
    # Python source must parse, and only the exact empty Bearer prefix in a
    # dynamic dict value qualifies. Literal payloads anywhere in the RHS do not.
    if len(data) > 2 * 1024 * 1024:
        return spans
    try:
        tree = ast.parse(data)
    except (SyntaxError, ValueError, UnicodeError, RecursionError):
        return spans
    lines = data.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    scopes = []
    functions = {}
    nodes = []
    stack = [(tree, None)]
    while stack:
        node, scope = stack.pop()
        if len(nodes) >= 100_000:
            return spans
        if isinstance(
            node,
            (
                ast.Module,
                ast.ClassDef,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.Lambda,
            ),
        ):
            parent = scope
            scope = {"parent": parent, "bindings": {}, "paths": set(), "unpack": {}}
            scopes.append(scope)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.setdefault(node.name, []).append((node, scope))
        nodes.append((node, scope))
        stack.extend((child, scope) for child in ast.iter_child_nodes(node))
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                path = _expression_path(target)
                if isinstance(target, ast.Name) and node.value is not None:
                    scope["bindings"].setdefault(target.id, []).append(node.value)
                elif path:
                    scope["paths"].add(path)
                elif isinstance(target, (ast.Tuple, ast.List)):
                    for position, item in enumerate(target.elts):
                        named = [
                            child.id
                            for child in ast.walk(item)
                            if isinstance(child, ast.Name)
                        ]
                        if (
                            isinstance(item, ast.Name)
                            and isinstance(node.value, ast.Call)
                            and isinstance(node.value.func, ast.Attribute)
                        ):
                            scope["unpack"].setdefault(item.id, []).append(
                                (node.value, position)
                            )
                        else:
                            for name in named:
                                scope["bindings"].setdefault(name, []).append(
                                    ast.Constant(value=None)
                                )

    def visible(scope, kind):
        chain = []
        while scope is not None:
            require(len(chain) < 64, "SECRET_DETECTED")
            chain.append(scope)
            scope = scope["parent"]
        result = {} if kind != "paths" else set()
        for ancestor in reversed(chain):
            if kind == "paths":
                result.update(ancestor[kind])
            else:
                result.update(ancestor[kind])
        return result

    def local_output_safe(
        expression, bindings, assigned_paths, seen=frozenset(), depth=0, budget=None
    ):
        if budget is None:
            budget = [4096]
        budget[0] -= 1
        if budget[0] < 0 or depth > 64:
            return False
        if isinstance(expression, ast.Constant):
            return not isinstance(expression.value, str)
        if isinstance(expression, ast.Call):
            # Only external method-call data remains opaque. Local callables,
            # bare calls and literal receivers cannot certify a return origin.
            return (
                isinstance(expression.func, ast.Attribute)
                and expression.func.attr not in functions
                and _expression_path(expression.func) not in assigned_paths
                and _expression_path(expression.func.value) is not None
                and _dynamic_credential_expression(
                    expression.func.value, bindings, assigned_paths, set()
                )
            )
        if isinstance(expression, ast.Name):
            if expression.id in seen:
                return False
            return all(
                local_output_safe(
                    value,
                    bindings,
                    assigned_paths,
                    seen | {expression.id},
                    depth + 1,
                    budget,
                )
                for value in bindings.get(expression.id, [])
            )
        if isinstance(expression, (ast.Attribute, ast.Subscript)):
            return _expression_path(
                expression
            ) not in assigned_paths and local_output_safe(
                expression.value, bindings, assigned_paths, seen, depth + 1, budget
            )
        return all(
            local_output_safe(child, bindings, assigned_paths, seen, depth + 1, budget)
            for child in ast.iter_child_nodes(expression)
        )

    for scope in scopes:
        bindings = visible(scope, "bindings")
        assigned_paths = visible(scope, "paths")
        runtime_unpack = set()
        for name, calls in scope["unpack"].items():
            safe = True
            for call, position in calls:
                if _expression_path(call.func) in assigned_paths:
                    safe = False
                for function, function_scope in functions.get(call.func.attr, []):
                    outputs = [
                        item
                        for item in ast.walk(function)
                        if isinstance(item, (ast.Return, ast.Yield, ast.YieldFrom))
                        and item.value is not None
                    ]
                    if not outputs:
                        safe = False
                    for item in outputs:
                        expression = item.value
                        if isinstance(item, ast.Return) and isinstance(
                            expression, (ast.Tuple, ast.List)
                        ):
                            if position >= len(expression.elts):
                                safe = False
                                continue
                            expression = expression.elts[position]
                        if not local_output_safe(
                            expression,
                            visible(function_scope, "bindings"),
                            visible(function_scope, "paths"),
                        ):
                            safe = False
            if safe:
                runtime_unpack.add(name)
            else:
                scope["bindings"].setdefault(name, []).append(ast.Constant(value=None))
        scope["runtime_unpack"] = runtime_unpack
    for node, scope in nodes:
        bindings = visible(scope, "bindings")
        assigned_paths = visible(scope, "paths")
        runtime_unpack = scope["runtime_unpack"]
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value.casefold() in _SENSITIVE_FIELDS
            ):
                literal = _literal_value(value, bindings)
                require(not isinstance(literal, str) or not literal, "SECRET_DETECTED")
            if not (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value.casefold() == "authorization"
                and isinstance(value, ast.BinOp)
                and isinstance(value.op, ast.Add)
                and isinstance(value.left, ast.Constant)
                and value.left.value == "Bearer "
                and _dynamic_credential_expression(
                    value.right, bindings, assigned_paths, runtime_unpack
                )
            ):
                continue
            left = value.left
            spans.add(
                (
                    offsets[left.lineno - 1] + left.col_offset,
                    offsets[left.end_lineno - 1] + left.end_col_offset,
                )
            )
    return spans


def scan_secrets(data: bytes):
    # Recognizable keys always scan the original bytes, including source forms.
    patterns = [
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        rb"\b(?:sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{30,})",
    ]
    require(
        not any(re.search(pattern, data) for pattern in patterns), "SECRET_DETECTED"
    )
    field = re.compile(
        rb'(?i)["\'](?:password|access_token|refresh_token|api_key|cookie|authorization)["\']\s*[:=]\s*(?:\(\s*)*(?P<value>["\'][^"\']+["\'])'
    )
    findings = list(field.finditer(data))
    if not findings and not re.search(
        rb'(?i)["\'](?:password|access_token|refresh_token|api_key|cookie|authorization)["\']',
        data,
    ):
        return
    spans = _source_literal_spans(data)
    for match in findings:
        # Dynamic Bearer spans cover only the matched value, not the key. The
        # proven UI ternary covers the entire false field-shaped match.
        value_start = match.start("value")
        require(
            any(start <= value_start and match.end() <= end for start, end in spans),
            "SECRET_DETECTED",
        )


def sync_directory(path: Path):
    require(os.name == "posix", "UNSUPPORTED_DURABILITY_BACKEND")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def publisher_lock(path):
    require(
        os.name == "posix" and not path.is_symlink(), "UNSUPPORTED_DURABILITY_BACKEND"
    )
    import fcntl

    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise HandoffError("GENERATION_CONFLICT") from exc
        yield
    finally:
        os.close(fd)  # Kernel releases the lock, including after process death.


def durable(path: Path, data: bytes, *, immutable=False):
    require(not path.is_symlink(), "INTEGRITY_FAILED")
    if immutable and path.exists():
        require(bounded(path) == data)
        return
    missing = []
    ancestor = path.parent
    while not ancestor.exists():
        missing.append(ancestor)
        ancestor = ancestor.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=True)
        sync_directory(directory.parent)
    fd, temporary = tempfile.mkstemp(prefix=".aos-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if immutable:
            try:
                os.link(temporary, path)
            except FileExistsError:
                require(not path.is_symlink() and path.read_bytes() == data)
        else:
            os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def bounded(path: Path, limit=MAX_OBJECT) -> bytes:
    require(not path.is_symlink() and path.is_file())
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, "SIZE_LIMIT")
    return data


class Store:
    def __init__(self, root: Path, library_id: str):
        raw = root.expanduser().absolute()
        require(not raw.is_symlink(), "INTEGRITY_FAILED")
        self.root = raw.resolve()
        self.library_id = valid_id(library_id)
        self.metrics = {
            "entry_files": 0,
            "index_pages": 0,
            "objects": 0,
            "directory_walks": 0,
        }

    def path(self, relative: str) -> Path:
        try:
            return within(self.root, relative)
        except ValueError as exc:
            raise HandoffError("INTEGRITY_FAILED") from exc

    def put(self, data: bytes, media_type="application/json", *, scan=True) -> dict:
        require(isinstance(data, bytes) and len(data) <= MAX_OBJECT, "SIZE_LIMIT")
        if scan:
            scan_secrets(data)
        digest = sha(data)
        path = self.path(f"objects/sha256/{digest[:2]}/{digest}")
        durable(path, data, immutable=True)
        return self.reference(data, media_type)

    def reference(self, data, media_type="application/json"):
        digest = sha(data)
        return {
            "object_id": "sha256:" + digest,
            "locator": f"aos://{self.library_id}/objects/sha256/{digest}",
            "size_bytes": len(data),
            "media_type": media_type,
        }

    def put_json(self, value, *, limit=MAX_OBJECT):
        data = encoded(value)
        require(len(data) <= limit, "SIZE_LIMIT")
        return self.put(data)

    def get(self, ref: dict, *, limit=MAX_OBJECT) -> bytes:
        require(
            isinstance(ref, dict)
            and set(ref) == {"object_id", "locator", "size_bytes", "media_type"}
        )
        oid = ref.get("object_id", "")
        require(isinstance(oid, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", oid))
        digest = oid[7:]
        require(ref["locator"] == f"aos://{self.library_id}/objects/sha256/{digest}")
        require(type(ref["size_bytes"]) is int and 0 <= ref["size_bytes"] <= limit)
        try:
            path = self.path(f"objects/sha256/{digest[:2]}/{digest}")
            require(path.exists() or path.is_symlink(), "SOURCE_UNAVAILABLE")
            data = bounded(path, limit)
        except OSError as exc:
            raise HandoffError("SOURCE_UNAVAILABLE") from exc
        require(len(data) == ref["size_bytes"] and sha(data) == digest)
        self.metrics["objects"] += 1
        return data

    def json(self, ref, *, limit=MAX_OBJECT):
        return parse(self.get(ref, limit=limit))

    def root_bytes(self):
        return bounded(self.path("ROOT.json"), MAX_ROOT)

    def commit(self, expected_generation: int, value: dict):
        # Caller owns publisher.lock for this whole comparison/replacement.
        current = parse(self.root_bytes())
        require(current["generation"] == expected_generation, "GENERATION_CONFLICT")
        data = encoded(value)
        require(len(data) <= MAX_ROOT, "SIZE_LIMIT")
        durable(self.path("ROOT.json"), data)
