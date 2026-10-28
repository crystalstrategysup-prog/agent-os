# Agentas installed source candidate

Candidate: `0.8.0rc2041+agentas1`. This branch preserves the public Atlas patch lineage and imports the reviewed rc2041 source, tests and tooling. All 397 package files are compared with the exact installed wheel; the manifest is `.release/0.8.0rc2041+agentas1-source.json`.

The optional Atlas CE binding checks physical source bytes and the existing FE/CE verifier pins. It does not copy a user overlay, grant live authority, or implement a hard same-user security fence. Private handoff files, host inventories, qualification payload archives, operational receipts and credentials are excluded from Git.

Prior scoped importer proofs and actual managed installation checks are reused at matching hashes. Current publication checks cover source/package identity, resource mirrors, source CLI version and public data boundaries. Full native business acceptance and a full regression of all future backlog items are not claimed. New edge cases remain separate work, driven by actual failures or needed functionality.

This is branch source publication. It creates no official tag, release asset, deployment or automatic merge. Existing releases and separate user overlays remain intact. The PEP440 local version suffix identifies the practical patch; offline release promotion retains its own stricter release policy.
