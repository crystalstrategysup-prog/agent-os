# F01 — independent reconciliation of the supplied foundation candidate

Status: CLOSED for candidate classification on 2026-09-25. Source baseline: public `552ac9a3c812959e9d62883fd0a9052d6e44400f`.

## Goal and permitted work

Verify the supplied beta archive, compare only its `public-core/` with the canonical public repository, inspect the code and tests, identify public/private boundary violations, and produce the exact implementation plan for F02–F04. Documentation edits in the public worktree are allowed now. Product code integration starts only after this stage's review and the next stage's precise contract.

## Inputs and trust

The owner-supplied ChatGPT handoff ZIP is untrusted candidate material. Its observed SHA-256 is recorded in the dossier. `PACKET_MANIFEST.json` proves internal consistency of listed files, not that generated claims, checks or signatures are true. Public `origin/main`, current project AGENTS, owner task and installed host policy define the boundary. No private tree or mixed archive is committed.

## Interfaces and data touched

Read-only archive inspection, Git diff, package metadata, unit-test invocation in an isolated environment and public documentation. No runtime service, fleet, browser account, private config or personal knowledge mutation. F02 will own overlay import/migration/installer contracts; F03 will own project entry/close gates; F04 will own MCP/CLI/config/schema and install docs.

## Acceptance criteria

1. Exact public baseline and candidate file list/diff are recorded; every proposed public file has a provenance and scope decision.
2. Archive path traversal/symlink/size and listed digest checks pass; candidate code is not executed before inspection.
3. Foundation↔Overlay contract states disjoint roots, versioned catalog, import/migration conflicts, update/rollback and portable limits.
4. Test claims are independently reproduced or marked unverified. The documented next stage has explicit write set, failure paths, checks and rollback.
5. No private overlay, provenance, handoff, verification log, host identifier, credential or production route is staged for public commit.

## Checks and closeout

Use Git diff against the fresh remote, an independent archive verifier, a targeted public-boundary scan and local package tests. Record executed commands, source SHA, results and findings here. Mark F01 closed only after that review; then update dossier and roadmap before F02.

## Result and evidence

- The ZIP was extracted only into private scratch after checking traversal and symlink entries. Its 537 manifest-listed files matched their digests; the manifest is intentionally not self-listed. This is integrity of received bytes, not origin authentication.
- The candidate `public-core` has 156 archive files: 143 source/doc/test/resource review candidates and 13 `.agentos/tasks` runtime receipts. The latter are excluded. The other four mixed-archive top-level trees are private and excluded. The exact per-file classification is retained outside the repository with this stage's review evidence.
- The candidate omits `docs/BROWSER_SURFACES.md` from current `origin/main`; this document must be preserved. Its current `AGENTS.md` policy must be reconciled rather than replaced blindly.
- Independent isolated Mac test run: `146 passed in 3.04s` with Python 3.14.6, pytest and jsonschema. The candidate's public-tree validator returned PASS. Its heuristic ignores `.agentos`, so it must be strengthened before publication.
- Independent offline wheel install/update/rollback fixture on Darwin arm64 returned PASS; its prior release was synthetic. The user-tree sentinel hashes survived. That run did not use the supplied overlay and did not activate native hooks or verify any private runtime.
- Public text scan found no absolute home paths or named private hosts in review candidates. A token-environment example and the validator's own forbidden-pattern literal matched the heuristic; inspect final staged bytes before push. The scan does not prove absence of every secret.

F01 closes with the following required F02–F04 corrections: exclude `.agentos`; preserve the newer browser contract; align package/CLI/MCP/release version representation; add machine-readable MCP output schemas and affected CLI/config/data contracts; test a supplied/synthetic overlay import; verify actual native hook capability before claiming enforcement; identify website source before changing it. No product code was changed in F01.
