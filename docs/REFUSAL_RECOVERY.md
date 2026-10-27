# Explicit refusal recovery: metadata disposition, not result acceptance

Version rc2009. Local same-owner, cooperative filesystem contract. No automatic
retry, background worker, source capture, scan, library operation or cleanup.
Original refusal and pre-journal partial objects remain UNKNOWN where unknown.
A generic SECRET_DETECTED is not evidence that a real credential was present.

## Separate A, B and C

A: `project refusal-acknowledge --root ROOT --task TASK --request FILE --permit FILE`
requires a definitive pinned legacy `{status: BLOCKED, error:
handoff_acceptance_failed:SECRET_DETECTED}` witness, exit2 attested in the exact
request. The task must be VERIFYING, bound to the expected existing home/session/
root/turn/project/revision and have no checkpoint/closeout or normal handoff
checkpoint/completion journal. Admission lists at most256 names in the exact task
metadata directory and refuses every handoff-shaped record, including uncertain
ones, without opening journal bodies or source/library objects. It changes only workflow status to RECOVERY_REQUIRED, answer
revision unchanged, retaining historical ready/checks. It records immutable
metadata request/authority witness references, pre/postimages, receipt and event.
It does NOT create an accepted handoff, CHECKPOINT, CLOSED, READY or authority to
retry. No source_snapshot, source/body/hash reread, scanner/capture, library
create/get/put/reconcile/publish is called. Existing source/scanner limits are not
changed. Exact witness root/path is separately owner-attested in request scope;
this explicit bounded metadata input is not a new project/executor root.

B: ordinary `project next-turn` accepts optional `--recovery-request FILE
--recovery-permit FILE` ONLY for RECOVERY_REQUIRED. Same root/task/session and
exact committed A/request, revision, project/task/binding CAS are required.
The permit's observed true current turn must be different from the old bound
turn. A separately journaled metadata transaction writes the existing standalone
binding to INTAKE_REQUIRED and an immutable ADVANCED receipt binding its
consumption/target. It leaves task RECOVERY_REQUIRED; no READY/result acceptance.
Normal next-turn for CLOSED/CHECKPOINT retains its original branch and controls.

C: `project enter --resume-task` remains ordinary full-answers admission. For
RECOVERY_REQUIRED ONLY, under project then user-turn locks, it verifies exact
committed B, task/revision/recovery-op/project/request, ack+permit hashes and true
new binding and exact reviewed next_scope.write_paths before ANY answers/docs/status write. A-only direct resume refuses
even if the old turn still matches. Missing/partial/mismatched B refuses. Valid C
increments revision, records CONSUMED with resumed_revision/entered_turn_id,
invalidates old ready/checks and binds normal entry. Subsequent ordinary entry
is ordinary scope revision, not another recovery consumption. Old receipts stay
historical. A changed target turn after B needs review; no automatic rebinding.
Fresh docs and normal READY/read inventory are separate. Original whole-root
source_snapshot scope remains; A/B never grant that read authority.

## Request and explicit permit

New documents <=16384 bytes, existing task metadata under unchanged safeio4MiB
ceiling. Strict object fields, duplicate/extra/malformed/recursive JSON and
unsafe/symlink/nonregular/oversize inputs fail with fixed sanitized errors.

`agentos.refusal-recovery-request/v1` has exactly schema, root, user_home,
operation_id (new32hex recovery identity), actor_id, session_id, project_id,
task_id, revision, expected, witness, goal, next_owner, next_scope.
- expected: task_sha256, project_sha256, turn_sha256, bound_turn_id, status=VERIFYING.
- witness: canonical root, relative path, bytes, sha256, kind=owner_attested_legacy,
  attempt_id=null, exit_code=2. No old attempt ID or failing asset is reconstructed.
- goal: state=OPEN, ref, sha256. Full original goal is retained by referenced owner
  task/context, not arbitrary body text in a new diagnostic.
- next_scope: ref, explicit same-root write_paths; no effect approval inherited.

`agentos.refusal-recovery-permit/v1` fields: schema, owner_attested=true,
decision_ref/decision_sha256, actor_id/session_id, current_turn_id, observed_at,
observation_ref, valid_from, valid_until (null allowed when owner supplied no
expiry), revoked=false, root/project_id/task_id/revision/operation_id,
request_sha256, phase=ack|advance|reconcile, receipt_sha256, journal_sha256.
Advance requires exact ack digest; reconcile requires exact pending journal
digest. Observations must be UTC, nonfuture and <=900seconds old. Actor, identity,
scope and hashes must match. No expiry/signature/human observation is invented.

