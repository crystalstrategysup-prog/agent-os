"""Finite document growth in disposable native fixtures; never real NEXT."""
import copy
import importlib
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sys
import time

import pytest
from test_atlas_readable import isolated_engine

SCRIPTS = Path(__file__).resolve().parents[1] / "modules/atlas/skills/atlas/scripts"
with isolated_engine(SCRIPTS):
    atlas = importlib.import_module("atlas")
    nav = importlib.import_module("navigator")


@pytest.fixture(autouse=True)
def standalone_import_scope():
    global atlas, nav
    with isolated_engine(SCRIPTS):
        atlas = importlib.import_module("atlas")
        nav = importlib.import_module("navigator")
        yield

AT = "2026-10-21T00:00:00+00:00"


def pin(root, path):
    raw = (root / path).read_bytes()
    return {"path": path, "sha256": nav.digest(raw), "bytes": len(raw)}


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def add_documents(root, model, count):
    added = []
    for ordinal in range(len(model["documents"]), count):
        path = f"docs/capacity/doc-{ordinal:04}.md"
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        body = f"# Synthetic capacity document {ordinal}\n"
        ident = f"CAP-DOC-{ordinal:04}"
        version = "1"
        if ordinal == 200:
            ident, version = "DOC-ROUTING-4", "4"
            body = (body + "Synthetic routing v4, no target authority.\n").ljust(18944, "x")
        target.write_text(body)
        record = {"id": ident, "title": f"Synthetic capacity document {ordinal}",
                  **pin(root, path), "kind": "markdown", "version": version,
                  "lifecycle": "current", "source_ref": "Synthetic capacity fixture only",
                  "readback_at": AT, "evidence_state": "DESIGN", "execution": "NOT_RUN"}
        model["documents"].append(record)
        added.append(ident)
    return added


def save(root, model, index, *, native=False):
    (root / index).write_bytes(nav.canonical(model))
    if native:
        project = nav.parse((root / ".atlas/project.json").read_bytes())
        project["documents"] = pin(root, index)
        (root / ".atlas/project.json").write_bytes(nav.canonical(project))


def fixture(tmp_path, count=200, *, native=False):
    root = (tmp_path / "project").resolve()
    shutil.copytree(SCRIPTS.parents[2] / ("examples/workflow" if native else "examples/synthetic"), root)
    index = "docs/DOCS_INDEX.json" if native else "DOCS_INDEX.json"
    model = nav.parse((root / index).read_bytes())
    added = add_documents(root, model, count)
    # Match the observed 200-member shape, without any real project bodies.
    archived = sum(d["lifecycle"] == "archived" for d in model["documents"])
    for document in reversed(model["documents"]):
        if archived >= 39:
            break
        if document["id"] in added and document["lifecycle"] == "current":
            document["lifecycle"] = "archived"
            archived += 1
    model["release"] = {"id": "CAP-BASE", "created_at": AT, "previous": None}
    model["history"].append({"id": "CAP-BASE-EVENT", "at": AT, "kind": "DOCUMENTS_ADDED",
                             "summary": "Synthetic finite-capacity baseline", "entity_ids": added[:1]})
    save(root, model, index, native=native)
    return root, model, index, root / "output"


def advance(root, model, index, previous, *, native=False, count=None):
    added = add_documents(root, model, count) if count is not None else []
    when = (datetime.fromisoformat(AT) + timedelta(seconds=len(model["history"]))).isoformat()
    model["release"] = {"id": "CAP-NEXT-" + str(len(model["history"])), "created_at": when, "previous": previous}
    model["history"].append({"id": "CAP-EVENT-" + str(len(model["history"])), "at": when,
                             "kind": "DOCUMENTS_ADDED", "summary": "Synthetic explicit successor",
                             "entity_ids": added})
    save(root, model, index, native=native)


@pytest.mark.parametrize("count", [200, 201, 1000])
def test_finite_boundary_load_and_measured_bytes(tmp_path, count):
    root, model, index, _ = fixture(tmp_path, count)
    started = time.perf_counter()
    result = nav.load(root, index)
    elapsed = time.perf_counter() - started
    assert len(result["documents"]) == count
    assert result["input"]["documents"] == model["documents"]
    print("CAPACITY_METRIC " + json.dumps({"documents": count, "input_bytes": (root / index).stat().st_size,
          "selected_body_bytes": sum(d["bytes"] for d in model["documents"]),
          "load_elapsed_wall_seconds": elapsed, "CPU_measured": False}))


