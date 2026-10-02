# Main coordinator knowledge and execution contract

Current public version: `0.7.0`. RC-labelled sections below are retained historical records, not current installation or publication claims.


Contract: `agentos.work-coordination/v1`, knowledge revision `1.1.1`.
Stable source: **0.7.0 — NOT_INSTALLED, NOT_PUBLISHED, NOT_LIVE_ADOPTED**.
This approved universal work-management contract governs the prepared public
source. The installed predecessor retains its own version. Source
rules never change model system instructions, start a scheduler, authorize a
new writer or alter actual target gates.
Its single index is `COORDINATOR_KNOWLEDGE_INDEX.json`; private display name and
preferences belong only in the external owner overlay.

## Assessment

The model is suitable for bounded projects with one accountable
coordination role and independently scoped execution. It needs durable state,
verified result acceptance and explicit resource limits. Merely asking an agent
to continue cannot guarantee that a session stays alive or wakes after a result.
Current AgentOS contains useful synchronous primitives, but no demonstrated
always-running main-coordinator loop. Architecture approval authorizes source preparation; deployment and live adoption remain separate.

The recommended adjustment is **local plan review after every result** and
**full replanning only after a material change**: goal/acceptance, critical path,
shared interfaces, available capacity, authority or significant risk. Constant
global rebuilding wastes context, creates checkpoint barriers and destabilizes
otherwise valid work. Record why each reassignment is necessary.

## Terms and ownership

- **Agent / role**: the responsibility, decision rights and acceptance duty.
  `main-coordinator` is a role, independent of a display name or model identity.
- **Session**: an actual provider-owned conversation/execution context with a
  verified session/thread identifier, lifetime and supported I/O. A CLI workflow
  label, directory or instruction is not proof of a running provider session.
- **Subagent**: a delegated execution context created through a supported
  capability inside a session. Its parent session owns its scope, evidence and
  reporting. A separate worker session is not counted as a subagent.

There is one logical plan owner per workstream. A standby may read and verify
state; it cannot take over a live or unknown operation because a heartbeat aged.
Recovery needs exact ownership reconciliation, current authority and fencing
against a former writer. The display name does not authenticate an actor.

## Required nine-step operating order

1. **Analyze actual state.** Verify selected source/runtime, current docs,
   accepted indexed results, open work, ownership and available tools. Mark
   unknown/stale facts and observation times; do not preload every transcript.
2. **Agree the final goal and acceptance.** Use the latest authorized goal and
   measurable result criteria. Separate stage completion, independent review,
   deployment and whole-project acceptance. Do not invent a missing decision.
3. **Plan steps, dependencies and critical path.** Give each work item a stable
   ID, owner, input/output contract, required predecessors, acceptance, boundary
   and next safe action. Estimates are estimates; elapsed execution is measured
   separately. Detect dependency cycles and explicitly track integration work.
4. **Distribute independent parts rationally.** Assign bounded work to separate
   supported working sessions with explicit non-conflicting write/effect sets.
   A session may use subagents only within current instructions, permissions,
   available capability and budget. Keep reviewers separate from authors where
   independent review is required. No replacement writer for unknown outcomes.
5. **Notify on partial and final results.** Each session supplies work/session
   identity, result kind, exact source/task/revision, indexed handoff ref,
   verified checks, unfinished scope, blocker and next recommendation. Preserve
   a stable notification/operation identity and a durable producer checkpoint.
   Notification submission, coordinator receipt and result acceptance are three
   distinct facts. The coordinator must verify provider evidence before receipt.
6. **Review every received result and choose the next action.** Read back the
   accepted handoff and relevant evidence, compare promised acceptance and
   current scope, record accepted/held/partial with reasons, then review the plan.
   Record the next work item/owner/action or a specific dependency/decision
   waiting state. Assignment is not proof of worker start or successful delivery.
   Reassign only when ownership and actual effects can be safely transferred.
7. **Collect coordinated checkpoints when full replanning is needed.** Request
   a versioned snapshot from every affected session, including in-flight/unknown
   effects and owned paths. Preserve independent safe execution and file
   ownership. A checkpoint request is not a global stop signal. Quiesce only a
   conflicting/in-flight effect or changed shared contract before its boundary
   changes; never pretend snapshots taken at different times are an atomic cut.
8. **Ask the owner only for an unavoidable decision or permission.** First use
   verified known facts, permitted recovery and already authorized alternatives.
   Escalate the exact missing business decision, authority, credential interaction
   or irreversible loss boundary with evidence and the smallest useful choice.
   Continue independent authorized work. No profile/plan bypasses confirmation.
9. **Keep indexed handoff and notification/action accounting.** Retain exact
   result refs, receiver acknowledgement, semantic review, plan revision and
   next-action assignment separately. Reconcile a missed notification through
   the supported provider read/receipt and explicitly selected stored result;
   do not infer failure from silence or resend an unknown operation blindly.
   Keep history and retry the same stable operation only after proven non-delivery.

