# Completion acceptance implementation contract

## Purpose
Retain the original user outcome until checked semantic acceptance, verified artifact delivery and independent review. The supplied version 1.0.0 specification is authoritative for R01–R38 and T01–T34. Original TZ SHA-256: `91efdac60531afc3000585bd714f97d005441d07399e5a68a3ce96e01a860c11`. The complete input is preserved verbatim in the private implementation evidence workspace; it is not rewritten or included in the English public source. The public traceability map retains its requirement/scenario IDs and input digest. This document selects integration and execution scope rather than replacing that specification.

## Current state
Canonical repository https://github.com/crystalstrategysup-prog/agent-os, baseline b3dc12dfd447d4164c26a3045e1ae01f27309821, release 0.7.1. Coordinator already publishes immutable snapshots through one atomic HEAD with POSIX fsync and a publisher lock. Existing continuation preserves unknown delivery, provider receipts and accepted indexed results. These mechanisms do not yet provide a full completion supervisor or receiver effect fence.

## Boundaries
Extend the existing Coordinator snapshot state, continuation adapter and result gate. No second task store, background scheduler, host fleet controller, native hooks or retired private kernel. A separately invoked bounded step supplies actual executor I/O. Target authorization and authentication remain adapter responsibilities, independent from stored labels and supplied evidence.

## Constraints
Only canonical public source and isolated local synthetic AgentOS homes/workspaces are approved for these stages. No production, unrelated project, credentials, OS security, model/provider/settings change or other live session mutation. Publication follows separate candidate review and exact target authorization.

## Objective
Implement the specification without interpreting a finished turn, sender enqueue, hash, selection or provider ACK as business acceptance.

## Change scope
Coordinator gains a versioned embedded completion contract, events, policy/capability snapshots, command ledger/outbox, evidence and review references, delivery ACK, ownership epoch, cancellation fence and bounded recovery. Existing task/work rows remain in the same snapshot. Old APIs may not bypass an activated completion gate.

## Context
Original goal and criteria are immutable under a generation; approved contract/source changes invalidate dependent evidence. Local POSIX execution is the initial qualified completion adapter. Cloud/remote effect admission remains UNKNOWN until its current receiver proves fencing or quiescence and exact-operation reconciliation. Existing generic routes are preserved, with no new promise of remote continuation.

## Components
work_coordination.Coordinator owns snapshot publication and CAS. Completion methods extend it in the canonical completion module; continuation_adapter resolves typed operations and runs one approved step; result_gate verifies current evidence provenance and semantic criteria; handoff_store supplies fsync objects, bounded byte reads and publisher locks. Handoff artifact verification uses exact inventory and target readback.

## Trust boundaries
Trusted adapters authenticate the actor, receiver and current authority. JSON hashes prove byte integrity, never identity. Dispatch intent is durable before I/O, and receiver admission is checked atomically against generation, epoch, cancel fence and exact policy. Network I/O and subprocess waiting/output occur outside the snapshot lock. The local receiver starts its owned process within the minimal fence transaction; cancel/revoke/takeover before that boundary forbids spawn. Effect-fenced takeover still reconciles admitted unknown effects. Without fencing, lease expiry alone cannot establish quiescence.

## Decisions
Reuse the current immutable snapshot/HEAD backend. Add a versioned optional extension instead of migrating unrelated legacy rows automatically. Reject downgrade of activated completion data; restore verified predecessor backup after quiescence. Keep operational input/readback evidence outside public source; synthetic test fixtures alone enter the release.

## Interfaces
The completion API accepts explicit version, actor, time, event identity and current capability/policy evidence. No arbitrary shell surface is exposed. The local adapter runs registered argument arrays, bounded output/time and isolated workspaces. Goals are opt-in and capability/policy dependent; baseline continuation never enables them.

## Schemas
Use the supplied spec/schemas contracts and a versioned completion snapshot schema. Command identities bind source commit, contract, generation, criterion, target and strategy. Receipts bind operation, attempt nonce, epoch, exact runtime and actual captured evidence. Caller timestamps are checked for causal order and freshness. All statuses are separate from turn and child completion.

## Compatibility
Unactivated 0.7.1 coordination and continuation workflows are preserved and regression-tested. Activated completion data fail closed under older writers; unsupported downgrade must be rejected before data change. Local POSIX support is tested on the current machine. Other platform/adapter adoption remains UNKNOWN rather than inferred from source tests.

## Errors
Typed operation-local errors preserve AUTH_REQUIRED, POLICY_DENIED, TARGET_NOT_FOUND_FOR_OPERATION, OFFLINE, UNSUPPORTED, TRANSIENT, RATE_LIMITED, STALE_TARGET and UNKNOWN_OUTCOME. Only authoritative non-admission or valid receiver dedup permits retry. A read success never grants send/start/resume access.

## Entities
Existing coordinator parent and work rows; embedded completion contract, criterion receipts, event inbox, operation ledger/outbox, effect admission, capability snapshots, policy revision, lease epoch, pending handoff and review. Requested, assigned and actual model identities remain distinct.

## Storage
One fsync immutable snapshot contains each atomic mutation together with its event and outbox state. A bounded atomic HEAD is the commit point. CAS and lock prevent concurrent lost updates. Crash after intent commit remains UNKNOWN and is reconciled before another effect.

## Migrations
Explicit activation has dry-run and predecessor checkpoint. Schema from/to, invariants and rollback support are recorded. Unsupported versions are refused. Restore rehearsals verify captured tracked/untracked source bytes and snapshot state before replacing a selected isolated canary.

