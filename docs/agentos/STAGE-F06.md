# F06 — beta hardening after external review

Status: LOCAL PASS, PUBLICATION READY. Baseline is the published `v0.5.0-beta.1` source plus F05 result on main. This stage fixes three independently confirmed local state boundary defects and publishes a new beta tag; the existing tag remains immutable.

## Defects and bounded fixes

1. Overlay import currently opens the destination with `O_EXCL` and writes bytes in place. A write or interruption can leave a partial target that later imports treat as a conflict. Create the fully fsynced file in the same directory, then atomically link it into an absent destination. A failed link must preserve the existing file; a failed write must leave no destination. A temporary orphan is not user data and can be reported for cleanup.
2. The managed installer checks that core/user paths are separate but activates a release without reading the existing user overlay/config schema. Before install and rollback activation, inspect only the local schema metadata with symlink/size/JSON guards. Unknown or incompatible user schemas block while leaving the current pointer untouched. Absent user data remains valid; v1–v4 community config can be read by the beta core without implicit migration.
3. `project.ready` currently accepts an already READY or CHECKPOINT task and can replace its source baseline after a write. Require the task to be in INTAKE; re-entry through the exact session/turn contract is the only path to a new baseline. A repeated ready must not clear receipts or change the approved scope snapshot.

## Acceptance

- Failure injection proves overlay import never leaves a partial destination and never overwrites a differing user file. Existing idempotent import remains valid.
- Unknown overlay/config schemas and symlinked metadata block both install and rollback before pointer mutation; known legacy config is accepted without writing user bytes.
- A second `ready` after a source write is refused and original out-of-scope assessment remains BLOCKED. Resume through `enter` still works.
- Version surfaces move together to human `0.5.0-beta.2` and distribution `0.5.0b2`; source/site installation links, MCP and CLI agree. Full tests, Ruff, public-tree privacy validator, Darwin install/update/rollback, Linux fresh smoke, public asset hash and tag read-back pass before release.

## Limits

The host gates recorded in F05 remain separate. This stage does not activate the live site, install on the live Mac, or claim Windows/native hook proof. Publish a new beta pre-release and update source guidance; do not rewrite `v0.5.0-beta.1`.

## Local result before publication

- `161` pytest cases and Ruff passed. Failure injection covered an interrupted create-only write, a destination appearing before the atomic link, incompatible/duplicate/symlinked user metadata, and a second `ready` after a source change.
- The public-tree validator and temporary lifecycle demo passed. The beta.2 wheel SHA-256 is `d3034d3f46d9b1582f518970bcfe9e50cab5ea398ff10947cfa316c2221ba615`.
- A disposable Darwin arm64 Python 3.14 fixture passed offline install, update, rollback, reactivation, overlay preservation and packaged-resource checks. A Linux arm64 Python 3.12 container installed the wheel with network disabled and passed version, init, doctor and resources read-back.
- These are synthetic/local checks. Public tag, release asset and site source read-back remain publication steps; the target host gates remain unresolved.
