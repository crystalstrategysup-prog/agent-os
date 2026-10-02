"""POSIX fsync storage for immutable handoff objects and conditional ROOT publication.

Trusted adapters supply principals. This format is portable; this disk adapter
does not claim isolation from a malicious process with the same UID.
"""

from __future__ import annotations

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


def scan_secrets(data: bytes):
    # Known sensitive fields and recognizable keys are refused, without echoing
    # the data. Classification/ACL and semantic review remain independent.
    patterns = [
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        rb"\b(?:sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{30,})",
        rb'(?i)["\'](?:password|access_token|refresh_token|api_key|cookie|authorization)["\']\s*[:=]\s*["\'][^"\']+["\']',
    ]
    require(
        not any(re.search(pattern, data) for pattern in patterns), "SECRET_DETECTED"
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
