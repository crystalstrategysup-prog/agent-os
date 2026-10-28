"""Metadata-only attestation for project source directory aliases; never follow them."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from .safeio import GateError, sha

MAX_GIT_METADATA = 4 * 1024 * 1024
MAX_LINK_BYTES = 4096


def _git(root: Path, *args: str) -> bytes:
    # No inherited alternate index/repository, global config, optional index
    # writes or fsmonitor command. These plumbing reads run no filters/hooks.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0"
    )
    try:
        process = subprocess.Popen(
            [
                "git",
                "--no-optional-locks",
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(root),
                *args,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except OSError as exc:
        raise GateError("tracked_symlink_git_unavailable") from exc
    timer = threading.Timer(5, process.kill)
    timer.daemon = True
    timer.start()
    try:
        output = process.stdout.read(MAX_GIT_METADATA + 1)
        if len(output) > MAX_GIT_METADATA:
            raise GateError("tracked_symlink_git_metadata_limit")
        if process.wait(timeout=1) != 0:
            raise GateError("tracked_symlink_git_read_failed")
        return output
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError("tracked_symlink_git_read_failed") from exc
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=1)
        process.stdout.close()


def _entries(root: Path, rel: str) -> list[tuple[bytes, bytes, bytes, bytes]]:
    output = _git(root, "ls-files", "--stage", "-z", "--", ":(literal)" + rel)
    entries = []
    for row in output.split(b"\0"):
        if not row:
            continue
        try:
            fields, path = row.split(b"\t", 1)
            mode, oid, stage = fields.split(b" ")
        except ValueError as exc:
            raise GateError("tracked_symlink_index_invalid") from exc
        if len(oid) not in (40, 64) or any(c not in b"0123456789abcdef" for c in oid):
            raise GateError("tracked_symlink_index_invalid")
        entries.append((mode, oid, stage, path))
    return entries


def _chain(root: Path, parts: tuple[str, ...]) -> list[tuple[Path, tuple[int, ...]]]:
    identities = []
    current = root
    for part in (None, *parts):
        if part is not None:
            current = current / part
        metadata = current.lstat()
        if not stat.S_ISDIR(metadata.st_mode):
            raise GateError("tracked_symlink_directory_chain_required")
        identities.append(
            (current, (metadata.st_dev, metadata.st_ino, metadata.st_mode))
        )
    return identities


def _link_state(path: Path) -> tuple[tuple[int, ...], bytes]:
    before = path.lstat()
    if not stat.S_ISLNK(before.st_mode):
        raise GateError("tracked_symlink_identity_changed")
    target = os.readlink(os.fsencode(path))
    after = path.lstat()

    def identity(s):
        return (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

    if identity(before) != identity(after):
        raise GateError("tracked_symlink_identity_changed")
    if not target or len(target) > MAX_LINK_BYTES:
        raise GateError("tracked_symlink_target_invalid")
    return identity(after), target


def attest_directory_link(
    root: Path, path: Path, excluded: set[str]
) -> tuple[dict, Callable[[], None]]:
    """Attest a tracked owning-repo link or exact sibling checkout alias; no walk."""
    try:
        rel = path.relative_to(root).as_posix()
        parents = _chain(root, path.parent.relative_to(root).parts)
        link_identity, target_bytes = _link_state(path)
        try:
            target = target_bytes.decode("utf-8")
        except UnicodeError as exc:
            raise GateError("tracked_symlink_target_invalid") from exc
        raw = PurePosixPath(target)
        if raw.is_absolute() or "\\" in target or "\x00" in target:
            raise GateError("tracked_symlink_relative_target_required")
        parts = list(path.parent.relative_to(root).parts)
        visited = list(parents)
        for part in raw.parts:
            if part == "..":
                if not parts:
                    raise GateError("tracked_symlink_target_escape")
                parts.pop()
            elif part != ".":
                parts.append(part)
            if any(p in excluded or p.endswith(".egg-info") for p in parts) or parts[
                :2
            ] == ["docs", "agentos"]:
                raise GateError("tracked_symlink_excluded_target")
            # Check each lexical step before a later '..' can cancel it.
            # A/../B is unsafe when A is a symlink, even if B is internal.
            visited.extend(_chain(root, tuple(parts)))
        if (
            not parts
            or any(p in excluded or p.endswith(".egg-info") for p in parts)
            or parts[:2] == ["docs", "agentos"]
        ):
            raise GateError("tracked_symlink_excluded_target")
        referent = _chain(root, tuple(parts))
        target_rel = PurePosixPath(*parts).as_posix()
        # Git ownership belongs to the link's actual parent, not necessarily
        # the admitted project directory. Never search through a link itself.
        try:
            owner = Path(os.fsdecode(_git(path.parent, "rev-parse", "--show-toplevel").rstrip(b"\n")))
        except GateError as exc:
            if str(exc) != "tracked_symlink_git_read_failed":
                raise
            owner = None
        if owner is None:
            # A checkout alias is metadata only: the real checkout is scanned
            # under its canonical directory elsewhere in the same source root.
            # Ordinary untracked directory aliases remain refused.
            target_path = root / target_rel
            actual = os.fsdecode(_git(target_path, "rev-parse", "--show-toplevel").rstrip(b"\n"))
            if actual != str(target_path) or target_path == root or path.parent != target_path.parent:
                raise GateError("tracked_symlink_stage0_link_required")
            head = _git(target_path, "rev-parse", "--verify", "HEAD")
            index = _git(target_path, "ls-files", "--stage", "-z")
            if not index or any(row.split(b"\t", 1)[0].split(b" ")[-1] != b"0" for row in index.split(b"\0") if row):
                raise GateError("tracked_symlink_stage0_link_required")
            def recheck_checkout() -> None:
                if _link_state(path) != (link_identity, target_bytes):
                    raise GateError("tracked_symlink_identity_changed")
                for item, identity in visited + referent:
                    m = item.lstat()
                    if (m.st_dev, m.st_ino, m.st_mode) != identity:
                        raise GateError("tracked_symlink_identity_changed")
                if (os.fsdecode(_git(target_path, "rev-parse", "--show-toplevel").rstrip(b"\n")) != actual
                    or _git(target_path, "rev-parse", "--verify", "HEAD") != head
                    or _git(target_path, "ls-files", "--stage", "-z") != index):
                    raise GateError("tracked_symlink_index_changed")
            recheck_checkout()
            return {"kind": "internal_git_checkout_alias/v1", "target": target,
                    "target_path": target_rel, "link_sha256": sha(target_bytes),
                    "git_head": head.decode().strip(), "git_index_sha256": sha(index)}, recheck_checkout
        try:
            owner.relative_to(root)
            git_rel = path.relative_to(owner).as_posix()
            git_target_rel = (root / target_rel).relative_to(owner).as_posix()
        except ValueError as exc:
            raise GateError("tracked_symlink_target_escape") from exc
        lexical = list(path.parent.relative_to(owner).parts)
        for part in raw.parts:
            if part == "..":
                if not lexical:
                    raise GateError("tracked_symlink_target_escape")
                lexical.pop()
            elif part != ".":
                lexical.append(part)
        owner_chain = _chain(root, owner.relative_to(root).parts)
        entries = _entries(owner, git_rel)
        if (
            len(entries) != 1
            or entries[0][0] != b"120000"
            or entries[0][2:] != (b"0", os.fsencode(git_rel))
        ):
            raise GateError("tracked_symlink_stage0_link_required")
        oid = entries[0][1]
        blob = b"blob " + str(len(target_bytes)).encode() + b"\0" + target_bytes
        actual_oid = (
            (hashlib.sha1(blob) if len(oid) == 40 else hashlib.sha256(blob))
            .hexdigest()
            .encode()
        )
        if actual_oid != oid:
            raise GateError("tracked_symlink_index_target_mismatch")
        target_entries = _entries(owner, git_target_rel)
        prefix = os.fsencode(git_target_rel) + b"/"
        if (
            not target_entries
            or any(
                stage != b"0" or not name.startswith(prefix)
                for _, _, stage, name in target_entries
            )
            or not any(
                mode in (b"100644", b"100755") for mode, _, _, _ in target_entries
            )
        ):
            raise GateError("tracked_symlink_tracked_directory_required")

        def recheck() -> None:
            try:
                if _link_state(path) != (link_identity, target_bytes):
                    raise GateError("tracked_symlink_identity_changed")
                for item, identity in visited + referent + owner_chain:
                    metadata = item.lstat()
                    if (metadata.st_dev, metadata.st_ino, metadata.st_mode) != identity:
                        raise GateError("tracked_symlink_identity_changed")
                if (
                    os.fsdecode(_git(path.parent, "rev-parse", "--show-toplevel").rstrip(b"\n")) != str(owner)
                    or _entries(owner, git_rel) != entries
                    or _entries(owner, git_target_rel) != target_entries
                ):
                    raise GateError("tracked_symlink_index_changed")
            except OSError as exc:
                raise GateError("tracked_symlink_identity_changed") from exc

        recheck()
        return {
            "kind": "tracked_internal_directory_symlink/v1",
            "target": target,
            "target_path": target_rel,
            **({"git_root": owner.relative_to(root).as_posix()} if owner != root else {}),
            "git_mode": "120000",
            "git_blob_oid": oid.decode(),
            "link_sha256": sha(target_bytes),
        }, recheck
    except OSError as exc:
        raise GateError("tracked_symlink_target_unavailable") from exc
