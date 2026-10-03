# Release policy

Current public version: `0.7.1`. RC-labelled sections below are retained historical records, not current installation or publication claims.


The current source proposes patch release `0.7.1` after the published canonical `0.7.0` baseline. The release tag must be `v0.7.1`; package, CLI, MCP and current documentation surfaces must agree. Earlier tags/assets remain immutable. This source document is not a publication or target-adoption receipt.

The release gate includes final diff review, current unit and integration checks, complete docs, reproducible source inventory, wheel hash, clean install in a fresh venv, privacy review, and an exact publication allowlist. Publish only public core and intended artifacts; never a mixed private handoff, user overlay, credential, host path or `.agentos/` runtime receipt. A prepared archive is not a published release.

Release notes state behavior changes, breaking interfaces, config migration, tested platforms, known limits, source and wheel hashes, install and rollback route, and the next stage. The stable model policy is a proposal contract, not runtime enforcement. Hooks remain disabled, existing clients require manual reload after a later install, voice is unverified and API publication is not available to this local preparation.

Before an authorized publication, verify canonical remote, exact source and clean worktree. Afterwards read back the annotated tag, GitHub release object, and independently downloaded wheel and source ZIP. Do not claim PyPI availability without a publication receipt. Native hooks remain excluded on release and rollback.

## Historical candidates

The `0.7.0rc1`, `0.7.0rc2` and `0.7.0rc3` source candidates are preserved as historical local evidence. They were not publication receipts, installation proof, live runtime adoption, voice verification or API availability proof.
