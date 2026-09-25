# F11 — stable 0.5.0 hardening and release

Status: IMPLEMENTED_LOCAL_CHECKS_PASS; artifact and target acceptance pending.
Owner request on 2026-09-25 expands F10 to a stable public
foundation and a separately verified Mac configuration. F10 source rule is
closed at `838b061`; its beta.6 artifacts are historical inputs, not release
assets. Curator investigation in the selected owner ChatGPT session reproduced
S1–S8 and identified a partial `project enter` failure path.

## Scope and architecture

Public work is limited to the existing `agent_os` foundation, package contracts,
tests, maintained docs, installer and integration. Keep direct read-only work,
documentation-first project changes, separate user overlay, target-specific
authority and disabled native hooks. Fix the following boundaries:

1. Codex integration chooses explicit `--codex-home`, then `CODEX_HOME`, then
   default. It must not turn an empty override into a shadow over owner AGENTS.
2. Preserve owner AGENTS bytes outside the managed block; validate ordered
   markers. Integration of AGENTS and skills must recover from partial writes
   without overwriting concurrent owner changes.
3. `project enter` must not leave a falsely active task if scaffold or turn
   binding fails. `project check` must finish/terminate its own process group,
   bound captured output, and never issue PASS while its children can still
   write to the project.
4. File inventory rejects FIFO, socket and device types before opening them.
5. Installer validates the actual owned installed payload against the trusted
   wheel before activating an existing release; damaged releases remain
   recoverable through a new immutable directory.
6. Tests must pass under module and console `pytest` invocation, including the
   verifier import contract.

The private `2.0.11-rc.*` runtime, owner overlay, Mac MCP launcher and live
services are separate target surfaces. Their migration is performed only after
the public candidate passes exact source/wheel review and target read-back.

## Acceptance and evidence

- Reproduce each S1–S8 and partial-enter case on an isolated prior source;
  add regression tests that pass only when the intended property holds.
- Run approved suite, demo and Ruff checks on this task source. Then verify a
  clean Git export, resource parity, wheel RECORD, offline install/update/
  rollback/reactivation, corruption refusal and owner-data preservation.
- Independently review exact final source/wheel bytes with the curator before
  stable release. Recheck remote/tag, push intentionally without Actions, tag
  `v0.5.0` only if free, publish the tested assets and re-download/hash them.
- On Mac, separately prove selected owner/macbook-pro context, active
  interpreter/MCP/AGENTS in a fresh session, no hooks and preserved overlay.
  Inventory private RC consumers and capabilities before archive and removal.

## Rollback and limits

Keep beta.5 and the last verified public release as immutable anchors. Do not
restore old hook integration. Keep exact backups of modified host instructions
and config. A failed source, wheel or target check blocks the associated
publication/activation/retirement; report the checkpoint without a false PASS.
Public source tests do not prove the private Telegram feature is replaced.

## Finding closure matrix (local source, before release)

Curator's S1–S8 reproductions are recorded in the selected owner conversation.
The following local regressions assert each intended invariant; all 245 tests
pass on macOS with both `python -m pytest` and console `pytest` as of 2026-09-25.
This records source behavior, not installed runtime behavior.

|Finding|Fix|Regression and current result|
|---|---|---|
|S1 CODEX_HOME ignored|Explicit > environment > default selection|`test_F_integration_uses_selected_codex_home`: PASS|
|S2 empty override shadows owner|Choose override only with nonempty instructions|same integration test: PASS|
|S3 partial integration|Lock, journal, backups, exact-hash recovery|`test_F_integration_fault_after_each_phase_rolls_back`, interrupted journal/conflict tests: PASS|
|S4 AGENTS bytes/markers|Byte-preserving block replacement and ordered markers|`test_F_integration_preserves_crlf_owner_bytes_and_rejects_reversed_markers`: PASS|
|S5 check descendants/output|Bounded output and POSIX process group completion|`test_F_check_runner_stops_late_descendant_writes`, output/launch test: PASS|
|S6 FIFO inventory|lstat regular-file gate before read|FIFO and Unix socket inventory tests: PASS|
|S7 installed payload|Compare package, metadata and entrypoint bytes to trusted wheel before activation|`tools/test_installation.py` integrity cases: PASS in disposable Mac fixture, final wheel pending|
|S8 console pytest|Import verifier by exact file path|console `pytest`: 245 PASS|
|Partial enter|Project/turn transaction and recovery before retry|scaffold, bind, interrupted recovery and conflict tests: PASS|

Curator required the remaining exact source/wheel review, Linux and macOS
artifact fixtures, release readback and separate private migration before a
complete acceptance claim.
