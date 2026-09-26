# Stage F14 — continuity guidance and English public release

Task: `task-fb3cedad5b71486e`

Status: public release published and managed Mac update verified on 2026-09-26.

## Objective

Finish the owner's two pending public AgentOS actions: make the MacBook
knowledge-continuity method available as host-neutral public guidance, and
publish and install the English public source candidate. The intended new
release identity is `0.5.1` / `v0.5.1`, provided that tag is still free at the
publication boundary. The baseline is branch
`codex/connection-scenarios-20260926` at `c5f47ba` with stable installed
`0.5.0` as the rollback anchor.

## Scope and design

Add one work-continuity guide and a reusable passport template to the packaged
public resources, referenced by the documentation index and knowledge/handoff
skills. This is a guided knowledge workflow, not a connection card or an
automatic device backup. The public content explains how to identify canonical
sources, date and verify project handoffs, separate data from pointers, find
local exceptions, and prove an independent recoverable copy before a device
clearance. A real user's populated passport remains in the external overlay.

Move source version and release metadata together; maintain CLI, Python, MCP,
source and packaged contract parity. Run local checks, privacy review, a clean
export, wheel build, offline installation fixture and fresh import. Review the
diff and deliver only to the canonical Crystal Strategy public repository. A
release requires an exact tag, GitHub release object, asset hash read-back and
an authorized account. Managed Mac installation requires an exact current
pointer, user-overlay compatibility, installer plan/apply, live read-back and
rollback anchor. Native hooks remain disabled. Website, PyPI, private runtime
retirement, private passport contents and user-data migration are outside scope.

## Acceptance

- The guide and template are generic, English, packaged, and do not contain any
  user's files, routes, credentials, account identifiers or live task titles.
- Version `0.5.1` agrees across package metadata, CLI, MCP, contracts and docs;
  the previous `v0.5.0` release is unchanged.
- All approved checks, public export, wheel inspection, privacy scan and diff
  review pass on the final source. GitHub source/tag/release and wheel bytes are
  read back before claiming publication.
- The managed Mac update is planned against the observed current release,
  applied only after compatibility proof, and read back without changing the
  external overlay or enabling native hooks.

Approved task checks: `continuity-check`, `full-tests`, and `install-fixture`
against `dist/crystal_agent_os-0.5.1-py3-none-any.whl`, built from a clean
temporary export. The wheel path is an ignored local artifact, not release
evidence until its hash and contents are reviewed.
Source, publication and installation are reported as separate evidence levels;
a failed external target gate yields an honest checkpoint.

## Rollback

Keep `v0.5.0` and the current managed release immutable. A source defect is
fixed in a subsequent version rather than rewriting an existing tag. If the
new managed release fails after activation, use the installer's exact planned
rollback to the verified previous release; never restore old hook integration
or overwrite user overlay bytes. A missing release capability prevents release
publication but does not invalidate a verified source candidate.

## Local evidence

On 2026-09-26, 267 Python tests passed, Ruff passed, and the clean public export
passed `tools/verify_public.py`. The clean-export wheel
`crystal_agent_os-0.5.1-py3-none-any.whl` has SHA-256
`b21325005ace0842103768de0744da53fdb61b987430dfa2fd94ad061941588a`.
It contains the English docs, setup catalog, continuity guide and passport
template. The Darwin arm64 Python 3.14.6 offline fixture passed install,
update, rollback, reactivation, package integrity and unchanged synthetic user
tree checks. The fixture did not use a real owner overlay or prove the live Mac
target.

## Publication and Mac read-back

Canonical source `75ebbee2624e3ea6801873fea9da24f501cfe04f` was pushed to
public `main` and immutable annotated tag `v0.5.1`. The [GitHub release](https://github.com/crystalstrategysup-prog/agent-os/releases/tag/v0.5.1)
names that same commit. Its downloaded wheel is 157156 bytes and matches
SHA-256 `b21325005ace0842103768de0744da53fdb61b987430dfa2fd94ad061941588a`;
the downloaded tagged source archive is 311502 bytes and matches SHA-256
`7c5e00bc70c0a5dd1141642857f08519784b9f9395e92e0a8f5f5ba5748ceb8a`.
Both match the locally reviewed artifacts.

The Mac installer planned release `0.5.1-b21325005ace` against observed current
`0.5.0-eee81cc03774`, reported no user-data or service writes, then applied
with that exact expected current ID. Live `current` now resolves to
`releases/0.5.1-b21325005ace`; its CLI reports `0.5.1`, setup discovery lists
the two English `guide_only` Telegram scenarios, and `doctor` reports PASS.
The owner and MacBook profiles remain selected. The external overlay inventory
had 49 files and SHA-256
`e2366ace7c90c2b3f27f375dc1c561a1bea0bf29d09329de76840be34e0d4d59`
before and after the core installer. The subsequent managed Codex integration
reported no conflicts, installed nine namespaced skills and updated only its
managed AGENTS block, with no auth, model or hook trust change. `hooks.json` is
absent. The prior managed `0.5.0` release remains the rollback anchor.

The installer and integration read-backs do not test behavior in a newly
started Codex session. The public work-continuity guide is a template, not an
independent backup or cloud-restore proof. Website and PyPI publication,
Windows execution, private provider installation, and retirement of older
private runtimes remain separate scopes.
