# Finite history requalification (source candidate 116)

Use only for an existing adapter-owned imported generation whose unchanged old
history has moved to different physical stat identity. Ordinary unchanged-stat
imports keep their existing path. Requalification never publishes, edits source,
rewrites IMPORT metadata or sends an external event.

## Explicit commands

Through the existing registered workspace:

```text
agentos atlas --registry REGISTRY history-requalification-status PROJECT --operation STABLE_ID
agentos atlas --registry REGISTRY history-requalify PROJECT --operation STABLE_ID --cursor 0
agentos atlas --registry REGISTRY history-requalify PROJECT --operation STABLE_ID --cursor RETURNED_CURSOR
```

Or `import_matrix.py history-requalify --root ROOT --binding .atlas/UPSTREAM.json
--operation STABLE_ID --cursor N`. `history-requalification-status` is read-only.
Python: `history_requalification.requalify(root, operation, binding_path,
cursor=0, read_only=False)`. `operation` is 1–96 ASCII letters/digits/underscore/
hyphen, beginning with a letter/digit. Cursor is an integer from 0 to 100000;
booleans are refused. Default binding remains `.atlas/UPSTREAM.json`.

Repeat only with the exact returned cursor until `CERTIFICATE_COMPLETE`.
`PAGE_COMPLETE` is partial coverage. Retrying the last page's starting cursor
returns `PAGE_ALREADY_COMMITTED`; history payloads are not reread. A completed
duplicate verifies metadata and does not rewrite the acceptance pointer.
Read-only status returns `NOT_STARTED`, `PENDING`, `PENDING_CERTIFICATE_COMMIT`
or `CERTIFICATE_COMPLETE`; it does not create a directory or repair a pointer.

All results report `read_bytes` and fixed `read_limit=33554432` (NOT_STARTED
reports the observed bytes), cursor/count when a plan exists, plan/certificate
pins and `publication=NOT_RUN` for an existing operation. No percentage or product
acceptance is inferred. CLI exit 0 is an observed method result, 1 is REFUSED,
2 is invalid arguments. Status readbacks may refuse if the saved context became
stale; they are current-context checks, not historical status relabeling.

## Durable schemas and trust roots

Under `.atlas/history-requalification/operations/ID/`:

* `PLAN.json`: `atlas.history-requalification-plan/v1`, operation and context.
  Context pins real root identity, binding, IMPORT_STATE, exact generation
  metadata, old projection, requested current source/document hashes, complete
  history paths, old source/retained roster digest, physical guards for all
  rows, writer and optional existing checkpoint-pending identity.
* `HEAD.json`: `atlas.history-requalification-head/v1`, exact plan pin, cursor
  and ordered page pins. Only HEAD is mutable within an operation.
* `page-N.json`: `atlas.history-requalification-page/v1`, operation, plan SHA,
  contiguous start/end (maximum 64 rows), proof entries. Each entry has exact
  row index, full enclosing source pin (or null for retained-only rows), selected
  SHA, retained pin and before/after checked source/retained stat guards.
* `CERTIFICATE.json`: `atlas.history-requalification-certificate/v1`, exact plan
  pin, context SHA, whole row count, complete ordered page pins, and status.

After full coverage, `by-generation/IMPORT_STATE_SHA.json` stores
`atlas.history-requalification-pointer/v1` with operation and certificate pin.
The importer selects this exact state-derived pointer, never a caller-supplied
certificate. Certificate, plan, pages, whole coverage and rebuilt current
context/physical identities must match. All consumed proof metadata and retained
payload guards survive through the importer's final prepublication check.
A foreign accepted pointer is refused;
it is not silently replaced by a different operation.

These are integrity-checked same-owner filesystem journals, as with IMPORT_STATE.
They are not signatures or a hostile same-UID filesystem sandbox. An actor who
can rewrite all trust roots can forge local state; no cryptographic authentication
or new security principal is claimed. Symlinks, foreign paths/operations, stale
hashes, corrupt pages, invented row proofs and incomplete certificates are refused.

## Bounds, state ownership and recovery

The new API counts all metadata and payload reads together against 32 MiB per
call; files remain at most 8 MiB, metadata files at most 8 MiB, rows at most the
existing 100000 metadata capacity. Metadata hydration has an injectable bounded
reader; existing callers preserve their previous behavior. Importer certificate
metadata reads share its current source-input budget. All source/retained pairs
are preflighted whole; there is no partial digest. A call that cannot fit a pair
refuses `REQUALIFICATION_NO_PAIR_FITS_BUDGET`. Nothing raises a limit.

The complete source-origin roster and every retained-only matrix are covered.
New unimported history paths are frozen into context and remain ordinary new
inputs for the subsequent importer; they are never mislabeled as old attested
history. Changed new history bytes are still verified by normal import.

Both checkpoint source flock and IMPORT.lock exclude cooperating writers.
Every call rebuilds the plan's context, verifies before/after stat for each full
read and rechecks all guards/roster before commits. Device is an observed value,
never a constant or ignored field. Missing generation_meta_sha256 or legacy
metadata without exact retained rows is refused explicitly; no weak fallback.

Expected errors include `REQUALIFICATION_STALE_OR_FOREIGN_PLAN`,
`REQUALIFICATION_SOURCE_HASH`, `REQUALIFICATION_RETAINED_HASH`,
`REQUALIFICATION_CHANGED_DURING_READ`, `REQUALIFICATION_PAGE_PROOF`,
`REQUALIFICATION_RECEIPT_HASH`, `REQUALIFICATION_INCOMPLETE_CERTIFICATE`,
`REQUALIFICATION_CURSOR`, `CHECKPOINT_WRITER_BUSY`, and
`REQUALIFICATION_IMPORT_BUSY_OR_UNKNOWN`.

A page written before a failed HEAD commit remains
`REQUALIFICATION_UNKNOWN_PARTIAL_EFFECT`: preserve it for the owning operator;
no deletion, adoption or replay is automatic. Unknown/foreign import locks are
also preserved. A complete HEAD/certificate interrupted before acceptance-pointer
commit can resume by exact cursor after complete revalidation. No timer or
background recovery loop is installed. A foreign accepted operation or stale
context requires explicit owning-writer review, not a replacement ID or reset.

After certificate completion, the current source writer calls the existing
`checkpoint-reconcile PROJECT --operation ORIGINAL_CHECKPOINT --finish-pending`.
This may publish once. Do not create a new checkpoint/work event or resend an
external operation. Existing checkpoint `replayed=true` on subsequent reads
means cached receipt readback; compare source bytes/event ID/CURRENT to prove
there was no second source or publication effect.

For rollback, stop using the new client and preserve all journals; old tools
ignore the new subtree. Before publication, old generation/state/source bytes
are unchanged. After publication, never rewind source or discard retained
history; rollback software separately and reconcile exact state with the owner.
Installed version, live publication and semantic acceptance need separate proof.
