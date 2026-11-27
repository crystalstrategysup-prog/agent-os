"""Frozen revision checks prove byte identity under the retained guard only."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ".release/work-laws-v1.json"
DOCUMENTS = {
    "laws": ("docs/PROCESS.md", "src/agent_os/resources/docs/PROCESS.md"),
    "orientation": ("docs/WORK_ENVIRONMENT.md", "src/agent_os/resources/docs/WORK_ENVIRONMENT.md"),
}


def load_tool(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load_tool("frozen_work_public_validation", "tools/verify_public.py")
resource_sync = load_tool("frozen_work_resource_sync", "tools/sync_resources.py")


@pytest.fixture
def frozen_tree(tmp_path):
    root = tmp_path / "candidate"
    for relative in (MANIFEST, *DOCUMENTS["laws"], *DOCUMENTS["orientation"]):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    return root


def change_document(path, kind):
    raw = path.read_bytes()
    if kind == "laws":
        raw = raw.replace(b"## Solution integrity", b"## Unreviewed law change", 1)
    else:
        raw += b"\nUnreviewed orientation change.\n"
    path.write_bytes(raw)


def test_actual_current_revision_and_both_packaged_copies_match():
    assert validator.frozen_work_laws_errors(ROOT) == []


@pytest.mark.parametrize("kind", ["laws", "orientation"])
@pytest.mark.parametrize("target", ["source", "resource", "both"])
def test_unreviewed_source_resource_and_matching_pair_drift_refused(frozen_tree, kind, target):
    paths = DOCUMENTS[kind]
    selected = paths if target == "both" else (paths[0 if target == "source" else 1],)
    for relative in selected:
        change_document(frozen_tree / relative, kind)
    assert validator.frozen_work_laws_errors(frozen_tree) == [
        "frozen_work_content_changed:" + relative for relative in selected
    ]


def test_recomputing_manifest_pin_cannot_clear_guard(frozen_tree):
    for relative in DOCUMENTS["laws"]:
        change_document(frozen_tree / relative, "laws")
    text = (frozen_tree / DOCUMENTS["laws"][0]).read_text(encoding="utf-8")
    body = text.split("<!-- agentos:solution-integrity:start -->", 1)[1].split(
        "<!-- agentos:solution-integrity:end -->", 1)[0].strip().encode("utf-8")
    path = frozen_tree / MANIFEST
    manifest = json.loads(path.read_bytes())
    manifest["laws"].update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert validator.frozen_work_laws_errors(frozen_tree) == [
        "frozen_work_manifest_changed:" + MANIFEST
    ]


@pytest.mark.parametrize("relative,damage", [
    (MANIFEST, "missing"),
    (MANIFEST, "oversize"),
    (MANIFEST, "symlink"),
    ("docs/PROCESS.md", "missing-marker"),
    ("docs/PROCESS.md", "duplicate-marker"),
    ("docs/PROCESS.md", "utf8"),
    ("docs/WORK_ENVIRONMENT.md", "symlink"),
    ("docs/WORK_ENVIRONMENT.md", "oversize"),
    ("docs/WORK_ENVIRONMENT.md", "directory"),
])
def test_missing_invalid_or_unbounded_protected_file_fails_closed(frozen_tree, tmp_path, relative, damage):
    path = frozen_tree / relative
    raw = path.read_bytes()
    if damage == "missing":
        path.unlink()
    elif damage == "oversize":
        path.write_bytes(b"x" * ((4096 if relative == MANIFEST else 128 * 1024) + 1))
    elif damage == "symlink":
        outside = tmp_path / "unselected-target"
        outside.write_bytes(raw)
        path.unlink()
        path.symlink_to(outside)
    elif damage == "directory":
        path.unlink()
        path.mkdir()
    elif damage == "missing-marker":
        path.write_bytes(raw.replace(b"<!-- agentos:solution-integrity:end -->", b"", 1))
    elif damage == "duplicate-marker":
        path.write_bytes(raw + b"\n<!-- agentos:solution-integrity:start -->\n")
    elif damage == "utf8":
        path.write_bytes(raw + b"\xff")
    prefix = "frozen_work_manifest_invalid:" if relative == MANIFEST else "frozen_work_content_invalid:"
    assert validator.frozen_work_laws_errors(frozen_tree) == [prefix + relative]


def test_changes_outside_laws_leave_pin_intact_but_do_not_hide_mirror_drift(frozen_tree):
    path = frozen_tree / "docs/PROCESS.md"
    path.write_bytes(b"# New unrelated project note\n\n" + path.read_bytes())
    assert validator.frozen_work_laws_errors(frozen_tree) == []
    mirrored = resource_sync.synchronize(frozen_tree)
    assert mirrored["status"] == "FAIL"
    assert mirrored["changed"] == ["PROCESS.md"]
    assert mirrored["effects"] == "NONE"


def test_public_verifier_reports_guard_refusal_and_continues_privacy_scan(frozen_tree, monkeypatch):
    (frozen_tree / "pyproject.toml").write_bytes((ROOT / "pyproject.toml").read_bytes())
    (frozen_tree / MANIFEST).write_bytes(b"not-json\xff")
    (frozen_tree / "docs/PROCESS.md").write_bytes(b"invalid-utf8\xff")
    control = "PRIVATE-" + "DO-NOT-PUBLISH"
    (frozen_tree / "contaminated.txt").write_text(control, encoding="utf-8")
    monkeypatch.setattr(validator, "ROOT", frozen_tree)
    result = validator.verify()
    assert result["status"] == "FAIL"
    assert "frozen_work_manifest_changed:" + MANIFEST in result["errors"]
    assert "private_marker:contaminated.txt" in result["errors"]
    assert control not in repr(result)
