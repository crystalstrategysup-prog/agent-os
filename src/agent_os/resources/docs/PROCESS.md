# Process: direct reading, documented changes

Read the selected source's `pyproject.toml` or installed package metadata for the
package version, and the selected release manifest for release identity. Version
metadata does not establish publication or host adoption. RC-labelled sections
below are retained historical records, not current installation or publication
claims.


## Historical indexed handoff successor0.7.0rc1

Every new/resumed mutable entry requires an accepted library handoff before CLOSED/CHECKPOINT. Checkpoints record unfinished work; legacy closed history is preserved. See [indexed handoff](INDEXED_HANDOFF.md).

This describes the candidate `0.8.0rc2` foundation. Native AgentOS hooks are excluded: do not
create, enable, trust again, or restore them during rollback. Older F01–F08
stages are historical evidence, not permission to reintroduce prompt interception
or a Stop hook.

## 1. Classify the action before registering a task

Answer ordinary questions, search, perform read-only audits, and discover
available APIs directly under existing read authority. These requests require no
`init`, `questions`, `enter`, `observe`, answers file, active profile, or closeout.
An unregistered working directory is acceptable.

An inherited `AGENTS.md` is a short router: scope, universal limits, and links to
relevant documents or skills. Read detailed architecture, operations, and dated
history on demand. If a file is truncated, report the risk and propose a separate
index change; a read-only request does not authorize rewriting instructions. A
file size target is editorial guidance, never a Stop gate or reason to refuse a
normal question. Creating a requested report file is not itself a product change;
changing source, configuration, or runtime is a product change even when called
an audit.

The optional `workflow route --kind audit` returns `FAST_PATH` without reading or
writing user data. `--kind project-change` or `--effect local-project-write`
returns `DOCUMENTATION_FIRST`. Effects such as `deploy`, `external-send`,
`production-write`, `runtime-write`, `db-write`, `credentials`, and `destructive`
return `BLOCKED` with the category of authority needed. This classifies the
declared effect. It neither interprets natural language nor proves authorization.
Even this optional routing command is not a prerequisite for a read-only answer.
Access to another person's data still needs its own authority.

## 2. Prepare a real change

Read the README, dossier, roadmap, latest stage and result, architecture, and
contracts for the affected components. Examine an unknown existing project
read-only before scaffolding. Reuse verified facts from current documents and
the owner's instruction; ask only about material unknowns. Load profiles only
when their verified owner or host context matters. A missing or stale selection
does not block unrelated reading, and dated host claims must not be used as live
facts without revalidation.

Prepare the complete plan for the current level and the declared next stage.
The project-level plan covers the route to the final result; module and
microprocess details are expanded when that level is selected. Start with a
connected working stand, then deepen its parts under **Project development**
below. Documentation and readiness describe the current level and stage; an
early stage may deliberately deliver a scaffold with explicit stubs.

When project metadata is absent, `project init --root P --name N --type TYPE
--context context.json` creates `.agentos/project.json` and draft docs. The
context supplies `purpose`, `current_state`, `boundaries`, and `constraints`.
Then use the explicit workflow session and turn:

```sh
agentos project questions --root P --answers answers.json
agentos project enter --root P --session S --turn T --answers answers.json
```

S and T are stable identifiers chosen for the CLI workflow, not simulated native
client events. Use client identifiers only when actually known. Context, answers,
and documents may be prepared before READY; that does not permit product writes.
JSON context, answers, and review inputs support `-` for stdin:

```sh
cat answers.json | agentos project enter --root P --session S --turn T --answers -
```

Stdin is limited to 4 MiB, must contain an object, and rejects duplicate keys.
Normal input paths must be regular non-symlink files; `/dev/stdin` does not bypass
that rule.

## 3. Continue without repeating known questions

```sh
agentos project questions --root P --resume-task TASK
agentos project enter --root P --session S --turn T --resume-task TASK \
  --reuse-answers --answers current-authority.json
```

`current-authority.json` supplies fresh `authority`; the other answers are reused
only for the same scope. Authority is never inherited. A changed scope requires
a complete new answer set without `--reuse-answers`. `--interactive` asks only
for missing answers. Resuming a task increments its revision and clears READY
and old check evidence. CLOSED is immutable; begin a new task.

Only one task may be active in a project. After CHECKPOINT or CLOSED in the same
workflow session, use `project next-turn --root P --session S --from-turn OLD
--turn NEW --task TASK`, then enter explicitly. An active binding to another
task blocks accidental entry. Unbound old observations do not block entry.

When a different task has since become active in the former project, run this
same `next-turn` command at the former root with the exact old terminal task,
session and previous turn. The old task must belong to that project and retain
that session/turn binding; the different active task must exist in the same
project. The existing exact receipt/root/task/status checks and project-then-turn
locks still apply. Only the old workflow receipt advances to INTAKE_REQUIRED;
both tasks, project active pointer/revision, READY and check evidence are left
unchanged. Then enter the intended isolated project explicitly. This does not
resume/accept the old task, enter the other active task, transfer its authority
or establish business completion. For this ordinary transition, missing, stale
or replayed bindings, nonterminal old tasks and pending recovery remain refusals.
Do not clear receipts manually
or invoke a lower-level helper as a consumer workaround; reconcile an unknown
atomic outcome before another transition.

If the exact former root is missing or has been moved, use the separate
`project recover-binding` procedure in [Binding recovery](BINDING_RECOVERY.md).
It requires the exact session, old turn/task/root, new turn and SHA-256 of the
current receipt, plus explicit owner permission to detach while the old task
state is unverifiable. It refuses existing roots, unsafe paths, mismatches and
conflicting registered executors. Under the user-turn lock, it archives the
original receipt and journals a compare-and-swap transition of this chat alone
to INTAKE_REQUIRED without a task binding. The old project, task and history
remain unchanged; no READY or authority is created. Then use ordinary `project
enter` at the intended project with the selected new turn and current authority.
An exact retry can finish a PREPARED transition from its unchanged original
receipt after repeating the preconditions, or confirm its exact replacement
receipt. A later entry cannot be cleared by replaying recovery.

