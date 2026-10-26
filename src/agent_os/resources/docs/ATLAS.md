# Atlas: local project work and documentation module

Candidate native Markdown entry migration uses the bundled Atlas
`references/source-relocation.md` contract. Its explicit source-relocate
plan/apply/status/reconcile route preserves historical logical identity,
accepted basis and retained bytes. Default historical rewrite/orphan guards
remain strict. Installation and real-project adoption need separate evidence.

Atlas connects a project's objective, documents, all declared work, ownership,
contracts and patches to retained evidence and matrix history. AgentOS exposes
the existing local Atlas workspace through one command family. The same reviewed
module remains usable on its own.

## One entry, two depths

`AGENTS.md` is only the Atlas development entry. For the exact MINIMAL/FULL
contract use `modules/atlas/skills/atlas/references/operating-modes.md`,
included in installed resources. MINIMAL reads only affected work/source/docs
and writes one evidence checkpoint; FULL maintains applicable architecture,
contract, matrix/history, tests, and rollout evidence. Both use an existing
writer and bounded indexed retrieval, not a duplicate project controller.
For changes to AgentOS public source, Atlas loads `docs/ATLAS_SOURCE_POLICY.md`
(the former project AGENTS guard clauses) before writes.

## Entry points and registry

```bash
agentos atlas list
agentos atlas --registry /ABSOLUTE/PROJECTS.json list
atlasctl --registry /ABSOLUTE/PROJECTS.json packet PROJECT --work WORK_ID
atlasctl views PROJECT
```

Without `--registry`, the only default is
`~/.agentos-user/knowledge/atlas/PROJECTS.json`. An explicit value selects that
exact file. The facade does not search other folders, create a registry, discover
hosts or initialize AgentOS configuration when the selected file is absent.
AgentOS `--home`/`--user-home` is not an Atlas registry selector; use `--registry`.

The registry uses `atlas.workspace/v1` and an explicit list of `key`, absolute
`root` and relative `.atlas/` `binding` records. The Atlas loader validates those
records, root identity, allowed paths and the selected binding. Missing,
malformed, duplicate, symlinked or unknown selections fail closed. CLI help and
argument errors retain the existing command behavior.

## Detect before development or continuation

A plain request to continue a project first triggers a scoped read of its current
instructions, exact registry entry and local Atlas binding. An existing binding
is read and started through its declared route; the current task/writer remains.
A missing command or registry does not establish that the project lacks Atlas.
Unreadable or conflicting state stays UNKNOWN until that exact gap is resolved.

When Atlas is confirmed absent, reuse an applicable explicit earlier choice;
otherwise offer exactly these three options:

1. **Create Atlas before development.** Bootstrap a truthful minimal binding,
   inventory, current writer and work packet, then continue.
2. **Continue this task explicitly without Atlas.** Retain that scoped choice in
   the current task checkpoint and continue its existing obligations.
3. **Continue the task and start a separate temporary Atlas bootstrap session.**
   Keep the main session accountable and preserve shared-resource ownership.
   Give the temporary worker an isolated, bounded inventory/binding/history
   assignment; review and integrate its result, then close that assignment.

No permanent keeper, replacement controller or forced session restart follows
from the third option. Use only the existing authorized native task/return route.
The bundled skill integration guide defines the bootstrap paths. A read-only
question does not require choosing or creating Atlas.

## Daily cycle

1. Start the assigned block with `agentos atlas start PROJECT --work WORK_ID`.
   This refreshes the projection and loads context; it writes no source begin event.
2. On actually beginning or delegating an executable step, its current writer
   immediately records the work, responsible actor and dispatch outcome through
   the typed `agentos atlas work` method below. It pins current source and prepared
   document/evidence files automatically. The opt-in
   `.atlas/WRITER.json` binds the exact source, shared lock and prepared doc paths;
   the bundled `references/workspace.md` defines its record and recovery.
3. Publish a checkpoint **before waiting after new facts**. Integrate returned
   deltas and maintain relevant documents while waiting; continue independent
   authorized work. Workers return facts to the shared matrix's writer. An
   unchanged wait creates no new event. Recorded DOING is not proof of live activity.
