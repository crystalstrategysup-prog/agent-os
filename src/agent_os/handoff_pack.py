"""Opt-in, immutable POSIX storage for index pages with unchanged object refs."""

import hashlib
import os
import re
import stat
import struct
import zlib
from contextlib import contextmanager
from pathlib import Path

from .handoff_store import (
    PAGE_BYTES, HandoffError, bounded, durable, encoded, parse,
    require, sha, sync_directory,
)

POINTER = "OBJECT_PACK.json"
SCHEMA = "agentos.index-pack/v1"
PACK_HEADER = b"AOSPK001"
INDEX_MAGIC = b"AOSIDX01"
INDEX_HEADER = struct.Struct(">8sQ")
ROW = struct.Struct(">32sQII")
MAX_ROWS = 1_000_000
MAX_FRAME = PAGE_BYTES + 128
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


@contextmanager
def opened(path):
    require(os.name == "posix", "UNSUPPORTED_DURABILITY_BACKEND")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), "INVALID_PACK")
        with os.fdopen(os.dup(fd), "rb") as stream:
            yield stream, info.st_size
    finally:
        os.close(fd)


def absolute_directory(path):
    path = Path(path).expanduser().absolute()
    require(path == path.resolve(), "INVALID_PACK_DIRECTORY")
    return path


def exact(stream, length, offset):
    result = os.pread(stream.fileno(), length, offset)
    require(len(result) == length, "INVALID_PACK")
    return result


def decode(stream, key, offset, compressed, raw):
    frame = exact(stream, compressed, offset)
    try:
        parser = zlib.decompressobj()
        content = parser.decompress(frame, raw + 1)
    except zlib.error as exc:
        raise HandoffError("INVALID_PACK") from exc
    require(parser.eof and not parser.unused_data and not parser.unconsumed_tail
            and len(content) == raw and hashlib.sha256(content).digest() == key,
            "INVALID_PACK")
    return content


def require_page(data):
    page = parse(data)
    require(isinstance(page, dict)
            and page.get("schema") in ("aos.index-page/v1", "aos.index-page/v2")
            and page.get("kind") in ("leaf", "branch")
            and isinstance(page.get("entries"), list), "PACK_INDEX_PAGE_REQUIRED")


def space_for(path, additional, reserve):
    info = os.statvfs(path)
    blocks = (additional + info.f_frsize - 1) // info.f_frsize
    require((info.f_bavail - blocks) * info.f_frsize >= reserve, "PACK_CAPACITY")


class IndexPack:
    def __init__(self, directory, library_id, manifest_digest=None):
        self.directory = absolute_directory(directory)
        raw = bounded(self.directory / "MANIFEST.json", 4096)
        self.digest = sha(raw)
        self.manifest = parse(raw)
        m = self.manifest
        require(isinstance(m, dict) and set(m) == {"schema", "library_id", "count", "pack", "index"}
                and m["schema"] == SCHEMA and m["library_id"] == library_id
                and (manifest_digest is None or manifest_digest == self.digest)
                and type(m["count"]) is int and 0 < m["count"] <= MAX_ROWS,
                "INVALID_PACK")
        for name in ("pack", "index"):
            value = m[name]
            require(isinstance(value, dict) and set(value) == {"size", "sha256"}
                    and type(value["size"]) is int and value["size"] > 0
                    and isinstance(value["sha256"], str) and DIGEST.fullmatch(value["sha256"]),
                    "INVALID_PACK")

    @contextmanager
    def files(self):
        with opened(self.directory / "index.bin") as (index, index_size), \
             opened(self.directory / "pack.bin") as (pack, pack_size):
            count = self.manifest["count"]
            require(index_size == self.manifest["index"]["size"] == INDEX_HEADER.size + count * ROW.size
                    and pack_size == self.manifest["pack"]["size"]
                    and exact(index, INDEX_HEADER.size, 0) == INDEX_HEADER.pack(INDEX_MAGIC, count)
                    and exact(pack, len(PACK_HEADER), 0) == PACK_HEADER, "INVALID_PACK")
            yield index, pack, pack_size

    @staticmethod
    def row(index, number, pack_size):
        item = ROW.unpack(exact(index, ROW.size, INDEX_HEADER.size + number * ROW.size))
        _, offset, compressed, raw = item
        require(offset >= len(PACK_HEADER) and 0 < compressed <= MAX_FRAME
                and offset + compressed <= pack_size and 0 < raw <= PAGE_BYTES, "INVALID_PACK")
        return item

    def read(self, digest, size):
        target = bytes.fromhex(digest)
        with self.files() as (index, pack, pack_size):
            left, right = 0, self.manifest["count"]
            while left < right:
                middle = (left + right) // 2
                key, offset, compressed, raw = self.row(index, middle, pack_size)
                if key == target:
                    require(raw == size, "INVALID_PACK")
                    return decode(pack, key, offset, compressed, raw)
                if key < target:
                    left = middle + 1
                else:
                    right = middle
        raise HandoffError("SOURCE_UNAVAILABLE")

    def verified_pages(self):
        with self.files() as (index, pack, pack_size):
            for name, stream in (("index", index), ("pack", pack)):
                require(hashlib.file_digest(stream, "sha256").hexdigest()
                        == self.manifest[name]["sha256"], "INVALID_PACK")
            end, prior = len(PACK_HEADER), b""
            for number in range(self.manifest["count"]):
                key, offset, compressed, raw = self.row(index, number, pack_size)
                require(key > prior and offset == end, "INVALID_PACK")
                content = decode(pack, key, offset, compressed, raw)
                require_page(content)
                end, prior = offset + compressed, key
                yield key.hex(), content
            require(end == pack_size, "INVALID_PACK")


