# Reviewed same-SID successor adoption

Cold adoption normally admits one attempt per SID. An UNKNOWN, in-flight or
unreviewed prior attempt still blocks. A successful adoption followed by a
distinct later failed dispatch needs a separate, explicit successor; resetting
the original journal or replaying an operation is never a recovery method.
The separate [pre-resume contract](SCREEN_PRE_RESUME.md) can preserve a proved
metadata-only failed root and enter its successful reviewed child through an
explicit `pre_resume_history` ref. It is not a general failed-root bypass and
does not change this contract's successful predecessor requirements.

Add `successor: {predecessor_sha256: RAW_SHA256}` to the existing adoption input.
The hash selects the exact successful current chain tip, never an arbitrary
path. Existing callers without that field retain the original SID-once refusal.
The destination is still the explicit new Screen name passed to `adopt_screen`;
the SID remains the existing native SID and the provider uses thread/resume.

The selected predecessor must have DISPATCH_OBSERVED, completed work, exact SID
and request/result consistency, accepted same-connection provider delivery and
retained startup. Its destination worker must match the current old worker's
identity, process IDs, connection, socket, bootstrap/request hashes and full
startup. The old bootstrap request therefore preserves the exact prior task;
the existing adopted_original_contract requirement retains goal, scope, known
context, acceptance and authority as historical data, with current authority
validated separately. No model, provider or permission setting is changed.

A verified `pending_reconciliation` receipt is mandatory. It must bind that
exact old worker and a different dispatch operation and completed turn from
the predecessor's work. Its original FAILED/pending/UNKNOWN records, commands
and reviewed effects stay intact. Distinct IDs alone do not prove chronology
or absence of effects: the trusted owning adapter must verify the actual
predecessor and later operation/effect relation from their qualified sources.

Every fresh adoption guard query includes a derived `successor_binding`:
predecessor raw hash, predecessor worker identity digest, old and destination
names, later operation ID, reviewed terminal turn and reconciliation receipt
hash. The held current guard must return `successor_binding_sha256` equal to
`safeio.digest` of that binding and
`predecessor_and_later_operation_reviewed: true`. The ordinary exact query,
freshness, stable owner token, actual lineage/writer exclusion, pending receipt
and reviewed terminal binding requirements also remain. These fields require
real owning observations and review; echoing a caller flag grants no authority.
Missing security/target authority continues to refuse before any real effect.

The original `state/screen-adoptions/SID.json` remains byte-identical. Under the
same existing SID lock, the successor reserves a create-only child journal at
`state/screen-adoption-successors/SID/PREDECESSOR_SHA256.json`. Its immutable
identity binds predecessor, destination and later receipt. Only this attempt
updates its own status during execution; terminal predecessors are never
rewritten. A reserved/failed/UNKNOWN child consumes its edge, even with a new
launch ID or destination name. There is no reset/delete or retry API.

The chain walk follows at most 32 canonical nodes. Each existing link binds the
raw predecessor hash. Only its current successful leaf can be selected; stale,
foreign, incomplete or conflicting nodes refuse. Once-per-predecessor edge and
the SID lock serialize competing callers and prevent forks/replay. Chain pins
are rechecked around each live guard; changed history refuses. Crash after an
edge is created requires reconciliation, never deletion to retry. This is
cooperative local storage, not a boundary against a hostile same-UID writer or
a crash-proof multi-file transaction.

Old process/lineage absence, natural worker.lock removal, current controller
exclusion, actual catalog/startup/settings readback, harmless probes, protected
READY/claim and target controls remain mandatory. The successor journal is
transport evidence only; completed delivery does not accept the business goal.
Source fixtures do not prove real security disposition or installed adoption.

An explicit `late_probe_history` reference may select a successful cold-continuation
root after reviewed late pre-work probe effects. See [SCREEN_LATE_PROBE.md](SCREEN_LATE_PROBE.md).
The continuation must independently satisfy the ordinary successful predecessor
criteria; an old late observation never becomes capability or business PASS.
