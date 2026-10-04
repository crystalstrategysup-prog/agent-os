#!/usr/bin/env python3
"""Actual installed local completion canary, confined to one new output root.

No network, model launch, credentials, production, hooks or existing sessions.
Prepare runs real argv steps and a separate process recovery. Finalize requires
an independent review receipt. Outputs contain operational paths; keep private.
"""

from __future__ import annotations

import argparse
import email
import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from agent_os import __version__
from agent_os.continuation_adapter import LocalCompletionRunner
from agent_os.handoff import verify_completion_inventory
from agent_os.handoff_store import encoded, require, sha
from agent_os.safeio import filemap, read_json, within
from agent_os.work_coordination import Coordinator

OWNER = "local-canary-coordinator"
REVIEWER = "independent-canary-reviewer"
GOAL = "Produce and independently verify three actual scoped local checksum results"
REQUIRED_MODULES = {
    "__init__.py",
    "completion.py",
    "continuation_adapter.py",
    "result_gate.py",
    "work_coordination.py",
    "handoff.py",
    "handoff_store.py",
    "project.py",
    "safeio.py",
}


def now():
    return int(time.time())


def save(path, value):
    path.write_bytes(encoded(value))


def load(root):
    return json.loads((root / "canary.json").read_bytes())


def authorize(action, value):
    # Selecting caller authorizes only these constant, owned fixture actions.
    require(action in {"plan", "dispatch", "receiver-admit"}, "CANARY_SCOPE_DENIED")
    require(
        value.get("task_id", "local-canary-task") == "local-canary-task",
        "CANARY_TASK_MISMATCH",
    )


def runner(data):
    return LocalCompletionRunner(
        data["recipes"],
        verify_authority=authorize,
        read_dependencies=lambda: verify_runtime(data),
        read_clock=now,
    )


def verify_runtime(data):
    """Reread actual installed bytes and selected configuration on every step."""
    import agent_os

    require(
        verify_candidate(data["candidate_manifest"]) == data["module_hashes"],
        "CANARY_CURRENT_CANDIDATE_MISMATCH",
    )
    module_root = Path(agent_os.__file__).parent
    require(
        module_root.is_relative_to(Path(sys.prefix))
        and __version__ == data["runtime"]["version"],
        "INSTALLED_CANARY_RUNTIME_CHANGED",
    )
    for name, expected in data["module_hashes"].items():
        path = module_root / name
        require(
            path.is_file()
            and not path.is_symlink()
            and sha(path.read_bytes()) == expected,
            "INSTALLED_CANARY_MODULE_MISMATCH",
        )
    require(
        sha(encoded(data["recipes"])) == data["dependencies"]["configuration_hash"],
        "CANARY_CONFIGURATION_CHANGED",
    )
    return data["dependencies"]


