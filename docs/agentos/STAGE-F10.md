# F10 — concise AGENTS routing rule

Status: LOCAL_SOURCE_CANDIDATE. Version target: `0.5.0-beta.6` / `0.5.0b6`.
Base: reviewed local beta.5 source commit `44b928786d0c3d1d48e1af96492869ba2a80304c`.

## Goal and decision

An inherited root `AGENTS.md` must give a short map of scope, universal limits and
links to applicable project guides. Detailed architecture, operations and dated
incident history live in project documentation or skills and are read only when
the task matches. User and host facts remain in the external overlay. A file
size warning is diagnostic only: it must not create a hook, Stop gate, mandatory
read-only intake or false claim that the whole document was loaded.

## Write set

Public docs and packaged mirrors, managed AGENTS block generator, two project
skills, version metadata/contracts, narrow regression tests and changelog.
No owner overlay, private workspace guide, current Mac release switch, remote
push/tag/release, production or external service effect.

## Acceptance

1. A new managed block tells the agent to keep project AGENTS concise and route
   to relevant docs/skills; it retains direct read-only and no-hook rules.
2. Documentation explains layer ownership and on-demand loading without turning
   an indicative size target into enforcement.
3. Local tests and clean export pass; package resources equal maintained source;
   human/CLI/MCP/distribution versions agree at beta.6.

## Rollback

The beta.5 release remains immutable and installed on the owner Mac. This stage
is source-only. Discard this branch to undo the candidate; do not run old hook
integration or restore paused hook files. A later authorized install uses the
managed installer and exact current pointer with a separate rollback rehearsal.
