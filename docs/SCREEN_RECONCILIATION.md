# Evidence-bound pending reconciliation

This source API fills a specific cold-adoption gap: a managed Screen dispatch
returned UNKNOWN and retained `pending.json`, while a qualified native read now
proves the exact turn completed and its actual commands/effects have been
reviewed. Completion alone never means no effects, business acceptance or safe
replay. This route neither clears the mailbox nor unblocks its old worker.

`screen_reconciliation.reconcile_pending(home, plan,
reconciliation_guard=held_owner_guard)` publishes one immutable receipt for a
selected session/operation. It makes no RPC, dispatch, stop, restart or setting
change. It retains original FAILED state, UNKNOWN response, pending request,
launch/continuation journals and all effects. No raw provider error text or
transcript is needed in this public contract.

The trusted caller supplies a bounded `agentos.screen-reconciliation-request/v1`
object with `old_name`, `session_id`, `operation_id`, exact native `turn_id`,
`old_pins`, and `evidence`. SHA-256 pins identify raw retained JSON bytes:

- `old_pins` includes identity.json, bootstrap.json, startup.json, state.json,
  pending.json, request.json and responses/OPERATION_ID.json, plus selected old
  failed/launch/continuation evidence. At most 32 files, 128 KiB each and 512 KiB
  together. Identity/request/bootstrap hashes, worker/connection identity,
  startup/SID, dispatch envelope and exact operation must agree. Only the
  selected FAILED + PENDING + UNKNOWN dispatch case is supported.
- `evidence` has exactly `terminal`, `commands`, `effects`, each a
  `{path, sha256}` reference to a regular non-symlink JSON file (128 KiB bound).
  These are normalized accessor outputs, not claims that arbitrary transcripts
  were parsed. Each has schema `agentos.screen-KIND-evidence/v1`, `session_id`,
  `operation_id`, `turn_id` and `envelope_sha256` (canonical `safeio.digest` of
  the exact original envelope string). The trusted accessor must independently
  verify the exact native source and map the envelope/operation to that turn.
- Terminal evidence has `status: completed`, `source_verified: true`.
  Commands evidence has `coverage: COMPLETE` and nonempty `commands`, at most
  2,048 entries, each with unique `id`, `command_sha256` and integer `exit_code`.
  Nonzero commands can be reconciled; they are never relabeled successful.
- Effects evidence has `coverage: COMPLETE` and one command entry for each
  command ID, with `disposition: OBSERVED|RECONCILED`, nonempty `scope` and
  `evidence_refs`. An empty inventory or unresolved effect cannot qualify.
  No rule infers absence of writes from a completed turn or zero exit code.

The owner adapter is an existing authorized context manager, not installed by
this module. `guard(plan)` yields `check(query)` while holding controller
exclusion across publication. The query binds phase `publish_reconciliation`,
plan/evidence digests, SID, operation and terminal turn. Its response echoes
every binding and supplies current `observed_at` (at most 60 seconds old), a
nonempty stable `owner_exclusion_token`, `owner_exclusion_held: true`,
`source_writer_state: FREE`, `old_owned_lineage_absent: true`,
`native_evidence_verified: true`, `command_effects_reviewed: true`,
`reviewed_plan_sha256` and nonempty `reviewer`. It must actually verify
provenance, complete command coverage and effect disposition against the
selected source/targets. This contract does not grant that accessor authority.

The core checks old PID absence and absent lifecycle worker.lock, locks the SID
reconciliation and old control paths, rechecks all pins/evidence after the owner
callback, and creates a receipt only once. Duplicate/concurrent publication,
changed inputs, live old writers or incomplete owner review refuse. Limits and
regular-file checks bound input, not the trustworthiness of its author.

The return is `{operation_id, receipt_sha256}`. Pass it as
`adoption.pending_reconciliation` to existing guarded `adopt_screen`. It refers
only to the canonical receipt under
`home/state/screen-reconciliations/SID/OPERATION_ID.json`; it is not an arbitrary
path or an authorization token. Every adoption readback revalidates retained
pending/evidence and receipt hash. An absent pending or stale receipt refuses.
All live adoption guard responses must additionally bind
`pending_reconciliation_sha256` to that receipt and `terminal_turn_id` to its
reviewed turn. PID/lineage/writer exclusion, current target authority, original
contract retention, model/provider/catalog/probes and SID once-journal still
apply. Reconciliation does not reset a previous adoption attempt.
An exact successful predecessor can instead be selected through the explicit
[reviewed successor contract](SCREEN_SUCCESSOR.md), with its own immutable
chain edge, later-operation binding and fresh guard review. Reconciliation
alone never unblocks or resets an existing SID attempt.

The receipt records `RECONCILED_FOR_COLD_ADOPTION`, the original UNKNOWN and
pending preservation, with `replay_authorized: false`, `business_accepted: false`.
This is a separate reviewed disposition, never a rewrite of old status. A
forged caller file is not authenticated by its checksum; the held trusted
accessor and fresh adoption guard remain mandatory. No hostile same-UID or
crash-proof transaction guarantee is made. Crash during receipt publication
requires exact-state reconciliation; never delete pending or retry effects.

Source fixtures prove this bounded API using synthetic native evidence and
held guards. They do not prove installed adoption, real native source
verification or any application's business acceptance. Installation and actual
recovery require separate owner review and current target authorization.
