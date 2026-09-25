# F05 — public beta verification and release

Status: DOCUMENTED BEFORE PUBLICATION. Start from the F04 result and this exact worktree; do not publish the mixed handoff archive.

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