## Architecture qualifications

| Risk | Required qualification before adoption |
|---|---|
| One coordinator becomes a bottleneck or single failure point | Bound coordinator context; retain a small versioned plan/index and immutable result refs. Recover from durable state with one fenced owner. Do not launch an active-active replacement merely on timeout. |
| Lost, repeated or out-of-order notices | At-least-once delivery with stable IDs and idempotent receive/review. Separate transport receipt from semantic acceptance. Bind exact work/result revision; stale reports stay historical. Outbox/inbox or equivalent durable provider reconciliation must be proven. |
| Registry damage or incomplete state | Atomic revision/CAS, schema/hash validation, independent backup and restore probe. The accepted Library ROOT protects library acceptance, not an unimplemented global workboard. Unknown ownership/delivery remains blocked for that effect. |
| Unbounded parallelism | Constrain real session/subagent capacity, cost, CPU/network, reviewer and integration capacity. Use backpressure and bounded work slices. More executor labels do not prove useful throughput. |
| Disjoint paths still share effects | Include Git branch/ref, generated files, lockfiles, migrations, DB/domain state, deployment target, services, credentials, ports and shared API contracts in conflict analysis. Use isolated worktrees where applicable and an integration owner. Check actual target leases; a draft write-set is not a distributed lock. |
| Frequent results force full replanning | Perform a local dependency/acceptance update each time. Rebuild the global plan only at the material-change triggers above; checkpoint only the affected consistency boundary. |
| Apparent idle time leads to unsafe duplication | Measure actual last progress/check/result/provider event, freshness and declared expected wait. An open session/heartbeat is not business progress. Inspect a stall through supported reads, distinguish dependency wait from failure, and never expire unknown effects into a new writer. |

Required measures: planned/assigned work separately from verified starts,
received notifications, reviewed results, accepted criteria, completed/remaining
work, blocked work, elapsed check/run time, critical-path wait, queue age and
last meaningful progress. Count verified sessions and subagents separately from
declared actor labels. Unknown runtime counters stay unknown; arbitrary progress
percentages and a receipt-only ACK must not become completion statistics.

## Existing supported primitives and gaps

Installed0.5.5 supports explicit documentation-first lifecycle and bounded
profiles. It lacks the candidate continuation and indexed-library modules.
The historical0.7.0rc1 source candidate supplied:

- `project.close`/`verify_closeout` and mandatory accepted Library handoff;
  `project.checkpoint` records incomplete work and leaves other project roots
  untouched. Current source/check/evidence identity must still be verified.
- `Library.resolve`/`read_evidence`/search for the selected authorized result;
  current ACL and exact refs apply. Full/partial recovery remains explicit.
- `continuation.reconcile(home, root, task_id)` or CLI equivalent for an
  explicitly selected **CLOSED** opted-in stage, including a missed final signal.
  Reconciliation is idempotent; claim/begin-delivery record exact ownership and
  unknown delivery before provider I/O. Bound receipt APIs record actual evidence.
  ACK/RECEIVED mean receipt, not review passed, worker started or project finished.

These are synchronous operations. The new opt-in `work_coordination.Coordinator` is a synchronous local durable
ledger. `create` records the original goal/criteria, typed actor/session ownership,
bounded DAG and resource/path sets. `receive` reads the exact current accepted
Library ref and required bytes, then saves receipt separately from review.
`review` checks the original goal binding and read-back evidence, records semantic
judgment/reasons/remainder and owned next actions atomically. Empty remainder or
an absent next action without an evidenced user pause/specific unavoidable blocker
is refused. A blocker cannot suppress a ready independent part.

Completed children leave the parent OPEN. Only `verify_goal` can complete it,
using an accepted, byte-verified result for the exact original goal and all
original criteria, completed required children and no unknown admitted effect.
Each required child's completion must bind its latest notice to an accepted
semantic review of the exact current Library manifest and captured evidence.
A new current report clears the prior acceptance; a formerly completed child is
held until review. Completed reports also require review. Superseded notices
remain historical with an explicit successor, without fabricated review or
acceptance; they cannot roll current work back through delayed delivery/review.
Current unreviewed notices block parent closure. Supersession or retraction in
Library blocks closure even before notification arrival. An old action receipt
cannot supply acceptance of a newer result. Exact current receive/review retries
are idempotent; calls after parent completion refuse changes. Legacy completed
rows lacking explicit notice/review binding fail closed and require fresh
reconciliation; there is no automatic state migration. These checks observe
current local Library state, not a distributed atomic cut or guarantee against
later result changes after closure.
The responsible caller still verifies the real user/business outcome; a synthetic
result, label or provider receipt cannot certify an unobserved live outcome.

