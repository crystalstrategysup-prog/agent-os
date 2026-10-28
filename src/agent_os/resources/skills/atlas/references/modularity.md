# Modules, explicit APIs, and compatible deployment

## Contents

- [Module boundaries](#module-boundaries)
- [API method registry](#api-method-registry)
- [Composite scenarios](#composite-scenarios)
- [Independent builds](#independent-builds)
- [Compatible deployment](#compatible-deployment)
- [Measuring speed](#measuring-speed)
- [Acceptance and gaps](#acceptance-and-gaps)

## Module boundaries

Use `assets/architecture-template.json` and `assets/module-template.json` from the
skill root as synthetic content templates. Their DESIGN/NOT_RUN values and
required project bindings are not source/runtime claims about a real project.

Describe each module as a defined responsibility with explicit inputs/outputs,
a state owner, and declared dependencies. Allow a modular monolith, packages
within one repository, and separately deployable services. Extract a module into
a separate service when actually needed, not merely because Atlas is present.

Fix a substantive required contract for each module:

| Field | What to establish |
|---|---|
| Identity/purpose | Stable module ID, one clear responsibility, authoritative source, and documents. |
| State owner | The data/states the module changes, their sole owner, and the transaction boundary. |
| Interfaces/callers | Explicit provided and consumed methods/events; actual callers and dependencies with exact references. |
| Boundaries | Permitted cross-module calls, errors, lifecycle, and restrictions on directly changing another owner's state. |
| Build unit | Named build/check methods, complete declared input set, dependencies, artifact identity, and evidence. |
| Deployment unit | What is actually deployed together, required compatibility, migrations, readiness, cutover/reconcile, and rollback. |

Do not treat a directory as an independent module based on its name alone. If
ownership/interfaces/build are not yet established, preserve UNKNOWN explicitly
and an exact work item to qualify the boundary. Allow a shared deployment unit
for a modular monolith; do not promise an independent runtime rollout for every
internal package when the actual deployment is one application.

## API method registry

Cover HTTP, event/RPC, in-process interfaces, and system methods when they form
module boundaries or are used by composite scenarios. Account for all such
methods in the declared inventory; a list of user-facing buttons is not a
complete API inventory.

Record the following for each method:

| Information | Required precision |
|---|---|
| Identity/version | Stable logical method key; actual version/variant and exact source definition. Do not invent a missing version. |
| Invocation | Kind, exact endpoint+verb or event/RPC/function name, handler, and invocation method. |
| Inputs | Fields and types, required/optional, defaults, omitted distinct from explicit null/false/empty, and allowed enum/range/shape. |
| Outputs | Success shape, types/fields, optional/nullability, and raw return semantics. |
| Errors | Exact code/type/status, triggering conditions, retry semantics, and possible effects on error/UNKNOWN. |
| Auth/tenant | Caller, role/tenant/context, and authority source; do not put credentials in the public registry. |
| Effects/owner | Modified state, transaction/commit boundary, external/provider effects, and their owner. |
| Idempotency/reconcile | Stable key, repeat behavior, qualification of lost ACK/UNKNOWN, and exact observer/reconcile path. |
| Callers/compatibility | Calling modules/scenarios, required versions, and compatibility conditions. |
| Evidence | Documentary/source/installed/runtime/use scope, exact refs/hashes, and limits of the current read-set. |

Preserve runtime class/exception identity where compatibility depends on it.
Do not replace a legacy alias/reference with your own redefinition. Qualify
unknown requiredness/default/nullability explicitly; missing information does
not mean false/null.

Separate AS_IS from a proposal. To change a method, create a patch against an
exact base, identify affected callers and required checks. An accepted proposal
does not switch the effective API. Establish application through the writer's
result and exact readback; retain the old version.

## Composite scenarios

Describe a repeatable useful result as a named sequence of explicit methods.
The scenario contains typed parameters, preconditions, ordered steps/permitted
branches, bindings from one step's outputs to another's inputs, a postcondition,
evidence, and a stop/reconcile condition.

Use the existing owner of each operation. Do not create a second state, queue,
or scheduler for orchestration when the sequence can call existing methods.
Make transfer of results between methods explicit: data/ID/version/nullability
and errors must match or have a declared adapter. Do not substitute a similar
port for a missing one.

Register repeatable build/check/deploy/reconcile/rollback methods with parameters
and actual bindings to existing local commands or MCP. A logical method key
alone does not make a command callable. Mark an unavailable method as a gap;
do not invent a new access chain on every run.

## Independent builds

Make the build unit reproducible from declared inputs: source/dependency revisions,
toolchain, lock/config, generated inputs, and required contracts. Do not include
secret values in the manifest; use authorized selectors/references and a qualified
environment. Fix the command, parameters, and outputs in the method registry.

For a package/module, establish that it can be built and meaningfully checked
separately, without manually copying a neighboring project or relying on
undeclared hidden dependencies. With a shared monolith build, state truthfully
which units are independent and which require the shared artifact. Record missing
independent-build support as a bounded task; do not claim it by declaration alone.

Link every produced artifact to exact source/input identities, version, digest,
build receipt, and check scope. Reuse cache only when relevant inputs/conditions
match. Do not present a cache hit as a new test run.

Check the affected dependency closure and compatibility contracts. Do not rebuild
independent modules without a reason. Run a shared integration check when it
addresses a specific composition risk or an accepted gate requires it.

## Compatible deployment

For a deployment unit, declare the target/environment, existing executor, exact
artifact, config compatibility, upstream/downstream API versions, state/schema
owner, and transition order. Include required preconditions, readiness/health,
observable result, cutover identity, UNKNOWN reconciliation, and rollback path.

Plan compatibility between old and new versions during the transition. For schema
changes, use compatible expansion and a separate later removal of the old form
where applicable to the project. Execute migrations through one owner using
the established mechanism. Do not implicitly change the state owner or introduce
a second ledger for a new deployment.

Check whether the old artifact can work with the already changed schema/data.
Do not treat restoring a binary as sufficient rollback for incompatible state.
If rollback is impossible, say so explicitly and prepare an accepted recovery/
forward-fix strategy. Do not perform a destructive reverse migration as an
automatic step.

Fix the boundary of successful deployment: artifact installed, required processes
ready, and the relevant runtime scenario confirmed. These are separate evidence
items when checked separately. Source/compile PASS establishes none of these
facts automatically.

## Measuring speed

Optimize the repeatable build/delivery path; do not promise the same number of
seconds for every environment and change. Define measurement boundaries first,
then retain actual cold/warm timings with the artifact, target, cache state,
and measurement method.

| Measurement | What to record |
|---|---|
| Cold | Which dependencies/artifacts/cache were absent in the selected test environment; actual stage durations. |
| Warm | Which exact cached inputs/artifacts were used; which stages actually ran and their durations. |
| Full rollout | From an explicitly named start to the selected readiness/functional result; whether build, transfer, migrations, and cutover are included. |
| Rollback/recovery | The actual operation checked, state compatibility, duration, and evidence scope, or NOT_RUN. |

Separate build, transfer/pull, migration, start/readiness, and functional
confirmation when this helps identify the cause of a delay. Do not combine
incomparable clocks from different hosts as an exact end-to-end result. Do not
erase production caches for a cold measurement; use an appropriate authorized
environment or truthfully leave the measurement NOT_RUN.

Report the budget/target time separately from observed values. Do not fill
unmeasured stages with estimates presented as actuals. Accept an optimization
against a comparable scenario and environment, preserving prior receipts.

## Acceptance and gaps

For each module, show its boundary/state owner; all declared API methods/callers;
build unit and actual evidence; deployment contract/compatibility/rollback;
measured cold/warm timings or an explicitly open work item. Link everything to
a criterion and exact basis.

Accept a local tool, modular source candidate, or contract within its declared
local scope. Runtime rollout and measurements may remain separate open work.
Atlas must show this remaining work without a false overall PASS and without
requiring production for completion of every local task.
