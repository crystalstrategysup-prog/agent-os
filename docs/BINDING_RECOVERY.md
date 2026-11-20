# Recover a chat binding whose former project root is missing

`project recover-binding` resolves the case where an ENTERED chat receipt still
names a project directory that has been deleted or moved. Ordinary `project
enter` preserves that existing binding, while `project next-turn` requires the
former project to remain readable. This explicit recovery command changes only
the selected chat's user-home binding and records a local recovery archive.

## Command and permission

Use the existing receipt's exact session, turn, task and absolute root. Read the
current receipt bytes in the selected user home's `state/turns/` and retain their
SHA-256 for the compare-and-swap precondition. The new turn must differ from the
old turn. Do not reconstruct missing identifiers or replace the recorded root
with a guessed moved location.

```sh
agentos project recover-binding \
  --root /absolute/former-project \
  --session SESSION \
  --from-turn OLD_TURN \
  --task OLD_TASK \
  --turn NEW_TURN \
  --expected-receipt-sha256 RECEIPT_SHA256 \
  --allow-unverifiable-detach
```

All values above are placeholders. Global `--user-home` belongs before `project`
when selecting a different existing user home. `--root` is required and reaches
the recovery module as the supplied string, without current-directory fallback,
tilde expansion or symlink resolution. Supply the exact canonical absolute root
already recorded in the receipt.

`--allow-unverifiable-detach` attests explicit owner permission to release this
chat's binding despite the unavailable old task state. The caller must already
have that permission. The flag is a local authorization attestation; the CLI
does not authenticate a human decision or infer permission from a missing root.
Omitting it refuses recovery. The permission covers the receipt transition and
its archive only. It grants no old-task completion, READY, external authority or
production permission.

## Admission and scope

The operation validates the existing ENTERED receipt's schema, exact session,
old turn, task and root, as well as the supplied SHA-256 of its original bytes.
The old root must be absent. An existing directory, file, symlink or unsafe path
refuses recovery; a dangling symlink also remains a symlink. A moved directory
is handled only because its former exact path is absent. The command does not
search for or change a relocated project.

Other registered ENTERED receipts in this user home that name the same former
root or task are executor conflicts and block detachment. Receipt corruption,
identifier mismatch, concurrent changes and an existing user-turn lock also
remain refusals. Registered receipts describe local workflow state; they cannot
prove that no external executor is running. The unavailable old task and
external execution state remain unverified after recovery.

Invalid initial identities, receipt digest, permission, root state or executor
conflicts refuse before an archive is published. A conflict that appears during
the final precondition checks leaves the prepared archive for review and an
exact retry; it does not authorize replacing a changed receipt.

The command never changes the old task's status, documents, history, project
active pointer, READY or check evidence. It does not create a new project task,
rewrite unrelated chat receipts, relax `validate_entry`, install native hooks
or grant target authority. A known active task in an existing root uses its
ordinary lifecycle and cannot be detached through this missing-root command.

## Lock, archive and compare-and-swap

The existing `state/turns.lock` serializes recovery with ordinary receipt writes.
The expected receipt digest and exact identities are checked before replacement;
the operation preserves the original bytes and a journal before committing the
new receipt. All persistent recovery artifacts stay beneath the selected user
home:

```text
state/binding-recoveries/RECOVERY_ID/receipt.before.json
state/binding-recoveries/RECOVERY_ID/receipt.after.json
state/binding-recoveries/RECOVERY_ID/request.json
state/binding-recoveries/RECOVERY_ID/journal.json
```

`RECOVERY_ID` is derived from the exact request identities, expected original
receipt digest and explicit permission. `receipt.before.json` preserves the
complete original receipt byte for byte. `request.json` retains the exact
request and its detach permission; the replacement receipt is retained beside
it. The journal records PREPARED then COMMITTED for this exact transition.
The archive is retained after success; it remains private runtime state and
must not be copied into a public release or used as authority for later work.

Only the selected current chat receipt becomes INTAKE_REQUIRED with
`task_id: null`. The result includes the session/new turn, `previous_task`,
`recovery_id`, `archive` and `replayed`. It leaves `old_task_changed`, `task_state_verified`,
`native_hook_proven`, `authority_granted` and `production_authorized` false.
INTAKE_REQUIRED means a new ordinary entry is possible; it makes no assertion
about the outcome of the old task.

## Retries and continuation

Repeat only the exact request, including its original expected digest, after an
uncertain result or when checking a completed recovery. The command verifies the
saved request, original bytes, replacement bytes and journal before reconciling:

| Current receipt | Journal | Result |
| --- | --- | --- |
| Exact archived original | PREPARED | Recheck root absence, executor conflicts and receipt CAS; finish the transition with `replayed: false` |
| Exact archived replacement | PREPARED or COMMITTED | Complete the journal if needed, preserve the current binding and return INTAKE_REQUIRED with `replayed: true` |
| Exact archived original | COMMITTED | Refuse; a committed recovery cannot be reapplied to a restored old receipt |
| Any other bytes, including a later entry | Either state | Refuse; never clear the newer binding |

The command never rewrites the immutable original receipt to make a retry fit.
A mismatched receipt or damaged archive cannot be treated as a successful
recovery. An unresolved lock or uncertain write requires review of that exact
operation; the command does not delete locks, overwrite newer receipts or
provide a force switch.

After successful recovery, enter the intended project normally:

```sh
agentos project enter --root /absolute/intended-project \
  --session SESSION --turn NEW_TURN --answers current-answers.json
```

The intended project must satisfy its usual initialization, entry, documents,
task-conflict and current-authority requirements. Recovery does not transfer old
answers or authority. It uses the existing standalone CLI protocol; native hooks
remain disabled.

Successful recovery or exact idempotent replay exits 0. Validation, permission,
conflict or integrity failures use the normal BLOCKED/GateError result and exit
2. No new global entry exception is introduced.
