import json
from types import SimpleNamespace
from tools.function_extractor.runner.environment_catalog import discover, prepare_offline_build

A = "sha256:" + "a"*64
B = "sha256:" + "b"*64
S = "c"*64

def profile(image):
    return dict(image_id=image, capsule_root="/tmp/fixture", files=[dict(path="x",bytes=1,sha256=S)],
                source_ref=S, python_abi="cp311")

def write(tmp_path, items):
    p=tmp_path/".agentos/route-probe/container/ENVIRONMENTS.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(schema="fe.environments/v1",profiles=items)))

def inspector(allowed):
    return lambda x: SimpleNamespace(returncode=0 if x in allowed else 1,stdout=x if x in allowed else "")

def test_exact_candidate(tmp_path):
    write(tmp_path,[profile(A),profile(B)])
    v=discover(tmp_path,inspect=inspector({B}),capsule_check=lambda *a: None)
    assert v["status"]=="EXISTING_QUALIFIED" and v["image_id"]==B

def test_missing(tmp_path):
    write(tmp_path,[profile(A)])
    assert discover(tmp_path,inspect=inspector(set()),capsule_check=lambda *a:None)["status"]=="MISSING_IMAGE"

def test_ambiguous(tmp_path):
    write(tmp_path,[profile(A),profile(B)])
    assert discover(tmp_path,inspect=inspector({A,B}),capsule_check=lambda *a:None)["reason"]=="ambiguous_qualified_images"

def test_invalid_and_duplicate(tmp_path):
    write(tmp_path,[profile("python:latest")])
    assert discover(tmp_path,inspect=inspector(set()),capsule_check=lambda *a:None)["status"]=="REFUSED"
    write(tmp_path,[profile(A),profile(A)])
    assert discover(tmp_path,inspect=inspector({A}),capsule_check=lambda *a:None)["status"]=="REFUSED"

def test_bad_capsule(tmp_path):
    write(tmp_path,[profile(A)])
    def fail(*a):raise ValueError("bad")
    assert discover(tmp_path,inspect=inspector({A}),capsule_check=fail)["status"]=="REFUSED"

def test_offline_plan_only():
    p=prepare_offline_build(base_image=A,wheels=[dict(name="abc-1-py3-none-any.whl",sha256=S)],image_name="fe-test-avl",source_ref=S)
    assert p["status"]=="BUILD_PLAN_READY" and not p["build_performed"] and p["plan"]["network"]=="none"

def test_unpinned_build_rejected():
    assert prepare_offline_build(base_image="python:latest",wheels=[],image_name="fe-test-avl",source_ref=S)["status"]=="REFUSED"

def test_runtime_catalog_explicit_refuses_unbound_image(tmp_path, monkeypatch):
    from tools.function_extractor.runner import container
    import json
    from pathlib import Path
    repo = tmp_path / "repo"
    config = repo / ".agentos/route-probe/container/IMAGE.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"image_id": A, "capsule_root": "/tmp/fixture",
                                  "files": [{"path":"x","bytes":1,"sha256":S}]}))
    write(repo,[profile(B)])
    monkeypatch.setattr(container, "__file__", str(repo / "tools/function_extractor/runner/container.py"))
    monkeypatch.setattr(container, "_capsule", lambda *a: tmp_path)
    from tools.function_extractor.runner import environment_catalog as ec
    monkeypatch.setattr(ec, "discover", lambda *a,**k:{
        "status": "EXISTING_QUALIFIED", "image_id": B})
    result=container.execute_container(None,{},timeout=2)
    assert result["status"]=="REFUSED" and result["reason"]=="candidate_profile_not_bound"


def test_runtime_catalog_missing_refuses_before_lease(tmp_path, monkeypatch):
    from tools.function_extractor.runner import container
    import json
    repo=tmp_path/"repo"
    config=repo/".agentos/route-probe/container/IMAGE.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"image_id": A, "capsule_root": "/tmp/fixture", "files":[]}))
    write(repo,[profile(B)])
    monkeypatch.setattr(container,"__file__",str(repo/"tools/function_extractor/runner/container.py"))
    monkeypatch.setattr(container,"_lease",lambda _: (_ for _ in ()).throw(AssertionError("lease_called")))
    from tools.function_extractor.runner import environment_catalog as ec
    monkeypatch.setattr(ec,"discover",lambda *a,**k:{"status":"MISSING_IMAGE"})
    result=container.execute_container(None,{},timeout=2)
    assert result["status"]=="REFUSED" and result["reason"]=="qualified_environment_missing_image"

def test_build_missing_requires_existing_lease_and_does_not_docker(tmp_path):
    from tools.function_extractor.runner.environment_catalog import build_missing_environment
    p=prepare_offline_build(base_image=A,wheels=[],image_name="fe-test-empty",source_ref=S)
    assert build_missing_environment(plan=p,local_wheelhouse=tmp_path,lease_assert=lambda _: (_ for _ in ()).throw(ValueError("denied")),docker=lambda *a: (_ for _ in ()).throw(AssertionError("docker")))["status"]=="REFUSED"

def test_build_missing_refuses_bad_wheel_before_lease(tmp_path):
    from tools.function_extractor.runner.environment_catalog import build_missing_environment
    p=prepare_offline_build(base_image=A,wheels=[{"name":"a-1-py3-none-any.whl","sha256":S}],image_name="fe-test-empty",source_ref=S)
    assert build_missing_environment(plan=p,local_wheelhouse=tmp_path,lease_assert=lambda _: (_ for _ in ()).throw(AssertionError("lease")))["reason"]=="wheel_invalid"


def test_ensure_reuses_existing_without_builder(tmp_path):
    from tools.function_extractor.runner.environment_catalog import ensure_environment
    got=ensure_environment(tmp_path,plan={},local_wheelhouse=tmp_path,
        discover_fn=lambda _: {"status":"EXISTING_QUALIFIED","image_id":A},
        build_fn=lambda **k: (_ for _ in ()).throw(AssertionError("build_invoked")))
    assert got["status"]=="EXISTING_QUALIFIED"


def test_ensure_missing_builds_but_not_automatically_admitted(tmp_path):
    from tools.function_extractor.runner.environment_catalog import ensure_environment
    plan=prepare_offline_build(base_image=A,wheels=[],image_name="fe-test-temp",source_ref=S)
    got=ensure_environment(tmp_path,plan=plan,local_wheelhouse=tmp_path,
        discover_fn=lambda _: {"status":"MISSING_IMAGE"},
        build_fn=lambda **k: {"status":"IMAGE_BUILT_UNQUALIFIED","image_id":B})
    assert got["status"]=="CREATED_PENDING_QUALIFICATION" and got["image_id"]==B


def test_ensure_rejects_ambiguity_and_never_builds(tmp_path):
    from tools.function_extractor.runner.environment_catalog import ensure_environment
    got=ensure_environment(tmp_path,plan={},local_wheelhouse=tmp_path,
        discover_fn=lambda _: {"status":"REFUSED"},
        build_fn=lambda **k: (_ for _ in ()).throw(AssertionError("build_invoked")))
    assert got["status"]=="REFUSED"



def test_missing_plan_rejects_missing_wheelhouse(tmp_path):
    from tools.function_extractor.runner.environment_catalog import ensure_environment
    plan=prepare_offline_build(base_image=A,wheels=[],image_name="fe-test-tempx",source_ref=S)
    got=ensure_environment(tmp_path,plan=plan,local_wheelhouse=None,
        discover_fn=lambda _: {"status":"MISSING_IMAGE"})
    assert got["status"]=="REFUSED" and got["reason"]=="wheelhouse_missing"
