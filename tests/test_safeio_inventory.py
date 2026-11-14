"""Synthetic inventory byte bounds, read stability and full-content hashing."""

from __future__ import annotations

import hashlib
import os
import tracemalloc
from pathlib import Path

import pytest

from agent_os import safeio
from agent_os.safeio import GateError, filemap


@pytest.mark.parametrize("size", [0, 1, 1024 * 1024 - 1, 1024 * 1024, 1024 * 1024 + 17])
def test_streaming_digest_covers_every_byte_at_exact_budget(tmp_path, size):
    content = b"x" * size
    (tmp_path / "sample.bin").write_bytes(content)
    assert filemap(tmp_path, max_bytes=size) == {
        "sample.bin": hashlib.sha256(content).hexdigest()
    }


def test_inventory_preserves_aggregate_byte_and_file_budgets(tmp_path):
    (tmp_path / "a").write_bytes(b"ab")
    (tmp_path / "b").write_bytes(b"cde")
    assert len(filemap(tmp_path, max_bytes=5, limit=2)) == 2
    with pytest.raises(GateError, match="tree_inventory_limit"):
        filemap(tmp_path, max_bytes=4)
    with pytest.raises(GateError, match="tree_inventory_limit"):
        filemap(tmp_path, limit=1)


def test_large_file_does_not_require_a_full_size_allocation(tmp_path):
    block = b"content-bound fixture\n" * 32768
    expected = hashlib.sha256()
    path = tmp_path / "sample.bin"
    with path.open("wb") as stream:
        for _ in range(24):
            stream.write(block)
            expected.update(block)
    tracemalloc.start()
    try:
        result = filemap(tmp_path, max_bytes=32 * 1024 * 1024)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result["sample.bin"] == expected.hexdigest()
    # The old read_bytes path required over 15 MiB for this fixture. Allow room
    # for buffers and ordinary bookkeeping, without relying on exact timings.
    assert peak < 8 * 1024 * 1024


def _mutate_before_open(monkeypatch, path, mutate):
    original = safeio.os.open
    observed = []

    def open_changed(candidate, flags, *args, **kwargs):
        if Path(candidate) == path and not observed:
            observed.append(flags)
            mutate()
        return original(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(safeio.os, "open", open_changed)
    return observed


def _mutate_after_first_read(monkeypatch, path, mutate):
    original = safeio.os.read
    identity = (path.stat().st_dev, path.stat().st_ino)
    observed = {"mutated": False, "read_bytes": 0}

    def read_changed(fd, count):
        data = original(fd, count)
        metadata = os.fstat(fd)
        if (metadata.st_dev, metadata.st_ino) == identity:
            observed["read_bytes"] += len(data)
            if not observed["mutated"]:
                observed["mutated"] = True
                mutate()
        return data

    monkeypatch.setattr(safeio.os, "read", read_changed)
    return observed


def test_growth_between_stat_and_open_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"x")
    changed = _mutate_before_open(monkeypatch, path, lambda: path.write_bytes(b"x" * 64))
    with pytest.raises(GateError, match="inventory_file_changed:sample.bin"):
        filemap(tmp_path, max_bytes=4)
    assert changed


def test_growth_during_read_stops_at_budget_plus_one_byte(tmp_path, monkeypatch):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"1234")

    def grow():
        with path.open("ab") as stream:
            stream.write(b"x" * 64)

    changed = _mutate_after_first_read(monkeypatch, path, grow)
    with pytest.raises(GateError, match="tree_inventory_limit"):
        filemap(tmp_path, max_bytes=4)
    assert changed["mutated"]
    assert changed["read_bytes"] == 5


@pytest.mark.parametrize("mutation", ["truncate", "rewrite", "replace", "delete"])
def test_file_change_during_read_never_returns_an_inventory(tmp_path, monkeypatch, mutation):
    path = tmp_path / "sample.bin"
    content = b"x" * (1024 * 1024 + 32)
    path.write_bytes(content)
    original_stat = path.stat()

    def mutate():
        if mutation == "truncate":
            with path.open("r+b") as stream:
                stream.truncate(0)
        elif mutation == "rewrite":
            with path.open("r+b") as stream:
                stream.write(b"y")
            # Size and mtime alone cannot establish read stability.
            os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        elif mutation == "replace":
            replacement = tmp_path / "replacement"
            replacement.write_bytes(content)
            os.replace(replacement, path)
        else:
            path.unlink()

    changed = _mutate_after_first_read(monkeypatch, path, mutate)
    with pytest.raises(GateError, match="inventory_file_changed:sample.bin"):
        filemap(tmp_path, max_bytes=4 * 1024 * 1024)
    assert changed["mutated"]


@pytest.mark.parametrize("replacement", ["regular", "directory", "symlink", "fifo"])
def test_substitution_before_open_is_refused(tmp_path, monkeypatch, replacement):
    if replacement == "fifo" and not hasattr(os, "mkfifo"):
        pytest.skip("FIFO fixture requires POSIX")
    path = tmp_path / "sample.bin"
    path.write_bytes(b"original")
    destination = tmp_path / "other.bin"
    destination.write_bytes(b"different")

    def substitute():
        if replacement == "regular":
            # Keep the old inode allocated: immediate unlink/recreate can reuse
            # its inode and indistinguishable timestamp on fast filesystems.
            path.rename(tmp_path / "original-held.bin")
            path.write_bytes(b"original")
        else:
            path.unlink()
        if replacement == "directory":
            path.mkdir()
        elif replacement == "symlink":
            path.symlink_to(destination.name)
        else:
            os.mkfifo(path)
            # Fail the regression promptly if NONBLOCK is ever removed; do not
            # hang the test process while opening a FIFO without a writer.
            assert flags[0] & os.O_NONBLOCK

    flags = _mutate_before_open(monkeypatch, path, substitute)
    with pytest.raises(GateError, match="(inventory_file_changed|regular_inventory_file_required):sample.bin"):
        filemap(tmp_path)
    assert flags


def test_descriptor_is_closed_after_read_failure(tmp_path, monkeypatch):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"original")
    descriptors = []

    def fail(fd, count):
        descriptors.append(fd)
        raise OSError("synthetic read failure")

    monkeypatch.setattr(safeio.os, "read", fail)
    with pytest.raises(OSError, match="synthetic read failure"):
        filemap(tmp_path)
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(descriptors[0])