4. `work` commits the declared prepared source/document changes and refreshes
   once. It does not author document/contract semantics or establish acceptance.
   For a delta already saved by the established project method, use `agentos atlas
   finish PROJECT` once instead. No extra finish follows a successful checkpoint.
   Unchanged inputs create no release; a write flow may repair the verified
   current-view copy without changing source or release history.
5. Use `packet` for context, `history --limit N` for retained matrix pages and
   `audit` for declared coverage/gaps. Reconcile an UNKNOWN operation before retry.

```bash
agentos atlas work PROJECT --operation OP_ID --work WORK_ID --phase start \
  --executor ACTOR --note "Actual beginning and scope" \
  --next-action "Next observable result"
```

Use `dispatch` for actual delegation. `progress`/`complete` require `--status`;
completion requires pinned evidence via `--evidence RELPATH`. Supply prepared
document changes with `--document-edit DEST PREPARED`; both options can repeat.
The same operation ID and arguments reuse the original record/time/pins.

An ordinary question outside an assigned project work item needs no bootstrap,
new task event or repetitive acceptance run. Earlier scoped evidence can be
reused until a relevant change, expiry or unresolved gap requires another check.

## Commands and effects

| Command | Inputs | Local effects |
|---|---|---|
| `list` | selected registry | none |
| `start PROJECT --work ID` | exact binding and work ID | refresh projection, then return packet |
| `refresh PROJECT`, `finish PROJECT` | exact binding | import changed owning sources; no new release when unchanged; may repair the verified current-view copy |
| `work PROJECT --operation ID --work ID --phase PHASE --executor ID --note TEXT --next-action TEXT` | writer profile; `--status` for progress/complete; repeatable `--evidence REL` and `--document-edit DEST PREPARED` | pin current inputs, retain the operation record, commit its delta and refresh once |
| `checkpoint PROJECT --record RELPATH` | current writer profile and prepared record | commit selected source/document delta and refresh once; same operation is not duplicated |
| `checkpoint-reconcile PROJECT --operation ID` | exact recorded writer operation | read its checkpoint outcome |
| `checkpoint-reconcile PROJECT --operation ID --finish-pending` | exact pending writer operation | complete only that operation through its guarded recovery |
| `packet PROJECT --work ID` | retained current projection | none |
| `history PROJECT [--limit N] [--cursor TOKEN]` | retained output | none; follows the explicit page cursor |
| `audit PROJECT` | declared inventory and current work | none; reports bounded coverage and gaps |
| `views PROJECT` | one verified CURRENT release and selected owning matrix | none; matrix comparison, stable/immutable view references and declared section routes |
| `reconcile PROJECT` | exact adapter/output | none; read current/pending operation state |
| `docs PROJECT --source-root PATH` | explicit replacement document tree | update the adapter's selected document snapshot |
| `docs-reconcile PROJECT` | document sync state | read only |
| `docs-reconcile PROJECT --finish-pending` | exact existing pending sync | finish that recorded pending sync only |

JSON schemas, exit outcomes, parameters and detailed limits are those of the
bundled Atlas workspace and adapter. The facade forwards them in process; it does
not interpret a source done claim as fresh acceptance or create a new controller.
The static signatures live in the bundled `scripts/WORKSPACE_OPERATIONS.json` and
`scripts/OPERATIONS.json`.

## Readable project page

The page combines a hierarchical roadmap, participants, contracts, documents,
relationships, history and coverage. Search keeps a matching work's ancestors
visible. Source work results, roles, scope notes and full event arrays come from
the exact retained owning-matrix document selected by `atlas.presentation`.
They remain separate from normalized Atlas acceptance and activity. A parent's
child summary does not create a new acceptance decision. The complete machine
snapshot and exact owning matrix remain available for export.

For "Open this project's Atlas contracts and roadmap", the current session runs
`atlasctl views PROJECT` once after resolving the existing binding. The result
names the verified observed release, HTML and JSON paths with byte/hash pins,
the pinned source revision when known and supported section routes.
`ARTIFACTS_READY` means the artifacts passed verification; browser presentation
is `NOT_REQUESTED`. The caller uses its existing supported display route and
confirms the actual release and section. A queued opening remains queued until
readback. Do not send this request to the same session.

