"""AGENTS/skills bootstrap only. Native hooks and client security config are untouched."""

from __future__ import annotations

import argparse
import json
import os
import re
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


def _recover_transaction(
    journal: Path, codex_home: Path, skills_home: Path, user_home: Path, *,
    selected_skills: list[str] | None = None,
) -> None:
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
        if not isinstance(row["path"], str):
            raise GateError("integration_recovery_path_invalid")
        path = Path(row["path"])
        if (
            selected_skills is not None
            and path not in {codex_home / "AGENTS.md", codex_home / "AGENTS.override.md",
                             codex_home / "agentos-integration.json"}
            and skills_home in path.parents
            and path.relative_to(skills_home).parts[0] not in selected_skills
        ):
            raise GateError("integration_recovery_skill_scope_mismatch")
        if not path.is_absolute() or not (
            path == codex_home / "AGENTS.md"
            or path == codex_home / "AGENTS.override.md"
            or path == codex_home / "agentos-integration.json"
            or (
                skills_home in path.parents
                and within(skills_home, path.relative_to(skills_home).as_posix()) == path
            )
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


def _skill_selection(resources: Path, skills: list[str] | None, agents_only: bool) -> list[str] | None:
    if skills is None:
        return None
    if agents_only:
        raise GateError("integration_skill_selection_conflict")
    if (
        not isinstance(skills, list) or not skills
        or any(not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
               for name in skills)
    ):
        raise GateError("integration_skill_name_invalid")
    selected = sorted(set(skills))
    for name in selected:
        root = within(resources / "skills", name)
        if not root.is_dir() or not within(root, "SKILL.md").is_file():
            raise GateError("integration_skill_unknown:" + name)
    return selected


def install(
    codex_home: Path, skills_home: Path, user_home: Path, *, apply: bool = False,
    agents_only: bool = False, skills: list[str] | None = None,
) -> dict:
    from .overlay import validate_roots

    resources = Path(__file__).parent / "resources"
    selected = _skill_selection(resources, skills, agents_only)
    recovery_options = {"selected_skills": selected} if selected is not None else {}
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
            _recover_transaction(journal, codex_home, skills_home, user_home, **recovery_options)
        return {
            "status": "RECOVERED_RETRY",
            "codex_home_selected": str(codex_home),
            "native_hooks": "DISABLED",
        }
    # Do not manufacture an override that shadows existing owner instructions.
    override = codex_home / "AGENTS.override.md"
    override_bytes = _current_bytes(override)
    agents = (
        override
        if override_bytes is not None and override_bytes.strip()
        else codex_home / "AGENTS.md"
    )
    agents_before = override_bytes if agents == override else _current_bytes(agents)
    old = agents_before or b""
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
        "At engineering entry and continuation, consume the current actual text returned by `agentos workflow guidance` (or the same foundation_guidance body in the current workflow/context result). It is the canonical PROCESS.md project-development method: a complete plan at the current level, mandatory modularity, a connected running stand, then recursive refinement of the selected part. Simple implementations and explicit stubs are valid stage results. A path, hash or acknowledgement is not the loaded method.\n"
        "On first engagement also read docs/WORK_ENVIRONMENT.md from the current resources, then reuse it and restore relevant parts after context loss. The work laws and introduction are frozen: agents must not revise, weaken or repin them without an explicit owner decision about those texts. Current project facts stay in their ordinary records; evaluate application through actual results.\n"
        "Use the owner's development level from 1 to 5 (balanced default 3) for the project, stage or module. At the start of genuinely new development that has not begun, offer five briefly described single-choice buttons using the canonical method unless the owner already selected a level. Patches, fixes, enhancements and continuation retain the existing level, or 3 when absent, without another chooser. Apply later level changes to subsequent work and preserve them in existing task context. Level 1 emphasizes fast assembly with debug context and an error journal; level 3 uses light synthetic checks; level 5 details and verifies each step immediately. For a concrete malfunction needing causal investigation, load `agentos workflow guidance --method causal-debugging` and resume its existing journal.\n"
        "For handoff lookup read " + str(resources / "docs/HANDOFF_DISCOVERY.md") + ". Use the selected project/user index; verify before opening. Task results and archives are not current handoffs.\n"
        "For project changes read " + method + ". Use `agentos project questions`, then `enter`, "
        "register required documents, `ready`, approved checks and `close` or `checkpoint`.\n"
        "For coordination read " + str(resources / "docs/COORDINATOR_KNOWLEDGE_INDEX.json") + ". Verify selected references; keep parent open until checked user result and record remainder/next owner. This routing does not launch sessions or prove live adoption.\n"
        "Native workers must preserve a final and return result/evidence/remainder/next owner to their delegator through an explicitly authorized supported route. Delegators retain responsibility through bounded wait, receipt and semantic review; an owned blocker checkpoint names the next owner instead of abandoning the child. Busy gets no redundant continuation; unknown inputs/effects are reconciled before replay. Prepared report, uncertain send, recipient receipt and semantic acceptance are separate. New instructions do not automatically update already-running chats.\n"
        "Core resources: " + str(resources) + "\n"
        "Private user overlay: " + str(user_home) + "\n"
        "Load only relevant verified overlay knowledge; absent/stale profiles do not block unrelated reads. Never preload history.\n"
        "Before relying on selected rules for project work, continuation or a project report, read " + str(resources / "docs/CONTEXT_BINDING.md") + ". Run `agentos --home USER_HOME context build --request REQUEST.json` with the private user overlay path above, current session/turn, purpose, relevant keys and existing goal. For registered engineering work bind `development_source` to the exact root/task_id/revision so the saved level/scope is carried and checked; otherwise carry typed `goal.development`. A prose-only known answer is insufficient. Consume the actual returned text and choice. A path/hash alone is not loaded context. Missing dependencies block only dependent work.\n"
        "Keep the original goal, semantic acceptance, known answers and scope through continuation. Verify current target authority; a copied reference never renews it. Validate observed behavior separately: install/selection/ACK and a context hash do not prove compliance.\n"
        "Before creating a worker session, read " + str(resources / "docs/SESSION_LAUNCH.md") + ". Match required capabilities against an existing owner-approved executor; require effective startup readback and harmless probes before task dispatch. Never infer permissions from a local/durable label, change security policy, or waive target gates. Ordinary reads need no launch gate.\n"
        "For persistent GNU Screen workers, read " + str(resources / "docs/SCREEN_LAUNCH.md") + ". Use guarded creation on the selected host; a provisional Screen container or a queued keystroke is not command proof. Preserve existing sessions and reconcile unknown writers before retry or transfer.\n"
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
    source_roots = [] if agents_only else (
        [resources / "skills" / name for name in selected]
        if selected is not None else [resources / "skills"]
    )
    for source_root in source_roots:
        for src in sorted(source_root.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(resources / "skills").as_posix()
            target = within(skills_home, rel)
            paths[str(target)] = src.read_bytes()
    conflicts = []
    receipt_path = codex_home / "agentos-integration.json"
    receipt_before = _current_bytes(receipt_path)
    previous = (
        read_json(receipt_path)
        if receipt_before is not None
        else {}
    )
    if _current_bytes(receipt_path) != receipt_before:
        raise GateError("integration_target_changed_replan:" + str(receipt_path))
    managed = previous.get("managed_files", {})
    if not isinstance(managed, dict):
        raise GateError("integration_managed_files_invalid")
    observed = {}
    for name, data in paths.items():
        path = Path(name)
        original = agents_before if path == agents else _current_bytes(path)
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
        "managed_files": {**(managed if agents_only or selected is not None else {}),
                          **{p: sha(d) for p, d in paths.items()}},
        "agents_only": agents_only,
        "skill_selection": {
            "mode": "AGENTS_ONLY" if agents_only else "EXPLICIT" if selected is not None else "ALL_SHIPPED",
            "names": selected,
            "unselected_files_verified": False,
        },
        "required_config": {},
        "note": (
            "Before applying changed shared inputs, qualify declared consumers per "
            "docs/UPDATE_VERIFICATION.md. Read back changed client integration in a fresh "
            "session and verify each affected consumer's next permitted dependent request. "
            "Preserve existing client configuration and keep retired AgentOS hooks disabled."
        ),
    }
    if not apply or conflicts:
        return report
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
        if _current_bytes(override) != override_bytes:
            raise GateError("integration_target_changed_replan:" + str(override))
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
            _recover_transaction(journal, codex_home, skills_home, user_home, **recovery_options)
            raise
        journal.unlink()
    return report


def command(argv: list[str], home: Path) -> tuple[dict, int]:
    p = argparse.ArgumentParser(prog="agentos integrate")
    p.add_argument("target", choices=["codex"])
    p.add_argument("--codex-home", type=Path)
    p.add_argument("--skills-home", type=Path, default=Path.home() / ".agents/skills")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--agents-only", action="store_true",
                   help="Update the managed instruction block without copying skills.")
    p.add_argument("--skill", action="append", dest="skills", metavar="NAME",
                   help="Copy only this exact shipped skill; repeat for more. Incompatible with --agents-only.")
    a = p.parse_args(argv)
    codex_home = a.codex_home
    if codex_home is None:
        env_home = os.environ.get("CODEX_HOME", "").strip()
        codex_home = Path(env_home) if env_home else Path.home() / ".codex"
    result = install(codex_home, a.skills_home, home, apply=a.apply,
                     agents_only=a.agents_only, skills=a.skills)
    return result, 0 if result["status"] in {"PLANNED", "INSTALLED_MANUAL_WORKFLOW"} else 2
