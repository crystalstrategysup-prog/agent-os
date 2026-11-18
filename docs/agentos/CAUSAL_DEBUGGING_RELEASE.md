# Causal debugging release contract

Task: `task-2a6ddad4532346a5`

## Purpose and current state

Ship mandatory evidence-based causal debugging through existing AgentOS engineering workflows. Base source: `af332457c41d1b0f5cb9aa2d1be9c11280ade48e`, version `0.8.0rc2054`. This record covers one release increment. It does not rewrite historical accepted stages or establish target installation.

## Objective, change scope and architecture

Keep one normative causal-debugging section in PROCESS.md. Existing Atlas and project-entry, implementation, handoff and closeout instructions load that rule. A bounded public-resource reader returns actual section bytes and hashes. The existing workflow and context commands use it for engineering entry and continuation; ordinary direct reading stays independent of profiles and task intake. Native hooks, access rules, schemas for saved user data and existing worker lifecycles are unchanged.

## Interfaces, compatibility and errors

The additive read-only `workflow guidance` response identifies the installed version, canonical document and section hashes, actual content, and unproven behavior. Engineering route/context results carry this same content. Invalid or unavailable canonical section fails only a dependent guidance request; no fallback fabricates content. Existing context receipts bind the guidance bytes, so a changed method requires a fresh capsule. No user-data migration is required.

## Stages, dependencies and checks

1. Inspect canonical source, source policy, current package and actual integration routes.
2. Update the existing process and loaders; retain one writer and disjoint delegated source areas.
3. Run meaningful guidance and executable scenario tests, existing relevant regressions and the current full source suite.
4. Start independent fresh agent sessions on ordinary fault requests. Retain raw actual probes and review five cases: one constraint, broken baseline, interaction, nonreproduction, and protected access. Test code alone is not this behavior evidence.
5. Review public diff/privacy and exact mirrors; create reproducible wheel/source assets and rehearse isolated installation and rollback.
6. Push reviewed source to the canonical repository; publish exact release assets and independently read them back. Separately apply through existing managed installer and integration, preserving overlays and observing each target.

## Acceptance and evidence

A fresh session chooses distinguishing experiments without a method hint in its task. Reversible causality needs work/fail/recover/fail with equal scenario and data; a failed baseline and nonreproduction remain explicit. Protected authorization, permissions, isolation and data integrity stay intact. Journal rows contain factor values, fixed conditions, expected/actual outcomes, error location, evidence and next step. Prepared, locally checked, installed and target-verified remain separate. Runtime receipts stay outside public source.

## Security, operations and release

Public source is host-neutral. No credentials, private host paths, user data or transcripts enter the package. Local tests use only disposable synthetic data. Publish a new prerelease version with consistent source/CLI/MCP metadata, deterministic build pin, manifest and checksums. Apply only the owner-authorized targets through their existing accounts and protections, compare the exact current pointer and preserve all previous immutable releases. Read back effective AGENTS and managed skills as well as CLI identity.

## Rollback, limitations and next stage

Revert the scoped source commit for source rollback; for managed targets use the existing installer's verified predecessor rollback and restore only exact managed integration bytes when compatible. Never restore hooks or change auth/settings. Installation and matching instruction hashes cannot prove cognition or that existing workers reloaded. This release makes future entry/resume guidance available and tests actual new isolated sessions; later live incident acceptance still needs that incident's original scenario. Next stage is completion of the evidence and separately authorized target readback, not another diagnostic regulation.
