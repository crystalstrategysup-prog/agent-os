"""Actual Coordinator state guards installer update/rollback reader selection."""

import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from test_completion import completion as _completion_fixture

from agent_os.safeio import filemap

completion = _completion_fixture
spec = importlib.util.spec_from_file_location(
    "completion_installer", Path(__file__).resolve().parents[1] / "tools/install.py"
)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_activated_completion_refuses_older_installer_without_any_data_write(
    completion,
):
    co, *_ = completion
    home = co.root.parents[2]
    before = filemap(home)
    old = {
        "overlay_schema": 1,
        "config_schema": "agent-os.community-config/v5",
        "continuation_schemas": [],
    }
    with pytest.raises(
        installer.InstallError,
        match="coordination_store_incompatible_preserve_and_hold",
    ):
        installer.check_user_compatibility(home, old)
    assert filemap(home) == before
    new = {
        **old,
        "coordination_schemas": [
            "agentos.work-coordination/v1",
            "agentos.work-coordination/v2",
        ],
    }
    with installer.coordination_locks(home):
        installer.check_user_compatibility(home, new)
    assert filemap(home) == before


def test_corrupt_current_snapshot_and_active_writer_block_install(completion):
    import fcntl

    co, *_ = completion
    home = co.root.parents[2]
    new = {
        "overlay_schema": 1,
        "config_schema": "agent-os.community-config/v5",
        "continuation_schemas": [],
        "coordination_schemas": [
            "agentos.work-coordination/v1",
            "agentos.work-coordination/v2",
        ],
    }
    with (co.root / "publisher.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with (
            pytest.raises(
                installer.InstallError,
                match="coordination_writer_active_preserve_and_hold",
            ),
            installer.coordination_locks(home),
        ):
            pytest.fail("active writer must not be switched")
    head = json.loads((co.root / "HEAD.json").read_bytes())
    snapshot = co.root / "snapshots" / (head["snapshot_sha256"] + ".json")
    snapshot.write_bytes(snapshot.read_bytes() + b" ")
    with pytest.raises(
        installer.InstallError, match="user_coordination_snapshot_invalid"
    ):
        installer.check_user_compatibility(home, new)


def test_wheel_completion_declaration_is_exact_and_missing_decl_never_grants_v2(
    tmp_path,
):
    root = Path(__file__).resolve().parents[1]
    raw = (root / "schemas/completion-install-v1.json").read_bytes()
    assert (
        raw
        == (
            root / "src/agent_os/resources/contracts/completion-install-v1.json"
        ).read_bytes()
    )
    wheel = tmp_path / "demo.whl"
    with ZipFile(wheel, "w"):
        pass
    assert installer.wheel_coordination_schemas(wheel) == [
        "agentos.work-coordination/v1"
    ]
    name = "agent_os/resources/contracts/completion-install-v1.json"
    with ZipFile(wheel, "w") as archive:
        archive.writestr(name, raw)
    assert installer.wheel_coordination_schemas(wheel) == [
        "agentos.work-coordination/v1",
        "agentos.work-coordination/v2",
    ]
    invalid = json.loads(raw)
    invalid["implicit_activation"] = True
    with ZipFile(wheel, "w") as archive:
        archive.writestr(name, json.dumps(invalid))
    with pytest.raises(
        installer.InstallError, match="wheel_completion_capabilities_invalid"
    ):
        installer.wheel_coordination_schemas(wheel)
