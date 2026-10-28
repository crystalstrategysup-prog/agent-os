"""Closed environment catalog and offline preparation plan for Function Extractor.

Discovery does not import application code, inspect container files or run images.
Building is deliberately separate and requires the canonical mutation authority.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import subprocess

_SHA = re.compile(r"sha256:[a-f0-9]{64}\Z")
_HEX = re.compile(r"(?:[a-f0-9]{40}|[a-f0-9]{64})\Z")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def discover(repo_root, *, inspect=None, capsule_check=None, catalog=None, required_source_ref=None):
    """Choose one exact qualified local image, or report why none is allowed."""
    from .environment import select_existing_environment
    from .container import _capsule
    root = Path(repo_root)
    if required_source_ref is not None and (
            type(required_source_ref) is not str or not _HEX.fullmatch(required_source_ref)):
        return {"status": "REFUSED", "reason": "required_source_ref_invalid"}
    if catalog is None:
        # A trusted catalog is explicit; never enumerate Docker images and guess.
        catalog = root / ".agentos/route-probe/container/ENVIRONMENTS.json"
    if not Path(catalog).is_file() or Path(catalog).is_symlink():
        # Legacy IMAGE.json has no source reference. Never claim compatible
        # source identity for it; preserve single-image behavior separately.
        if required_source_ref is not None:
            return {"status": "REFUSED", "reason": "catalog_source_proof_required"}
        return select_existing_environment(root, inspect=inspect, capsule_check=capsule_check)
    try:
        p = Path(catalog)
        if p.stat().st_size > 1_000_000:
            raise ValueError("catalog_size")
        data = json.loads(p.read_text())
        if set(data) != {"schema", "profiles"} or data["schema"] != "fe.environments/v1":
            raise ValueError("catalog_schema")
        rows = data["profiles"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 12:
            raise ValueError("catalog_bound")
        if inspect is None:
            def inspect(image):
                return subprocess.run(
                    ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock",
                     "image", "inspect", image, "--format", "{{.Id}}"],
                    capture_output=True, text=True, check=False, timeout=7)
        check = capsule_check or _capsule
        qualified = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or (
                    set(row) - {"image_id", "capsule_root", "files", "source_ref", "python_abi", "public_binary_pins"}):
                raise ValueError("catalog_row")
            image = row["image_id"]
            if (not isinstance(image, str) or not _SHA.fullmatch(image)
                    or image in seen or not isinstance(row["source_ref"], str)
                    or not _HEX.fullmatch(row["source_ref"])
                    or row["python_abi"] != "cp311"):
                raise ValueError("catalog_identity")
            seen.add(image)
            if required_source_ref is not None and row["source_ref"] != required_source_ref:
                continue
            check(row["capsule_root"], row["files"], row.get("public_binary_pins", ()))
            found = inspect(image)
            if found.returncode == 0 and found.stdout.strip() == image:
                qualified.append(row)
        if len(qualified) > 1:
            return {"status": "REFUSED", "reason": "ambiguous_qualified_images"}
        if qualified:
            r = qualified[0]
            return {"status": "EXISTING_QUALIFIED", "image_id": r["image_id"],
                    "capsule_file_count": len(r["files"]), "source_ref": r["source_ref"],
                    "selection_digest": _digest(r), "execution_authorized": False}
        return {"status": "MISSING_IMAGE", "reason": "no_exact_qualified_image"}
    except (ValueError, TypeError, KeyError, OSError, UnicodeError,
            json.JSONDecodeError, subprocess.TimeoutExpired):
        return {"status": "REFUSED", "reason": "catalog_or_capsule_invalid"}


def prepare_offline_build(*, base_image, wheels, image_name, source_ref):
    """Return a sealed build proposal, never run Docker or install a package."""
    if (not isinstance(base_image, str) or not _SHA.fullmatch(base_image)
            or not isinstance(source_ref, str) or not _HEX.fullmatch(source_ref)
            or not isinstance(image_name, str) or not re.fullmatch(r"fe-test-[a-z0-9-]{1,32}", image_name)
            or not isinstance(wheels, list) or len(wheels) > 128):
        return {"status": "REFUSED", "reason": "invalid_build_inputs"}
    pins = []
    for row in wheels:
        if (not isinstance(row, dict) or set(row) != {"name", "sha256"}
                or not isinstance(row["name"], str)
                or not re.fullmatch(r"[a-zA-Z0-9_.+-]+\.whl", row["name"])
                or not isinstance(row["sha256"], str) or not _HEX.fullmatch(row["sha256"])):
            return {"status": "REFUSED", "reason": "wheel_pin_invalid"}
        pins.append(dict(row))
    if len({x["name"] for x in pins}) != len(pins):
        return {"status": "REFUSED", "reason": "wheel_duplicate"}
    plan = {"base_image": base_image, "wheels": sorted(pins, key=lambda x: x["name"]),
            "image_name": image_name, "source_ref": source_ref,
            "network": "none", "pull": "never", "credentials": False}
    return {"status": "BUILD_PLAN_READY", "plan": plan, "plan_digest": _digest(plan),
            "build_performed": False, "requires": "canonical_container_mutation_lease"}


def select_bound_profile(repo_root, *, selected_image=None):
    """Return exact verified profile for dispatch, never a raw arbitrary Docker image.

    Catalog rows must match the approved source pin of the default profile.
    Only catalog profiles with the same public capsule identity as the approved
    default are eligible for automatic substitution at this stage. This avoids
    passing an unrelated application's installed dependencies as qualification.
    """
    from .container import _capsule
    root = Path(repo_root)
    path = root / ".agentos/route-probe/container/IMAGE.json"
    if not path.is_file() or path.is_symlink():
        raise ValueError("qualified_test_image_missing")
    default = json.loads(path.read_text())
    _capsule(default["capsule_root"], default["files"], default.get("public_binary_pins", ()))
    catalog = root / ".agentos/route-probe/container/ENVIRONMENTS.json"
    if not catalog.exists() and not catalog.is_symlink():
        return default
    result = discover(root)
    if result["status"] != "EXISTING_QUALIFIED":
        raise ValueError("qualified_environment_" + result["status"].lower())
    # A catalog may select only its exactly pinned profile, not just image ID.
    document = json.loads(catalog.read_text())
    matches = [p for p in document["profiles"] if p["image_id"] == result["image_id"]]
    if len(matches) != 1:
        raise ValueError("catalog_identity_missing")
    row = matches[0]
    # The known public dependency capsule remains exact and separately hashed;
    # only the runtime base image changes. Never borrow production container
    # files or accept a different unpinned dependency tree.
    if (row["capsule_root"] != default["capsule_root"] or
            row["files"] != default["files"]):
        raise ValueError("candidate_capsule_not_bound")
    if row["source_ref"] != default["engine_source_ref"]:
        raise ValueError("candidate_source_ref_not_bound")
    _capsule(row["capsule_root"], row["files"], default.get("public_binary_pins", ()))
    if selected_image is not None and row["image_id"] != selected_image:
        raise ValueError("container_image_or_budget")
    return {**default, "image_id": row["image_id"]}

def build_missing_environment(*, plan, local_wheelhouse, lease_assert=None, docker=None):
    """Offline Docker build; requires explicit exact canonical mutation authority.

    Never read arbitrary containers, fetch dependencies, or create an image if
    authority or local SHA-pinned wheels are missing.
    """
    from .container import _lease
    import tempfile
    source = plan.get("plan") if isinstance(plan, dict) else None
    if not isinstance(source, dict) or plan.get("status") != "BUILD_PLAN_READY":
        return {"status": "REFUSED", "reason": "build_plan_invalid"}
    if _digest(source) != plan.get("plan_digest") or source.get("network") != "none" or source.get("pull") != "never":
        return {"status": "REFUSED", "reason": "build_plan_integrity"}
    if local_wheelhouse is None or not isinstance(local_wheelhouse, (str, Path)):
        return {"status": "REFUSED", "reason": "wheelhouse_missing"}
    root = Path(local_wheelhouse)
    if not root.is_dir() or root.is_symlink():
        return {"status": "REFUSED", "reason": "wheelhouse_missing"}
    wheels = source["wheels"]
    try:
        for row in wheels:
            f = root / row["name"]
            if f.is_symlink() or not f.is_file() or f.stat().st_size > 16_000_000:
                return {"status": "REFUSED", "reason": "wheel_invalid"}
            if hashlib.sha256(f.read_bytes()).hexdigest() != row["sha256"]:
                return {"status": "REFUSED", "reason": "wheel_hash_mismatch"}
        # Assert the *existing* canonical authority before any Docker mutation.
        check = lease_assert or _lease
        check("function-extractor:synthetic:" + source["base_image"])
        # The builder itself remains gated to prevent accidental implicit
        # authority from a caller supplying only a preparation plan.
        if docker is None:
            docker = _build_docker_offline
        with tempfile.TemporaryDirectory(prefix="fe-offline-image-") as d:
            path = Path(d)
            lines = ["FROM " + source["base_image"]]
            if wheels:
                lines += ["COPY --chown=65534:65534 wheels/ /wheels/",
                          "RUN python -m pip install --no-index --no-deps /wheels/*.whl"]
            lines += ["USER 65534:65534"]
            (path / "Dockerfile").write_text("\n".join(lines) + "\n")
            (path / "wheels").mkdir()
            for row in wheels:
                (path / "wheels" / row["name"]).write_bytes((root / row["name"]).read_bytes())
            result = docker(path, source["image_name"])
        return result
    except (OSError, ValueError, TypeError, KeyError):
        return {"status": "REFUSED", "reason": "build_precondition_failed"}


def _build_docker_offline(context, name):
    """Actual Docker builder: local immutable base only, no external network."""
    # BuildKit does not accept raw image IDs in FROM as local bases; it
    # interprets sha256:... as a repository name and attempts a remote pull.
    # Resolve an existing LOCAL tag, then independently prove it points to
    # the exact requested immutable image before using that tag in Dockerfile.
    source = Path(context) / "Dockerfile"
    lines = source.read_text().splitlines()
    if not lines or not lines[0].startswith("FROM "):
        return {"status": "BUILD_FAILED", "reason": "base_dockerfile_missing"}
    image_id = lines[0][5:]
    if not _SHA.fullmatch(image_id):
        return {"status": "BUILD_FAILED", "reason": "base_image_identity_invalid"}
    info = subprocess.run(
        ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock",
         "image", "inspect", image_id, "--format", "{{json .RepoTags}}"],
        capture_output=True, text=True, check=False, timeout=8)
    if info.returncode:
        return {"status": "BUILD_FAILED", "reason": "base_image_not_local"}
    try:
        tags = json.loads(info.stdout)
    except (ValueError, TypeError):
        tags = []
    valid = []
    for tag in tags if isinstance(tags, list) else []:
        if not isinstance(tag, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:/-]{1,120}", tag):
            continue
        tag_check = subprocess.run(
            ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock",
             "image", "inspect", tag, "--format", "{{.Id}}"],
            capture_output=True, text=True, check=False, timeout=7)
        if tag_check.returncode == 0 and tag_check.stdout.strip() == image_id:
            valid.append(tag)
    if not valid:
        return {"status": "BUILD_FAILED", "reason": "no_verified_local_base_tag"}
    source.write_text("FROM " + sorted(valid)[0] + "\n" + "\n".join(lines[1:]) + "\n")
    p = subprocess.run(
        ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock", "build",
         "--pull=false", "--network=none", "--tag", name, str(context)],
        capture_output=True, text=True, check=False, timeout=90)
    if p.returncode:
        # Only bounded diagnostics from a sealed synthetic build context.
        return {"status": "BUILD_FAILED", "reason": "docker_build_exit_nonzero",
                "exit_code": p.returncode, "stderr_tail": p.stderr[-1200:],
                "stdout_tail": p.stdout[-500:]}
    check = subprocess.run(
        ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock",
         "image", "inspect", name, "--format", "{{.Id}}"],
        capture_output=True, text=True, check=False, timeout=10)
    image = check.stdout.strip()
    if check.returncode or not _SHA.fullmatch(image):
        return {"status": "BUILD_FAILED", "reason": "output_image_not_qualified"}
    return {"status": "IMAGE_BUILT_UNQUALIFIED", "image_id": image,
            "requires": "dependency_capsule_and_sandbox_acceptance"}


def ensure_environment(repo_root, *, plan, local_wheelhouse,
                       discover_fn=None, build_fn=None):
    """End-to-end fail-closed find-or-build orchestration.

    Built images are NOT admitted for Function Extractor replay until a
    separate pinned capsule and runtime acceptance is completed.
    """
    search = discover_fn or discover
    result = search(repo_root)
    if result.get("status") == "EXISTING_QUALIFIED":
        return result
    if result.get("status") != "MISSING_IMAGE":
        return {"status": "REFUSED", "reason": "candidate_discovery_" +
                str(result.get("status", "invalid")).lower()}
    if not isinstance(plan, dict) or plan.get("status") != "BUILD_PLAN_READY":
        return {"status": "REFUSED", "reason": "approved_build_plan_missing"}
    builder = build_fn or build_missing_environment
    built = builder(plan=plan, local_wheelhouse=local_wheelhouse)
    if built.get("status") != "IMAGE_BUILT_UNQUALIFIED":
        return built
    return {"status": "CREATED_PENDING_QUALIFICATION",
            "image_id": built["image_id"],
            "reason": "new_image_requires_dependency_capsule_and_runtime_verification"}
