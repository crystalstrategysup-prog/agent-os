"""Read only selected project metadata, without admission, repair or discovery.

Descriptor-relative reads reject aliases and special files. Like safeio, this is
not a security boundary against a hostile process with the same OS identity.
The result qualifies only the named local surfaces, never a whole project.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import re
import stat
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .safeio import GateError, MAX_JSON, _parse_json, sha

SCHEMA = "agentos.project-diagnostics/v1"
MAX_DOCUMENT = 512 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_REFERENCES = 256
MAX_LINKS = 128
MAX_FINDINGS = 128
MAX_STDOUT_BYTES = 32 * 1024
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,99}\Z")
_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TERMINAL = frozenset({"CLOSED", "CHECKPOINT"})
_MARKERS = (
    ".agentos/entry-transaction.json", ".agentos/scoped-transaction.json",
    ".agentos/refusal-recovery-transaction.json", ".agentos/refusal-recovery-pending",
    ".agentos/interrupted-continuation-pending.json", ".agentos/write.lock",
    ".atlas/IMPORT_PENDING.json", ".atlas/DOC_SYNC_PENDING.json", ".atlas/IMPORT.lock",
)


class _ReadFailure(Exception):
    def __init__(self, code):
        self.code = code


def _plain(value, limit):
    return (isinstance(value, str) and 0 < len(value) <= limit
            and not any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value))


def _parts(value):
    if (not _plain(value, 1000) or value.startswith("/") or "\\" in value
            or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise _ReadFailure("UNSAFE")
    return value.split("/")


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _os_failure(exc):
    if exc.errno == errno.ENOENT:
        return _ReadFailure("MISSING")
    if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
        return _ReadFailure("UNSAFE")
    return _ReadFailure("UNREADABLE")


class _Reader:
    def __init__(self, root):
        self.fd = None
        self.bytes_read = 0
        self.files_read = 0
        if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
                or os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd
                or os.stat not in os.supports_follow_symlinks):
            raise _ReadFailure("PLATFORM_NOT_QUALIFIED")
        value = os.fspath(root)
        if (not _plain(value, 4096) or "\\" in value or ".." in value.split("/")):
            raise _ReadFailure("UNSAFE")
        self.path = os.path.abspath(value)
        current = None
        try:
            current = os.open(os.path.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            for part in Path(self.path).parts[1:]:
                following = self._directory(current, part)
                os.close(current)
                current = following
            self.fd = current
            self.root_stat = os.fstat(current)
        except OSError as exc:
            if current is not None:
                os.close(current)
            raise _os_failure(exc) from None
        except BaseException:
            if current is not None:
                os.close(current)
            raise

    @staticmethod
    def _directory(parent, name):
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode):
            raise _ReadFailure("UNSAFE")
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        if (os.fstat(fd).st_dev, os.fstat(fd).st_ino) != (info.st_dev, info.st_ino):
            os.close(fd)
            raise _ReadFailure("CHANGED")
        return fd

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    @contextmanager
    def parent(self, relative):
        parts = _parts(relative)
        fd = os.dup(self.fd)
        try:
            for part in parts[:-1]:
                following = self._directory(fd, part)
                os.close(fd)
                fd = following
            yield fd, parts[-1]
        except OSError as exc:
            raise _os_failure(exc) from None
        finally:
            os.close(fd)

    def inspect(self, relative, *, directory=False):
        with self.parent(relative) as (parent, name):
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                return info
            if directory and stat.S_ISDIR(info.st_mode):
                return info
            raise _ReadFailure("UNSAFE")

    def read(self, relative, limit):
        with self.parent(relative) as (parent, name):
            fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise _ReadFailure("UNSAFE")
                if before.st_size > limit:
                    raise _ReadFailure("TOO_LARGE")
                if before.st_size + self.bytes_read > MAX_TOTAL_BYTES:
                    raise _ReadFailure("READ_LIMIT")
                allowed = min(limit, MAX_TOTAL_BYTES - self.bytes_read)
                chunks, size = [], 0
                while size <= allowed:
                    chunk = os.read(fd, min(65536, allowed + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                self.bytes_read += size
                self.files_read += 1
                if size > allowed:
                    raise _ReadFailure("TOO_LARGE" if allowed == limit else "READ_LIMIT")
                if _identity(before) != _identity(os.fstat(fd)) or size != before.st_size:
                    raise _ReadFailure("CHANGED")
                return b"".join(chunks)
            finally:
                os.close(fd)

    def json(self, relative):
        raw = self.read(relative, MAX_JSON)
        try:
            value = _parse_json(raw)
        except (ValueError, GateError, UnicodeError, RecursionError):
            raise _ReadFailure("INVALID") from None
        if not isinstance(value, dict):
            raise _ReadFailure("INVALID")
        return value, raw


class _Report:
    def __init__(self):
        self.value = {
            "schema": SCHEMA, "status": "OBSERVED", "effect": "READ_ONLY", "advisory": True,
            "root": {"state": "UNKNOWN"},
            "limits": {"json_bytes": MAX_JSON, "document_bytes": MAX_DOCUMENT,
                       "total_read_bytes": MAX_TOTAL_BYTES, "declared_references": MAX_REFERENCES,
                       "markdown_links": MAX_LINKS, "findings": MAX_FINDINGS,
                       "stdout_bytes": MAX_STDOUT_BYTES},
            "coverage": {"scope": "SELECTED_LOCAL_METADATA_ONLY", "complete": True,
                         "truncated": False, "source_inventory": "NOT_SCANNED",
                         "live_activity": "NOT_CHECKED", "external_bindings": "NOT_CHECKED",
                         "files_read": 0, "bytes_read": 0, "omitted": {}},
            "project": {"state": "UNKNOWN"},
            "documents": {"declared": 0, "examined": 0, "verified": 0, "records": []},
            "task": {"state": "UNKNOWN", "recorded_task_terminal": None,
                     "live_activity": "NOT_CHECKED", "writer_activity": "UNKNOWN"},
            "transactions": {"scope": "LISTED_MARKERS_ONLY", "state": "UNKNOWN", "holds": 0, "markers": []},
            "atlas": {"local_binding": "UNKNOWN", "coverage": "UNKNOWN",
                      "registry": "NOT_CHECKED", "custom_bindings": "NOT_CHECKED",
                      "references": []},
            "links": {"scope": "AGENTS.md_AND_README.md_LOCAL_MARKDOWN_LINKS_ONLY",
                      "entrypoints": [], "examined": 0, "records": []},
            "findings": [], "finding_counts": {},
            "next_action": {"code": "CONTINUE_AUTHORIZED_WORK", "subject": "selected-root",
                            "route": "existing-authorized-workflow",
                            "detail": "Continue independently authorized work; review observations only for the affected surface."},
        }
        self.references = 0
        self.action_rank = 3

    def issue(self, code, severity, subject, remediation, *, incomplete=False):
        v = self.value
        v["finding_counts"][code] = v["finding_counts"].get(code, 0) + 1
        if len(v["findings"]) < MAX_FINDINGS:
            v["findings"].append({"code": code, "severity": severity, "subject": subject,
                                  "remediation": remediation})
        else:
            v["coverage"]["truncated"] = True
            v["coverage"]["omitted"]["findings"] = v["coverage"]["omitted"].get("findings", 0) + 1
        rank = {"ERROR": 0, "WARNING": 1, "INFO": 3}[severity]
        if rank < self.action_rank:
            route = "existing-project-workflow"
            if code.startswith(("DOCUMENT_", "REFERENCE_", "STAGE_")):
                route = "agentos project document"
            elif code in {"PENDING_TRANSACTION", "LOCK_PRESENT"} or code.startswith("TRANSACTION_"):
                route = "existing-transaction-owner-and-reconciliation"
            elif code.startswith("ATLAS_"):
                route = "existing-explicit-atlas-binding"
            elif code.startswith("ROOT_"):
                route = "existing-filesystem-read-access"
            elif code.startswith(("MARKDOWN_", "ENTRY_DOCUMENT_")):
                route = "owning-project-documentation"
            v["next_action"] = {"code": code, "subject": subject, "route": route, "detail": remediation}
            self.action_rank = rank
        if incomplete:
            v["coverage"]["complete"] = False
        if severity in {"WARNING", "ERROR"}:
            v["status"] = "FINDINGS"

    def failure(self, prefix, subject, failure):
        missing = failure.code == "MISSING"
        self.issue(prefix + "_" + failure.code, "WARNING" if missing else "ERROR", subject,
                   "Have the owning writer verify this exact local reference and restore or reconcile it through the existing workflow.",
                   incomplete=not missing)
        if failure.code in {"READ_LIMIT", "TOO_LARGE"}:
            self.value["coverage"]["truncated"] = True

    def reference(self):
        if self.references >= MAX_REFERENCES:
            if self.references == MAX_REFERENCES:
                self.issue("REFERENCE_LIMIT", "WARNING", "declared-references",
                           "Use a separately scoped inspection for references beyond the diagnostic limit.", incomplete=True)
                self.value["coverage"]["truncated"] = True
            self.references += 1
            return False
        self.references += 1
        return True


def _metadata(reader, report, relative, prefix, *, optional=False):
    try:
        value, raw = reader.json(relative)
        return value, {"path": relative, "state": "READ", "sha256": sha(raw), "bytes": len(raw)}
    except _ReadFailure as exc:
        if not (optional and exc.code == "MISSING"):
            report.failure(prefix, relative, exc)
        return None, {"path": relative, "state": exc.code}


def _pin(reader, report, record, subject, *, limit=MAX_DOCUMENT):
    row = {"subject": subject, "state": "INVALID"}
    if not report.reference():
        row["state"] = "NOT_CHECKED_LIMIT"
        return row
    if not isinstance(record, dict):
        report.failure("REFERENCE", subject, _ReadFailure("INVALID"))
        return row
    try:
        _parts(record.get("path"))
    except _ReadFailure as exc:
        report.failure("REFERENCE", subject, exc)
        row["state"] = exc.code
        return row
    row["path"] = record["path"]
    expected = record.get("sha256")
    size = record.get("bytes")
    if (not isinstance(expected, str) or not _HASH.fullmatch(expected)
            or ("bytes" in record and (type(size) is not int or size < 0))):
        report.failure("REFERENCE_PIN", row["path"], _ReadFailure("INVALID"))
        return row
    row["expected_sha256"] = expected
    try:
        raw = reader.read(record["path"], limit)
    except _ReadFailure as exc:
        report.failure("DOCUMENT", row["path"], exc)
        row["state"] = exc.code
        return row
    row.update(actual_sha256=sha(raw), bytes=len(raw))
    row["state"] = "VERIFIED" if row["actual_sha256"] == expected and (size is None or size == len(raw)) else "STALE"
    if row["state"] == "STALE":
        report.issue("DOCUMENT_HASH_MISMATCH", "WARNING", row["path"],
                     "Review the changed document with its owning writer before updating its declared pin.")
    return row


def _project(reader, report):
    v = report.value
    project, observation = _metadata(reader, report, ".agentos/project.json", "PROJECT_METADATA")
    v["project"] = observation
    if project is None:
        v["task"]["state"] = "NOT_RESOLVED"
        return
    if project.get("schema") != "agentos.project/v1" or not isinstance(project.get("documents"), dict):
        report.failure("PROJECT_METADATA", ".agentos/project.json", _ReadFailure("INVALID"))
        v["project"]["state"] = "INVALID"
        return
    project_id = project.get("id")
    if not isinstance(project_id, str) or not _ID.fullmatch(project_id):
        report.failure("PROJECT_ID", ".agentos/project.json", _ReadFailure("INVALID"))
        project_id = None
    else:
        v["project"]["id"] = project_id
    records = project["documents"]
    v["documents"]["declared"] = len(records)
    for index, (doc_id, record) in enumerate(records.items()):
        if index >= MAX_REFERENCES:
            report.reference()
            break
        subject = doc_id if isinstance(doc_id, str) and _ID.fullmatch(doc_id) else "document#" + str(index + 1)
        if subject != doc_id:
            report.failure("DOCUMENT_ID", subject, _ReadFailure("INVALID"))
        row = _pin(reader, report, record, subject)
        if isinstance(record, dict) and record.get("status") != "current":
            report.issue("DOCUMENT_REVIEW_STALE", "WARNING", row.get("path", subject),
                         "Have the owning writer review the document's recorded status.")
            if row["state"] == "VERIFIED":
                row["state"] = "STALE"
        v["documents"]["records"].append(row)
        v["documents"]["examined"] += 1
        v["documents"]["verified"] += row["state"] == "VERIFIED"
    pointer = project.get("active_task")
    if pointer is None:
        v["task"]["state"] = "NO_ACTIVE_POINTER"
        return
    if not isinstance(pointer, str) or not _TASK_ID.fullmatch(pointer):
        report.failure("ACTIVE_TASK_POINTER", ".agentos/project.json", _ReadFailure("INVALID"))
        return
    task_path = ".agentos/tasks/" + pointer + "/task.json"
    v["task"]["active_pointer"] = pointer
    task, observation = _metadata(reader, report, task_path, "TASK_METADATA")
    v["task"].update(observation)
    if task is None:
        return
    if (task.get("schema") != "agentos.project-task/v1" or task.get("id") != pointer
            or project_id is None or task.get("project_id") != project_id):
        report.failure("TASK_BINDING", task_path, _ReadFailure("INVALID"))
        v["task"]["state"] = "INVALID"
        return
    status = task.get("status")
    if not isinstance(status, str) or re.fullmatch(r"[A-Z][A-Z0-9_]{0,39}", status) is None:
        report.failure("TASK_STATUS", task_path, _ReadFailure("INVALID"))
        v["task"]["state"] = "INVALID"
        return
    terminal = status in _TERMINAL
    v["task"].update(recorded_status=status, recorded_task_terminal=terminal,
                     state="RECORDED_TERMINAL" if terminal else "RECORDED_NONTERMINAL")
    if terminal:
        report.issue("ACTIVE_POINTER_TERMINAL", "INFO", task_path,
                     "Treat the terminal task as recorded history; establish current work and writer through the existing entry workflow.")
    selection = task.get("selection")
    required = selection.get("required") if isinstance(selection, dict) else None
    if (not isinstance(required, list) or len(required) > MAX_REFERENCES
            or any(not isinstance(x, str) or not _ID.fullmatch(x) for x in required)):
        report.failure("TASK_DOCUMENT_SELECTION", task_path, _ReadFailure("INVALID"))
        return
    for doc_id in required:
        if doc_id not in records:
            report.issue("DOCUMENT_UNREGISTERED", "WARNING", doc_id,
                         "Register the required document through the owning project's existing document workflow.")
    stage = records.get("stage")
    if not terminal and isinstance(stage, dict) and stage.get("task_id") != pointer:
        report.issue("STAGE_TASK_MISMATCH", "WARNING", "stage",
                     "Have the owning writer reconcile the stage document with the selected active task.")


def _transactions(reader, report):
    for relative in _MARKERS:
        row = {"path": relative}
        try:
            info = reader.inspect(relative, directory=True)
            row.update(state="PRESENT", kind="directory" if stat.S_ISDIR(info.st_mode) else "file")
            report.value["transactions"]["holds"] += 1
            report.issue("LOCK_PRESENT" if relative.endswith(".lock") else "PENDING_TRANSACTION",
                         "WARNING", relative,
                         "Ask the owning writer to inspect the existing lock or reconcile the original transaction; do not remove or replay it automatically.")
        except _ReadFailure as exc:
            row["state"] = exc.code
            if exc.code != "MISSING":
                report.failure("TRANSACTION_MARKER", relative, exc)
        report.value["transactions"]["markers"].append(row)
    result = report.value["transactions"]
    if all(row["state"] in {"PRESENT", "MISSING"} for row in result["markers"]):
        result["state"] = "HOLDS_PRESENT" if result["holds"] else "NO_LISTED_MARKERS"


def _upstream_selected_fields(value):
    """Qualify only declared metadata shape/paths; do not load an owning matrix."""
    try:
        if value.get("schema") != "atlas.upstream-binding/v1":
            return False
        project, matrix, history = value["project"], value["matrix"], value["history"]
        if (not isinstance(project, dict) or not isinstance(matrix, dict) or not isinstance(history, dict)
                or not isinstance(project.get("id"), str) or not _ID.fullmatch(project["id"])):
            return False
        for field in ("title", "objective", "writer", "authority_ref", "scope_note"):
            if not isinstance(project.get(field), str) or not 0 < len(project[field]) <= 20000:
                return False
        if not _plain(matrix.get("allowed_schema"), 1000):
            return False
        _parts(matrix["path"])
        _parts(value["output"])
        if not value["output"].startswith(".atlas/"):
            return False
        for field in ("paths", "directories"):
            rows = history[field]
            if not isinstance(rows, list) or len(rows) > 2000:
                return False
            for relative in rows:
                _parts(relative)
        documents = value["documents"]
        if not isinstance(documents, list) or len(documents) >= 198:
            return False
        for document in documents:
            if not isinstance(document, dict):
                return False
            _parts(document["path"])
        return True
    except (KeyError, TypeError, _ReadFailure):
        return False


def _atlas(reader, report):
    result = report.value["atlas"]
    present, unknown = False, False
    project, observation = _metadata(reader, report, ".atlas/project.json", "ATLAS_METADATA", optional=True)
    result["project_manifest"] = observation
    if project is not None:
        if (project.get("schema") != "atlas.project/v1"
                or not isinstance(project.get("id"), str) or not _ID.fullmatch(project["id"])
                or not isinstance(project.get("mode"), str) or project["mode"] not in {"native", "projection"}
                or not isinstance(project.get("documents"), dict)
                or not isinstance(project.get("work_files"), list)):
            report.failure("ATLAS_METADATA", ".atlas/project.json", _ReadFailure("INVALID"))
            unknown = True
        else:
            present = True
            result.update(project_id=project["id"], mode=project["mode"], validation="SELECTED_FIELDS_ONLY")
            result["references"].append(_pin(reader, report, project["documents"], "atlas-documents", limit=MAX_JSON))
            if result["references"][-1]["state"] != "VERIFIED":
                unknown = True
            coverage = project.get("coverage")
            if coverage is not None:
                if isinstance(coverage, dict) and isinstance(coverage.get("inventory"), dict):
                    result["references"].append(_pin(reader, report, coverage["inventory"], "atlas-inventory", limit=MAX_JSON))
                    if result["references"][-1]["state"] != "VERIFIED":
                        unknown = True
                else:
                    report.failure("ATLAS_COVERAGE", ".atlas/project.json", _ReadFailure("INVALID"))
                    unknown = True
            result["declared_work_files"] = len(project["work_files"])
            for index, relative in enumerate(project["work_files"]):
                if not report.reference():
                    break
                row = {"subject": "atlas-work#" + str(index + 1)}
                try:
                    _parts(relative)
                    row["path"] = relative
                    info = reader.inspect(relative)
                    row.update(state="PRESENT_NOT_READ", bytes=info.st_size)
                except _ReadFailure as exc:
                    row["state"] = exc.code
                    report.failure("ATLAS_WORK_REFERENCE", row.get("path", row["subject"]), exc)
                    unknown = True
                result["references"].append(row)
    elif observation["state"] != "MISSING":
        unknown = True
    upstream, observation = _metadata(reader, report, ".atlas/UPSTREAM.json", "ATLAS_UPSTREAM", optional=True)
    result["upstream_binding"] = observation
    if upstream is not None:
        if _upstream_selected_fields(upstream):
            present = True
            result["upstream_validation"] = "SELECTED_FIELDS_ONLY_SOURCE_NOT_READ"
        else:
            report.failure("ATLAS_UPSTREAM", ".atlas/UPSTREAM.json", _ReadFailure("INVALID"))
            unknown = True
    elif observation["state"] != "MISSING":
        unknown = True
    if unknown:
        result["local_binding"] = "UNKNOWN"
    elif present:
        result["local_binding"] = "PRESENT_AT_KNOWN_PATHS"
    else:
        try:
            reader.inspect(".atlas", directory=True)
            result["local_binding"] = "UNKNOWN"
        except _ReadFailure as exc:
            result["local_binding"] = "ABSENT_AT_KNOWN_PATHS" if exc.code == "MISSING" else "UNKNOWN"
            if exc.code != "MISSING":
                report.failure("ATLAS_DIRECTORY", ".atlas", exc)
        report.issue("ATLAS_BINDING_COVERAGE_UNKNOWN", "INFO", ".atlas",
                     "Resolve the project's existing explicit Atlas binding before concluding that Atlas is absent; do not initialize a second binding.")


_INLINE_LINK = re.compile(r'(?<!!)\[[^\]\r\n]{0,200}\]\((?:<([^>\r\n]+)>|([^\s)]+))(?:\s+["\'][^\r\n]*["\'])?\)')
_REFERENCE_LINK = re.compile(r'^ {0,3}\[[^\]\r\n]{1,200}\]:\s*(?:<([^>\r\n]+)>|(\S+))', re.M)


def _links(reader, report):
    result = report.value["links"]
    seen = set()
    for entry in ("AGENTS.md", "README.md"):
        try:
            raw = reader.read(entry, MAX_DOCUMENT)
            text = raw.decode("utf-8")
            result["entrypoints"].append({"path": entry, "state": "READ", "sha256": sha(raw), "bytes": len(raw)})
        except (UnicodeError, _ReadFailure) as exc:
            failure = exc if isinstance(exc, _ReadFailure) else _ReadFailure("INVALID")
            result["entrypoints"].append({"path": entry, "state": failure.code})
            if failure.code != "MISSING":
                report.failure("ENTRY_DOCUMENT", entry, failure)
            continue
        # Ignore fenced examples. This is a bounded link check, not a Markdown renderer.
        lines, fence = [], None
        for line in text.splitlines():
            marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
            if marker:
                token = marker.group(1)
                if fence is None:
                    fence = token
                elif token[0] == fence[0] and len(token) >= len(fence):
                    fence = None
                continue
            if fence is None:
                lines.append(line)
        text = "\n".join(lines)
        for pattern in (_INLINE_LINK, _REFERENCE_LINK):
            for match in pattern.finditer(text):
                target = match.group(1) or match.group(2)
                try:
                    if not _plain(target, 1000):
                        raise _ReadFailure("UNSAFE")
                    parsed = urlsplit(target)
                    if parsed.scheme or parsed.netloc or not parsed.path:
                        continue
                    relative = unquote(parsed.path, errors="strict")
                    if relative.startswith("./"):
                        relative = relative[2:]
                    if not relative.lower().endswith((".md", ".markdown")):
                        continue
                    if relative in seen:
                        continue
                    if len(seen) >= MAX_LINKS:
                        report.issue("MARKDOWN_LINK_LIMIT", "WARNING", entry,
                                     "Inspect additional declared local Markdown links in a separate bounded scope.", incomplete=True)
                        report.value["coverage"]["truncated"] = True
                        return
                    seen.add(relative)
                    _parts(relative)
                    row = {"source": entry, "path": relative}
                    try:
                        reader.inspect(relative)
                        row["state"] = "PRESENT_NOT_READ"
                    except _ReadFailure as exc:
                        row["state"] = exc.code
                        report.failure("MARKDOWN_LINK", relative, exc)
                except (ValueError, UnicodeError, _ReadFailure):
                    row = {"source": entry, "state": "UNSAFE"}
                    report.failure("MARKDOWN_LINK", entry, _ReadFailure("UNSAFE"))
                result["records"].append(row)
                result["examined"] += 1


def _finish(report):
    value = report.value
    coverage = value["coverage"]
    if not coverage["complete"] or coverage["truncated"]:
        coverage["complete"] = False
        if value["status"] != "NOT_QUALIFIED":
            value["status"] = "INCOMPLETE"
    def encoded():
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded()) + 1 > MAX_STDOUT_BYTES:
        value["status"] = "INCOMPLETE"
        coverage.update(complete=False, truncated=True)
        value["finding_counts"]["OUTPUT_LIMIT"] = 1
        lists = {"documents": value["documents"]["records"], "atlas_references": value["atlas"]["references"],
                 "links": value["links"]["records"], "findings": value["findings"]}
        while len(encoded()) + 1 > MAX_STDOUT_BYTES:
            populated = [(name, rows) for name, rows in lists.items() if rows]
            if not populated:
                raise GateError("diagnostic_output_bound")
            name, rows = max(populated, key=lambda pair: len(json.dumps(pair[1], ensure_ascii=False)))
            rows.pop()
            coverage["omitted"][name] = coverage["omitted"].get(name, 0) + 1
    return value


def diagnose(root):
    """Return metadata only. Never load user configuration or execute source text."""
    report = _Report()
    reader = None
    try:
        reader = _Reader(root)
        report.value["root"] = {"state": "OPENED", "path": reader.path,
                                "device": reader.root_stat.st_dev, "inode": reader.root_stat.st_ino}
        _project(reader, report)
        _transactions(reader, report)
        _atlas(reader, report)
        _links(reader, report)
    except _ReadFailure as exc:
        report.failure("ROOT", "selected-root", exc)
        report.value["coverage"]["complete"] = False
        if exc.code == "PLATFORM_NOT_QUALIFIED":
            report.value["status"] = "NOT_QUALIFIED"
    finally:
        if reader is not None:
            report.value["coverage"].update(bytes_read=reader.bytes_read, files_read=reader.files_read)
            reader.close()
    return _finish(report)


def command(argv):
    parser = argparse.ArgumentParser(prog="agentos project diagnose", allow_abbrev=False,
                                     description="Inspect bounded local metadata without initialization or repair.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    result = diagnose(args.root)
    # Observations are advisory, including stale/missing metadata. This command
    # is not an intake/READY prerequisite or an admission decision.
    return result, (0 if result["root"]["state"] == "OPENED" else 2)
