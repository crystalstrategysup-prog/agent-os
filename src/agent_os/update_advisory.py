"""Rate-limited, advisory-only checks for public Community Edition tags."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import stat
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

SCHEMA = "agent-os.community-update-advisory/v1"
OFFICIAL_TAGS_API = (
    "https://api.github.com/repos/crystalstrategysup-prog/agent-os/tags?per_page=100"
)
OFFICIAL_TAG_ROOT = "https://github.com/crystalstrategysup-prog/agent-os/tree/"
MAX_RESPONSE_BYTES = 1024 * 1024
DEFAULT_INTERVAL_SECONDS = 172800
DEFAULT_FAILURE_RETRY_SECONDS = 21600

_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


class UpdateAdvisoryError(ValueError):
    """A bounded public update check could not be trusted as advisory data."""


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _parse_time(value: object) -> dt.datetime:
    if not isinstance(value, str):
        raise UpdateAdvisoryError("invalid advisory timestamp")
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise UpdateAdvisoryError("advisory timestamp lacks timezone")
    return parsed.astimezone(dt.UTC)


def _semver_key(value: str) -> tuple[Any, ...]:
    match = _SEMVER.fullmatch(value.removeprefix("v"))
    if match is None:
        raise UpdateAdvisoryError("unsupported semantic version")
    major, minor, patch = (int(match.group(index)) for index in (1, 2, 3))
    prerelease = match.group(4)
    if prerelease is None:
        return major, minor, patch, 1, ()
    identifiers = tuple(
        (0, int(item)) if item.isdigit() else (1, item)
        for item in prerelease.split(".")
    )
    return major, minor, patch, 0, identifiers


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise UpdateAdvisoryError("duplicate JSON key")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise UpdateAdvisoryError(f"non-finite JSON value: {value}")


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.resolve(strict=True) != path.parent:
        raise UpdateAdvisoryError("advisory state parent must be canonical")
    if path.exists() or path.is_symlink():
        current = path.lstat()
        if not stat.S_ISREG(current.st_mode) or stat.S_ISLNK(current.st_mode):
            raise UpdateAdvisoryError("advisory state must be a regular non-symlink file")
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _load_cached(path: Path) -> dict[str, Any] | None:
    try:
        item = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(item.st_mode) or stat.S_ISLNK(item.st_mode):
        return None
    if item.st_size <= 0 or item.st_size > 128 * 1024:
        return None
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, UpdateAdvisoryError):
        return None
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        return None
    return value


def _fetch_tags(opener: Callable[..., Any], timeout_seconds: int) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        OFFICIAL_TAGS_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Crystal-AgentOS-community-update-advisory",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    response = opener(request, timeout=timeout_seconds)
    try:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
    if len(raw) > MAX_RESPONSE_BYTES:
        raise UpdateAdvisoryError("public update response exceeds the bound")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateAdvisoryError("public update response is invalid") from exc
    if not isinstance(value, list) or len(value) > 100:
        raise UpdateAdvisoryError("public update response shape is invalid")
    return value


def _latest_tag(rows: list[dict[str, Any]]) -> tuple[str, str]:
    candidates: list[tuple[tuple[Any, ...], str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        commit = row.get("commit")
        sha = commit.get("sha") if isinstance(commit, dict) else None
        if not isinstance(name, str) or not name.startswith("v"):
            continue
        if not isinstance(sha, str) or re.fullmatch(r"[a-f0-9]{40}", sha) is None:
            continue
        try:
            key = _semver_key(name)
        except UpdateAdvisoryError:
            continue
        candidates.append((key, name, sha))
    if not candidates:
        raise UpdateAdvisoryError("no semantic release tag found")
    _, tag, commit_sha = max(candidates, key=lambda item: item[0])
    return tag, commit_sha


def _settings(config: dict[str, object]) -> tuple[bool, int, int]:
    value = config.get("update_advisory")
    if not isinstance(value, dict):
        raise UpdateAdvisoryError("update advisory configuration is invalid")
    enabled = value.get("enabled")
    interval = value.get("interval_seconds")
    retry = value.get("failure_retry_seconds")
    automatic = value.get("automatic_install")
    if not isinstance(enabled, bool):
        raise UpdateAdvisoryError("update advisory enabled flag is invalid")
    if not isinstance(interval, int) or isinstance(interval, bool) or not 3600 <= interval <= 2678400:
        raise UpdateAdvisoryError("update advisory interval is invalid")
    if not isinstance(retry, int) or isinstance(retry, bool) or not 300 <= retry <= interval:
        raise UpdateAdvisoryError("update advisory failure retry is invalid")
    if automatic is not False:
        raise UpdateAdvisoryError("community update advisory cannot install software")
    return enabled, interval, retry


def check(
    state_dir: Path,
    config: dict[str, object],
    current_version: str,
    *,
    force: bool = False,
    opener: Callable[..., Any] = urllib.request.urlopen,
    now: dt.datetime | None = None,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Check the fixed public tag source when due; never install anything."""

    enabled, interval, retry = _settings(config)
    moment = (now or _now()).astimezone(dt.UTC)
    state_root = Path(state_dir).expanduser()
    state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_path = (
        state_root / "update-advisory.json"
        if state_root.is_symlink()
        else state_root.resolve(strict=True) / "update-advisory.json"
    )
    cached = _load_cached(state_path)
    if not enabled:
        return {
            "schema": SCHEMA,
            "status": "DISABLED",
            "check_performed": False,
            "automatic_install": False,
            "interval_seconds": interval,
        }
    if cached is not None and not force:
        try:
            next_check = _parse_time(cached.get("next_check_at"))
        except (ValueError, UpdateAdvisoryError):
            next_check = moment
        if moment < next_check:
            result = dict(cached)
            result["check_performed"] = False
            result["cache_reused"] = True
            return result

    checked_at = _iso(moment)
    try:
        tag, commit_sha = _latest_tag(_fetch_tags(opener, timeout_seconds))
        latest_version = tag.removeprefix("v")
        current_key = _semver_key(current_version)
        latest_key = _semver_key(latest_version)
        status = (
            "UPDATE_AVAILABLE"
            if current_key < latest_key
            else "LOCAL_AHEAD"
            if current_key > latest_key
            else "CURRENT"
        )
        result = {
            "schema": SCHEMA,
            "status": status,
            "check_performed": True,
            "cache_reused": False,
            "checked_at": checked_at,
            "next_check_at": _iso(moment + dt.timedelta(seconds=interval)),
            "interval_seconds": interval,
            "current_version": current_version,
            "latest_version": latest_version,
            "latest_tag": tag,
            "latest_commit_sha": commit_sha,
            "latest_tag_url": OFFICIAL_TAG_ROOT + tag,
            "source": "OFFICIAL_GITHUB_TAGS_ADVISORY",
            "automatic_install": False,
            "metadata_authorizes_mutation": False,
        }
    # The advisory must never turn a provider/client failure into a blocked
    # local AgentOS command. Persist only the exception class, never its text.
    except Exception as exc:  # noqa: BLE001
        result = {
            "schema": SCHEMA,
            "status": "UNAVAILABLE",
            "check_performed": True,
            "cache_reused": False,
            "checked_at": checked_at,
            "next_check_at": _iso(moment + dt.timedelta(seconds=retry)),
            "interval_seconds": interval,
            "current_version": current_version,
            "latest_version": None,
            "latest_tag": None,
            "latest_commit_sha": None,
            "latest_tag_url": None,
            "source": "OFFICIAL_GITHUB_TAGS_ADVISORY",
            "automatic_install": False,
            "metadata_authorizes_mutation": False,
            "error_class": type(exc).__name__,
        }
    try:
        result["state_persisted"] = True
        _atomic_write(state_path, result)
    except (OSError, UpdateAdvisoryError):
        # An advisory state-path problem is visible but cannot block AgentOS.
        result["state_persisted"] = False
    return result
