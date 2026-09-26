# Stage F15D — publish AgentOS 0.5.3

Task: `task-c68683d75a4e4186`

Status: PUBLIC RELEASE PASS; owner-Mac installation not requested.

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

## Publication and download read-back

Reviewed source `aaf33929db6e17b57a02cc750530bc53e0c1ebc9` was pushed directly
to canonical public main and annotated tag `v0.5.3` without force. The tag object
is `381825bd72c183b9900c13ea71a1db9ec31e5647` and peels to that exact source.
The stable [GitHub release](https://github.com/crystalstrategysup-prog/agent-os/releases/tag/v0.5.3)
was published by `crystalstrategysup-prog` at `2026-09-26T02:51:03Z`, release
ID `397047878`, with Latest displayed, draft=false and prerelease=false.

Downloaded source ZIP `agentos-0.5.3-source-aaf3392.zip`: 345051 bytes, SHA-256
`939eddfa4469f137aaf39f01f25bd44ad9edb7321034c29da7dcb48bd2824fb7`.
The downloaded wheel is 169252 bytes and matches the rebuilt hash above.
Both assets match local bytes. GitHub-generated source links are separate from
the reviewed uploaded ZIP. No Actions run or live installed-runtime change was
used. Installed stable remains 0.5.2; Screen Sharing and viewer support remain
deferred. Publication evidence is recorded after the immutable release source.
