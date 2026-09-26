# Requirements and verifiable acceptance

- **FR-01:** Questions, searches, read-only audits, and API discovery work under
  existing read authority without project init/intake, observe, active profile,
  answers file, or closeout, including in an unregistered directory.
- **FR-02:** A real project change needs current architecture and applicable
  documents before implementation. Draft or stale docs block READY.
- **FR-03:** Verified facts are reused. Same-scope resume reuses answers but
  requires fresh authority and resets READY/check evidence. New scope requires
  full entry.
- **FR-04:** Context, answers, and review accept bounded JSON object stdin via
  `-` with duplicate-key, size, path, and symlink controls.
- **FR-05:** Closeout binds current source, task, revision, policy, logs, latest
  checks, and semantic review. Read-only `verify-closeout` detects later drift.
- **FR-06:** Native hooks are excluded. Integration never creates, changes, or
  restores them; retired callbacks are no-ops. Pre-entry failure creates no
  fictional task.
- **FR-07:** External send, production/runtime/database writes, credentials,
  destructive actions, and deployment need separate target capabilities.
  Routing, READY, and profiles grant none.
- **FR-08:** Core and user data have separate roots. Update and rollback preserve
  the overlay; partial owner exports are not complete settings replacements.
- **FR-09:** Unbound old prompt receipts do not block entry, while a conflicting
  active task remains protected. Optional audit receipts do not overwrite task
  state.

Nonfunctional requirements: standard-library runtime, bounded local reads,
locks, explicit errors, and exact hashes. No daemon, natural-language intent
engine, new database, public secrets, or personal settings. Local acceptance
does not replace Mac/Codex readback or independent integration review.

Traceability: workflow, foundation, and contract tests; demo lifecycle;
PROCESS, QUALITY, and COMPATIBILITY. Exact results belong in each candidate's
check receipts. A universal sandbox, private fleet parity, native hooks, and
Windows managed installer are not claimed features.
