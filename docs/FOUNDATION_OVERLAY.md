# Foundation ↔ user overlay contract

Contract version: `agentos.foundation-overlay/v1` with optional `agentos.profile/v1` adapter.

## Physical boundary

The foundation is the installed Python package plus immutable release assets. Runtime commands never put user content into that package or its source checkout. The default overlay is one user-owned folder, `~/.agentos-user`, overridable by one explicit absolute user-home setting. An optional managed core install uses a separate `~/.local/share/agentos-foundation` root. The two roots may not be equal, nested or symlinked into each other. Existing `~/.agent-os` is legacy input and is not silently deleted, moved or replaced.

The overlay has a versioned `overlay.json` catalog and named areas: `config.json`, `state/`, `secrets/`, `knowledge/`, `preferences/`, `projects/`, `extensions/` and `backups/`. The optional `profiles/<id>/profile.json` files and `state/profile-selection.json` also live here. The catalog records overlay schema/version and compatibility metadata, not credential values. Knowledge indexing uses bounded references and never auto-loads history or raw project contents. A user can inspect and back up this one folder independently of the core.

## Optional profiles: 0 / 1 / N

The user home is a storage root, not a mandatory active profile. With no selection the adapter returns `NONE`; a user can select `none`, one exact ID, or every inventoried ID in an explicit order. Profile files use `agentos.profile/v1` and contain bounded facts, preferences or owner-authored instructions with source, timestamp and verification status. The adapter does not discover other homes or silently select a profile.

`agentos profiles inventory` lists exact IDs, versions, hashes, host bindings and overlapping keys. Before selecting `all`, the owner must choose the winning profile for every differing key; ordering alone does not resolve a conflict. Selection stores exact hashes and inventory digest outside the package. A changed or deleted selected profile, or a changed set under `all`, yields `STALE_SELECTION` with no entries until the owner inventories and selects again. `none` remains available when profile storage is broken. `agentos profiles interview` prefills current device observations and selected profile fields, then asks about missing owner/host fields. It never infers the owner's identity from a home path.

## Ownership and authority

The foundation owns schemas, default templates, validators, CLI/MCP contracts and opt-in adapters. The user owns all overlay bytes. An overlay entry cannot grant new shell, network, host or deployment authority merely by being present. Private executable providers are separate code with explicit interfaces and approval; they are not treated as user knowledge. No secrets, auth files, host passport, production route or private business rule enters the public package or its release artifacts.

The foundation also owns the general instruction to keep inherited `AGENTS.md`
files concise and route agents to relevant project documents and skills. It does
not own the detailed content of each project's guide. Host/owner facts stay in
the external overlay; dated project state stays in the project's own docs and
must be checked against current source/runtime before action. A long-file
warning is advisory, never a permission grant or lifecycle gate.

## Migration and update behavior

Import is a plan by default. Apply creates missing files only after path, schema, manifest and SHA-256 checks; identical existing bytes are preserved and conflicting bytes block. No overwrite/delete fallback. Legacy community config v1–v4 may be upgraded explicitly to v5: preserve unknown keys, create a byte-exact backup first, write atomically and read back. A partial private config needs a separately reviewed field mapping. Core installation/rollback reads compatibility metadata but does not mutate the overlay. A newer core with an unsupported overlay schema blocks rather than guessing a downgrade.

## Portability and proof

The package CLI targets Python 3.11+ on macOS, Linux and Windows where its components use portable APIs. The managed immutable-release installer is POSIX-only until an actual Windows installer is designed and tested. GNU Screen remains unavailable on Windows. Platform claims require a clean installation, `doctor`, version/MCP read-back and overlay preserve probe on that platform; source inspection alone yields NOT_TESTED.

## Failure and recovery

An interrupted import may leave create-only files and a rerun must classify them as identical; it never overwrites. A failed migration retains its backup and reports the current config hash. An incomplete core release never becomes current. Rollback points to the prior verified core and leaves the overlay untouched. Existing private runtime is never selected as a rollback target for this public installer.

## Workflow scope (beta.5 candidate)

Ordinary questions/search/read-only audits/API discovery require neither profiles nor intake.
Use selected verified facts only when relevant; stale host facts must not be used. A missing
profile does not block unrelated reading. Owner instructions which universally require
questions/observe must be migrated separately, preserving their narrower host authority rules.
Partial sanitized exports are review evidence, not complete replacement profiles. After a
real profile edit, inventory and explicit re-selection refresh the exact hashes; schema-only
selection evidence does not prove ACTIVE. Never use mode none to evade a required host identity.
Core rollback must not restore native hooks or call a legacy integration generator.
