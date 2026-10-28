"""Versioned source inventory classification, never a secret-scanner exemption.

Only direct, generator-owned cache directories in a recognized package are
omitted. Unknown provenance remains source. Canonical conflicts fail closed.
"""

from pathlib import Path

from .safeio import MAX_JSON, GateError, _parse_json, sha, within

POLICY_VERSION = "agentos.source-selection/v2"
GENERATORS = {
    ".astro": {"astro", "@eventcatalog/core"},
    ".vite": {"vite", "astro", "@eventcatalog/core", "@sveltejs/kit"},
    ".next": {"next"},
    ".nuxt": {"nuxt"},
    ".svelte-kit": {"@sveltejs/kit"},
    ".parcel-cache": {"parcel", "@parcel/core"},
    ".turbo": {"turbo"},
}


class SourceSelection:
    def __init__(self, root: Path, canonical_paths=()):
        self.root = root
        self.canonical_paths = tuple(canonical_paths)
        self.excluded = []

    def exclude_directory(self, path: Path) -> bool:
        generators = GENERATORS.get(path.name)
        if generators is None:
            return False
        manifest = path.parent / "package.json"
        if not manifest.exists() and not manifest.is_symlink():
            return False
        # Bounded regular JSON, no duplicate keys, escapes or linked manifests.
        manifest_rel = manifest.relative_to(self.root).as_posix()
        manifest = within(self.root, manifest_rel, allow_missing=False)
        with manifest.open("rb") as stream:
            manifest_bytes = stream.read(MAX_JSON + 1)
        if len(manifest_bytes) > MAX_JSON:
            raise GateError("json_size_limit")
        package = _parse_json(manifest_bytes)
        if not isinstance(package, dict):
            raise GateError("source_package_object_required")
        dependencies = {}
        for field in ("dependencies", "devDependencies"):
            values = package.get(field, {})
            if not isinstance(values, dict):
                raise GateError("source_package_dependencies_invalid")
            dependencies.update(values)
        matched = sorted(g for g in generators if isinstance(dependencies.get(g), str)
                         and dependencies[g].strip())
        if not matched:
            return False
        rel = path.relative_to(self.root).as_posix()
        if path.is_symlink():
            raise GateError("generated_cache_symlink_refused")
        if any(p == rel or p.startswith(rel + "/") for p in self.canonical_paths):
            raise GateError("generated_cache_canonical_conflict:" + rel)
        # A tracked source under a customary cache name is not disposable.
        # Reuse bounded Git plumbing with hooks/filters/optional writes disabled.
        git_path = path.absolute()
        for parent in (git_path.parent, *git_path.parent.parents):
            # A selected project can be below its owning repository. Inspect
            # ancestor metadata only, never source bodies outside the project.
            # lstat distinguishes absent metadata from an unreadable identity.
            try:
                (parent / ".git").lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise GateError("generated_cache_tracking_unknown") from exc
            else:
                from .source_links import _entries

                if _entries(parent, git_path.relative_to(parent).as_posix()):
                    raise GateError("generated_cache_tracked_conflict:" + rel)
                break
        self.excluded.append({
            "path": rel,
            "rule": path.name[1:] + ":package-cache/v1",
            "package_manifest": manifest_rel,
            "package_sha256": sha(manifest_bytes),
            "generators": matched,
            "recovery": "Regenerate with the package's pinned dependencies and documented build/dev command; never execute on restore.",
        })
        return True

    def record(self):
        return {"version": POLICY_VERSION,
                "generated_caches": sorted(self.excluded, key=lambda x: x["path"])}


def require_source_write_paths(snapshot, paths):
    for cache in snapshot.get("source_selection", {}).get("generated_caches", []):
        rel = cache["path"]
        if any(p == rel or p.startswith(rel + "/") for p in paths):
            raise GateError("generated_cache_write_conflict:" + rel)
