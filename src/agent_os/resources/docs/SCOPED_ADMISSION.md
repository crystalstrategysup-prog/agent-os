# Scoped file admission

`agentos project scoped-apply --root ROOT --request REQUEST.json --plan`
validates a finite same-task source change; omit `--plan` to apply it. This is
an explicit local operation, not a universal authorization flag. The target
adapter must verify the current human authority, actor, root and permitted
operation before invoking it. Supplied authority strings are evidence references,
not authenticated grants. Existing external controls are never overridden.

The request schema is `agentos.scoped-file-admission/v1`: operation, task,
session_id, turn_id, actor, authority, reviewer, expected hashes for project,
task, events and binding, held_paths, files, and create_directories. Each file
contains source, target, before (SHA-256 or null for absence) and after SHA-256.
Source bytes must already be staged in the same root. Maximum 16 files,
1 MiB per source/target, 32 explicitly listed new parent directories, and a
4 MiB journal. Inputs reject extra fields, aliases, traversal, hard links,
symlinks and control metadata targets. Declared held paths are negative
identifiers: their content is never opened. The target supplies the complete
applicable hold set; this local API cannot discover hidden external denials.

Project and user-turn locks serialize cooperative writers. Metadata identity,
active task, exact workflow binding, current document gate and every target
preimage are checked before the journal or product writes. No source_snapshot,
command runner, directory tree scan, archive or global check/assess is invoked.
Plan output enumerates reads/writes, declared directories and bounded temporary
file effects. Metadata paths are derived from validated task/operation identity;
receipt-parent creation and same-directory atomic-write temporary files are
implementation effects, not extra product scope.

The transaction retains full pre/post bytes in the bounded journal before the
first write. Each row is compared again immediately before replacement and read
back afterwards. Multi-file changes are recoverable, not globally atomic.
While a journal remains, ordinary project lifecycle mutation is blocked. Repeat
only the exact request and operation to reconcile: a row must equal its recorded
preimage or postimage; any foreign state stops without overwriting it. The
request, source pins, project/binding and document gate must still match.
A successful replay returns the original result without another event. A stale
completed receipt is not silently reapplied. No automatic destructive rollback
is provided; preserve the journal and use a separately reviewed forward repair
when inputs changed. The same-UID filesystem is a cooperative trust boundary.

Success advances the same task revision, adds the exact target paths and records
SCOPED_APPLIED separately. Original task objective, READY source map, prior check
receipts and history remain intact, but old READY is explicitly historical.
The turn binding and project active pointer are unchanged. Global check/assess
cannot accept SCOPED_APPLIED; assess rejects it before source inventory. A later
whole-project acceptance requires ordinary authorized re-entry and full checks.
Scoped equality checks do not re-run or relabel earlier unit/UI tests and never
establish live business acceptance.

Compatibility: additive command and task fields. Preserve this reader whenever
scoped journals or task state exist. Do not downgrade a runtime with a pending
journal; an old release cannot provide the reconciliation guard. Installation
uses a versioned wheel and the existing expected-current managed installer;
no hooks, client trust, authentication or service configuration is changed.

Validation: `tests/test_scoped_admission.py` exercises finite success, old-state
preservation, same-ID replay, metadata CAS, held paths, symlink/hardlink aliases,
missing parents, metadata targets, foreign writes, CLI dispatch and crashes
after each durable row. Existing foundation/workflow tests cover unchanged
ordinary lifecycle behavior. Synthetic results are separate from target proof.

Existing regular-file modes 0600, 0644 and 0664 are preserved exactly; newly created targets use 0644. Executable, set-id, world-writable and other modes remain unsupported. This does not grant rights or chmod target files.
