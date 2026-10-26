# Native source relocation

Source candidate 0.8.0rc2031; installation and adoption are separate.
Contract `atlas.source-relocation/v1` updates a registered natural Markdown
entry while preserving historical logical document/artifact identity and bytes.
Only native projects with output inside the selected root are supported.
No project/global policy, host, credentials, database, production or extra-writer
authority follows from the method. The caller must independently verify current
authority for the exact root and replacement; registration is not approval.

## Preserved identity

Old records keep ID, logical path, SHA, length, source/readback and evidence.
They gain a distinct `storage` descriptor bound to retained bytes, request and
immutable anchor; old documents become archived and a distinct current alias
represents the natural entry. Accepted basis/decisions stay unchanged. The
method renews no activity, tests, semantic acceptance or permissions. Unsupported
receipt consumers, foreign writers and incomplete pin closure are refused.
Ordinary `HISTORICAL_MEMBER_REWRITE` stays strict.

## API

The selected verified candidate supports `agentos atlas source-relocate ACTION`
and standalone `atlas.py source-relocate ACTION`. Native routing requires an
explicit root, without workspace-registry discovery. Request JSON is a regular
bounded file or `-` for stdin. No source body appears in CLI plan output.

* `plan --root ROOT --request FILE`: selected reads and disposable preview only;
  returns full-plan/request hashes, changed-path hashes and preview identities.
* `apply --root ROOT --request FILE --expected-plan SHA`: recomputes the exact
  plan, locks the existing publisher, checks head and every preimage, then
  journals/applies/verifies only that transition.
* `status --root ROOT --operation ID --expected-plan SHA`: read-only exact
  journal/file-state observation, including incomplete preparation.
* `reconcile --root ROOT --operation ID --expected-plan SHA`: resumes only the
  same pinned operation. `--rollback` restores only unpublished explained source
  states, keeping retained objects/journals. Published reversal needs a separate
  authorized successor. Committed historical operations are never replayed.

Exact request fields:

```
schema, operation_id, root, project_path, output, project_id, writer,
authority_ref, at, valid_until,
expected:{release,manifest_sha256,project_sha256,source_sha256},
entries:[{path,before:{sha256,bytes},replacement_document,
          replacement:{path,sha256,bytes}}]
```

Operation ID is 32 lowercase hex characters. The exact root is absolute; entry
and replacement are distinct safe relative `.md` files. Root/selected symlinks
are refused. Limits: eight entries, 256 rows, 64 KiB request, 16 MiB full plan,
24 KiB CLI metadata. Unknown/over-limit input holds rather than raising limits.
Input `at`/`valid_until` is an aware positive window of at most 15 minutes.
This freshness window is not an invented lifetime of the owner's permission.

## Recovery and current authority

`PENDING` blocks ordinary native loads/publication during partial changes.
Create-only files publish atomically. Preparation is rebuilt only from the same
original request, unchanged source/head and expected plan hash. If reservation
did not retain the request, pass that exact request through reconcile's
`--request`; foreign/unknown content is never adopted. Recovery re-derives the
permitted rows from the immutable anchor and pinned images, rejecting arbitrary
selected-source rewrites even when a caller recomputes a forged plan hash.

`--stale-lock-sha256` qualifies only this exact operation lock and a demonstrably
absent owner PID. Active/unknown/foreign/changed locks hold; age alone grants
nothing. A live lease spans source CAS, publication and verification. This is
coordination among cooperating writers, not protection against hostile same-UID
IO or an OS transaction. No archived command/body is executed.

An operation-owned orphan release may finish only through a live typed proof
matching the plan, after-images, original head, authority and exact preview
release/manifest/snapshot. No public JSON flag relaxes default
`ORPHAN_RECONCILE_ONLY`.

An expired invocation requires revalidated current scope, not mutation of its
old request. `--authorization FILE` accepts exact
`atlas.source-relocation-reconcile/v1` fields:

```
schema, operation_id, root, project_id, writer, authority_ref,
authorization_ref, plan_sha256, action, at, valid_until,
expected:{release,manifest_sha256}
```

Action is `resume` or `rollback`. Identity/scope/plan must match; the current
head must match this attestation and the operation's before/after states. Fresh
aware validity is at most 15 minutes. `authorization_ref` identifies separately
verified current authority: reuse a still-valid owner instruction after checking
scope, validity and revocation; a process/session change alone needs no new
owner approval. Expired/revoked rights or changed scope never renew implicitly.
Original requests remain immutable; fresh attestations are separately retained.
Historical attestations grant no current authority.

## Restoration and acceptance limits

Restore needs the retained bytes, operation journal and original publication;
a presentation snapshot alone is not a complete source-project backup. Only
affected metadata/images are retained, not whole snapshot copies or chat history.
No broad cleanup is implemented. New storage descriptors require this successor;
older consumers fail closed and must not be treated as compatible after adoption.

Repeated updates include only explicitly referenced prior operation proofs in
their disposable preview, not an unbounded history scan. Duplicate members are
copied once and the total temporary bytes stay within the existing combined
source/snapshot/HTML envelope. No full snapshot copy is stored in the operation
journal. Normal historical reads verify the relevant pinned proofs; this is not
a causal context/time savings claim.

`COMMITTED` verifies the mechanical migration only. It accepts neither new
instructions nor the whole project, runtime, delivery or business result. Old
logical paths stay provenance; validated snapshot `storage` names their separate
physical bytes. Browser/UI and real-project adoption require their own evidence.

A durable terminal receipt and a leftover `PENDING` need cleanup only. Reconcile
validates the original receipt (including its historical authority proof), exact
operation/plan, current head, source and toolchain under the existing writer
lease. COMMITTED requires the exact after-head and all after-images; unpublished
rollback cleanup requires original preimages/head and preserves retained objects.
A fresh same-scope cleanup attestation is stored separately. The original receipt
bytes and original authority pin are never replaced with the new attestation.
Cleanup returns the stored terminal result with `replayed:false`; it neither
replaces source nor republishes. Changed head/scope/receipt/source/pending proof
remains HOLD. A stored terminal receipt never authorizes restoration of its old
result over a different current head.
