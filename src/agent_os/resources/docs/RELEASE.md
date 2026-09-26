# Release policy

The current source declares `0.5.1`; `v0.5.0` is the previous stable release.
Publication and installation need separate readback; historical beta.4 is not
current source authority. The user overlay version is independent of core
version and compatibility is checked separately. Optional `agentos.profile/v1`
files remain in the user home; updating
a core neither creates nor selects profiles. A changed public protocol needs a
new versioned release. Release tag and package version must agree. Do not label
a beta as v0.4.0 or replace an installed stable release implicitly. The old
`v0.5.0` tag and assets remain immutable. Confirm that `v0.5.1` is free and all
version surfaces agree before tagging; then read back the canonical repository,
annotated tag, release object and downloaded wheel.

The release gate includes final diff review, current unit and integration
checks, complete docs, reproducible source inventory, wheel hash, clean install
in a fresh venv, privacy review, and an exact publication allowlist. Publish
only public core and intended artifacts; never a mixed private handoff or
`.agentos/` runtime receipts. Authorized tag/signature and release actions
require the exact account and host. A prepared archive is not a published
release. Before push, verify remote, HEAD, and worktree state; reconcile
concurrent work without force, reset, or stashing another person's changes.
GitHub Actions is not a delivery gate: use local checks and recorded evidence.

Release notes state behavior changes, breaking interfaces, config migration,
tested platforms, known limits, source and wheel hashes, install and rollback
route, and next stage. Exclude private host names and paths, personal knowledge,
PII logs, and sensitive historical references.

Use verified source and wheel installation guidance. Do not claim PyPI
availability without a publication receipt. Source archives may contain
bootstrap and self-verification docs. Later project changes still require
explicit entry; questions, searches, and read-only audits do not. Native hooks
are excluded on release and rollback. Schemas and skills are bundled resources,
inherited only after explicit integration; user overrides stay outside core.
