# Explicit output selection for unfinished checkpoints

Whole source identity and result byte preservation are different facts. A broad
write scope can contain complete input repositories, historical tests and local
configs. Publishing all those bytes is not required for an honest unfinished
checkpoint and can wrongly turn an archive privacy guard into a workflow stop.
This opt-in contract selects preserved result bytes explicitly; it never drops
files from source inventory or changes their hashes, scanner or permissions.

`project checkpoint --capture-selection REQUEST.json` (or JSON stdin `-`) uses
`agentos.checkpoint-capture-selection/v1` with exactly schema, root, task_id,
revision, task_sha256, project_sha256, source_sha256, authority_ref, capture_paths.
All identities pin current admitted root/task/revision, exact task/project bytes
and full source snapshot. authority_ref is a caller attestation, no grant.
1..64 unique canonical relative paths (<=1024chars each) must exist in the full
snapshot and be contained in the approved write surfaces. No root wildcard,
traversal, absolute path, missing/foreign scope or stale pin is accepted.

Only selected approved files plus all required maintained entry docs are
embedded. The unchanged scanner still checks every embedded byte, including
selected source, documents, manifest and evidence. A selected sensitive file
still refuses. Optional protected-source requests retain rc2020 rules; their
metadata references are included even outside the selection, never their bytes.
No source file is changed, moved or removed; no write path is rewritten.

`evidence/review.json` keeps the complete source snapshot and explicit selection
request. Omitted source content has a required UNKNOWN source-baseline dependency,
external_required recovery, explicit not_restored record and a selection
limitation. Local originals and earlier failed attempts remain intact. This is
an indexed unfinished CHECKPOINT, not self-contained recovery, source acceptance,
CLOSED, READY, renewed authority or business completion. Full enter/docs/READY
and actual product/runtime checks remain necessary. Completion cannot accept
this parameter. Ordinary checkpoint capture is unchanged without the opt-in.

Generate pinned requests outside source, e.g. in an owned temporary directory;
writing an input file into source after taking its snapshot correctly makes it
stale. Explicitly choose current result/document surfaces, not another workspace
or a hidden directory exclusion. If exact complete source recovery is required,
retain its authorized external baseline and verify it separately; this contract
never claims to have embedded or restored omitted code/configs.
