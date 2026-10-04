"""Public candidate scanner controls never include real owner data."""

import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "control",
    [
        b"PRIVATE-" + b"DO-NOT-PUBLISH",
        b"sk-" + b"a" * 32,
        b"-----BEGIN " + b"OPENSSH PRIVATE KEY-----",
    ],
)
def test_actual_public_tree_scanner_blocks_synthetic_contamination(tmp_path, control):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "public_candidate_scanner", root / "tools/verify_public.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = tmp_path
    (tmp_path / "pyproject.toml").write_bytes((root / "pyproject.toml").read_bytes())
    (tmp_path / "contaminated.txt").write_bytes(control)
    result = module.verify()
    assert result["status"] == "FAIL"
    assert any(
        e.startswith(("secret_shape:", "private_marker:")) for e in result["errors"]
    )
    assert control.decode() not in repr(result)