def verify_candidate(manifest):
    """Compare the full wheel package inventory with actual installed bytes.

    This is provenance for an explicitly selected owned local fixture, not
    authentication of an arbitrary release manifest or permission to publish.
    """
    require(
        isinstance(manifest.get("module_hashes"), dict)
        and REQUIRED_MODULES <= manifest["module_hashes"].keys(),
        "CANARY_COMPLETE_MODULE_SET_REQUIRED",
    )
    wheel = Path(manifest["wheel_path"])
    source = Path(manifest["source_archive_path"])
    for path, digest in (
        (wheel, manifest["wheel_sha256"]),
        (source, manifest["source_archive_sha256"]),
    ):
        require(
            path.is_file()
            and not path.is_symlink()
            and path.stat().st_size <= 128 * 1024 * 1024
            and sha(path.read_bytes()) == digest,
            "CANARY_ARTIFACT_BYTES_MISMATCH",
        )
    # Reproduce the archive from the actual selected canonical Git object. A ZIP
    # comment or caller-supplied hash cannot establish commit provenance.
    repository = Path(manifest["source_git_root"])
    require(
        repository.is_dir() and not repository.is_symlink(),
        "CANARY_SOURCE_REPOSITORY_REQUIRED",
    )

    def git_read(*args):
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True,
            timeout=10,
            check=False,
        )
        require(
            result.returncode == 0 and len(result.stdout) <= 4096,
            "CANARY_SOURCE_GIT_READ_FAILED",
        )
        return result.stdout.decode("utf-8").strip()

    require(
        git_read("rev-parse", "HEAD") == manifest["source_commit"]
        and git_read("remote", "get-url", "origin") == manifest["origin_readback"]
        and manifest["repository_url"]
        == "https://github.com/crystalstrategysup-prog/agent-os",
        "CANARY_CANONICAL_SOURCE_MISMATCH",
    )
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "archive",
                "--format=zip",
                manifest["source_commit"],
            ],
            stdout=output,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        require(
            result.returncode == 0 and output.tell() <= 128 * 1024 * 1024,
            "CANARY_GIT_ARCHIVE_FAILED",
        )
        output.seek(0)
        require(
            sha(output.read()) == manifest["source_archive_sha256"],
            "CANARY_GIT_ARCHIVE_PROVENANCE_MISMATCH",
        )
    with zipfile.ZipFile(wheel) as archive:
        require(
            len(archive.infolist()) <= 4096
            and sum(x.file_size for x in archive.infolist()) <= 128 * 1024 * 1024
            and archive.testzip() is None,
            "CANARY_WHEEL_INTEGRITY_FAILED",
        )
        inventory = {}
        names = set()
        metadata = []
        for entry in archive.infolist():
            require(
                not entry.is_dir()
                and entry.filename not in names
                and not stat.S_ISLNK(entry.external_attr >> 16),
                "CANARY_WHEEL_INVENTORY_INVALID",
            )
            names.add(entry.filename)
            if entry.filename.endswith(".dist-info/METADATA"):
                metadata.append(email.message_from_bytes(archive.read(entry)))
            if entry.filename.startswith("agent_os/"):
                relative = entry.filename.removeprefix("agent_os/")
                within(Path(sys.prefix), relative)
                inventory[relative] = sha(archive.read(entry))
        require(
            inventory == manifest["module_hashes"], "CANARY_WHEEL_MODULE_SET_MISMATCH"
        )
        require(
            len(metadata) == 1
            and metadata[0]["Name"] == "crystal-agent-os"
            and metadata[0]["Version"] == manifest["version"],
            "CANARY_WHEEL_VERSION_MISMATCH",
        )
    with zipfile.ZipFile(source) as archive:
        require(
            archive.comment.decode("ascii") == manifest["source_commit"]
            and len(archive.infolist()) <= 4096
            and sum(x.file_size for x in archive.infolist()) <= 128 * 1024 * 1024
            and archive.testzip() is None,
            "CANARY_SOURCE_ARCHIVE_MISMATCH",
        )
        require(
            len(set(archive.namelist())) == len(archive.namelist()),
            "CANARY_SOURCE_ARCHIVE_MISMATCH",
        )
        for name, digest in inventory.items():
            require(
                sha(archive.read("src/agent_os/" + name)) == digest,
                "CANARY_WHEEL_SOURCE_MISMATCH",
            )
        require(
            sha(archive.read("docs/completion/COMPLETION_CONTRACT.md"))
            == manifest["contract_hash"],
            "CANARY_CONTRACT_SOURCE_MISMATCH",
        )
        driver = archive.read("tools/completion_canary.py")
        require(
            sha(driver) == manifest["driver_sha256"]
            and Path(__file__).read_bytes() == driver,
            "CANARY_DRIVER_MISMATCH",
        )
    receipt = read_json(Path(sys.prefix) / ".agentos-candidate-install.json")
    require(
        receipt["schema"] == "agentos.candidate-install/v1"
        and receipt["sys_prefix"] == sys.prefix
        and receipt["exit_code"] == 0
        and receipt["version"] == __version__ == manifest["version"]
        and receipt["wheel_sha256"] == manifest["wheel_sha256"]
        and receipt["module_hashes"] == inventory
        and receipt["source_archive_sha256"] == manifest["source_archive_sha256"]
        and receipt["driver_sha256"] == manifest["driver_sha256"],
        "CANARY_INSTALLED_RECEIPT_MISMATCH",
    )
    log = Path(receipt["log_path"])
    require(
        log.is_file()
        and not log.is_symlink()
        and log.stat().st_size <= 4 * 1024 * 1024
        and sha(log.read_bytes()) == receipt["log_sha256"],
        "CANARY_INSTALL_LOG_MISMATCH",
    )
    return inventory


