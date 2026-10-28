# Atlas 1.0 — data and executable interface

Contents: [sources](#sources), [commands](#commands), [work](#work),
[evidence](#evidence), [patches](#patches), [completeness](#completeness),
[history](#history), [boundaries](#boundaries).

## Sources

`scripts/atlas.py` is the local implementation. `navigator.py` DN-01.2 preserves
documents and their versions. The adjacent JSON schemas are the exact structural
contract: `atlas.project.schema.json`, `atlas.work.schema.json`,
`atlas.inventory.schema.json`, and `navigator.schema.json`. Python functions
check semantic constraints. A fixed supported subset of JSON Schema is used
without an external library. Extend the schema and runtime together. Unknown
fields are refused.

`<project>/.atlas/project.json` selects the document manifest and specific work
files. Project files remain canonical. Atlas does not appoint itself writer of
an existing matrix. `mode=native` means authoritative Atlas records;
`mode=projection` means a normalized projection of the canonical matrix,
published by its existing writer.

Material project fields:

| Field | Meaning |
|---|---|
| `id`, `title`, `objective` | Stable ID, title, and objective. The ID matches the documentary manifest. |
| `authority_ref`, `writer`, `source_ref` | Basis for the work, integration owner, and provenance. These are declarations, not new authority. |
| `mode`, `scope_note` | Authoritative/projection mode and exact scope/unknowns. |
| `documents` | `{path, sha256, bytes}` for the selected `docs-navigator.input/v1`. Paths are relative to the project root. |
| `work_files` | Explicit list of `atlas.work/v1` files; a separate writer for each file. |
| `coverage` | Optional pinned inventory and bindings; absence produces UNKNOWN. |
| `matrix_history` | Optional external matrix versions: ID, time, source, FULL_MATRIX/REFS_ONLY, and pinned file. |
| `projection_archive` | Projection only: exact previous release/manifest, relative output, and cumulative matrix version count. Current `matrix_history` then contains the new page. |

All JSON inputs are UTF-8 without duplicate keys or nonfinite numbers.
Document bodies permit JSON/MD/TXT/YAML; Markdown/YAML render as safe text.
Artifact/receipt bytes are hashed and not executed; their extension proves
neither their type nor content safety.

## Commands

Python 3.11+ and the standard library are required. Node is needed only for DOM
tests. Substitute exact valid paths in `atlas_tool`, `atlas_project`, and
`atlas_output`. Do not use `$HOME` as a task variable.

```bash
python3 -B "$atlas_tool" init --root "$atlas_project" --project-id PROJECT-ID --title "Title" --objective "Project outcome" --writer ACTOR-ID --authority-ref "Original assignment" --mode native
python3 -B "$atlas_tool" run session-start --root "$atlas_project" --work WORK-ID
python3 -B "$atlas_tool" run finish-block --root "$atlas_project" --output "$atlas_output"
python3 -B "$atlas_tool" run integrate --root "$atlas_project" --output "$atlas_output"
python3 -B "$atlas_tool" run reconcile --root "$atlas_project" --output "$atlas_output"
python3 -B "$atlas_tool" run project-audit --root "$atlas_project"
```

`init --mode projection` is suitable for a separate, manually maintained projection
of an existing authoritative matrix. For the automatic upstream adapter, create
its explicit binding first and call `import_matrix.py refresh` according to
[upstream-adapter.md](upstream-adapter.md); do not call `init` beforehand: the
adapter does not take over another writer's existing `project.json`. `init` itself
creates only a previously absent `.atlas`: an objective, one bootstrap work item,
a documentary index, and an incomplete inventory of six domains. It overwrites
nothing. A repeat returns `ATLAS_ALREADY_EXISTS_RECONCILE`; continue the existing
binding. This prepares control records; it does not automatically document an
unknown implementation.

`finish-block` and `integrate` call the same local `cycle`. Before the call, the
implementer saves a substantive delta in their record and affected documents;
for a shared matrix, its writer does this. The CLI does not invent an outcome,
checks, roles, or events, or apply a patch to sources. It reads pinned inputs,
checks schema/bytes/links/acceptance/history, and publishes a local immutable
snapshot through a writer lock and comparison of the expected previous manifest
before replacing CURRENT. This protection requires all writers to follow the
writer protocol; it is not an atomic OS compare-and-replace against an external
process ignoring the lock. `NO_CHANGE` creates no event or new version.

`session-start` with `--work` includes the exact work packet and linked
module/contract/doc references. Without `--work`, it returns state and next
actions for work selection. BLOCKED does not become permission to execute the
blocked step. `reconcile` verifies the latest local release; remote UNKNOWN
requires exact `operation_get` from the declared adapter, not a repeat command.

Additional primitives:

```bash
python3 -B "$atlas_tool" validate --root "$atlas_project" --at 2026-10-17T04:00:00Z
python3 -B "$atlas_tool" basis --root "$atlas_project"
python3 -B "$atlas_tool" packet --root "$atlas_project" --work WORK-ID
python3 -B "$atlas_tool" pins --root "$atlas_project" --path docs/contract.md --path receipts/check.json
python3 -B "$atlas_tool" impact --root "$atlas_project" --changed src/module.py --changed .atlas/work/WORK-ID.json
python3 -B "$atlas_tool" discover --root "$atlas_project" --under docs/contracts
python3 -B "$atlas_tool" coverage --root "$atlas_project"
python3 -B "$atlas_tool" history --output "$atlas_output"
python3 -B "$atlas_tool" history --output "$atlas_output" --limit 10
python3 -B "$atlas_tool" history --output "$atlas_output" --limit 10 --cursor "$atlas_history_cursor"
python3 -B "$atlas_tool" diff --output "$atlas_output" --before RELEASE-A --after RELEASE-B
python3 -B "$atlas_tool" methods
```

`--project` defaults to `.atlas/project.json`. By default, read-only commands
calculate freshness at the time of one run; `--at` pins a point in time for
reproduction. This is not an updated source readback. `basis` returns a hash of
declared fields, not a conclusion that a criterion is satisfied. `impact` also
works when files have already changed: it compares declared paths/scopes and
propagates impact through dependencies; it does not claim completeness of unknown
semantic relations. `discover` reads content only for already registered
documents; it returns name/size for new candidates. It does not traverse arbitrary
hidden/administrative/secret directories; name the traversal root explicitly.

`cycle` accepts `--release ID`, `--at UTC`, and `--previous MANIFEST_SHA`. Without
these, it uses a content/toolchain-bound ID, read-current, and previous manifest
verification under the shared output writer lock. If inputs and tool version
match, it returns `NO_CHANGE`; repeating an explicitly named existing release
verifies its full bytes. Low-level `build` requires an explicit ID and time:

```bash
python3 -B "$atlas_tool" build --root "$atlas_project" --output "$atlas_output" --release RELEASE-ID --at 2026-10-17T04:00:00Z --previous EXACT-SHA256
```

Omit `--previous` for genesis. An orphan or lost CURRENT does not become a new
genesis. CLI exit codes: 0 for a completed local operation; 1 for controlled
`REFUSED`; 2 for invalid argparse argument structure.

## Work

A complete small example is in `public/examples/workflow/.atlas/work/` in the
distribution. Create every required field from the schema/example rather than guessing.

A record links `id`, `parent_id`, `title`, `objective`, expected `outcome`,
`criteria`, `state`, `writer`, `assigned_to`, `write_scope`, `depends_on`,
`artifacts`, `evidence`, `acceptance`, `activity`, `blocker`, actual `result`,
`remaining`, `next_action`, and `events`. An empty list means no records; `null`
means the object is absent; the string UNKNOWN means an unknown value. UNKNOWN
is not proven absence of an implementation.

`criteria`: `{id, text, required_scope, artifact_ids}`. All criteria are mandatory;
for an optional check, create evidence rather than a mandatory criterion.
`ACTIVITY` is not an acceptance scope. ACCEPTED requires all criteria and an
actual result. A local SOURCE/TEST deliverable can be completed without a runtime criterion.

States: PLANNED, DOING, REVIEW, ACCEPTED, BLOCKED, PAUSED, CANCELLED, UNKNOWN.
The latest typed STARTED/RESUMED/REVIEWED/ACCEPTED/BLOCKED/PAUSED/CANCELLED/REOPEN
event must match the current state. REOPEN returns PLANNED; a new execution then
requires STARTED. RESULT/IMPLEMENTED describe a result; they do not themselves
accept the work. A parent has no activity or write_scope of its own; its content
is divided into leaf work items. A parent with unfinished children cannot be accepted.

`write_scope`: exact relative files or directories with a trailing `/`.
Globs, absolute paths, `..`, and ambiguous separators are refused. Overlapping
scopes of two DOING/REVIEW work items are forbidden even for one actor: the block
must be serialized or combined. A reader gains no write scope from a document
reference. DOING/ACCEPTED require ACCEPTED dependencies. Parent trees and work
dependencies contain no cycles; the architectural module dependency graph in DN
may contain a cycle as a documentary fact and is not presented as execution order.

`events` preserve ID, time with timezone, actor, kind, summary, and evidence_ids.
The prior prefix is immutable. A record change requires a new event; HANDOFF is
required for a writer/assigned_to change; REOPEN for resuming ACCEPTED/CANCELLED
work. Changing project control fields requires PROJECT_CHANGED/HANDOFF; a change
between native/projection uses a separate explicit migration preserving the prior
lineage, not an ordinary release.

## Evidence

Evidence contains `id`, `check_id`, `scope`, `subjects=[{artifact_id,sha256}]`,
`environment`, `actor`, `at`, `receipt={path,sha256,bytes}`, and
`result=PASS|FAIL|UNKNOWN`. Scopes: DOCUMENTARY, SOURCE, TEST, RUNTIME, DELIVERY,
OWNER_ACCEPTANCE, ACTIVITY. They do not form an interchangeable ladder.
Command text inside a receipt is data.

Acceptance: `{criterion_id,decision,actor,at,evidence_ids,basis_sha256}`.
The basis binds ID/objective/outcome/criteria to artifact identity/path/hash/role
and patch target, base, and selectors. Status, clocks, activity, evidence, and
events are excluded. A criterion or bytes cannot be changed while carrying the
old decision forward. The old decision remains in history; a new one is recorded
in the next row. An UNKNOWN reviewer does not yield ACCEPTED. PASS in the required
scope must cover every artifact subject for that criterion. A later FAIL/UNKNOWN
for the same check, subjects, and environment contradicts applicability of earlier
successful acceptance until resolved/reconciled. Repeating an identical check
requires `repeat_reason`. Different `check_id` values are not treated as a repeat
of the same check.

`activity={actor,observed_at,valid_until,evidence_id}` is allowed on a DOING leaf.
It requires ACTIVITY/PASS evidence for the same actor and `work_id`; its `at` and
`valid_until` match the activity. The window is at most one hour and does not
start before the current STARTED, RESUMED, REOPEN, or HANDOFF. A project can choose
a shorter duration. An old receipt cannot be revived with a new expiry; new
actually observed proof is required. After expiry, the state is EXPIRED/UNKNOWN
and ownership is preserved. Freshness is a bounded claim based on an observation,
not continuous process monitoring.

## Patches

Artifact: `{id,path,sha256,bytes,role,entity_ids}`. `role` = input/output/reference/patch.
A patch requires `{target_id,base_sha256,selectors,state,decision_evidence_ids,
result_artifact_id}`. Its target is an artifact in the same work item, pinned by
exact base bytes. Selectors are explicit addresses such as `/parameters/limit`;
`/` means the entire document. Do not claim automatic semantic applicability of
patch contents.

States: PROPOSED, ACCEPTED_UNAPPLIED, APPLIED, REJECTED, SUPERSEDED.
ACCEPTED_UNAPPLIED requires DOCUMENTARY/PASS for patch+base. APPLIED additionally
requires a separate output artifact and SOURCE/RUNTIME readback for patch+base+result.
For other states, result_artifact_id=null. SOURCE application does not prove
production deployment. Two accepted patches against the same base/path with
overlapping selectors require explicit reconciliation; filename and later date
do not establish priority.

## Completeness

An inventory specifies source_ref, observed_at, scope_note, and domains: goals,
modules, contracts, documents, source, works. A domain has stable item IDs, an
exhaustive flag, and explicit exclusions with reasons. Coverage links each
inventory record to documentary entities and/or work IDs.

An open work item to write a document is not a written document. For works,
coverage checks the specific work item; other domains require documentary
bindings. Gaps yield PARTIAL; missing inventory yields UNKNOWN. COMPLETE means
completeness only relative to this explicitly pinned inventory and its exclusions.
An authoritative source/review establishes whether the inventory covers the real
project; a false exhaustive value in JSON is not evidence. Complete documentation
does not mean a complete product.

## History

Output contains `CURRENT.json` and `releases/<id>/{index.html,snapshot.json,MANIFEST.json}`.
The manifest pins the HTML and full snapshot. Each snapshot contains all selected
work records, their journal, source pins, documents, modules, contracts, and
coverage. All previous releases are retained. `history` verifies the chain backward
from CURRENT; `diff` compares two explicitly selected versions and their
state/fields/events/source paths. A broken CURRENT, incorrect SHA, orphan, or
stale lock requires reconciliation.

For matrices predating Atlas, `matrix_history` references every available
immutable version with a pinned file. When transferring/archiving, include these
files in the package, not just references. Do not treat REFS_ONLY as full matrix
content. List unknown or unavailable earlier versions in integration gaps; do
not restore them with invented events. Separate new Atlas snapshots already
contain full records.

### Projection archive pages

The current input need not accumulate all prior document/contract cards and all
raw matrix bytes. In an opt-in projection, the current DN contains the current
graph and new documentary event; prior full snapshots remain in immutable
releases. Preserve previous raw matrix files and import generations in full as
well. A single SHA row in the transferred archive cannot replace missing files.

The project field has this exact form:

```json
{
  "schema": "atlas.projection-archive/v1",
  "output": ".atlas/output",
  "previous_release": "EXACT-RELEASE-ID",
  "previous_manifest_sha256": "<64 lowercase hexadecimal characters>",
  "matrix_history_total": 41
}
```

This illustrates the structure: replace the placeholder SHA with the actual
manifest SHA. `output` is an existing relative directory within the selected
project root; `build/cycle` must publish to that same directory. Archive is
unavailable in native mode. Bootstrap without this field follows the prior
cumulative rules. Each subsequent projection checkpoint points to exactly its
previous release, and `matrix_history` contains only new unique versions, sorted
by their timezone-aware source time within the page. An older ancestor cannot
replace the current previous release. The cumulative count equals the previous
total plus the size of the new page.

A normal load verifies current inputs and one exact previous immutable release:
manifest, snapshot, and HTML. `atlas.projection_archive` records
`previous_snapshot_sha256`, `previous_matrix_history_total`,
`parent_manifest_status=VERIFIED_AT_SNAPSHOT_LOAD`, and
`archived_source_status=VERIFIED_AT_IMPORT`. This is not a current verification
of all ancestors or all prior raw sources. `atlas.matrix_history_total` shows the
cumulative count; in archive mode, the length of `atlas.matrix_history` shows
only the new page.

Prior DN cards and documentary events may be omitted from the current projection
only with this binding to a retained parent. A surviving document/contract ID
remains an immutable version under the existing DN rules; a substantive change
requires a new version ID. Module IDs may persist while the current model is
refined with a new documentary event. Native work IDs do not disappear: work
events, evidence, and acceptance still preserve strict append history. Once
archive is enabled, its field cannot be silently removed to return to cumulative input.

### Reading history pages

In archive mode, `history --limit N` returns at most N revisions, newest to
oldest, with N from 1 to 100 and a default of 50. One response contains at most
2000 matrix entries; reaching either boundary returns `has_more=true` and
`next_cursor`. Pass the `next_cursor` value unchanged through `--cursor`.
The cursor binds an exact release ID and manifest SHA; it is not an arbitrary
file path. A new call verifies its anchor and next page without retraversing
all the previous chain back to CURRENT.

A full chain read in one call from CURRENT to genesis yields `VERIFIED_CHAIN`.
An incomplete page or a continuation call yields `VERIFIED_PAGE`;
`ancestry_to_current=NOT_RETRAVERSED_FOR_CALLER_SUPPLIED_CURSOR` explicitly limits
the continuation claim. On continuation, `has_more=false` means the end after
that anchor, not a separate recheck of the entire chain. Counts on each loaded
link are verified; a missing or modified page is refused when read. Remaining
unloaded pages are not presented as verified in the current call.

`imported_matrix_history` returns the original `file={path,sha256,bytes}`,
`source_ref`, `retained_in_release`, and `file_target` — the actual local file
address relative to the project root. `source_validation=VERIFIED_AT_IMPORT`
and `raw_source_read_now=false`: `history` itself does not reread old raw matrices.
For a specific newly required byte check, use `pins` with the returned relative
path and compare the result with the retained pin. This is a targeted check,
not a new conclusion about runtime or acceptance of the original work.

Compatibility without archive: `history` preserves the prior full chronological
output of all locally retained releases and the unreferenced release list.
The `--limit` range is validated, but the old mode does not use it to shorten
output; `--cursor` is refused in that mode. Old releases store the previous SHA
without a release ID, so reaching such a legacy tail from archive may require
a search through MANIFEST headers. Its cost is reported in
`readback.legacy_manifest_headers_read`; only this explicit history request
performs that search. A normal refresh follows one direct parent link.
Archive pagination does not scan orphan releases.

### Metadata for accumulated importer history

New `IMPORT.json` files contain `history_metadata` with schema
`atlas.import-history-index/v1`: a total `row_count` and two sections,
`history_origins` / `retained_matrices`. Each section specifies `count`, the
SHA256 of the ordered record list, and page pins `{path,sha256,bytes,count}`.
An `atlas.import-history-page/v1` page contains the section name and up to 2000
`entries`; it is stored in an immutable import generation with its content
SHA256 in the filename. An unchanged full page is reused through its previous
exact pin. New source paths are appended after prior origins, so a new filename
that sorts before old names does not shift all accumulated pages.

`hydrate_history_metadata` verifies pins, shapes, strict integer counts, the
aggregate hash, and links from origins to retained matrices. It reads metadata,
not all old raw matrices. The existing inline format of two lists is supported
on the next update; a new release writes pages. `identity.histories` stores
`count` and the SHA256 of the sorted `{path,sha256}` sequence, not another full
copy of the list. The fixed state pin for the new `IMPORT.json` extends integrity
verification to this index.

Importer budgets are independent: 100000 visited source directory entries
(including files of other extensions and revisited entries in overlapping
declarations), 100000 rows total across both metadata sections, up to 2000 new
unique matrices in the current release page, and 32 MiB of source bytes first
read in this refresh. Metadata has an additional 8 MiB limit per page; the
project manifest remains limited to 512 KiB. Declared `paths` and `directories`
arrays contain up to 2000 entries each, but selected directory contents may
contain more than 2000 historical files. Scanning uses a bounded iterator;
exceeding any budget refuses the operation before a new generation or publication
pointer is written. History is not deleted.

Successful `refresh`, including `NO_CHANGE`, returns `capacity` with actual
`used`, `limit`, and `remaining` for scan, metadata rows, the new matrix page,
and new input bytes. This is a visible capacity boundary, not a promise of
infinite history. `new_input_bytes` counts the size of unique selected source
files read in that operation; a repeated verification read before publication
does not increase the counter. Old raw files with unchanged stat guards are not
reread, and qualification remains `VERIFIED_AT_IMPORT`. A changed guard triggers
a targeted read and verification of the previous selected SHA.

### Single writer of an imported projection

For an adapter-managed projection, only `import_matrix.py refresh` updates
`project.json`, import metadata/state, and output. All cooperating refresh
processes must observe `.atlas/IMPORT.lock`; output publication also uses its
`.writer.lock`. The existing upstream writer changes the source, then the single
adapter publishes a new projection. Another agent does not write `project.json`
in parallel or bypass the adapter with direct `atlas.py cycle`.

The source/project/CURRENT check before installation detects an observed
concurrent edit, but `compare` and `os.replace` are separate filesystem actions.
A process ignoring the lock and changing `project.json` between them may lose
its edit. The serialization guarantee applies to participants in the shared
writer protocol. Another read does not turn it into atomic OS CAS. Pending/UNKNOWN
requires exact reconciliation of the existing effect; do not appoint a second
writer to repeat installation.

## Boundaries

No network, SSH, DB, provider calls, application launch, arbitrary shell, or
execution of commands from documents. In the `atlas.py` CLI, `init` creates only
a new control directory; `build/cycle` write only the selected output. Other
operations read/compute. The caller must select authorized files; a hash is
neither a secret scanner nor an author signature. Atlas verifies consistency of
claims and bytes, not the truth of an arbitrary text receipt or a remote actor's identity.

Current source limits: up to 1000 work files; 1000 DN documents (DN-01.4), 2 MiB/document, 16 MiB
total document bodies, and up to 8 MiB for the DN input manifest; 1000 current
contracts; 32 MiB of selected Atlas bytes; 2000 events/evidence per record; and
2000 matrix entries per page. Archive does not raise these limits: it selects
the current graph/page while preserving prior full releases and raw files.
Split long-running work into explicit successor work items before its journal
limit; automatically deleting old events is forbidden. Reaching a limit refuses
the operation. Do not discard documents for an attractive COMPLETE: split project
areas with an explicit aggregate inventory or extend the contract/implementation
with a targeted check. Pages do not fetch/use a CDN or hide freshness conditions.
DOM tests do not confirm appearance in a real browser.

DN-01.4 document-record capacity counts both current and archived records. All published identities/fields and history remain in the native index; new versions append, never delete/rebind an old ID. Schema/runtime/OPERATIONS enforce1000;1001refuses. The existing byte ceilings above are unchanged. This is a versioned finite capacity successor, not a guard override or native-to-projection migration. See selected-document-capacity.md for bounded adoption/rollback and the retained predecessor note.
