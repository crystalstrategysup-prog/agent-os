# Stage F19 — verified public release and managed fleet adoption

Task: `task-2419e33e1e6a4197`

Status: DOCUMENTED PLAN. Owner authorized public release and deployment after private retirement.

Version reviewed F18 provider-independence guidance as 0.5.5; preserve immutable prior releases. Public source and package contain universal rules only. User profiles, host adapters, credentials and rollout evidence stay outside the core. No new executable provider, hook or business integration is introduced.

Exact changes: public version declarations including schema mirrors and version-contract tests, current install/release guidance, packaged mirrors and stage/handoff documents. Run full-tests, resource-parity and offline install/update/rollback fixture, review clean public export and wheel composition. Publish directly to canonical main and annotated v0.5.5 plus verified source/wheel release assets; GitHub Actions excluded.

Separate owner-authorized host rollout uses exact offline verified wheel, current user/host binding, installed plan and observed expected-current. Preserve disjoint external user overlays byte-for-byte during core activation. Managed integration writes only managed AGENTS/skills with backups and conflict checks. Test fresh installed-process read/project workflows; do not claim a fresh Codex client session. Target authority and actual readback govern remote effects; no credential/auth/model/trust/SSH/VPN changes, service restart or business DB write. Retired private providers stay inactive. Remote first installations have no previous public release to roll back to; retain artifact/preimages and never restore private code or hooks.

Local acceptance is source/tests/publication review; actual host receipts are separate evidence and never inferred from local closeout. Record target residuals honestly. Website, PyPI and private-scenario implementation remain outside scope.

## Local verification before publication

278 tests, resource parity, Ruff lint, complete diff review and clean public export passed. Offline Darwin arm64 Python 3.14.6 install/update/rollback fixture passed. Clean-export wheel has exact parity for 112 package files and excludes obsolete build-cache content. Wheel SHA-256 `f299847753acef17073e24d9850f72b48ce54a6f08f52313b69682477abea039`, 174672 bytes. No blocking findings. Machine protocols/config schemas are unchanged; version fields advance to 0.5.5. No fresh Codex client or Windows proof is claimed. Publication and live host installs remain separate pending readback at this source commit.
