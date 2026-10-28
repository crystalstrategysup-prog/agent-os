# Explicit protected-source references for unfinished checkpoints

`project checkpoint --protected-sources REQUEST.json` (or `-` for JSON stdin)
adds an explicit metadata-only capture contract. It does not retry publication
of refused bytes, modify the original config or scanner, grant read/write
permissions, or accept the product result. Ordinary checkpoint and completion
keep their existing scanner behavior. Completion never accepts this argument.

Request schema `agentos.protected-checkpoint-sources/v1` has exactly:
`schema`, `root` (canonical admitted root), `task_id`, `revision`, `task_sha256`,
`project_sha256`, `source_sha256`, `authority_ref`, `sources`.
The SHA fields bind exact current task/project file bytes and source snapshot.
`authority_ref` is a bounded caller attestation, never proof of authority.
`sources` has 1..32 unique records with exactly `path`, `sha256`, `bytes`.
Only ordinary `.env` or `.env.*` files already in approved capture are allowed,
up to1MiB each. Selected required documents and directory-link metadata cannot
be withheld. Relative paths must be canonical and contained, with no traversal.
Each config must match its source snapshot and exact byte count. The unchanged
scanner MUST reject those original bytes as SECRET_DETECTED before metadata-only
capture is allowed; benign files or another scanner failure refuse.

The original remains local and unchanged. All source files are still hashed;
no source inventory exclusion is added. The handoff embeds a regular JSON
`agentos.protected-source-reference/v1` at `protected-source-refs/`, containing
original path/hash/bytes and explicit content_embedded=false, external_required,
SECRET_DETECTED and not_implemented restore markers. It never embeds the original
bytes. The manifest records required UNKNOWN protected-source dependencies,
not_restored paths and limitations. Indexed CHECKPOINT remains unfinished and
external_required, never self-contained or completed. Fingerprint includes the
request so prior refusals/journals are not overwritten or relabeled. Rechecks
still compare the complete source snapshot and maintained documents before
publication. Keep previous failed-attempt evidence; do not replay UNKNOWN sends
or publish original config blobs through another route.

Generate the request outside the source tree or supply stdin; writing a request
inside source after calculating source_sha256 correctly makes that pin stale.
The existing owning executor verifies current authority, invokes checkpoint,
then performs ordinary next-turn, full enter, docs and READY for the same task.
Protected local config recovery is manual under its own current authorization.
No source-root transition, task-binding rewrite or security setting change is
part of this contract. Native hooks remain disabled.

Protected dependency IDs bind canonical relative path AND content SHA. Distinct
paths with identical bytes retain distinct required UNKNOWN dependencies and
metadata references. Genuine duplicate dependency IDs remain rejected.
