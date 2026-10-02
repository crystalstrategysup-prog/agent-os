# Historical single-response cloud observation adapter

This optional adapter implements task22/OBSERVED-RECEIVED-DESIGN.md in separate
local source. It does not alter the frozen coordinator/core, v2/v3 queue or
receipt schemas, capabilities, installed0.5.5, workers, grants or credentials.
No live cloud workflow is activated. Fixture results are local proof only.

## Scope and ownership

`cloud_observed` owns a disposable journal under
`state/cloud-observed/<id>/`, separate from `state/continuations`.
`prepare(home, root, task_id, actor, pin, payload=...)` binds one explicitly
selected verified CLOSED stage and its continuation owners, then commits an
exact new challenge: ledger/operation identity, generation1, random nonce,
target/workstream, adapter/mapping hash, payload/hash and full envelope/hash.
Existing journal plus different payload HOLD; a historical request cannot be
retrofitted to an old uncertain work send. Old coordinator state is untouched.

`run(home, id, actor, expected_revision, provider)` atomically changes this
adapter's PENDING into DELIVERY_UNKNOWN before a single invocation. Subsequent
UNKNOWN runs query only; no timeout takeover, resend or NOT_SENT route exists.
The adapter's own revision CAS and stage binding gate recording. It does not
write a new coordinator receipt or claim coordinator delivery completion.
Recovery reads the journal, not a reconstructed nonce/generation. A known
terminal returns without any send/read. Lost CAS responses read back durable
state; an uncommitted old observation is never substituted for a fresh read.

Distinct local discriminator: `agentos.cloud-observed-receipt/v1`,
`evidence_kind=single_read_causal_observation`,
`acceptance_scope=observed_received_only`. Its journal terminal is
`OBSERVED_RECEIVED` or `OBSERVED_RECEIVED_REFUSED`. The earlier cached v3
contract/hash and accepted-work meanings are not reused. Receipt means that
one authenticated response exposed acknowledged input at observation time.
It proves neither current persistent contents, eternal immutability, an atomic
server snapshot, successful work, project completion nor new authority.

## Actual port trust and full text

`Provider(port, pin, verify_authority=..., verify_complete=...)` pins existing
`cloud_threads.send_message` / `cloud_threads.read` with genuine provider
identity and an optional locally inspected tool-schema hash. This adapter's
actual source SHA256 is mandatory in the pin. No new server schema field is
required, and no identity dictionary authenticates a callback. The root owner
must verify the connected tool origin, selected target/turn/role attribution,
authority/writer lease and bounded calls. The exact target must already exist.

The Python port signatures are local integration shims. Its `read` returns
`RawRead(original_response_bytes, invocation_ref=None)` for **one** actual tool
result. Serialize the original returned tool object once; do not stitch arrays,
flatten pages into one result, infer roles or substitute an editable transcript.
The optional reference is retained only if genuine. Adapter parses these bytes
itself and hashes the whole original response without persisting unrelated text.
The inspected actual response must supply `items.id/turnId/role/text`; genuine
send projection uses `threadId/turnId/admissionOutcome`. Admission is not receipt.
If actual tool result nesting differs, review that projection explicitly before
wiring; do not pass a fabricated shaped fixture as an actual tool response.

`verify_complete(raw, selected_records)` must establish complete selected text
from the actual full-record read contract/mode or reliable existing metadata.
Known truncated/partial/summary flags refuse. Absent flags alone do not establish
completeness; a hash cannot recover omitted bytes. Do not set fictional complete
or immutable fields, or use unconditional verifier callbacks in production.
No eternal immutability guarantee is required. All owner and port callbacks run
outside journal locks; synchronous port calls must enforce their own bounds.

## One-response positive proof

The complete user text equals the full precommitted
`AGENTOS_CLOUD_OBSERVED_REQUEST_V1` envelope. The complete assistant text is a
standalone final `AGENTOS_CLOUD_OBSERVED_ACK_V1` JSON object with schema
`agentos.cloud-observed-ack/v1`, scope `observed_received_only`, received/refused
status and exact ledger/operation/integer generation/nonce/request hash/target/
workstream echo. Refusal additionally names its reason. The committed request
provides precise ACK instructions. No quotes/fences, generic activity, tool or
user-authored ACK, latestTurn status or timestamps substitute for that object.

Both actual records must have distinct IDs and the same actual turn. The pair
must be unique **inside this one original response**. A known returned send turn
must match; null/lost turn may be correlated by the unique fresh challenge.
Search at most four bounded responses/pages of50, but never join their contents.
A page containing only one side creates no witness cache and cannot certify
anything. A later page may qualify only if it independently contains the entire
complete pair. Unrelated tool entries need no invented message fields. Pagination
remainder/omissions do not prove absence and need not supply total history or
cross-page atomicity. Wrong provider/target/role/turn/challenge, ambiguous or
partial pair, read failure and cycle leave UNKNOWN without resend.

Before CAS, publish an append-only hash-addressed observation retaining:
provider/tool identity, adapter/schema pins, exact challenge and request hash,
genuine available send target/turn/admission, optional real read reference,
exact selected texts/IDs/roles/turns, parsed ACK, canonical pair hash, original
response hash, local checked_at and expected journal revision. checked_at is
observation time, never fabricated producer ordering. Evidence-before-CAS
failure leaves UNKNOWN; known committed readback remains terminal. Storage
is not a security boundary against a hostile same-UID writer.

`recheck(home, id, provider)` is an optional explicit one-response owner read.
Later visible changes append a discrepancy containing hashes; omitted records
are not proof of deletion. Original observation/state is never overwritten,
reopened or invalidated. A contradictory late send result is retained separately
and appended as a discrepancy too. No future change erases the historical fact.

## Review and root receipt-only E2E

The isolated targeted suite covers mixed responses/pages, replay, full-record
refusal, wrong provider/turn/challenge, truncation, evidence/CAS faults, stale
revision, concurrency and later discrepancies. Independent source review and a
real root receipt-only canary remain pending. Root must inspect its actual
schemas/full-read mode and pin an existing authorized target/lease, using a
disposable local journal rather than the installed queue. Commit one benign
canary, send once, obtain a target final explicit ACK, then record one complete
actual response pair and repeat readback with no send. Local loss of the send
result may be simulated by discarding only its local projection, never another
send. Prior uncertain work lacking this challenge remains uncertain; a distinct
authorized canary is not a retry. Host rollout/publication remain separate gates.
