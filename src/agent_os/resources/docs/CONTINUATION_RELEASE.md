# Continuation release candidate and acceptance boundaries

Current source candidate: `0.8.0rc2` (not publication or host adoption). RC-labelled sections below are retained historical records, not current installation or publication claims.


## Historical: Indexed handoff successor0.7.0rc1

The following0.6 continuation documentation remains predecessor-specific. Indexed handoff candidate0.7.0rc1 does not activate a scheduler or change continuation delivery authority. See [indexed handoff](INDEXED_HANDOFF.md).

The predecessor continuation candidate proposed `0.6.0rc3`. Its local wheel,
structural tests and installed fixture are separate proofs. They do not establish live provider continuation,
client adoption, remote activation or publication. Previous artifacts remain
immutable. No scheduler, arbitrary send, credential grant or hook is added.

## State owner and compatibility

Core owns a bounded external local ledger, CAS revision, stable operation key,
per-delivery generation/nonce and consumed receipt history. The real parent owns
workstream progress, provider authorization/provenance and the actual target
lease. Migration owns only explicit safe promotion with an immutable backup;
the installer owns core release pointers and reads user schemas without resetting
them. Provider bindings and private target maps remain outside the public core.

`continuation migrate-legacy --id ID --actor PARENT --revision REV` is a read-only
plan. Only v1 `PENDING` with no attempt, receipt, generation/history or started
worker can be promoted. Apply uses the exact plan SHA:

```sh
agentos --home USER continuation migrate-legacy --id ID --actor PARENT \
  --revision REV --apply --expected-sha256 EXACT_PLAN_SHA256
```

The tool preserves original bytes in `USER/backups/continuation-v1/`, checks
revision and hash under the continuation lock and creates v2 generation0 with
unchanged stage/owner identity. This admits no dispatch; normal current-source
checks still apply. A lost response is recovered by reading the existing item
and exact backup, never by rewriting task records or creating a new PENDING.

v1 CLAIMED, DELIVERY_UNKNOWN and ACKNOWLEDGED return `HOLD_LEGACY_UNBOUND`.
They stay readable and byte-identical. Their missing generation/nonce cannot be
reconstructed from timestamps or actor labels. The actual parent/provider must
reconcile the original operation and retain its durable result first. This
candidate implements no unsafe owned-state migration or automatic retry. Known
ACK remains known; unknown remains unknown. A separately reviewed migration is
required if a live old queue contains owned legacy state.

The wheel bundles `continuation-capabilities-v1.json`; its exact verified bytes
supply installer reader capabilities. Old wheels with no declaration support
no continuation queue. Before activation/rollback, the installer bounds and
checks each queued schema. Unsupported v1/v2 state returns
`continuation_queue_incompatible_preserve_and_hold`; it does not move current
or alter queues. An existing continuation state directory is locked across the
final check and pointer switch, serializing compliant local queue writers.
A host activation still requires a quiesced real parent and target lease;
this temporary lock is neither authentication nor distributed coordination.

Rollback to an old core is safe only when its verified artifact can read every
retained queue item. There is no force/reset flag. If an older artifact cannot,
retain the current reader and HOLD, or deploy a reviewed compatible forward
repair. Never delete, archive away, downgrade by guessing or recreate active
items merely to make rollback pass. Empty-queue old/new/old is a separate fixture
from a blocked downgrade with preserved unknown/ACK. Integration rollback never
restores hooks or changes unrelated security/auth/model configuration.

## Actual parent/provider contract

`continuation_adapter.binding`, `request` and `check_receipt` are pure helpers.
They pin the configured provider namespace, parent/target owner and exact target
/workstream, propagate committed operation/generation/nonce, and check receipt
shape/time/binding. Their result explicitly has external provenance and delivery
acceptance false. They perform no I/O or ledger transition. A caller-supplied
label, JSON field or synthetic event is not an authenticated provider receipt.

The production adapter is acceptable only after these observable requirements:

1. Read the actual authorized tool/adapter schema and connected identity. Select
   one pinned mapping from provider to real target/workstream and parent. Record
   its version/hash privately before sending. A provider rename or changed
   target is a reviewed mapping change, never a way to reuse old evidence.
2. Verify the actual existing writer lease and target authority. Reconcile the
   explicitly selected CLOSED stage; claim current metadata and commit
   DELIVERY_UNKNOWN before the provider invocation. Propagate the stable
   operation key plus current generation/nonce to the exact call/message
   envelope the actual provider supports. Record the durable invocation ID.
3. Retrieve authoritative provider state, using the same connected identity and
   exact target. ACK requires the matching accepted **user event** followed by
   later non-user activity. Verify IDs, event payload/call correlation and actual
   provider sequence. Merely echoing nonce, filling timestamps, queued Screen
   keystrokes, notification ACK or process liveness does not meet this boundary.
4. Match the observed events to the persisted generation/nonce and pinned
   namespace; retain bounded event references and hashes outside public source.
   Only then supply the v2 receipt to the current ledger revision. ACK means work
   accepted, not independent review PASS or project completion. Record review
   outcome and choose the next stage separately.
5. After a lost/ambiguous response, retain UNKNOWN and inspect the same operation
   through the authoritative provider. No new writer/send or timeout takeover.
   CONFIRMED_NOT_SENT requires proof that this specific invocation was rejected
   before delivery, with one stable rejection identity. An accepted request that
   later failed work is not non-delivery. If the provider cannot prove this,
   continue HOLD; do not manufacture a rejection or receipt.

Required live acceptance packet: adapter/tool identity, mapping digest, target
lease/authority reference, exact source/stage/ledger identity, actual invocation
reference, authenticated user event and later activity references, reconciliation
query evidence and ledger before/after hashes. Keep credentials, message bodies,
private hosts and personal target IDs outside public artifacts. Synthetic test
packets are labeled fixtures and cannot satisfy this packet.

Live acceptance must demonstrate ordinary completed-stage→review admission,
lost-response recovery without resend, stale ACK/rejection at current revision,
consumed rejection replay, read-only report interleaving and absence of a
replacement writer. A blocked or unsupported transport leaves only that effect
pending; the parent continues already authorized independent work. No actual
provider proof is included by this source candidate.

## Sequential host acceptance and publication

Plan exact per-host/user current release, Python, roots, queue schema/state counts,
current client integration, protected configuration hashes and rollback target
from fresh authorized readback. Historical host lists are discovery leads only.
Do not infer another user's installation from the same host. Keep private
identities in the external rollout record.

Activate the local canary only after its exact authority/artifact/compatibility
review; then user contours and hosts sequentially. For each: retain old immutable
release, snapshot bounded external metadata under the real lease, verify wheel
hash, plan, apply against exact expected-current, run the **installed** version,
doctor/resources/MCP/read-only and explicit project lifecycle, then read back
current and queue bytes. Run managed integration separately only when authorized.
Fresh process and fresh connected client instruction adoption are distinct proofs.
On mismatch, HOLD that contour and use verified compatible rollback/forward
repair; never proceed fleet-wide from an earlier host's result.

Publication comes after agreed host/user acceptance and actual parent/provider
proof. Verify tag availability, canonical account/repository/HEAD, local gates,
intended public-file allowlist and exact artifact hashes before direct Git/tag
and release actions. Downloaded assets must match the same hashes. No GitHub
Actions, force/reset or overwriting prior assets. Preparing this RC grants no
publication or host activation authority.