`views` compares only the selected owning matrix, reporting `freshness.matrix`
as `MATCHED`, `CHANGED` or `UNKNOWN`. It does not refresh sources. Other documents
remain unverified for freshness; `freshness.owning_sources` stays `NOT_COMPARED`.
Successful publication maintains `output/index.html` byte-for-byte with the
current immutable HTML. `views` selects
that stable URL only after verification against CURRENT, otherwise returns the
verified immutable artifact with an explicit qualifier. Reloading a stable URL
shows the latest publication; an old release URL or downloaded HTML remains its
historical snapshot. This is not a source watcher or automatic browser refresh.
Write flows can repair the stable copy after NO_CHANGE, against exact CURRENT pins.
A missing current release returns `NO_CURRENT_VIEW`; invalid registry/binding/output uses the existing
precise refusal. Older releases without presentation route declarations receive
the base URL and manual section names, never invented anchors. If the supported
display cannot confirm opening, deliver the verified HTML/JSON files and state
the specific limitation. The renderer requires no network service.

The page includes all data selected by the project's declared binding and
catalogs. Full catalog inventory, embedded readable files and completeness of
semantic work/contract relations are reported separately. Source writers update
their affected catalogs from actual results before one `finish`; opening the
page does not discover new project files, author missing contracts or infer
dependencies from names. Existing IDs, source versions and full matrix history
remain stable across presentation upgrades.

## Bounded command output

The facade emits less than 32 KiB on stdout. Smaller workspace JSON results are
forwarded unchanged. An oversized result becomes
`agent-os.atlas-cli-summary/v1`: it retains the original status and command exit
outcome, exact raw-result byte count and SHA-256, relevant counts, selected
project/current-release identifiers, and existing immutable view/snapshot
references when available. A bounded sample is explicitly a sample. Omitted
rows are counted and never described as complete output.

The digest describes the full in-memory workspace result from this invocation;
a referenced snapshot is the retained state artifact and is not falsely labeled
as the identical command response. The facade never writes a new receipt just
to reduce stdout. Read-only commands and unchanged refreshes retain their original
effect contract. For large histories follow the existing page cursor; exact
underlying Atlas commands and the immutable snapshot remain available locally.

## A new, existing or undocumented project

After the create/temporary-bootstrap choice or an explicit Atlas integration
assignment, read the project's existing instructions, matrix, documented
objective and writer before registering it. Use the bundled skill's `references/integration.md` for
the applicable onboarding path. For a new native project use the documented
`atlas.py init` method with actual objective, writer and authority. For an
existing owning matrix, bind its exact source through the documented adapter and
refresh; do not run native initialization over that existing binding.

An initial inventory is partial until exact document, goal, module, contract,
work and other declared surfaces are bound. Record unknown or unmapped surfaces
as gaps and create the next precise work item when needed. Update incrementally;
do not repeat a full bootstrap or unchanged checks after each block. Preserve all
available full matrix versions; record a real history gap rather than inventing
earlier revisions from event arrays.

Owning source matrices retain their current writer. The importer alone writes
its projection under the existing lock. Stable work IDs, artifact links,
contract patch/base pins, append-only history and bounded criterion evidence
provide the trace from a requested result to its acceptance. No permanent keeper,
new scheduler, fleet controller or native hook is required.

## Source, resources and distribution

The selected reviewed English-derived public source is under `modules/atlas`.
Original and derived file hashes make the translation boundary explicit. API
identifiers, schemas, status/error strings, filenames and behavior retain their
contracts; human-facing prose is reviewed in English. Its skill
subtree is mirrored to `src/agent_os/resources/skills/atlas`; this document is
mirrored to `src/agent_os/resources/docs/ATLAS.md`. `tools/sync_atlas.py` checks
membership and byte parity by default; writing mirrors requires explicit
`--apply`. Both module and packaged mirrors use the same selected English
version. The frozen original remains its provenance source and is not rewritten.

