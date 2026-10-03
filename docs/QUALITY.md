# Verification strategy

Current public version: `0.7.1`. RC-labelled sections below are retained historical records, not current installation or publication claims.


## Historical: Indexed handoff successor0.7.0rc1

Run synthetic indexed handoff, lifecycle and100k actual accepted-package tests. Required claim evidence includes exact oracle matches, clean process recovery, corruption/ACL/CAS negatives and measured page/disk metrics. See [indexed handoff](INDEXED_HANDOFF.md).

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

F14 checks the generic continuity guide and template for required evidence and
recovery boundaries, public/private separation, source/package parity and
absence of personal data. A clean-export wheel must contain both resources.
Version identity is checked in the package, CLI and MCP, and the installer
fixture must keep user-overlay bytes and rollback anchors intact. Release and
live Mac read-back remain separate target evidence beyond fixture tests.

Linux checks do not prove macOS, Keychain, launchd, or Codex session behavior.

F15B uses a fake SSH process to exercise fixed arguments, bounded output and
timeouts, RFB protocol parsing, failed channels, cleanup and keyboard interrupt.
A separate live exact-host invocation records authenticated SSH and RFB
transport. Neither test is VNC login or framebuffer proof; that requires the
approved viewer and a current frame on the selected device before claiming the
owner's complete reference procedure.
Mac acceptance needs exact source/runtime identity, disjoint roots, no AgentOS
hooks, unchanged auth/config, fresh effective AGENTS, local lifecycle probes
without external writes, and rollback/readback. Report unrun target checks as
NOT_RUN; hooks are not part of acceptance.

## Historical: Narrow independent HOLD delta in0.7.0rc1

Affected checks include link-containing approved scopes for close and checkpoint, metadata recovery/no alias read, link identity and Git index drift before acceptance, absent/unbound/unavailable/mismatched/corrupt dependency captures, complete-positive restored bytes and legacy unbound dependency PARTIAL behavior. Run indexed/source-link/lifecycle/foundation/contract/persona/profile regression plus mirrored document/schema parity, lint and offline package checks. Independent exact source/package delta review still gates adoption/publication.

The prior100k run is evidence for its recorded original source hash. A narrow lifecycle/dependency-validation repair may inherit it only with unchanged exact store/index and scale-test hashes and an explicit applicability statement; it must not be reported as a new-source100k execution. Logical retirement still reclaims0 bytes, physical session cleanup remains NOT_IMPLEMENTED and real session deletion NOT_RUN.

## Historical: Main coordination successor0.7.0rc2

Candidate0.7.0rc2 verifies indexed completion→original-goal review→remaining→owned next action, orphan/partial negatives, selected missed-notice recovery, immutable/CAS decisions and registry recovery, independent checkpoints, actor/dependency/resource/capacity boundaries and three isolated disconnect windows. No real network/VPN disruption. Exact counts belong to source-bound execution receipts; inherited100k metrics retain predecessor SHA and are NOT_RUN on this successor unless explicitly repeated.

The isolated rc2 independent P1 repair additionally checks late partial and
completed reports awaiting review, supersession/retraction between receipt,
review and parent verification without a notification, out-of-order historical
notices/reviews and effect receipts, exact retry idempotence, immutable closed
state and successful original-goal closure only after current accepted review.
Preserve the original rc2 HOLD and bind new receipts/packages to the new source.

## Historical: Model-selection successor0.7.0rc3

Check current/unknown catalog, latest available Sol without alias, no automatic Luna/Astra fallback, exact scoped exception, unsupported effort/model/environment intersections, conservative task basis and explicit escalation/quality acceptance. E/max require complete referenced comparative quality/latency/cost claims. Preserve fixed/unknown mandatory constraints and independent bound runtime metadata; requested/assigned never become actual. Config upgrade keeps stored owner values without granting agreement. Run routing/CLI/config plus inherited coordinator/indexed/source-link/lifecycle/foundation/contracts/persona/profiles/continuation gate, parity/lint, exact package and isolated proposal smoke. Tests are synthetic; benefit/capability/authority records are trusted adapter inputs, not remote authentication.
