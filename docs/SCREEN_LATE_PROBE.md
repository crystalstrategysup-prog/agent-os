# Late harmless probe disposition and cold continuation

`screen_late_probe.reconcile_late_probe(home, plan, owning_guard=...)` publishes
one immutable `agentos.late-probe-reconciliation/v1` receipt for a narrowly
qualified pre-work failure. It performs no mailbox/native action and never
changes the original FAILED worker, pending probe, UNKNOWN launch/adoption,
claim history or failed successor edge. The receipt says effects reviewed,
not old probe PASS or work replay authorized.

## Request and trust boundary

`agentos.late-probe-request/v1` binds session_id, operation_id, turn_id, exact
failed_adoption and failed_adoption_sha256, failed_worker_name, seven exact
worker_pins (identity/bootstrap/startup/state/pending/request/selected response),
failed_launch_sha256, old dispatch_binding, pinned probe_evidence, replacement_name
and exact replacement_request. The failed journal is selected through canonical
SID ancestry, with successful predecessors only and a bounded chain. A stale,
foreign, consumed, UNKNOWN or in-flight predecessor refuses.

The exact accepted failure has a resumed SID, FAILED worker on `probe`, a PENDING
probe mailbox and UNKNOWN `screen_provider_TimeoutError` response. Its launch
is STOPPED after STARTUP_READBACK_VERIFIED, before probe acceptance, work or claim.
The pinned `agentos.late-probe-evidence/v1` must bind exact SID/worker/connection/
request/operation/attempt/terminal turn; complete native provenance and execution
code pins; zero work; absent old dispatch claim; complete temporary-file cleanup;
and exactly the ordinary filesystem read/write scripts, nonce outputs, workspace
and successful exits. Other capabilities/commands, missing effects, active native
work and flags without trusted provenance do not qualify.

A held trusted owning accessor returns the complete plan/query binding, fresh
stamp and stable exclusion token, reviewer/evidence ref and true flags
`owner_exclusion_held`, `both_owned_lineages_absent`, `native_evidence_verified`,
`complete_probe_effects_and_cleanup_reviewed`, `no_work_or_claim_verified`,
`same_sid_continuation_authorized`, `current_target_security_verified`. It proves
the actual complete native trace, current authority/security and exclusion; JSON
assertions alone grant no authority. Local PID/lock/pin checks supplement this
accessor. The original source and failed destination must both be quiescent.

## One new transport, new capability proof

The returned reference contains failed_adoption_sha256 and receipt_sha256.
`adopt_screen` takes an explicit adoption with exactly session_id, old_name
(the failed worker), old_pins and late_probe_recovery(reference). Fresh launch_id
and worker name are required. The replacement request preserves all settings,
goal, authority and targets, updating only context.adopted_original_contract to
the failed request contract and optionally its validated finite probe budget.

The existing SID lock and create-only attempt reserve one continuation, including
failed attempts. Existing normal catalog, actual startup/settings, current READY,
target/security and dispatch claim gates still run. Live guard records bind
late_probe_binding_sha256, exact terminal turn and true late_probe_effects_only_verified,
both_owned_lineages_absent, fresh_same_connection_probes_required and
current_target_security_verified, alongside all ordinary adoption guard fields.

The new transport resumes the SAME native SID and MUST perform normal fresh-nonce
same-connection capability probes under the reviewed finite budget before work.
The late old probe supplies no capability proof for that changed dependency.
A new unknown outcome remains guarded; this is no generic failed-work retry or
permission to stop/reset/replay. No model/provider/effort/permissions change or new
blank native session is authorized. A later normal successful successor may use
explicit late_probe_history(reference); success is still independently checked.
Nested late-probe recovery is deliberately unsupported. Publication, installation
and actual recovery require their separate current owning review and authority.
