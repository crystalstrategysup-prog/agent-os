# F09 — source-only workflow correction

Status: LOCAL_CANDIDATE_FOR_INDEPENDENT_REVIEW. Version 0.5.0-beta.5 / 0.5.0b5.
Scope: supplied public beta.4 tree and sanitized settings evidence, not live host state.
Prior to implementation the local curator recorded DECISION.md in the review workspace;
this stage publishes that architecture decision in portable form, not retroactive runtime evidence.

## Goal / architecture

Read-only work is immediate; product changes retain docs-first entry/checks/closeout.
Remove global native callbacks and their installation rather than broaden brittle shell
allowlists. Keep no-op entrypoints for stale references, explicit turns separately,
bounded stdin, same-scope reuse excluding authority, independent optional observations,
explicit current closeout verification. Keep target authority at real executors, not profiles.
ADR-008 / PROCESS / SECURITY_MODEL specify limitations: no universal sandbox claim.

## Write-set / non-goals

Public Python lifecycle, integration, CLI/MCP contracts, regression tests, mirrored docs,
9 skills, version metadata and local demo/install next-step text. No new runtime dependency.
Owner overlay/AGENTS changes are a separate proposal, not installed or mixed into public core.
No publish/tag/push, Mac install/current switch, auth/model/security config modification,
other host/service writes, production/DB/deploy actions or native-hook activation.

## Acceptance A–F

A direct read-only/unregistered cwd; B new local docs/code/real tests; C undocumented existing
project; D same-scope continuation with current authority; E declared target effect refusals
and preserved exact scope/dispatch/MCP gates; F no hook restore/Stop loop/fake closeout,
legacy receipt compatibility and post-close evidence drift. Tests run in temporary fixtures.

## Verification / release boundary

Baseline and candidate test logs, input/source/wheel hashes, patch apply/reverse verification,
public-tree scan and wheel smoke belong in the curator handoff. Test counts are recorded there,
not asserted before execution in this stage. Actual Mac/Codex effective instruction acceptance
is NOT_RUN here; integrate only after independent source review and a separately authorized
local target stage. Existing historical receipts are not fresh candidate evidence.

## Migration / rollback

Apply exact patch to matching clean source; no schema migration of user profiles/config.
Refresh no-hook AGENTS/skills only after resolving conflicting owner blocks independently.
Old bound task receipts require real checkpoint/close before explicit transition; unbound
prompt receipts remain inert until explicit entry. Checks bind version/module hash: resume
unclosed tasks and recheck; never rewrite old CLOSED evidence. Reverse patch on clean source
restores baseline; deployment rollback must keep hooks disabled and never run old integrate.
