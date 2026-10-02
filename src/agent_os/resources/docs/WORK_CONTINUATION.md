# Completed stages and unfinished projects

Current public version: `0.7.0`. RC-labelled sections below are retained historical records, not current installation or publication claims.


A CLOSED result proves one local stage, not completion of the whole project or
delivery to the next agent. The parent adapter owns continuation, provider I/O,
target authority and independent evidence verification. This optional protocol
adds durable metadata; it is not a scheduler, hook, worker launcher or grant.

## Before the stage

For a continuing workstream, set `continuation_required: true` in the task answers.
At closeout provide `review.continuation` with exactly these fields:

```json
{
  "schema": "agentos.stage-continuation/v1",
  "parent_owner": "parent",
  "stage_owner": "author",
  "next_owner": "independent-reviewer",
  "next_action": {"kind": "review", "summary": "Review frozen final bytes."},
  "project_complete": false
}
```

Actions are `review`, `next-stage`, `owner-decision` or `verify-target`, with no
command payload. A review owner differs from the stage author. Identifiers are
actor labels, not identity authentication. Record private thread/host mappings
only in the external user configuration. Existing tasks without opt-in retain
their original closeout behavior; no historical records are rewritten.

## Parent continuation

Reconcile each explicitly selected completed task before reporting unrelated
status. Record the planned next actor/action even if a real capability is absent.
Do not infer a completed project from a completed stage or a read-only report.

```sh
agentos --home U continuation reconcile --root P --task TASK
agentos --home U continuation status
agentos --home U continuation claim --id ID --actor parent --revision 1
agentos --home U continuation begin-delivery --id ID --actor parent --revision 2
```

Creating a new item with `reconcile` verifies current closeout/source and copies
its continuation to the external overlay. Recovering an existing item checks
its immutable stage binding and returns its exact identity and delivery state,
even after source drift or evidence aging. Recovery never admits a new send.
No whole-project/history scan occurs. A compare-and-swap revision and one parent
owner prevent a second claim. Core metadata never substitutes for a target lease.
An owned or unknown delivery also blocks a replacement claim from another stage
of that same registered project/root. Different roots/host actors still require
the real coordination lease; the local queue is not a global lock service.

Commit `DELIVERY_UNKNOWN` before any send. The v2 item keeps stable `attempt_id`
as the operation key and creates a new `delivery_generation`, random
`delivery_nonce` and `delivery_started_at` for every admitted delivery. Pass these
exact fields through the provider adapter and its verified evidence. Then use the existing authorized
provider adapter. If the response is lost, inspect its actual durable state for
the same actor/attempt; do not create a replacement writer or send again. This
state has no timeout-based takeover. Read-only reports never consume the item.
Admission requires current source/check evidence. Recording an already admitted
provider acknowledgement uses its immutable stage identity even if subsequent
work changed source; it does not authorize a fresh delivery of stale work.

After observing the exact target's accepted user event followed by later activity,
pass a bounded receipt to `continuation acknowledge`. Its exact fields are
`schema=agentos.continuation-delivery-receipt/v2`, `attempt_id`,
`delivery_generation`, `delivery_nonce`, `target_owner`, `provider`, `checked_at`,
`status=ACCEPTED`, `user_event_id`, `later_activity_id`, `user_event_at` and
`later_activity_at`. All timestamps carry a timezone. Core requires the current
generation/nonce, delivery start <= accepted event < later activity <= checked
time, and rejects checked times over five minutes in the future. Receipt event
identities are consumed and retained in bounded history; changing a revision,
generation/nonce or checked time cannot reuse consumed evidence identities.
The adapter must validate origin, actual sequence and current scope; structural
timestamps and actor/provider labels do not authenticate the evidence. A queued keystroke or
an ordinary notification is insufficient. Local same-user forgery is outside
the structural trust boundary, as with other AgentOS receipts.

Only proven non-delivery permits `continuation not-sent` with status
CONFIRMED_NOT_SENT and a specific `rejection_id` instead of all four event fields,
with the same common v2 binding fields and checked time. A rejection identity is
consumed once. Retry preserves the operation identity but increments generation
and creates a fresh nonce; an old receipt cannot reopen the newer unknown send.
After 128 admitted deliveries, further retry requires owner review. Ambiguous
delivery stays owned and blocked.
Provider idempotency/reconciliation remains necessary; no exactly-once external
execution is promised.

ACKNOWLEDGED means the next actor accepted work, not that the review passed or
the project finished. The parent retains its role, records actual review outcome,
updates the current handoff and selects any next stage separately. This protocol
does not automatically implement a downstream stage, choose business scope,
clear HOLD, create permissions or erase an acknowledged item's history.

## Scope changes and limits

An explicit new owner instruction can resolve a prior scope question. Reuse the
same workstream ownership, refresh the scope and evidence, then route the next
safe action; do not repeat a superseded blocker. Keep unrelated coverage and
authority gaps explicit. Missing tools block only their dependent effects.

Package adoption, user policy adoption and actual parent adapter use are separate
proofs. Tests establish local durability and refusal behavior, not that every
client loaded the guide or that a remote transport works. Updates preserve the
external queue, ownership and attempts; rollback must not discard them or revive
native hooks. Publishing and host activation require their own reviewed scope.

Legacy v1 ledger items remain readable and recoverable, including existing
unknown delivery and known ACK. All their transitions fail closed with
`legacy_delivery_binding_requires_owner_reconciliation`: old evidence has no
generation/nonce binding and cannot be safely upgraded by guessing. This source
candidate supplies no automatic migration or reset. A separately reviewed
owner/provider reconciliation is required before those items can transition.

For explicit untouched-PENDING legacy promotion, artifact queue compatibility,
rollback HOLD and the real provider acceptance packet, see
`CONTINUATION_RELEASE.md`. Unknown/ACK transitions still require separately
reviewed owner/provider reconciliation.

## Historical: Main coordination successor0.7.0rc2

The universal [coordination contract](WORK_COORDINATION.md) adds original-goal retention and an opt-in local receipt/review/next-action ledger. Existing continuation schemas/transitions remain byte-inherited; ACK/RECEIVED still means receipt, not semantic acceptance or project completion. Selected active partial handoffs can use Coordinator.recover_notice without pretending CLOSED-only continuation accepts them.
