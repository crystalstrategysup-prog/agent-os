"""Synthetic stale-chat recovery cases; no operational identities or archives."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import sys
import threading
from types import SimpleNamespace

import pytest

from agent_os import binding_recovery as recovery, project as p, turns
from agent_os.safeio import GateError, atomic_json, digest, lock, read_json, sha


def files(root):
    return {
        item.relative_to(root).as_posix(): (
            ("symlink", str(item.readlink())) if item.is_symlink() else item.read_bytes()
        )
        for item in root.rglob("*") if item.is_symlink() or item.is_file()
    }


def make_case(tmp_path, root_state="moved"):
    root = tmp_path / "old-parent" / "project"
    root.mkdir(parents=True)
    home = tmp_path / "user"
    newroot = tmp_path / "new-project"
    newroot.mkdir()
    context = {
        key: "Synthetic local recovery fixture; no external service, user or authority."
        for key in p.CONTEXT_KEYS
    }
    for project_root in (root, newroot):
        p.initialize(project_root, "Synthetic recovery project", ["general"], [], context)
    answers = {
        key: "Synthetic bounded recovery contract; inspect local state and retained bytes."
        for key in p.QUESTIONS
    }
    answers.update(
        change_kind="implementation", write_paths=["module.py"],
        acceptance=[{"id": "A1", "criterion": "Synthetic local process succeeds.",
                     "checks": ["unit"]}],
        checks=[{"id": "unit", "argv": [sys.executable, "-c", 'print("fixture PASS")'],
                 "timeout": 30}],
    )
    task = p.enter(root, answers, session_id="fixture-chat", turn_id="old-turn",
                   user_home=home)["task_id"]
    receipt = turns.turn_path(home, "fixture-chat")
    # A valid receipt need not use the serializer's whitespace or key order.
    before = (json.dumps(read_json(receipt), indent=3, sort_keys=False) + "\n\n").encode()
    receipt.write_bytes(before)
    project_before = files(root)
    moved = tmp_path / "moved-project"
    if root_state == "moved":
        root.rename(moved)
    elif root_state == "missing":
        shutil.rmtree(root)
    else:
        assert root_state == "existing"
    return SimpleNamespace(root=root, home=home, newroot=newroot, moved=moved,
        answers=answers, task=task, receipt=receipt, before=before,
        expected_sha=sha(before), project_before=project_before)


def recover(case, **overrides):
    values = {
        "session_id": "fixture-chat", "previous_turn": "old-turn", "turn_id": "new-turn",
        "task_id": case.task, "expected_receipt_sha256": case.expected_sha,
        "allow_unverifiable_detach": True,
    }
    values.update(overrides)
    return recovery.recover_binding(values.pop("root", case.root), case.home, **values)


def cli_args(case):
    return ["recover-binding", "--root", str(case.root), "--session", "fixture-chat",
            "--from-turn", "old-turn", "--task", case.task, "--turn", "new-turn",
            "--expected-receipt-sha256", case.expected_sha, "--allow-unverifiable-detach"]


def archive_files(case):
    return files(case.home / "state" / "binding-recoveries")


@pytest.mark.parametrize("root_state", ["missing", "moved"])
def test_recovery_preserves_old_state_and_allows_fresh_normal_entry(tmp_path, root_state):
    case = make_case(tmp_path, root_state)
    unrelated_root = tmp_path / "unrelated-project"
    unrelated_root.mkdir()
    p.initialize(unrelated_root, "Synthetic unrelated project", ["general"], [], {
        key: "Synthetic unrelated task outside recovery scope." for key in p.CONTEXT_KEYS
    })
    unrelated = p.enter(unrelated_root, case.answers, session_id="unrelated-chat",
                       turn_id="unrelated-turn", user_home=case.home)["task_id"]
    unrelated_files = files(unrelated_root)
    unrelated_receipt = turns.turn_path(case.home, "unrelated-chat").read_bytes()
    before_new = files(case.newroot)
    with pytest.raises(GateError, match="turn_binding_mismatch_reenter_correct_turn"):
        p.enter(case.newroot, case.answers, session_id="fixture-chat", turn_id="new-turn",
                user_home=case.home)
    with pytest.raises(GateError, match="project_directory_missing"):
        p.next_turn(case.root, case.home, session_id="fixture-chat", previous_turn="old-turn",
                    turn_id="new-turn", task_id=case.task)
    assert files(case.newroot) == before_new
    assert case.receipt.read_bytes() == case.before

    result = recover(case)
    assert result["status"] == "INTAKE_REQUIRED" and result["task_id"] is None
    assert result["replayed"] is False
    for flag in ("authority_granted", "production_authorized", "native_hook_proven",
                 "task_state_verified", "old_task_changed"):
        assert result[flag] is False
    detached = read_json(case.receipt)
    assert detached["schema"] == "agentos.turn/v1"
    assert detached["session_id"] == "fixture-chat" and detached["turn_id"] == "new-turn"
    assert detached["status"] == "INTAKE_REQUIRED" and detached["task_id"] is None
    assert detached["hook_seen"] is False
    assert "ready" not in detached and "authority" not in detached

    archive = Path(result["archive"])
    assert archive.parent == case.home / "state" / "binding-recoveries"
    assert archive.name == result["recovery_id"]
    assert (archive / "receipt.before.json").read_bytes() == case.before
    assert (archive / "receipt.after.json").read_bytes() == case.receipt.read_bytes()
    request = read_json(archive / "request.json")
    assert request["expected_receipt_sha256"] == case.expected_sha
    assert request["allow_unverifiable_detach"] is True
    assert digest(request) == result["recovery_id"]
    journal = read_json(archive / "journal.json")
    assert journal["schema"] == "agentos.binding-recovery/v1"
    assert journal["state"] == "COMMITTED"
    assert journal["before_sha256"] == case.expected_sha
    assert journal["after_sha256"] == sha(case.receipt.read_bytes())
    assert journal["prepared_at"] and journal["committed_at"]
    saved_archive = archive_files(case)
    assert files(case.newroot) == before_new

    entered = p.enter(case.newroot, case.answers, session_id="fixture-chat", turn_id="new-turn",
                      user_home=case.home)
    assert entered["status"] == "INTAKE" and entered["task_id"] not in {case.task, unrelated}
    newtask = p.load_task(case.newroot, entered["task_id"])
    assert newtask["status"] == "INTAKE" and newtask["receipts"] == []
    assert "ready" not in newtask
    assert archive_files(case) == saved_archive
    assert files(unrelated_root) == unrelated_files
    assert turns.turn_path(case.home, "unrelated-chat").read_bytes() == unrelated_receipt
    if root_state == "moved":
        assert files(case.moved) == case.project_before
        assert p.load_task(case.moved, case.task)["status"] == "INTAKE"
    else:
        assert not case.root.exists()


def test_explicit_detachment_permission_is_required(tmp_path):
    case = make_case(tmp_path)
    before = files(tmp_path)
    with pytest.raises(GateError):
        recover(case, allow_unverifiable_detach=False)
    assert files(tmp_path) == before


def test_existing_active_project_cannot_be_detached(tmp_path):
    case = make_case(tmp_path, "existing")
    before = files(tmp_path)
    assert p.load_task(case.root, case.task)["status"] == "INTAKE"
    with pytest.raises(GateError):
        recover(case)
    assert files(tmp_path) == before


@pytest.mark.parametrize("field,value", [
    ("session_id", "another-chat"), ("previous_turn", "another-old-turn"),
    ("turn_id", "old-turn"), ("task_id", "task-unrelated"),
    ("expected_receipt_sha256", "0" * 64),
])
def test_exact_request_identifiers_and_sha_are_required(tmp_path, field, value):
    case = make_case(tmp_path)
    before = files(tmp_path)
    with pytest.raises(GateError):
        recover(case, **{field: value})
    assert files(tmp_path) == before


@pytest.mark.parametrize("root_kind", ["different", "relative", "dot-component"])
def test_exact_absolute_old_root_is_required(tmp_path, root_kind):
    case = make_case(tmp_path)
    root = {
        "different": str(tmp_path / "another-missing-project"),
        "relative": "old-parent/project",
        "dot-component": str(case.root.parent) + "/./project",
    }[root_kind]
    before = files(tmp_path)
    with pytest.raises(GateError):
        recover(case, root=root)
    assert files(tmp_path) == before


@pytest.mark.parametrize("raw", [b"not JSON", b"[]", b"null", b"{}",
    b'{"schema":"agentos.turn/v1","schema":"different"}'])
def test_corrupt_receipt_is_a_controlled_refusal(tmp_path, raw):
    case = make_case(tmp_path)
    case.receipt.write_bytes(raw)
    before = files(tmp_path)
    with pytest.raises(GateError):
        recover(case, expected_receipt_sha256=sha(raw))
    assert files(tmp_path) == before


@pytest.mark.parametrize("field,value", [
    ("schema", "agentos.turn/invalid"), ("session_id", "another-chat"),
    ("turn_id", "another-turn"), ("task_id", "task-unrelated"),
    ("status", "INTAKE_REQUIRED"), ("task_id", None),
])
def test_receipt_identity_and_entered_state_must_match(tmp_path, field, value):
    case = make_case(tmp_path)
    receipt = read_json(case.receipt)
    receipt[field] = value
    atomic_json(case.receipt, receipt)
    expected = sha(case.receipt.read_bytes())
    before = files(tmp_path)
    with pytest.raises(GateError):
        recover(case, expected_receipt_sha256=expected)
    assert files(tmp_path) == before


@pytest.mark.parametrize("kind", ["root", "dangling-root", "ancestor", "receipt", "archives"])
def test_symlink_paths_are_refused_without_following_or_overwriting(tmp_path, kind):
    case = make_case(tmp_path)
    if kind in {"root", "dangling-root"}:
        case.root.symlink_to(case.moved if kind == "root" else tmp_path / "absent-target")
    elif kind == "ancestor":
        case.root.parent.rename(tmp_path / "old-parent-moved")
        target = tmp_path / "other-parent"
        target.mkdir()
        case.root.parent.symlink_to(target)
    elif kind == "receipt":
        target = tmp_path / "external-receipt.json"
        case.receipt.rename(target)
        case.receipt.symlink_to(target)
    else:
        target = tmp_path / "external-archives"
        target.mkdir()
        (case.home / "state" / "binding-recoveries").symlink_to(target)
    before = files(tmp_path)
    with pytest.raises(GateError):
        recover(case)
    assert files(tmp_path) == before


@pytest.mark.parametrize("conflict", ["same-root", "moved-task"])
def test_other_registered_executor_conflicts_are_preserved(tmp_path, conflict):
    case = make_case(tmp_path)
    other_root = case.root if conflict == "same-root" else case.moved
    other_task = "task-unrelated" if conflict == "same-root" else case.task
    turns.bind_turn(case.home, "other-worker", "other-turn", other_root, other_task)
    before = files(tmp_path)
    with pytest.raises(GateError):
        recover(case)
    assert files(tmp_path) == before


def test_historical_dispatch_is_preserved_and_does_not_grant_authority(tmp_path):
    case = make_case(tmp_path)
    claim = case.home / "state" / "dispatch" / (digest(["fixture-chat", "old-turn"]) + ".json")
    atomic_json(claim, {
        "schema": "agentos.dispatch-claim/v1", "session_id": "fixture-chat",
        "turn_id": "old-turn", "task_id": case.task, "at": "2026-01-01T00:00:00+00:00",
        "prompt_sha256": digest("Synthetic historical dispatch"),
        "destination_session": None, "state": "CLAIMED_NOT_PROOF_OF_EXECUTION",
    })
    before = claim.read_bytes()
    result = recover(case)
    assert result["status"] == "INTAKE_REQUIRED" and result["task_id"] is None
    assert claim.read_bytes() == before


def test_existing_turn_lock_prevents_recovery(tmp_path):
    case = make_case(tmp_path)
    with lock(case.home / "state" / "turns.lock"):
        before = files(tmp_path)
        with pytest.raises(GateError, match="busy_or_stale_lock_manual_review_required"):
            recover(case)
        assert files(tmp_path) == before


def test_cas_preserves_concurrent_receipt_and_prepared_archive(tmp_path, monkeypatch):
    case = make_case(tmp_path)
    competing = read_json(case.receipt)
    competing["turn_id"] = "competing-turn"
    competing_bytes = (json.dumps(competing, indent=1) + "\n").encode()
    commit = recovery._commit_receipt

    def race(path, expected_bytes, new_bytes):
        path.write_bytes(competing_bytes)
        return commit(path, expected_bytes, new_bytes)

    monkeypatch.setattr(recovery, "_commit_receipt", race)
    with pytest.raises(GateError):
        recover(case)
    assert case.receipt.read_bytes() == competing_bytes
    archives = list((case.home / "state" / "binding-recoveries").iterdir())
    assert len(archives) == 1
    assert (archives[0] / "receipt.before.json").read_bytes() == case.before
    assert read_json(archives[0] / "journal.json")["state"] == "PREPARED"
    saved = files(tmp_path)
    monkeypatch.setattr(recovery, "_commit_receipt", commit)
    with pytest.raises(GateError):
        recover(case)
    assert files(tmp_path) == saved


def test_two_concurrent_recoveries_have_only_one_initial_commit(tmp_path):
    case = make_case(tmp_path)
    barrier = threading.Barrier(2)

    def attempt():
        barrier.wait(timeout=5)
        try:
            return recover(case)
        except GateError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    successes = [result for result in results if isinstance(result, dict)]
    assert sum(result["replayed"] is False for result in successes) == 1
    assert all(result["status"] == "INTAKE_REQUIRED" for result in successes)
    assert all(isinstance(result, dict) or result == "busy_or_stale_lock_manual_review_required"
               for result in results)
    assert len(list((case.home / "state" / "binding-recoveries").iterdir())) == 1
    assert read_json(case.receipt)["task_id"] is None


@pytest.mark.parametrize("committed", [False, True])
def test_interrupted_commit_can_resume_only_the_exact_transaction(tmp_path, monkeypatch, committed):
    case = make_case(tmp_path)
    commit = recovery._commit_receipt

    def interrupted(path, expected_bytes, new_bytes):
        if committed:
            commit(path, expected_bytes, new_bytes)
        raise OSError("synthetic interrupted recovery")

    monkeypatch.setattr(recovery, "_commit_receipt", interrupted)
    with pytest.raises(OSError, match="synthetic interrupted recovery"):
        recover(case)
    archive = next((case.home / "state" / "binding-recoveries").iterdir())
    original = (archive / "receipt.before.json").read_bytes()
    expected = (archive / "receipt.after.json").read_bytes()
    assert original == case.before
    assert case.receipt.read_bytes() == (expected if committed else original)
    assert read_json(archive / "journal.json")["state"] == "PREPARED"
    monkeypatch.setattr(recovery, "_commit_receipt", commit)
    result = recover(case)
    assert result["status"] == "INTAKE_REQUIRED"
    assert case.receipt.read_bytes() == expected
    assert (archive / "receipt.before.json").read_bytes() == original
    assert read_json(archive / "journal.json")["state"] == "COMMITTED"


@pytest.mark.parametrize("stage", ["archive-publication", "receipt-publication", "journal-publication"])
def test_retry_reestablishes_durability_after_a_directory_flush_failure(tmp_path, monkeypatch, stage):
    case = make_case(tmp_path)
    archive_parent = case.home / "state" / "binding-recoveries"
    flush = recovery._fsync_directory

    def interrupted_flush(path):
        fail = (
            (stage == "archive-publication" and path == archive_parent)
            or (stage == "receipt-publication" and path == case.receipt.parent)
            or (stage == "journal-publication" and (path / "journal.json").is_file()
                and read_json(path / "journal.json").get("state") == "COMMITTED")
        )
        if fail:
            raise OSError("synthetic directory flush failure")
        flush(path)

    monkeypatch.setattr(recovery, "_fsync_directory", interrupted_flush)
    with pytest.raises(OSError, match="synthetic directory flush failure"):
        recover(case)
    archive = next(archive_parent.iterdir())
    original = (archive / "receipt.before.json").read_bytes()
    expected = (archive / "receipt.after.json").read_bytes()
    immutable = {name: (archive / name).read_bytes() for name in (
        "receipt.before.json", "receipt.after.json", "request.json")}
    assert original == case.before
    assert case.receipt.read_bytes() == (original if stage == "archive-publication" else expected)
    assert read_json(archive / "journal.json")["state"] == (
        "COMMITTED" if stage == "journal-publication" else "PREPARED")

    events = []
    commit = recovery._commit_receipt
    mark = recovery._mark_committed

    def recording_flush(path):
        events.append(("flush", path))
        flush(path)

    def recording_commit(path, expected_bytes, new_bytes):
        events.append(("receipt", path))
        commit(path, expected_bytes, new_bytes)

    def recording_mark(path, journal):
        events.append(("journal-start", path))
        mark(path, journal)
        events.append(("journal-end", path))

    monkeypatch.setattr(recovery, "_fsync_directory", recording_flush)
    monkeypatch.setattr(recovery, "_commit_receipt", recording_commit)
    monkeypatch.setattr(recovery, "_mark_committed", recording_mark)
    assert recover(case)["status"] == "INTAKE_REQUIRED"
    journal_start = events.index(("journal-start", archive))
    journal_end = events.index(("journal-end", archive))
    assert ("flush", archive) in events[journal_start + 1:journal_end]
    assert ("flush", case.receipt.parent) in events[:journal_start]
    if stage == "archive-publication":
        commit_index = events.index(("receipt", case.receipt))
        assert ("flush", archive_parent) in events[:commit_index]
        assert ("flush", archive_parent.parent) in events[:commit_index]
    assert case.receipt.read_bytes() == expected
    assert read_json(archive / "journal.json")["state"] == "COMMITTED"
    assert {name: (archive / name).read_bytes() for name in immutable} == immutable


def test_retry_is_idempotent_and_never_clears_a_later_entry(tmp_path):
    case = make_case(tmp_path)
    first = recover(case)
    before = files(tmp_path)
    repeated = recover(case)
    assert repeated["replayed"] is True
    assert repeated["recovery_id"] == first["recovery_id"]
    assert files(tmp_path) == before
    p.enter(case.newroot, case.answers, session_id="fixture-chat", turn_id="new-turn",
            user_home=case.home)
    before = files(tmp_path)
    with pytest.raises(GateError):
        recover(case)
    assert files(tmp_path) == before


def test_unfinished_journal_never_clears_a_later_entry(tmp_path, monkeypatch):
    case = make_case(tmp_path)
    commit = recovery._commit_receipt

    def interrupted(path, expected_bytes, new_bytes):
        commit(path, expected_bytes, new_bytes)
        raise OSError("synthetic committed receipt with unfinished journal")

    monkeypatch.setattr(recovery, "_commit_receipt", interrupted)
    with pytest.raises(OSError):
        recover(case)
    monkeypatch.setattr(recovery, "_commit_receipt", commit)
    p.enter(case.newroot, case.answers, session_id="fixture-chat", turn_id="new-turn",
            user_home=case.home)
    before = files(tmp_path)
    with pytest.raises(GateError):
        recover(case)
    assert files(tmp_path) == before


@pytest.mark.parametrize("filename", ["receipt.before.json", "receipt.after.json", "request.json"])
def test_retry_never_overwrites_a_changed_archive(tmp_path, filename):
    case = make_case(tmp_path)
    result = recover(case)
    (Path(result["archive"]) / filename).write_bytes(b"synthetic archive corruption\n")
    before = files(tmp_path)
    with pytest.raises(GateError):
        recover(case)
    assert files(tmp_path) == before


def test_cli_requires_exact_inputs_and_explicit_permission(tmp_path):
    case = make_case(tmp_path)
    args = cli_args(case)
    before = files(tmp_path)
    with pytest.raises(GateError):
        p.command(args[:-1], case.home)
    assert files(tmp_path) == before
    result, code = p.command(args, case.home)
    assert code == 0 and result["status"] == "INTAKE_REQUIRED"
    assert result["task_id"] is None
    repeated, code = p.command(args, case.home)
    assert code == 0 and repeated["replayed"] is True


@pytest.mark.parametrize("flag", ["--root", "--expected-receipt-sha256"])
def test_cli_does_not_infer_missing_recovery_identity(tmp_path, flag):
    case = make_case(tmp_path)
    args = cli_args(case)
    index = args.index(flag)
    del args[index:index + 2]
    before = files(tmp_path)
    with pytest.raises(SystemExit) as raised:
        p.command(args, case.home)
    assert raised.value.code == 2
    assert files(tmp_path) == before
