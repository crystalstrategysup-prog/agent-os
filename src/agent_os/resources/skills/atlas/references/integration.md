# Integrating Atlas with AgentOS and active projects

## Contents

- [Shared protocol and project facts](#shared-protocol-and-project-facts)
- [Detect Atlas and select onboarding](#detect-atlas-and-select-onboarding)
- [Project binding](#project-binding)
- [New, existing and undocumented projects](#new-existing-and-undocumented-projects)
- [Procedure registry](#procedure-registry)
- [Open current project views](#open-current-project-views)
- [Active sessions](#active-sessions)
- [Refresh and history](#refresh-and-history)
- [Integration validation](#integration-validation)

## Shared protocol and project facts

Include Atlas in the shared AgentOS: one skill, a local CLI, schemas, standard procedures,
reference instructions and synthetic examples. Connect it through the existing routing
rules for engineering tasks. Preserve the current AgentOS packaging and release process.
Do not create a new global controller, scheduler, database or mandatory daemon session.

| Scope | Location |
|---|---|
| Protocol, schema, validator/builder/viewer and shared routines | Public AgentOS core, following its repository and release rules. |
| Personal rules, private routes and MCP bindings | The existing private user or organization extension. |
| Requirements, all project documentation, contracts, matrix/work records and evidence | The canonical project; privacy follows its contents and rules. |
| History of all authoritative matrices and Atlas snapshots | Immutable project artifacts with source, time, identity and exact hashes. |
| HTML, coverage/diff/packets | Derived views of canonical project data. |

First establish the active AgentOS authority. If the public core is live and the former
private extension is retired, extend the live core and project-local bindings. Do not
restore a retired extension as a second source of instructions or state. Project facts
remain private regardless of whether the shared tool is public.

Do not include real names, conversation URLs, host inventory, private paths, credentials
or project evidence in the public core. Permission to transfer a particular snapshot
does not automatically permit public distribution. Use synthetic examples and
parameterized adapter declarations.

Install and record the shared skill through the current AgentOS process. Publish within
the actual assignment and repository rules. Do not describe an archive as installed in
every session or as a published release.

The current owner instruction takes precedence over an earlier archive-only handoff.
When integration is explicitly authorized, perform it through registered projects,
existing writers and permitted task channels; delivering a ZIP alone is insufficient.
Retain actual evidence for each applied change and all current UNKNOWN states.

Use the owner-approved validation and release process. Do not automatically create a
new CI/CD workflow. If GitHub Actions is prohibited, do not add its workflows or an
equivalent invocation through that mechanism.

## Detect Atlas and select onboarding

A request to develop, resume or continue a project, including a plain-language
request such as "continue development of PROJECT", starts with an Atlas check.
Read the selected project's current instructions and exact registered binding;
check its local Atlas manifest or declared custom location. Use only the known
project root and registry. A missing CLI/registry is not proof that the project
has no Atlas, and an unreadable or inconsistent binding is UNKNOWN, not absent.

**Atlas exists:** read the binding and current writer, select the already assigned
work, and invoke its declared start/refresh-and-packet routine. For a registered
WM-UI project use `atlasctl start PROJECT --work ID`; for another native binding
use its documented `session-start` route. Continue the original task. Do not
bootstrap a second matrix, reopen unchanged accepted work or restart the session.

**Atlas is confirmed absent:** reuse an explicit prior choice for this project
and task scope. Otherwise offer exactly these three choices before Atlas writes:

1. **Create Atlas before development.** Establish the smallest truthful binding,
   initial inventory, writer and first work packet, then continue the task.
2. **Continue this task explicitly without Atlas.** Record that scoped choice in
   the existing task checkpoint; continue the authorized work and its applicable
   documentation/contract obligations. Do not initialize Atlas implicitly.
3. **Continue the task and start a separate temporary Atlas bootstrap session.**
   The main session keeps the task and current writer ownership. Give the
   temporary session a bounded inventory/binding/history deliverable, separate
   write scope and return checkpoint; integrate its reviewed result through the
   main writer, then close that temporary assignment. No permanent keeper,
   scheduler or parallel status owner is created.

Use the authorized native delegation/return route for the selected third choice;
the skill does not itself launch or message sessions. A routine read-only
question does not trigger this onboarding choice. The following project paths apply after that choice.

For the temporary-session choice, reuse the existing project/native admission
and return contracts. The brief names the exact root, canonical matrix writer,
source/doc read set, isolated writable paths, known history, inventory gaps,
criteria, parent and one return checkpoint. Existing shared files stay with
their current writer. The main session may continue independent product work
with its established scope; it does not wait for irrelevant historical cleanup.

The temporary worker returns prepared bindings/document links, exact source
pins, preserved full matrix versions, explicit gaps and validation evidence.
The main session reviews the result, performs shared-file integration once and
records adoption. A bootstrap receipt is neither current product acceptance nor
evidence that every document or old matrix has been recovered. Finish the bounded
assignment through the existing native route; do not leave an always-on keeper.

## Project binding

For a qualified WM-UI source, follow `upstream-adapter.md`: record the UPSTREAM binding
and invoke the separate `refresh`. It preserves the authoritative sources, creates a
projection, then makes it available to the core routines. No preceding `init` is needed.
With an active UPSTREAM binding, refresh the projection before reading a work packet.

For other cases, when `.atlas` is absent, use `init` from `operations.md`. Supply the
known project ID/title/objective/writer/authority and mode. It creates INITIALIZED_PARTIAL
with ATLAS-BOOTSTRAP and six domains with `exhaustive=false`, preserving existing files.
If `.atlas` already exists, it returns ATLAS_ALREADY_EXISTS_RECONCILE; first reconcile
the current binding. Do not delete control state merely to repeat initialization.

1. Find the registered project roots, current requirements, authoritative matrix and
   writer. Use the existing applicable inventory or perform a scoped project bootstrap.
   Do not survey an unchanged environment again merely because Atlas is being installed.
2. Create `.atlas/project.json` or the agreed manifest name. Declare the exact document
   manifest, per-work files, coverage registry and matrix history according to the data
   contract. Preserve stable IDs, namespaces, canonical paths, roles and prior evidence refs.
3. If a matrix exists, obtain its normalized projection from its writer. The existing
   source retains authority over status and ownership; do not edit the projection as a
   second matrix.
4. If there is no matrix and creating one is part of the assigned integration, designate
   one canonical set of work records and one writer for shared resources. Include current
   substantive work; identify unknown earlier history as a gap.
5. Register the entire project scope: documents, goals, modules, contracts, work surfaces,
   all work items, authoritative matrices and their available historical versions. Pin
   exact inventory bindings, source times and explicit unmapped/UNKNOWN gaps.

Use one authoritative route: an existing matrix with a projection, or canonical work
records for a new project. Documents remain in their existing locations; Atlas links
them to work and versions. Full coverage is valid only for a demonstrably complete,
declared project inventory. A few selected documents do not establish project completeness.

For already assigned documentation/tooling integration, apply the authorization within
the registered scope. Do not request repeated confirmation for routine, reversible binding.
If a missing input affects a particular step, complete the independent useful work first,
then clarify only that input. Authorization for Atlas does not authorize new product effects.

## New, existing and undocumented projects

At the start of assigned development or a same-project continuation, perform the
Atlas detection above. If it exists, load/start it and continue. If confirmed
absent and no applicable explicit choice is retained, present exactly the three
choices above. Missing requirements or module/API contracts remain specific
gaps; they do not authorize an implicit Atlas bootstrap after a no-Atlas choice.

| Initial state | Onboarding action | First verifiable result |
|---|---|---|
| New project with an idea or assignment | Record the objective, constraints, criteria, minimum module boundaries and first matrix; designate a writer; declare the inventory of future artifacts. | A minimal working binding and the first executable work item. Unresolved API/design decisions remain explicitly open. |
| Existing project with documentation/matrix, without Atlas | Read the applicable inventory; link existing canonical documents, obtain the writer projection, preserve available matrix history and configure routines. | Navigation and tracking over the existing canonical sources, without rewriting them wholesale or replacing the writer. |
| Existing project with Atlas | Run `session-start`, check declared coverage and actual changes, then continue the required work. | The required packet and a plan limited to the relevant delta, without repeating bootstrap. |
| Existing project without sufficient documentation | Perform a bounded inventory of all registered source/work surfaces; separate observed AS_IS from future design; open work for specific missing contracts/documents. | An honest partial map, exact known API/source bindings, bounded gaps and the next useful step. |

For an undocumented project, establish actual entrypoints, modules, state owners,
interfaces between them, callers and existing build/deploy commands from available
primary sources. Record UNKNOWN for inaccessible facts. Source availability does not
establish installed/runtime state. Do not infer a mandatory new API version, invented
defaults or architecture from directory names.

Give every material gap a stable work ID, exact subject, minimum read set, expected
document/contract, criterion and owner. Continue authorized work whose inputs are already
sufficient. A missing Atlas binding does not require stopping the whole project until
every historical detail has been documented.

Within the selected create/temporary-bootstrap branch or an explicitly assigned
Atlas integration, create the necessary local documents and binding without
asking again for that same authorization. In the explicit no-Atlas branch,
continue its scoped task without creating Atlas. Qualify only a genuinely new,
unauthorized scope or effect separately. Preserve the established canonical sources;
do not automatically migrate directories wholesale or rewrite history.

Define module boundaries, API methods, composite scenarios, independent builds and
compatible deployment according to `modularity.md`. If the project does not yet support
a property, show the gap and a bounded next work item. Declaring a command alone does
not establish independent builds or fast deployment.

## Procedure registry

Configure `session-start`, `finish-block`, `integrate`, `reconcile`, `project-audit` as
static, named compositions. Declare typed parameters, preconditions, ordered methods,
outputs, effect scope and reconciliation. Use one local CLI and specify its exact
syntax in the data contract.

For a bound WM-UI project, configure the current writer's opt-in
`.atlas/WRITER.json` once: exact source/pointer, shared source lock, permitted
prepared document paths and checkpoint recovery. Use `checkpoint PROJECT --record
RELPATH` for advanced prepared records; daily work uses the typed `work` method
in `workspace.md`, which pins inputs automatically. Use `checkpoint-reconcile PROJECT
--operation ID` for an uncertain outcome. See `workspace.md` for the implemented
contract. A missing writer profile is a specific integration gap; repeated
refreshes cannot replace a missing source event. Preserve the established writer
method until this explicit profile is adopted by that same writer.

For host steps, maintain a private adapter to the existing owner MCP: exact method ID,
explicit target, required parameters and result schema. Obtain values from the actual
available methods and registered project bindings. Do not invent callable names,
permissions, successful receipts or replacement routes.

Once configured, pass project/work/operation parameters to the procedure. There is no
need to select the connection method again or manually reconstruct the method sequence.
Change the registry only when a binding/contract actually changes or a gap is established;
retain an event with the reason and previous version.

Distinguish the plan prepared by the local CLI from actual execution of its external
steps. The authorized current executor invokes them through the existing adapter and
retains real primary receipts. Declaring a routine does not bypass approvals, execute
host effects by itself or replace an UNKNOWN result with a prediction.

## Open current project views

An instruction to open this project's Atlas contracts and roadmap belongs to
the session receiving it. Resolve its existing project/binding once and call
`agentos atlas views PROJECT`; use the known explicit registry when required.
Do not self-forward the request or create a permanent view/document keeper.
The exact read-only API and legacy routes are in `workspace.md`.

Treat `ARTIFACTS_READY` as verified retained HTML/JSON. The read compares only the
selected owning matrix; other source documents are not compared. Use a supported,
authorized interface to open and confirm the intended release/section. Queued or
sent is not opened. If opening
cannot be confirmed, deliver the verified HTML and complete JSON through the
supported downloadable-file route and report the actual status. Do not bypass a
denied opening route. Preserve `NO_CURRENT_VIEW`, UNKNOWN and partial coverage.
Use the stable current-view URL only when the read method verifies it against
CURRENT. Its reload shows the latest published bytes. An immutable release URL
or downloaded HTML remains historical; neither form watches the working source.

## Active sessions

Give each existing main project session the detection rule and three absent-Atlas
choices through its already authorized instruction/return route. Record actual
consumer read/adoption separately from installed files. Preserve ongoing
assignments, current writers, task IDs, checkpoints and unresolved UNKNOWN states. Do not require a restart, context reset, new queues/session IDs or
reacceptance of unchanged results. Expired activity does not authorize resource reassignment.

The integrator should read the permitted existing project/session registry and prepare
a short binding note for each accessible active session:

```text
Atlas version / exact source / operation registry:
Project / canonical manifest / owning matrix:
Current work ID / writer / permitted scope:
Accepted results / open UNKNOWN states / coverage gaps:
Next begin/dispatch/progress checkpoint before waiting / required delta:
```

Transmit it only through task channels and coordination mechanisms already authorized
by the owner. The skill and CLI do not themselves send messages, connect to sessions,
create actors or change the scheduler.

Preserve the active task and adopt the cycle at its next begin, dispatch or progress
boundary, before waiting. Record already-running work as observed now, with its
original history; do not invent a past start time or wait for final completion to
publish it. The existing writer uses its configured checkpoint or source method
and `finish`; workers return prepared deltas. Update shared files sequentially.
If a writer handoff is needed, first reconcile completed and unknown operations,
exact outputs and the recipient, then record the transfer.

| Integration status | What is established |
|---|---|
| INSTALLED | Files for the specified skill version are installed at the selected location and pinned by exact hashes. Reading/use by an active session is not yet established. |
| ADOPTED | A scoped receipt establishes reading or use of the specified version by an active consumer: version/hash, session/work identity and project binding. |
| NEXT_CHECKPOINT | The current writer retains the task; the next begin/dispatch/progress boundary before waiting and required delta are known. |
| BLOCKED | The exact reason, scope and condition for continuation are stated. |
| UNKNOWN | Current availability or adoption is not established. |

Qualify an ACK by its content: an installation record establishes INSTALLED; actual
consumer reading/use establishes ADOPTED. A file, shared routing or a transmitted handoff
does not establish that an active session has read this version. No such ACK accepts
code, a contract, runtime behavior or a product. A missing ACK does not establish that
a session has stopped or transfer its write ownership to another agent.

## Refresh and history

Configure source/index paths and supported extraction formats once for the
declared directories. Extract every record selected by that catalogue contract
and retain its manifest pins. Report full publication inventory, documents
selected in the view and semantic coverage separately. An inventory count alone
does not prove that every work/module/patch has an established relationship.

Begin, actual dispatch, progress, result and blocker are substantive checkpoint
boundaries; publish their new facts before waiting. The current owner prepares
affected source/catalogue/document changes from real work and evidence. Update
semantic catalogs/bindings through their existing declared method; `work` saves
the permitted matrix/document delta and publishes once. Use `finish` once when
the existing source method already saved the delta. An unchanged wait adds
nothing. `views` only reads that publication.
The present methods do not automatically discover every future file or author missing semantics:
extend the declared binding for a concrete new scope/gap through its current
writer. Do not promise an unimplemented auto-gather operation or repeat a broad
host inventory to open the page. Keep immutable publications and prior binding
history; avoid new logical document IDs merely for a new day or view.

After bootstrap, use known changed paths and explicitly affected relationships. `impact`
shows declared dependencies; a missing edge does not establish that no real dependency
exists. Add a newly uncovered area to a scoped inventory and a bounded work item.

`discover --under <relative-path>` returns candidates only from the selected directory.
Do not infer a current contract, applied patch, completed work or author from a name,
mtime or heading. The writer qualifies role and provenance. A missing required contract
creates an exact work item with subject, inputs, outcome, criteria and owner.

Prepare exact references through `pins`; have the established writer update the manifest.
Preserve every previously obtained version of every authoritative matrix, including its
source times and hashes. Do not present Atlas snapshot history as complete project
history when earlier matrices have not been obtained. Mark unavailable history as a
gap and identify the exact next source for recovery.
The WM-UI adapter accepts a pinned semantic catalogue with logical doc/module/contract
IDs, explicit work bindings, source result context and patch/base references. Connect
an existing INDEX/catalogue through a deterministic builder once, then update it for
substantive changes. Unbound work remains a visible gap; installing Atlas does not
invalidate prior scoped results or require a blanket rerun.
Write `.atlas/project.json` and import state only through the importer under `IMPORT.lock`.
Participants change the authoritative source through its established writer and read
the projection. A hash check before atomic rename does not protect against an unrelated
writer that ignores this lock; every updated active-session route must follow this protocol.

For `build`, choose the output, release ID, UTC time and previous manifest SHA. On a
repeat or UNKNOWN, reconcile the original identity. Do not activate an orphan without
reconciling the original operation; do not create a release for unchanged subject state.

## Integration validation

Perform a real scoped pilot: a current work item exists, its writer supplies one delta,
Atlas links it to a document/contract/evidence, and the next agent recovers the required
context through the standard procedure. Check that:

- canonical IDs, prior events, matrix revisions and exact evidence are preserved;
- objective, criteria, writer, next action, coverage and gaps are visible;
- proposal/accepted/applied, source/runtime and assigned/activity remain distinct;
- each shared resource has one writer and no parallel authoritative matrix exists;
- the routine uses pinned methods/parameters and distinguishes plans from actual receipts;
- a scoped change does not trigger a full baseline without a reason;
- repeating without changes neither adds events nor extends activity.

Qualify DOM/static checks by their actual scope. Perform visual validation through an
authorized route; do not bypass a denial with another preview or server. Distinguish
local tool readiness, actual project integration, full coverage and user acceptance.

Then apply compatible bindings to the remaining assigned projects through their current
writers. List actual integration, pending checkpoints and exact blockers/UNKNOWN states.
Do not claim every session is updated merely because a shared SKILL.md exists.

## Machine limits

Observe the current limits: 1000 works, 200 selected docs, 32 MiB of workflow inputs;
DN documents have a 16 MiB total limit and a 2 MiB per-file limit. Exceeding a limit
is rejected without truncation. In a projection archive, the current page selects only
current docs/cards and new complete matrices; previous immutable snapshots and originals
remain in the chain. An ordinary pass verifies one parent and the new sources. For an
explicit archive audit, read `history` using `next_cursor`; `VERIFIED_PAGE` does not
mean a complete chain audit or a new read of old source bytes. Native events and
evidence continue to follow strict history rules.
For larger projects, split project/module views with a shared coverage map, or qualify
a limit change separately. Do not hide raw documents to obtain COMPLETE. Switching
between native and projection modes within an existing output chain is prohibited;
it requires an explicit new migration lineage. An open work link does not replace the
document for a missing contract.
