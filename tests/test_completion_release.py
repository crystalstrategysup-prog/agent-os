"""Synthetic release decisions never grant real publication authority."""

import copy

import pytest

from agent_os.handoff_store import HandoffError, Store, sha
from agent_os.result_gate import evaluate_completion_release


@pytest.fixture
def release(tmp_path):
    store = Store(tmp_path, "completion-release-demo")
    artifact = b"actual synthetic candidate bytes"
    deps = {
        "source_commit": "a" * 40,
        "contract_hash": "b" * 64,
        "build_hash": sha(artifact),
        "configuration_hash": "d" * 64,
        "environment_fingerprint": "environment-demo",
    }
    checks = {
        key: store.put_json(
            {
                "schema": "agentos.completion-stage-receipt/v1",
                "check_id": key,
                "status": "PASS",
                "checked_at": 100,
                "evidence_refs": [store.put(("actual fixture check " + key).encode())],
                **deps,
            }
        )
        for key in ("G0", "G1", "G2", "G3", "G4", "T22", "T27", "T32")
    }
    snapshot = {
        "schema": "agentos.completion-release/v1",
        "phase": "PREPUBLISH",
        "candidate": {
            **deps,
            "version": "0.8.0rc2",
            "target": "public-demo",
            "artifact_ref": store.put(artifact),
        },
        "checks": checks,
        "authorization_ref": None,
        "publication_ref": None,
    }
    return store, deps, snapshot


def authorize(store, snapshot):
    c = snapshot["candidate"]
    snapshot["authorization_ref"] = store.put_json(
        {
            "schema": "agentos.completion-release-authority/v1",
            **{k: c[k] for k in ("target", "version", "build_hash")},
            "expires_at": 200,
            "revoked": False,
            "evidence_refs": [
                store.put(b"actual fixture scoped publication authorization")
            ],
        }
    )


def test_missing_scope_blocks_and_synthetic_prepublish_never_claims_released(release):
    store, deps, s = release
    assert (
        evaluate_completion_release(s, store, deps, 100, None)["status"]
        == "BLOCKED_AUTHORIZATION"
    )
    authorize(store, s)
    result = evaluate_completion_release(s, store, deps, 100, lambda *_: True)
    assert (
        result["status"] == "READY_TO_PUBLISH"
        and not result["actual_publication_proven"]
    )
    s["phase"] = "POSTPUBLISH"
    with pytest.raises(HandoffError, match="POSTPUBLISH_RECEIPT_REQUIRED"):
        evaluate_completion_release(s, store, deps, 100, lambda *_: True)


def test_postpublish_requires_independent_retrieved_bytes_and_install(release):
    store, deps, s = release
    authorize(store, s)
    s["phase"] = "POSTPUBLISH"
    install = store.put_json(
        {
            "status": "PASS",
            "version": "0.8.0rc2",
            "build_hash": deps["build_hash"],
            "evidence_refs": [store.put(b"fixture installed runtime readback")],
        }
    )
    proof = {
        "schema": "agentos.completion-publication/v1",
        "target": "public-demo",
        "version": "0.8.0rc2",
        "build_hash": deps["build_hash"],
        "checked_at": 100,
        "retrieved_artifact_ref": s["candidate"]["artifact_ref"],
        "install_receipt_ref": install,
    }
    s["publication_ref"] = store.put_json(proof)
    assert (
        evaluate_completion_release(
            s, store, deps, 100, lambda *_: True, lambda *_: True
        )["status"]
        == "PUBLISHED_VERIFIED"
    )
    s["publication_ref"] = store.put_json(
        {**proof, "retrieved_artifact_ref": store.put(b"wrong published bytes")}
    )
    with pytest.raises(HandoffError, match="PUBLISHED_BYTES_MISMATCH"):
        evaluate_completion_release(
            s, store, deps, 100, lambda *_: True, lambda *_: True
        )


def test_changed_source_test_or_build_never_accepts_old_receipt(release):
    store, deps, s = release
    with pytest.raises(HandoffError, match="RELEASE_SOURCE_CHANGED"):
        evaluate_completion_release(
            s, store, {**deps, "source_commit": "f" * 40}, 100, None
        )
    changed = copy.deepcopy(s)
    changed["candidate"]["artifact_ref"] = store.put(b"wrong build")
    with pytest.raises(HandoffError, match="RELEASE_BUILD_MISMATCH"):
        evaluate_completion_release(changed, store, deps, 100, None)
    receipt = store.json(s["checks"]["G2"])
    s["checks"]["G2"] = store.put_json({**receipt, "build_hash": "f" * 64})
    with pytest.raises(HandoffError, match="STALE_STAGE_RECEIPT"):
        evaluate_completion_release(s, store, deps, 100, None)


def test_unknown_target_unverified_authority_and_missing_file_block(release):
    store, deps, s = release
    authorize(store, s)
    with pytest.raises(HandoffError, match="RELEASE_AUTHORIZATION_UNVERIFIED"):
        evaluate_completion_release(s, store, deps, 100, lambda *_: False)
    s["candidate"]["target"] = "different-demo"
    with pytest.raises(HandoffError, match="RELEASE_AUTHORIZATION_SCOPE_MISMATCH"):
        evaluate_completion_release(s, store, deps, 100, lambda *_: True)
    s["candidate"]["artifact_ref"] = {
        **s["candidate"]["artifact_ref"],
        "object_id": "sha256:" + "f" * 64,
        "locator": "aos://completion-release-demo/objects/sha256/" + "f" * 64,
    }
    with pytest.raises(HandoffError):
        evaluate_completion_release(s, store, deps, 100, None)


@pytest.mark.parametrize("field", ["target", "version", "environment_fingerprint"])
@pytest.mark.parametrize("value", [None, "", "   ", "UNKNOWN", "N/A"])
def test_release_refuses_unknown_target_context_before_authority_callback(
    release, field, value
):
    store, deps, s = release
    s["candidate"][field] = value
    calls = []
    with pytest.raises(HandoffError, match="RELEASE_TARGET_OR_CONTEXT_UNKNOWN"):
        evaluate_completion_release(s, store, deps, 100, lambda *_: calls.append(True))
    assert calls == []