def create(root, data, stream):
    session = {
        "session_id": "local-canary-logical-session",
        "kind": "session",
        "parent_session_id": None,
    }
    rows = [
        {
            "work_id": "local-canary-work",
            "entity_id": "local-canary-entity",
            "handoff_id": "local-canary-initial",
            "role": "worker",
            "session": session,
            "depends_on": [],
            "write_set": [{"resource": "local-canary-workspace", "paths": ["."]}],
            "state": "pending",
            "required": True,
        }
    ]
    co = Coordinator.create(
        root / "home",
        stream,
        OWNER,
        GOAL,
        [r["criterion_id"] for r in data["contract"]["criteria"]],
        rows,
        coordinator_session=session,
    )
    co.activate_completion(
        OWNER, co.read()["revision"], data["contract"], data["policy"], now()
    )
    cap = {
        "status": "SUPPORTED",
        "adapter_version": "local-completion/v1",
        "runtime_version": platform.python_version(),
        "source": "actual-installed-canary-argv",
        "target_class": "owned-local-canary",
        "scope": "local-canary-task",
        "evidence_hash": sha(encoded(data["module_hashes"])),
        "checked_at": now(),
        "expires_at": now() + 200,
    }
    co.completion_update_route(
        OWNER, co.read()["revision"], now(), capabilities={"resume": cap}
    )
    return co


