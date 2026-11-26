"""Bounded, read-only resource observations; no resource lifecycle authority.

Descriptors are caller declarations, not an ownership registry or a reservation.
Only explicitly named metadata is read. Nothing here walks a tree, writes state,
opens resource contents, stops a process, or authorizes physical cleanup. Even a
candidate needs separate qualification of its actual writers, tree and recovery.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import errno
import json
import os
import re
import stat
import sys

from . import __version__
from .safeio import GateError, now, sha

REQUEST_SCHEMA = "agentos.resource-observation-request/v1"
PLAN_SCHEMA = "agentos.resource-observation-plan/v1"
MAX_INPUT_BYTES = 256 * 1024
MAX_ROOTS = 16
MAX_RESOURCES = 128
MAX_CAPACITY = 16
MAX_RESERVATIONS = 128
MAX_INTEGER = 2**63 - 1
MAX_ROOT_PATH_BYTES = 4096
MAX_RELATIVE_NAME_BYTES = 1024
ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}"
CLASSES = frozenset({
    "reproducible-temporary", "build-output", "private-cache", "shared-cache",
    "test-database", "temporary-backup", "durable-backup", "accepted-checkpoint",
    "deliverable", "journal", "unknown",
})
RETENTION_REASONS = frozenset({
    "ROLLBACK_WINDOW", "ACCEPTED_HISTORY", "UNIQUE_DATA", "LIVE_CONSUMER",
    "UNKNOWN_OPERATION", "OTHER_DECLARED",
})
_CANDIDATE_CLASSES = {"build-output", "test-database"}
_PROTECTED_CLASSES = {
    "temporary-backup", "durable-backup", "accepted-checkpoint", "deliverable",
    "journal", "shared-cache",
}
_LOCAL_FS = {"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "overlay"}
_MEMORY_FS = {"tmpfs", "ramfs"}
_NETWORK_FS = {"nfs", "nfs4", "cifs", "smb3", "9p", "ceph", "fuse.sshfs"}
_PSEUDO_FS = {"proc", "sysfs", "devtmpfs", "devpts", "cgroup", "cgroup2"}


def _refuse(code: str = "invalid_input") -> None:
    # Never incorporate a key, path, exception string or descriptor into errors.
    raise GateError("resource_observation_" + code)


def _object(value: object, fields: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        _refuse()
    return value


def _identifier(value: object, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or re.fullmatch(ID_PATTERN, value) is None:
        _refuse("invalid_identifier")
    return value


def _enum(value: object, choices: set[str] | frozenset[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        _refuse()
    return value


def _number(value: object, *, nullable: bool = False) -> int | None:
    if nullable and value is None:
        return None
    if type(value) is not int or not 0 <= value <= MAX_INTEGER:
        _refuse("invalid_quantity")
    return value


def _quantities(value: object, *, nullable: bool = False) -> dict:
    value = _object(value, {"bytes", "inodes"})
    return {key: _number(value[key], nullable=nullable) for key in ("bytes", "inodes")}


def _path(value: object, *, root: bool) -> str:
    limit = MAX_ROOT_PATH_BYTES if root else MAX_RELATIVE_NAME_BYTES
    if (not isinstance(value, str) or not value or "\x00" in value or "\\" in value
            or len(value.encode("utf-8")) > limit):
        _refuse("invalid_path")
    parts = value.split("/")
    if root:
        if not value.startswith("/"):
            _refuse("invalid_path")
        parts = parts[1:]
        if value == "/":
            parts = []
    elif value.startswith("/"):
        _refuse("invalid_path")
    if any(part in {"", ".", ".."} for part in parts):
        _refuse("invalid_path")
    return value


def _retention(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        _refuse("invalid_retention")
    fields = set(value)
    if fields not in ({"owner_id", "reason_code", "next_review"},
                      {"owner_id", "reason_code", "release_event_id"}):
        _refuse("invalid_retention")
    result = {"owner_id": _identifier(value["owner_id"]),
              "reason_code": _enum(value["reason_code"], RETENTION_REASONS)}
    if "release_event_id" in value:
        result["release_event_id"] = _identifier(value["release_event_id"])
    else:
        timestamp = value["next_review"]
        if not isinstance(timestamp, str) or len(timestamp) > 40:
            _refuse("invalid_retention")
        try:
            parsed = datetime.fromisoformat(timestamp)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                _refuse("invalid_retention")
        except ValueError:
            _refuse("invalid_retention")
        # Canonical time avoids echoing a caller-controlled ISO separator.
        result["next_review"] = parsed.isoformat()
    return result


def _normalize(payload: object) -> dict:
    try:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError, UnicodeError):
        _refuse()
    if len(encoded) > MAX_INPUT_BYTES:
        _refuse("input_size_limit")
    payload = _object(payload, {"schema", "project_id", "task_id", "run_id",
                                "operation_id", "roots", "resources", "capacity"})
    if payload["schema"] != REQUEST_SCHEMA:
        _refuse("unsupported_schema")
    result = {key: _identifier(payload[key])
              for key in ("project_id", "task_id", "run_id", "operation_id")}
    for key, lower, upper in (("roots", 1, MAX_ROOTS),
                              ("resources", 0, MAX_RESOURCES),
                              ("capacity", 0, MAX_CAPACITY)):
        if not isinstance(payload[key], list) or not lower <= len(payload[key]) <= upper:
            _refuse("item_limit")
    roots, root_ids = [], set()
    for raw in payload["roots"]:
        raw = _object(raw, {"admitted_root_id", "path"})
        identity = _identifier(raw["admitted_root_id"])
        if identity in root_ids:
            _refuse("duplicate_identifier")
        root_ids.add(identity)
        roots.append({"admitted_root_id": identity, "path": _path(raw["path"], root=True)})
    result["roots"] = roots
    resources, resource_ids = [], set()
    for raw in payload["resources"]:
        raw = _object(raw, {"resource_id", "admitted_root_id", "relative_name", "class",
                            "owner_id", "origin", "reproducible", "inputs_ref",
                            "process_state", "dependencies", "release_condition", "retention"})
        identity = _identifier(raw["resource_id"])
        root_id = _identifier(raw["admitted_root_id"])
        if identity in resource_ids or root_id not in root_ids:
            _refuse("invalid_reference")
        resource_ids.add(identity)
        if raw["reproducible"] is not None and type(raw["reproducible"]) is not bool:
            _refuse()
        resources.append({
            "resource_id": identity, "admitted_root_id": root_id,
            "relative_name": _path(raw["relative_name"], root=False),
            "class": _enum(raw["class"], CLASSES),
            "owner_id": _identifier(raw["owner_id"], nullable=True),
            "origin": _enum(raw["origin"], {"DECLARED_RUN", "UNKNOWN"}),
            "reproducible": raw["reproducible"],
            "inputs_ref": _identifier(raw["inputs_ref"], nullable=True),
            "process_state": _enum(raw["process_state"], {"STOPPED", "ACTIVE", "UNKNOWN"}),
            "dependencies": _enum(raw["dependencies"], {"CLEAR", "ACTIVE", "UNKNOWN"}),
            "release_condition": _enum(raw["release_condition"], {"SATISFIED", "OPEN", "UNKNOWN"}),
            "retention": _retention(raw["retention"]),
        })
    result["resources"] = resources
    capacity, budget_roots = [], set()
    for raw in payload["capacity"]:
        raw = _object(raw, {"admitted_root_id", "remaining_peak", "headroom",
                            "unconsumed_reservations", "quota"})
        root_id = _identifier(raw["admitted_root_id"])
        if root_id not in root_ids or root_id in budget_roots:
            _refuse("invalid_reference")
        budget_roots.add(root_id)
        reservations = raw["unconsumed_reservations"]
        if not isinstance(reservations, list) or len(reservations) > MAX_RESERVATIONS:
            _refuse("item_limit")
        normalized, reservation_ids = [], set()
        for item in reservations:
            item = _object(item, {"reservation_id", "bytes", "inodes"})
            identity = _identifier(item["reservation_id"])
            if identity in reservation_ids:
                _refuse("duplicate_identifier")
            reservation_ids.add(identity)
            normalized.append({"reservation_id": identity,
                               "bytes": _number(item["bytes"]),
                               "inodes": _number(item["inodes"])})
        quota = _object(raw["quota"], {"status", "required", "available_bytes", "available_inodes"})
        status = _enum(quota["status"], {"UNKNOWN", "NOT_APPLICABLE", "DECLARED"})
        if type(quota["required"]) is not bool:
            _refuse()
        quota = {"status": status, "required": quota["required"],
                 "available_bytes": _number(quota["available_bytes"], nullable=True),
                 "available_inodes": _number(quota["available_inodes"], nullable=True)}
        if (status != "DECLARED"
                and any(quota[key] is not None for key in ("available_bytes", "available_inodes"))):
            _refuse("invalid_quota")
        capacity.append({"admitted_root_id": root_id,
                         "remaining_peak": _quantities(raw["remaining_peak"], nullable=True),
                         "headroom": _quantities(raw["headroom"], nullable=True),
                         "unconsumed_reservations": normalized, "quota": quota})
    result["capacity"] = capacity
    return result


class _ObservationError(Exception):
    """Internal static reason; OS exception text must never reach the result."""


def _os_reason(exc: OSError) -> str:
    return {errno.ENOENT: "MISSING", errno.EACCES: "INACCESSIBLE",
            errno.EPERM: "INACCESSIBLE", errno.ELOOP: "SYMLINK",
            errno.ENOTDIR: "NOT_DIRECTORY"}.get(exc.errno, "FILESYSTEM_UNKNOWN")


def _identity(info: os.stat_result) -> dict:
    kind = ("DIRECTORY" if stat.S_ISDIR(info.st_mode) else
            "REGULAR_FILE" if stat.S_ISREG(info.st_mode) else
            "SYMLINK" if stat.S_ISLNK(info.st_mode) else "SPECIAL")
    return {"type": kind, "dev": info.st_dev, "inode": info.st_ino,
            "uid": info.st_uid, "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode),
            "nlink": info.st_nlink, "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino, left.st_mode, left.st_ctime_ns) == (
        right.st_dev, right.st_ino, right.st_mode, right.st_ctime_ns)


def _open_directory(parent: int, name: str) -> int:
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if stat.S_ISLNK(info.st_mode):
        raise _ObservationError("SYMLINK")
    if not stat.S_ISDIR(info.st_mode):
        raise _ObservationError("NOT_DIRECTORY")
    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    if not _same_identity(info, os.fstat(child)):
        os.close(child)
        raise _ObservationError("IDENTITY_CHANGED")
    return child


def _open_root(path: str) -> int:
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_DIRECTORY") or os.open not in os.supports_dir_fd):
        raise _ObservationError("PLATFORM_PROFILE_UNQUALIFIED")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.split("/")[1:]:
            if part:
                child = _open_directory(fd, part)
                os.close(fd)
                fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _mount_table() -> tuple[int | None, dict[int, str]]:
    if not sys.platform.startswith("linux"):
        return None, {}
    try:
        namespace = os.stat("/proc/self/ns/mnt").st_ino
        with open("/proc/self/mountinfo", "rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            return None, {}
        result = {}
        for line in data.splitlines():
            left, right = line.split(b" - ", 1)
            mount_id = int(left.split(b" ", 1)[0])
            filesystem = right.split(b" ", 1)[0].decode("ascii")
            # Mount paths/source names are deliberately discarded, never echoed.
            known = _LOCAL_FS | _MEMORY_FS | _NETWORK_FS | _PSEUDO_FS
            result[mount_id] = filesystem if filesystem in known else "UNKNOWN"
        return namespace, result
    except (OSError, ValueError, UnicodeError):
        return None, {}


def _unknown_mount() -> dict:
    return {"status": "UNKNOWN", "namespace_inode": None, "mount_id": None,
            "filesystem_type": "UNKNOWN", "filesystem_scope": "UNKNOWN"}


def _mount_identity(fd: int, table: tuple[int | None, dict[int, str]]) -> dict:
    namespace, entries = table
    if namespace is None:
        return _unknown_mount()
    try:
        with open(f"/proc/self/fdinfo/{fd}", "rb") as stream:
            data = stream.read(4097)
        if len(data) > 4096:
            return _unknown_mount()
        found = [int(line.split(b":", 1)[1]) for line in data.splitlines()
                 if line.startswith(b"mnt_id:")]
        if len(found) != 1 or found[0] not in entries:
            return _unknown_mount()
        filesystem = entries[found[0]]
        scope = ("LOCAL" if filesystem in _LOCAL_FS else
                 "MEMORY" if filesystem in _MEMORY_FS else
                 "NETWORK" if filesystem in _NETWORK_FS else
                 "PSEUDO" if filesystem in _PSEUDO_FS else "UNKNOWN")
        return {"status": "OBSERVED", "namespace_inode": namespace, "mount_id": found[0],
                "filesystem_type": filesystem, "filesystem_scope": scope}
    except (OSError, ValueError):
        return _unknown_mount()


def _physical_snapshot(fd: int) -> dict:
    result = {"status": "UNKNOWN", "source": "UNKNOWN", "available_bytes": None,
              "available_inodes": None, "total_bytes": None, "total_inodes": None}
    try:
        info = os.fstatvfs(fd)
        block = info.f_frsize or info.f_bsize
        if block <= 0 or not 0 <= info.f_bavail <= info.f_blocks:
            return result
        result.update(status="OBSERVED", source="STATVFS",
                      available_bytes=info.f_bavail * block, total_bytes=info.f_blocks * block)
        # Filesystems reporting no inode accounting have UNKNOWN, not zero capacity.
        if info.f_files > 0 and 0 <= info.f_favail <= info.f_files:
            result.update(available_inodes=info.f_favail, total_inodes=info.f_files)
    except (OSError, AttributeError, OverflowError):
        pass
    return result


def _root_observation(raw: dict, table: tuple) -> tuple[dict, dict, int | None]:
    row = {"admitted_root_id": raw["admitted_root_id"], "observation_status": "UNKNOWN",
           "identity": None, "mount": _unknown_mount(), "volume_id": None,
           "private_owner": None, "reasons": []}
    physical = {"status": "UNKNOWN", "source": "UNKNOWN", "available_bytes": None,
                "available_inodes": None, "total_bytes": None, "total_inodes": None}
    fd = None
    try:
        fd = _open_root(raw["path"])
        info = os.fstat(fd)
        row.update(observation_status="OBSERVED", identity=_identity(info),
                   mount=_mount_identity(fd, table),
                   volume_id="volume-" + sha(f"local-device:{info.st_dev}".encode())[:20],
                   private_owner=info.st_uid == os.geteuid() and not (info.st_mode & 0o077))
        physical = _physical_snapshot(fd)
        if not row["private_owner"]:
            row["reasons"].append("ROOT_NOT_PRIVATE_OWNER")
        if row["mount"]["status"] != "OBSERVED":
            row["reasons"].append("MOUNT_IDENTITY_UNKNOWN")
        if row["mount"]["filesystem_scope"] not in {"LOCAL", "MEMORY"}:
            row["reasons"].append("FILESYSTEM_PROFILE_UNQUALIFIED")
    except _ObservationError as exc:
        row["reasons"].append(str(exc))
    except OSError as exc:
        row["reasons"].append(_os_reason(exc))
    return row, physical, fd


def _resource_metadata(root_fd: int, relative: str, table: tuple) -> tuple[dict, dict, dict, list[str]]:
    fd = os.dup(root_fd)
    try:
        parts = relative.split("/")
        for part in parts[:-1]:
            child = _open_directory(fd, part)
            os.close(fd)
            fd = child
        info = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
        identity = _identity(info)
        size = {"logical_bytes": None, "allocated_bytes": None,
                "tree_bytes": None, "source": "NOT_MEASURED"}
        if stat.S_ISLNK(info.st_mode):
            return identity, _unknown_mount(), size, ["SYMLINK"]
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            return identity, _unknown_mount(), size, ["SPECIAL_FILE"]
        reasons = []
        if sys.platform.startswith("linux") and hasattr(os, "O_PATH"):
            flags = os.O_PATH | os.O_NOFOLLOW
        elif stat.S_ISDIR(info.st_mode):
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        else:
            # O_RDONLY could open a substituted device between lstat and open.
            # Without a metadata-only handle, retain a point-in-time lstat only.
            flags = None
        if flags is None:
            mount = _unknown_mount()
            reasons.append("METADATA_HANDLE_UNAVAILABLE")
        else:
            child = os.open(parts[-1], flags, dir_fd=fd)
            try:
                current = os.fstat(child)
                if not _same_identity(info, current):
                    raise _ObservationError("IDENTITY_CHANGED")
                mount = _mount_identity(child, table)
            finally:
                os.close(child)
        if stat.S_ISREG(info.st_mode):
            size.update(logical_bytes=info.st_size, source="FILE_METADATA",
                        allocated_bytes=getattr(info, "st_blocks", 0) * 512
                        if hasattr(info, "st_blocks") else None)
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            reasons.append("HARDLINK_OR_UNLINKED")
        if info.st_uid != os.geteuid():
            reasons.append("FILESYSTEM_OWNER_MISMATCH")
        return identity, mount, size, reasons
    finally:
        os.close(fd)


def _resource_observation(raw: dict, root: dict, fd: int | None, table: tuple) -> dict:
    declaration_keys = ("owner_id", "origin", "reproducible", "inputs_ref",
                        "process_state", "dependencies", "release_condition")
    row = {key: raw[key] for key in ("resource_id", "admitted_root_id", "class", "retention")}
    row.update(declarations={"source": "CALLER_DECLARED",
                             **{key: raw[key] for key in declaration_keys}},
               identity=None, mount=_unknown_mount(),
               size={"logical_bytes": None, "allocated_bytes": None,
                     "tree_bytes": None, "source": "NOT_MEASURED"},
               status="HOLD", reasons=[], next_action="RESOLVE_HOLD",
               recursive_inventory="NOT_PERFORMED", deletion_authorized=False)
    holds = list(root["reasons"])
    if fd is None:
        holds.append("ROOT_UNOBSERVED")
    else:
        try:
            identity, mount, size, reasons = _resource_metadata(fd, raw["relative_name"], table)
            row.update(identity=identity, mount=mount, size=size)
            holds.extend(reasons)
            if mount["status"] != "OBSERVED":
                holds.append("MOUNT_IDENTITY_UNKNOWN")
            elif (mount["namespace_inode"], mount["mount_id"]) != (
                    root["mount"]["namespace_inode"], root["mount"]["mount_id"]):
                holds.append("NESTED_MOUNT")
        except _ObservationError as exc:
            holds.append(str(exc))
        except OSError as exc:
            holds.append(_os_reason(exc))
    for condition, reason in (
        (raw["owner_id"] is None, "OWNER_UNKNOWN"),
        (raw["origin"] != "DECLARED_RUN", "ORIGIN_UNKNOWN"),
        (raw["class"] == "unknown", "CLASS_UNKNOWN"),
        (raw["process_state"] != "STOPPED", "PROCESS_" + raw["process_state"]),
        (raw["dependencies"] != "CLEAR", "DEPENDENCIES_" + raw["dependencies"]),
        (raw["release_condition"] != "SATISFIED", "RELEASE_" + raw["release_condition"]),
        (raw["reproducible"] is None, "REPRODUCTION_UNKNOWN"),
        (raw["reproducible"] is True and raw["inputs_ref"] is None, "REPRODUCTION_INPUTS_UNKNOWN"),
    ):
        if condition:
            holds.append(reason)
    if holds:
        row["reasons"] = sorted(set(holds))
    elif raw["retention"] is not None:
        row.update(status="RETAINED", reasons=["RETENTION_DECLARED"], next_action="REVIEW_RETENTION")
    elif raw["reproducible"] is False:
        row.update(status="RETAINED", reasons=["NON_REPRODUCIBLE"], next_action="PRESERVE_UNIQUE_DATA")
    elif raw["class"] in _PROTECTED_CLASSES:
        row.update(status="RETAINED", reasons=["PROTECTED_CLASS"], next_action="DEFINE_RETENTION")
    elif raw["class"] not in _CANDIDATE_CLASSES:
        row.update(status="RETAINED", reasons=["CLASS_PROFILE_UNQUALIFIED"], next_action="QUALIFY_PROFILE")
    else:
        row.update(status="CANDIDATE_FOR_QUALIFICATION", reasons=["DECLARED_CONDITIONS_ONLY"],
                   next_action="QUALIFY_TREE_WRITERS_AND_RECOVERY")
    return row


def _sum_known(values: list[int | None]) -> int | None:
    return None if any(value is None for value in values) else sum(values)


def _volume_plan(volume_id: str, roots: list[dict], physical: dict, budgets: list[dict]) -> dict:
    # Root aliases share one physical pool. They never multiply its availability.
    samples = [physical[row["admitted_root_id"]] for row in roots]
    snapshot = {"status": "OBSERVED", "source": "STATVFS", "samples": len(samples)}
    for key in ("available_bytes", "available_inodes", "total_bytes", "total_inodes"):
        values = [sample[key] for sample in samples]
        snapshot[key] = min(values) if all(value is not None for value in values) else None
    if any(sample["status"] != "OBSERVED" for sample in samples):
        snapshot.update(status="UNKNOWN", source="UNKNOWN")
    reasons = []
    reservations = {}
    for budget in budgets:
        for reservation in budget["unconsumed_reservations"]:
            key = reservation["reservation_id"]
            if key in reservations and reservations[key] != reservation:
                reasons.append("RESERVATION_CONFLICT")
            reservations[key] = reservation
    quota = budgets[0]["quota"] if budgets else {
        "status": "UNKNOWN", "required": True, "available_bytes": None, "available_inodes": None}
    if any(budget["quota"] != quota for budget in budgets):
        reasons.append("QUOTA_CONFLICT")
    if not budgets:
        reasons.append("BUDGET_NOT_DECLARED")
    peak, headroom, reserved, dimensions = {}, {}, {}, {}
    for dimension in ("bytes", "inodes"):
        peak[dimension] = _sum_known([b["remaining_peak"][dimension] for b in budgets]) if budgets else None
        values = [b["headroom"][dimension] for b in budgets]
        headroom[dimension] = max(values) if values and all(v is not None for v in values) else None
        reserved[dimension] = sum(item[dimension] for item in reservations.values())
        available = snapshot["available_" + dimension]
        quota_available = quota["available_" + dimension]
        if quota["status"] == "DECLARED" and quota_available is not None:
            available = min(available, quota_available) if available is not None else quota_available
        after = None if available is None or headroom[dimension] is None else (
            available - headroom[dimension] - reserved[dimension])
        # Known insufficiency stays useful even if another required limit is unknown.
        status = "UNKNOWN"
        if after is not None and peak[dimension] is not None:
            status = "INSUFFICIENT" if after < peak[dimension] else "FITS_REPORTED_VALUES"
        required_unknown = (quota["required"] and
                            (quota["status"] == "UNKNOWN" or
                             (quota["status"] == "DECLARED" and quota_available is None)))
        if status == "FITS_REPORTED_VALUES" and (required_unknown or snapshot["available_" + dimension] is None):
            status = "UNKNOWN"
        if reasons:
            status = "UNKNOWN"
        dimensions[dimension] = {"status": status, "available_after_allowances": after,
                                 "required_remaining_peak": peak[dimension]}
    statuses = {item["status"] for item in dimensions.values()}
    status = ("INSUFFICIENT" if "INSUFFICIENT" in statuses else
              "FITS_REPORTED_VALUES" if statuses == {"FITS_REPORTED_VALUES"} else "UNKNOWN")
    if quota["status"] == "UNKNOWN":
        reasons.append("QUOTA_UNKNOWN")
    if any(value["status"] == "UNKNOWN" for value in dimensions.values()):
        reasons.append("CAPACITY_INCOMPLETE")
    return {
        "volume_id": volume_id, "admitted_root_ids": [row["admitted_root_id"] for row in roots],
        "physical": snapshot,
        "declared": {"source": "CALLER_DECLARED", "remaining_peak": peak,
                     "headroom": headroom, "unconsumed_reserved": reserved,
                     "reservation_ids": sorted(reservations), "quota": dict(quota)},
        "assessment": {"status": status, **dimensions, "reasons": sorted(set(reasons)),
                       "scope": "SNAPSHOT_ARITHMETIC_ONLY"},
        "admission_granted": False,
    }


def observe_plan(payload: dict) -> dict:
    """Observe explicit metadata and report a conservative plan without effects.

    IDs are public-safe opaque references supplied by the caller. Private root
    mappings and relative filenames are never returned, including on errors.
    Physical snapshots include current writes already: remaining_peak and
    unconsumed reservations mean additional, not total, future usage.
    """
    normalized = _normalize(payload)
    table = _mount_table()
    roots, physical, descriptors = [], {}, {}
    try:
        for raw in normalized["roots"]:
            row, snapshot, fd = _root_observation(raw, table)
            roots.append(row)
            physical[raw["admitted_root_id"]] = snapshot
            descriptors[raw["admitted_root_id"]] = fd
        by_root = {row["admitted_root_id"]: row for row in roots}
        resources = [_resource_observation(raw, by_root[raw["admitted_root_id"]],
                                          descriptors[raw["admitted_root_id"]], table)
                     for raw in normalized["resources"]]
        groups = defaultdict(list)
        for row in roots:
            # Missing roots cannot be assumed to share a filesystem.
            identity = row["volume_id"] or "unknown-" + row["admitted_root_id"]
            groups[identity].append(row)
        volumes = []
        for identity, group in groups.items():
            ids = {row["admitted_root_id"] for row in group}
            budgets = [budget for budget in normalized["capacity"] if budget["admitted_root_id"] in ids]
            volumes.append(_volume_plan(identity, group, physical, budgets))
        return {
            "schema": PLAN_SCHEMA, "status": "OBSERVATION_ONLY", "version": __version__,
            "observed_at": now(),
            **{key: normalized[key] for key in ("project_id", "task_id", "run_id", "operation_id")},
            "roots": roots, "resources": resources, "volumes": volumes,
            "effects": "NONE", "physical_cleanup_supported": False,
            "reservation_supported": False, "apply_supported": False,
            "admission_granted": False, "authority_granted": False,
            "task_mutation": False, "native_hooks": "DISABLED",
        }
    finally:
        for fd in descriptors.values():
            if fd is not None:
                os.close(fd)