The new `agent_os.atlas_module` uses the packaged workspace in process, and
`agentos atlas` dispatches before foundation config/update/task processing.
Unrelated native session, messaging, model/provider, capability and hard-pin
behavior remains outside this extension. The readable-view successor candidate
is `0.8.0rc2002+atlas.2`, based on the retained `0.8.0rc2002+atlas.1` module.
Source integration does not install or publish that candidate. Its builder
accepts `--output dist/atlas-readable-candidate` so the previous wheel and
receipts retain their original paths.

The affected checks are deterministic sync, standard-library facade tests,
local-candidate installer tests and the repository's offline wheel/package
verifier. The installer's selected syntax fix accepts lawful local version labels
and their release/wheel/long-shebang forms while preserving digest, exact-current,
immutable payload, user-schema, continuation and quiescence gates. Stable release
builder rules and reviewed release pins are unchanged. Resource presence, a successful
build and a source test do not prove current adoption by an open chat. Install,
load, readback and business acceptance remain separate observed outcomes.

## Preserved foundation prerequisite

The foundation advanced independently to 0.8.0rc2002 during the first Atlas
integration. Its inventory-budget implementation and contracts were preserved
in 0.8.0rc2002+atlas.1 and remain the predecessor for this successor. The project implementation, packaged
project schema, PROCESS and CONTRACTS retain exact prerequisite bytes. Three JSON
records retain every other value while four distribution identity fields are
aligned: CLI distribution_version/release, MCP serverInfo.version and the
Coordinator index core_version. Canonical schema/doc counterparts equal their
packaged records. No absent second project-schema source is created.

Original prerequisite pins and exact selected values remain reviewable in the
Atlas source provenance. The selected input came from the independently matched
installed-package source; this source preservation is not a new runtime test or
permission to downgrade the live predecessor. Stable release pins stay unchanged.

## Recovery and state ownership

Keep the exact operation ID and inspect its durable result after UNKNOWN. Read
the current adapter state with `reconcile`; do not repeat an uncertain mutation.
Retain predecessor source and output versions. Source code rollback does not
roll back project work, a remote effect, documentation acceptance or native
session history. Apply any schema migration or writer transfer explicitly under
that project's current authority and preserve the earlier lineage.

Public resources are host-neutral. Personal roots, actors, source captures,
credentials, project registries and runtime receipts belong in private scopes.
An entry in a public adapter registry never grants external execution authority.

## Bounded old-history requalification candidate116

The workspace exposes explicit `history-requalify` and read-only
`history-requalification-status`, with stable operation and returned cursor.
See [history requalification](../skills/atlas/references/history-requalification.md)
for the versioned API, fixed 32 MiB budget, immutable proof chain and existing
exact checkpoint continuation. Certificate completion is not publication or
acceptance. No automatic monitor, source rewrite or guard raise.


## Exact protected texts and pinned display fields

Explicit v3 restores only predecessor-bound objective/scope_note under original pending PLAN/CAS/AFTER/lineage guards; old v2 unchanged. Five pinned display fields preserve original authority/history and provenance; display_fields shares facade origin/snapshot/finally. Source fixtures do not establish installation or user acceptance. Keep a capable reader after any v3 preparation/UNKNOWN.

The optional `agentos atlas profile` method composes the existing workflow route;
see operating-modes.md for explicit declarations, UNKNOWN and authority limits.
No project registry or intake is read for the READ_ONLY path.

## DN-01.4 finite native document growth

AgentOSrc2032 supports up to1000selected document records, including archived, under the unchanged2MiB/file,16MiBaggregate,8MiBinput,32MiBworkflow/snapshot and48MiBHTML bounds. Schema, runtime and OPERATIONS agree;1001refuses. Existing native indexes append identities while retaining all published versions and immutable releases. No guard override, deletion/repath, mode switch, lazy archive or automatic growth is added. See bundled references/selected-document-capacity.md and data-contract.md. Source/package acceptance, installation, project CAS publication, selector activation and business acceptance remain separate.
