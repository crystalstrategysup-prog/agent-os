# Accepted checkpoint history in typed continuation

This opt-in contract addresses historical checkpoint publications already accepted by
the selected current indexed Library. A handoff-shaped filename alone is insufficient
proof of a pending publication. It is also insufficient proof of acceptance.

## Read-only qualification

`python -m agent_os.accepted_checkpoint_history --root ROOT --home HOME
--task-id TASK --project-id PROJECT --revision REVISION` reads a bounded exact task
metadata directory and the selected HOME/results-library. It never writes or publishes.
It returns detached references and `sha256`, not archived source/payload contents.

Only regular nonsymlink `handoff-checkpoint-<payload SHA256>.json` journals with the
exact lifecycle grammar qualify. Each must match its filename, idempotency key,
selected Library and typed manifest reference. The current Library ACL, operation
receipt and registry must independently confirm that exact candidate was accepted.
The current exact historical registry row must be accepted or superseded. Retracted or unknown publication state is HOLD even when an old operation receipt says accepted. Superseded means an accepted older checkpoint, never renewed permission. The manifest must bind the same task/project, an older task revision, active state,
checkpoint result type and exact required review payload. Required preserved object
bytes are hash-verified within a total bound. The complete journal set/bytes and
current Library identity/ACL are checked again before qualification returns.

Bounds: 256 task directory entries (existing inventory ceiling), 32 checkpoint
journals, 16 KiB per journal, 1024 required refs and 64 MiB aggregate required bytes.
Existing per-object, manifest, Library and provider bounds remain. Exceeding a bound
is HOLD; do not raise it or skip an object merely to obtain PASS.

## Opt-in request and transaction

`agentos.completed-continuation-request/v2` and
`agentos.interrupted-continuation-request/v2` each contain their corresponding
v1 fields plus exactly
`accepted_checkpoint_history_sha256`, the read-only qualification digest. The
existing request-hash-bound current authority schema is unchanged. No saved report,
ACK, caller boolean or historical permission replaces fresh core-side qualification.
The existing supported bridge accepts this request through its normal advance and
reconcile route; original provider response/wire/time limits remain unchanged.

Under existing project/turn locks, v2 requalifies before live native observation,
after that observation, and before finishing the durable transaction. A changed
journal set, digest, current ACL or unverified publication stops dependent work.
The digest excludes unrelated Library generation increments; accepted operation
identities and current ACL are still pinned. Current authority, exact task/project/
revision/source CAS remain required. Completed v2 requires the old turn completed;
interrupted v2 requires it interrupted. Both require the exact current turn
inProgress. These old-turn states are not interchangeable. Each returns its own
completed/interrupted-continuation-receipt/v2; authority v1 remains unchanged.

Only the normal nonaccepting FULL_ENTRY_REQUIRED transition is possible. Fresh
same-owner full intake preserves objective, outcome and original acceptance before
READY and exact approved checks. It never accepts the product or renews target rights.
A partial or committed operation uses existing exact-operation reconcile, not replay.
Journal files are retained byte-for-byte and historical results remain indexed.

## Compatibility, safety and limits

Completed v1, interrupted v1 and refusal-recovery defaults still reject every
handoff-prefixed entry. SECRET recovery is unchanged. Unknown/malformed/unaccepted,
missing/corrupt/foreign/unsupported journals, missing current ACL, unfinished entry
or refusal transactions and active/unknown old writers remain HOLD. Nothing scans
around or removes a failed publication. No hooks, credentials, permissions or product
data are changed. The existing same-UID cooperative filesystem trust boundary applies;
this is not a sandbox against another malicious process with the same UID.

Source tests use actual disposable Library publications and normal lifecycle APIs,
including fresh full entry/READY/check and partial-commit reconciliation. Their fake
provider is explicitly synthetic; tests do not prove installed behavior or real native
admission. The interrupted-v2 route is separately exercised through full entry, negatives,
Library-lock retention and exact partial/committed-operation reconciliation.
Actual use needs reviewed installed bytes and the selected live supported
provider in the existing owning chat. Preserve original refusals and operation history.

Current-Library consistency: qualification takes a nonblocking shared POSIX flock on the existing stable publisher.lock inode, read-only without creating it. It cooperates with the Library exclusive publisher lock. The continuation transaction retains this shared lock only for its final post-observer qualification and metadata commit/reconciliation, never while calling the native provider. Busy/unsupported/missing lock is HOLD. Unrelated generation changes between qualifications remain admissible; concurrent publication during the brief final commit follows the existing GENERATION_CONFLICT behavior. No lock is deleted or replaced.
