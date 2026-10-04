# Completion mutation surfaces and guard matrix

This inventory covers every public Coordinator/CompletionMixin state/effect write,
its legacy delegates, and passive evidence exports. Private publication helpers
are trusted implementation details, not actor-authenticated public entry points.
All integration callers still authenticate current authority independently.

## Common invariants
A state write requires the current owner, exact revision, non-reversed checked
clock and live lease. Takeover is the explicitly authenticated successor exception:
current epoch, policy, fencing/quiescence and exact target proof are mandatory;
lease expiry alone grants nothing. Exact duplicate evidence/event reads do not
renew a lease, advance revision, update runtime/budget or accept a project.
Conflicting identifiers fail closed. Stale owners cannot add even audit records.

Ordinary control-plane writes reject terminal records. Execution/acceptance writes
also require an unrevoked, unexpired policy. Policy replacement/discovery,
heartbeat, cancellation and checkpoint are separately owned administrative actions;
none is effect authority. Revocation does not prevent recording cancellation or
preserving a verified backup. Cancelled recovery is allowed only to preserve
cancellation, ledger truth and actual unfinished bytes. ACCEPTED is immutable to
checkpoint/restore and control-plane operations.

Route replacement cannot un-revoke policy or replace capabilities after revocation.
Only the distinct takeover path with fresh independently authenticated target,
fencing/quiescence proof and live replacement policy can transfer authority.
Void authentication/authority verifiers use the existing raising-only adapter
contract: failure must raise; success returns None or explicit True. False,
numeric truthiness or arbitrary values are rejected. Structured target/receiver
verifiers retain their separately validated evidence shapes; Goals requires True.

## Audit versus execution
Pure audit may append bounded terminal event identities and immutable audit
references. It cannot alter work, ownership/fences, policy/capabilities, dispatch,
criteria/results, remaining budget, actual runtime, semantic progress, review,
handoff/delivery or goal acceptance. Audit projection timestamps/revision describe
observation, not permission renewal. Terminal retention has a separate finite
identity bound; identical duplicates are read-only even at capacity and conflicts
are rejected. Overflow rejects a new identity without losing earlier history.

Ledger reconciliation is a distinct safety write: authenticated exact evidence
may resolve an existing UNKNOWN operation, and thus remove its planning hold.
This is not pure audit, a new effect, a budget debit or semantic acceptance.
Old-generation/epoch/cancel/policy results preserve historical usage/runtime only
inside that operation, never in current budget/runtime/results/work/review. Current
result promotion additionally rechecks current policy revision, scope, expiry and
cancellation. Reconciliation preserves the same operation identity and dedup key.

## Enumerated entry points
- Creation/activation: Coordinator.create; activate_completion (including dry-run).
- Administration: completion_heartbeat, completion_update_route,
  completion_route_error, completion_wait, completion_change_contract.
- Events: completion_event, including cancellation, duplicate/conflicting IDs,
  out-of-order/generation mismatch, terminal retention and revoked-policy notices.
- Effects/budget: completion_plan, completion_begin_dispatch,
  completion_receiver_admit, completion_spawn_local, completion_goals_opt_in.
- Acceptance/delivery: completion_review, completion_prepare_handoff,
  completion_handoff_sent, completion_ack, completion_accept.
- Ledger/evidence: completion_record_result, completion_reconcile.
- Ownership/recovery: completion_takeover, completion_checkpoint,
  completion_restore. Checkpoint must revalidate owner/revision after capture.
- Passive reads/materialization: completion_verify_checkpoint,
  completion_rehearse_restore. They do not activate the copied paused snapshot or
  renew current authority; destination filesystem authority remains caller-owned.
- Legacy writes after activation: receive, recover_notice, review, checkpoint,
  begin_action, record_outcome, verify_goal. Reject before external Library reads,
  and again at publication. Unactivated v1 behavior remains separately tested.
- Private support: _completion_store (immutable objects),
  _completion_transaction (atomic state commit), Coordinator._save (HEAD publisher).
- Adapter delegates: LocalCompletionRunner.run/run_bounded; receiver admission and
  process spawn remain behind the current Coordinator guards, with real I/O tests.

The executable inventory in MUTATION_SURFACES.json records per-operation policy,
terminal, replay and write classes. Tests compare it with actual public methods so
an added mutator cannot silently escape the matrix. Systematic valid-input tests
cross owner/lease/cancellation/revocation/replay dimensions. Generated state-machine
sequences assert invariants after each interleaving, including audit retention,
late evidence, revocation, cancellation and stale/exhausted writers. Source checks
still do not prove installed-host adoption or publication. Prior candidate receipts
remain historical until final changed-byte regressions and independent re-review.

The shared-event replay matrix does not substitute for operation replay. Commands
without an event/evidence ID reject reused revisions through CAS. Exact ACK/result/
reconciliation evidence duplicates are read-only after lease expiry, revocation or
cancellation for the current owner; conflicting evidence and stale owners fail
closed. Creation has no prior owner/lease, and passive exports have no actor API;
their N/A dimensions are explicitly recorded rather than treated as passed guards.
Checkpoint pause prevents new dispatch, but a process inventory alone does not
prove that previously admitted effects are quiescent. Restore separately verifies
target fencing/quiescence and reconciles such effects before unpausing.
