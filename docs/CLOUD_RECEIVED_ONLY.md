# Optional causal cloud receipt

This separately versioned local successor implements a received-only validator
and an optional owner-wired port. No real cloud tool, target ACK, root wiring,
client adoption, installed-core update or release is proven here. Synthetic
tests use the supplied cloud result fields; native events never become cloud
evidence. The frozen provider and accepted RC remain separate artifacts.

## Exact meaning and versions

`agentos.continuation-item/v3` commits a causal request before one possible send.
`agentos.continuation-delivery-receipt/v3` has `evidence_kind=causal_challenge`
and `acceptance_scope=received_only`. Its terminal states are `RECEIVED` and
`RECEIVED_REFUSED`. Both mean that the target explicitly acknowledged this
input. Neither proves successful execution, acceptance of review/work, delegated
authority, deployment or project completion. A refusal is delivered input,
never proof of non-delivery. v3 has no `not-sent`, reopen or automatic resend.

Native v2 keeps its timestamp/order receipt and `ACKNOWLEDGED` semantics. v1
remains read-only until its existing explicit untouched-PENDING migration.
`reconcile-causal` only creates a new selected v3 item; existing v1/v2 items are
preserved and HOLD. Causal items cannot use legacy migration or v2 receipts.
Reader capability declaration v2 lists these distinct contracts. Activation
of a release lacking v3 is refused while any v3 item exists, including PENDING
and received terminal history. No downgrade/conversion resets that history.
Actual frozen old-reader rejection is separately tested on a synthetic queue.

## Owner port and admission boundary

`cloud_continuation.CloudProvider(port, mapping, verify_authority=...)` requires
an exact pin: provider `cloud_threads`, this adapter contract SHA256, selected
parent/target owner, target thread and workstream. The contract hash identifies
the checked-in adapter field projection, **not** the entire cloud API schema.
The owner must wire `port.send_message(thread_id, message)` to the existing
`cloud_threads.send_message` and `port.read(thread_id, cursor=..., limit=50)` to
`cloud_threads.read`, normalizing its opaque pagination into `items/nextCursor`.
This Python port signature is an integration shim, not a claim that the tool
accepts those exact argument names. No hidden history/session route is used.

The supplied send fields are `threadId`, `turnId`, `admissionOutcome`. Admission
alone never acknowledges input. Read witnesses use `items.id`, `turnId`, `role`,
and complete `text`; `latestTurn` status is not receipt evidence. Producer
timestamps are neither supplied nor invented. The owner must independently
verify authenticated callback origin, selected-target authorization and lease,
and **persistent immutable complete item identities/content**. An identity
dictionary and callback are assertions, not authentication or new authority.
The available fields alone do not establish that immutability guarantee.
Unverified production ports must HOLD. The port must bound each external call;
this synchronous wrapper cannot cancel arbitrary SDK callbacks. All port I/O
and authority callbacks run outside the local continuation/driver locks.

## Durable challenge and explicit ACK

`cloud_continuation.run(home, id, actor, expected_revision, provider,
payload=...)` accepts only explicit v3. Before provider invocation the CAS core
commits `DELIVERY_UNKNOWN`, operation key, ledger revision, fresh random nonce,
generation, exact payload/hash, mapping hash and exact request text/hash.
The wrapper then persists `MAY_HAVE_BEEN_SENT` before calling send once.
Later UNKNOWN calls are query-only, including a missing intent or lost send
response. Recovery uses the committed core request, never permission to resend.
Wrong pin, owner or revision refuses. A received terminal returns without I/O.

The user message must equal the entire `AGENTOS_CLOUD_CHALLENGE_V1` envelope.
The target must emit one standalone **assistant** message beginning exactly
`AGENTOS_CLOUD_ACK_V1` plus a complete JSON object. It echoes schema, scope,
ledger ID, operation key, integer generation, nonce, request SHA256, target
thread and workstream, with `status=received` or `received_refused`; the latter
also requires `refusal_reason`. The committed envelope contains these exact
instructions. Quoted/fenced ACK, user/tool text, generic assistant activity,
admission, substring matches, extra fields, stale echoes and success claims do
not qualify. Explicit received ACK does not require completing the requested
work first. The owner must arrange this target behavior before a live probe.

## Positive bounded evidence and CAS

Read at most four pages of 50 items. A unique complete exact user witness and
unique valid explicit assistant ACK must have distinct actual event IDs and
the same actual turn. A known returned turn ID must match. Null/lost returned
turn can be recovered from this unique positive pair. Page order and local
clocks are not producer causal timestamps. Complete positive witnesses may
span bounded pages/reads, contingent on the owner-verified immutable record
contract. Retain only matching witness IDs, roles, turn, text digests and parsed
ACK; arbitrary transcripts/tool output are not cached. Identical boundary
overlap deduplicates. Changed IDs/content, multiple matching messages, conflicting
received/refused ACKs or conflicting turns HOLD as UNKNOWN. Detected identity
mutation/contradictory witnesses stay blocked pending separate owner review.

Partial/truncated matching evidence, incomplete page, failed read, pagination
cycle or ambiguous scope cannot qualify. Pagination remainder and omitted
unrelated events never prove absence/non-delivery; they do not negate a complete
immutable positive pair. Query cache is bounded to 32 matching witnesses.
After external reads the core rechecks current revision and receipt binding,
then atomically records its separate received-only terminal and consumed IDs.
`checked_at` is local observation time only. Source drift after admitted send
does not erase its receipt; the immutable stage binding must still hold.
Lost receipt-commit responses read back the durable terminal without another
send. The core validates structured receipt binding; origin/evidence acquisition
remain the selected owner port's responsibility. Storage is not a security
boundary against a hostile same-UID writer.

## Review and later live gates

The local tests exercise synthetic loss, replay, contention and invalid evidence;
their IDs/ACKs are fixtures. First independently review the exact source/delta.
Then the root owner must verify its actual tool contract, immutable read behavior,
authority/lease, existing target mapping and explicit ACK behavior, wire this port
and obtain a real complete receipt pair. SDK call bounds and late contradictory
provider responses also require that integration review; a terminal receipt
preserves its evidence and cannot be silently reopened. Installed/host adoption,
rollout and publication require their existing separate gates. No permission,
network control, credential or financial confirmation is relaxed by this code.
