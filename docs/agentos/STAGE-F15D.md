# Stage F15D — publish AgentOS 0.5.3

Task: `task-c68683d75a4e4186`

Status: local release checks passed; publication pending.

## Objective and authority

Owner instruction on 2026-09-26: make the release. Publish the reviewed F15B/F15C
SSH/RFB candidate to the canonical public crystalstrategysup-prog/agent-os
repository as stable v0.5.3. Screen Sharing and desktop viewer integration
remain deferred. This task does not update the installed foundation or hosts.

## Scope and architecture

Diagnostic implementation and machine contracts are unchanged. Update release
stage/dossier/roadmap and publication evidence, build a clean public source
archive and wheel, validate package parity and privacy, run local checks,
review the diff, push main and an annotated tag without force, then publish the
GitHub release under the existing owner account. Publish only the exact source
ZIP and wheel; exclude local task records, private routes and user overlays.
No GitHub Actions, private Helper, website, PyPI, hooks or credential changes.

## Acceptance and checks

- Registered full-tests and install-fixture pass for the rebuilt wheel.
- Source/resources, version surfaces and wheel files match; public export passes.
- Canonical main/tag match reviewed source, release targets v0.5.3 and names
  artifact hashes and honest platform/proof limits.
- Downloaded release assets match local SHA-256 hashes; verify Latest.
- Do not claim installation or VNC authentication/frame from these checks.

## Rollback and limitations

Keep v0.5.2 immutable. Reverting source uses an ordinary reviewed commit; the
release does not change any host runtime. Installed stable remains 0.5.2.
Windows diagnostic execution and desktop viewer support remain unverified.
One-host SSH/RFB evidence is bounded and not universal device setup proof.

## Evidence

Publication receipts will be appended after exact tag and asset read-back.

## Local candidate verification

278 tests passed; registered full-tests receipt `86a4a712386149fbb4a7993ca41d87e6`.
Ruff lint and formatting of the changed Python files passed. A full-tree format
check found pre-existing unrelated formatting differences; no unrelated files
were rewritten. Source/resource parity and clean public export validation passed.
No blocking findings in final review of the diagnostic, CLI, schema and deferred
viewer card. Force-kill cleanup and Windows execution remain unproven.

Rebuilt wheel `crystal_agent_os-0.5.3-py3-none-any.whl`: 169252 bytes, SHA-256
`ecc905905844f063d060014ef65c0ed1f44375e722d6bf84854887ae6a2f6580`.
All 110 packaged agent_os files match source. Darwin arm64 Python 3.14.6 offline
install/update/rollback/reactivation and synthetic user preservation passed;
receipt `6b9c2500ba1f4eb39e65a598e947ebc1`. This is an isolated fixture,
not a managed owner-Mac update. The tagged source excludes local task receipts
and untracked closeout reports. Download verification remains required.