## Deletion
No automatic deletion of user work, old operations, unknown outcomes or cancellation records. Retention bounds stop admission instead of losing history.

## Channels
Completion events are explicitly delivered through the current adapter, without installed hooks. Finish/reconnect/budget/approval changes trigger one bounded evaluation; WAITING_USER has no turn polling. Cancellation dominates old completion events. Duplicate event identity is durable and cannot schedule a second effect.

## Delivery
Persist intent before dispatch; reconcile ambiguous responses. Handoff verifies actual artifacts, commit, contract/manifest hashes and receiver context. Only a fresh exact receiver ACK permits ownership change; late or mismatched ACK stays audit evidence.

## Assets
Original user outcome, workspaces, task snapshots, private overlays, approved capabilities, public artifact provenance and current recipient binding.

## Threats
Paused old sender, coordinator crash, stale ACK, lost response, duplicate events, receiver downtime, replay, policy revoke between discovery and effect, traversal/symlink artifact substitution, forged PASS, budget loops and contaminated public archives.

## Authority
Only current exact owner-approved action/target/receiver/data/environment/policy revision and expiry allow effect admission. Stored authority references and project READY grant no external capability. A denied operation cannot be routed around by changing adapters.

## Secrets
Never publish private profiles, source session logs, auth data, account/host identifiers or production routes. Public input is the owner-provided sanitized specification; source tests and fixtures are synthetic. Scan exact archive bytes and metadata before candidate delivery.

## Stages
P0 discovery/integration review; P1 baseline reproductions and contract; P2 implementation and old-workflow regressions; P3 deterministic fault/race tests and independent review; P4 isolated local canary/checkpoint/restore; P5 candidate/build/install/privacy and final review. Gate dependencies come from the supplied acceptance matrix.

## Dependencies
Durable state precedes outbox and receiver admission; those precede autonomous steps. Functional PASS cannot replace actual adapter/canary or final artifact checks. Goals support is optional; mandatory safety/degradation and no-Goals end-to-end remain required.

## Next stage
P0/P1 review and baseline checks precede implementation. Current P2/P3 source checks do not claim target acceptance or publication; P4/P5 need actual canary, install and independent candidate receipts.

## Acceptance
Every applicable MUST maps to an executable fresh receipt. NOT_RUN blocks its required gate. Independent reviewer closes all blocking findings; semantic evidence and recipient ACK are checked against actual bytes. Gates cannot report release PASS before postpublication readback.

## Rollback
Preserve the original checkout and its untracked work. Stop only isolated canary dispatch, reconcile its admitted operations, verify checkpoint hashes, restore exact predecessor bytes and reject unsupported downgrade. Existing owner runtime and other projects remain untouched.

## Checks
Registered local pytest regressions and build; additional deterministic subprocess/crash tests, schema/traceability validator, provenance/privacy scan and isolated wheel installation. Network/model calls and external sends are excluded from synthetic checks.

## Evidence
Receipts record actual run identity, build/source/contract/config/environment digests, command/exit code, artifact/log hashes and independent reviewer. Baseline, documentary validation, product tests, target adoption and final acceptance are different statuses.

## Limitations
A Python API and synchronous adapter do not create an always-running service or prove live adoption by existing sessions. Remote/cloud completion and Goals activation remain UNKNOWN unless qualified separately. Publisher-lock backend is POSIX; unsupported platforms fail closed.

## Installation
Build the exact reviewed source with the repository's setuptools backend; install candidate wheel only into disposable test environments in the approved local canary.

## Verification
Verify input bytes, current source, receipt provenance, exact artifact inventory and installed runtime readback. Preserve failed receipts and rerun only affected checks after changes.

## Update
No automatic installation into the owner's managed pointer. Candidate update exercises predecessor state on disposable homes with schema preflight and backup.

## Recovery
Crash recovery reloads the atomic HEAD; pending intent remains owned, unknown effects require reconciliation, cancellation and expired authority remain effective. Reinitialization increments generation/epoch only after checkpoint, policy and safe takeover verification.

## Versions
Predecessor 0.7.1; this source candidate is 0.8.0rc2. No publication or installed owner runtime is claimed.

## Contents
Public core, mirrored public docs/contracts, preserved sanitized specification and synthetic tests. No working state or private operational receipts in candidate.

## Publication
Candidate preparation does not publish. An exact immutable candidate and verified canonical target precede separate authorization; unknown publish outcome is reconciled before any retry.

## Getting started
Read the authoritative supplied spec then this integration decision. Run only the registered checks in an isolated development environment. Do not reuse an unqualified live worker as a canary.

## Navigation
Existing canonical modules and docs remain the entry points. This extension uses WORK_COORDINATION, PROCESS, SESSION_LAUNCH and existing result/handoff contracts; no separate universal policy is introduced.

## Commands
Use explicit CLI project entry and documentation readiness, then registered checks. Completion integration uses the existing Coordinator API and an explicitly configured adapter.

## Troubleshooting
Report concrete operation-local blocker and next owner. Reconcile unknown outcomes; do not retry by elapsed time, fabricate model/runtime identity or close the parent because a turn ended.

## Systemic mutation re-review
Read [MUTATION_SURFACES.md](MUTATION_SURFACES.md) and its executable inventory for all public mutations, pure audit versus ledger resolution, and owner/lease/policy/terminal/replay matrix. Prior candidate acceptance does not cover new changed bytes. G2 re-review needs the full current systematic regressions and independent final-byte review.
