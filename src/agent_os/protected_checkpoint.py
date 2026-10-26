"""Explicit metadata-only checkpoint references; never publish config contents."""
from pathlib import Path, PurePosixPath

from .safeio import GateError, digest, sha
from .handoff_store import HandoffError, scan_secrets

SCHEMA = "agentos.protected-checkpoint-sources/v1"


def validate(root, task, snapshot, docs, request):
    """Validate bounded caller attestation; does not grant target authority."""
    if request is None:
        return {}
    def require(condition):
        if not condition:
            raise GateError("protected_checkpoint_request_invalid")
    require(isinstance(request, dict) and set(request) == {
        "schema", "root", "task_id", "revision", "task_sha256",
        "project_sha256", "source_sha256", "authority_ref", "sources"})
    require(request["schema"] == SCHEMA and request["root"] == str(root))
    require(request["task_id"] == task["id"] and type(request["revision"]) is int
            and request["revision"] == task["revision"])
    require(request["task_sha256"] == sha((root / ".agentos/tasks" / task["id"] / "task.json").read_bytes()))
    require(request["project_sha256"] == sha((root / ".agentos/project.json").read_bytes()))
    require(request["source_sha256"] == snapshot["sha256"])
    require(isinstance(request["authority_ref"], str) and 0 < len(request["authority_ref"]) <= 512)
    require(isinstance(request["sources"], list) and 0 < len(request["sources"]) <= 32)
    from .project import load_project
    project = load_project(root)
    document_paths = {project["documents"][key]["path"] for key in docs["document_hashes"]}
    result = {}
    for item in request["sources"]:
        require(isinstance(item, dict) and set(item) == {"path", "sha256", "bytes"})
        path = item["path"]
        require(isinstance(path, str) and 0 < len(path) <= 1024)
        parts = PurePosixPath(path)
        require(not parts.is_absolute() and path == parts.as_posix() and ".." not in parts.parts
                and "\\" not in path and "\x00" not in path and path not in result)
        require(parts.name == ".env" or parts.name.startswith(".env."))
        require(path not in document_paths and path not in snapshot.get("symlinks", {}))
        require(path in snapshot["files"] and item["sha256"] == snapshot["files"][path])
        require(type(item["bytes"]) is int and 0 < item["bytes"] <= 1024 * 1024)
        require(any(path == allowed or path.startswith(allowed.rstrip("/") + "/")
                    for allowed in task["answers"]["write_paths"]))
        result[path] = dict(item)
    return result


def reference(item, data):
    """Keep the existing scanner decisive; refuse safe or changed inputs."""
    if len(data) != item["bytes"] or sha(data) != item["sha256"]:
        raise GateError("protected_checkpoint_source_changed")
    try:
        scan_secrets(data)
    except HandoffError as exc:
        if exc.code != "SECRET_DETECTED":
            raise
    else:
        raise GateError("protected_checkpoint_source_not_sensitive")
    return {"schema": "agentos.protected-source-reference/v1", **item,
            "content_preservation": "external_required", "scanner": "SECRET_DETECTED",
            "content_embedded": False, "restore": "not_implemented"}
