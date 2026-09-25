# F05 — public beta verification and release

Status: PUBLIC BETA PUBLISHED; LIVE MAC AND WEBSITE DEPLOYMENT BLOCKED BY EXISTING HOST GATES. Start from the F04 result and this exact worktree; do not publish the mixed handoff archive.

## Target and boundaries

Publish the reviewed public foundation as `v0.5.0-beta.1` from canonical `origin/main`, then publish the maintained static website correction after the tag exists. The public site target is `https://crystalstrategy.ru/agent-os/`; `/agent-os/community/` is a different auth-gated route. This stage may install the public release into a new, separate Mac foundation location only after a read-only conflict preflight; it must not repoint or modify the existing private AgentOS runtime. A real GitHub Release object, PyPI upload, Windows support, native hook enforcement and website deployment need their own actual read-back before being claimed.

## Publish inventory and checks

1. Recheck remote main/tag identity and both worktrees' tracked/untracked files. Stage only the public repository's intended docs, schemas, package code, tests, examples and tools. Exclude `.agentos`, caches, venvs, generated distributions, the supplied handoff and all user overlays.
2. Run `git diff --check`, full tests, public-tree validator, contract validation, wheel build and clean install probes. Review meaningful changed code and secrets/host paths. Record final wheel and source commit hashes.
3. Fast-forward the canonical public main only if its remote head still equals the verified base. Create an annotated tag on that commit, push it without force and read back the public GitHub tag/source link. Publish a GitHub Release object and attach the verified wheel only if an authorized release API/UI is available; otherwise state that the tag is published but no Release object/assets exist.
4. Fast-forward the maintained site source only after the tag's public read-back. Verify the live public route, release links and install command. If deployment is outside the Git push path or the route remains gated, record that exact residual state rather than claiming the website is updated.
5. For any side-by-side Mac install, preflight existing paths and permissions, apply only to the new core/user location, run installed CLI/MCP read-back and preserve the previous runtime pointer. Keep native hooks disabled until actual trust and negative-write proof.

## Acceptance and rollback

Public source must be reachable at the exact beta tag, version surfaces must agree, the package install must pass on tested targets, and published instructions must resolve to that tag. A push failure leaves the reviewed local commit available without a false release claim. If a site source push succeeds but live route does not update, leave its source commit and report the deployment gap. No force push, destructive cleanup or implicit private-user migration.

The F05 closeout records the exact source SHA, tag, wheel hash, public URL read-back, website source/live state, Mac target state, test summary and unresolved limits. Update the dossier and roadmap from those facts.

## F05 result — 2026-09-25

- Canonical public `main` and annotated `v0.5.0-beta.1` resolve to source commit `4b6d59e82cc74a3991e5cbd3c607d49caaf6c8ee`. [GitHub pre-release](https://github.com/crystalstrategysup-prog/agent-os/releases/tag/v0.5.0-beta.1) is published with wheel `crystal_agent_os-0.5.0b1-py3-none-any.whl`. The public asset's downloaded SHA-256 matched `d322d32d00b1c4a14baf520694234e28a45e10ae019845650b10e893461313d2`.
- Full local suite: 153 PASS, Ruff PASS, public-tree validator PASS, synthetic lifecycle PASS. Disposable Darwin arm64 offline install/update/rollback/overlay fixture PASS on the released wheel. Linux arm64 Python 3.12 fresh wheel/init/doctor/resources/MCP smoke PASS. A fresh clone of the published tag installed in an isolated Mac venv, and `init`/`doctor` returned PASS. Windows and actual native hook activation were not run.
- Maintained website source `agent-os-site` `main` is commit `00993354b2c927832fd594960d8974cd1eb4d626`, with beta copy and tagged source installation. Live `https://crystalstrategy.ru/agent-os/` still returned the old 0.4.0 HTML, broken PyPI command and `Last-Modified: 2026-09-20`; Git push did not deploy it. The site runs on service-host, whose installed host-mutation inventory does not allowlist this AgentOS site scope. No unrelated production lease was borrowed. Release notes explicitly direct visitors to the verified tag.
- Side-by-side Mac core/user target paths are absent and existing private runtime was not touched. The installed Mac host-mutation gate requires root even for status/plan, while noninteractive sudo requires a password. No live Mac installation, user-overlay import, private-runtime replacement or native hook change was performed. The disposable Mac fixture is the available proof, not a live target receipt.
- PyPI remains unpublished. No GitHub Actions or mixed private handoff content was published. The source and website commits are the rollback anchors. A future site deployment needs an authorized allowlisted lease/profile and exact host read-back; Mac installation needs the normal root/gate path and separate preservation checks.