Native provenance alone is neither authority nor evidence of native enforcement.

If an interrupted `enter` leaves `.agentos/entry-transaction.json`, dependent
lifecycle commands report `entry_recovery_required`. Questions and read-only
diagnostics continue. Check the exact stale lock, then repeat `enter` to recover
and re-establish the task binding.

## 4. Document before implementing

Select only applicable layers from the catalog: dossier, roadmap, and stage are
basic; API work needs a contract, personal data needs access and data rules,
and operations need runbook and rollback. Keep the overall objective and plan
visible, while detailing the selected project, module or microprocess level.
Define readiness and acceptance for the declared stage: a reviewed scaffold
stage can be ready without completing every module or release requirement.
A draft document never passes READY. The reviewer fills in facts, sources,
unknowns, write paths, architecture decision, stage acceptance, and rollback.
Reuse the existing documents instead of adding parallel plans. Register each
required document:

```sh
agentos project document --root P --id dossier --path docs/agentos/DOSSIER.md \
  --owner Reviewer --source 'current source and owner task' --summary 'Reviewed facts'
agentos project ready --root P --task TASK --reviewer Reviewer
```

A stage registration also needs `--task TASK`, and the document must name that
exact task. READY checks hashes, currency, and structural correspondence; it is
not an interception of arbitrary tool calls. The agent respects the boundary,
while the client, operating system, or target executor enforces any hard external
limit. Documentation does not grant production authority.

## 5. Implement with exact authority and checks

Write only within approved paths. `project check --root P --task TASK --check-id
NAME` runs the registered argument array with a timeout and a bounded,
source-bound receipt. Its runner stops its own process group on timeout, output
overflow, lingering child, or selector/pipe failure. A nonzero return code or a
source change during the check is FAIL. `shell=False` avoids shell interpolation
but is not a sandbox: the command may still reach a network or host. Verify its
real effects before running it. Local checks should use test data, temporary
directories, and no credentials or dangerous executors.

