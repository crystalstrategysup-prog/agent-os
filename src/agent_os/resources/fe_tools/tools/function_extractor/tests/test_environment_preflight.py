import json
from pathlib import Path
from types import SimpleNamespace

from tools.function_extractor.runner.environment import select_existing_environment


PIN = "sha256:" + "a" * 64


def case(tmp_path, image=PIN):
    path = tmp_path / ".agentos/route-probe/container/IMAGE.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"image_id": image, "capsule_root": str(tmp_path),
                                "files": [{"path": "x", "sha256": "b" * 64, "bytes": 1}]}))
    return path


def test_exact_local_selection(tmp_path):
    case(tmp_path)
    result = select_existing_environment(tmp_path, inspect=lambda _: SimpleNamespace(returncode=0, stdout=PIN+"\n"),
                                         capsule_check=lambda *a: None)
    assert result["status"] == "EXISTING_QUALIFIED"
    assert result["execution_authorized"] is False


def test_missing_image_refuses(tmp_path):
    case(tmp_path)
    assert select_existing_environment(tmp_path, inspect=lambda _: SimpleNamespace(returncode=1, stdout=""),
                                       capsule_check=lambda *a: None)["status"] == "MISSING_IMAGE"


def test_mismatched_identity_refuses(tmp_path):
    case(tmp_path)
    assert select_existing_environment(tmp_path, inspect=lambda _: SimpleNamespace(returncode=0, stdout="sha256:"+"b"*64),
                                       capsule_check=lambda *a: None)["status"] == "MISSING_IMAGE"


def test_invalid_pin_refuses_without_inspection(tmp_path):
    case(tmp_path, image="latest")
    assert select_existing_environment(tmp_path, inspect=lambda _: (_ for _ in ()).throw(AssertionError("inspect_called")),
                                       capsule_check=lambda *a: None)["status"] == "REFUSED"


def test_corrupt_capsule_refuses_without_inspection(tmp_path):
    case(tmp_path)
    def reject(*args):
        raise ValueError("capsule_pin")
    assert select_existing_environment(tmp_path, inspect=lambda _: (_ for _ in ()).throw(AssertionError("inspect_called")),
                                       capsule_check=reject)["status"] == "REFUSED"


def test_absent_or_symlinked_profile_refuses(tmp_path):
    assert select_existing_environment(tmp_path)["status"] == "REFUSED"
    path=case(tmp_path)
    real=tmp_path/"other.json"
    path.rename(real)
    path.symlink_to(real)
    assert select_existing_environment(tmp_path)["status"] == "REFUSED"
