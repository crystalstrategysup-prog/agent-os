# Binding an existing authoritative matrix

`scripts/import_matrix.py` is a separate local adapter for an explicitly selected WM-UI
source with `steps`, `events`, `actors` and `updated_at`. It preserves the active matrix
and documents in their existing locations and creates a derived Atlas projection.
The private project binding specifies the exact permitted source schema; a schema
name alone does not make an unknown format compatible.

This is a standalone CLI. `atlas.py` does not acquire a new `refresh` command; a shared
project helper may invoke the adapter and then the required core procedure sequentially.
There is no network access, shell wrapper, automatic dispatch, scheduler or background polling.

## One ordinary pass

Set `atlas_importer` to the installed `scripts/import_matrix.py`, `atlas_tool` to its
sibling `atlas.py`, and `atlas_project` to the registered project root.

```bash
python3 -B "$atlas_importer" refresh --root "$atlas_project"
python3 -B "$atlas_tool" run session-start --root "$atlas_project" --work "$atlas_work_id"
```

The executor continues its existing assignment. The established writer saves the source
matrix delta; the next `refresh` updates only dependent parts of the projection. An
installed adapter does not establish that an active session has read the new version.

| Method | Parameters | Effects and result |
|---|---|---|
| `refresh` | Required `--root`; optional `--binding` (default `.atlas/UPSTREAM.json`), `--at` (UTC/aware observation timestamp) | Reads selected sources, retains an immutable generation and a local release through core `cycle`; returns `IMPORTED_PARTIAL` or `NO_CHANGE`. Does not write source matrix/docs/history. |
| `reconcile` | Required `--root`; optional `--binding` | Reads only projection state, exact CURRENT, pending generation and lock. Does not repeat the original operation, repair a pointer or delete a lock. |

```bash
python3 -B "$atlas_importer" reconcile --root "$atlas_project"
```

JSON inputs are not executed. `--at` fixes the observation time; it does not make old
source activity receipts fresh. For `reconcile`, time does not change retained state.
Exit codes: `0` means the local method completed, `1` means `REFUSED` with an exact
code, and `2` means invalid CLI argument form. `RECONCILE_REQUIRED` is an observed
state, not evidence that a previously unknown change succeeded.

## Initial binding

1. Find the exact authoritative matrix, writer, project root, documents and available
   originals of earlier matrices. Use existing rules and the already authorized scope.
2. Write `.atlas/UPSTREAM.json` using `assets/upstream-template.json`. The template is
   a structural example; replace its values with project facts. A placeholder actor
   or authority does not confer actual permission.
3. Do not run a separate `atlas.py init` before the first `refresh`: the adapter creates
   its own projection. An existing `.atlas/project.json` owned by something else yields
   `EXISTING_ATLAS_NOT_ADAPTER_OWNED`; preserve its owner and choose an explicit integration.
4. Run `refresh`, then obtain the required work packet. Retain actual installation
   and consumer-read results separately from product acceptance.

The binding contains `schema=atlas.upstream-binding/v1` and the following sections:

| Section | Required value and semantics |
|---|---|
| `project` | `id`, `title`, `objective`, `writer`, `authority_ref`, `scope_note`. The writer is known; the record grants no new rights. |
| `matrix` | `path` relative to the project root and exact `allowed_schema`; optional `pointer`, default `""`. |
| `history` | `paths` for specific files, `directories` for specific directories, `coverage_note`; optional `pointer`, default `""`. Directories are read one level deep and all `.json` files are selected; a missing directory or invalid pointer is refused. |
| `documents` | Explicit `id`, `path`, `title`, `role`, `domain` for each document. Domain: goals/modules/contracts/documents/source/works. Role describes its actual role; it is not an executable command. |
| `semantic_catalog` | Optional exact `{path, sha256, bytes}` for an external `atlas.semantic-catalog/v1` file. The catalogue explicitly links selected documents, modules/contracts, relationships and work; `null` does not enable a catalogue. |
| `output` | A selected path inside `.atlas/`, outside `.atlas/imports/`. Usually `.atlas/output`. |

