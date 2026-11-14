# AgentOS normalization — source stage

Task: `task-d6f4bfc9625648c0`
Base: `92bcbd50a2e91c7eb28ce2265445ea10d6b0ef41`.
Stage contract: prepared. Exact source-bound receipts and final review establish acceptance; this document alone does not.

## Purpose
Make the existing modules dependable and proportionate for project and API work.
## Current state
A complete source checkout and inherited diagnostics/recovery integration are available. Baseline tests and targeted reproductions establish current behavior.
## Boundaries
Core owns local lifecycle and safe I/O. Atlas owns derived project/API catalogs. Projects own domain contracts and runtime state. Package tooling ships reviewed canonical inputs.
## Constraints
No target deployment, external messages, private user data, model settings or permissions are changed. Preserve UNKNOWN and historical evidence.
## Stages
Baseline; reproduce; isolate and repair; integrate; regress; package; publish source handoff.
## Dependencies
Read authoritative module contracts before editing. Root owns integration, pins, version and publication; module workers own disjoint files.
## Next stage
Review tested candidates and record actual remaining defects before any runtime adoption.
## Objective
Repair observed API information loss, inventory read bounds and package validation gaps.
## Change scope
Atlas catalog and native activity indicators with relevant tests/references; safeio inventory and race tests; installer schema readers and document sync; public module contracts, version-identity regressions and build provenance.
## Acceptance
N1: preserve integrity and UNKNOWN regressions. N2: faithful OpenAPI declarations. N3: public source/package parity. Complete test outcomes remain separately reported.
## Rollback
Revert the isolated source commits. No live runtime migration occurs in this stage.
## Checks
Run the repository core suite, Atlas check, public contract verifier and document parity check. The public verifier runs in a clean worktree of the same committed source, matching the release tool's clean-source boundary; active local receipts stay outside that public tree. Record pre-existing failures separately.
## Evidence
Root retains command outputs, source versions and test summaries; synthetic tests do not establish host acceptance.
## Limitations
No claim of exhaustive absence of bugs, live deployment, all OpenAPI versions or external provider qualification.
## Context
The owner requested efficient modular engineering across projects/APIs/contracts.
## Components
Core safeio and project lifecycle; Atlas semantic catalog compiler; offline packaging and installer verification.
## Trust boundaries
Imported specifications are untrusted data and never executed. Local test fixtures are isolated. Target authority remains external.
## Decisions
Repair canonical modules; retain public interfaces and explicit unsupported behavior; avoid adding a new orchestration system or HTTP server.
## Interfaces
Existing CLI/MCP/Python and atlas.semantic-catalog/v1; project-owned HTTP APIs stay in their projects.
## Schemas
Preserve literal declared values and unresolved references; reject ambiguous inputs explicitly.
## Compatibility
No state migration, dropped reader or changed permission contract. Package mirrors are generated from exact canonical sources.
## Errors
Unknown external outcomes require original-operation readback. Validation failures never authorize alternative effects.
## Assets
Public source and tests only; no credentials or private overlay in commits.
## Threats
Reference cycles, malformed specs, source substitution while hashing, contradictory schema keys and stale package mirrors.
## Authority
Owner's current normalization request covers source/test/branch work; root coordinates the shared result.
## Secrets
Use synthetic examples. Scan actual diff before publication.
## Versions
Candidate version is updated only with integrated changes; historical provenance stays intact.
## Contents
Full source repository, targeted module fixes, regressions and public documentation.
## Publication
A reviewed feature branch and draft PR are source delivery; merge and runtime adoption are separate.
## Getting started
Use a local Python environment and existing package entry points.
## Navigation
AGENTS routes to Atlas; docs/ARCHITECTURE.md and docs/CONTRACTS.md describe core boundaries.
## Commands
pytest, modules/atlas/check.py, tools/verify_public.py, tools/sync_resources.py.
## Troubleshooting
Keep exact failure codes and original evidence; distinguish baseline failures from introduced regressions.
## Installation
Only a disposable wheel installation is used for verification.
## Verification
Compare current source and package bytes and exercise relevant entry points.
## Update
No automatic installed-host update.
## Recovery
Preserve journals and original operation identifiers. Reconcile before repeating effects.