These are explicitly OWNER-ATTESTED local inputs. Core checks form, exact scope,
CAS and freshness, NOT human authentication or truth of a native observation.
The existing trusted executor/owner must independently verify source authority,
actual identity, revocation and target before supplying permits. A copied path,
hash, capsule, boolean or receipt alone does not grant authority. No private
profile/provider/signer, credentials, security-policy or permission change is
introduced. Synthetic permits in tests authorize only synthetic fixtures.

## Transactions and unknown outcomes

Project lock then existing user-turn lock; no nested reacquisition in C. Existing
entry journal, recovery reservation OR complete recovery transaction blocks normal
entry/READY/check/terminal work. Before any request/permit/preimage preparation,
A/B atomically reserve `.agentos/refusal-recovery-pending/` and sync its parent,
then persist bounded operation identity. Any subsequent ambiguous I/O outcome
remains fail-closed even if no request or complete journal was saved. If the first
atomic mkdir fails and readback proves no reservation/preparation exists, the
result is recovery_preparation_not_started, not UNKNOWN. No ordinary gate is
released for an UNKNOWN incomplete preparation. Task metadata and exact standalone binding are CAS protected.
Only fixed metadata target labels are admitted. Request, phase permits and
pre/postimages are create-only0600, bounded, file+directory synced and read back.
A global project recovery journal lists exact before/after hashes/sizes. The
reservation is released only after all semantic postimages are read back; the
complete journal remains as a gate until reservation release is synced. Crash
between either signal release is explicitly reconciled from that exact complete
journal, never by deleting incomplete preparation. No
arbitrary path from a journal is executed. Semantic postimages and original
permit hash are verified before applying/finishing them.

`project refusal-status --root ROOT --task TASK --operation HEX32` is read-only,
no locks/writes/repair, source or library discovery. It returns exact metadata
states METADATA_UNAVAILABLE, UNKNOWN, PREPARED, ACKNOWLEDGED or ADVANCED. Committed
receipt readback is explicitly historical; it never says current task READY.
Partially prepared B retains UNKNOWN/unknown_phase=advance even when A is known.
No-attempt metadata is unavailable, never proof zero old object writes.

`project refusal-reconcile ... --request FILE --permit FILE` is a SEPARATE
explicitly authorized action for an exact existing pending journal. It only
applies those fixed staged metadata postimages if every target is still before
or after, and project/other binding/task CAS matches. It never re-executes the
original checkpoint. Same ID/request returns historical committed receipts;
different request is conflict. Incomplete preparation with no complete journal
is UNKNOWN and stops for owner review, not a new original attempt or cleanup.
A real process crash can leave existing cooperative locks. Status remains
read-only; reconcile preserves the existing stale-lock refusal until an owner
resolves it through the target's existing authorized procedure. No force or
lock deletion is implemented. Postimage/durability uncertainty stays UNKNOWN.

## Refusals, compatibility and adoption

New status blocks oldREADY via unchanged check_ready status predicate. Checkpoint
on RECOVERY_REQUIRED refuses before deliver. Scanner/handoff/source and all
ordinary nonrecovery admission controls remain unchanged. Reader-local
RecursionError handling preserves diagnostic_receipt_invalid/BLOCKED/exit2 on
Python>=3.11; no global exception catch is expanded.

This source does not install/adopt anything. Exact wheel review, managed plan,
current target/CAS and owner scope precede actual A/B/C. No real original failure
is retried merely for diagnostics. Old binaries do not understand the new
workflow protocol: rollback to a pre-recovery core is only a pre-A/B option.
After actual recovery metadata exists, retain the compatible core and use
reviewed forward repair; the unchanged generic installer cannot certify this
new task-state rollback compatibility. Do not claim its old guards do so.


## Shipped schemas and typed identities

Bundled project-task-v1 and project-event-v1 schemas retain all legacy enum values
and bounds and add RECOVERY_REQUIRED / REFUSAL_ACKNOWLEDGED. The new task status
requires typed recovery metadata; the new event details require exact operation/
witness digest/OPEN/UNKNOWN fields. C's CONSUMED metadata is also described.
Actual complete public fixture postimages are validated against these schemas.
Production dependencies are unchanged. A transparent test-only stdlib evaluator
checks every keyword used in these exact schemas and fails on unsupported
vocabulary; it is not advertised as a general Draft2020 implementation.

Permit and receipt revision identity uses strict Python int/range checks (JSON
boolean true cannot equal revision1); new receipt booleans are checked by identity.
Legacy task revision bounds and other global parser/acceptance predicates remain
unchanged. No diagnostics contain credential values or infer literal credentials.


