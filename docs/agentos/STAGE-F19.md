# Stage F19 — verified public release and managed fleet adoption

Task: `task-2419e33e1e6a4197`

Status: VERIFIED RELEASE AND HOST ADOPTION, 2026-09-26. Owner authorized public release and deployment after private retirement.

Version reviewed F18 provider-independence guidance as 0.5.5; preserve immutable prior releases. Public source and package contain universal rules only. User profiles, host adapters, credentials and rollout evidence stay outside the core. No new executable provider, hook or business integration is introduced.

Exact changes: public version declarations including schema mirrors and version-contract tests, current install/release guidance, packaged mirrors and stage/handoff documents. Run full-tests, resource-parity and offline install/update/rollback fixture, review clean public export and wheel composition. Publish directly to canonical main and annotated v0.5.5 plus verified source/wheel release assets; GitHub Actions excluded.

Separate owner-authorized host rollout uses exact offline verified wheel, current user/host binding, installed plan and observed expected-current. Preserve disjoint external user overlays byte-for-byte during core activation. Managed integration writes only managed AGENTS/skills with backups and conflict checks. Test fresh installed-process read/project workflows; do not claim a fresh Codex client session. Target authority and actual readback govern remote effects; no credential/auth/model/trust/SSH/VPN changes; narrowly update an existing public MCP command to the managed current public Python and add absent per-user public CLI launchers, preserving all other configuration with exact backups and parsed comparison. No service restart or business DB write. Retired private providers stay inactive. Remote first installations have no previous public release to roll back to; retain artifact/preimages and never restore private code or hooks.

Local acceptance is source/tests/publication review; actual host receipts are separate evidence and never inferred from local closeout. Record target residuals honestly. Website, PyPI and private-scenario implementation remain outside scope.

## Local verification before publication

278 tests, resource parity, Ruff lint, complete diff review and clean public export passed. Offline Darwin arm64 Python 3.14.6 install/update/rollback fixture passed. Clean-export wheel has exact parity for 112 package files and excludes obsolete build-cache content. Wheel SHA-256 `f299847753acef17073e24d9850f72b48ce54a6f08f52313b69682477abea039`, 174672 bytes. No blocking findings. Machine protocols/config schemas are unchanged; version fields advance to 0.5.5. No fresh Codex client or Windows proof is claimed. Publication and host activation have separate verified receipts; see the result below.

## Publication and adoption result

At publication, canonical main and annotated `v0.5.5` pointed to `cd003615c4f4c11170a936849535ff53cbfc627a`. GitHub release ID `397114615`, published `2026-09-26T06:04:17Z`, is a stable Latest release: https://github.com/crystalstrategysup-prog/agent-os/releases/tag/v0.5.5. Downloaded source ZIP SHA-256 `c027d40d87e96df756d02efe8116e9651c9072b70b8e0bd3622d705ad23a9a29` and wheel SHA-256 above match the reviewed local artifacts. Prior tags/assets are preserved.

Owner-authorized adoption verified five active macOS/Linux hosts and nine runtime user contours. Every contour reports 0.5.5, doctor PASS, managed AGENTS/skills integration and fresh installed-process read-only/project lifecycle smoke PASS. External overlay files remained unchanged during core activation; auth/model/trust/SSH configuration remained unchanged during installer/integration. Native hooks remain absent/disabled. Existing private providers remain retired. Exact target identities, protected-file hashes and receipts stay in the external owner overlay/report store. These are bounded installation/workflow checks, not a full business application health audit.

One service user has its Codex home equal to its OS home. Initial integration correctly refused a core nested inside that Codex home; the verified core was instead installed into a separate sibling directory without relaxing checks. The unintegrated public copy is preserved as inactive history. Stable per-user CLI launchers invoke the verified current core; PATH and service environments were not modified. The Mac's existing public MCP command was pinned to 0.5.0: only that command was updated to the managed current Python, with exact backup and parsed whole-config comparison. A fresh MCP initialize response reports 0.5.5. Existing connected clients were not restarted; reconnecting a long-running client may still be required.

No business application, DB, Telegram send, private-provider restoration, Screen Sharing, website or PyPI deployment is included. Remote first public installations have no previous public rollback release. Local closeout is separate from the actual published/host receipts and grants no later external authority.