Paths are relative, without `..`, symlinks or shell syntax. Authoritative sources are
outside the generated `.atlas/` tree. `null` and `false` do not replace an omitted
optional string. Empty history lists mean no files are bound; describe the actual known
gap in `coverage_note`. Events in the current matrix cannot establish missing complete
historical versions.

Project identity/authority/writer, matrix path/pointer/schema, output and existing
history directory bindings are preserved. Changing these boundaries requires an explicit,
agreed transition, not a silent reset. New `documents` and `history.paths` may be
**appended** through an ordinary `refresh`. Existing definitions of those bindings are
not rewritten. Changing the bytes of an existing document creates its next immutable
document version; the prior bytes and card remain in an immutable archived release.
Atlas history continues. A catalogue may be attached through the first ordinary refresh;
its path is then preserved, while its pin is updated for substantive catalogue changes.

## Declarative relationship catalogue

For documentation that already has structure, use one deterministic builder and pin its
result. `catalog.py` supports OpenAPI, record catalogues and operation registries; `--help`
defines the exact CLI. It transfers claims from the selected source, preserves UNKNOWN
and does not invoke the APIs it describes. The manual sidecar template is
`assets/semantic-catalog-template.json`.

The catalogue requires `schema`, `modules`, `contracts`, `relations`, `work_bindings`;
`work_context` and `patch_bindings` are optional lists. An empty list means no relationships
are declared, not that such relationships do not exist in the project.

| Section | Exact structure and meaning |
|---|---|
| `modules`, `contracts`, `relations` | Native DN record format from `data-contract.md`. All `docs`/`evidence_docs` use logical IDs from UPSTREAM.documents; entity refs are module/contract card IDs or selected document IDs. |
| `work_bindings` | `{work_id, entity_ids}`; one record per source work item. A packet expands only declared contract/module dependencies and their documents, without keyword matching. |
| `work_context` | `{work_id, outcome?, result_claim?, remaining?, next_action?: {actor, action}}`; supply only known, nonempty strings. An absent field comes from the retained source or an explicitly bounded fallback. |
| `patch_bindings` | `{work_id, patch_doc_id, target_doc_id, base_sha256, selectors, source_state}`. Patch and target are selected documents; SHA equals the exact target bytes, and selectors are unique JSON Pointer strings. The original lifecycle remains in the fragment. |

The importer maps logical IDs to current immutable doc/contract version IDs. A contract
version depends on its card, supporting document versions and declared contract
dependencies. Changing an unrelated card does not rewrite the others. If many contracts
reference one large document, changing it affects all those references; explicit module-level
source slices can limit that scope while retaining the complete original in the archive.
Do not arbitrarily split a source to pass limits or label an incomplete binding as complete.

A native patch is created as `PROPOSED`, without decision evidence. A historical source
claim of applied/accepted remains a source claim; it does not replace documented Atlas
application/readback. If the target has already changed, bind the actual old base snapshot
as a separate document; do not substitute the current SHA for the historical one. An
invalid pin, dangling entity or patch-base mismatch produces an exact refusal.

## Nested matrix and preservation boundaries

If a shared JSON file contains the matrix inside a larger state, specify its JSON Pointer,
for example `/work/ownerMatrix`. The adapter retains canonical JSON for only the selected
subtree. Provenance retains the enclosing file path/SHA/size, pointer and selected SHA.
Complete enclosing-file bytes are not copied into Atlas documents, fragments or output.
This preserves the exact selected subtree, without claiming to preserve the entire source file.

The fingerprint uses selected matrix bytes, selected history/docs, the binding and tool
version. An unrelated change in the enclosing context yields `NO_CHANGE`; the response
may report a new observed enclosing SHA without rewriting the prior receipt. During a
substantive refresh, source CAS checks the entire file that was read. An invalid pointer
does not permit fallback to the entire document.

## Meaning of projection state

All source fields, actors/events/activity arrays and original timestamps remain in the
retained matrix. `source_definition` may be any JSON value; a structured value is retained
in full in the work fragment. Event append order is preserved, including backfill and
equal timestamps; global sorting does not rewrite the source.