## Operator turn-boundary protocol

A is separately reviewed and executed. After installed candidate/current pins and
the actual ACK are reviewed, the owner/coordinator may issue one immutable exact
authority/target/effect algorithm for B through C, normal new READY and the fully
approved tail. The same approved executor observes its ACTUAL native session/
turn before starting; it may mechanically materialize the permit's current turn,
fresh observation/time, canonical request hash and actual ACK SHA from supported
proof under that already issued algorithm. This is not new authority or crypto
authentication. B, C, new READY and that entire approved tail must finish in ONE
observed native turn, without a follow-up/Root message or fabricated future turn
between them. Drift, interruption/turn change or any guard/UNKNOWN stops the
pipeline for owned review; there is no automatic replay or permissive rebinding.
Installation and any real recovery still require their separate exact reviews;
this document alone never authorizes a permit or operation.


## Typed staged semantics before any target write

Every staged task/turn/ack/advance postimage is parsed and compared with its
expected postimage using canonical typed JSON bytes BEFORE the first fixed target
write. Python dict equality and mathematical JSON Schema integer equivalence are
not sufficient: bool/int/float substitutions (true versus1,2.0 versus2,0 versus
false) are refused. Canonical key order and harmless whitespace remain allowed;
raw postimage/dependent hashes must still match the exact journal. A malformed
staged postimage leaves all targets, pending reservation and journal unchanged;
there is no implicit repair, cleanup, acceptance or original-operation replay.


## Modern SAVED witness extension (SOURCE R0)

The separate request `agentos.refusal-recovery-request/v2` supports exactly
`witness.kind=owner_attested_modern_v1`, with a known 32hex attempt_id and
`witness.diagnostic={path,bytes,sha256}`. All other request fields and current
permit/exit2/state/CAS/locks/authority requirements remain mandatory. The v1
legacy request keeps its exact shape and null attempt. Never strip a modern
envelope or fabricate an older attestation. Core cannot authenticate human
attestation or discover a deliberately hidden modern witness.

A pins and parses the WHOLE original status/error/diagnostic JSON. Its diagnostic
envelope must satisfy the existing producer v1 schema and declare SAVED, the
known attempt and the identical diagnostic reference. The only additional read
is that bounded exact `.agentos/tasks/TASK/diagnostics/ATTEMPT.json` metadata
record under the admitted root. Raw hash/length and existing typed receipt must
match exact task/revision/session/old-bound-turn/attempt. Null/mismatched IDs,
unsafe/symlink paths, unknown/missing metadata and malformed fields fail before
reservation or fixed writes. Nothing follows asset/candidate/source references;
no scanner, capture or library port is called. Unknown diagnostic outcome is
not promoted to SAVED and does not qualify for A.

V2 ack/advance/result and task recovery use
`agentos.refusal-recovery-receipt/v2`. They retain original_attempt_id and
diagnostic_receipt; the acknowledgement event carries the same fields and v2
schema. The exact pinned request binds the original whole witness. Fixed staged
postimages and reconcile enforce the same typed values. B/C consume committed
metadata only and do not reread source/witness/diagnostic bytes. C retains these
fields in CONSUMED and still requires full answers and a fresh normal READY.
Task/event schema legacy branches remain exact; a separate v2 branch describes
modern metadata. V1 request/receipt/permit/journal consumers are not silently
upgraded. Request-hash-bound existing fixed transaction journals remain v1.

This extension is an isolated source candidate, not installed/adopted proof.
Actual A/B/C and installation need separate reviewed authorization and current
readback. Retain compatible readers after v2 metadata activation; the generic
installer cannot certify rollback of this additional workflow schema. All
operator-turn rules, original refusals and UNKNOWN partial-object boundaries
above remain in force.


## Standalone session-label compatibility

Workflow session_id uses the same bounded domain as ordinary project.enter and
turns.turn_path: safeio.nonempty(value, "session_id", 200). The exact raw string
is retained, including permitted whitespace/Unicode; the stripped validator
return is intentionally not assigned. Existing UUID sessions remain supported.
No native chat UUID is substituted for a standalone workflow label.

turn_path still uses the digest of canonical JSON of the raw session string,
under the fixed state/turns directory and within containment. Opaque session
labels are never interpreted as paths. This changes only session validation;
bound/current/target turn UUID grammar, actor/operation grammar, request/permit
identity equality, CAS, modern whole-witness/diagnostic requirements, legacy
branch, typed staged postimages, reservation/journal/UNKNOWN and scanner/source
limits remain unchanged. Existing session labels are not normalized or migrated.