def prepare(root, manifest):
    require(not root.exists(), "CANARY_ROOT_MUST_BE_ABSENT")
    require(manifest["version"] == __version__, "INSTALLED_CANARY_VERSION_MISMATCH")
    verify_candidate(manifest)
    import agent_os

    module_root = Path(agent_os.__file__).parent
    require(
        module_root.is_relative_to(Path(sys.prefix)),
        "INSTALLED_CANARY_RUNTIME_REQUIRED",
    )
    module_hashes = {}
    for name, expected in manifest["module_hashes"].items():
        path = module_root / name
        require(
            path.is_file()
            and not path.is_symlink()
            and sha(path.read_bytes()) == expected,
            "INSTALLED_CANARY_MODULE_MISMATCH",
        )
        module_hashes[name] = expected
    root.mkdir(mode=0o700)
    workspace = root / "workspace"
    workspace.mkdir()
    recipes = {}
    for i in range(3):
        script = (
            "import hashlib,json;from pathlib import Path;"
            f"n={i + 1};b=('AgentOS real local step '+str(n)).encode();"
            "v={'step':n,'sha256':hashlib.sha256(b).hexdigest()};"
            "p=Path('result-'+str(n)+'.json');p.write_text(json.dumps(v,sort_keys=True)+'\\n');"
            "assert json.loads(p.read_text())==v;print('ACTUAL_LOCAL_STEP_'+str(n)+'_PASS')"
        )
        recipes[str(i)] = {
            "argv": [sys.executable, "-c", script],
            "workspace": str(workspace),
            "timeout": 5,
            "artifact_paths": [f"result-{i + 1}.json"],
        }
    dependencies = {
        "source_commit": manifest["source_commit"],
        "contract_hash": manifest["contract_hash"],
        "build_hash": manifest["wheel_sha256"],
        "configuration_hash": sha(encoded(recipes)),
        "environment_fingerprint": sha(
            encoded(
                {
                    "platform": platform.platform(),
                    "executable": sys.executable,
                    "root": str(root),
                    "module_hashes": module_hashes,
                }
            )
        ),
    }
    criteria = [
        {
            "criterion_id": f"local-criterion-{i + 1}",
            "requirement_ids": ["R02", "R33"],
            "operation": "resume",
            "target": "owned-local-canary",
            "receiver": "local-canary-receiver",
            "data_hash": sha(encoded(recipe)),
            "recipe_id": name,
        }
        for i, (name, recipe) in enumerate(recipes.items())
    ]
    contract = {
        "schema": "agentos.completion-contract/v1",
        "task_id": "local-canary-task",
        "goal": GOAL,
        "acceptance_owner": REVIEWER,
        **dependencies,
        "criteria": criteria,
        "budget": {
            "steps": 8,
            "deadline": now() + 600,
            "tokens": 100,
            "cost_units": 100,
        },
        "limits": {
            "max_attempts": 3,
            "max_no_progress": 2,
            "lease_seconds": 60,
            "ack_timeout": 120,
            "backoff": [5, 20, 60],
        },
    }
    policy = {
        "revision": 1,
        "actor": OWNER,
        "expires_at": now() + 600,
        "revoked": False,
        "scope": [
            {
                **{k: r[k] for k in ("operation", "target", "receiver", "data_hash")},
                "environment_fingerprint": dependencies["environment_fingerprint"],
            }
            for r in criteria
        ],
        "source_ref": "explicit-owner-disposable-local-canary-scope",
    }
    data = {
        "schema": "agentos.local-completion-canary/v1",
        "recipes": recipes,
        "dependencies": dependencies,
        "contract": contract,
        "policy": policy,
        "module_hashes": module_hashes,
        "candidate_manifest": manifest,
        "runtime": {
            "version": __version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
    }
    save(root / "canary.json", data)
    co = create(root, data, "completion-canary")
    run = runner(data).run_bounded(co, OWNER, clock=now, max_steps=3)
    require(
        len(run["runs"]) == 3 and run["status"]["project_state"] == "VERIFYING",
        "CANARY_THREE_STEPS_FAILED",
    )
    require(co.read()["parent_state"] == "open", "CANARY_PREMATURE_ACCEPTANCE")
    save(root / "three-steps.json", run)
    # Separate unfinished stream: one real result, complete source/state backup,
    # then a fresh interpreter verifies recovery and performs the safe remainder.
    recovery = create(root, data, "recovery-canary")
    require(
        runner(data).run(recovery, OWNER, now())["status"] == "PASS",
        "CANARY_FIRST_RECOVERY_STEP_FAILED",
    )
    source = root / "recovery-source"
    source.mkdir()
    (source / "source.py").write_text('print("scoped tracked source")\n')
    (source / "untracked.txt").write_text("unfinished scoped untracked work\n")
    (source / "dirty.patch").write_text("scoped actual dirty patch bytes\n")
    inventory = filemap(source)
    target = {
        "target_ref": "owned-local-recovery-canary",
        "environment": dependencies["environment_fingerprint"],
        "source_commit": dependencies["source_commit"],
        "branch": "isolated-canary",
        "process_inventory": [],
        "ownership_verified": True,
        "source_manifest": {
            "schema": "agentos.completion-source-checkpoint/v1",
            "tracked_paths": ["source.py"],
            "untracked_paths": ["untracked.txt"],
            "dirty_patch_path": "dirty.patch",
            "inventory_sha256": sha(encoded(inventory)),
        },
    }
    cp = recovery.completion_checkpoint(
        OWNER,
        recovery.read()["revision"],
        now(),
        source,
        list(inventory),
        lambda *_: target,
    )
    rehearsal = recovery.completion_rehearse_restore(
        cp["checkpoint_ref"], root / "rehearsal"
    )
    save(
        root / "recovery.json",
        {"checkpoint": cp, "rehearsal": rehearsal, "target": target},
    )
    from agent_os.project import _bounded_check_process

    argv = [
        sys.executable,
        str(Path(__file__).resolve()),
        "recover",
        "--root",
        str(root),
    ]
    exit_code, output = _bounded_check_process(argv, Path.cwd(), dict(os.environ), 30)
    require(exit_code == 0, "ACTUAL_RESTART_RECOVERY_FAILED")
    save(
        root / "restart-receipt.json",
        {
            "argv_hash": sha(encoded(argv)),
            "exit_code": exit_code,
            "output": output,
            "runtime": data["runtime"],
            "process_completed": True,
        },
    )
    print(
        json.dumps(
            {
                "status": "CANARY_PREPARED_REVIEW_REQUIRED",
                "root": str(root),
                "three_real_steps": 3,
                "recovery_restart": "PASS",
                "project_accepted": False,
            }
        )
    )


def recover(root):
    data = load(root)
    verify_runtime(data)
    packet = json.loads((root / "recovery.json").read_bytes())
    old = Coordinator(root / "home", "recovery-canary")
    require(old.read()["completion"]["paused"] is True, "OLD_CANARY_WRITER_NOT_PAUSED")
    # New state namespace is the verified paused canonical snapshot, not a
    # competing active store. Old writer remains paused; no pending effects.
    co = Coordinator(root / "rehearsal/.agentos-recovery", "recovery-canary")
    checkpoint, _ = co.completion_verify_checkpoint(
        packet["checkpoint"]["checkpoint_ref"]
    )
    require(
        not co.completion_status(now())["unknown_operations"], "UNKNOWN_EFFECT_NO_RETRY"
    )
    target = {
        k: packet["target"][k] for k in ("target_ref", "environment", "source_commit")
    }
    target.update(
        old_writer_quiescent=False,
        receiver_fence_verified=True,
        current_authority=True,
        reconciled_operation_ids=[],
        restored_artifact_hashes=[v["sha256"] for v in checkpoint["captures"]],
    )
    for capture in checkpoint["captures"]:
        require(
            sha((root / "rehearsal" / capture["path"]).read_bytes())
            == capture["sha256"],
            "RESTORED_CANARY_BYTES_MISMATCH",
        )
    rehearsal_ref = co._completion_store().put_json(packet["rehearsal"])
    co.completion_restore(
        OWNER,
        co.read()["revision"],
        now(),
        packet["checkpoint"]["checkpoint_ref"],
        rehearsal_ref,
        lambda *_: target,
    )
    require(
        len(co.completion_status(now())["remaining"]) == 2, "RECOVERY_PROGRESS_LOST"
    )
    result = runner(data).run_bounded(co, OWNER, clock=now, max_steps=2)
    require(
        len(result["runs"]) == 2 and result["status"]["project_state"] == "VERIFYING",
        "RECOVERY_REMAINDER_FAILED",
    )
    require(old.read()["completion"]["paused"] is True, "OLD_CANARY_WRITER_REVIVED")
    save(
        root / "recovery-result.json",
        {
            "schema": "agentos.local-recovery-result/v1",
            "pid": os.getpid(),
            "runtime": data["runtime"],
            "actual_recovered_state": co.read(),
            "next_safe_runs": result,
            "tracked_untracked_bytes_verified": True,
            "old_dispatch_paused": True,
        },
    )
    print("ACTUAL_RESTART_UNFINISHED_RECOVERY_PASS")


def heartbeat(root):
    verify_runtime(load(root))
    co = Coordinator(root / "home", "completion-canary")
    co.completion_heartbeat(OWNER, co.read()["revision"], now())
    print("CANARY_LIVE_LEASE_REFRESHED")


def finalize(root, review_path):
    data = load(root)
    verify_runtime(data)
    co = Coordinator(root / "home", "completion-canary")
    review = json.loads(review_path.read_bytes())
    require(
        review["status"] == "PASS"
        and review["independent"] is True
        and review["dependencies"] == data["dependencies"],
        "INDEPENDENT_CANARY_REVIEW_REQUIRED",
    )
    store = co._completion_store()
    # Independently supplied byte receipts plus current native outputs are read
    # again; a review label alone is insufficient.
    for i in range(1, 4):
        raw = (root / "workspace" / f"result-{i}.json").read_bytes()
        require(
            sha(raw) == review["artifact_hashes"][f"result-{i}.json"],
            "CANARY_REVIEW_BYTES_CHANGED",
        )
        require(
            json.loads(raw)
            == {
                "step": i,
                "sha256": hashlib.sha256(
                    f"AgentOS real local step {i}".encode()
                ).hexdigest(),
            },
            "CANARY_SEMANTIC_RESULT_FAILED",
        )
    c = co.read()["completion"]
    evidence = store.put(review_path.read_bytes())
    review_receipt = {
        "schema": "agentos.completion-review/v1",
        "reviewer": REVIEWER,
        "generation": c["generation"],
        **data["dependencies"],
        "result_refs": {k: v["receipt_ref"] for k, v in c["results"].items()},
        "blocking_findings": [],
        "semantic_acceptance": True,
        "docs_consistent": True,
        "checked_at": now(),
        "evidence_refs": [evidence],
    }
    co.completion_review(
        OWNER,
        co.read()["revision"],
        store.put_json(review_receipt),
        now(),
        lambda receipt: require(
            receipt["evidence_refs"] == [evidence], "CANARY_REVIEW_ORIGIN_MISMATCH"
        ),
    )
    receiver = root / "receiver"
    receiver.mkdir()
    artifacts = []
    for name in sorted(review["artifact_hashes"]):
        raw = (root / "workspace" / name).read_bytes()
        (receiver / name).write_bytes(raw)
        artifacts.append({"path": name, "size_bytes": len(raw), "sha256": sha(raw)})
    manifest = {
        "schema_version": "1.0.0",
        "task_id": "local-canary-task",
        "generation": c["generation"],
        **{k: data["dependencies"][k] for k in ("source_commit", "contract_hash")},
        "artifacts": artifacts,
        "integrity": "HASH_VERIFIED",
        "signature_ref": None,
    }
    envelope = {
        "schema": "agentos.completion-handoff/v1",
        "handoff_id": "local-canary-output",
        "operation_id": "local-canary-transfer",
        "task_id": "local-canary-task",
        "generation": c["generation"],
        "from_ref": OWNER,
        "to_ref": "local-canary-receiver",
        **{k: data["dependencies"][k] for k in ("source_commit", "contract_hash")},
        "manifest": manifest,
        "manifest_hash": sha(encoded(manifest)),
        "remaining_requirements": [],
        "next_step": "Read the three independently accepted checksum results",
        "policy_scope_ref": "explicit-owner-disposable-local-canary-scope",
        "expiry": now() + 100,
        "ownership_transition": "KEEP_OWNER",
        "sender_receipt": None,
        "authentication_mechanism": "owner-selected-local-byte-adapter",
        "target_environment": data["dependencies"]["environment_fingerprint"],
    }
    co.completion_prepare_handoff(
        OWNER, co.read()["revision"], envelope, receiver, now(), lambda *_: None
    )
    co.completion_handoff_sent(OWNER, co.read()["revision"], now())
    inventory = verify_completion_inventory(receiver, manifest)
    ack = {
        "schema_version": "1.0.0",
        "purpose": "EXECUTION_HANDOFF",
        **{
            k: envelope[k]
            for k in ("handoff_id", "operation_id", "task_id", "generation")
        },
        "receiver_ref": envelope["to_ref"],
        "verified_commit": envelope["source_commit"],
        "commit_status": "VERIFIED",
        "verified_contract_hash": envelope["contract_hash"],
        "verified_manifest_hash": inventory["manifest_hash"],
        "received_artifact_hashes": inventory["artifact_hashes"],
        "accepted_scope": [envelope["policy_scope_ref"]],
        "next_step": envelope["next_step"],
        "actual_environment": envelope["target_environment"],
        "received_at": datetime.now(UTC).isoformat(),
        "status": "ACKED",
        "verification_method": "Actual isolated receiver bytes and current reviewed source manifest",
        "can_mutate": False,
    }

    def verify_receiver(value):
        require(value == ack, "CANARY_ACK_ORIGIN_MISMATCH")
        readback = verify_completion_inventory(receiver, manifest)
        return {
            "manifest_hash": readback["manifest_hash"],
            "artifact_hashes": readback["artifact_hashes"],
            "source_commit": data["dependencies"]["source_commit"],
            "contract_hash": data["dependencies"]["contract_hash"],
            "receiver_ref": envelope["to_ref"],
            "environment": envelope["target_environment"],
        }

    co.completion_ack(
        OWNER, co.read()["revision"], store.put_json(ack), now(), verify_receiver
    )
    def verify_acceptance(_):
        verify_receiver(ack)
        return True

    co.completion_accept(OWNER, co.read()["revision"], now(), verify_acceptance)
    before = co.read()
    require(
        not runner(data).run_bounded(co, OWNER, clock=now)["runs"],
        "ACCEPTED_CANARY_RESTARTED",
    )
    require(co.read() == before, "TERMINAL_CANARY_MUTATED")
    save(
        root / "acceptance.json",
        {
            "status": "PASS",
            "candidate_dependencies": data["dependencies"],
            "actual_runtime": data["runtime"],
            "coordinator": co.completion_status(now()),
            "receiver_ack": ack,
            "independent_review_sha256": sha(review_path.read_bytes()),
            "parent_upgrade_complete": False,
        },
    )
    print("INSTALLED_LOCAL_CANARY_ACCEPTED_PARENT_UPGRADE_OPEN")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", choices=["prepare", "recover", "heartbeat", "finalize"]
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    root = args.root.absolute()
    if args.phase == "prepare":
        require(args.manifest is not None, "CANARY_MANIFEST_REQUIRED")
        prepare(root, json.loads(args.manifest.read_bytes()))
    elif args.phase == "recover":
        recover(root)
    elif args.phase == "heartbeat":
        heartbeat(root)
    else:
        require(args.review is not None, "INDEPENDENT_CANARY_REVIEW_REQUIRED")
        finalize(root, args.review)


if __name__ == "__main__":
    main()
