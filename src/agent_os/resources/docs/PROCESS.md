# Process: direct reading, documented changes

This describes the `0.5.2` foundation. Native AgentOS hooks are excluded: do not
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
