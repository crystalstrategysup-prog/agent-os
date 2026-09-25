"""Safe local discovery and control of persisted Codex and GNU Screen sessions."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_UUID = re.compile(
    r"(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)
_SCREEN_LINE = re.compile(
    r"^\s*(?P<socket>\d+\.[^\s]+)\s+\([^)]*\)\s+\((?P<state>[^)]+)\)"
)
_SCREEN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,47}$")


@dataclass(frozen=True, slots=True)
class CodexSession:
    session_id: str
    updated_at: str
    workspace: str | None
    source_file: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ScreenSession:
    socket: str
    name: str
    state: str
    pid: int
    codex_session_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DispatchResult:
    status: str
    session_id: str | None
    output: str
    return_code: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def codex_home(config: dict[str, Any]) -> Path:
    configured = str(config.get("codex", {}).get("home", "")).strip()
    if configured:
        return Path(configured).expanduser()
    env_home = os.environ.get("CODEX_HOME")
    if env_home:
        return Path(env_home).expanduser()
    return Path.home() / ".codex"


def session_roots(config: dict[str, Any]) -> list[Path]:
    configured = config.get("codex", {}).get("session_roots", [])
    if configured:
        return [Path(str(item)).expanduser() for item in configured]
    return [codex_home(config) / "sessions"]


def allowed_workspaces(config: dict[str, Any]) -> list[Path]:
    section = config.get("codex", {})
    values = list(section.get("allowed_workspaces", []))
    if not values and section.get("default_workspace"):
        values = [section["default_workspace"]]
    if not values:
        values = [str(Path.home())]
    return [Path(str(value)).expanduser().resolve() for value in values]


def validate_workspace(
    config: dict[str, Any], requested: str | Path | None = None
) -> Path:
    section = config.get("codex", {})
    value = requested or section.get("default_workspace") or Path.home()
    candidate = Path(value).expanduser().resolve()
    for root in allowed_workspaces(config):
        if candidate == root or root in candidate.parents:
            if not candidate.is_dir():
                raise ValueError("workspace_not_directory")
            return candidate
    raise ValueError("workspace_not_allowed")


def discover_sessions(
    config: dict[str, Any], limit: int | None = None
) -> list[CodexSession]:
    maximum = int(
        limit or config.get("telegram_session_hub", {}).get("max_sessions", 20)
    )
    files: list[Path] = []
    for root in session_roots(config):
        if root.is_dir():
            files.extend(path for path in root.rglob("*.jsonl") if path.is_file())
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    result: list[CodexSession] = []
    seen: set[str] = set()
    for path in files:
        record = _session_from_file(path)
        if record and record.session_id not in seen:
            seen.add(record.session_id)
            result.append(record)
        if len(result) >= maximum:
            break
    return result


def _session_from_file(path: Path) -> CodexSession | None:
    match = _UUID.search(path.name)
    session_id = match.group("id") if match else None
    workspace: str | None = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(32):
                line = handle.readline(1_000_000)
                if not line:
                    break
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("type") != "session_meta":
                    continue
                payload = item.get("payload", {})
                session_id = str(payload.get("id") or session_id or "")
                workspace = payload.get("cwd")
                break
    except OSError:
        return None
    if not session_id or not _UUID.fullmatch(session_id):
        return None
    updated = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    return CodexSession(
        session_id, updated, str(workspace) if workspace else None, str(path)
    )


def discover_screens() -> list[ScreenSession]:
    if os.name == "nt" or not shutil.which("screen"):
        return []
    completed = subprocess.run(
        ["screen", "-ls"], capture_output=True, text=True, timeout=5, check=False
    )
    processes = _process_rows()
    result: list[ScreenSession] = []
    for line in (completed.stdout + completed.stderr).splitlines():
        match = _SCREEN_LINE.match(line)
        if not match:
            continue
        socket = match.group("socket")
        pid_text, name = socket.split(".", 1)
        pid = int(pid_text)
        result.append(
            ScreenSession(
                socket=socket,
                name=name,
                state=match.group("state"),
                pid=pid,
                codex_session_id=_codex_descendant_session(pid, processes),
            )
        )
    return result


def _process_rows() -> list[tuple[int, int, str]]:
    completed = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,args="],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    rows: list[tuple[int, int, str]] = []
    for line in completed.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
    return rows


def _codex_descendant_session(
    root_pid: int, rows: list[tuple[int, int, str]]
) -> str | None:
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, parent, _ in rows:
            if parent in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    for pid, _, args in rows:
        if pid not in descendants or "codex" not in args.lower():
            continue
        match = _UUID.search(args)
        if match:
            return match.group("id")
    return None


class CodexRunner:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.executable = str(config.get("codex", {}).get("executable", "codex"))
        self.timeout = int(config.get("codex", {}).get("turn_timeout_seconds", 1800))

    def capabilities(self) -> dict[str, Any]:
        return {
            "codex": shutil.which(self.executable) is not None,
            "screen": os.name != "nt" and shutil.which("screen") is not None,
            "platform": "windows" if os.name == "nt" else "unix",
            "session_roots": [str(path) for path in session_roots(self.config)],
            "allowed_workspaces": [
                str(path) for path in allowed_workspaces(self.config)
            ],
        }

    def continue_session(self, session_id: str, prompt: str) -> DispatchResult:
        if not _UUID.fullmatch(session_id):
            raise ValueError("session_id_invalid")
        from .dispatch_gate import claim

        claim(prompt, destination_session=session_id)
        command = [
            self.executable,
            "exec",
            "resume",
            "--skip-git-repo-check",
            session_id,
            "-",
        ]
        return self._run(command, prompt)

    def create_session(
        self, prompt: str, workspace: str | Path | None = None
    ) -> DispatchResult:
        selected = validate_workspace(self.config, workspace)
        from .dispatch_gate import claim

        claim(prompt, workspace=selected)
        command = [
            self.executable,
            "exec",
            "--skip-git-repo-check",
            "-C",
            str(selected),
            "--json",
            "-",
        ]
        result = self._run(command, prompt)
        return result

    def create_screen(
        self, name: str, prompt: str, workspace: str | Path | None = None
    ) -> DispatchResult:
        if os.name == "nt" or not shutil.which("screen"):
            raise RuntimeError("screen_not_supported")
        if not _SCREEN_NAME.fullmatch(name):
            raise ValueError("screen_name_invalid")
        if any(item.name == name for item in discover_screens()):
            raise ValueError("screen_name_exists")
        created = self.create_session(prompt, workspace)
        if created.return_code != 0 or not created.session_id:
            return created
        selected = validate_workspace(self.config, workspace)
        completed = subprocess.run(
            [
                "screen",
                "-dmS",
                name,
                self.executable,
                "resume",
                "--no-alt-screen",
                "-C",
                str(selected),
                created.session_id,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=self._environment(),
        )
        status = (
            "screen_started" if completed.returncode == 0 else "screen_start_failed"
        )
        output = _bounded_output(created.output + "\n" + completed.stderr)
        return DispatchResult(status, created.session_id, output, completed.returncode)

    def continue_screen(self, screen: ScreenSession, prompt: str) -> DispatchResult:
        if not screen.codex_session_id:
            raise RuntimeError("screen_codex_session_unknown")
        record = next(
            (
                item
                for item in discover_sessions(self.config, limit=500)
                if item.session_id == screen.codex_session_id
            ),
            None,
        )
        if record is None:
            raise RuntimeError("screen_codex_session_file_missing")
        from .dispatch_gate import claim

        claim(
            prompt,
            workspace=Path(record.workspace) if record.workspace else None,
            destination_session=screen.codex_session_id,
        )
        path = Path(record.source_file)
        offset = path.stat().st_size
        subprocess.run(
            ["screen", "-S", screen.socket, "-p", "0", "-X", "stuff", prompt],
            timeout=5,
            check=True,
        )
        subprocess.run(
            ["screen", "-S", screen.socket, "-p", "0", "-X", "stuff", "\n"],
            timeout=5,
            check=True,
        )
        proof = _wait_for_screen_proof(path, offset, prompt, 6.0)
        if proof == "queued_or_unsent":
            subprocess.run(
                ["screen", "-S", screen.socket, "-p", "0", "-X", "stuff", "\r"],
                timeout=5,
                check=True,
            )
            proof = _wait_for_screen_proof(path, offset, prompt, 8.0)
        return DispatchResult(
            proof, screen.codex_session_id, "", 0 if proof == "accepted" else 3
        )

    def _run(self, command: list[str], prompt: str) -> DispatchResult:
        if not 1 <= len(prompt.strip()) <= 20_000:
            raise ValueError("prompt_length_invalid")
        completed = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
            env=self._environment(),
        )
        session_id = _thread_id_from_jsonl(completed.stdout)
        output = _bounded_output(completed.stdout + "\n" + completed.stderr)
        status = "completed" if completed.returncode == 0 else "failed"
        return DispatchResult(status, session_id, output, completed.returncode)

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(codex_home(self.config))
        return environment


def _thread_id_from_jsonl(output: str) -> str | None:
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("type") in {"thread.started", "thread_started"}:
            value = item.get("thread_id") or item.get("thread", {}).get("id")
            if value and _UUID.fullmatch(str(value)):
                return str(value)
    return None


def _wait_for_screen_proof(path: Path, offset: int, prompt: str, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    saw_user = False
    while time.monotonic() < deadline:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                lines = handle.readlines()
        except OSError:
            return "proof_unavailable"
        for line in lines:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = item.get("payload", {})
            if _is_matching_user_message(payload, prompt):
                saw_user = True
                continue
            if saw_user and _is_non_user_event(item):
                return "accepted"
        time.sleep(0.25)
    return "queued_not_started" if saw_user else "queued_or_unsent"


def _is_matching_user_message(payload: dict[str, Any], prompt: str) -> bool:
    if payload.get("type") != "message" or payload.get("role") != "user":
        return False
    texts = [
        part.get("text", "")
        for part in payload.get("content", [])
        if isinstance(part, dict)
    ]
    return prompt in texts


def _is_non_user_event(item: dict[str, Any]) -> bool:
    if item.get("type") == "response_item":
        payload = item.get("payload", {})
        return payload.get("role") != "user"
    return item.get("type") == "event_msg" and item.get("payload", {}).get(
        "type"
    ) not in {
        "user_message",
        "token_count",
    }


def _bounded_output(value: str, limit: int = 8_000) -> str:
    return value[-limit:]