| Source state | Atlas state |
|---|---|
| Parent with child work items | `PLANNED`, without its own activity/write scope. |
| `planned` | `PLANNED`. |
| `doing`, with one explicitly declared, known executor | `DOING`; activity remains `null`. |
| `done` or `partial`, with one explicitly declared, known executor | `REVIEW`; raw source acceptance is retained as a source claim. |
| `doing/done/partial` without a single known executor | `UNKNOWN`; no executor is invented merely to pass validation. |
| `blocked` | `BLOCKED`; the source reason is retained, and an unknown unblock condition is explicit. |
| `waiting` | `PAUSED`; this interprets a source label and does not establish that a process has stopped. |
| No status event, or the label is unqualified | `UNKNOWN`. |

The current core has no typed transition from a previously established state to `UNKNOWN`.
In that case the adapter returns the work item to `PLANNED` with a `REOPEN` event and
explicit source UNKNOWN in `remaining`. This is a qualification plan, without a claim
of current execution.

`assigned_to` comes only from singleton `executor_ids` whose executor is present in the
actors registry. A multiple-executor list is retained in the source and is not collapsed
by choosing one person. `writer` is the current projection owner from the binding.

The adapter creates no PASS evidence, acceptance or activity. The work outcome preserves
explicit work_context or the scope of the source definition. `result` shows `SOURCE_CLAIM`
with exact status/event/time/accepted/note and additional source result_claim. The complete
event and original acceptance scope remain in the fragment. Unknown criteria, work
dependencies and write scopes are not invented: criteria/write_scope/depends_on remain
empty and explicitly unqualified. This grants no permission to write and does not
establish that dependencies are absent.

The absence of new native Atlas acceptance **does not invalidate** an earlier scoped
result and does not require completed work to be tested again. Work item `ATLAS-IMPORT-GAPS`
records metadata gaps with the `ON_NEXT_TOUCHED_WORK` policy: the existing writer closes
only the specific gap that blocks the next assigned change. First reuse relevant prior
evidence, then perform the missing validation.

Existing source `done/accepted/matrix_complete` does not confer Atlas `ACCEPTED/COMPLETE`.
All six inventory domains remain `exhaustive=false` until review by the owner establishes
completeness. Module/API cards and work bindings come from the pinned catalogue; filename
semantics alone create neither a relationship nor evidence of completeness.

## History, avoiding empty actions and refusal

Sources are retained in `.atlas/imports/<fingerprint>/`; the root `.atlas/project.json`
references immutable generation files. Unchanged work records and fragments are reused
at their existing paths. The complete matrix SHA is not included in every work artifact:
changing one source step does not create events in every other work item.

The first pass pins bytes and source times for every explicitly available history file.
It does not require different old presentation schemas to be byte-identical, and it
does not treat `previous_payload_sha256` as an automatically verified raw file hash.
On subsequent passes, prior definitions and event-array prefixes in the current
authoritative matrix are immutable; `order` is permitted as a presentation field.
Historical source files must not be deleted or changed. Already pinned history paths
are checked by size/mtime/ctime/device/inode; a new file or changed stat metadata requires
a targeted read and rehash. Unchanged stat metadata does not trigger another read of
all old raw bytes: their status is `VERIFIED_AT_IMPORT`, not verified in full now.
This checks local continuity and does not protect against privileged forgery of stat
metadata or files. Later backfill of an earlier complete matrix requires an explicit
import lineage: core append-only matrix history does not insert versions retroactively.

Identical matrix bytes already retained are not duplicated as a new version. Provenance
for selected source history paths is retained separately. When transferring an Atlas
project, include **the entire transitive `.atlas/imports/` and output history**, not just
the latest generation: its work/doc references may point to earlier immutable generations.

From the second release, the adapter includes `projection_archive`: exact previous
release, manifest SHA, output path and cumulative matrix_history_total. The current DN
contains current documents/cards and the new event; matrix_history contains only new,
unique, complete matrices. Old snapshots and source bytes are retained separately.
The core verifies one immutable parent; an ordinary refresh does not reload the entire
archive. `history` reads one page of the retained chain: `--limit` is 1 to 100, default
50. Read the next page using `next_cursor` while `has_more=true`, only when the remaining
history is needed. One `VERIFIED_PAGE` does not establish verification of the complete
chain. Archived source bytes remain `VERIFIED_AT_IMPORT`; the current request checks
immutable release files. This paginated route does not perform a global orphan scan.
Native projects retain strict append-only rules; the archive hook applies only to projections.

