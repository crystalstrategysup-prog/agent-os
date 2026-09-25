"""Optional source-hash audit receipt. Never a prerequisite for ordinary reads."""

from __future__ import annotations

import argparse
from pathlib import Path

from .safeio import (
    GateError,
    atomic_json,
    digest,
    lock,
    nonempty,
    now,
    read_json_input,
    sha,
    within,
)


def verify(root: Path, receipt: dict) -> None:
    if (
        receipt.get("mode") != "observation"
        or receipt.get("product_writes_authorized") is not False
    ):
        raise GateError("invalid_observation_receipt")
    for source in receipt.get("sources", []):
        path = within(root, source["path"], allow_missing=False)
        if sha(path.read_bytes()) != source["sha256"]:
            raise GateError("observation_source_changed:" + source["path"])
    if not receipt.get("sources"):
        raise GateError("observation_sources_required")


def record(
    root: Path, answers: dict, home: Path, session_id: str, turn_id: str
) -> dict:
    from .overlay import validate_roots

    validate_roots(home)
    nonempty(session_id, "session_id", 200)
    nonempty(turn_id, "turn_id", 200)
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise GateError("project_directory_required")
    for key in (
        "objective",
        "why",
        "outcome",
        "authority",
        "summary",
        "limitations",
        "next_step",
    ):
        nonempty(answers.get(key), key)
    refs = answers.get("sources")
    if not isinstance(refs, list) or not 1 <= len(refs) <= 100:
        raise GateError("observation_sources_required")
    sources = []
    for relative in refs:
        path = within(root, relative, allow_missing=False)
        if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            raise GateError("invalid_observation_source")
        sources.append({"path": relative, "sha256": sha(path.read_bytes())})
    receipt = {
        "schema": "agentos.observation/v1",
        "mode": "observation",
        "at": now(),
        "product_writes_authorized": False,
        "answers": answers,
        "sources": sources,
        "scope": "read-only findings about listed files; no whole-tree immutability claim",
    }
    # Optional observations never bind or overwrite a project task/turn receipt.
    relative = "state/observations/" + digest([session_id, turn_id, str(root)]) + ".json"
    receipt.update(session_id=session_id, turn_id=turn_id, root=str(root))
    with lock(within(home, "state/observations.lock")):
        path = within(home, relative)
        if path.exists():
            raise GateError("observation_receipt_exists_use_new_turn")
        atomic_json(path, receipt)
    return {
        "status": "OBSERVATION_RECORDED",
        "receipt_sha256": digest(receipt),
        "receipt_path": relative,
        "project_writes": [],
        "external_runtime_proven": False,
    }


def command(argv: list[str], home: Path) -> tuple[dict, int]:
    p = argparse.ArgumentParser(prog="agentos project observe")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--answers", type=Path, required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--turn", required=True)
    a = p.parse_args(argv)
    return record(a.root, read_json_input(a.answers), home, a.session, a.turn), 0