def test_schema_runtime_and_contract_bounds_are_synchronous():
    schema = nav.parse((SCRIPTS / "navigator.schema.json").read_bytes())
    limits = nav.parse((SCRIPTS / "OPERATIONS.json").read_bytes())["limits"]
    assert nav.VERSION == "DN-01.4"
    assert schema["properties"]["documents"]["maxItems"] == nav.MAX_DOCUMENTS == limits["max_selected_documents"] == 1000
    assert (nav.MAX_FILE, nav.MAX_TOTAL, nav.MAX_INPUT, atlas.MAX_SELECTED, nav.MAX_SNAPSHOT, nav.MAX_HTML) == (
        2*1024**2, 16*1024**2, 8*1024**2, 32*1024**2, 32*1024**2, 48*1024**2)
    assert limits["max_navigator_document_bytes_total"] == nav.MAX_TOTAL


@pytest.mark.parametrize("runtime_only", [False, True])
def test_1001_refused_by_each_guard_without_output_changes(tmp_path, monkeypatch, runtime_only):
    root, model, index, out = fixture(tmp_path)
    first = nav.build(root, index, out)
    advance(root, model, index, first["manifest_sha256"], count=1001)
    before = tree(out)
    if runtime_only:
        # Isolate the second independent check in memory, never installed policy.
        monkeypatch.setattr(nav, "structural", lambda *a, **kw: None)
    with pytest.raises(nav.Invalid, match="ARRAY:documents" if runtime_only else "SCHEMA_ARRAY:input.documents"):
        nav.build(root, index, out)
    assert tree(out) == before


def test_native_200_to_201_to_1000_preserves_acceptance_and_immutable_history(tmp_path):
    root, model, index, out = fixture(tmp_path, native=True)
    first = atlas.cycle(root, ".atlas/project.json", out, release="CAP-NATIVE-200", at=AT)
    assert len(model["documents"]) == 200 and sum(d["lifecycle"] == "archived" for d in model["documents"]) == 39
    old_documents = copy.deepcopy(model["documents"])
    old_history = copy.deepcopy(model["history"])
    _, original = atlas.current_output(out)
    accepted = copy.deepcopy(original["atlas"]["works"][0]["acceptance"])
    accepted_basis = atlas.basis(original["atlas"]["works"][0])
    retained_releases = tree(out / "releases")
    for count in (201, 1000):
        previous = nav.digest((root / index).read_bytes())
        advance(root, model, index, previous, native=True, count=count)
        started = time.perf_counter()
        result = atlas.cycle(root, ".atlas/project.json", out, release=f"CAP-NATIVE-{count}", at=model["release"]["created_at"])
        _, current = atlas.current_output(out)
        assert len(current["documents"]) == count
        assert current["input"]["documents"][:200] == old_documents
        assert current["input"]["history"][:len(old_history)] == old_history
        assert current["atlas"]["works"][0]["acceptance"] == accepted
        assert atlas.basis(current["atlas"]["works"][0]) == accepted_basis
        assert current["input"]["project"]["id"] == original["input"]["project"]["id"]
        for name, raw in retained_releases.items():
            assert (out / "releases" / name).read_bytes() == raw
        release = out / "releases" / result["release"]
        print("CAPACITY_PUBLICATION_METRIC " + json.dumps({"documents": count,
              "snapshot_bytes": (release / "snapshot.json").stat().st_size,
              "html_bytes": (release / "index.html").stat().st_size,
              "publication_elapsed_wall_seconds": time.perf_counter()-started, "CPU_measured": False}))
        retained_releases = tree(out / "releases")


