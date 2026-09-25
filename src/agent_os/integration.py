"""AGENTS/skills bootstrap only. Native hooks and client security config are untouched."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .safeio import (
    GateError,
    atomic_bytes,
    atomic_json,
    lock,
    now,
    read_json,
    sha,
    within,
)

START = "<!-- AGENTOS FOUNDATION BEGIN -->"
END = "<!-- AGENTOS FOUNDATION END -->"


def _current_bytes(path: Path) -> bytes | None:
    if path.is_symlink():
        raise GateError("integration_symlink_refused")
    if not path.exists():
        return None
    if not path.is_file():
        raise GateError("integration_regular_file_required")
    return path.read_bytes()


def _recover_transaction(journal: Path, codex_home: Path, skills_home: Path, user_home: Path) -> None:
    record = read_json(journal)
    if (
        record.get("schema") != "agentos.integration-transaction/v1"
        or record.get("codex_home") != str(codex_home)
        or record.get("skills_home") != str(skills_home)
        or not isinstance(record.get("files"), list)
        or len(record["files"]) > 10000
    ):
        raise GateError("integration_recovery_journal_invalid")
    restore = []
    for row in record["files"]:
        if not isinstance(row, dict) or set(row) != {"path", "before", "after", "backup"}:
            raise GateError("integration_recovery_journal_invalid")
        path = Path(row["path"])
        if not path.is_absolute() or not (
            path == codex_home / "AGENTS.md"
            or path == codex_home / "AGENTS.override.md"
            or path == codex_home / "agentos-integration.json"
            or skills_home in path.parents
        ):
            raise GateError("integration_recovery_path_invalid")
        current = _current_bytes(path)
        current_hash = sha(current) if current is not None else None
        if current_hash not in {row["before"], row["after"]}:
            raise GateError("integration_recovery_conflict:" + str(path))
        backup = row["backup"]
        if row["before"] is not None:
            if not isinstance(backup, str):
                raise GateError("integration_recovery_journal_invalid")
            old = within(user_home, backup, allow_missing=False).read_bytes()
            if sha(old) != row["before"]:
                raise GateError("integration_recovery_backup_mismatch")
        else:
            if backup is not None:
                raise GateError("integration_recovery_journal_invalid")
            old = None
        restore.append((path, current_hash, row["before"], old))
    for path, current_hash, _, _ in restore:
        current = _current_bytes(path)
        if (sha(current) if current is not None else None) != current_hash:
            raise GateError("integration_recovery_conflict:" + str(path))
    for path, current_hash, before, old in reversed(restore):
        if current_hash == before:
            continue
        if old is None:
            path.unlink()
        else:
            atomic_bytes(path, old)
    journal.unlink()


def install(
    codex_home: Path, skills_home: Path, user_home: Path, *, apply: bool = False
) -> dict:
    from .overlay import validate_roots

    codex_home = codex_home.expanduser()
    if not codex_home.is_absolute():
        raise GateError("codex_home_absolute_required")
    if codex_home.is_symlink():
        raise GateError("codex_home_symlink_refused")
    validate_roots(user_home)
    validate_roots(codex_home)
    validate_roots(skills_home)
    user_home = user_home.expanduser().resolve()
    codex_home = codex_home.resolve()
    skills_home = skills_home.expanduser().resolve()
    journal = within(user_home, "state/integration-transaction.json")
    if journal.exists():
        if not apply:
            return {
                "status": "RECOVERY_REQUIRED",
                "codex_home_selected": str(codex_home),
                "native_hooks": "DISABLED",
            }
        with lock(within(user_home, "state/integration.lock")):
            _recover_transaction(journal, codex_home, skills_home, user_home)
        return {
            "status": "RECOVERED_RETRY",
            "codex_home_selected": str(codex_home),
            "native_hooks": "DISABLED",
        }
    resources = Path(__file__).parent / "resources"
    # Do not manufacture an override that shadows existing owner instructions.
    override = codex_home / "AGENTS.override.md"
    if override.is_symlink():
        raise GateError("integration_symlink_refused")
    agents = (
        override
        if override.is_file() and override.read_bytes().strip()
        else codex_home / "AGENTS.md"
    )
    if agents.is_symlink():
        raise GateError("integration_symlink_refused")
    old = agents.read_bytes() if agents.exists() else b""
    start, end = START.encode(), END.encode()
    if (
        old.count(start) != old.count(end)
        or old.count(start) > 1
        or (start in old and old.index(start) > old.index(end))
    ):
        raise GateError("damaged_managed_agents_block")
    method = str(resources / "skills/agentos-project-entry/SKILL.md")
    block = (
        START + "\n## AgentOS foundation\n"
        "Questions, searches, read-only audits and API discovery proceed directly, even from an unregistered cwd.\n"
        "No project init/intake/observe, answers file or closeout is required for those reads.\n"
        "For actual project changes, inspect current architecture and write missing docs before product writes.\n"
        "Keep inherited project AGENTS.md concise: scope, universal limits and links to relevant docs/skills.\n"
        "This is editorial guidance, not a size gate or prerequisite for read-only work; follow only relevant links.\n"
        "A read-only request does not authorize rewriting instructions; propose that as a separate project change.\n"
        "Read detailed knowledge on demand; verify dated status when the answer or action depends on it.\n"
        "Reuse verified existing answers; do not interrogate the owner again for known facts.\n"
        "For project changes read " + method + ". Use `agentos project questions`, then `enter`, "
        "register required documents, `ready`, approved checks and `close` or `checkpoint`.\n"
        "Core resources: " + str(resources) + "\n"
        "Private user overlay: " + str(user_home) + "\n"
        "Load only relevant verified overlay knowledge; absent/stale profiles do not block unrelated reads. Never preload history.\n"
        "Project intake and semantic reviews do not grant external authority. Preserve narrower host rules.\n"
        "Native hooks are DISABLED and excluded: do not install, enable or restore them.\n"
        "Bootstrap context/answers and docs may be prepared before readiness; JSON stdin is supported with --answers -.\n"
        "Close/checkpoint only a registered task; report a pre-entry failure directly, never invent a task ID.\n"
        + END
    )
    if start in old:
        a, rest = old.split(start, 1)
        _, b = rest.split(end, 1)
        updated = a + block.encode() + b
    else:
        separator = b""
        if old:
            separator = (b"" if old.endswith(b"\n") else b"\n") + b"\n"
        updated = old + separator + block.encode() + b"\n"
    paths = {str(agents): updated}
    # Copy maintained skills into namespaced folders; never delete user skills.
    for src in sorted((resources / "skills").rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(resources / "skills").as_posix()
        target = within(skills_home, rel)
        paths[str(target)] = src.read_bytes()
    conflicts = []
    previous = (
        read_json(codex_home / "agentos-integration.json")
        if (codex_home / "agentos-integration.json").exists()
        else {}
    )
    managed = previous.get("managed_files", {})
    observed = {}
    for name, data in paths.items():
        path = Path(name)
        original = _current_bytes(path)
        observed[name] = original
        if path == agents:
            continue
        if (
            original is not None
            and original != data
            and sha(original) != managed.get(name)
        ):
            conflicts.append(name)
    report = {
        "status": "CONFLICT" if conflicts else "PLANNED",
        "files": sorted(paths),
        "conflicts": conflicts,
        "agents_selected": str(agents),
        "codex_home_selected": str(codex_home),
        "auth_changes": False,
        "model_changes": False,
        "hook_trust_changed": False,
        "activation_status": "MANUAL_WORKFLOW_NO_HOOKS",
        "native_hooks": "DISABLED",
        "hook_files_changed": False,
        "managed_files": {p: sha(d) for p, d in paths.items()},
        "required_config": {},
        "note": "Read back AGENTS/skills in a new session. Existing hooks/config are untouched; never restore retired AgentOS hooks.",
    }
    if not apply or conflicts:
        return report
    receipt_path = codex_home / "agentos-integration.json"
    receipt_before = _current_bytes(receipt_path)
    report["status"] = "INSTALLED_MANUAL_WORKFLOW"
    report["at"] = now()
    receipt_bytes = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()
    to_write = [(Path(name), data, observed[name]) for name, data in paths.items()]
    to_write.append((receipt_path, receipt_bytes, receipt_before))
    with lock(within(user_home, "state/integration.lock")):
        if journal.exists():
            raise GateError("integration_recovery_required_replan")
        for path, _, original in to_write:
            if _current_bytes(path) != original:
                raise GateError("integration_target_changed_replan:" + str(path))
        records = []
        for path, data, original in to_write:
            if original == data:
                continue
            backup_rel = None
            if original is not None:
                backup_rel = (
                    "backups/integration/"
                    + sha(str(path).encode())
                    + "-"
                    + sha(original)
                )
                backup = within(user_home, backup_rel)
                if backup.exists():
                    if _current_bytes(backup) != original:
                        raise GateError("integration_backup_conflict")
                else:
                    atomic_bytes(backup, original)
            records.append(
                {
                    "path": str(path),
                    "before": sha(original) if original is not None else None,
                    "after": sha(data),
                    "backup": backup_rel,
                }
            )
        atomic_json(
            journal,
            {
                "schema": "agentos.integration-transaction/v1",
                "codex_home": str(codex_home),
                "skills_home": str(skills_home),
                "files": records,
            },
        )
        try:
            for path, data, original in to_write:
                if original != data:
                    atomic_bytes(path, data)
            for path, data, _ in to_write:
                if _current_bytes(path) != data:
                    raise GateError("integration_readback_failed:" + str(path))
        except BaseException:
            _recover_transaction(journal, codex_home, skills_home, user_home)
            raise
        journal.unlink()
    return report


def command(argv: list[str], home: Path) -> tuple[dict, int]:
    p = argparse.ArgumentParser(prog="agentos integrate")
    p.add_argument("target", choices=["codex"])
    p.add_argument("--codex-home", type=Path)
    p.add_argument("--skills-home", type=Path, default=Path.home() / ".agents/skills")
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    codex_home = a.codex_home
    if codex_home is None:
        env_home = os.environ.get("CODEX_HOME", "").strip()
        codex_home = Path(env_home) if env_home else Path.home() / ".codex"
    result = install(codex_home, a.skills_home, home, apply=a.apply)
    return result, 0 if result["status"] in {"PLANNED", "INSTALLED_MANUAL_WORKFLOW"} else 2
