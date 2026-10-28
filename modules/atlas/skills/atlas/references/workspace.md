# One command for bound projects

`scripts/workspace.py` connects existing local Atlas methods to an explicit registry. It runs in the same Python process: without SSH, a shell, discovery of new hosts, messaging, or deployment. An installation may give it the short name `atlasctl`; installation itself is outside this façade.

## Contents

- [Registry](#registry)
- [Daily cycle](#daily-cycle)
- [Writer checkpoint](#writer-checkpoint)
- [Machine result](#machine-result)
- [Current contracts and roadmap views](#current-contracts-and-roadmap-views)

## Registry

Pass `--registry /absolute/path/PROJECTS.json` before the command name. The file has only these fields:

```json
{
  "schema": "atlas.workspace/v1",
  "projects": [
    {
      "key": "example",
      "root": "/absolute/project/path",
      "binding": ".atlas/UPSTREAM.json"
    }
  ]
}
```

`root` is an existing absolute directory with no symlink in its path. Keys and roots are unique; `binding` is a safe relative path within `.atlas/`. An unknown key, extra fields, path traversal, or a symlink causes refusal. The façade does not extend the project list itself or assign a new writer.

## Daily cycle

```sh
python3 -B scripts/workspace.py --registry /absolute/path/PROJECTS.json list
python3 -B scripts/workspace.py --registry /absolute/path/PROJECTS.json start example --work WORK-ID
# Current writer: record actual begin/dispatch, then new progress before waiting.
python3 -B scripts/workspace.py --registry /absolute/path/PROJECTS.json work example \
  --operation OP-ID --work WORK-ID --phase start --executor ACTOR \
  --note "Actual beginning and scope" --next-action "Next observable result"
# For a source delta already saved by the existing writer method: finish example.
```

| Command | Result and effect |
|---|---|
| `list` | Only declared keys, roots, and bindings; creates no projections. |
| `refresh PROJECT` | `import_matrix.refresh`: refresh the projection of the authoritative matrix and pinned documents. |
| `start PROJECT --work ID` | One refresh, then the verified packet for a specific work item. Loads context without writing a source begin event. |
| `finish PROJECT` | The same refresh after a saved source delta. Unchanged inputs produce `NO_CHANGE`, with no new release; the verified current-view copy may be repaired. |
| `work PROJECT --operation ID --work ID --phase PHASE --executor ID --note TEXT --next-action TEXT` | Pin current source and supplied files, retain the exact operation record and execute its checkpoint. `--status` is required for progress/complete; `--evidence REL` and `--document-edit DEST PREPARED` can repeat. |
| `checkpoint PROJECT --record RELPATH` | The current writer commits one declared, prepared source/document delta through its opt-in profile, then refreshes once. |
| `checkpoint-reconcile PROJECT --operation ID` | Read the exact writer checkpoint's recorded outcome; do not replay it under a new ID. |
| `checkpoint-reconcile PROJECT --operation ID --finish-pending` | Finish only that existing pending checkpoint through guarded recovery. |
| `packet PROJECT --work ID` | Read the verified existing projection and work packet; no refresh. |
| `audit PROJECT` | Read criteria, coverage, issues, and next actions from the existing projection. Runs no product checks. |
| `views PROJECT` | Verify one CURRENT release and its current-view copy; compare the selected owning matrix and return compact HTML/JSON pins, section routes and coverage. No refresh, writes or browser action. |
| `history PROJECT --limit 20 [--cursor TOKEN]` | Read retained history through `atlas.history`. Pass the next `next_cursor` unchanged. The limit is 1–100; the core result determines completeness of the entire history. |
| `reconcile PROJECT` | Only read current receipts, pending state, and lock. Does not remove a lock or repeat an unknown operation. |
| `docs PROJECT --source-root /absolute/source` | `sync_docs.update`: update only the previously pinned document set from an explicitly selected local source. Preserve the source set and authoritative sources; the updater finishes by refreshing the projection. |
| `docs-reconcile PROJECT [--finish-pending]` | Check an existing document update operation; with the flag, finish that exact operation through supported recovery. |

`packet` and `audit` reflect the pinned projection. If authoritative inputs have changed since it was produced, `refresh` is required first; reading does not import a delta or claim remote host freshness. A historical source claim remains a claim of its source; the façade does not turn it into new acceptance or current activity.

## Writer checkpoint

Configure `.atlas/WRITER.json` explicitly through the established current writer;
it is not created by `start`. It binds the exact source matrix/pointer, writer,
shared source lock and allowed prepared document paths. All participants must
respect that lock. A profile does not transfer authority or make Atlas a second
source writer. A missing or mismatched profile is a specific refusal: retain the
existing source method and fix that binding once, rather than repeatedly calling
refresh and expecting it to invent a begin event.
The source-writing route requires POSIX `flock` (macOS/Linux); it is not currently
a portable Windows writer. Existing read-only routes retain their platform scope.
Preflight limits are 8 MiB for the enclosing JSON and 2 MiB for the selected matrix
as a document; a direct matrix is therefore limited to 2 MiB. Oversized input is
refused before source changes.

The profile below illustrates the complete required shape. Replace the example
IDs/paths/schema with the current binding and writer; do not infer them from names.

```json
{
  "schema": "atlas.matrix-writer/v1",
  "binding": ".atlas/UPSTREAM.json",
  "project_id": "example",
  "writer": "main",
  "matrix": {"path": "work/MATRIX.json", "pointer": "", "allowed_schema": "example.work-matrix/v1"},
  "lock_path": ".atlas/CHECKPOINT.lock",
  "document_paths": ["docs/WORK.md"],
  "history": {"mode": "retained-operation-snapshots", "previous_payload_hash": "source-bytes"}
}
```

`matrix` must match UPSTREAM exactly; `document_paths` selects existing bound
documents outside `.atlas/`, excluding the matrix and semantic catalog itself.
An empty pointer requires `source-bytes`, the hash of the whole previous file;
a nonempty pointer requires `selected-canonical`, the hash of
`nav.canonical(previous selected matrix)`. Checkpoint preserves the other
enclosing JSON bytes. Binding/catalog changes still use the established writer's
method; this adapter does not rebuild a semantic catalog or rewrite its binding.

On actual beginning or delegation, immediately record the existing executable
work ID, responsible actor and actual dispatch outcome. Publish before waiting
after a new fact. Workers return start/progress/result/blocker deltas through
their existing authorized route; the main writer incorporates shared-file changes.
The writer prepares any affected document bytes and calls the typed `work` method
shown in the daily cycle. It reads the current binding/profile, pins the source,
evidence and prepared edits, saves `.atlas/checkpoint-records/<operation>.json`
and executes the checkpoint. No manual source-hash sequence is needed. Reusing
the operation ID and identical arguments reuses its original time/pins; changed
arguments under that ID are refused. One completed checkpoint includes its
projection refresh; do not follow it with another `finish`.

For `start`/`dispatch`, status defaults to `doing`. For `progress`/`complete`, pass
`--status` explicitly using the table below. Add evidence with `--evidence REL`
and prepared doc changes with `--document-edit DEST PREPARED`; both options may
repeat. Activity claims use only the advanced prepared-record API below.

### Advanced prepared record

Use `checkpoint PROJECT --record RELPATH` when an exact record is already prepared,
including a separately supported activity claim. It uses the same writer profile
and recovery as `work`.

The record has the following required fields. This is a template, not a ready
request: replace example identities, `<...>` and numeric zeros with observed
values. `expected_source.sha256` and `bytes` pin the **whole raw enclosing file**,
even with a matrix pointer; `revision` is the selected matrix's revision.

```json
{
  "schema": "atlas.checkpoint/v1",
  "operation_id": "op-step-1-start",
  "project_id": "example",
  "writer": "main",
  "work_id": "STEP-1",
  "phase": "start",
  "at": "<UTC timestamp>",
  "expected_source": {"sha256": "<whole source SHA-256>", "bytes": 0, "revision": 0},
  "executor_id": "main",
  "status": "doing",
  "note": "<actual beginning and bounded scope>",
  "next_action": "<next observable result>",
  "evidence": [],
  "document_edits": []
}
```

| Phase | Allowed recorded status and basis |
|---|---|
| `start` | `doing`; actual beginning of the selected executable step. |
| `dispatch` | `doing`; actual delegation outcome, not inferred worker execution. |
| `progress` | `doing`, `waiting`, `blocked` or `partial`; a new scoped fact. |
| `complete` | `done` or `partial`; at least one pinned evidence file. A source result does not establish Atlas acceptance. |

Evidence rows are `{path, sha256, bytes}`. Prepared `document_edits` rows are
`{path, before: {sha256, bytes}, after: {path, sha256, bytes}}`: the destination
must be permitted by the profile; `after.path` is a separate pinned staging file
inside the project, distinct from every destination. Paths must be safe and
without symlinks. Empty edits mean no material document change was prepared;
do not invent one merely to mark beginning.

Optional `activity` has `{observed_at, valid_until, source, ref, receipt}`;
`receipt` is a pinned `{path, sha256, bytes}`. Its source is
`supported_native_route`, `supported_native_wait`, `collaboration` or
`supported_command`. Supply it only for `start`/`progress` with `doing` and actual
actor/work proof whose validity window is at most one hour. Dispatch alone never
creates activity. Recorded status persists independently of that expiry.
The pinned receipt JSON must contain `scope: "ACTIVITY"`, `result: "PASS"`,
`actor_id` equal to the executor, `step_id` equal to the work, `state: "active"`,
and `at`, `valid_until`, `source`, `ref` matching the activity record (`at` matches
`observed_at`). Extra fields are allowed. These are pinned recorded observations;
the command does not perform an independent live activity probe.

Repeated unchanged waiting is not another event. Preserve the same operation
ID and exact record bytes: a replay returns the existing outcome without another
source event. `CHECKPOINT_PUBLISHED` records successful publication; `NO_CHANGE`
creates no new event. `CHECKPOINT_PENDING` leaves an incomplete operation whose
source and projection outcomes must be read separately. For an uncertain checkpoint, call
`checkpoint-reconcile PROJECT --operation ID`; use `--finish-pending` only to
complete that exact recorded operation. Do not delete its lock, invent a new ID,
rewrite history or replay a dispatch. Checkpoint sends no messages and does not
author semantic document or contract changes.

`CHECKPOINT_FINALIZATION_PENDING` means a result was already retained but its
own pending marker remains. The response keeps `status: CHECKPOINT_PENDING` and
the earlier `recorded_status`. Read-only reconciliation preserves that distinction;
`--finish-pending` can complete this exact finalization without another source
event or publication. Do not treat the pending response as a fresh dispatch request.

The source transaction uses cooperative `CHECKPOINT.lock` and temporarily blocks
ordinary imports with `IMPORT.lock`. Interrupted partial changes retain their
blocking token and stored before/after bytes. Recovery completes only those exact
changes; it does not repeat an external action. A writer ignoring the shared lock
is outside this coordination guarantee.

## Machine result

Standard output contains one JSON object. `list` returns `schema: atlas.workspace.list/v1` and `projects`. Project commands add `project_key`, `current`, and `view_path`: the stable `output/index.html` only when verified against CURRENT, otherwise the verified immutable release path. `current_view` qualifies that choice. Before the first release, `current` and `view_path` are `null`. A corrupt CURRENT or release returns `REFUSED`, not a path to a presumed working view.

`start` and `packet` return `status: CONTEXT_LOADED` and a nested `packet` in `atlas.packet/v1` format; `start` also contains `refresh`, `summary`, and `coverage`. `audit` returns `PROJECT_CONTROL_REVIEW`, `coverage`, `summary`, `issues`, `next_actions`, and `product_execution: NOT_RUN`. Other commands preserve the statuses and fields of their corresponding core/adapter API.

Exit codes: `0` — command completed; `1` — JSON `REFUSED` with a reason code; `2` — unsupported or incomplete CLI arguments. First reconcile an unknown mutation outcome through the corresponding `reconcile`; creating a new operation under a different ID is not recovery.

## Current contracts and roadmap views

Use `agentos atlas views PROJECT`, or `atlasctl views PROJECT` through its selected
distribution. An explicit `--registry PATH` goes before `views`. Handle an opening
request in the receiving session; resolve its known project once and do not send
the request back to itself or create another keeper.

`views` returns `atlas.workspace.views/v1`: `ARTIFACTS_READY` means both artifacts
passed the existing CURRENT/manifest verifier. The record includes paths, file
URLs, SHA-256/bytes, release, `as_of`, compact coverage, counts and source revision.
It observes one CURRENT pointer, does not scan all history and makes no writes.
`freshness.matrix` compares only the selected owning matrix: `MATCHED`, `CHANGED`
or `UNKNOWN`, with observed source revision when established. Other documents
remain `NOT_COMPARED`; the broad `freshness.owning_sources = NOT_COMPARED` is not
overridden by a matrix match. A changed matrix needs the current writer's finish
route; this read does not import it. The retained source revision comes only from
a matched document pin in the published snapshot.

`current_view.status = CURRENT` selects the stable `output/index.html` for
`view_path` and section URLs. It is byte-identical to the verified immutable HTML.
Reloading this URL shows later successful publications. Other current-view states
retain the verified immutable path with their explicit qualifier; `views` does
not repair them. `artifacts.html` and `artifacts.json` always name the immutable
release, suitable for history and downloads. A downloaded file or immutable URL
does not advance to a new release when reloaded. Neither URL watches source code
or automatically refreshes the browser.

Publication updates the stable copy. Explicit write flows such as
refresh/start/finish/checkpoint may repair it after `NO_CHANGE`, under the existing
output writer lock and exact CURRENT release/manifest pins. This changes no work
event or release; conflicting or unmanaged state is refused rather than overwritten.

`NO_CURRENT_VIEW` has no artifact paths; an incomplete/corrupt release is
`REFUSED` and is not repaired. Only an `atlas.presentation/v1` marker declaring
the section enables `#contracts` or `#roadmap`. Old releases receive the base URL
and manual section names, with `UNKNOWN` for unavailable source revision.

The command reports presentation/browser `NOT_REQUESTED`. Open the returned
artifact once through an authorized supported interface and confirm its release
and intended section before reporting `OPENED`. A queued message or returned path
is not that confirmation. If the interface cannot confirm opening, provide both
verified files through the supported downloadable-file route and report the
actual status. Preserve a denied route; do not substitute another browser/server.

If updating sources is also authorized, the existing writer commits one prepared
checkpoint, or uses `finish PROJECT` once for an already saved delta. Then read
`views PROJECT`. The read method does not author missing contracts, change the
writer, reset the binding or turn source claims into acceptance/activity evidence.

## Explicit bounded old-history requalification

See [history-requalification.md](history-requalification.md) for the finite page API, full SHA/stat/generation proofs, exact pending recovery and separate certificate/publication statuses. Defaults and old immutable history remain unchanged.


## Exact prior project texts and display translations (rc2015 SOURCE candidate)

`checkpoint-reconcile PROJECT --operation OP --inspect-protected-text-restore` is read-only qualification of the exact existing committed pending operation. `--restore-protected-texts --finish-pending` permits only its original writer to restore project.objective/project.scope_note from the frozen archived predecessor, preserving the original PLAN/record, source AFTER, project identity/writer/output and every other authority field. The v3 manifest is atlas.protected-project-text-recovery/v3; old scope_note-only v2 flags/manifests remain distinct. Partial staging, original/restored CAS and an independently verified immediate published successor are reconciled; no blind refresh, repin or new operation is implied. Preserve the capable reader after any v3 preparation/manifest/UNKNOWN or intermediate restored state; do not claim a v2 reader can finish v3. Installer compatibility alone does not establish project-checkpoint reader compatibility.

A current bound Markdown document may contain exactly one section:

````text
<!-- ATLAS_DISPLAY_FIELDS_BEGIN -->
```json
{"schema":"atlas.localized-display-fields/v1","language":"ru","project_id":"EXACT_PROJECT_ID","records":[{"target_id":"EXACT_WORK_OR_PROJECT_ID","field":"work.objective","original_value":"Exact source value","original_sha256":"SHA256_OF_EXACT_UTF8_ORIGINAL","translated_value":"Русское отображение"}]}
```
<!-- ATLAS_DISPLAY_FIELDS_END -->
````

Only work.title/work.objective/work.scope_note/project.objective/project.scope_note are accepted. Use an already bound current mutable document; no historical path rewrite or extra document slot is needed. Current document SHA/bytes/pin, exact identity/source-original value+hash and language are checked. Duplicate/stale/invalid projections remain UNKNOWN and retain original source. Display fields do not edit project authority, original definitions/events/criteria/dependencies/assignments or sanitize rules. The title-fallback objective can derive a verified title only when the owning step has no nonempty string definition; it is labeled DERIVED_TITLE_NOT_SEPARATE_OBJECTIVE. Raw original records/project and display provenance remain separate in both copy packets. Rendering is snapshot-based, not installed/runtime/business acceptance.
