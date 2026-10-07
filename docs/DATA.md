# Data and documentation

Current source candidate: `0.8.0rc2` (not publication or host adoption). RC-labelled sections below are retained historical records, not current installation or publication claims.


## Historical: Indexed handoff successor0.7.0rc1

User-owned scope-private results libraries are separate from core and sessions. Capture approved result surfaces/current docs, record exact hashes/provenance and explicit baseline dependencies; do not import unrelated data. See [indexed handoff](INDEXED_HANDOFF.md).

## Project records

`.agentos/project.json` stores identity, name, types, features, source-backed
context, document registry, active task, and revision. `.agentos/tasks/<id>/task.json`
stores answers, selected docs, status, revision, session and turn, READY
baseline, check receipts, and closeout or checkpoint. Current documents remain
in the project under registered paths, not inside the runtime package. Each
registry entry records path, owner, source, summary, SHA-256, review time,
revision, and task ID.

A check receipt and bounded log record task ID/revision, policy and source
before and after execution, argv, return code, timestamps, executor module
hash, log hash, and foundation version. The latest receipt for a check ID wins;
an old PASS cannot override a newer FAIL.

Task states progress through INTAKE, READY, VERIFYING, and CLOSED. CHECKPOINT
records incomplete work. Resume increases revision and clears READY and prior
check evidence. Old receipts remain history. Source snapshots exclude
`.agentos`, `docs/agentos`, build caches, venv, and node modules; these have
separate checks. Other registered documents remain part of the source snapshot.
Snapshots are bounded by 20,000 files and 128 MiB; an oversized project needs
an explicit scope decision, not silent truncation.

The unpublished tracked-directory-alias source delta records an admitted Git
symlink as exact metadata without following it. An optional `symlinks` map and
its bound digest distinguish the alias from ordinary file hashes. Generic
storage/import guards remain strict; see [source link contract](SOURCE_SYMLINKS.md).

## User overlay

`config.json` uses community-config/v5; `overlay.json` uses
agentos.user-overlay/v1. `knowledge/INDEX.json` indexes references with
provenance. `preferences/` holds personal decisions, `projects/` holds links,
`extensions/` holds metadata outside core, `state/` holds explicit turn,
dispatch, and import receipts, and `state/observations/` holds optional separate
read audit records. `backups/` preserves earlier configs and integrations;
`secrets/` is local storage and never a public export. The user root is mode
0700 and created config/state files are 0600. Public source docs may be 0644.
Host ACLs and disk encryption remain host responsibilities.

Home resolution is explicit `--home`, then `AGENTOS_USER_HOME`, then legacy
`AGENT_OS_HOME`, then `~/.agentos-user`. Conflicting environment homes block
without an explicit override. Core and user roots may not match or nest. User
root symlinks are refused and resolved containment applies when core home is
overridden.

## Migration and retention

Import checks manifest, schema, SHA-256, and allowed paths. Missing files are
created, matching files preserved, and differing files rejected. Preflight is
complete before writing; an I/O failure may leave partial create-only results,
so a rerun must classify them idempotently. It is not a whole-filesystem
transaction. Config migration backs up and reads back, preserving unknown keys.
Unsupported future schemas block; implicit downgrade is not allowed. Never
import secrets or live state from an archive.

There is no automatic deletion of evidence, backups, or history. Retention must
follow the user's content and project requirements; this document invents no
legal period. Deletion needs separate scope and authority, verified export
metadata, and a recovery sample. Logs may be sensitive; redaction is heuristic.

## Explicit turn behavior

`turn/v1` is an explicit project anchor, not a receipt for every prompt. Unbound
old intake or observation receipts do not block a new explicit entry; a bound
task requires the proper transition. Optional observations keyed by session,
turn, and root do not overwrite project task state. Same-scope answer reuse
does not inherit authority. `verify-closeout` reads CLOSED history without
rewriting it when evidence becomes stale. A changed foundation version or
executor hash invalidates old check evidence for new acceptance, while retaining
the historical record.