Before external messages, production/runtime/database writes, credential use,
destructive actions, or deployment, verify the exact actor, target, operation,
validity period or lease, allowed effects, and rollback at the target. Read
authority does not authorize a send. Local READY does not authorize production.
If a target capability is absent, stop only that action and continue other
authorized preparation. There is no universal `--authorized` override.
Choose protection by the actual effect and affected state under
[Proportionate protection](#proportionate-protection-of-data-and-runtime).
Rollback means a sufficient recovery route, not an automatic full copy.

<!-- agentos:solution-integrity:start -->

## Solution integrity

**A solution is a justified change that removes the established cause of a
discrepancy, preserves the meaning of the original task, and withstands a relevant
check. A desired output alone proves none of these.**

Apply this standard to development, research, calculations and diagnosis at every
development level **1–5**. A level changes implementation detail and verification
breadth, never the integrity of the task, evidence or conclusion. For new work
without an observed malfunction, justify the intended result and the meaningful
input-to-output chain; do not invent a failure or a cause to satisfy this rule.
An explicit stub, scoped stage, hypothesis or mitigation can be useful progress
without being a proven correction or a completed product.

### Twelve working laws

1. **Preserve the task.** Keep the agreed inputs, conditions, constraints and
   success criterion. Do not silently remove difficult cases, costs or required
   behavior to obtain a desired answer. A changed premise or criterion is an
   explicitly identified separate experiment; it does not solve the original one.

2. **Justify the expectation.** Establish why the expected result should hold:
   units, semantics, order of operations, timing, rounding and relevant contract.
   The expectation itself may be wrong. Explain a necessary correction to it
   using evidence instead of silently changing either the task or the output.

3. **Trace the result.** Retain the material chain **source → input →
   transformation → output**, including relevant versions, imported functions,
   effective configuration, timestamps and units. Inspect the actual values at
   the suspect boundary; do not insert an output adjustment merely to hide an
   unexplained discrepancy. A contractually justified conversion remains valid.

4. **Find the first divergence.** Locate the last correct state and first
   incorrect state, then investigate the boundary between them. Follow upstream
   dependencies when evidence moves the divergence there. Observed divergence
   determines useful depth; inspecting every lower layer by default does not.

5. **Make causes testable.** State what a proposed cause predicts when present,
   removed or changed, and what competing explanations predict. Revise a
   hypothesis when observation contradicts it. A plausible story, temporal
   association or one successful retry does not establish the mechanism.

6. **Use an independent reference.** Check the critical result by a method that
   does not reproduce the same suspected error: a small hand calculation, a
   separately justified invariant, an independent implementation or a qualified
   reference. Do not calculate the expected test answer with the function under
   test. Synthetic input is useful when its expected behavior and basis are known.

7. **Make experiments distinguishable.** Retain an adequate baseline and make
   changes whose effects can be distinguished. Reuse versioned source, input
   identities and necessary evidence; this does not require a full backup.
   Isolate hypotheses when possible. Several interacting changes may be required;
   explain and check their relationship rather than hiding a bundle of changes.

8. **Correct the mechanism.** Change the mechanism that produced the discrepancy.
   Name temporary symptom relief as mitigation and retain any unresolved cause.
   The cause determines the needed scope: one line or several component contracts.
   Restored availability alone does not prove that the original cause was fixed.

9. **Respect information timing.** Justify a decision only with information
   available at that decision time. Preserve data vintages and the time a value
   or event became known/confirmed. Later outcomes may evaluate a decision; they
   cannot retroactively justify it. Do not replace original inputs with corrected
   later data without identifying the new experiment.

10. **Preserve state and history.** Interpret an event in its actual state and
    preceding transitions. A renamed object, new identifier, session or retry
    does not erase earlier actions, partial effects or a failed premise. Reuse
    the real continuation context and reconcile uncertain operations through
    their existing identity; do not treat them as an untouched first attempt.

11. **Try to disprove the result.** Choose a relevant case that could show the
    proposed rule or correction to be wrong or harmful. Check meaningful
    alternatives and tradeoffs, including a beneficial behavior it might remove.
    A check capable only of confirming the preferred answer is insufficient.

12. **Match the claim to the evidence.** Distinguish observation, hypothesis,
    established mechanism, result on a checked sample, and untested generalization.
    Related observations are not automatically independent confirmations. A
    successful launch does not prove a calculation; one correct example does not
    establish general reliability. Include material untested conditions.

### Sufficient explanation and proportionate work

Before claiming that a discrepancy is corrected, be able to explain where it
first appears and the evidence, the mechanism, why the change affects it, which
check could refute the explanation and what it showed, and which material
conditions remain untested. Use the smallest discriminating check sufficient for
the scoped claim. Mathematical or contract evidence can supply an independent
reference; an operational reversal cycle is not required for every calculation,
new feature or observation. A market price sequence can establish a checked
predictive association without proving all causes of the price movement.

At level 1, retain the complete short structure plan, connected modular stand,
explicit stubs, useful boundary debug and accessible error journal. A small
independent example and a relevant counterexample may suffice for a new
connection. Keep unverified internals and conclusions explicit and continue
independent authorized assembly; do not turn each helper edit into deep
acceptance. Levels 2–5 increase the selected coverage and detail, not permission
to substitute premises or overstate evidence. Preserve the selected level on
continuation and deepen only the relevant module or microprocess.

Keep material reasoning and evidence in the existing plan, code, check or journal;
reuse unchanged evidence. These laws add no per-command form, status registry,
fixed test/time quota, universal backup or full-report requirement. Use existing
checkpoints for sufficient outcomes and residual work, then continue. Preserve
Auth/ACL, data protection, external authority, UNKNOWN reconciliation and the
distinctions between synthetic, candidate, installed and target-verified results.
Reading these laws grants no authority and does not prove their application.

<!-- agentos:solution-integrity:end -->

<!-- agentos:project-development:start -->

## Project development

Use this method to advance the whole project to the user's result through
understandable plans and working increments. It applies to ordinary development,
features and policy work. The canonical text is this marked section of
`docs/PROCESS.md`; read its current body through `agentos workflow guidance`,
or directly from the selected source or installed resource when the CLI is
unavailable. Apply the shared [Solution integrity](#solution-integrity) laws at
every level; guidance includes their current body before this method. When
reading the document directly, read both sections. Continue the existing project
and writer, using the current plan.

### Development level: 1–5, default 3

The level sets a development mode, not completion percentage. The user may change
it anytime for a project, stage or module. Inherit the enclosing level unless a
narrower choice exists; otherwise use **3**. Briefly state it at start/change and
record its scope in the current plan. Changes govern subsequent work; do not
rebuild completed work merely for a level change.

Carry the choice across sessions and handoffs. The existing task answers and
context goal can contain `development: {"level": 1, "scope": "project"}`;
`1D` is an input alias of level 1, not another level. Same-task resume retains
an omitted saved choice. For registered tasks, context callers bind the exact
current task and revision through `development_source` in [CONTEXT_BINDING](CONTEXT_BINDING.md);
the builder carries and checks its saved choice. Unregistered/portable callers
carry typed `goal.development`; a choice recorded only in prose is insufficient. Scope
names identify the existing plan's project/stage/module, not an authority grant
or an automatically inferred scope tree. Use the enclosing plan to resolve it.
When loading guidance, pass that same choice with `--development-level` and
`--development-scope`, including an explicit causal-debugging lookup. Omitted
arguments expose the stateless default; they do not replace a choice already
known from the plan. Without the CLI, retain the choice beside the actual method
text in that plan; no installation is required merely to read the method.

Only for a new project whose development has not begun, offer a native
single-choice control with the five options below, in the user's language;
if unavailable, present one compact five-option choice. Apply an explicit level
without repeating the choice. Patches, fixes, small changes and continuation
inherit the level, defaulting to **3**; show no selector. Create no forms,
standalone storage or imitation buttons.

| Level / short button label | Description |
|---|---|
| **1 — Fast assembly** | Connect the whole with simple implementations or explicit stubs; check the new connection and material risk sufficiently, retain useful debug and an accessible error journal, then continue assembly. |
| **2 — Main connections** | Assemble quickly with debug; check main module boundaries and connections, then deepen details. |
| **3 — Working stage** | Run a coherent stage with related functions/exports connected and exercised; use a light synthetic end-to-end scenario, then proceed. |
| **4 — Integration detail** | Detail selected module contracts and check main failure scenarios during integration. |
| **5 — Deep steps** | Detail and verify each step immediately within the overall plan. |

Instrument key paths and module boundaries. Use existing logging or a simple
accessible shared error journal: time, module/operation, error, known
cause/stack when available, and request/run identity linking the scenario.
Keep context bounded and free of secrets. Once a specific part works, remove or
disable temporary noisy debug and retain normal error logging; confirmation of
that part suffices without whole-project proof.

Every level preserves modularity, common working stand before recursive detail,
explicit stub status, access rights and essential checks for secrets, irreversible
effects and other protected operations.

At level 1, choose a connected increment as the unit of progress. A helper,
file edit or internal microstep need not become a separate acceptance cycle.
Keep module inputs/outputs and the short complete structure plan visible; defer
nonblocking internal detail to its named recursive stage. One relevant existing
check or a small scenario may suffice for the changed connection. Check affected
Auth/ACL and data/effect protections when needed at every level. Investigate a
concrete malfunction causally, then return to assembly once its scoped blocking
condition is resolved. No level imposes a fixed number of minutes or tests.

### Proportionate protection of data and runtime

Assess the actual action and affected state before choosing protection.
Distinguish a live service or operational database, unique non-production data,
and an isolated reproducible development stand. A new runtime is not production
merely because it runs a server or database. Names such as `lab` or `test` do not
establish isolation either; use the known target, connections, storage and
dependencies. Reuse unchanged facts instead of repeating discovery for every edit.

- For versioned source and reproducible development state, preserve changes
  through Git and retain the available inputs needed to rebuild or reseed the
  affected stand. Preserve relevant uncommitted or untracked work before an
  operation that could remove it. Do not routinely copy the whole runtime,
  dependencies, caches, synthetic database or earlier backups. A release package
  captures its declared source/artifacts; it does not require a running database
  copy. A full stand capture is warranted for a concrete transfer or recovery
  rehearsal that needs those bytes, not for ordinary development increments.
- Unique data, configuration or evidence can exist outside production. Preserve
  only the affected material that cannot be safely or acceptably recreated.
  Retain an expensive experiment's necessary result without copying unrelated
  runtime state. An isolated copy of real data remains confidential; keep private
  data and secrets out of public Git even when that copy can be recreated.
- For live services and operational data, assess concrete loss or corruption,
  interruption, disclosure and external effects. Choose the smallest sufficient
  protection: an existing applicable recovery point, transaction, targeted
  preimage/export, configuration rollback or retained release. A code-only change
  does not automatically require a database copy; code can still cause destructive
  writes without a schema migration. Read-only inspection requires no new backup.

A new backup needs a concrete reason: what state could be lost, by which action,
why it cannot be safely or acceptably recreated, and why an available recovery
route or a smaller copy is insufficient. A full backup is appropriate only when
the affected scope and recovery need justify it, or it is the requested
deliverable. Reuse an available, sufficiently current recovery point when it
covers the operation. Account for the copy's disk, time and service impact;
repeated copies are not evidence of safety.

Record material decisions briefly in the existing plan or operation record,
without a separate risk register, per-command form or repeated owner approval.
If the target or effect is uncertain, make the smallest relevant read-only check
and continue independent authorized work. Development level changes verification
depth, not the value of data or a default backup requirement. Existing target
authority, ownership, mandatory narrow transactional journals and UNKNOWN
reconciliation remain in force. This rule does not authorize deleting retained
backups, evidence or history.

### Working cycle

1. **Define the result.** State the intended product, its main user scenarios,
   scope and constraints. Identify what completion means at the current level.
   Keep this outcome visible when choosing work, so implementation choices serve
   the project instead of accumulating unrelated features or process tasks.

2. **Plan the whole current level.** Before its main implementation, describe
   the path from beginning to result: necessary stages, their order,
   dependencies and concrete next steps. At project level, cover architecture,
   code structure, data, interfaces, integrations, infrastructure, launch and
   completion. Name unknowns and the stage that will resolve them. A complete
   project plan does not require every lowest-level detail upfront; expand a
   module or microprocess when choosing to work at that depth.

3. **Keep modularity mandatory.** Give each part a clear responsibility, inputs,
   outputs and interface to the rest of the project. Preserve these boundaries
   as work becomes more detailed. Prefer existing components and straightforward
   interfaces. A module boundary should make a part understandable and replaceable;
   it need not create a separate service or extra deployment machinery.

4. **Build the common working stand first.** Establish a runnable project with
   connected parts and one main end-to-end scenario before deeply polishing an
   individual component. This stand can use simple implementations and explicit
   stubs for unfinished parts. Its purpose is to make the overall structure work
   and expose the next useful increment. In an existing project, reuse the
   working stand and preserve its useful behavior instead of starting another.

5. **Use interim solutions deliberately.** Choose the simplest implementation
   sufficient for the declared stage. For a stub, say what it substitutes for,
   what behavior it currently provides, and which planned stage will replace it.
   Keep its boundary clear to callers and users who depend on that behavior.
   A scaffold, prototype or contract can be a completed stage result. Schedule
   robustness, optimization and broader coverage where the product needs them.

6. **Deepen recursively.** After the common stand works, select a module,
   function or detail and repeat the same cycle: complete plan for that level,
   understandable steps, working result, then further depth when useful.
   Apply it again to a selected microprocess if necessary. Reconnect each result
   to the common stand. Keep unresolved internals behind their declared interface
   or stub so one detail does not block independent platform work.

7. **Finish the declared stage.** Give each step a purpose, actions, expected
   output and a simple completion criterion. Judge that output against its own
   scope. Place whole-product integration and release acceptance in their planned
   stages. Record nonblocking improvements at an explicit later point in the
   same plan. Resolve a blocking dependency sufficiently to resume progress;
   parallelize independent work with clear ownership.

8. **Check enough, then stop.** Match verification to the selected development
   level, changed behavior and risk: inspection, a build, a relevant existing
   check or a focused user scenario may suffice. Sensitive data, access and
   critical operations require their applicable checks and recovery provisions. Once the stage criterion
   and required checks pass, with no concrete obstacle to continuation, stop
   checking and proceed. Extend verification for an observed defect, changed
   conditions, unresolved material risk or a planned acceptance gate. Reuse
   applicable results; do not repeat unchanged checks or add speculative test
   programs to a finished step.

9. **Record and continue.** Update the existing plan briefly with the result,
   remaining stubs or limits, and the next step. Save changes through the
   project's normal route, then perform that step. Adjust affected plans when
   new information changes dependencies or scope. When newer scoped guidance
   supersedes part of a mutable plan, mark the replaced section as historical
   and link to the current plan and its scope. Preserve accepted results and
   dated evidence. For immutable snapshots, update the existing current index
   instead. Repair affected links and conflicts without a separate documentation
   sweep. Make routine technical decisions within the assignment without
   repeatedly returning them to the owner. This method uses existing authority
   and does not change external permissions, protections or UNKNOWN reconciliation.

### Internal progress, handoff and coordination

For an internal step in the same retained working stand, keep a compact record:
changed connection, sufficient check/result, remaining stub or error, and next
authorized action. Continue within the current assignment. This is not a call
to `project close` or `project checkpoint`; those terminal operations retain
their existing accepted-handoff requirements. A long report and a rebuilt full
archive are not prerequisites for every internal step.

Reuse an accepted available base and retain changed/added/deleted files and
relevant new evidence as a delta. Pin the base and delta identities and their
relationship; preserve the dependencies required to reconstruct the result.
A delta without its accessible verified base is partial, not a self-contained
handoff. Produce a complete package when requested, when transfer/recovery needs
it, or when the destination cannot obtain the pinned base. Existing capture,
integrity, required result-delivery and restore checks still apply.

Preserve the result before a notification attempt. A failed optional owner
notification does not hold the saved result or an already authorized independent
next step; retain its exact delivery state for reconciliation. Required result
receipt/review and optional notification are separate. The coordinator still
reviews the declared result and owns the next assignment; do not infer permission
for an unassigned step or send a duplicate to a busy/unknown executor.

Delegate bounded independent parts when they can help. Record each returned
contribution and observed execution, dependent wait and integration time where
available; reuse existing timestamps at meaningful boundaries. Distinguish
implementation, checks, packaging/reporting, coordinator wait and lost access.
Unknown intervals stay UNKNOWN, overlaps are not summed twice, and gaps between
messages do not establish their cause. A launch count or an unmatched before/after
observation does not establish acceleration. This is lightweight task accounting,
not per-command instrumentation or another mandatory report.

A new method file, capsule hash or ACK proves neither active-session pickup nor
application. Deliver the exact current instruction through the authorized route
at a safe boundary, then inspect the next permitted action: retained level/scope,
connected increment, proportionate check, useful journal, compact progress and
continued ownership. Mark each observed behavior separately from unexercised or
unknown behavior. Do not restart work or replay a finished scenario to manufacture
adoption evidence.

<!-- agentos:project-development:end -->

<!-- agentos:causal-debugging:start -->

## Causal debugging

Select this method separately with
`agentos workflow guidance --method causal-debugging` for a specific malfunction
in UI, API, services, data, performance or operational constraints when causal
investigation is needed. Ordinary development follows **Project development**;
causal diagnosis is not a universal prerequisite. Define a sufficient correction
or mitigation criterion for the current problem, then return to the project plan
when it is met. Keep any unresolved cause explicit rather than extending the
investigation solely for completeness. This method uses the existing diagnosis,
implementation and acceptance cycle, without a second workflow, new task gate or
permission. On continuation restore the experiment and its evidence from the
existing work packet rather than restarting diagnosis.
The canonical text is this section of `docs/PROCESS.md`, mirrored byte-for-byte
in installed `resources/docs/PROCESS.md` (located with `agentos resources`).
Read the actual bounded section returned by the effect-free
`agentos workflow guidance --method causal-debugging`; if the CLI is unavailable,
read this exact section and shared [Solution integrity](#solution-integrity) from
the selected source or installed resource. Guidance includes the shared laws
before this method; their integrity requirements apply at every development level.
Entry/context output that already
materializes the same current body may be reused. A link, hash or receipt for
instruction delivery alone does not prove agent behavior. Ordinary feature work
without a malfunction does not require an invented failure or reversal cycle.

### Define and reproduce the failure

Record the user's action, expected result, actual result and an observable
success/failure criterion before choosing a cause. Reproduce with the exact
relevant environment, source/runtime version, data or fixture, configuration,
initial state and load. Record actual effective settings and actual execution,
including the first failing boundary, safe error/code and exit or response.
Keep source, installed version and already-loaded worker code distinct.

If reproduction fails or is unavailable, say so explicitly. Preserve the incident
as unresolved; a suspected cause remains a hypothesis. Select the next bounded
observation or safe reproduction that distinguishes the remaining explanations.
Do not invent a failure, infer recovery from a healthy process, or claim causality
from timing, a matching error label or one successful run.

The same HTTP 503 can originate at different boundaries. An `EXPORT_DEADLINE`
records the export's observed time boundary; it does not establish a database
`statement_timeout`. Retain the actual safe error, SQLSTATE if observed, and
diagnostic classification. A missing SQLSTATE or unobserved database boundary
remains unknown; never fill it with a guessed cause.

### Establish a working baseline

Obtain a configuration in which the same scenario meets its success criterion.
When artificial operational limits are suspected, use an authorized isolated
environment and sufficient **finite** values to establish that baseline. Record
which limits changed and their effective values; an explicit request is not
proof that a setting took effect. Keep data, scenario and required semantics
equivalent. Reuse a qualified baseline only while its relevant inputs match.

Before launch, check compatible finite limits along the whole relevant chain:
**producer/exporter → writer → reader → restore**. Compare effective units and
semantics, including output, chunk/page, stored, expanded and restore-input sizes;
raising the producer's ceiling does not establish downstream capacity. Account
for the files that can coexist on each filesystem: primary data/output, staging
and temporary copies, rollback/WAL and other journals, indexes and service data,
retained partials and required recovery copies. Compare their combined requirement
and justified headroom with available space. Preserve the previous configuration
and an applicable rollback route; do not discard a partial to make the budget fit.
Select recovery copies under [Proportionate protection](#proportionate-protection-of-data-and-runtime):
the action's actual risk determines their scope. A reproducible stand normally
uses retained source and rebuild inputs; this capacity check does not require a
full runtime or database backup. Reuse an applicable existing recovery point.

Keep **configured ceilings**, **estimated requirements**, **observed usage** and
**measured peaks** separate. A configured stage budget, end-of-run file size or
arithmetic sum is not a measured disk peak or process RSS. Record the measurement
method and scope, or leave the peak/RSS unknown. Missing sizing facts call for a
bounded measurement or explicit estimate, not an invented capacity guarantee.

Preserve authentication, authorization/access boundaries, isolation, data
integrity and every mandatory protection. An operational experiment must not
disable a security guard, expand private-data access, change credentials, enable
native hooks or bypass a target refusal. A limit serving a protective purpose
cannot be reclassified merely because it blocks progress. Use approved test
identities and synthetic or otherwise authorized data. If a safe experiment
cannot be made, state the exact boundary and leave the dependent cause unknown;
continue independent authorized work. This method grants no production mutation.

If the intended baseline also fails, localize its **first failure** and restore a
working baseline before testing the suspected restriction. Do not put restrictions
back over a broken baseline and interpret the resulting failures as their effect.
For a necessary limit adjustment on an actual target, retain its existing explicit
setter, ownership, authority, readback and rollback requirements.

Retain failed-baseline evidence and partial outputs. Use observed elapsed time,
completed/remaining work, bytes, phases and the first boundary to select the next
distinguishing experiment and justify its finite resource profile. State the
remaining uncertainty, expected new information, maximum duration/resources and
stop conditions before launch. Do not cycle through known-insufficient profiles
or repeat identical checks that add no knowledge. There is no automatic limit
escalation or permission to exceed an approved ceiling; a further profile needs
its existing scoped authority. A grouped profile change may establish a working
baseline, but does not identify one factor's cause. Restore restrictions one at a
time only after that baseline succeeds.

### Isolate the factor and demonstrate reversal

Choose each experiment to discriminate between named hypotheses or to verify a
specific correction. State the differing predicted outcomes before executing it.
Change one factor while holding data, scenario, initial state, versions, other
settings, observation method and load fixed. Reset mutable state equivalently
between runs and record any unavoidable difference. If many factors are involved,
a bounded binary search may locate a group; then isolate the individual factor.
If an effect requires a combination, test the combinations explicitly and name
the interaction. Group removal or changing several settings at once is not proof
of a single cause.

For two binary factors, observe all four states: neither enabled, each enabled
separately, and both enabled, with other factors and initial conditions fixed.
Do not infer an unmeasured reference state from assumed monotonicity or knowledge
of the implementation. If a state cannot be tested safely, identify the observed
states and keep the broader interaction claim partial.

Demonstrate a reversible sequence: **working configuration → failure → restoration
→ repeated failure**, with primary evidence for all four steps. For example,
with two actually overlapping requests and unchanged data/authentication, a finite
admission limit of 2 succeeds, 1 rejects the second request, 2 restores success,
and 1 repeats that rejection. Observe actual overlap and admission state; merely
requesting concurrency or reading a configured value does not establish either.
Connect the controlled factor to the first failing boundary and the user's
criterion. Temporal correlation and a single successful retry are insufficient.

Use only reversible, authorized effects. A failed or unknown external operation
is not permission to replay it for this sequence: reconcile its original operation
identity through the existing route first. When reversal cannot safely be tested,
retain partial observations, explain the limitation and keep the causal claim
unconfirmed. A synthetic reversal establishes only that experiment's scope;
claiming the historical or target incident's cause requires matching evidence.
An interrupted or stopped chat does not prove that an external process stopped.
Restore the original operation ID, inspect its durable result and actual effects,
and preserve UNKNOWN when evidence is insufficient. A new session, operation ID
or transport is not permission to repeat that effect.

### Keep a compact experiment journal

Keep the journal with the existing work/bug/incident record, linked by the current
writer. Do not create a competing status ledger or copy private payloads into
public reports. Retain the experiment ID, named hypotheses and differing forecasts
before launch. Record every discriminating run, including failed baselines:

| Step | Factor and actual value | Fixed conditions | Hypothesis and forecast | Actual result | Error and first failing location | Evidence reference | Conclusion and next step |
|---|---|---|---|---|---|---|---|
| Experiment/run ID | Effective setting or controlled input | Exact relevant pins, fixture, initial state and load | Named alternatives and their predictions, retained before the run | Observed criterion and response/exit | Safe code and boundary, or none | Primary retained receipt/artifact | What changed in knowledge; next discriminating action |

Label **hypothesis**, **observation**, **confirmed conclusion** and **unknown**
separately. A receipt proves only its actual scope. Retain failed observations
alongside later successes and record the reason for any repeated check. If a run
adds no information, revise the experiment instead of collecting the same symptoms
again. Identify bottlenecks in diagnosis itself: slow tools or remote calls,
unprepared data, redundant checks and unnecessary sequential execution. Prepare
stable inputs once and parallelize independent observations without changing a
controlled experiment or creating competing writers.

At existing checkpoints, assess the investigation's own bottleneck: elapsed work
and waits, slow remote access, unprepared local Linux environment/data, missing
declared dependencies, repeated checks or needless serialization. Remedy a
material bottleneck within current authority and verify the effect; otherwise
state the exact boundary and next owner/action. Do not leave a solvable setup
problem as a permanent blocker. Use subagents for useful independent work and
review, with one owner for each changed file and environment. This adds no fixed
checkpoint timer or authority to alter a protected environment.

### Correct, verify and continue

After establishing the cause, make the smallest correction that satisfies the
contract. Re-run the original user scenario, relevant boundaries and regressions,
and exercise rollback where applicable. A mitigation may be useful before proof;
identify it as a mitigation and keep the cause unresolved. Do not present an
isolated or synthetic success as a working-product fix.
For resource/admission changes, exercise the relevant capacity boundary, actual
resource release and the contracted refusal or queue behavior; a successful
request below the limit alone does not establish those properties.

Report these stages separately, with the exact source, artifact and evidence:

| Stage | Evidence needed for the stated scope |
|---|---|
| PREPARED | Reviewable correction and its exact basis exist. |
| LOCALLY_VERIFIED | The local scenario and relevant checks actually passed. |
| INSTALLED | The authorized target installation and readback are confirmed. |
| TARGET_VERIFIED | The original scenario actually passed in the target environment. |

Artifact status is a separate dimension. A checksum, retained partial or
`SEALED` label establishes only its verified artifact contract; it does not prove
source completeness, representativeness, successful restore or product acceptance.
An actual restore also establishes only the verified restored scope. Keep missing
required/optional work and the original user criterion visible.

For result handoff, follow the existing [coordination](WORK_COORDINATION.md),
[completion](COMPLETION.md) and [durable handoff](INDEXED_HANDOFF.md) contracts as
applicable. Keep prepared, send-uncertain, recipient-received and semantically
accepted results separate; use their existing states rather than a second ledger.
A visible sent message or sender enqueue is not durable preservation or confirmed
recipient receipt. Verify retained bytes/readback and the actual receiving-side
evidence before declaring delivery complete. A receiver ACK is not semantic
acceptance; a reviewed result may still be held or partial. Reconcile an uncertain
send by its original identity before another attempt.

These are reporting stages, not replacements for existing task/Atlas statuses.
On continuation, restore the user criterion, reproduction/baseline pins, journal,
current effective configuration, confirmed/unknown findings and next experiment.
Recheck changed dependencies; reuse unchanged applicable evidence. Installation,
document pickup and agent behavior remain distinct. For substantial changes to
diagnostic behavior, qualify the affected scenarios in proportion to risk, using
fresh-session behavior where needed. Select relevant cases such as one restriction,
a failing baseline, interacting factors, non-reproduction, a protected data/access
boundary or continuation with an existing journal and uncertain operation.
A default-method or routing change alone does not require the full fresh-session
diagnostic set. Requirements for claims of causality remain unchanged.
Evaluate the experiments actually chosen, preserved history, reconciliation
and conclusions, not just the presence
of this text. A fresh planning exercise can test interpretation of partial
evidence; it does not execute or establish the source incident's next result.

<!-- agentos:causal-debugging:end -->

## 6. Close only a registered task

Update documents to reflect the result and register their new hashes. Run the
exact approved checks, then `assess`, then `close --review review.json` (or
`--review -`). Review every acceptance criterion and required document, scope,
limitations, and next step. The task, revision, policy, source, and logs must
match; the latest relevant checks must pass and be no older than 24 hours. No
out-of-scope change may remain. Local closeout uses only `not_requested` or
`pending_target_verification` as deployment status.

`project verify-closeout --root P --task TASK` reads whether a CLOSED result still
has current source, documents, logs, policy, and evidence. CLOSED remains a
historical fact if later work makes that evidence stale. For unfinished
registered work, use a truthful checkpoint with `complete=false`. A failure
before entry has no task to close. A read-only answer ends normally; there is
no Stop requirement.

## 7. Optional audit record

Use `project observe --root P --session S --turn T --answers audit.json` only when
there is a reason to record bounded read evidence or hashes. It writes a
separate observation in the user home and does not create or change a project
task. Reusing the same session, turn, and root is rejected rather than silently
overwritten. API or mail reading requires no such record. An observation does
not prove external API completeness or that a disk never changed.

For provider selection and target-policy diagnosis, follow
[PROVIDER_INDEPENDENCE](PROVIDER_INDEPENDENCE.md). Public project work requires
no private kernel, fleet controller or notification service. Preserve actual
target controls; missing optional reporting does not block local completion.

## Historical: Main coordination successor0.7.0rc2

For continuing work, follow [WORK_COORDINATION](WORK_COORDINATION.md): child/session completion never closes the original parent goal. Record each verified result, remainder and owned next action; preserve independent work during checkpoints and reconcile unknown effects before retry. The optional synchronous ledger does not supply an always-running client.

## Explicit completion and recovery

Follow [the completion contract](COMPLETION.md) for bounded continuation, current target scope, confirmed handoff and safe recovery. Turn completion leaves the project open until independent current evidence satisfies the original goal. Source implementation and documentary checks do not establish host adoption or publication. The local validation chain includes `python3 tools/verify_completion.py`; GitHub Actions remain unused.


## Explicit per-project source inventory budget (local candidate)

The source inventory defaults remain 20,000 files and 128 MiB total bytes. Every
regular file still contributes its complete SHA-256; no evidence path is excluded
by this setting. Large evidence projects can explicitly opt in with:

```sh
agentos project inventory-budget --root P
agentos project inventory-budget --root P --max-bytes 536870912
agentos project inventory-budget --root P --max-files 40000
agentos project inventory-budget --root P --reset
```

The validated optional `inventory_budget` project field has schema
`agentos.project-inventory-budget/v1`, integer `max_files` in 1..40000 (default 20000), and integer
`max_bytes` in 1..17179869184 (booleans rejected). The setter uses the existing
project lock and atomic metadata writer; it does not alter tasks or evidence.
Readback reports the explicit/default choice and project revision. Identical
settings are a no-op. Reset removes the override and restores 128 MiB and 20000 files.

Explicit budgets are included in policy digests and source snapshots. A change
invalidates existing READY/check evidence until the normal re-entry and READY
workflow is completed; old receipts remain historical. Omitted settings preserve
previous policy digests. This setting grants no external authority and does not
change containment, symlink, directory-link attestation, file-limit enforcement, or hooks.
The snapshot still hashes ordinary files with the existing implementation; the
bounded total budget is not a hostile same-UID filesystem sandbox.

Every effective setting change also increments project `inventory_budget_revision`
(integer 1..2147483647, fail closed on exhaustion). Reset retains this generation,
so returning to a previous byte budget cannot resurrect old READY/check receipts.
Policy/snapshot include the generation after first use; untouched projects retain
exact historical digests. A no-op neither increments nor invalidates.


## Owner-local finite capacity successor 0.8.0rc2016

The supported maximum explicit per-project byte budget is 16 GiB. The default remains 128 MiB and the default file budget remains 20,000; an explicit per-project file budget is bounded at 40,000. Only an explicit supported project setter opts into a larger budget; every path and full content SHA remains in the inventory. No evidence exclusions, guard skips, symlink relaxation, secret scan exception or external authority is introduced. Re-entry and current READY are still required after a policy change. This owner-local version is not an upstream release. ATLAS_SOURCE retains historical source-base hashes; those are not current PROCESS pins. The selected coordinator PROCESS edge is updated; prior WORK_COORDINATION indexed mismatch is retained.


### Optional lock-bound inventory setter predicates (rc2016)

Set/reset may supply BOTH `--expected-project-sha256 SHA256` and
`--expected-budget-revision N`. The digest is exactly 64 lowercase hexadecimal
characters over the current `.agentos/project.json` bytes; revision is an exact
integer 0..2147483647 (0 for an untouched legacy project, booleans rejected in the
typed API). Both current comparisons run inside the existing project write lock
before any project metadata write, including a no-op. One predicate, malformed
values, stale digest/revision or predicates on a read-only call fail closed.
The typed API names are `expected_project_sha256`, `expected_budget_revision`.
Omitting BOTH preserves legacy read/set/reset. Readback grants no authority.
Re-read and reconcile after mismatch; never automatically retry a changed target.

The finite maximum is 17179869184 bytes (16 GiB); default remains 134217728 bytes
and default max_files remains 20000; explicit max_files is bounded at 40000. This raises a reader ceiling without allocating disk.
All source files/content hashes and existing safety checks remain included. At
either ceiling STOP; no automatic expansion, guard skip or evidence exclusions.
Once a project stores a value above 4294967296, rc2015 cannot read that project.
Preserve a compatible forward reader; automatic downgrade or metadata reset is
forbidden. Isolated installer rollback does not prove project downgrade safety.


### Optional finite per-project file budget (rc2017)

`--max-files F` / typed `max_files=F` accepts exact integer1..40000, rejecting
booleans/floats/overflow and malformed records. Global defaults remain20000 files
and128MiB; max_bytes ceiling remains16GiB. The exact budget record keeps its
three fields and schema version. Omitted max_files preserves EFFECTIVE current
file budget on byte-only update; omitted max_bytes preserves EFFECTIVE current
byte budget on count-only update. Both can be set together. Reset conflicts with
either setter input and restores BOTH defaults through the existing monotonic
generation; an untouched read keeps legacy default/digest bytes. Optional paired
CAS predicates remain strictly typed and checked under the existing write lock
before any project write/no-op; current Root mutation must supply BOTH.

Source policy/readiness invalidation and historical evidence retention are
unchanged. This does not change safeio walk/hash/alias/content checks or SKIP;
every accepted file is fully hashed. Further byte/file guard refusal means STOP
and qualification of the first boundary, never automatic expansion/exclusions.
Whether40000 suffices for any real corpus is UNKNOWN until separately authorized
Root source proof. Once a project stores max_files other than20000, rc2016 cannot
read it: retain a compatible forward reader; no automatic downgrade/reset.


### READY task metadata bound (rc2017)

A finite file inventory does not guarantee that its full READY task fits the
default4MiB task JSON reader; explicit rc2018 project task policy may select up to32MiB. READY serializes the complete future task with the
existing UTF-8 JSON formatting and checks its exact byte length before the atomic
task write or READY event. Above the effective task ceiling (4194304 by default) it fails with
`ready_task_metadata_limit`, preserving the prior task and history. Exactly the selected task ceiling
is accepted; the generic JSON reader stays4MiB. No source-map truncation, compression,
external storage, recovery route or global metadata-limit expansion is introduced.

Actual full corpus and task overhead must be qualified separately; synthetic
40000-path success/failure is not a real-project compatibility claim. Other
metadata writers and future receipt growth remain unchanged and retain their
existing reader limits. A refusal remains an explicit compatibility boundary.


## Explicit per-project TASK metadata budget (rc2018)

`project task-metadata-budget --root P` reads optional task_metadata_budget.
`--max-bytes N` or `--reset` explicitly changes project policy; optional PAIRED
expected-project-sha256/expected-budget-revision are compared under existing lock
before no-op/write. This command uses task_metadata_budget_revision, not inventory
budget revision. Exact record: schema agentos.project-task-metadata-budget/v1,
max_bytes integer4194304..33554432 (booleans/floats/extra fields rejected).
Default4MiB for untouched projects. Changes increment policy generation/project
revision and invalidate READY normally; reset retains generation. Byte-identical
legacy digests when both policy fields were never present. Lowering/reset is
refused when oversized tasks or unclassified retained preimages prevent bounded
compatibility proof; never delete/reset history to force it.

Only task.json and its typed lifecycle before/after/raw backup/readback rows use
this ceiling. Global safeio/project/turn/events/requests/provider/privacy limits
stay fixed. Full source map remains inline, no storage migration/compression or
truncation. Inventory16GiB/40000 unchanged. Entry/current READY/check/close/checkpoint
task writes are bounded before their task write, with exact readback. Existing
external checks/handoff side effects retain their authority and unknown handling.

Continuation embedded journal remains24MiB including base64 pre/postimages and
retarget history: an allowed32MiB task can fail journal eligibility. Refusal small
journal/request/permit caps and non-task row limits stay fixed; staged TASK raw
rows alone follow project policy. Handoff objects still16MiB/scanners unchanged.
No universal32MiB lifecycle guarantee. Ineligible route STOP, no auto cap increase,
new recovery route or replay. Legacy reader cannot read task>4MiB; preserve a
compatible forward reader/policy while such tasks/preimages exist. No auto downgrade.
