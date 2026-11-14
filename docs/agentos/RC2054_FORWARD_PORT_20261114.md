# Forward-port rc2054 — 14 November 2026

Base: rc2053 source commit 153698c4792875565a422cc78ae28e229b08ab3b.
Scope: carry normalized OpenAPI v3.0/v3.1 JSON declaration semantics, safer streamed inventory hashing, duplicate installer metadata validation, Atlas work-packet API contract binding docs, current source/package mirrors, and corrected deterministic substitution test. Preserve the newer rc2053 source worker, cold continuation and release capabilities; do not replace the original module map with the older candidate.

Identity: crystal-agent-os 0.8.0rc2054, distinct from installed rc2053. Not a production lease or runtime authorization.

Compatibility boundaries:
- Newer rc2053 packaging removed tools/verify_rebuild_contracts.py. Do not restore this obsolete file.
- Atlas selected source pins are refreshed without rewriting historical source provenance.
- Any source test that modifies or imports Atlas files can create ignored Python bytecode caches; clean generated caches before source parity checks, or verify a fresh export.
- This record is source-stage evidence; completed full suite, wheel build, release installation and session adoption require separate receipts.