History provenance and retained complete-matrix registries are stored in separate
immutable metadata pages. A small `history_metadata` index pins counts, sequence SHA
and those pages. Unchanged complete pages are reused. The former inline metadata format
remains readable. These pages contain references and historical qualifications; reading
metadata does not relabel old raw bytes as verified now or rewrite source snapshots.

An ordinary pass follows: source read → source continuity → immutable candidate → core
validation → optimistic source/project/CURRENT checks under the writer lock → core cycle.
With an unchanged fingerprint, the current snapshot is checked for applicability;
`NO_CHANGE` creates no event, generation, release or new product test.

**Only the importer** writes `.atlas/project.json`, import state and pending receipts
under `IMPORT.lock`; a second refresh is refused. The existing authoritative writer
changes the source matrix, then invokes the adapter. Direct projection editing, including
manual repair by another agent, violates this protocol. A comparison before atomic rename
is not filesystem CAS against an unrelated writer that ignores the lock: a window remains
between comparison and rename. Compatibility with active sessions requires routing all
projection writes through the importer, rather than promising that an additional check
eliminates this window.

If publication is known not to have occurred, the adapter restores its own project
pointer to the previous bytes. If the effect is unknown, the original fingerprint,
pending receipt and exact state are retained for `reconcile`; no repeated mutation or
new operation identity is started. Do not remove a lock or pending receipt to bypass
uncertainty. An independent writer does not acquire a resource through expired activity
or a missing ACK.

Core limits apply: up to 1000 current works including gap work, 200 current DN documents,
200 modules, 1000 contracts, 2 MiB per DN document, 16 MiB of DN documents in total and
32 MiB of currently selected workflow bytes. A semantic catalogue is limited to 8 MiB;
each metadata page is limited to 2000 rows and 8 MiB. Cumulative `history_origins` and
`retained_matrices` together are limited to 100000 metadata rows. Traversal of registered
history directories together with explicitly listed paths is limited to 100000 visited
source entries; visited entries not selected as JSON also count. Each declarative
binding array, `history.paths` and `history.directories`, is limited to 2000 entries.
One refresh adds up to 2000 new, unique, complete matrices; this is the new-page size,
not a cumulative history limit. During initial bootstrap, all supplied history bytes
count toward the bounded 32 MiB read. A larger old archive requires an explicit, agreed
import lineage that preserves originals.

Successful `refresh` and `NO_CHANGE` results return `capacity`: actual `source_entries`,
`selected_history_paths`, `metadata_rows`, `retained_matrices`, `new_matrix_page`,
`new_input_bytes` and `metadata_page_rows`. Budget fields report `used`, `limit` and
`remaining`; `new_input_bytes` covers selected source bytes in the current call.
Exceeding a limit yields `REFUSED`, without silently excluding source/history to claim
COMPLETE. Preserve existing imports and output archives; do not delete history merely
to continue importing. Local import/no-op timings measure adapter execution in that
environment; they are not product cold/warm deployment timings or a universal speed promise.

## Adapter validation

Separate synthetic tests are in `public/tests/test_import_matrix.py`:

```bash
python3 -B -m unittest discover -s "$atlas_public/tests" -p test_import_matrix.py -v
```

They cover first import, unchanged no-op, selective append, immutable-source refusals,
appended document bindings, current-version rollover, authority preservation, selected-subtree
privacy, confirmed rollback, lost-ACK reconciliation, semantic packet closure, selective
contract impact, legacy claim scopes, patch pins and the historical stat cache with
targeted refusal on a change. Real private replay receipts are retained separately
from the public skill and do not establish runtime or product acceptance.

## Explicit bounded old-history requalification

See [history-requalification.md](history-requalification.md) for the finite page API, full SHA/stat/generation proofs, exact pending recovery and separate certificate/publication statuses. Defaults and old immutable history remain unchanged.
