"""Bounded, read-only inventory of registered AgentOS project knowledge."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

CATALOG_SCHEMA = "agent-os.full-inventory-catalog/v1"
INVENTORY_SCHEMA = "agent-os.full-inventory/v1"
SELECTION_SCHEMA = "agent-os.full-inventory-selection/v1"
CLASSES = ("project", "roadmap", "skill", "problem", "host", "history")
MAX_CATALOG_BYTES = 1024 * 1024
DEFAULT_MAX_FILES = 4096
DEFAULT_MAX_BYTES = 64 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 8 * 1024 * 1024

_FIXED_ROOTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("skill", "knowledge/skills", (".md", ".json", ".yaml", ".yml")),
    ("skill", "skills", (".md", ".json", ".yaml", ".yml")),
    ("skill", "docs/runbooks", (".md", ".json", ".yaml", ".yml")),
    ("skill", "runbooks", (".md", ".json", ".yaml", ".yml")),
    ("problem", "knowledge/problems", (".md", ".json", ".yaml", ".yml")),
    ("host", "docs/host-overlays", (".md",)),
    ("host", "knowledge/hosts", (".md", ".json", ".yaml", ".yml")),
    ("host", "docs/fleet/passports", (".md", ".json")),
    ("history", "history", (".md", ".json", ".yaml", ".yml")),
    ("history", "artifacts/history", (".md", ".json", ".yaml", ".yml")),
)
_PROJECT_DOC_EXCLUDED = (
    "docs/runbooks/",
    "docs/host-overlays/",
    "docs/fleet/passports/",
    "docs/history/",
)


class FullInventoryError(ValueError):
    """A deterministic inventory contract violation."""


def write_result(path: Path, payload: dict[str, Any]) -> Path:
    """Atomically persist a non-secret inventory result with private permissions."""

    target = Path(path).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    parent = target.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        if parent.resolve(strict=True) != parent:
            raise FullInventoryError("inventory output parent must be canonical")
        if target.exists() or target.is_symlink():
            current = target.lstat()
            if not stat.S_ISREG(current.st_mode) or stat.S_ISLNK(current.st_mode):
                raise FullInventoryError("inventory output must be a regular non-symlink file")
    except OSError as exc:
        raise FullInventoryError("inventory output is unavailable") from exc
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        target.chmod(0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return target


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FullInventoryError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise FullInventoryError(f"nonfinite JSON value: {value}")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _read_bounded_json(path: Path, *, limit: int, label: str) -> dict[str, Any]:
    if not path.is_absolute():
        raise FullInventoryError(f"{label} path must be absolute")
    try:
        if path.resolve(strict=True) != path:
            raise FullInventoryError(f"{label} path must be canonical")
    except OSError as exc:
        raise FullInventoryError(f"{label} is unavailable") from exc
    try:
        before = path.lstat()
    except OSError as exc:
        raise FullInventoryError(f"{label} is unavailable") from exc
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise FullInventoryError(f"{label} must be a regular non-symlink file")
    if before.st_size <= 0 or before.st_size > limit:
        raise FullInventoryError(f"{label} size is invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise FullInventoryError(f"{label} changed while opening")
        raw = bytearray()
        while len(raw) < opened.st_size:
            block = os.read(descriptor, min(1024 * 1024, opened.st_size - len(raw)))
            if not block:
                raise FullInventoryError(f"{label} ended unexpectedly")
            raw.extend(block)
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ):
            raise FullInventoryError(f"{label} changed while reading")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(
            bytes(raw).decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FullInventoryError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise FullInventoryError(f"{label} must be a JSON object")
    return value


def _portable_relative(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise FullInventoryError(f"{label} is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise FullInventoryError(f"{label} must be a portable relative path")
    if len(value) > 512:
        raise FullInventoryError(f"{label} is too long")
    return path.as_posix()


def _canonical_root(value: Any) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise FullInventoryError("project root is invalid")
    root = Path(value)
    if not root.is_absolute():
        raise FullInventoryError("project root must be absolute")
    try:
        if stat.S_ISLNK(root.lstat().st_mode):
            raise FullInventoryError("project root must not be a symlink")
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise FullInventoryError("project root is unavailable") from exc
    if resolved != root or not resolved.is_dir():
        raise FullInventoryError("project root must be a canonical directory")
    return root


def _catalog_projects(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    if set(catalog) != {"schema", "catalog_id", "projects"}:
        raise FullInventoryError("catalog fields are invalid")
    if catalog.get("schema") != CATALOG_SCHEMA:
        raise FullInventoryError("catalog schema is unsupported")
    catalog_id = catalog.get("catalog_id")
    if not isinstance(catalog_id, str) or not catalog_id or len(catalog_id) > 128:
        raise FullInventoryError("catalog_id is invalid")
    rows = catalog.get("projects")
    if not isinstance(rows, list) or not rows or len(rows) > 256:
        raise FullInventoryError("catalog projects are invalid")
    seen: set[str] = set()
    seen_roots: set[Path] = set()
    result: list[dict[str, Any]] = []
    allowed = {"project_id", "host_id", "root", "policy_paths", "roadmap_paths", "enabled"}
    for row in rows:
        if not isinstance(row, dict) or not set(row) <= allowed:
            raise FullInventoryError("project entry fields are invalid")
        project_id = row.get("project_id")
        host_id = row.get("host_id")
        if (
            not isinstance(project_id, str)
            or not project_id
            or len(project_id) > 128
            or project_id in seen
        ):
            raise FullInventoryError("project_id is invalid or duplicated")
        if host_id is not None and (not isinstance(host_id, str) or not host_id or len(host_id) > 128):
            raise FullInventoryError("host_id is invalid")
        enabled = row.get("enabled", True)
        if not isinstance(enabled, bool):
            raise FullInventoryError("project enabled must be boolean")
        policy_paths = row.get("policy_paths", ["AGENTS.md"])
        roadmap_paths = row.get("roadmap_paths", ["ROADMAP.json"])
        if (
            not isinstance(policy_paths, list)
            or not 1 <= len(policy_paths) <= 32
            or not isinstance(roadmap_paths, list)
            or len(roadmap_paths) > 32
        ):
            raise FullInventoryError("project path lists are invalid")
        policies = [_portable_relative(value, label="policy path") for value in policy_paths]
        roadmaps = [_portable_relative(value, label="roadmap path") for value in roadmap_paths]
        if len(set(policies)) != len(policies) or len(set(roadmaps)) != len(roadmaps):
            raise FullInventoryError("project path lists contain duplicates")
        root_value = row.get("root")
        if enabled:
            project_root = _canonical_root(root_value)
            if project_root in seen_roots:
                raise FullInventoryError("enabled project root is duplicated")
            seen_roots.add(project_root)
        else:
            if not isinstance(root_value, str) or not root_value or "\x00" in root_value or not Path(root_value).is_absolute():
                raise FullInventoryError("disabled project root must be absolute")
            project_root = Path(root_value)
        result.append(
            {
                "project_id": project_id,
                "host_id": host_id,
                "root": project_root,
                "policy_paths": policies,
                "roadmap_paths": roadmaps,
                "enabled": enabled,
            }
        )
        seen.add(project_id)
    return result


def _ensure_components_safe(root: Path, relative: str) -> Path:
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        try:
            item = current.lstat()
        except OSError as exc:
            raise FullInventoryError("registered path became unavailable") from exc
        if stat.S_ISLNK(item.st_mode):
            raise FullInventoryError("registered path contains a symlink")
    return current


def _hash_file(root: Path, relative: str) -> tuple[str, int]:
    path = _ensure_components_safe(root, relative)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise FullInventoryError("knowledge artifact must be a single-link regular file")
    if before.st_size > MAX_SINGLE_FILE_BYTES:
        raise FullInventoryError("knowledge artifact exceeds the per-file bound")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        digest = hashlib.sha256()
        read = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            read += len(block)
        after = os.fstat(descriptor)
        identity = lambda item: (
            item.st_dev,
            item.st_ino,
            item.st_mode,
            item.st_nlink,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )
        if identity(opened) != identity(after) or read != opened.st_size:
            raise FullInventoryError("knowledge artifact changed while reading")
    finally:
        os.close(descriptor)
    return digest.hexdigest(), read


def _walk_fixed_root(root: Path, relative_root: str, suffixes: tuple[str, ...]) -> Iterable[str]:
    base = root / relative_root
    try:
        base_item = base.lstat()
    except FileNotFoundError:
        return ()
    except OSError as exc:
        raise FullInventoryError("canonical knowledge root is unavailable") from exc
    if stat.S_ISLNK(base_item.st_mode):
        raise FullInventoryError("canonical knowledge root contains a symlink")
    _ensure_components_safe(root, relative_root)
    if not stat.S_ISDIR(base_item.st_mode):
        raise FullInventoryError("canonical knowledge root is not a directory")
    found: list[str] = []
    for directory, dirnames, filenames in os.walk(base, topdown=True, followlinks=False):
        directory_path = Path(directory)
        safe_dirs: list[str] = []
        for name in sorted(dirnames):
            child = directory_path / name
            if child.is_symlink():
                raise FullInventoryError("canonical knowledge root contains a symlink")
            safe_dirs.append(name)
        dirnames[:] = safe_dirs
        for name in sorted(filenames):
            child = directory_path / name
            if child.is_symlink():
                raise FullInventoryError("canonical knowledge root contains a symlink")
            if child.suffix.lower() not in suffixes:
                continue
            found.append(child.relative_to(root).as_posix())
    return tuple(sorted(found))


def _project_doc_paths(root: Path) -> tuple[str, ...]:
    paths = _walk_fixed_root(root, "docs", (".md",))
    return tuple(
        path
        for path in paths
        if not any(path.casefold().startswith(prefix.casefold()) for prefix in _PROJECT_DOC_EXCLUDED)
    )


def _artifact_kind(knowledge_class: str, path: str) -> str:
    if knowledge_class == "project":
        return "project_policy" if PurePosixPath(path).name in {"AGENTS.md", "AGENTS.override.md"} else "project_document"
    return {
        "roadmap": "roadmap",
        "skill": "runbook" if "/runbooks/" in f"/{path}" else "skill",
        "problem": "problem_card",
        "host": "host_passport" if "HOST_PASSPORT" in path else "host_overlay",
        "history": "historical_evidence",
    }[knowledge_class]


def _artifact(root: Path, knowledge_class: str, path: str) -> dict[str, Any]:
    digest, size = _hash_file(root, path)
    history = knowledge_class == "history"
    return {
        "class": knowledge_class,
        "kind": _artifact_kind(knowledge_class, path),
        "path": path,
        "sha256": digest,
        "size_bytes": size,
        "state": "HISTORICAL_EVIDENCE" if history else "CURRENT_STATE",
        "retrieval": "disabled" if history else "on_demand",
    }


def collect(catalog_path: Path, *, max_files: int = DEFAULT_MAX_FILES, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, Any]:
    if not isinstance(max_files, int) or max_files < 1 or max_files > 100_000:
        raise FullInventoryError("max_files is invalid")
    if not isinstance(max_bytes, int) or max_bytes < 1 or max_bytes > 1024 * 1024 * 1024:
        raise FullInventoryError("max_bytes is invalid")
    catalog = _read_bounded_json(catalog_path, limit=MAX_CATALOG_BYTES, label="inventory catalog")
    projects = _catalog_projects(catalog)
    output_projects: list[dict[str, Any]] = []
    total_files = 0
    total_bytes = 0
    for project in sorted(projects, key=lambda value: value["project_id"]):
        if not project["enabled"]:
            output_projects.append(
                {
                    "project_id": project["project_id"],
                    "host_id": project["host_id"],
                    "root": str(project["root"]),
                    "status": "DISABLED",
                    "artifacts": [],
                    "class_counts": {name: 0 for name in CLASSES},
                    "missing_required": [],
                }
            )
            continue
        classified: dict[str, set[str]] = {name: set() for name in CLASSES}
        missing_required: list[str] = []
        for path in project["policy_paths"]:
            if (project["root"] / path).exists():
                classified["project"].add(path)
            else:
                missing_required.append(path)
        for path in project["roadmap_paths"]:
            if (project["root"] / path).exists():
                classified["roadmap"].add(path)
        classified["project"].update(_project_doc_paths(project["root"]))
        for knowledge_class, relative_root, suffixes in _FIXED_ROOTS:
            classified[knowledge_class].update(
                _walk_fixed_root(project["root"], relative_root, suffixes)
            )
        artifacts: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for knowledge_class in CLASSES:
            for path in sorted(classified[knowledge_class]):
                folded = path.casefold()
                if folded in seen_paths:
                    raise FullInventoryError("knowledge artifact is classified more than once")
                seen_paths.add(folded)
                artifact = _artifact(project["root"], knowledge_class, path)
                total_files += 1
                total_bytes += int(artifact["size_bytes"])
                if total_files > max_files:
                    raise FullInventoryError("inventory exceeds the file-count bound")
                if total_bytes > max_bytes:
                    raise FullInventoryError("inventory exceeds the byte bound")
                artifacts.append(artifact)
        counts = {name: sum(1 for item in artifacts if item["class"] == name) for name in CLASSES}
        output_projects.append(
            {
                "project_id": project["project_id"],
                "host_id": project["host_id"],
                "root": str(project["root"]),
                "status": "PASS" if not missing_required else "INCOMPLETE",
                "artifacts": artifacts,
                "class_counts": counts,
                "missing_required": sorted(missing_required),
            }
        )
    payload: dict[str, Any] = {
        "schema": INVENTORY_SCHEMA,
        "catalog_id": catalog["catalog_id"],
        "status": "PASS" if all(row["status"] in {"PASS", "DISABLED"} for row in output_projects) else "PARTIAL",
        "projects": output_projects,
        "project_count": len(output_projects),
        "file_count": total_files,
        "total_bytes": total_bytes,
        "contents_included": False,
        "history_auto_loaded": False,
    }
    payload["inventory_sha256"] = _digest(payload)
    return payload


def _validated_inventory(path: Path) -> dict[str, Any]:
    inventory = _read_bounded_json(path, limit=32 * 1024 * 1024, label="full inventory")
    recorded = inventory.get("inventory_sha256")
    payload = {key: value for key, value in inventory.items() if key != "inventory_sha256"}
    if inventory.get("schema") != INVENTORY_SCHEMA or not isinstance(recorded, str) or _digest(payload) != recorded:
        raise FullInventoryError("full inventory hash is invalid")
    expected_fields = {
        "schema", "catalog_id", "status", "projects", "project_count",
        "file_count", "total_bytes", "contents_included",
        "history_auto_loaded", "inventory_sha256",
    }
    if set(inventory) != expected_fields:
        raise FullInventoryError("full inventory fields are invalid")
    if (
        not isinstance(inventory.get("catalog_id"), str)
        or not inventory["catalog_id"]
        or inventory.get("status") not in {"PASS", "PARTIAL"}
        or inventory.get("contents_included") is not False
        or inventory.get("history_auto_loaded") is not False
        or not isinstance(inventory.get("projects"), list)
        or not 1 <= len(inventory["projects"]) <= 256
        or type(inventory.get("project_count")) is not int
        or inventory["project_count"] != len(inventory["projects"])
        or type(inventory.get("file_count")) is not int
        or inventory["file_count"] < 0
        or type(inventory.get("total_bytes")) is not int
        or inventory["total_bytes"] < 0
    ):
        raise FullInventoryError("full inventory summary is invalid")
    project_ids: set[str] = set()
    total_files = 0
    total_bytes = 0
    expected_project_fields = {
        "project_id", "host_id", "root", "status", "artifacts",
        "class_counts", "missing_required",
    }
    expected_artifact_fields = {
        "class", "kind", "path", "sha256", "size_bytes", "state", "retrieval",
    }
    for project in inventory["projects"]:
        if not isinstance(project, dict) or set(project) != expected_project_fields:
            raise FullInventoryError("full inventory project is invalid")
        project_id = project.get("project_id")
        host_id = project.get("host_id")
        artifacts = project.get("artifacts")
        counts = project.get("class_counts")
        missing = project.get("missing_required")
        if (
            not isinstance(project_id, str)
            or not project_id
            or project_id in project_ids
            or (host_id is not None and (not isinstance(host_id, str) or not host_id))
            or not isinstance(project.get("root"), str)
            or not Path(project["root"]).is_absolute()
            or project.get("status") not in {"PASS", "INCOMPLETE", "DISABLED"}
            or not isinstance(artifacts, list)
            or not isinstance(counts, dict)
            or set(counts) != set(CLASSES)
            or any(type(counts[name]) is not int or counts[name] < 0 for name in CLASSES)
            or not isinstance(missing, list)
            or any(not isinstance(value, str) for value in missing)
        ):
            raise FullInventoryError("full inventory project is invalid")
        project_ids.add(project_id)
        seen_paths: set[str] = set()
        observed_counts = {name: 0 for name in CLASSES}
        for artifact in artifacts:
            if not isinstance(artifact, dict) or set(artifact) != expected_artifact_fields:
                raise FullInventoryError("full inventory artifact is invalid")
            knowledge_class = artifact.get("class")
            relative = _portable_relative(artifact.get("path"), label="inventory artifact path")
            sha256 = artifact.get("sha256")
            size = artifact.get("size_bytes")
            history = knowledge_class == "history"
            if (
                knowledge_class not in CLASSES
                or not isinstance(artifact.get("kind"), str)
                or not artifact["kind"]
                or not isinstance(sha256, str)
                or len(sha256) != 64
                or any(character not in "0123456789abcdef" for character in sha256)
                or type(size) is not int
                or not 0 <= size <= MAX_SINGLE_FILE_BYTES
                or artifact.get("state") != ("HISTORICAL_EVIDENCE" if history else "CURRENT_STATE")
                or artifact.get("retrieval") != ("disabled" if history else "on_demand")
                or relative.casefold() in seen_paths
            ):
                raise FullInventoryError("full inventory artifact is invalid")
            seen_paths.add(relative.casefold())
            observed_counts[knowledge_class] += 1
            total_files += 1
            total_bytes += size
        if counts != observed_counts:
            raise FullInventoryError("full inventory class counts are invalid")
        if project["status"] == "DISABLED" and (artifacts or missing):
            raise FullInventoryError("disabled project inventory is invalid")
        if project["status"] == "PASS" and missing:
            raise FullInventoryError("complete project inventory is invalid")
        if project["status"] == "INCOMPLETE" and not missing:
            raise FullInventoryError("incomplete project inventory is invalid")
    if total_files != inventory["file_count"] or total_bytes != inventory["total_bytes"]:
        raise FullInventoryError("full inventory totals are invalid")
    expected_status = "PASS" if all(
        project["status"] in {"PASS", "DISABLED"} for project in inventory["projects"]
    ) else "PARTIAL"
    if inventory["status"] != expected_status:
        raise FullInventoryError("full inventory status is invalid")
    return inventory


def select(
    inventory_path: Path,
    *,
    project_id: str,
    classes: Iterable[str] | None = None,
) -> dict[str, Any]:
    inventory = _validated_inventory(inventory_path)
    minimal_default = classes is None
    selected_classes = tuple(dict.fromkeys(classes or ("project", "roadmap")))
    if not selected_classes or any(value not in CLASSES or value == "history" for value in selected_classes):
        raise FullInventoryError("selected classes must be durable knowledge classes")
    rows = [row for row in inventory.get("projects", []) if row.get("project_id") == project_id]
    if len(rows) != 1:
        raise FullInventoryError("project_id is not present exactly once")
    project = rows[0]
    if project.get("status") != "PASS":
        raise FullInventoryError("project inventory is not complete")
    root = _canonical_root(project.get("root"))
    artifacts: list[dict[str, Any]] = []
    for item in project.get("artifacts", []):
        if item.get("class") not in selected_classes:
            continue
        if minimal_default and item.get("class") == "project" and item.get("kind") != "project_policy":
            continue
        relative = _portable_relative(item.get("path"), label="inventory artifact path")
        digest, size = _hash_file(root, relative)
        if digest != item.get("sha256") or size != item.get("size_bytes"):
            raise FullInventoryError("selected artifact no longer matches inventory")
        artifacts.append(
            {
                "class": item["class"],
                "kind": item["kind"],
                "path": str(root / relative),
                "relative_path": relative,
                "sha256": digest,
                "size_bytes": size,
                "retrieval": "on_demand",
            }
        )
    payload: dict[str, Any] = {
        "schema": SELECTION_SCHEMA,
        "status": "PASS",
        "inventory_sha256": inventory["inventory_sha256"],
        "project_id": project_id,
        "host_id": project.get("host_id"),
        "classes": list(selected_classes),
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "contents_included": False,
        "history_auto_loaded": False,
    }
    payload["selection_sha256"] = _digest(payload)
    return payload