## Exact scope list capacity

Recovery accepts 1–64 distinct explicit next_scope.write_paths. The previous
32-entry metadata ceiling could not represent an otherwise valid ordinary
project entry with 53 explicitly reviewed paths. This finite capacity increase
does not authorize any path or permit parent-directory/wildcard substitution.
Each path retains its existing 512-character limit and containment checks.
The complete request and permit remain bounded by 16 KiB; consequently some
64-path lists can still exceed the byte ceiling and are refused.
Ordinary resume still requires the exact reviewed list (order-insensitive only),
with unchanged authority, CAS, witness, turn, journal, locks and UNKNOWN guards.
Source inventory, scanner and result-library capacities are unchanged.


## Workflow/native identity v3 — source-only candidate

`agentos.refusal-recovery-request/v3` is a separate modern-witness branch.
V1/v2 requirements, UUID grammar and receipt shapes remain unchanged. V3 retains
all v2 request fields and adds exactly `native_origin`: `thread_id` and `turn_id`
are canonical lowercase native UUIDs; `observation_ref` is a bounded short reference
and `observation_sha256` is its exact evidence digest. The operator independently
checks the historical mapping from this native origin to the exact task/witness.
The whole request hash binds that mapping, expected metadata CAS and whole witness.
References/hashes do not authenticate a human, provider, callable or historical
mapping and are not permission to fetch referenced private contents.

Only v3 `expected.bound_turn_id` uses ordinary entry's nonempty string domain
(maximum200characters). Its raw value is NEVER normalized, migrated or substituted.
Task, existing standalone binding and saved modern diagnostic must still match it
literally. Producer diagnostic grammar is unchanged; a workflow label unsupported
by a SAVED whole diagnostic does not qualify merely because entry accepted it.
Native current/target turns remain strict UUIDs. B compares the current UUID to
`native_origin.turn_id`, never to the opaque workflow label.

First v3 A/B and reconcile require a selected existing `SupportedReadThreadObserver` bridge
(`interrupted_continuation.py`). The embedding passes it via `observer=` to
`refusal_recovery.acknowledge/advance/reconcile`, or `recovery_observer=` to
`project.next_turn`. No observer is selected by default; ordinary CLI requests
without it refuse BEFORE reservation/fixed writes. A caller JSON document is not
accepted as proof of a tool call. The trusted embedding verifies the callable's
actual supported-tool origin and retains its primary observation with the permit.
No new provider, RPC, worker, credentials or security policy is introduced.

The bridge retains its existing byte/page/turn/time bounds. V3 checks exact native
thread/cwd/request/session/origin/current metadata and <=120second nonfuture
observation. Current must be inProgress. A may use the still-current origin; if
current differs, origin must already be completed/interrupted. B always requires
a different current native UUID and inactive origin. All project/task/binding
CAS preimages and permit validity are rechecked after the observer call and before preparation.
A rechecks the bounded whole witness/diagnostic pins after that call; B/C do not
reread those historical bytes. Committed replay and status remain historical
metadata readbacks, not a fresh native observation or new effect authority.
An unknown/stale/missing/mismatched native observation refuses without writes.
Truth of historical origin-to-witness mapping and owner authority remain separate
operator checks, not a claim that source fixture PASS authenticates native work.

V3 uses `agentos.refusal-recovery-receipt/v3` in task recovery, ack, advance and
results. It carries the same original attempt and diagnostic reference as v2,
plus the exact native_origin descriptor. The acknowledgement event has a separate
v3 schema branch. Old v1/v2 schema branches remain byte-equivalent values.
Existing request-hash-bound transaction journals remain v1 with exact typed
postimage checks. Modern witness/envelope/diagnostic formats and readers are
unchanged; no legacy downgrade or source/scanner/library operation is introduced.

V3 reconcile only finishes the exact admitted staged metadata, with a fresh
supported native observation and all existing journal/CAS checks. For an interrupted
B, the real current UUID must still equal the original B target; changed native
turn requires owned review and is never silently rebound. No original checkpoint
or side effect is replayed. Incomplete pre-journal preparation remains UNKNOWN.

C still requires committed B, the exact original request and scope, unchanged
metadata CAS and its exact target turn. A-only resume refuses. C increments the
ordinary answer revision and invalidates old readiness/checks. New ordinary READY
and any authorized tail are separate. V3 metadata requires a v3-capable reader;
no generic installer/rollback compatibility is inferred after real activation.
This source candidate is not managed adoption or actual recovery qualification.
