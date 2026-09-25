"""Non-destructive Codex bootstrap. Installation is not proof that hooks are active."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from .safeio import (
    GateError,
    atomic_bytes,
    atomic_json,
    now,
    read_json,
    sha,
    within,
)

START = "<!-- AGENTOS FOUNDATION BEGIN -->"
END = "<!-- AGENTOS FOUNDATION END -->"
EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "Stop")


def install(
    codex_home: Path, skills_home: Path, user_home: Path, *, apply: bool = False
) -> dict:
    from .overlay import validate_roots

    validate_roots(user_home)
    validate_roots(codex_home)
    validate_roots(skills_home)
    codex_home = codex_home.expanduser().resolve()
    skills_home = skills_home.expanduser().resolve()
    resources = Path(__file__).parent / "resources"
    # Do not manufacture an override that shadows existing owner instructions.
    agents = codex_home / (
        "AGENTS.override.md"
        if (codex_home / "AGENTS.override.md").exists()
        else "AGENTS.md"
    )
    old = agents.read_text(encoding="utf-8") if agents.exists() else ""
    if old.count(START) != old.count(END) or old.count(START) > 1:
        raise GateError("damaged_managed_agents_block")
    method = str(resources / "skills/agentos-project-entry/SKILL.md")
    block = (
        START + "\n## AgentOS foundation\n"
        "For every new or resumed project task run the AgentOS project intake before product writes.\n"
        "Reuse verified existing answers; do not interrogate the owner again for known facts.\n"
        "Read " + method + " on entry. Use `agentos project questions`, then `enter`, "
        "register required documents, `ready`, approved checks and `close` or `checkpoint`.\n"
        "Core resources: " + str(resources) + "\n"
        "Private user overlay: " + str(user_home) + "\n"
        "Load its index first and only relevant verified host/project knowledge. Never preload history.\n"
        "Project intake and semantic reviews do not grant external authority. Preserve narrower host rules.\n"
        "An untrusted/unavailable hook is NOT active enforcement. Report that condition; do not bypass it.\n"
        + END
    )
    if START in old:
        a, rest = old.split(START, 1)
        _, b = rest.split(END, 1)
        updated = a + block + b
    else:
        updated = old.rstrip() + "\n\n" + block + "\n"
    # Explicit pinned interpreter and separate user path; no secret/auth/model edits.
    command = " ".join(
        shlex.quote(x)
        for x in [
            sys.executable,
            "-m",
            "agent_os.cli",
            "--home",
            str(user_home),
            "hook",
        ]
    )
    hooks_path = codex_home / "hooks.json"
    hooks = read_json(hooks_path) if hooks_path.exists() else {"hooks": {}}
    if not isinstance(hooks.get("hooks"), dict):
        raise GateError("invalid_existing_hooks")
    for event in EVENTS:
        groups = hooks["hooks"].setdefault(event, [])
        if not isinstance(groups, list):
            raise GateError("invalid_hook_groups")
        # Only replace our tagged command definitions; every other hook is preserved.
        cleaned = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise GateError("invalid_existing_hook_group")
            kept = [
                h
                for h in group["hooks"]
                if h.get("statusMessage") != "AgentOS project lifecycle"
            ]
            if kept:
                cleaned.append({**group, "hooks": kept})
        groups[:] = cleaned
        groups.append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": 20,
                        "statusMessage": "AgentOS project lifecycle",
                    }
                ]
            }
        )
    paths = {
        str(agents): updated.encode(),
        str(hooks_path): (json.dumps(hooks, indent=2) + "\n").encode(),
    }
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
    for name, data in paths.items():
        path = Path(name)
        if path.is_symlink():
            raise GateError("integration_symlink_refused")
        if path in (agents, hooks_path):
            continue
        if (
            path.exists()
            and path.read_bytes() != data
            and sha(path.read_bytes()) != managed.get(name)
        ):
            conflicts.append(name)
    report = {
        "status": "CONFLICT" if conflicts else "PLANNED",
        "files": sorted(paths),
        "conflicts": conflicts,
        "agents_selected": str(agents),
        "auth_changes": False,
        "model_changes": False,
        "hook_trust_changed": False,
        "activation_status": "PENDING_NATIVE_TRUST_AND_NEW_SESSION_PROBE",
        "managed_files": {p: sha(d) for p, d in paths.items()},
        "required_config": {"features.hooks": True},
        "note": "Review /hooks in the actual Codex client. No trust bypass is performed.",
    }
    if not apply or conflicts:
        return report
    for name, data in paths.items():
        path = Path(name)
        if path.exists() and path.read_bytes() == data:
            continue
        if path.exists():
            old_data = path.read_bytes()
            backup = within(
                user_home,
                "backups/integration/" + sha(str(path).encode()) + "-" + sha(old_data),
            )
            if not backup.exists():
                atomic_bytes(backup, old_data)
        atomic_bytes(path, data)
    report["status"] = "INSTALLED_NOT_YET_PROVEN_ACTIVE"
    report["at"] = now()
    atomic_json(codex_home / "agentos-integration.json", report)
    return report


def command(argv: list[str], home: Path) -> tuple[dict, int]:
    p = argparse.ArgumentParser(prog="agentos integrate")
    p.add_argument("target", choices=["codex"])
    p.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    p.add_argument("--skills-home", type=Path, default=Path.home() / ".agents/skills")
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    result = install(a.codex_home, a.skills_home, home, apply=a.apply)
    return result, 2 if result["status"] == "CONFLICT" else 0