def pointer(store):
    try:
        with opened(store.path(POINTER)) as (stream, length):
            require(0 < length <= 8192, "INVALID_PACK")
            config = parse(exact(stream, length, 0))
    except FileNotFoundError:
        return None
    require(isinstance(config, dict) and set(config) == {"directory", "manifest_sha256"}
            and isinstance(config["directory"], str) and Path(config["directory"]).is_absolute()
            and isinstance(config["manifest_sha256"], str)
            and DIGEST.fullmatch(config["manifest_sha256"]), "INVALID_PACK")
    return config


def read_packed(store, digest, size):
    require(os.name == "posix", "SOURCE_UNAVAILABLE")
    config = pointer(store)
    require(config is not None, "SOURCE_UNAVAILABLE")
    try:
        pack = IndexPack(config["directory"], store.library_id, config["manifest_sha256"])
        return pack.read(digest, size)
    except (OSError, ValueError) as exc:
        if isinstance(exc, HandoffError):
            raise
        raise HandoffError("PACK_UNAVAILABLE") from exc


def build_pack(store, selection, directory, budget, reserve):
    require(type(budget) is int and type(reserve) is int and budget > 0 and reserve >= 0,
            "INVALID_PACK_CAPACITY")
    directory = absolute_directory(directory)
    require(directory != store.root and store.root not in directory.parents, "INVALID_PACK_DIRECTORY")
    space_for(directory.parent, budget, reserve)
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise HandoffError("DESTINATION_EXISTS") from exc
    names = ("pack.bin", "index.bin", "MANIFEST.json")
    try:
        sync_directory(directory.parent)
        with opened(selection) as (keys, length), \
             (directory / names[0]).open("xb") as pack, \
             (directory / names[1]).open("x+b") as index:
            require(0 < length <= MAX_ROWS * 65, "INVALID_PACK_SELECTION")
            pack.write(PACK_HEADER)
            index.write(INDEX_HEADER.pack(INDEX_MAGIC, 0))
            count, previous = 0, ""
            capacity_check = 0
            while line := keys.readline(66):
                require(len(line) == 65 and line.endswith(b"\n"), "INVALID_PACK_SELECTION")
                try:
                    digest = line[:-1].decode("ascii")
                except UnicodeError as exc:
                    raise HandoffError("INVALID_PACK_SELECTION") from exc
                require(DIGEST.fullmatch(digest) and digest > previous and count < MAX_ROWS,
                        "INVALID_PACK_SELECTION")
                data = bounded(store.path(f"objects/sha256/{digest[:2]}/{digest}"), PAGE_BYTES)
                require(sha(data) == digest, "INTEGRITY_FAILED")
                require_page(data)
                frame = zlib.compress(data, 3)
                used = pack.tell() + index.tell()
                require(used + len(frame) + ROW.size + 4096 <= budget, "PACK_CAPACITY")
                if used >= capacity_check:
                    pack.flush()
                    index.flush()
                    step = 4 * 1024 * 1024
                    space_for(directory, min(budget - used, step + MAX_FRAME + 4096), reserve)
                    capacity_check = used + step
                index.write(ROW.pack(bytes.fromhex(digest), pack.tell(), len(frame), len(data)))
                pack.write(frame)
                count, previous = count + 1, digest
            require(count > 0, "INVALID_PACK_SELECTION")
            index.seek(0)
            index.write(INDEX_HEADER.pack(INDEX_MAGIC, count))
            for stream in (pack, index):
                stream.flush()
                os.fsync(stream.fileno())
        info = {"schema": SCHEMA, "library_id": store.library_id, "count": count}
        for name in ("pack", "index"):
            with opened(directory / f"{name}.bin") as (stream, length):
                info[name] = {"size": length, "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
        space_for(directory, 4096, reserve)
        raw = encoded(info)
        durable(directory / names[2], raw, immutable=True)
        return {"status": "built", "count": count, "manifest_sha256": sha(raw)}
    except BaseException:
        for name in names:
            (directory / name).unlink(missing_ok=True)
        directory.rmdir()
        raise


def attach_pack(store, directory, expected_manifest):
    require(isinstance(expected_manifest, str) and DIGEST.fullmatch(expected_manifest),
            "INVALID_PACK")
    pack = IndexPack(directory, store.library_id, expected_manifest)
    config = {"directory": str(pack.directory), "manifest_sha256": pack.digest}
    existing = pointer(store)
    require(existing is None or existing == config, "PACK_ALREADY_ATTACHED")
    for _ in pack.verified_pages():
        pass
    if existing is None:
        durable(store.path(POINTER), encoded(config), immutable=True)
    return {"status": "attached", "count": pack.manifest["count"], "manifest_sha256": pack.digest}


def restore_pack(store, reserve):
    require(type(reserve) is int and reserve >= 0, "INVALID_PACK_CAPACITY")
    config = pointer(store)
    require(config is not None, "SOURCE_UNAVAILABLE")
    pack = IndexPack(config["directory"], store.library_id, config["manifest_sha256"])
    for digest, data in pack.verified_pages():
        path = store.path(f"objects/sha256/{digest[:2]}/{digest}")
        try:
            path.lstat()
        except FileNotFoundError:
            space_for(store.root, len(data), reserve)
            durable(path, data, immutable=True)
        else:
            require(bounded(path, PAGE_BYTES) == data, "INTEGRITY_FAILED")
    store.path(POINTER).unlink()
    sync_directory(store.root)
    return {"status": "restored", "count": pack.manifest["count"], "manifest_sha256": pack.digest}
