# Process: direct reading, documented changes

Current source candidate: `0.8.0rc2` (not publication or host adoption). RC-labelled sections below are retained historical records, not current installation or publication claims.


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
or establish business completion. Missing/stale/replayed bindings, nonterminal
old tasks and pending recovery remain refusals. Do not clear receipts manually
or invoke a lower-level helper as a consumer workaround; reconcile an unknown
atomic outcome before another transition.

Native provenance alone is neither authority nor evidence of native enforcement.

If an interrupted `enter` leaves `.agentos/entry-transaction.json`, dependent
lifecycle commands report `entry_recovery_required`. Questions and read-only
diagnostics continue. Check the exact stale lock, then repeat `enter` to recover
and re-establish the task binding.

## 4. Document before implementing

Select only applicable layers from the catalog: dossier, roadmap, and stage are
basic; API work needs a contract, personal data needs access and data rules,
and operations need runbook and rollback. A draft never passes READY. The
reviewer fills in facts, sources, unknowns, write paths, architecture decision,
measurable acceptance, and rollback. Register each required document:

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
