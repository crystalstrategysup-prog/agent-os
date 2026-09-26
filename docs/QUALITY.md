# Verification strategy

Evidence for each candidate records exact counts and environment; this document
does not promise a fixed count. Check functions and negative cases, a full
lifecycle in temporary directories, packaged resources and contracts, offline
wheel build and smoke tests. Verify the actual Mac/Codex target separately.

```sh
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3 tools/demo_lifecycle.py
PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_public.py
python3 tools/sync_resources.py
```

The public-tree verifier refuses local `.agentos/` receipts. To check a working
repository containing registered task state, run it against a clean export
without that directory; never publish the receipts with core source.

## Core acceptance paths

- Direct stateless reading must work without project entry or overlay; optional
  audit recording is separate.
- A new task must support stdin bootstrap, current docs, READY, actual source
  change, exact checks, and closeout. An unknown undocumented project must be
  inspected before scaffolding.
- Same-scope resume must reuse verified answers without inheriting authority;
  readiness and evidence reset.
- Declared local writes route to documentation, while external effects report
  missing target authority. This is not a universal network sandbox test.
- Negative cases must cover scope, check receipts, MCP, dispatch, paths,
  symlinks, duplicate JSON keys, evidence hashes and age, versions, profiles,
  import, and installer contracts.
- Retired callbacks must remain no-ops, even with malformed input. Integration
  must create no hooks and preserve unrelated config and owner text. Active task
  bindings remain protected; old unbound receipts do not block entry. No fake
  closeout is created before entry, and `verify-closeout` detects stale proof.

## Stage-specific regressions

F10 verifies that managed AGENTS routes briefly to topical docs and skills
without a length gate, hook, or mandatory history preload. Check merged owner
text and read effective instructions in a fresh session; a fixture alone does
not prove that every client displays the entire file.

F11 covers reported S1–S8 failures: `CODEX_HOME`, empty override files, partial
integration, CRLF and marker order, descendant cleanup, FIFO/socket installed
inventory, damaged payload, and console pytest. Interrupted `project enter` is
tested after draft or turn creation, on recovery, and against concurrent edits.
Both supported pytest invocation forms, clean Git export, wheel metadata and
RECORD, isolated Mac and Linux fixtures, and separate live configuration
acceptance matter. Stable-candidate review also covers ST-01–ST-06: substituted
`.pyc`, owner edits between AGENTS reads, pending entry journal before READY or
check, selector failure after process launch, missing entrypoint hashes, and
shell launchers under long or space-containing paths. These two path shapes
have different pip launcher behavior and must be tested separately. Descendant
checks allow enough time for Python startup while keeping timeout cases short.
Additional F12 fixture cases include symlinks in package-directory ancestors,
interrupted entry after readiness precheck, old pip launcher templates for v1
rollback, and preserving exit code 125 if cleanup crosses the execution
deadline. Check owner tree and current pointer in installer fixtures; Linux
x86_64 Python 3.13 also needs both full pytest invocation forms.

Native interception tests are replaced by no-op and no-installation tests; do
not retain a hidden promise of enforcement. Tests should measure acceptance
criteria, not merely mirror implementation. Mark synthetic fixtures clearly.
Receipts record argv, environment, source and wheel hashes, return code, and
limits. The public-tree scanner is heuristic, not a security certification.
Source docs and packaged copies must match.

Linux checks do not prove macOS, Keychain, launchd, or Codex session behavior.
Mac acceptance needs exact source/runtime identity, disjoint roots, no AgentOS
hooks, unchanged auth/config, fresh effective AGENTS, local lifecycle probes
without external writes, and rollback/readback. Report unrun target checks as
NOT_RUN; hooks are not part of acceptance.
