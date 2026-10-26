"""Fail-closed read-only selection of an existing, explicitly pinned runtime.

This preflight does not install packages, create images, or start containers.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
import subprocess

_IMAGE = re.compile(r"sha256:[a-f0-9]{64}\Z")


def select_existing_environment(repo_root, *, inspect=None, capsule_check=None):
    """Return a closed status. Image existence is not dependency qualification."""
    path = Path(repo_root) / ".agentos/route-probe/container/IMAGE.json"
    if not path.is_file() or path.is_symlink():
        return {"status": "REFUSED", "reason": "pinned_profile_missing"}
    try:
        if path.stat().st_size > 1_000_000:
            raise ValueError("profile_oversize")
        profile = json.loads(path.read_text(encoding="utf-8"))
        image = profile["image_id"]
        if type(image) is not str or not _IMAGE.fullmatch(image):
            raise ValueError("image_pin_invalid")
        if capsule_check is None:
            from .container import _capsule
            capsule_check = _capsule
        capsule_check(profile["capsule_root"], profile["files"],
                      profile.get("public_binary_pins", ()))
        if inspect is None:
            def inspect(image):
                return subprocess.run(
                    ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock",
                     "image", "inspect", image, "--format", "{{.Id}}"],
                    text=True, capture_output=True, timeout=7, check=False)
        observation = inspect(image)
        if observation.returncode or observation.stdout.strip() != image:
            return {"status": "MISSING_IMAGE", "reason": "image_not_exact_local"}
        return {"status": "EXISTING_QUALIFIED", "image_id": image,
                "capsule_file_count": len(profile["files"]),
                "reason": "pinned_image_and_capsule_verified",
                "execution_authorized": False}
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired,
            UnicodeError, json.JSONDecodeError):
        return {"status": "REFUSED", "reason": "profile_or_capsule_invalid"}
