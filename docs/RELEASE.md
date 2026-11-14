# Release policy

Current publication candidate: `0.8.0rc2042`, incorporating the reviewed Atlas/FE source lineage and bounded recovery v3 adapter. Package, CLI, MCP and release metadata must agree. This is a prerelease; source publication, target installation and actual recovery acceptance are separate.

Recovery v3 preserves workflow/native-turn identity and existing CAS/journal and finite supported-observer limits. It does not provide missing provider exact-origin capabilities. Old v1/v2-only readers are not safe rollback targets after real v3 metadata activation. No host activation, scheduler or native hook is implied. Earlier tags and published assets remain immutable.

The release gate includes final diff review, current unit and integration checks, complete docs, reproducible source inventory, wheel hash, clean install in a fresh venv, privacy review, and an exact publication allowlist. Publish only public core and intended artifacts; never a mixed private handoff, user overlay, credential, host path or `.agentos/` runtime receipt. A prepared archive is not a published release.

Release notes state behavior changes, breaking interfaces, config migration, tested platforms, known limits, source and wheel hashes, install and rollback route, and the next stage. The stable model policy is a proposal contract, not runtime enforcement. Hooks remain disabled, existing clients require manual reload after a later install, voice is unverified and API publication is not available to this local preparation.

Before an authorized publication, verify canonical remote, exact source and clean worktree. Afterwards read back the annotated tag, GitHub release object, and independently downloaded wheel and source ZIP. Do not claim PyPI availability without a publication receipt. Native hooks remain excluded on release and rollback.

## Historical candidates

The `0.7.0rc1`, `0.7.0rc2` and `0.7.0rc3` source candidates are preserved as historical local evidence. They were not publication receipts, installation proof, live runtime adoption, voice verification or API availability proof.
