"""Installer capability declarations reject contradictory and repeated JSON fields."""

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/install.py"
SPEC = importlib.util.spec_from_file_location("strict_capability_installer", SCRIPT)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)

DECLARATIONS = [
    ("continuation-capabilities-v1.json", "wheel_continuation_schemas", "provider_io", {
        "schema": "agentos.continuation-capabilities/v1",
        "readable_item_schemas": ["agentos.continuation-item/v1", "agentos.continuation-item/v2"],
        "transition_item_schemas": ["agentos.continuation-item/v2"],
        "receipt_schema": "agentos.continuation-delivery-receipt/v2",
        "legacy_promotion": "untouched_pending_only", "provider_io": False,
    }),
    ("continuation-capabilities-v2.json", "wheel_continuation_schemas", "provider_io", {
        "schema": "agentos.continuation-capabilities/v2",
        "readable_item_schemas": ["agentos.continuation-item/v1", "agentos.continuation-item/v2",
                                  "agentos.continuation-item/v3"],
        "transition_item_schemas": ["agentos.continuation-item/v2", "agentos.continuation-item/v3"],
        "receipt_schemas": ["agentos.continuation-delivery-receipt/v2",
                            "agentos.continuation-delivery-receipt/v3"],
        "causal_acceptance_scope": "received_only",
        "legacy_promotion": "untouched_pending_only", "provider_io": False,
    }),
    ("completion-install-v1.json", "wheel_coordination_schemas", "implicit_activation", {
        "schema": "agentos.completion-install/v1",
        "readable_coordination_schemas": ["agentos.work-coordination/v1", "agentos.work-coordination/v2"],
        "implicit_activation": False, "unsupported_downgrade": "preserve_and_hold",
    }),
]


def wheel(folder, name, raw):
    path = folder / "synthetic-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("agent_os/resources/contracts/" + name, raw)
    return path


@pytest.mark.parametrize("name,reader,field,declaration", DECLARATIONS)
def test_unambiguous_capability_contracts_keep_compatible_readers(tmp_path, name, reader, field, declaration):
    path = wheel(tmp_path, name, json.dumps(declaration).encode())
    expected = declaration.get("readable_item_schemas", declaration.get("readable_coordination_schemas"))
    assert getattr(installer, reader)(path) == expected


@pytest.mark.parametrize("name,reader,field,declaration", DECLARATIONS)
@pytest.mark.parametrize("first", [True, False])
def test_duplicate_capability_fields_are_refused_even_if_values_match(tmp_path, name, reader,
                                                                     field, declaration, first):
    raw = ('{' + json.dumps(field) + ':' + json.dumps(first) + ','
           + json.dumps(declaration)[1:]).encode()
    path = wheel(tmp_path, name, raw)
    with pytest.raises(installer.InstallError, match="metadata_duplicate_key"):
        getattr(installer, reader)(path)


@pytest.mark.parametrize("name,reader,field,declaration", DECLARATIONS)
@pytest.mark.parametrize("apply", [False, True])
def test_ambiguous_install_plan_and_apply_leave_core_and_user_untouched(tmp_path, name, reader,
                                                                     field, declaration, apply):
    raw = ('{' + json.dumps(field) + ':true,' + json.dumps(declaration)[1:]).encode()
    path = wheel(tmp_path, name, raw)
    core, user = tmp_path / "managed-core", tmp_path / "owner-overlay"
    user.mkdir()
    sentinel = user / "owner-note"
    sentinel.write_bytes(b"Owner content stays unchanged.\n")
    argv = ["install", "--wheel", str(path), "--sha256", installer.digest(path),
            "--version", "1.0.0", "--core-home", str(core), "--user-home", str(user)]
    if apply:
        argv += ["--apply", "--expected-current", "none"]
    with pytest.raises(installer.InstallError, match="metadata_duplicate_key"):
        installer.execute(installer.parser().parse_args(argv))
    assert not core.exists()
    assert list(user.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"Owner content stays unchanged.\n"
