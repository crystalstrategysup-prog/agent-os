"""Native entry migration in disposable fixtures, never the real NEXT root."""
import copy
import importlib
import json
import shutil
import sys
import subprocess
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from test_atlas_readable import isolated_engine

SCRIPTS = Path(__file__).resolve().parents[1] / "modules/atlas/skills/atlas/scripts"
with isolated_engine(SCRIPTS):
    atlas = importlib.import_module("atlas")
    nav = importlib.import_module("navigator")
    relocation = importlib.import_module("source_relocation")


@pytest.fixture(autouse=True)
def standalone_import_scope():
    global atlas, nav, relocation
    with isolated_engine(SCRIPTS):
        atlas = importlib.import_module("atlas")
        nav = importlib.import_module("navigator")
        relocation = importlib.import_module("source_relocation")
        yield


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def write(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(nav.canonical(value))


@pytest.fixture
def case(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(SCRIPTS.parents[2] / "examples/workflow", root)
    # Actual-case shape/identities, with entirely synthetic bodies and authority.
    for path in root.rglob("*.json"):
        original_json = path.read_text()
        raw = original_json.replace('"DOC-CONTRACT"', '"DOC-ROUTING"').replace('"A-BASE"', '"A-BINDING"')
        if raw != original_json:
            path.write_bytes(nav.canonical(json.loads(raw)))
    project_path = ".atlas/project.json"
    project = nav.parse((root / project_path).read_bytes())
    docs_path = project["documents"]["path"]
    model = nav.parse((root / docs_path).read_bytes())
    old = next(d for d in model["documents"] if d["id"] == "DOC-ROUTING")
    original = (root / old["path"]).read_bytes()
    (root / "AGENTS.md").write_bytes(original)
    old["path"] = "AGENTS.md"
    old["source_ref"] = "Synthetic original natural entry"
    work_path = ".atlas/work/W-01.json"
    work = nav.parse((root / work_path).read_bytes())
    for evidence in work["evidence"]:
        evidence["receipt"] = relocation.pin(evidence["receipt"]["path"], (root / evidence["receipt"]["path"]).read_bytes())
    work["artifacts"][0]["path"] = "AGENTS.md"
    for decision in work["acceptance"]:
        decision["basis_sha256"] = atlas.basis(work)
    write(root, work_path, work)
    write(root, docs_path, model)
    project["documents"] = relocation.pin(docs_path, (root / docs_path).read_bytes())
    project["coverage"]["inventory"] = relocation.pin(project["coverage"]["inventory"]["path"], (root / project["coverage"]["inventory"]["path"]).read_bytes())
    write(root, project_path, project)
    at = datetime.now(timezone.utc) - timedelta(seconds=1)
    output = root / "output"
    atlas.cycle(root, project_path, output, release="ATLAS-BEFORE", at=at.isoformat())
    pointer, snapshot = atlas.current_output(output)
    replacement = next(d for d in model["documents"] if d["id"] == "DOC-PATCH")
    request = {"schema": relocation.SCHEMA, "operation_id": "a" * 32,
               "root": str(root.resolve()), "project_path": project_path, "output": "output",
               "project_id": project["id"], "writer": project["writer"],
               "authority_ref": project["authority_ref"],
               "at": (at + timedelta(milliseconds=100)).isoformat(),
               "valid_until": (at + timedelta(minutes=10)).isoformat(),
               "expected": {"release": pointer["release"], "manifest_sha256": pointer["manifest_sha256"],
                            "project_sha256": nav.digest((root / project_path).read_bytes()),
                            "source_sha256": snapshot["atlas"]["source_sha256"]},
               "entries": [{"path": "AGENTS.md", "before": {"sha256": old["sha256"], "bytes": old["bytes"]},
                            "replacement_document": replacement["id"],
                            "replacement": {k: replacement[k] for k in ("path", "sha256", "bytes")}}]}
    return root, request, copy.deepcopy(work), original


def test_plan_is_read_only_and_preserves_accepted_basis(case):
    root, request, work, _ = case
    before = tree(root)
    plan = relocation.plan(root, request)
    assert tree(root) == before
    assert plan["preview"]["release"].startswith("ATLAS-SRC-")
    assert plan["request_sha256"] == nav.digest(nav.canonical(request))


def test_apply_retains_history_and_natural_entry_with_same_acceptance(case):
    root, request, work, original = case
    original_history = tree(root / "output/releases")
    plan = relocation.plan(root, request)
    result = relocation.apply(root, request, nav.digest(nav.canonical(plan)))
    assert result["status"] == "COMMITTED"
    assert (root / "AGENTS.md").read_bytes() == (root / request["entries"][0]["replacement"]["path"]).read_bytes()
    assert (root / relocation.retained_path(request["operation_id"], nav.digest(original))).read_bytes() == original
    current = atlas.load_project(root, request["project_path"])
    accepted = next(w for w in current["atlas"]["works"] if w["id"] == work["id"])
    assert accepted["acceptance"] == work["acceptance"]
    assert atlas.basis(accepted) == atlas.basis(work)
    assert accepted["artifacts"][0]["path"] == "AGENTS.md"
    assert accepted["artifacts"][0]["sha256"] == nav.digest(original)
    for path, raw in original_history.items():
        assert (root / "output/releases" / path).read_bytes() == raw
    assert not (root / relocation.PENDING).exists()
    status = relocation.status(root, request["operation_id"], nav.digest(nav.canonical(plan)))
    assert status["receipt"]["status"] == "COMMITTED"


@pytest.mark.parametrize("subject", ["retained", "request", "receipt"])
def test_changed_history_proof_fails_closed_without_writing(case, subject):
    root, request, _, original = case
    (root / "AGENTS.md").chmod(0o640)
    plan = relocation.plan(root, request)
    relocation.apply(root, request, nav.digest(nav.canonical(plan)))
    assert (root / "AGENTS.md").stat().st_mode & 0o777 == 0o640
    prefix = relocation.area(request["operation_id"])
    if subject == "retained":
        target = root / relocation.retained_path(request["operation_id"], nav.digest(original))
        target.write_bytes(b"Synthetic corrupt retained historical body.")
    elif subject == "request":
        target = root / prefix / "request.json"
        value = json.loads(target.read_bytes())
        value["writer"] = "unrelated-writer"
        target.write_bytes(nav.canonical(value))
    else:
        target = root / prefix / "receipt.json"
        value = json.loads(target.read_bytes())
        value["semantic_acceptance"] = True
        target.write_bytes(nav.canonical(value))
    before = tree(root)
    with pytest.raises(nav.Invalid):
        atlas.load_project(root, request["project_path"])
    assert tree(root) == before


@pytest.mark.parametrize("field", ["writer", "authority_ref", "source_sha", "manifest_sha", "entry_sha", "replacement_sha", "expiry", "escape"])
def test_invalid_or_stale_request_has_no_effects(case, field):
    root, request, _, _ = case
    bad = copy.deepcopy(request)
    if field in ("writer", "authority_ref"):
        bad[field] = "unrelated-current-actor"
    elif field in ("source_sha", "manifest_sha"):
        bad["expected"]["source_sha256" if field == "source_sha" else "manifest_sha256"] = "0" * 64
    elif field == "entry_sha":
        bad["entries"][0]["before"]["sha256"] = "0" * 64
    elif field == "replacement_sha":
        bad["entries"][0]["replacement"]["sha256"] = "0" * 64
    elif field == "expiry":
        bad["at"] = "2020-01-01T00:00:00Z"
        bad["valid_until"] = "2020-01-01T00:10:00Z"
    else:
        bad["entries"][0]["path"] = "../AGENTS.md"
    before = tree(root)
    with pytest.raises(nav.Invalid):
        relocation.plan(root, bad)
    assert tree(root) == before


def test_same_historical_id_cannot_be_retargeted_without_operation(case):
    root, request, _, original = case
    project = nav.parse((root / request["project_path"]).read_bytes())
    path = project["documents"]["path"]
    docs = nav.parse((root / path).read_bytes())
    (root / "old-entry.md").write_bytes(original)
    old = next(d for d in docs["documents"] if d["id"] == "DOC-ROUTING")
    old["path"] = "old-entry.md"
    previous_input = nav.digest((root / path).read_bytes())
    docs["release"] = {"id": "DN-TRY-REPATH", "created_at": request["at"], "previous": previous_input}
    docs["history"].append({"id": "TRY-REPATH", "at": request["at"], "kind": "SOURCE_RELOCATED", "summary": "Unprivileged repath fixture", "entity_ids": [old["id"]]})
    write(root, path, docs)
    project["documents"] = relocation.pin(path, (root / path).read_bytes())
    write(root, request["project_path"], project)
    before = tree(root / "output")
    with pytest.raises(nav.Invalid, match="HISTORICAL_MEMBER_REWRITE"):
        atlas.cycle(root, request["project_path"], root / "output", release="ATLAS-UNSUPPORTED", at=request["at"])
    assert tree(root / "output") == before


def test_root_alias_and_replacement_symlink_refused(case, tmp_path):
    root, request, _, _ = case
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(nav.Invalid, match="INVALID_ROOT"):
        relocation.plan(alias, request)
    target = root / request["entries"][0]["replacement"]["path"]
    saved = tmp_path / "outside.md"
    saved.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(saved)
    with pytest.raises(nav.Invalid, match="SYMLINK"):
        relocation.plan(root, request)


@pytest.mark.parametrize("fail_at", [0, 1, 2, 3, 4])
def test_each_partial_source_write_is_owned_and_reconciled(case, monkeypatch, fail_at):
    root, request, _, _ = case
    plan = relocation.plan(root, request)
    plan_sha = nav.digest(nav.canonical(plan))
    original = relocation._replace
    calls = 0
    def fail_once(*args, **kwargs):
        nonlocal calls
        if Path(args[0]).resolve() != root.resolve():
            return original(*args, **kwargs)
        i = calls
        calls += 1
        if i == fail_at:
            raise OSError("Synthetic source write interruption")
        return original(*args, **kwargs)
    monkeypatch.setattr(relocation, "_replace", fail_once)
    with pytest.raises(OSError):
        relocation.apply(root, request, plan_sha)
    assert (root / relocation.PENDING).exists()
    with pytest.raises(nav.Invalid, match="PENDING_RECONCILE_REQUIRED"):
        atlas.load_project(root, request["project_path"])
    before_status = tree(root)
    assert relocation.status(root, request["operation_id"], plan_sha)["pending"]
    assert tree(root) == before_status
    monkeypatch.setattr(relocation, "_replace", original)
    result = relocation.reconcile(root, request["operation_id"], plan_sha)
    assert result["status"] == "COMMITTED"
    before_replay = tree(root)
    assert relocation.reconcile(root, request["operation_id"], plan_sha)["replayed"] is False
    assert tree(root) == before_replay


def interrupt(case, monkeypatch, *, path_suffix):
    root, request, _, _ = case
    plan = relocation.plan(root, request)
    plan_sha = nav.digest(nav.canonical(plan))
    original = relocation._create
    def fail(selected_root, path, *args, **kwargs):
        if Path(selected_root).resolve() == root.resolve() and path.endswith(path_suffix):
            raise OSError("Synthetic metadata write interruption")
        return original(selected_root, path, *args, **kwargs)
    monkeypatch.setattr(relocation, "_create", fail)
    with pytest.raises(OSError):
        relocation.apply(root, request, plan_sha)
    monkeypatch.setattr(relocation, "_create", original)
    return plan_sha


@pytest.mark.parametrize("phase", ["plan.json", relocation.PENDING, "receipt.json"])
def test_preparation_and_postpublication_metadata_recovery(case, monkeypatch, phase):
    root, request, _, _ = case
    plan_sha = interrupt(case, monkeypatch, path_suffix=phase)
    result = relocation.reconcile(root, request["operation_id"], plan_sha)
    assert result["status"] == "COMMITTED"
    assert not (root / relocation.PENDING).exists()


def committed_before_cleanup(case, monkeypatch):
    root, request, _, _ = case
    plan_sha = nav.digest(nav.canonical(relocation.plan(root, request)))
    unlink = Path.unlink
    def crash(path, *args, **kwargs):
        if path == root / relocation.PENDING:
            raise OSError("Synthetic crash after durable receipt before cleanup")
        return unlink(path, *args, **kwargs)
    with monkeypatch.context() as failure:
        failure.setattr(Path, "unlink", crash)
        with pytest.raises(OSError):
            relocation.apply(root, request, plan_sha)
    receipt = root / relocation.area(request["operation_id"]) / "receipt.json"
    assert json.loads(receipt.read_bytes())["status"] == "COMMITTED"
    assert (root / relocation.PENDING).exists()
    return plan_sha, receipt, receipt.read_bytes()


def fresh_cleanup_authority(root, request, plan_sha, monkeypatch, *, hours=1, action="resume"):
    later = datetime.now(timezone.utc) + timedelta(hours=hours)
    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return later
    monkeypatch.setattr(relocation, "datetime", Later)
    pointer, _ = atlas.current_output(root / request["output"])
    return {"schema": relocation.RECONCILE_SCHEMA,
            **{key: request[key] for key in ("operation_id", "root", "project_id", "writer", "authority_ref")},
            "authorization_ref": "Synthetic current same-scope cleanup authority " + str(hours),
            "plan_sha256": plan_sha, "action": action,
            "at": (later - timedelta(seconds=1)).isoformat(),
            "valid_until": (later + timedelta(minutes=5)).isoformat(),
            "expected": {key: pointer[key] for key in ("release", "manifest_sha256")}}


def forbid_replay(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Terminal cleanup must not replace source or publish")
    monkeypatch.setattr(atlas, "cycle", forbidden)
    monkeypatch.setattr(relocation, "_replace", forbidden)


@pytest.mark.parametrize("renew", [False, True])
def test_committed_receipt_cleanup_preserves_original_across_expiry(case, monkeypatch, renew):
    root, request, original_work, _ = case
    plan_sha, receipt, original_receipt = committed_before_cleanup(case, monkeypatch)
    published = tree(root / "output")
    authority = fresh_cleanup_authority(root, request, plan_sha, monkeypatch) if renew else None
    forbid_replay(monkeypatch)
    result = relocation.reconcile(root, request["operation_id"], plan_sha, renewal=authority)
    assert result == {**json.loads(original_receipt), "replayed": False}
    assert receipt.read_bytes() == original_receipt
    assert tree(root / "output") == published
    assert not (root / relocation.PENDING).exists()
    current = atlas.load_project(root, request["project_path"])
    assert next(w for w in current["atlas"]["works"] if w["id"] == original_work["id"])["acceptance"] == original_work["acceptance"]
    if renew:
        assert (root / relocation.area(request["operation_id"]) / "authorities" / (nav.digest(nav.canonical(authority)) + ".json")).read_bytes() == nav.canonical(authority)


@pytest.mark.parametrize("fault", ["missing_authority", "writer", "operation", "authority", "head", "receipt", "source", "toolchain", "pending"])
def test_terminal_cleanup_rejects_conflicts_before_effects(case, monkeypatch, fault):
    root, request, _, _ = case
    plan_sha, receipt, _ = committed_before_cleanup(case, monkeypatch)
    authority = fresh_cleanup_authority(root, request, plan_sha, monkeypatch)
    if fault == "missing_authority":
        authority = None
    elif fault in ("writer", "operation", "authority"):
        key = {"writer": "writer", "operation": "operation_id", "authority": "authority_ref"}[fault]
        authority[key] = "b" * 32 if fault == "operation" else "unrelated-authority"
    elif fault == "head":
        # A valid older immutable head must never cause terminal republishing.
        pointer = {"schema": "docs-navigator.current/v1", **{key: request["expected"][key] for key in ("release", "manifest_sha256")}}
        (root / "output/CURRENT.json").write_bytes(nav.canonical(pointer))
        authority["expected"] = {key: pointer[key] for key in ("release", "manifest_sha256")}
    elif fault == "receipt":
        value = json.loads(receipt.read_bytes()); value["semantic_acceptance"] = True
        receipt.write_bytes(nav.canonical(value))
    elif fault == "source":
        (root / "AGENTS.md").write_text("Synthetic concurrent source edit")
    elif fault == "toolchain":
        monkeypatch.setattr(atlas, "toolchain_digest", lambda: "0" * 64)
    else:
        pending = json.loads((root / relocation.PENDING).read_bytes()); pending["request_sha256"] = "0" * 64
        (root / relocation.PENDING).write_bytes(nav.canonical(pending))
    before = tree(root)
    forbid_replay(monkeypatch)
    with pytest.raises(nav.Invalid):
        relocation.reconcile(root, request["operation_id"], plan_sha, renewal=authority)
    assert tree(root) == before
    assert (root / relocation.PENDING).exists()


@pytest.mark.parametrize("corrupt_prior_authority", [False, True])
def test_terminal_cleanup_after_multiple_renewals_keeps_first_receipt(case, monkeypatch, corrupt_prior_authority):
    root, request, _, _ = case
    plan_sha = interrupt(case, monkeypatch, path_suffix="receipt.json")
    first = fresh_cleanup_authority(root, request, plan_sha, monkeypatch)
    unlink = Path.unlink
    def crash(path, *args, **kwargs):
        if path == root / relocation.PENDING:
            raise OSError("Synthetic second cleanup crash")
        return unlink(path, *args, **kwargs)
    with monkeypatch.context() as failure:
        failure.setattr(Path, "unlink", crash)
        with pytest.raises(OSError):
            relocation.reconcile(root, request["operation_id"], plan_sha, renewal=first)
    receipt = root / relocation.area(request["operation_id"]) / "receipt.json"
    original_receipt = receipt.read_bytes()
    first_sha = nav.digest(nav.canonical(first))
    assert json.loads(original_receipt)["reconcile_authority_sha256"] == first_sha
    second = fresh_cleanup_authority(root, request, plan_sha, monkeypatch, hours=2)
    if corrupt_prior_authority:
        (root / relocation.area(request["operation_id"]) / "authorities" / (first_sha + ".json")).write_bytes(b"{}")
    before = tree(root)
    published = tree(root / "output")
    forbid_replay(monkeypatch)
    if corrupt_prior_authority:
        with pytest.raises(nav.Invalid, match="RECEIPT_AUTHORITY_PIN"):
            relocation.reconcile(root, request["operation_id"], plan_sha, renewal=second)
        assert tree(root) == before
    else:
        result = relocation.reconcile(root, request["operation_id"], plan_sha, renewal=second)
        assert result["replayed"] is False
        assert result["reconcile_authority_sha256"] == first_sha
        assert not (root / relocation.PENDING).exists()
        assert tree(root / "output") == published
    assert receipt.read_bytes() == original_receipt


def test_rolled_back_terminal_receipt_only_finishes_cleanup(case, monkeypatch):
    root, request, _, original_entry = case
    replace, unlink = relocation._replace, Path.unlink
    def partial(selected, row, *args, **kwargs):
        if Path(selected).resolve() == root.resolve() and row["kind"] == "entry":
            raise OSError("Synthetic partial apply after retaining old bytes")
        return replace(selected, row, *args, **kwargs)
    plan_sha = nav.digest(nav.canonical(relocation.plan(root, request)))
    with monkeypatch.context() as failure:
        failure.setattr(relocation, "_replace", partial)
        with pytest.raises(OSError):
            relocation.apply(root, request, plan_sha)
    def crash(path, *args, **kwargs):
        if path == root / relocation.PENDING:
            raise OSError("Synthetic rollback cleanup crash")
        return unlink(path, *args, **kwargs)
    with monkeypatch.context() as failure:
        failure.setattr(Path, "unlink", crash)
        with pytest.raises(OSError):
            relocation.reconcile(root, request["operation_id"], plan_sha, rollback=True)
    receipt = root / relocation.area(request["operation_id"]) / "receipt.json"
    original_receipt = receipt.read_bytes()
    authority = fresh_cleanup_authority(root, request, plan_sha, monkeypatch, action="rollback")
    before = tree(root / "output")
    forbid_replay(monkeypatch)
    result = relocation.reconcile(root, request["operation_id"], plan_sha, rollback=True, renewal=authority)
    assert result["status"] == "ROLLED_BACK_UNPUBLISHED" and result["replayed"] is False
    assert receipt.read_bytes() == original_receipt and not (root / relocation.PENDING).exists()
    assert tree(root / "output") == before
    assert (root / "AGENTS.md").read_bytes() == original_entry


def test_operation_owned_orphan_is_reconciled_without_relaxing_default_guard(case, monkeypatch):
    root, request, _, _ = case
    plan = relocation.plan(root, request)
    plan_sha = nav.digest(nav.canonical(plan))
    replace = nav.os.replace
    def fail_pointer(source, destination):
        if Path(destination) == root / "output/CURRENT.json":
            raise OSError("Synthetic crash before CURRENT commit")
        return replace(source, destination)
    monkeypatch.setattr(nav.os, "replace", fail_pointer)
    with pytest.raises(OSError):
        relocation.apply(root, request, plan_sha)
    monkeypatch.setattr(nav.os, "replace", replace)
    _, orphan = nav.verify_release(root / "output", plan["preview"]["release"])
    with pytest.raises(nav.Invalid, match="ORPHAN_RECONCILE_ONLY"):
        nav.publish(orphan, root / "output", history_fn=atlas.check_history, version=atlas.VERSION)
    assert relocation.reconcile(root, request["operation_id"], plan_sha)["status"] == "COMMITTED"


def test_rollback_is_only_unpublished_and_keeps_retained_bytes(case, monkeypatch):
    root, request, _, original = case
    plan_sha = interrupt(case, monkeypatch, path_suffix=relocation.PENDING)
    assert relocation.reconcile(root, request["operation_id"], plan_sha, rollback=True)["status"] == "ROLLED_BACK_UNPUBLISHED"
    assert (root / "AGENTS.md").read_bytes() == original
    assert atlas.current_output(root / "output")[0]["release"] == request["expected"]["release"]


def test_forged_journal_or_concurrent_source_edit_is_not_overwritten(case, monkeypatch):
    root, request, _, _ = case
    plan_sha = interrupt(case, monkeypatch, path_suffix="receipt.json")
    (root / "AGENTS.md").write_text("Concurrent independent source")
    before = tree(root)
    with pytest.raises(nav.Invalid, match="CONFLICT"):
        relocation.reconcile(root, request["operation_id"], plan_sha)
    assert tree(root) == before


def test_recomputed_plan_hash_does_not_allow_uncontracted_metadata_write(case, monkeypatch):
    root, request, _, _ = case
    plan_sha = interrupt(case, monkeypatch, path_suffix=relocation.PENDING)
    path = root / relocation.area(request["operation_id"]) / "plan.json"
    plan = nav.parse(path.read_bytes())
    row = next(r for r in plan["rows"] if r["path"] == request["project_path"])
    import base64
    after = nav.parse(base64.b64decode(row["after"]))
    after["objective"] = "Uncontracted objective rewrite"
    raw = nav.canonical(after)
    row["after"] = base64.b64encode(raw).decode()
    row["after_sha256"] = nav.digest(raw)
    path.write_bytes(nav.canonical(plan))
    before = tree(root)
    with pytest.raises(nav.Invalid, match="PLAN_TRANSITION"):
        relocation.reconcile(root, request["operation_id"], nav.digest(path.read_bytes()))
    assert tree(root) == before


def test_early_preparation_needs_exact_original_request(case, monkeypatch):
    root, request, _, _ = case
    plan = relocation.plan(root, request)
    plan_sha = nav.digest(nav.canonical(plan))
    original = relocation._create
    def fail(selected, path, *args, **kwargs):
        if Path(selected).resolve() == root.resolve() and path.endswith("request.json"):
            raise OSError("Synthetic failure before reservation")
        return original(selected, path, *args, **kwargs)
    monkeypatch.setattr(relocation, "_create", fail)
    with pytest.raises(OSError):
        relocation.apply(root, request, plan_sha)
    monkeypatch.setattr(relocation, "_create", original)
    with pytest.raises(nav.Invalid, match="PREPARATION_REQUEST_REQUIRED"):
        relocation.reconcile(root, request["operation_id"], plan_sha)
    assert relocation.reconcile(root, request["operation_id"], plan_sha, preparation_request=request)["status"] == "COMMITTED"


def test_published_result_cannot_be_rolled_back_and_is_not_replayed(case):
    root, request, _, _ = case
    plan_sha = nav.digest(nav.canonical(relocation.plan(root, request)))
    relocation.apply(root, request, plan_sha)
    before = tree(root)
    with pytest.raises(nav.Invalid, match="PUBLISHED_ROLLBACK_REQUIRES_SUCCESSOR"):
        relocation.reconcile(root, request["operation_id"], plan_sha, rollback=True)
    assert tree(root) == before
    (root / "AGENTS.md").write_text("Later caller source; historical reconcile must not overwrite it.")
    before = tree(root)
    assert relocation.reconcile(root, request["operation_id"], plan_sha)["replayed"] is False
    assert tree(root) == before


def test_exact_stale_lock_and_dead_owner_required(case, monkeypatch):
    root, request, _, _ = case
    plan_sha = interrupt(case, monkeypatch, path_suffix=relocation.PENDING)
    lock_path = root / "output/.writer.lock"
    tag = {"schema": relocation.SCHEMA, "operation_id": request["operation_id"], "plan_sha256": plan_sha, "pid": os.getpid()}
    lock_path.write_bytes(nav.canonical(tag))
    before = tree(root)
    with pytest.raises(nav.Invalid, match="STALE_LOCK_EXACT_QUALIFICATION_REQUIRED"):
        relocation.reconcile(root, request["operation_id"], plan_sha)
    with pytest.raises(nav.Invalid, match="LOCK_OWNER_ACTIVE"):
        relocation.reconcile(root, request["operation_id"], plan_sha, stale_lock_sha256=nav.digest(lock_path.read_bytes()))
    assert tree(root) == before
    def dead(*args):
        raise ProcessLookupError("Synthetic deceased fixture owner")
    monkeypatch.setattr(relocation.os, "kill", dead)
    assert relocation.reconcile(root, request["operation_id"], plan_sha, stale_lock_sha256=nav.digest(lock_path.read_bytes()))["status"] == "COMMITTED"


def test_expired_operation_requires_fresh_same_scope_authority(case, monkeypatch):
    root, request, work, _ = case
    plan_sha = interrupt(case, monkeypatch, path_suffix=relocation.PENDING)
    later = datetime.now(timezone.utc) + timedelta(hours=1)
    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return later
    monkeypatch.setattr(relocation, "datetime", Later)
    before = tree(root)
    with pytest.raises(nav.Invalid, match="EXPIRED"):
        relocation.reconcile(root, request["operation_id"], plan_sha)
    assert tree(root) == before
    pointer, _ = atlas.current_output(root / "output")
    authority = {"schema": relocation.RECONCILE_SCHEMA,
                 **{k: request[k] for k in ("operation_id", "root", "project_id", "writer", "authority_ref")},
                 "authorization_ref": "Synthetic fresh owner authorization for exactly this unfinished operation",
                 "plan_sha256": plan_sha, "action": "resume",
                 "at": (later - timedelta(seconds=1)).isoformat(),
                 "valid_until": (later + timedelta(minutes=10)).isoformat(),
                 "expected": {k: pointer[k] for k in ("release", "manifest_sha256")}}
    forged = {**authority, "writer": "different-owner"}
    with pytest.raises(nav.Invalid, match="RECONCILE_AUTHORITY_IDENTITY"):
        relocation.reconcile(root, request["operation_id"], plan_sha, renewal=forged)
    assert tree(root) == before
    assert relocation.reconcile(root, request["operation_id"], plan_sha, renewal=authority)["status"] == "COMMITTED"
    historical = atlas.load_project(root, request["project_path"])
    assert next(w for w in historical["atlas"]["works"] if w["id"] == work["id"])["acceptance"] == work["acceptance"]


def test_cli_plan_has_hashes_not_source_bodies_and_uses_no_registry(case):
    root, request, _, original = case
    source = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-B", "-m", "agent_os", "atlas", "source-relocate", "plan", "--root", str(root), "--request", "-"]
    environment = {**os.environ, "PYTHONPATH": str(source / "src")}
    # Exact canonical/packaged mirrors are synchronized before formal checks.
    response = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True, env=environment, timeout=30)
    assert response.returncode == 0, response.stdout + response.stderr
    result = json.loads(response.stdout)
    assert result["status"] == "PLANNED"
    assert "plan_sha256" in result and "default_registry" not in response.stdout
    assert original.decode() not in response.stdout
    assert all("before" not in row and "after" not in row for row in result["rows"])


def test_second_entry_update_retains_both_prior_versions_and_basis(case):
    root, request, original_work, original = case
    plan_sha = nav.digest(nav.canonical(relocation.plan(root, request)))
    relocation.apply(root, request, plan_sha)
    first_entry = (root / "AGENTS.md").read_bytes()
    project = nav.parse((root / request["project_path"]).read_bytes())
    path = project["documents"]["path"]
    raw = (root / path).read_bytes()
    model = nav.parse(raw)
    at = datetime.now(timezone.utc)
    replacement = copy.deepcopy(next(d for d in model["documents"] if d["id"] == "DOC-PATCH"))
    (root / "docs/AGENTS-v3.md").write_text("Synthetic third version of the natural entry.\n")
    replacement.update(id="ENTRY-V3", version="3", readback_at=at.isoformat(), **relocation.pin("docs/AGENTS-v3.md", (root / "docs/AGENTS-v3.md").read_bytes()))
    model["documents"].append(replacement)
    model["release"] = {"id": "DN-V3-REGISTERED", "created_at": at.isoformat(), "previous": nav.digest(raw)}
    model["history"].append({"id": "REGISTER-V3", "at": at.isoformat(), "kind": "DOCUMENT_ADDED", "summary": "Explicit new version in synthetic fixture", "entity_ids": [replacement["id"]]})
    write(root, path, model)
    project["documents"] = relocation.pin(path, (root / path).read_bytes())
    write(root, request["project_path"], project)
    atlas.cycle(root, request["project_path"], root / "output", release="ATLAS-V3-REGISTERED", at=at.isoformat())
    pointer, snapshot = atlas.current_output(root / "output")
    next_request = copy.deepcopy(request)
    next_request.update(operation_id="b" * 32, at=at.isoformat(), valid_until=(at + timedelta(minutes=10)).isoformat())
    next_request["expected"] = {"release": pointer["release"], "manifest_sha256": pointer["manifest_sha256"], "project_sha256": nav.digest((root / request["project_path"]).read_bytes()), "source_sha256": snapshot["atlas"]["source_sha256"]}
    next_request["entries"] = [{"path": "AGENTS.md", "before": {"sha256": nav.digest(first_entry), "bytes": len(first_entry)}, "replacement_document": replacement["id"], "replacement": {k: replacement[k] for k in ("path", "sha256", "bytes")}}]
    second_plan = relocation.plan(root, next_request)
    assert relocation.apply(root, next_request, nav.digest(nav.canonical(second_plan)))["status"] == "COMMITTED"
    final = atlas.load_project(root, request["project_path"])
    archived = [d for d in final["documents"] if d["path"] == "AGENTS.md" and d["lifecycle"] == "archived"]
    assert {d["content"].encode() for d in archived} == {original, first_entry}
    work = next(w for w in final["atlas"]["works"] if w["id"] == original_work["id"])
    assert work["acceptance"] == original_work["acceptance"] and atlas.basis(work) == atlas.basis(original_work)


def test_toolchain_or_unaffected_selected_source_change_holds_recovery(case, monkeypatch):
    root, request, _, _ = case
    plan_sha = interrupt(case, monkeypatch, path_suffix=relocation.PENDING)
    original_digest = atlas.toolchain_digest
    monkeypatch.setattr(atlas, "toolchain_digest", lambda: "0" * 64)
    before = tree(root)
    with pytest.raises(nav.Invalid, match="TOOLCHAIN_CHANGED"):
        relocation.reconcile(root, request["operation_id"], plan_sha)
    assert tree(root) == before
    monkeypatch.setattr(atlas, "toolchain_digest", original_digest)
    (root / "src/batch.py").write_text("Independent concurrent selected-source edit\n")
    before = tree(root)
    with pytest.raises(nav.Invalid, match="SELECTED_SOURCE_CHANGED"):
        relocation.reconcile(root, request["operation_id"], plan_sha)
    assert tree(root) == before
