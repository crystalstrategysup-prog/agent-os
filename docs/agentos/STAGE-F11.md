# F11 — stable 0.5.0 hardening and release

Task: `task-8ce6b2b81c57493c`.

Status: CURATOR_CHANGES_REQUESTED; corrected candidate checks and acceptance pending.
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
The first `d339d6e` candidate passed 245 tests locally, but the curator found
ST-01–ST-06 and refused its release. Its source ZIP and wheel are HOLD. The
corrected candidate must be built and checked again; previous pass counts do
not apply to these changed bytes.

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

## Independent review of d339d6e and correction scope

The curator returned CHANGES_REQUESTED. The following corrections are scoped to
this new candidate, with new regressions and artifact checks required before
resubmission:

|Finding|Corrected contract|Verification required|
|---|---|---|
|ST-01 unverified `.pyc` executed|Remove only package cache files after owned payload and entrypoint verification, before any apply probe; plan remains read-only|Timestamp-valid injected bytecode, install/reactivate/rollback|
|ST-02 owner AGENTS edit lost|One selected snapshot for planned bytes, preimage, backup and journal; recheck owner/override before write|Edit between snapshot and locked write must cause replan|
|ST-03 pending enter false READY|Dependent lifecycle calls refuse pending entry journal; questions still work|READY/check/close/checkpoint and read-only contrast|
|ST-04 runner setup leak|Process-group cleanup starts immediately after Popen, including selector/pipe setup failures|Injected setup failures and no delayed child write|
|ST-05 manifest hash downgrade|New manifest v2 requires complete script hashes; legacy public beta.5 v1 requires canonical scripts|Modified entrypoint with missing hash refused; beta.5 rollback preserved|
|ST-06 valid path refused|Validate exact direct shebang, quoted pip shell trampoline for spaces, and unquoted shell-safe trampoline for a long path|Short path with spaces and separate long path without spaces; arbitrary shell remains rejected|

Curator also observed a Linux x86_64 Python 3.13 module `pytest` discrepancy:
the immediate-exit descendant test returned timeout code 124 rather than
descendant code 125 with a one-second startup deadline. The runner classifies
an exited parent with a live process group at deadline as descendant failure
and retains that classification after successfully stopping the group.
The regression now gives that immediate-exit scenario five seconds for slower
interpreter startup while retaining the separate one-second timeout scenario;
both still check that the delayed child cannot write. Both full invocation modes
and raw Mac/Linux platform receipts must be attached to the next exact candidate.

## F12 boundary review of 029d838

The curator verified the immutable source/wheel identity, all 96 source-to-wheel
package files, and 101 RECORD hashes, then returned CHANGES_REQUESTED for five
reproduced boundary failures. That candidate remains HOLD. The next candidate
must include these fixes and exact-platform receipts:

|Finding|Contract and regression|
|---|---|
|F12-01 package ancestor symlink|Refuse a symlink at every `.venv/lib/pythonX/site-packages` ancestor before payload reads, cache cleanup or probe; an owner-root cache sentinel and `current` must remain unchanged.|
|F12-02 pending enter race|Repeat the pending-journal check inside the project write lock for ready, document registration, next turn, close and checkpoint. Interleave a real interrupted resume-enter before ready obtains that lock.|
|F12-03 long path launcher|Accept only exact direct, quoted and shell-safe unquoted pip launcher prefixes; exercise a long path without spaces separately from a path with spaces.|
|F12-04 v1 rollback template|Accept the two exact known pip launcher bodies for legacy beta.1–beta.5 while retaining mandatory v2 hashes; prove both via a fixture and a real beta.5 wheel cycle.|
|F12-05 descendant status|Keep a proven descendant failure as 125 when bounded cleanup crosses the execution deadline; deterministic delayed-cleanup and full Linux x86_64 Python 3.13 pytest are required.|

No public release or Mac activation may use 029d838. The private Telegram
runtime still depends on a snapshot of the old RC kernel and remains a separate
migration before RC retirement. Native hooks remain disabled.
