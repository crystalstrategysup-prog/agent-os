"""AGENTS/skills bootstrap only. Native hooks and client security config are untouched."""

from __future__ import annotations

import argparse
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
    if START in old:
        a, rest = old.split(START, 1)
        _, b = rest.split(END, 1)
        updated = a + block + b
    else:
        updated = old.rstrip() + "\n\n" + block + "\n"
    paths = {str(agents): updated.encode()}
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
        if path == agents:
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
        "activation_status": "MANUAL_WORKFLOW_NO_HOOKS",
        "native_hooks": "DISABLED",
        "hook_files_changed": False,
        "managed_files": {p: sha(d) for p, d in paths.items()},
        "required_config": {},
        "note": "Read back AGENTS/skills in a new session. Existing hooks/config are untouched; never restore retired AgentOS hooks.",
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
    report["status"] = "INSTALLED_MANUAL_WORKFLOW"
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