The ledger uses bounded immutable SHA snapshots and one conditional HEAD under a
kernel publication lock. Owner/revision conflicts refuse; duplicate result notices
and exact repeated reviews retain the same decision/action. `recover_notice`
reads the explicitly selected registered work's current indexed result, including
active partial handoffs; it does not scan sessions or relaunch a worker. This adds
partial-result receipt accounting alongside existing CLOSED-only continuation.
`checkpoint` preserves the local plan/ownership/effects and records checkpoint
recipients; actual requests/aggregation use the real provider, not this method.

`begin_action` persists UNKNOWN before a caller performs an external effect.
`record_outcome` requires hash-verified captured provider evidence bound to exact
action/operation/generation/nonce; it consumes event identities. Running, stopped
and unknown observations remain unknown effect outcomes. Only proven non-execution
permits a bounded retry with the same operation identity and a fresh generation.
No call executes the action. Trusted adapter provenance and actual target authority
remain separate; these local same-UID records are not remote authentication.

No background monitor, automatic provider inbox/outbox, worker launcher, global
DAG scheduler, ownership-transfer service or runtime-counter collector is supplied.
The ledger plans/reserves disjoint declared effects and checks bounded capacity,
but cannot infer hidden shared effects or authenticate a live session. Continuous
operation and automatic wakeup depend on actual platform support.

## Knowledge reading and adoption boundary

The generic index pins relative document paths, versions/statuses and hashes.
Consumers read the selected index and verify only relevant referenced bytes;
they do not duplicate rules in a private profile or infer that source preparation
means live adoption. An owner profile can carry a bounded role/index pointer and preferences
through `agentos.profile/v1`; exact inventory/selection guards still apply.

For a local root session the supported path is explicit `agentos resources`,
`profiles context`/project questionnaire, followed by file read and hash checks.
Profiles transport text; they do not dereference an index, inject new system
instructions or continuously run a coordinator. The candidate managed AGENTS/skills route to the one generic index. Applying
that bootstrap to a real client is separate: preserve owner content/overrides
and read back the effective routing in a fresh session before claiming adoption.
No current client files are rewritten during source preparation.

A voice session needs an actually connected tool/app capable of reading the
selected private profile/index and required result refs, plus authenticated
receive/action support. Local filesystem availability or a configured display
name does not prove this. The candidate persona gate consumes trusted interaction
signals and returns a response plan; it does not implement microphone detection,
knowledge loading or message delivery. Root and voice live use are NOT_VERIFIED.

Independent exact-source/package acceptance, any core release, live profile/routing
adoption and a real root/voice canary remain distinct future proofs. No install/publication
or owner instruction change is performed during preparation.

## Parent goal and reconnect recovery

The parent remains open until the original checked user result, regardless of
delegation, child completion, partial report, session exit or notification receipt.
Every result follows report → original-goal check → explicit remainder → next
owned action. A temporary unreviewed notice stays visibly owned by the coordinator.
An explicit user pause or evidenced inevitable blocker is recorded with scope and
continuation; independent authorized work continues unless the user paused it.

After reconnect, recover the exact goal/plan/checkpoint/assignments and inspect
actual provider sessions (running/stopped/completed), accepted results, source
changes and unknown effects before issuing commands. A cloud session may have
continued while the Mac executor was inaccessible. Client “connected”, admission
or a session title is not executor execution evidence. A tool response lost after
action is neither success nor confirmed non-execution. Read the operation/result
through supported provider/target probes; do not assume a new executor is needed.

The implemented local failure windows are: pre-action admission loss retains
UNKNOWN until a verified non-execution receipt; action-before-receipt loss blocks
repeat while actual effect is reconciled; notice-before-review loss retains an
unreviewed record; review/assignment commit-before-response loss recovers the same
atomic decision and assignment. Registry corruption refuses progress instead of
reconstructing guessed state. Exactly-once deploy/DB/message effects still require
the actual target's idempotency or verified reconciliation; this module cannot
guarantee network availability, session survival, notification wakeups or external
transactions. Tests simulate faults in disposable fixtures, never by disabling
the user's network or VPN.

## Compact handoff and session retention

A current handoff preserves goal, boundaries, decisions with reasons, exact
evidence/source/version, remaining work/blockers, ownership and next step. Use
Library START/ROOT/ROUTES as its three bounded entry files and selected immutable
refs; restore verified required assets in a fresh process/destination without
old chat, archived commands or permissions. The coordinator ledger has its own
small HEAD and selected hash snapshot; it is not another transcript archive.

Full sessions are not presumed permanent knowledge storage. Preserve necessary
compact indexed evidence/recovery first. Logical retraction retains history and
reclaims0 bytes. Physical session deletion remains a separate exact approved
operation with loss boundary, restore proof and apparent/allocated-space
measurement; this candidate implements no session cleanup API.
