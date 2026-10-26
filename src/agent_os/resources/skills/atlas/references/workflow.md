# Atlas work cycle

## Contents

- [Unit of work](#unit-of-work)
- [Responsibilities](#responsibilities)
- [Start, delegate and wait](#start-delegate-and-wait)
- [Standard procedures](#standard-procedures)
- [States and activity](#states-and-activity)
- [Contract and patch](#contract-and-patch)
- [Evidence and checks](#evidence-and-checks)
- [Completeness and history](#completeness-and-history)
- [Completing a block](#completing-a-block)

## Unit of work

Choose a complete change with an observable result: an implemented port, a fixed
bug, an accepted contract, a prepared source candidate, or a specific uncertainty
resolved. Link it to the objective and completion criteria. Account for all
substantive project work, including audit, acceptance, integration, and documentation;
do not create a separate row for each command, file read, or message.

For a new project, start with the objective, constraints, and observable result.
Use the owner's instruction within its scope. In an existing project, use the
active specification/contract and stable IDs without seeking renewed agreement
on unchanged conditions. Identify unknown conditions that affect the decision explicitly.

Plan a hierarchy to a useful depth: objective → independent outcomes → executable
steps. Bind dependencies to the required result or artifact version. A change to
one dependency does not halt all independent work.

## Responsibilities

| Role | Action |
|---|---|
| Outcome owner/coordinator | Link work to the objective, define scopes and criteria, record begin/dispatch promptly, and integrate new facts before waiting. |
| Implementer | Return actual start/progress/result or blocker for the assigned work; maintain material documents/contracts within its write scope and provide primary evidence. |
| Writer for a specific resource | Serialize prepared changes to a shared file/matrix, publish its new facts before waiting, check the previous revision, and preserve history. |
| Reviewer accepting the result | Check criteria in the required scope and bind the decision to the exact basis. |

One agent may perform multiple roles when the criteria permit. Require independent
acceptance where a criterion or project process calls for it. Do not appoint a
permanent separate documenter solely for Atlas.

Assigning work does not grant rights to another actor's resource. Preserve one
writer for a shared file and an explicit handoff. Give parallel implementers
separate authorized artifacts and deltas; the current writer incorporates them.

## Start, delegate and wait

`start PROJECT --work ID` restores context; it does not create a source begin event.
The main writer records an executable step's actual beginning or delegation
immediately, using its existing work ID, responsible actor and real dispatch
outcome. With the explicitly configured writer profile, run
the typed `work` method with operation/work IDs, phase, executor, note and next
action. It pins current inputs, saves one prepared source/document delta and
refreshes the view once. Exact flags and recovery are in `workspace.md`; the
advanced `checkpoint PROJECT --record RELPATH` accepts an already prepared record.

Before waiting after a new fact, publish that checkpoint. While waiting, integrate
available results and prepare affected documentation from actual work; continue
independent authorized work. A repeat observation with no change reuses the earlier
checkpoint, without a new event, release or broad check. Workers return deltas
through their existing authorized route; they do not become shared-matrix writers.
If the source was already committed by the established project method, `finish`
publishes it once. Do not run an extra finish after a completed checkpoint.

Keep dispatch, receipt and confirmed execution distinct. A queued or uncertain
dispatch is not activity evidence; record its actual outcome and reconcile the
original operation instead of resending. Checkpoint does not send messages or
author document semantics. It only commits the declared prepared changes. A
retry of `work` with the same operation ID and arguments reuses its original
record/time/pins; changing those arguments under the same ID is refused.

## Standard procedures

Use the named sequences in the operation registry. Take parameters and method
order from the data contract and project binding. Once configured, use one CLI
entrypoint: the agent need not reselect SSH, the authorized MCP method, and its
call chain.

| Procedure | Input and expected result |
|---|---|
| `session-start` | Selected project/work → verified relevant packet, current writer, criteria, blockers, and next step. |
| `finish-block` | Exact work/document inputs already prepared by the writer → one-load validation/CAS output or NO_CHANGE. |
| `integrate` | Inputs after the current writer incorporates deltas → the same cycle and a new snapshot only on change. |
| `reconcile` | Selected local output → exact current immutable snapshot; remote operation readback is performed by a separate declared adapter. |
| `project-audit` | Exact registered inventory → coverage, unmapped/UNKNOWN gaps, and bounded work to close them. |

Preserve the objective, typed parameters, preconditions, method order, outputs,
effect scope, and reconciliation path for each procedure. Bind host steps through
a declarative adapter to exact MCP methods already available. The adapter/registry
does not create permission; a missing required binding produces a specific gap.
Do not replace it with an unauthorized alternative connection.

The local engine reads/validates/compiles selected data. A prepared plan in stdout
is not execution of a host step. The current authorized actor executes it through
the existing adapter; the receipt must distinguish a plan from an actual result.

Within `finish-block`: confirm the outcome and scope → make the substantive change →
update the material contract → check the affected risk → prepare one delta.
For `integrate`, verify the current basis and previous snapshot, preserve old
events, then update the canonical source and projection. If there is no substantive
change, finish with a no-op.

## States and activity

Use machine values from `data-contract.md`. Main path:

| Transition | Sufficient basis |
|---|---|
| PLANNED → DOING | An implementer is assigned, outcome and bounded scope are defined, and dependencies permit this step. |
| DOING → REVIEW | The result is prepared, with exact outputs and qualified evidence pinned. |
| REVIEW → ACCEPTED | All mandatory criteria are accepted for the current basis within their required scope. |
| Open work → BLOCKED | The exact reason, affected scope, resumption condition, and next owner are stated. |
| BLOCKED/PAUSED → resumption | The required condition/decision is available; the event preserves the reason for the change of direction. |

Preserve UNKNOWN for an unestablished imported state. Record cancellation and
pause as decisions. When an accepted result changes, open the next required
step or revision with an event; earlier acceptance remains historical.

Display assigned implementer, journal status, and activity separately. Fresh
activity requires evidence for a specific actor and bounded step. A snapshot
or refresh does not confirm it. Expiry produces EXPIRED: current activity is
unverified, while recorded DOING and ownership are preserved. The active-only
filter requires fresh evidence. For WM-UI, a normalized DOING step needs exactly
one known executor; parents remain summary work and acquire no artificial activity.
Do not create a heartbeat service
merely to show a green indicator.

ACTIVITY evidence requires `check_id` and `valid_until`; the cutoff matches the
activity record and the window is no longer than one hour. Other evidence also
requires `check_id`. The latest typed state event must match the current work
state. An UNKNOWN actor or a later relevant FAIL/UNKNOWN does not support current acceptance.

## Contract and patch

Give a proposal an exact target, base revision/hash, and the semantics being
changed. Link it to work, criteria, and affected consumers. Preserve defaults,
omitted/null behavior, errors, auth, and state owner when they are in scope.

Distinguish an accepted proposal from an applied result. Apply a patch through
the target writer after verifying the base; pin the exact result and readback
evidence. On conflict, do not choose a winner by date. Define the sequence or a
new agreed change; preserve earlier proposals and decisions.

Do not invent a contract patch for a document without behavioral changes. Keep
a source candidate UNAPPLIED if it was not applied. Turn a missing required
contract into an exact work item: known subject, required inputs, outcome,
criteria, and owner.

## Evidence and checks

Link evidence to the claim, exact relevant inputs, scope/environment, time,
actor, and primary receipt. Distinguish documentary description, source review,
isolated tests, installed state, runtime, and user acceptance. Determine needed
levels from the task; do not introduce a universally required ladder.

Accept local work against local criteria. Do not require production for a
document, tool, or unapplied candidate. A local result does not satisfy a
separately open runtime criterion.

Reuse an earlier receipt when its relevant inputs and conditions remain
applicable. Preserve its date and scope. Qualify read-set completeness; do not
treat an unknown dependency as matching. A change to a criterion or substantive
bytes does not inherit acceptance from the old basis.

Repeat a check for a material reason: changed input/criterion/environment, a new
defect, expired applicable freshness, or a required gate. Record the reason.
New HTML, a renamed report, and a new session alone are not reasons to repeat
the earlier suite.

For an UNKNOWN outcome, call `reconcile` with the original identity. A missing
ACK does not prove absence of an effect. Preserve the exact refusal and resumption
condition; do not pass the same action to another agent or route to bypass a restriction.

## Completeness and history

Perform bootstrap against an exact project inventory once, or reuse an already
verified applicable inventory. Cover documents, goals, modules, contracts, work
surfaces, all substantive work, and every existing authoritative matrix.
Establish completeness through exact bindings and the absence of unexplained
unmapped/UNKNOWN gaps.

Thereafter update changed paths and affected links. Repeat a full audit when
scope/inventory changes or a specific gap cannot be closed through a scoped delta.
Keep a partial set partial; registration alone does not make it complete.

Preserve every received version of every matrix with its identity, source time,
hashes, and provenance. Atlas-generated snapshot history does not replace the
history of prior authoritative matrices. Mark unavailable earlier versions as
a gap; do not reconstruct them as actual. Do not rewrite events; record a
correction or changed interpretation in a new event.

## Completing a block

Leave one short record containing the items relevant to the result:

```text
Work / result:
Changed artifacts / material contracts:
New evidence / scope:
Reused evidence / applicability:
Coverage delta / open gaps:
Remaining work or blocker / resumption condition:
Next responsible actor / action:
```

Do not copy entire logs. Reconcile the same delta without applying it twice.
A substantive work record change requires an event; a no-op creates none.
Stop maintenance when the result is verifiable and the next step is clear.
