#!/usr/bin/env python3
"""Offline release installer. No sudo, service edits, network, or user-data writes.

Run plan first, then apply with the exact reported --expected-current identifier.
This script deliberately does not retire a different/private AgentOS runtime.
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path
from zipfile import BadZipFile, ZipFile


class InstallError(ValueError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path: Path, value: dict) -> None:
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def normalized(path: Path) -> Path:
    path = path.expanduser().absolute()
    # /var -> /private/var is common on macOS. Reject the destination itself
    # and rely on resolved containment checks for ancestors.
    if path.is_symlink():
        raise InstallError("destination_symlink_refused:" + str(path))
    return path.resolve()


def separate(a: Path, b: Path) -> None:
    a, b = a.resolve(), b.resolve()
    if a == b or a in b.parents or b in a.parents:
        raise InstallError("core_and_user_paths_must_be_disjoint")


def wheel_continuation_schemas(wheel: Path) -> list[str]:
    """Use the hash-verified wheel's bounded declaration, never version guessing."""
    name = "agent_os/resources/contracts/continuation-capabilities-v1.json"
    try:
        with ZipFile(wheel) as archive:
            if 'agent_os/resources/contracts/continuation-capabilities-v2.json' in archive.namelist():
                name = 'agent_os/resources/contracts/continuation-capabilities-v2.json'
            if name not in archive.namelist():
                return []
            if archive.namelist().count(name) != 1 or archive.getinfo(name).file_size > 4096:
                raise InstallError("wheel_continuation_capabilities_invalid")
            value = json.loads(archive.read(name), object_pairs_hook=unique_object)
    except (BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
        raise InstallError("wheel_continuation_capabilities_invalid") from exc
    if isinstance(value, dict) and value.get('schema') == 'agentos.continuation-capabilities/v2':
        expected = {'schema': 'agentos.continuation-capabilities/v2',
                    'readable_item_schemas': ['agentos.continuation-item/v1', 'agentos.continuation-item/v2', 'agentos.continuation-item/v3'],
                    'transition_item_schemas': ['agentos.continuation-item/v2', 'agentos.continuation-item/v3'],
                    'receipt_schemas': ['agentos.continuation-delivery-receipt/v2', 'agentos.continuation-delivery-receipt/v3'],
                    'causal_acceptance_scope': 'received_only', 'legacy_promotion': 'untouched_pending_only', 'provider_io': False}
        if value != expected:
            raise InstallError('wheel_continuation_capabilities_invalid')
        return value['readable_item_schemas']
    if (not isinstance(value, dict) or value.get("schema") != "agentos.continuation-capabilities/v1"
            or value.get("readable_item_schemas") != ["agentos.continuation-item/v1", "agentos.continuation-item/v2"]
            or value.get("transition_item_schemas") != ["agentos.continuation-item/v2"]
            or value.get("receipt_schema") != "agentos.continuation-delivery-receipt/v2"
            or value.get("legacy_promotion") != "untouched_pending_only" or value.get("provider_io") is not False):
        raise InstallError("wheel_continuation_capabilities_invalid")
    return value["readable_item_schemas"]


def wheel_coordination_schemas(wheel: Path) -> list[str]:
    """A missing completion declaration never authorizes the new v2 store."""
    name = "agent_os/resources/contracts/completion-install-v1.json"
    try:
        with ZipFile(wheel) as archive:
            if name not in archive.namelist():
                return ["agentos.work-coordination/v1"]
            if archive.namelist().count(name) != 1 or archive.getinfo(name).file_size > 4096:
                raise InstallError("wheel_completion_capabilities_invalid")
            value = json.loads(archive.read(name), object_pairs_hook=unique_object)
    except (BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
        raise InstallError("wheel_completion_capabilities_invalid") from exc
    expected = {
        "schema": "agentos.completion-install/v1",
        "readable_coordination_schemas": ["agentos.work-coordination/v1", "agentos.work-coordination/v2"],
        "implicit_activation": False,
        "unsupported_downgrade": "preserve_and_hold",
    }
    if value != expected:
        raise InstallError("wheel_completion_capabilities_invalid")
    return value["readable_coordination_schemas"]


SCOPED_INSTALL = {
    "schema": "agentos.scoped-install/v1",
    "readable_transaction_schemas": ["agentos.scoped-transaction/v1"],
    "readable_task_states": ["SCOPED_APPLIED"],
    "implicit_migration": False,
    "unsupported_downgrade": "preserve_and_hold",
}
# Canonical pre-declaration source commits 7d56569 and b157dbf. Recognize
# implementation bytes, not version names or an arbitrary file's presence.
LEGACY_SCOPED_MODULES = {
    "1d8c7453ec94abbd5d1caafdfc60270fb9d8fcaf074f998dcbbee40e0b845658",
    "cafc523e29714c1a79924b6f17651166c7c44a15210431479a1660df24e1ad95",
}
LEGACY_SCOPED_DEPENDENCIES = {
    "agent_os/project.py": "fd3682442cf54fedeae50a7b5cde739ed84eafb74e7dde684bc3cfd1c21348db",
    "agent_os/resources/schemas/project-task-v1.schema.json":
        "ebde2ca75c054b9c33e074b276ae6de23fee7e3f512c47593c2a0769faf8fbc9",
}


def wheel_scoped_schemas(wheel: Path) -> list[str] | None:
    """Recognize declared/known readers; unknown legacy code remains UNKNOWN."""
    declaration = "agent_os/resources/contracts/scoped-install-v1.json"
    implementation = "agent_os/scoped_admission.py"
    try:
        with ZipFile(wheel) as archive:
            names = archive.namelist()

            def member(name, limit):
                if names.count(name) != 1 or archive.getinfo(name).file_size > limit:
                    raise InstallError("wheel_scoped_capabilities_invalid")
                return archive.read(name)

            if declaration in names:
                value = json.loads(member(declaration, 4096), object_pairs_hook=unique_object)
                if value != SCOPED_INSTALL or implementation not in names:
                    raise InstallError("wheel_scoped_capabilities_invalid")
                if names.count(implementation) != 1 or not archive.getinfo(implementation).file_size:
                    raise InstallError("wheel_scoped_capabilities_invalid")
                return list(SCOPED_INSTALL["readable_transaction_schemas"])
            if implementation not in names:
                return []
            if names.count(implementation) != 1:
                raise InstallError("wheel_scoped_capabilities_invalid")
            if (archive.getinfo(implementation).file_size > 1024 * 1024
                    or any(name not in names for name in LEGACY_SCOPED_DEPENDENCIES)):
                return None
            if hashlib.sha256(member(implementation, 1024 * 1024)).hexdigest() not in LEGACY_SCOPED_MODULES:
                return None
            if any(archive.getinfo(name).file_size > 1024 * 1024 for name in LEGACY_SCOPED_DEPENDENCIES):
                return None
            pins = {name: hashlib.sha256(member(name, 1024 * 1024)).hexdigest()
                    for name in LEGACY_SCOPED_DEPENDENCIES}
            if pins != LEGACY_SCOPED_DEPENDENCIES:
                return None
            return list(SCOPED_INSTALL["readable_transaction_schemas"])
    except (BadZipFile, UnicodeError, json.JSONDecodeError, KeyError) as exc:
        raise InstallError("wheel_scoped_capabilities_invalid") from exc


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InstallError("metadata_duplicate_key")
        result[key] = value
    return result


def bounded_file(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise InstallError("provenance_regular_bounded_file_required")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise InstallError("provenance_file_bound")
    return raw


def build_provenance(raw: bytes | None, wheel: Path, version: str) -> dict:
    """Bind existing build metadata to this wheel; metadata grants no authority."""
    result = {"schema": "agentos.install-provenance/v1", "status": "UNKNOWN",
              "source_commit": None, "source_dirty": None,
              "source_identity_status": "UNKNOWN", "source_files_sha256": None,
              "build_manifest_schema": None, "build_manifest_sha256": None,
              "build_versions": None, "source_date_epoch": None}
    if raw is None:
        return result
    if len(raw) > 8 * 1024 * 1024:
        raise InstallError("provenance_file_bound")
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or value.get("version") != version:
        raise InstallError("build_manifest_identity_mismatch")
    schema = value.get("schema")
    expected = {"sha256": digest(wheel), "size": wheel.stat().st_size}
    if schema == "agentos.public-release/v1":
        artifacts = value.get("artifacts")
        artifact = artifacts.get(wheel.name) if isinstance(artifacts, dict) else None
        if artifact != expected:
            raise InstallError("build_manifest_wheel_mismatch")
        commit = value.get("source_commit")
        identity_status, dirty, source_hash = "COMMITTED_ARCHIVE_DECLARED", False, None
        versions = value.get("build_versions")
    elif schema == "agent-os.atlas-candidate-build/v1":
        if (value.get("status") != "BUILD_SUCCEEDED"
                or value.get("qualification") != "LOCAL_CANDIDATE_ONLY"
                or value.get("wheel") != {"name": wheel.name, "bytes": expected["size"],
                                         "sha256": expected["sha256"]}):
            raise InstallError("build_manifest_wheel_mismatch")
        source = value.get("source_files")
        if not isinstance(source, dict) or not source or len(source) > 100_000:
            raise InstallError("build_manifest_source_invalid")
        for name, item in source.items():
            if (not isinstance(name, str) or Path(name).is_absolute()
                    or ".." in Path(name).parts or "\\" in name
                    or not name or name != Path(name).as_posix()
                    or any(ord(c) < 32 for c in name)
                    or not isinstance(item, dict) or set(item) != {"bytes", "sha256"}
                    or type(item["bytes"]) is not int or item["bytes"] < 0
                    or not isinstance(item["sha256"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])):
                raise InstallError("build_manifest_source_invalid")
        source_hash = hashlib.sha256(
            (json.dumps(source, sort_keys=True, indent=2) + "\n").encode()).hexdigest()
        try:
            with ZipFile(wheel) as archive:
                names = [n for n in archive.namelist()
                         if n.startswith("agent_os/") and not n.endswith("/")]
                if len(names) != len(set(names)):
                    raise InstallError("build_manifest_source_invalid")
                actual = {"src/" + n: {"bytes": archive.getinfo(n).file_size,
                                       "sha256": hashlib.sha256(archive.read(n)).hexdigest()}
                          for n in names}
        except BadZipFile as exc:
            raise InstallError("build_manifest_wheel_invalid") from exc
        if not actual or actual != {p: item for p, item in source.items()
                                    if p.startswith("src/agent_os/")}:
            raise InstallError("build_manifest_package_source_mismatch")
        identity = value.get("source_identity")
        commit, dirty, identity_status = None, None, "UNKNOWN"
        if identity is not None:
            if (not isinstance(identity, dict)
                    or identity.get("schema") != "agentos.build-source-identity/v1"
                    or identity.get("source_files_sha256") != source_hash
                    or identity.get("selected_files") != len(source)
                    or identity.get("dirty_scope") != "SELECTED_PACKAGE_INPUTS"):
                raise InstallError("build_manifest_source_identity_invalid")
            commit, dirty, identity_status = (identity.get("source_commit"),
                                             identity.get("dirty"), identity.get("status"))
            if (not isinstance(identity_status, str)
                    or (identity_status == "COMMITTED" and dirty is not False)
                    or (identity_status == "DIRTY" and dirty is not True)
                    or (identity_status == "UNKNOWN" and (dirty is not None or commit is not None))
                    or identity_status not in {"COMMITTED", "DIRTY", "UNKNOWN"}):
                raise InstallError("build_manifest_source_identity_invalid")
            counts = [identity.get(k) for k in ('changed_files', 'untracked_files', 'deleted_files')]
            if identity_status == "UNKNOWN":
                if identity.get("git_tree") is not None or counts != [None, None, None]:
                    raise InstallError("build_manifest_source_identity_invalid")
            elif (not isinstance(identity.get("git_tree"), str)
                  or not re.fullmatch(r"[0-9a-f]{40}", identity["git_tree"])
                  or any(type(count) is not int or count < 0 for count in counts)
                  or bool(sum(counts)) != dirty):
                raise InstallError("build_manifest_source_identity_invalid")
        interpreter = value.get("interpreter")
        versions = interpreter.get("build_versions") if isinstance(interpreter, dict) else None
    else:
        raise InstallError("build_manifest_schema_unsupported")
    if commit is not None and (not isinstance(commit, str)
                              or not re.fullmatch(r"[0-9a-f]{40}", commit)):
        raise InstallError("build_manifest_commit_invalid")
    if identity_status != "UNKNOWN" and commit is None:
        raise InstallError("build_manifest_commit_invalid")
    if (not isinstance(versions, dict) or not versions or len(versions) > 32
            or any(not isinstance(k, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", k)
                   or not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_.+!-]{1,100}", v)
                   for k, v in versions.items())):
        raise InstallError("build_manifest_versions_invalid")
    epoch = value.get("source_date_epoch")
    if type(epoch) is not int or epoch < 315532800:
        raise InstallError("build_manifest_epoch_invalid")
    result.update(status="RECORDED" if commit is not None else "UNKNOWN",
                  source_commit=commit, source_dirty=dirty,
                  source_identity_status=identity_status, source_files_sha256=source_hash,
                  build_manifest_schema=schema, build_manifest_sha256=hashlib.sha256(raw).hexdigest(),
                  build_versions=versions, source_date_epoch=epoch)
    return result


def select_build_manifest(explicit: Path | None, wheel: Path, version: str):
    """Use existing adjacent build metadata automatically, without a new setup step.

    Unrelated or unreadable metadata is not a requirement for legacy packages.
    A document that explicitly claims this wheel must agree with its identity.
    """
    if explicit is not None:
        raw = bounded_file(explicit.expanduser().absolute(), 8 * 1024 * 1024)
        return raw, build_provenance(raw, wheel, version), "EXPLICIT"
    matches = []
    for name in ("BUILD_RECEIPT.json", "MANIFEST.json"):
        path = wheel.parent / name
        if not path.exists() and not path.is_symlink():
            continue
        try:
            raw = bounded_file(path, 8 * 1024 * 1024)
            value = json.loads(raw, object_pairs_hook=unique_object)
        except (OSError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        if value.get("schema") == "agentos.public-release/v1":
            artifacts = value.get("artifacts")
            selected = isinstance(artifacts, dict) and wheel.name in artifacts
        elif value.get("schema") == "agent-os.atlas-candidate-build/v1":
            artifact = value.get("wheel")
            selected = isinstance(artifact, dict) and artifact.get("name") == wheel.name
        else:
            selected = False
        if selected:
            matches.append((raw, build_provenance(raw, wheel, version), "ADJACENT:" + name))
    if not matches:
        return None, build_provenance(None, wheel, version), "UNKNOWN"
    if len(matches) == 2:
        left, right = matches[0][1], matches[1][1]
        for field in ("source_commit", "source_dirty", "source_files_sha256",
                      "build_versions", "source_date_epoch"):
            if left[field] is not None and right[field] is not None and left[field] != right[field]:
                raise InstallError("adjacent_build_manifest_identity_conflict")
        # Prefer identified source over an old receipt with UNKNOWN; otherwise
        # the local receipt provides the strongest package-file binding.
        if left["source_commit"] is None and right["source_commit"] is not None:
            return matches[1]
    return matches[0]


def verify_provenance(path: Path, manifest: dict, wheel: Path) -> None:
    if "provenance" not in manifest:
        return  # Historical immutable releases retain unknown provenance.
    provenance = manifest["provenance"]
    if not isinstance(provenance, dict):
        raise InstallError("release_provenance_invalid")
    installer_raw = bounded_file(path / "INSTALLER.py", 1024 * 1024)
    if hashlib.sha256(installer_raw).hexdigest() != provenance.get("installer_sha256"):
        raise InstallError("release_installer_provenance_mismatch")
    raw = None
    if provenance.get("build_manifest_sha256") is not None:
        raw = bounded_file(path / "BUILD_MANIFEST.json", 8 * 1024 * 1024)
    expected = build_provenance(raw, wheel, manifest["version"])
    expected["installer_sha256"] = hashlib.sha256(installer_raw).hexdigest()
    if provenance != expected:
        raise InstallError("release_build_provenance_mismatch")


def preserve_scoped_reader(root: Path, old: str, selected: dict) -> str:
    if old == "none":
        return "NO_PREVIOUS_RELEASE"
    path = release(root, old)
    # Recovery must not require a healthy current runtime or provenance
    # sidecars. Its verified wheel/INSTALL identity is sufficient reader
    # evidence; execute() fully verifies the target before activating it.
    current = read_manifest(path, verify_payload=False)
    wanted = wheel_scoped_schemas(path / current["wheel_name"])
    provided = selected["scoped_transaction_schemas"]
    if provided is None or wanted is None:
        return "UNKNOWN"
    if not set(wanted).issubset(provided):
        raise InstallError("scoped_reader_incompatible_preserve_and_hold")
    return "PRESERVED"


def release(root: Path, identifier: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,119}", identifier):
        raise InstallError("invalid_release_id")
    path = root / "releases" / identifier
    if path.is_symlink() or (root / "releases").is_symlink():
        raise InstallError("release_symlink_refused")
    return path


def read_manifest(
    path: Path, *, verify_payload: bool = True, normalize_caches: bool = False
) -> dict:
    marker = path / "INSTALL.json"
    if marker.is_symlink() or not marker.is_file() or (path / "INCOMPLETE").exists():
        raise InstallError("release_not_complete:" + path.name)
    data = json.loads(marker.read_text())
    if not isinstance(data, dict):
        raise InstallError("release_manifest_invalid")
    schema = data.get("schema")
    if schema not in {"agentos.install/v1", "agentos.install/v2"} or data.get("overlay_schema") != 1:
        raise InstallError("release_schema_incompatible")
    version, wheel_name, wheel_hash = (
        data.get("version"), data.get("wheel_name"), data.get("wheel_sha256")
    )
    if (
        not isinstance(version, str)
        or not isinstance(wheel_name, str)
        or not re.fullmatch(r"[A-Za-z0-9_.+-]+\.whl", wheel_name)
        or not isinstance(wheel_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", wheel_hash)
    ):
        raise InstallError("release_manifest_invalid")
    wheel = path / wheel_name
    if (
        wheel.parent != path
        or wheel.is_symlink()
        or not wheel.is_file()
        or digest(wheel) != wheel_hash
    ):
        raise InstallError("installed_wheel_hash_mismatch")
    if path.name != version + "-" + wheel_hash[:12]:
        raise InstallError("release_identity_mismatch")
    if schema == "agentos.install/v2":
        hashes = data.get("script_sha256")
        if not isinstance(hashes, dict) or not hashes or any(
            not isinstance(name, str)
            or not isinstance(value, str)
            or not re.fullmatch(r"[0-9a-f]{64}", value)
            for name, value in hashes.items()
        ):
            raise InstallError("installed_entrypoint_hash_contract_missing")
    elif not re.fullmatch(r"0\.5\.0-beta\.[1-5]", version):
        raise InstallError("legacy_manifest_version_unsupported")
    if verify_payload:
        supported_coordination = wheel_coordination_schemas(wheel)
        if data.get("coordination_schemas", supported_coordination) != supported_coordination:
            raise InstallError("release_completion_capabilities_mismatch")
        data["coordination_schemas"] = supported_coordination
        if data.get("continuation_schemas", []) != wheel_continuation_schemas(wheel):
            raise InstallError("release_continuation_capabilities_mismatch")
        scoped = wheel_scoped_schemas(wheel)
        if data.get("scoped_transaction_schemas", scoped) != scoped:
            raise InstallError("release_scoped_capabilities_mismatch")
        data["scoped_transaction_schemas"] = scoped
        verify_provenance(path, data, wheel)
        _verify_owned_payload(
            path,
            wheel,
            data.get("script_sha256"),
            legacy=schema == "agentos.install/v1",
            normalize_caches=normalize_caches,
        )
    return data


def _site_packages(path: Path) -> Path:
    for directory in (path / ".venv", path / ".venv/lib"):
        if directory.is_symlink() or not directory.is_dir():
            raise InstallError("installed_site_packages_directory_invalid")
    candidates = list((path / ".venv/lib").glob("python*/site-packages"))
    if len(candidates) != 1:
        raise InstallError("installed_site_packages_missing_or_ambiguous")
    site = candidates[0]
    # glob/is_dir follow an intermediate symlink. A linked pythonX directory
    # could otherwise make cache normalization delete bytes in the owner tree.
    for directory in (site.parent, site):
        if directory.is_symlink() or not directory.is_dir():
            raise InstallError("installed_site_packages_directory_invalid")
    return site


def _verify_owned_payload(
    path: Path, wheel: Path, script_hashes: dict | None, *,
    legacy: bool = False, normalize_caches: bool = False,
) -> dict[str, str]:
    """Compare actual package bytes with the trusted wheel before importing it."""
    site = _site_packages(path)
    try:
        with ZipFile(wheel) as archive:
            names = [n for n in archive.namelist() if not n.endswith("/")]
            metadata = [n for n in names if n.endswith(".dist-info/entry_points.txt")]
            if len(metadata) != 1:
                raise InstallError("wheel_entrypoints_missing_or_ambiguous")
            entries = configparser.ConfigParser(interpolation=None)
            entries.read_string(archive.read(metadata[0]).decode("utf-8"))
            if "console_scripts" not in entries:
                raise InstallError("wheel_console_scripts_missing")
            expected = {}
            for name in names:
                if name.startswith("agent_os/") or ".dist-info/" in name:
                    if name.endswith(".dist-info/RECORD"):
                        continue  # pip rewrites installed RECORD.
                    if Path(name).is_absolute() or ".." in Path(name).parts:
                        raise InstallError("wheel_payload_path_invalid")
                    expected[name] = hashlib.sha256(archive.read(name)).hexdigest()
    except (BadZipFile, UnicodeError, configparser.Error) as exc:
        raise InstallError("wheel_payload_invalid") from exc
    if not expected or not any(n.startswith("agent_os/") for n in expected):
        raise InstallError("wheel_package_missing")
    for name, expected_hash in expected.items():
        actual = site / name
        if actual.is_symlink() or not actual.is_file() or digest(actual) != expected_hash:
            raise InstallError("installed_payload_mismatch:" + name)
    allowed_metadata = {"RECORD", "INSTALLER", "REQUESTED", "direct_url.json"}
    package = site / "agent_os"
    if package.is_symlink() or not package.is_dir():
        raise InstallError("installed_package_directory_invalid")
    cache_files = []
    for root, dirs, files in os.walk(package, followlinks=False):
        for directory in dirs:
            if (Path(root) / directory).is_symlink():
                raise InstallError("installed_payload_symlink")
        for filename in files:
            actual = Path(root) / filename
            if actual.is_symlink() or not actual.is_file():
                raise InstallError("installed_payload_type_invalid")
            rel = actual.relative_to(site).as_posix()
            if "__pycache__" in actual.parts and filename.endswith(".pyc"):
                cache_files.append(actual)
                continue
            if rel not in expected:
                raise InstallError("installed_payload_extra:" + rel)
    # pip and normal use may create caches. Remove only verified regular cache
    # files in this owned package before any import: -B prevents writes, not
    # execution of a pre-existing timestamp-valid .pyc.
    dist_info = site / metadata[0].split("/", 1)[0]
    if dist_info.is_symlink() or not dist_info.is_dir():
        raise InstallError("installed_metadata_directory_invalid")
    for root, dirs, files in os.walk(dist_info, followlinks=False):
        for directory in dirs:
            if (Path(root) / directory).is_symlink():
                raise InstallError("installed_metadata_symlink")
        for filename in files:
            actual = Path(root) / filename
            if actual.is_symlink() or not actual.is_file():
                raise InstallError("installed_metadata_type_invalid")
            rel = actual.relative_to(site).as_posix()
            if rel not in expected and not (
                actual.parent == dist_info and filename in allowed_metadata
            ):
                raise InstallError("installed_metadata_extra:" + rel)
    scripts = {}
    for name, target in entries["console_scripts"].items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
            raise InstallError("wheel_entrypoint_name_invalid")
        script = path / ".venv/bin" / name
        if script.is_symlink() or not script.is_file():
            raise InstallError("installed_entrypoint_missing:" + name)
        module, sep, function = target.partition(":")
        if not sep or not module.startswith("agent_os.") or not function.isidentifier():
            raise InstallError("wheel_entrypoint_target_invalid")
        body = script.read_text(encoding="utf-8")
        interpreter = str(path / ".venv/bin/python")
        direct_shebang = "#!" + interpreter + "\n"
        # pip/distlib uses a POSIX sh trampoline when the venv path contains
        # spaces, because a kernel shebang cannot quote its interpreter.
        shell_shebang = (
            "#!/bin/sh\n'''exec' \""
            + interpreter.replace('"', '\\"')
            + "\" \"$0\" \"$@\"\n' '''\n"
        )
        # On Linux distlib uses the sh trampoline for a long shebang even when
        # the interpreter has no spaces, and then leaves a shell-safe path
        # unquoted. Accept that exact form only for safe path characters.
        plain_shell_shebang = (
            "#!/bin/sh\n'''exec' " + interpreter + " \"$0\" \"$@\"\n' '''\n"
            if re.fullmatch(r"[A-Za-z0-9/_.+-]+", interpreter)
            else ""
        )
        prefixes = tuple(x for x in (direct_shebang, shell_shebang, plain_shell_shebang) if x)
        if not body.startswith(prefixes) or (
            f"from {module} import {function}" not in body
        ):
            raise InstallError("installed_entrypoint_target_mismatch:" + name)
        if legacy:
            prefix = next(x for x in prefixes if body.startswith(x))
            modern = (
                prefix
                + "import sys\n"
                + f"from {module} import {function}\n"
                + "if __name__ == '__main__':\n"
                + "    sys.argv[0] = sys.argv[0].removesuffix('.exe')\n"
                + f"    sys.exit({function}())\n"
            )
            pip_legacy = (
                prefix
                + "# -*- coding: utf-8 -*-\n"
                + "import re\n"
                + "import sys\n"
                + f"from {module} import {function}\n"
                + "if __name__ == '__main__':\n"
                + "    sys.argv[0] = re.sub(r'(-script\\.pyw|\\.exe)?$', '', sys.argv[0])\n"
                + f"    sys.exit({function}())\n"
            )
            if body not in (modern, pip_legacy):
                raise InstallError("legacy_entrypoint_not_canonical:" + name)
        scripts[name] = digest(script)
    if script_hashes is not None and scripts != script_hashes:
        raise InstallError("installed_entrypoint_hash_mismatch")
    if normalize_caches:
        for cache in cache_files:
            cache.unlink()
    return scripts


def check_user_compatibility(user: Path, manifest: dict, *, check_continuations: bool = True) -> None:
    """Read only the schema headers that the selected release can consume."""
    if (
        manifest.get("overlay_schema") != 1
        or manifest.get("config_schema") != "agent-os.community-config/v5"
    ):
        raise InstallError("release_user_schema_contract_unsupported")

    def read_metadata(name: str) -> dict | None:
        path = user / name
        if path.is_symlink():
            raise InstallError("user_metadata_symlink_refused:" + name)
        if not path.exists():
            return None
        if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            raise InstallError("user_metadata_not_bounded_file:" + name)

        def unique(pairs: list[tuple[str, object]]) -> dict:
            value = {}
            for key, item in pairs:
                if key in value:
                    raise InstallError("user_metadata_duplicate_key:" + name)
                value[key] = item
            return value

        try:
            value = json.loads(
                path.read_text(encoding="utf-8"), object_pairs_hook=unique
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise InstallError("user_metadata_invalid_json:" + name) from exc
        if not isinstance(value, dict):
            raise InstallError("user_metadata_not_object:" + name)
        return value

    overlay = read_metadata("overlay.json")
    if overlay is not None and overlay.get("schema") != "agentos.user-overlay/v1":
        raise InstallError("user_overlay_schema_unsupported")
    config = read_metadata("config.json")
    if config is not None and config.get("schema") not in {
        f"agent-os.community-config/v{version}" for version in range(1, 6)
    }:
        raise InstallError("user_config_schema_unsupported")
    if not check_continuations:
        return
    # Verify actual immutable HEAD/snapshot bytes, not a version label. No
    # migration or payload rewrite is performed, even during rollback planning.
    for directory in [user / "state", user / "state/work-coordination"]:
        if directory.is_symlink():
            raise InstallError("user_coordination_directory_symlink_refused")
    queue_root = user / "state/work-coordination"
    if queue_root.exists():
        if not queue_root.is_dir():
            raise InstallError("user_coordination_directory_invalid")
        streams = sorted(queue_root.iterdir())
        if len(streams) > 1000:
            raise InstallError("user_coordination_inventory_limit")
        supported = manifest.get("coordination_schemas", ["agentos.work-coordination/v1"])
        for stream in streams:
            if stream.is_symlink() or not stream.is_dir() or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", stream.name):
                raise InstallError("user_coordination_stream_invalid")
            prefix = "state/work-coordination/" + stream.name + "/"
            head = read_metadata(prefix + "HEAD.json")
            if (head is None or set(head) != {"schema", "revision", "snapshot_sha256", "size_bytes"}
                    or type(head["revision"]) is not int
                    or type(head["size_bytes"]) is not int or not 0 < head["size_bytes"] <= 1024 * 1024
                    or not isinstance(head["snapshot_sha256"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", head["snapshot_sha256"])):
                raise InstallError("user_coordination_head_invalid")
            if head["schema"] not in supported:
                raise InstallError("coordination_store_incompatible_preserve_and_hold")
            if (stream / "snapshots").is_symlink():
                raise InstallError("user_coordination_snapshot_symlink_refused")
            relative = prefix + "snapshots/" + head["snapshot_sha256"] + ".json"
            state = read_metadata(relative)
            snapshot = user / relative
            if (state is None or snapshot.stat().st_size != head["size_bytes"]
                    or digest(snapshot) != head["snapshot_sha256"]
                    or state.get("schema") != head["schema"] or state.get("revision") != head["revision"]
                    or (head["schema"] == "agentos.work-coordination/v2"
                        and (not isinstance(state.get("completion"), dict)
                             or state["completion"].get("schema") != "agentos.completion/v1"))):
                raise InstallError("user_coordination_snapshot_invalid")
    for path in [user / "state", user / "state/continuations"]:
        if path.is_symlink():
            raise InstallError("user_continuation_directory_symlink_refused")
    queue = user / "state/continuations"
    if not queue.exists():
        return
    if not queue.is_dir():
        raise InstallError("user_continuation_directory_invalid")
    paths = sorted(queue.glob("*.json"))
    if len(paths) > 1000 or sum(x.stat().st_size for x in paths if not x.is_symlink()) > 32 * 1024 * 1024:
        raise InstallError("user_continuation_inventory_limit")
    supported = manifest.get("continuation_schemas", [])
    for path in paths:
        if not re.fullmatch(r"[0-9a-f]{64}\.json", path.name):
            raise InstallError("user_continuation_filename_invalid")
        item = read_metadata("state/continuations/" + path.name)
        states = ({'PENDING', 'CLAIMED', 'DELIVERY_UNKNOWN', 'RECEIVED', 'RECEIVED_REFUSED'}
                  if item and item.get('schema') == 'agentos.continuation-item/v3'
                  else {"PENDING", "CLAIMED", "DELIVERY_UNKNOWN", "ACKNOWLEDGED"})
        if (item is None or item.get("id") != path.stem or item.get('state') not in states
                or item.get("schema") not in {"agentos.continuation-item/v1", "agentos.continuation-item/v2", 'agentos.continuation-item/v3'}):
            raise InstallError("user_continuation_metadata_invalid")
        if item["schema"] not in supported:
            raise InstallError("continuation_queue_incompatible_preserve_and_hold")


@contextmanager
def coordination_locks(user: Path):
    """Use existing Coordinator publisher locks for final check/switch.

    The selecting host must still prove quiescence/target authority; this is not
    a replacement for fencing an executor or preventing new stream creation.
    """
    import fcntl

    directory = user / "state/work-coordination"
    if not directory.exists():
        yield
        return
    if directory.is_symlink() or not directory.is_dir():
        raise InstallError("user_coordination_directory_invalid")
    streams = sorted(directory.iterdir())
    if len(streams) > 1000:
        raise InstallError("user_coordination_inventory_limit")
    with ExitStack() as stack:
        for stream in streams:
            lock = stream / "publisher.lock"
            if stream.is_symlink() or lock.is_symlink() or not lock.is_file():
                raise InstallError("user_coordination_lock_invalid")
            handle = stack.enter_context(lock.open("rb"))
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise InstallError("coordination_writer_active_preserve_and_hold") from exc
            stack.callback(fcntl.flock, handle, fcntl.LOCK_UN)
        if sorted(directory.iterdir()) != streams:
            raise InstallError("coordination_inventory_changed_preserve_and_hold")
        yield


@contextmanager
def continuation_lock(user: Path):
    """Serialize compliant queue writers during the final compatibility/switch."""
    state = user / "state"
    if not state.exists():
        # First install has no owner state to lock. The host activation contract
        # still requires a quiesced authorized parent and its target lease.
        yield
        return
    if state.is_symlink() or not state.is_dir():
        raise InstallError("user_continuation_state_invalid")
    marker = state / "continuations.lock"
    try:
        marker.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise InstallError("continuation_lock_exists_manual_review_required") from exc
    try:
        yield
    finally:
        marker.rmdir()


def current_id(root: Path) -> str:
    current = root / "current"
    if not current.exists() and not current.is_symlink():
        return "none"
    if not current.is_symlink():
        raise InstallError("refuse_replace_unmanaged_current")
    target = current.resolve()
    if target.parent != (root / "releases").resolve():
        raise InstallError("refuse_replace_foreign_current")
    if not target.is_dir() or target.is_symlink():
        raise InstallError("current_release_directory_missing")
    return target.name


def run(argv: list[str], *, timeout: int = 180) -> str:
    env = {
        **os.environ,
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        argv, capture_output=True, text=True, timeout=timeout, env=env, check=False
    )
    if result.returncode:
        raise InstallError("subprocess_failed:" + result.stderr[-4000:])
    return result.stdout


def probe(path: Path, expected_version: str) -> dict:
    code = """import json; from pathlib import Path; import agent_os
from agent_os.mcp_server import TOOLS
r = Path(agent_os.__file__).parent/'resources'
assert (r/'skills/agentos-project-entry/SKILL.md').is_file()
assert (r/'schemas/project.schema.json').is_file()
assert len(TOOLS) == 6
print(json.dumps({'version': agent_os.__version__, 'tools': len(TOOLS), 'resources': True}))
"""
    value = json.loads(run([str(path / ".venv/bin/python"), "-I", "-B", "-c", code]))
    if value["version"] != expected_version:
        raise InstallError("installed_version_mismatch")
    return value


def activate(root: Path, identifier: str, old: str) -> None:
    if current_id(root) != old:
        raise InstallError("current_changed_during_install")
    previous = {
        "schema": "agentos.previous/v1",
        "previous": old,
        "selected": identifier,
        "at_unix": time.time(),
    }
    write_json(root / "PREVIOUS.json", previous)
    temp = root / (".current-" + uuid.uuid4().hex)
    try:
        temp.symlink_to(Path("releases") / identifier, target_is_directory=True)
        os.replace(temp, root / "current")
    finally:
        temp.unlink(missing_ok=True)
    if current_id(root) != identifier:
        raise InstallError("activation_readback_failed")


def execute(args: argparse.Namespace) -> dict:
    if os.name != "posix":
        raise InstallError("managed_installer_supports_POSIX_only")
    if sys.version_info < (3, 11):  # noqa: UP036 - this script runs before package installation
        raise InstallError("Python_3_11_or_newer_required")
    root, user = normalized(args.core_home), normalized(args.user_home)
    separate(root, user)
    separate(Path(__file__).resolve().parent.parent, root)
    old = current_id(root)
    installer_raw = bounded_file(Path(__file__), 1024 * 1024)
    installer_hash = hashlib.sha256(installer_raw).hexdigest()
    build_raw = None
    build_selection = "EXISTING_RELEASE"
    if args.action == "rollback":
        target = release(root, args.release_id)
        manifest = read_manifest(target, verify_payload=False)
        identifier = target.name
        # Preserve the existing bounded user-metadata preflight priority. Only
        # after it passes derive reader capabilities from the actual wheel;
        # stored manifest labels are never trusted for the complete store check.
        check_user_compatibility(user, manifest, check_continuations=False)
        supported = wheel_coordination_schemas(target / manifest["wheel_name"])
        if manifest.get("coordination_schemas", supported) != supported:
            raise InstallError("release_completion_capabilities_mismatch")
        manifest["coordination_schemas"] = supported
        manifest["scoped_transaction_schemas"] = wheel_scoped_schemas(target / manifest["wheel_name"])
    else:
        wheel = args.wheel.expanduser().absolute()
        if wheel.is_symlink() or not wheel.is_file() or wheel.suffix != ".whl":
            raise InstallError("local_regular_wheel_required")
        expected = args.sha256.lower()
        if not re.fullmatch("[0-9a-f]{64}", expected) or digest(wheel) != expected:
            raise InstallError("wheel_sha256_mismatch")
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+|-[A-Za-z0-9.-]+)?(?:\+[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)?", args.version):
            raise InstallError("invalid_version")
        identifier = args.version + "-" + expected[:12]
        target = release(root, identifier)
        manifest = {
            "schema": "agentos.install/v2",
            "version": args.version,
            "wheel_sha256": expected,
            "wheel_name": wheel.name,
            "overlay_schema": 1,
            "config_schema": "agent-os.community-config/v5",
        }
        check_user_compatibility(user, manifest, check_continuations=False)
        manifest["continuation_schemas"] = wheel_continuation_schemas(wheel)
        manifest["coordination_schemas"] = wheel_coordination_schemas(wheel)
        manifest["scoped_transaction_schemas"] = wheel_scoped_schemas(wheel)
        build_raw, manifest["provenance"], build_selection = select_build_manifest(
            getattr(args, "build_manifest", None), wheel, args.version)
        manifest["provenance"]["installer_sha256"] = installer_hash
    check_user_compatibility(user, manifest)
    reader_compatibility = preserve_scoped_reader(root, old, manifest)
    if args.action == "rollback":
        manifest = read_manifest(target)
    elif target.exists():
        stored = read_manifest(target)
        if build_raw is not None:
            retained, supplied = stored.get("provenance", {}), manifest["provenance"]
            for field in ("source_commit", "source_dirty", "source_files_sha256",
                          "build_versions", "source_date_epoch"):
                if retained.get(field) is not None and supplied[field] is not None and retained[field] != supplied[field]:
                    raise InstallError("immutable_release_provenance_conflict")
            build_selection = "EXISTING_RELEASE_UNCHANGED"
        manifest = stored
    plan = {
        "status": "PLANNED",
        "action": args.action,
        "core_home": str(root),
        "user_home": str(user),
        "expected_current": old,
        "release_id": identifier,
        "user_data_writes": [],
        "service_changes": [],
        "network_required": False,
        "activation_proven": False,
        "scoped_transaction_schemas": manifest["scoped_transaction_schemas"],
        "scoped_reader_compatibility": reader_compatibility,
        "build_manifest_selection": build_selection,
        "provenance": manifest.get("provenance", {"status": "UNKNOWN"}),
        "executing_installer_sha256": installer_hash,
    }
    if not args.apply:
        return plan
    if args.expected_current is None or args.expected_current != old:
        raise InstallError("explicit_matching_expected_current_required")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = root / ".install.lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        raise InstallError("installation_lock_exists_manual_review_required")
    try:
        write_json(lock / "owner.json", {"pid": os.getpid(), "at_unix": time.time()})
        if current_id(root) != old:
            raise InstallError("current_changed_before_install")
        if args.action == "rollback":
            read_manifest(target, normalize_caches=True)
        if args.action == "install":
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if target.exists():
                stored = read_manifest(target, normalize_caches=True)
                if (
                    stored["wheel_sha256"] != manifest["wheel_sha256"]
                    or stored["version"] != manifest["version"]
                ):
                    raise InstallError("immutable_release_conflict")
            else:
                # Build at final immutable path: venv scripts contain absolute paths.
                target.mkdir(mode=0o700)
                (target / "INCOMPLETE").write_text(
                    "Do not activate. Inspect/retry in a different reviewed release directory.\n"
                )
                shutil.copyfile(wheel, target / wheel.name)
                if digest(target / wheel.name) != manifest["wheel_sha256"]:
                    raise InstallError("wheel_changed_during_copy")
                with (target / "INSTALLER.py").open("xb") as stream:
                    stream.write(installer_raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                if build_raw is not None:
                    with (target / "BUILD_MANIFEST.json").open("xb") as stream:
                        stream.write(build_raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                run([sys.executable, "-I", "-m", "venv", str(target / ".venv")])
                run(
                    [
                        str(target / ".venv/bin/python"),
                        "-I",
                        "-m",
                        "pip",
                        "--isolated",
                        "install",
                        "--no-index",
                        "--no-deps",
                        "--disable-pip-version-check",
                        str(target / wheel.name),
                    ]
                )
                manifest["script_sha256"] = _verify_owned_payload(
                    target, target / wheel.name, None, normalize_caches=True
                )
                evidence = probe(target, manifest["version"])
                manifest["probe"] = evidence
                manifest["created_at_unix"] = time.time()
                write_json(target / "INSTALL.json", manifest)
                (target / "INCOMPLETE").unlink()
        evidence = probe(target, manifest["version"])
        with continuation_lock(user), coordination_locks(user):
            check_user_compatibility(user, manifest)
            verified = read_manifest(target)
            preserve_scoped_reader(root, old, verified)
            if hashlib.sha256(bounded_file(Path(__file__), 1024 * 1024)).hexdigest() != installer_hash:
                raise InstallError("installer_changed_during_install")
            activate(root, identifier, old)
        return {
            **plan,
            "status": "INSTALLED" if args.action == "install" else "ROLLED_BACK",
            "activation_proven": True,
            "local_probe": evidence,
            "previous": old,
            "next": "Import separate overlay, then integrate AGENTS/skills and read back in a new session. Keep native hooks disabled. No live service was replaced.",
        }
    finally:
        (lock / "owner.json").unlink(missing_ok=True)
        lock.rmdir()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    for action in ("install", "rollback"):
        s = sub.add_parser(action)
        s.add_argument(
            "--core-home",
            type=Path,
            default=Path.home() / ".local/share/agentos-foundation",
        )
        s.add_argument("--user-home", type=Path, default=Path.home() / ".agentos-user")
        s.add_argument("--apply", action="store_true")
        s.add_argument("--expected-current")
        if action == "install":
            s.add_argument("--wheel", type=Path, required=True)
            s.add_argument("--sha256", required=True)
            s.add_argument("--version", required=True)
            s.add_argument("--build-manifest", type=Path,
                           help="Override automatic adjacent BUILD_RECEIPT.json / MANIFEST.json selection")
        else:
            s.add_argument("--release-id", required=True)
    return p


def main() -> int:
    try:
        print(json.dumps(execute(parser().parse_args()), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as e:
        print(json.dumps({"status": "BLOCKED", "error": str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