@pytest.mark.parametrize("fault", ["removed", "rebound", "rewritten", "dangling", "hash", "parent", "lock"])
def test_growth_conflicts_preserve_current_and_every_published_byte(tmp_path, fault):
    root, model, index, out = fixture(tmp_path)
    first = nav.build(root, index, out)
    advance(root, model, index, first["manifest_sha256"], count=201)
    target = next(d for d in model["documents"] if d["id"] == "CAP-DOC-0199")
    expected = {"removed": "HISTORY_MEMBER_REMOVED", "rebound": "HISTORICAL_MEMBER_REWRITE",
                "rewritten": "HISTORICAL_MEMBER_REWRITE", "dangling": "DANGLING", "hash": "DOCUMENT_HASH",
                "parent": "EXPECTED_PREVIOUS_MISMATCH", "lock": "WRITER_LOCK_RECONCILE_REQUIRED"}[fault]
    if fault == "removed":
        model["documents"].remove(target)
    elif fault == "rebound":
        (root / "docs/rebound.md").write_bytes((root / target["path"]).read_bytes())
        target["path"] = "docs/rebound.md"
    elif fault == "rewritten":
        target["version"] = "forged-version"
    elif fault == "dangling":
        model["contracts"][0]["docs"].append("ABSENT-DOCUMENT")
    elif fault == "hash":
        model["documents"][-1]["sha256"] = "0" * 64
    elif fault == "parent":
        model["release"]["previous"] = "0"*64
    else:
        (out / ".writer.lock").write_bytes(b"Existing unknown writer; do not remove")
    save(root, model, index)
    before = tree(out)
    with pytest.raises(nav.Invalid, match=expected):
        nav.build(root, index, out)
    assert tree(out) == before


@pytest.mark.parametrize("fault", ["tampered", "missing"])
def test_exact_archived_release_read_refuses_corruption_without_current_changes(tmp_path, fault):
    root, model, index, out = fixture(tmp_path)
    first = nav.build(root, index, out)
    advance(root, model, index, first["manifest_sha256"], count=201)
    nav.build(root, index, out)
    archived = out / "releases" / first["release"] / "snapshot.json"
    if fault == "tampered":
        archived.write_bytes(archived.read_bytes() + b" ")
    else:
        archived.unlink()
    before = tree(out)
    with pytest.raises(nav.Invalid):
        nav.verify_release(out, first["release"], first["manifest_sha256"])
    assert tree(out) == before


@pytest.mark.parametrize("fault", ["tampered", "missing"])
def test_growth_refuses_corrupt_current_parent_without_changing_current(tmp_path, fault):
    root, model, index, out = fixture(tmp_path)
    first = nav.build(root, index, out)
    advance(root, model, index, first["manifest_sha256"], count=201)
    second = nav.build(root, index, out)
    advance(root, model, index, second["manifest_sha256"], count=202)
    parent = out / "releases" / second["release"] / "snapshot.json"
    if fault == "tampered":
        parent.write_bytes(parent.read_bytes() + b" ")
    else:
        parent.unlink()
    before = tree(out)
    with pytest.raises(nav.Invalid):
        nav.build(root, index, out)
    assert tree(out) == before


@pytest.mark.parametrize("fault", ["file", "total", "input", "snapshot", "html"])
def test_byte_budgets_still_refuse_without_publication(tmp_path, monkeypatch, fault):
    root, model, index, out = fixture(tmp_path)
    first = nav.build(root, index, out)
    advance(root, model, index, first["manifest_sha256"], count=201)
    snapshot = nav.load(root, index)
    if fault in ("file", "total"):
        fillers = [d for d in model["documents"] if d["id"].startswith("CAP-DOC-")]
        for doc in fillers[:1 if fault == "file" else 9]:
            (root / doc["path"]).write_bytes(b"x" * (nav.MAX_FILE + (1 if fault == "file" else 0)))
            doc.update(pin(root, doc["path"]))
        save(root, model, index)
    elif fault == "input":
        raw = (root / index).read_bytes()
        (root / index).write_bytes(raw + b" " * (nav.MAX_INPUT + 1 - len(raw)))
    elif fault == "snapshot":
        # Inject a smaller synthetic output budget to exercise the unchanged gate.
        monkeypatch.setattr(nav, "MAX_SNAPSHOT", len(nav.canonical(snapshot))-1)
    else:
        monkeypatch.setattr(nav, "MAX_HTML", len(nav.render(snapshot))-1)
    before = tree(out)
    with pytest.raises(nav.Invalid):
        nav.build(root, index, out)
    assert tree(out) == before
