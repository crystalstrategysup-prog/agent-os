"""Project intake, document readiness and source-bound local result evidence.

The machine validates structural contracts and receipts; semantic correctness and
external authorization still require the named reviewer and the target system.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .doc_catalog import DOCS, FEATURES, TYPES, select
from .safeio import (
    GateError,
    atomic_bytes,
    atomic_json,
    digest,
    filemap,
    identifier,
    lock,
    nonempty,
    now,
    read_json,
    sha,
    within,
)

SKIP = {
    ".git",
    ".agentos",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
    ".coverage",
    ".DS_Store",
}
KINDS = (
    "observe",
    "docs",
    "implementation",
    "architecture",
    "integration",
    "data",
    "infrastructure",
    "security",
    "release",
    "incident",
)
QUESTIONS = {
    "objective": "Что нужно получить в этой задаче?",
    "why": "Зачем это нужно и какую проблему решает?",
    "outcome": "Как будет выглядеть проверяемый результат?",
    "scope_in": "Какие изменения разрешены?",
    "scope_out": "Что не входит в задачу?",
    "constraints": "Какие ограничения, риски и правила нельзя нарушать?",
    "operation": "Как это должно работать: основной путь и ошибки?",
    "authority": "Какое текущее поручение разрешает эти действия?",
}
CONTEXT_KEYS = ("purpose", "current_state", "boundaries", "constraints")


def root_path(root: Path) -> Path:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise GateError("project_directory_missing")
    # A source project may have symlinks, but AgentOS metadata may not escape it.
    within(root, ".agentos/project.json")
    return root


def project_file(root: Path) -> Path:
    return within(root, ".agentos/project.json")


def load_project(root: Path) -> dict:
    value = read_json(project_file(root))
    if value.get("schema") != "agentos.project/v1":
        raise GateError("unsupported_project_schema")
    select(value["types"], value["features"])
    return value


def task_path(root: Path, task_id: str) -> Path:
    return within(root, ".agentos/tasks/" + identifier(task_id) + "/task.json")


def load_task(root: Path, task_id: str) -> dict:
    task = read_json(task_path(root, task_id))
    if task.get("schema") != "agentos.project-task/v1" or task.get("id") != task_id:
        raise GateError("unsupported_or_mismatched_task")
    return task


def _event(root: Path, task: dict, event: str, details: dict | None = None) -> None:
    path = within(root, f".agentos/tasks/{task['id']}/events.jsonl")
    row = {"at": now(), "event": event, "details": details or {}}
    prior = path.read_bytes() if path.exists() else b""
    if len(prior) > 4 * 1024 * 1024:
        raise GateError("event_log_limit")
    atomic_bytes(path, prior + (json.dumps(row, ensure_ascii=False) + "\n").encode())


def initialize(
    root: Path, name: str, types: list[str], features: list[str], context: dict
) -> dict:
    root = root_path(root)
    selection = select(types, features)
    for key in CONTEXT_KEYS:
        nonempty(context.get(key), key)
    nonempty(name, "project_name", 200)
    with lock(within(root, ".agentos/write.lock")):
        path = project_file(root)
        if path.exists():
            raise GateError("project_exists_no_overwrite")
        value = {
            "schema": "agentos.project/v1",
            "id": "project-" + uuid.uuid4().hex[:16],
            "name": name,
            "types": sorted(set(types)),
            "features": sorted(set(features)),
            "context": context,
            "documents": {},
            "created_at": now(),
            "revision": 1,
        }
        atomic_json(path, value)
        scaffold(root, selection["required"])
    return {
        "status": "DOCUMENTATION_REQUIRED",
        "project": value,
        "selection": selection,
    }


def scaffold(root: Path, doc_ids: list[str], task_id: str | None = None) -> list[str]:
    created = []
    for doc_id in doc_ids:
        title, headings = DOCS[doc_id]
        rel = (
            f"docs/agentos/stages/{task_id}.md"
            if doc_id == "stage" and task_id
            else f"docs/agentos/{doc_id.upper()}.md"
        )
        path = within(root, rel)
        if path.exists():
            continue
        body = f"# {title}\n\n"
        if task_id and doc_id == "stage":
            body += f"Задача: `{task_id}`\n\n"
        body += "Статус: draft. Заполнить по фактам; шаблон не проходит gate.\n\n"
        for heading in headings:
            body += f"## {heading}\n\n[REQUIRED] Укажите сведения и источник.\n\n"
        atomic_bytes(path, body.encode(), 0o644)
        created.append(rel)
    return created


def questionnaire(root: Path, answers: dict | None = None) -> dict:
    root = root_path(root)
    project = load_project(root) if project_file(root).exists() else None
    answers = answers or {}
    return {
        "schema": "agentos.questionnaire/v1",
        "existing_project": bool(project),
        "known_context": project["context"] if project else {},
        "project_types": project["types"] if project else [],
        "questions": [
            {"id": key, "question": value}
            for key, value in QUESTIONS.items()
            if not isinstance(answers.get(key), str) or not answers[key].strip()
        ],
        "additional_required": ["change_kind", "write_paths", "acceptance", "checks"],
        "rule": "Use verified project facts first; ask the owner only unresolved material questions.",
    }


def _answers(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise GateError("answers_must_be_object")
    for key in QUESTIONS:
        nonempty(raw.get(key), key)
    if raw.get("change_kind") not in KINDS:
        raise GateError("invalid_change_kind")
    if not isinstance(raw.get("write_paths"), list):
        raise GateError("write_paths_required")
    for entry in raw["write_paths"]:
        if (
            not isinstance(entry, str)
            or not entry
            or entry.startswith("/")
            or ".." in Path(entry).parts
        ):
            raise GateError("invalid_write_path")
        if "\\" in entry or entry.startswith(".git/") or entry == ".git":
            raise GateError("invalid_write_path")
    acceptance = raw.get("acceptance")
    checks = raw.get("checks")
    if not isinstance(acceptance, list) or not acceptance or len(acceptance) > 100:
        raise GateError("acceptance_required")
    if not isinstance(checks, list) or not checks or len(checks) > 100:
        raise GateError("checks_required")
    ids = []
    for check in checks:
        if not isinstance(check, dict):
            raise GateError("invalid_check_record")
        ids.append(identifier(check.get("id")))
        argv = check.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or len(argv) > 128
            or any(
                not isinstance(x, str) or not x or len(x) > 8192 or "\x00" in x
                for x in argv
            )
        ):
            raise GateError("invalid_check_argv")
        if (
            not isinstance(check.get("timeout", 120), int)
            or not 1 <= check.get("timeout", 120) <= 3600
        ):
            raise GateError("invalid_check_timeout")
    if len(set(ids)) != len(ids):
        raise GateError("duplicate_check_id")
    acc_ids = []
    for item in acceptance:
        if not isinstance(item, dict):
            raise GateError("invalid_acceptance_record")
        acc_ids.append(identifier(item.get("id")))
        nonempty(item.get("criterion"), "acceptance_criterion")
        refs = item.get("checks")
        if not isinstance(refs, list) or not refs or any(c not in ids for c in refs):
            raise GateError("acceptance_check_mapping_required")
    if len(set(acc_ids)) != len(acc_ids):
        raise GateError("duplicate_acceptance_id")
    if raw["change_kind"] == "observe" and raw["write_paths"]:
        raise GateError("observe_cannot_authorize_product_writes")
    return raw


def enter(
    root: Path,
    answers: dict,
    *,
    session_id: str,
    turn_id: str,
    user_home: Path,
    resume_task: str | None = None,
) -> dict:
    """Every distinct task/turn has a fresh receipt. Resume invalidates readiness."""
    from .hooks import bind_turn, turn_path

    root = root_path(root)
    answers = _answers(answers)
    nonempty(session_id, "session_id", 200)
    nonempty(turn_id, "turn_id", 200)
    pending_path = turn_path(user_home, session_id)
    if pending_path.exists():
        pending = read_json(pending_path)
        if pending["turn_id"] != turn_id or pending["root"] != str(root):
            raise GateError("turn_binding_mismatch_reenter_correct_turn")
    with lock(within(root, ".agentos/write.lock")):
        project = load_project(root)
        active = project.get("active_task")
        if active and active != resume_task:
            previous = load_task(root, active)
            if previous["status"] not in {"CLOSED", "CHECKPOINT"}:
                raise GateError("active_task_requires_resume_or_checkpoint")
        selection = select(
            project["types"], project["features"], answers["change_kind"]
        )
        if resume_task:
            task = load_task(root, resume_task)
            if task["status"] == "CLOSED":
                raise GateError("closed_task_is_immutable_start_new_task")
            task["answers"] = answers
            task["revision"] += 1
            task.pop("ready", None)
            task["receipts"] = []
        else:
            task_id = "task-" + uuid.uuid4().hex[:16]
            task = {
                "schema": "agentos.project-task/v1",
                "id": task_id,
                "project_id": project["id"],
                "created_at": now(),
                "revision": 1,
                "answers": answers,
                "receipts": [],
            }
        task.update(
            {
                "status": "INTAKE",
                "selection": selection,
                "session_id": session_id,
                "turn_id": turn_id,
                "entered_at": now(),
                "foundation_version": __version__,
            }
        )
        atomic_json(task_path(root, task["id"]), task)
        project["active_task"] = task["id"]
        atomic_json(project_file(root), project)
        created = scaffold(root, selection["required"], task["id"])
        _event(
            root, task, "ENTER", {"revision": task["revision"], "selection": selection}
        )
    bind_turn(user_home, session_id, turn_id, root, task["id"])
    return {
        "status": "INTAKE",
        "task_id": task["id"],
        "required_documents": selection,
        "created_drafts": created,
        "missing_documents": document_check(root, task)["errors"],
    }


def register_document(
    root: Path,
    doc_id: str,
    relative: str,
    owner: str,
    source: str,
    summary: str,
    task_id: str | None = None,
) -> dict:
    root = root_path(root)
    if doc_id not in DOCS:
        raise GateError("unknown_document_id")
    nonempty(owner, "document_owner", 200)
    nonempty(source, "document_source")
    nonempty(summary, "document_summary")
    path = within(root, relative, allow_missing=False)
    if path.stat().st_size > 512 * 1024:
        raise GateError("document_size_limit")
    content = path.read_text(encoding="utf-8")
    nonempty(content, "document_body", 512 * 1024)
    if len(content.strip()) < 100:
        raise GateError("document_too_short")
    if doc_id == "stage":
        if not task_id:
            raise GateError("stage_task_binding_required")
        load_task(root, task_id)
        if task_id not in content:
            raise GateError("stage_must_name_task")
    with lock(within(root, ".agentos/write.lock")):
        project = load_project(root)
        old = project["documents"].get(doc_id, {})
        record = {
            "id": doc_id,
            "path": relative,
            "owner": owner,
            "source": source,
            "summary": summary,
            "sha256": sha(path.read_bytes()),
            "reviewed_at": now(),
            "revision": old.get("revision", 0) + 1,
            "task_id": task_id,
            "status": "current",
        }
        project["documents"][doc_id] = record
        atomic_json(project_file(root), project)
    return record


def document_check(root: Path, task: dict) -> dict:
    project = load_project(root)
    errors = []
    current = {}
    for doc_id in task["selection"]["required"]:
        record = project["documents"].get(doc_id)
        if not record:
            errors.append("unregistered:" + doc_id)
            continue
        try:
            path = within(root, record["path"], allow_missing=False)
            nonempty(path.read_text(encoding="utf-8"), "document_body", 512 * 1024)
            current[doc_id] = sha(path.read_bytes())
            if current[doc_id] != record["sha256"] or record.get("status") != "current":
                errors.append("unreviewed_change:" + doc_id)
            if doc_id == "stage" and record.get("task_id") != task["id"]:
                errors.append("wrong_stage_task")
        except (GateError, OSError, UnicodeError) as e:
            errors.append("invalid:" + doc_id + ":" + type(e).__name__)
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "document_hashes": current,
        "documents_digest": digest(current),
    }


def source_snapshot(root: Path) -> dict:
    load_project(root)
    items = filemap(root, skip=SKIP)
    # Metadata/evidence and maintained document content have independent hashes.
    items = {
        p: h
        for p, h in items.items()
        if not p.startswith("docs/agentos/")
        and p != ".coverage"
        and not p.endswith((".pyc", ".pyo"))
        and not any(x.endswith(".egg-info") for x in Path(p).parts)
    }
    return {"files": items, "sha256": digest(items), "file_count": len(items)}


def _policy_digest(project: dict, task: dict) -> str:
    return digest(
        {
            "project_id": project["id"],
            "types": project["types"],
            "features": project["features"],
            "context": project["context"],
            "answers": task["answers"],
            "selection": task["selection"],
            "revision": task["revision"],
        }
    )


def ready(root: Path, task_id: str, reviewer: str) -> dict:
    root = root_path(root)
    nonempty(reviewer, "reviewer", 200)
    with lock(within(root, ".agentos/write.lock")):
        task = load_task(root, task_id)
        project = load_project(root)
        if task["status"] not in {"INTAKE", "READY", "CHECKPOINT"}:
            raise GateError("ready_invalid_state")
        _answers(task["answers"])
        docs = document_check(root, task)
        if docs["status"] != "PASS":
            return {"status": "BLOCKED", "errors": docs["errors"]}
        task["ready"] = {
            "at": now(),
            "reviewer": reviewer,
            "docs": docs,
            "policy_digest": _policy_digest(project, task),
            "source": source_snapshot(root),
        }
        task["status"] = "READY"
        task["receipts"] = []
        atomic_json(task_path(root, task_id), task)
        _event(root, task, "READY", {"reviewer": reviewer})
    return {
        "status": "READY",
        "task_id": task_id,
        "note": "Structural gate; no external authority granted.",
    }


def check_ready(root: Path, task_id: str) -> dict:
    task = load_task(root, task_id)
    project = load_project(root)
    errors = []
    if task["status"] not in {"READY", "VERIFYING"} or not task.get("ready"):
        errors.append("readiness_required")
    elif task["ready"]["policy_digest"] != _policy_digest(project, task):
        errors.append("scope_changed_reenter_required")
    errors += document_check(root, task)["errors"]
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "task_id": task_id,
    }


def _scrub(text: str) -> str:
    text = re.sub(
        r"(?i)(?:sk-[A-Za-z0-9_-]{16,}|\b\d{6,12}:[A-Za-z0-9_-]{25,})",
        "[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?im)^.*(?:password|secret|api[_-]?key|access[_-]?token)\s*[:=].*$",
        "[REDACTED LINE]",
        text,
    )
    return text[-200000:]


def run_check(root: Path, task_id: str, check_id: str) -> dict:
    root = root_path(root)
    with lock(within(root, ".agentos/write.lock")):
        gate = check_ready(root, task_id)
        if gate["status"] != "PASS":
            return gate
        task = load_task(root, task_id)
        check = next(
            (c for c in task["answers"]["checks"] if c["id"] == check_id), None
        )
        if not check:
            raise GateError("check_not_in_stage_contract")
        before = source_snapshot(root)
        started = now()
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        # shell=False is not a sandbox. These are trusted, stage-reviewed programs.
        with tempfile.TemporaryFile() as capture:
            try:
                result = subprocess.run(
                    check["argv"],
                    cwd=root,
                    env=env,
                    stdout=capture,
                    stderr=subprocess.STDOUT,
                    timeout=check.get("timeout", 120),
                    check=False,
                )
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 124
                capture.write(b"\nCHECK TIMEOUT\n")
            except OSError as e:
                code = 127
                capture.write(("CHECK LAUNCH FAILED: " + type(e).__name__).encode())
            length = capture.seek(0, 2)
            capture.seek(max(0, length - 200000))
            output = capture.read(200000).decode("utf-8", "replace")
        after = source_snapshot(root)
        receipt_id = uuid.uuid4().hex
        log_rel = f".agentos/tasks/{task_id}/evidence/{receipt_id}.log"
        log = _scrub(output).encode()
        atomic_bytes(within(root, log_rel), log)
        status = "PASS" if code == 0 and before["sha256"] == after["sha256"] else "FAIL"
        receipt = {
            "schema": "agentos.check-receipt/v1",
            "id": receipt_id,
            "check_id": check_id,
            "task_id": task_id,
            "task_revision": task["revision"],
            "status": status,
            "started_at": started,
            "finished_at": now(),
            "return_code": code,
            "source_before": before["sha256"],
            "source_after": after["sha256"],
            "policy_digest": task["ready"]["policy_digest"],
            "argv": check["argv"],
            "log": log_rel,
            "log_sha256": sha(log),
            "foundation_version": __version__,
            "executor_module_sha256": sha(Path(__file__).read_bytes()),
            "scope": "local_process_only",
            "external_runtime_proven": False,
        }
        atomic_json(
            within(root, f".agentos/tasks/{task_id}/evidence/{receipt_id}.json"),
            receipt,
        )
        task["receipts"].append(receipt_id)
        task["status"] = "VERIFYING"
        atomic_json(task_path(root, task_id), task)
        _event(
            root,
            task,
            "CHECK",
            {"id": receipt_id, "check_id": check_id, "status": status},
        )
    return receipt


def assess(root: Path, task_id: str) -> dict:
    root = root_path(root)
    task = load_task(root, task_id)
    gate = check_ready(root, task_id)
    errors = list(gate["errors"])
    snapshot = source_snapshot(root)
    latest = {}
    for rid in task["receipts"]:
        receipt = read_json(
            within(root, f".agentos/tasks/{task_id}/evidence/{identifier(rid)}.json")
        )
        latest[receipt["check_id"]] = receipt
    for check in task["answers"]["checks"]:
        item = latest.get(check["id"])
        if not item:
            errors.append("missing_check:" + check["id"])
            continue
        try:
            age = (
                datetime.now(UTC) - datetime.fromisoformat(item["finished_at"])
            ).total_seconds()
            valid = (
                item["status"] == "PASS"
                and item["return_code"] == 0
                and item["task_id"] == task_id
                and item["task_revision"] == task["revision"]
                and item["source_before"] == item["source_after"] == snapshot["sha256"]
                and item["policy_digest"] == task["ready"]["policy_digest"]
                and item["argv"] == check["argv"]
                and 0 <= age <= 86400
                and item.get("executor_module_sha256")
                == sha(Path(__file__).read_bytes())
                and item.get("foundation_version") == __version__
                and sha(within(root, item["log"], allow_missing=False).read_bytes())
                == item["log_sha256"]
            )
        except (KeyError, ValueError, OSError):
            valid = False
        if not valid:
            errors.append("invalid_or_stale_check:" + check["id"])
    baseline = task.get("ready", {}).get("source", {}).get("files", {})
    changed = sorted(
        p
        for p in set(baseline) | set(snapshot["files"])
        if baseline.get(p) != snapshot["files"].get(p)
    )
    write_paths = task["answers"]["write_paths"]
    out_of_scope = [
        p
        for p in changed
        if not any(
            p == a.rstrip("/") or p.startswith(a.rstrip("/") + "/") or a == "."
            for a in write_paths
        )
    ]
    if out_of_scope:
        errors.append("out_of_scope_changes")
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "changed_files": changed,
        "out_of_scope": out_of_scope,
        "source_sha256": snapshot["sha256"],
        "checks": sorted(latest),
        "external_runtime_proven": False,
    }


def close(root: Path, task_id: str, review: dict) -> dict:
    root = root_path(root)
    for key in ("reviewer", "summary", "next_step", "limitations"):
        nonempty(review.get(key), key)
    if review.get("scope_reviewed") is not True:
        raise GateError("scope_review_required")
    with lock(within(root, ".agentos/write.lock")):
        task = load_task(root, task_id)
        assessment = assess(root, task_id)
        if assessment["status"] != "PASS":
            return assessment
        expected = {a["id"] for a in task["answers"]["acceptance"]}
        if set(review.get("accepted_criteria", [])) != expected:
            raise GateError("semantic_acceptance_review_required")
        if set(review.get("reviewed_documents", [])) != set(
            task["selection"]["required"]
        ):
            raise GateError("document_closeout_review_required")
        # Local receipts do not authorize a claim about a remote service.
        if review.get("deployment_status") not in {
            "not_requested",
            "pending_target_verification",
        }:
            raise GateError("external_deployment_requires_separate_target_receipt")
        task["status"] = "CLOSED"
        task["closed_at"] = now()
        task["closeout"] = {
            "review": review,
            "assessment": assessment,
            "documents": document_check(root, task),
        }
        atomic_json(task_path(root, task_id), task)
        report = (
            f"# Результат {task_id}\n\nСтатус: CLOSED (локальный этап).\n\n"
            + review["summary"]
        )
        report += "\n\n## Ограничения\n\n" + review["limitations"]
        report += "\n\n## Следующий этап\n\n" + review["next_step"] + "\n"
        atomic_bytes(
            within(root, f"docs/agentos/results/{task_id}.md"), report.encode(), 0o644
        )
        _event(
            root,
            task,
            "CLOSE",
            {"reviewer": review["reviewer"], "source": assessment["source_sha256"]},
        )
    return {
        "status": "CLOSED",
        "task_id": task_id,
        "assessment": assessment,
        "deployment_status": review["deployment_status"],
    }


def checkpoint(root: Path, task_id: str, reason: str, next_step: str) -> dict:
    nonempty(reason, "checkpoint_reason")
    nonempty(next_step, "checkpoint_next_step")
    root = root_path(root)
    with lock(within(root, ".agentos/write.lock")):
        task = load_task(root, task_id)
        if task["status"] == "CLOSED":
            raise GateError("closed_task_is_immutable")
        task["status"] = "CHECKPOINT"
        task["checkpoint"] = {
            "at": now(),
            "reason": reason,
            "next_step": next_step,
            "complete": False,
        }
        atomic_json(task_path(root, task_id), task)
        _event(root, task, "CHECKPOINT", task["checkpoint"])
    return {"status": "CHECKPOINT", "complete": False, "task_id": task_id}


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentos project")
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init")
    init.add_argument("--name", required=True)
    init.add_argument("--type", action="append", choices=TYPES, required=True)
    init.add_argument("--feature", action="append", choices=FEATURES, default=[])
    init.add_argument("--context", type=Path, required=True)
    ask = sub.add_parser("questions")
    ask.add_argument("--answers", type=Path)
    ent = sub.add_parser("enter")
    ent.add_argument("--answers", type=Path)
    ent.add_argument("--interactive", action="store_true")
    ent.add_argument("--session", required=True)
    ent.add_argument("--turn", required=True)
    ent.add_argument("--resume-task")
    doc = sub.add_parser("document")
    for name in ("id", "path", "owner", "source", "summary"):
        doc.add_argument("--" + name, required=True)
    doc.add_argument("--task")
    read = sub.add_parser("ready")
    read.add_argument("--reviewer", required=True)
    chk = sub.add_parser("check")
    chk.add_argument("--check-id", required=True)
    sub.add_parser("assess")
    sub.add_parser("status")
    fin = sub.add_parser("close")
    fin.add_argument("--review", type=Path, required=True)
    cp = sub.add_parser("checkpoint")
    cp.add_argument("--reason", required=True)
    cp.add_argument("--next-step", required=True)
    sub.add_parser("gate")
    sub.add_parser("snapshot")
    for name, child in sub.choices.items():
        child.add_argument("--root", type=Path, default=Path.cwd())
        if name in {
            "ready",
            "check",
            "assess",
            "status",
            "close",
            "checkpoint",
            "gate",
        }:
            child.add_argument("--task", required=True)
    return parser


def command(argv: list[str], user_home: Path) -> tuple[dict, int]:
    if argv and argv[0] == "observe":
        from .observation import command as observation_command

        return observation_command(argv[1:], user_home)
    args = make_parser().parse_args(argv)
    root = args.root
    if args.action == "init":
        result = initialize(
            root, args.name, args.type, args.feature, read_json(args.context)
        )
    elif args.action == "questions":
        result = questionnaire(root, read_json(args.answers) if args.answers else None)
    elif args.action == "enter":
        answers = read_json(args.answers) if args.answers else {}
        if args.interactive:
            for key, question in QUESTIONS.items():
                if not answers.get(key):
                    answers[key] = input(question + " ")
            for key in ("change_kind",):
                if not answers.get(key):
                    answers[key] = input(key + ": ")
            for key in ("write_paths", "acceptance", "checks"):
                if key not in answers:
                    answers[key] = json.loads(input(key + " (JSON): "))
        result = enter(
            root,
            answers,
            session_id=args.session,
            turn_id=args.turn,
            user_home=user_home,
            resume_task=args.resume_task,
        )
    elif args.action == "document":
        result = register_document(
            root, args.id, args.path, args.owner, args.source, args.summary, args.task
        )
    elif args.action == "ready":
        result = ready(root, args.task, args.reviewer)
    elif args.action == "gate":
        result = check_ready(root, args.task)
    elif args.action == "check":
        result = run_check(root, args.task, args.check_id)
    elif args.action == "assess":
        result = assess(root, args.task)
    elif args.action == "status":
        result = load_task(root, args.task)
    elif args.action == "snapshot":
        result = source_snapshot(root)
    elif args.action == "close":
        result = close(root, args.task, read_json(args.review))
    else:
        result = checkpoint(root, args.task, args.reason, args.next_step)
    return result, (2 if result.get("status") in {"BLOCKED", "FAIL"} else 0)
