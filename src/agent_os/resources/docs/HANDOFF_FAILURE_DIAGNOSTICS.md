# Bounded handoff failure metadata (owner-local rc2006)

This additive diagnostic is evidence from the original attempt, not an approval,
scanner result reclassification, credential proof, or authorization to retry.
`scan_secrets` and all scanner helpers/predicates/thresholds remain unchanged.

The actual failed embedded asset put may attach `HandoffError.handoff_asset` with
asset ID and byte count. No body/match is copied. At that boundary the complete
manifest is not yet validated, so its proposed path is never echoed; direct
Library callers have null path/hash. Lifecycle alone may join the original
already checked capture path and precomputed full-asset hash.
Library signatures and original exception code remain unchanged.

At the existing project lifecycle failure boundary, an already captured and
verified full-asset hash may be joined by exact ID and byte count. The existing
payload fingerprint/source-snapshot digest, task ID/revision and task-bound
session/turn are retained only when already available. These session/turn fields
are the saved task binding, not independently observed current client startup.
Candidate ref is retained only if an actual returned/saved candidate exists.
There is no separate capture-manifest reference at this boundary: it stays null.
Specific secret subtype is not inferred; category is the original safe enum
SECRET_DETECTED and unknown fields remain null with explicit gaps.

An at-most16KiB create-only0600 receipt goes under the existing owning task:
`.agentos/tasks/TASK/diagnostics/ATTEMPT.json`. The producer never reads an asset
or blob for diagnostics and never scans a receipt. Failure to construct, write,
fsync or verify it preserves the original error and reports only optional
WRITE_FAILED_OR_UNKNOWN metadata status. No fallback sink, overwrite, task status
transition, library publication, scheduler or retry is introduced.

CLI keeps statusBLOCKED, the original error string and exit2; it may add a safe
`diagnostic` envelope containing attempt identity and receipt path/size/SHA.

Read only already saved metadata with:

```text
agentos project handoff-diagnostic --root PROJECT --task TASK --revision N [--attempt HEX32]
```

No attempt/record means METADATA_UNAVAILABLE, never reconstructed from current
source, oldREADY or current manifests. Invalid, extra-field, duplicate-key, unsafe,
symlink, nonregular, oversized, changed or wrong-identity records fail closed
without echoing input. This command reads the task record and exact receipt only;
it never invokes source_snapshot, build/capture/scanner, store objects or retry.
A missing old failure receipt cannot be recovered by installing this version.
Read-only UNAVAILABLE is a successful metadata lookup, not recovery or READY.

Same-owner local metadata has no signature or hostile-same-UID guarantee.
Installed adoption, a real operation and business acceptance require their own
reviewed target authority/evidence. Earlier refusals are never replayed or automatically changed. The native hooks remain disabled.
