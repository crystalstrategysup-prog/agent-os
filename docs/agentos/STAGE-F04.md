# F04 — contracts, version and developer onboarding

Status: IMPLEMENTED AND LOCALLY VERIFIED. F02/F03 local result is recorded in its stage file. F04 changes only the public repository and the independently located maintained public website source. Public release remains F05.

## Objective and boundaries

Make the actual CLI, config, data and MCP interfaces discoverable by another developer or agent through versioned machine-readable contracts. Align the release name, Python distribution, CLI, MCP `serverInfo`, release notes and working installation command. Repair the public-tree privacy validator's `.agentos` blind spot and preserve the current public browser-surface contract. Do not publish to PyPI without a real upload/read-back; do not invent website access or change an unrelated site checkout.

## Version decision

The human release identity is `0.5.0-beta.1`, with Python PEP 440 distribution version `0.5.0b1`. These are the documented equivalent representations of the same beta. CLI `--version`, package `__version__` and MCP `serverInfo.version` must agree exactly with the human identity; wheel metadata must normalize to `0.5.0b1`. Tag/release notes must name the same beta, and tests must assert the mapping. If another public tag already occupies the identity, choose the next beta ordinal and update all surfaces together.

## Applicable contracts

| Surface | Artifact and check |
| --- | --- |
| MCP stdio | Versioned JSON document with all tool input and output schemas; `tools/list` exposes matching `inputSchema` and `outputSchema`; successful structured results validate; initialize returns current package identity. |
| CLI | Versioned machine-readable command/output catalog covering new `project`, `overlay`, `integrate`, `resources`, `hook`, install and rollback operations, side effects and exit statuses. Keep the human guide in sync. |
| Config/user data | Packaged JSON Schemas for config v5, overlay catalog/manifest, task answers, project/task, evidence/check receipt and closeout; tests exercise valid and invalid representatives. |
| Events | Versioned schema for the project `events.jsonl` record because F03 introduced persisted events; no AsyncAPI is needed for a local JSONL file. |
| HTTP | N/A: this release introduces no HTTP server, so OpenAPI/Swagger would be fictitious. |

## Documentation and install path

README and developer onboarding must link the canonical public repository, dossier, roadmap, stage cycle, contract index, clean install, migration, fixture checks and actual limitations. Preserve meaningful 0.4.0 changelog history and current browser-surface documentation. The public site must stop recommending `pip install crystal-agent-os` while PyPI returns 404. If maintained site source cannot be found or accessed, document the precise blocker and provide the verified GitHub source/wheel installation path in the repository and release.

## Acceptance criteria

1. Contract files are valid JSON Schema or a defined machine-readable registry, included in the wheel, versioned and covered by tests against real CLI/MCP outputs. Existing `tools/list` calls remain backward compatible except for additive `outputSchema` metadata.
2. `agentos --version`, MCP initialize `serverInfo.version`, `agent_os.__version__`, package metadata, tag/release notes and wheel filename map to one beta. PyPI status is checked immediately before any install text or release claim.
3. Fresh wheel installation, `init`, `doctor`, MCP initialize and resource listing pass in a new isolated user home. A legacy v4 config migrates with backup; synthetic overlay and bytes survive update/rollback.
4. Public-source validation fails if `.agentos` runtime receipts, forbidden private files or host-specific paths are staged. Final tracked-file review also scans for secrets and private data.
5. README, developer onboarding, compatibility and release docs describe only verified platforms and actual support. Actual Windows and Linux runtime probes, if available, are recorded separately; a mocked test is not a platform PASS.

## Verification and closeout

Run full tests, JSON Schema validation, wheel build/install, MCP/CLI smoke, privacy scan, diff review and available platform probes. Record exact outputs, wheel/source SHA, website source status and unresolved limits here. Update dossier and roadmap before F05.

## F04 result — 2026-09-25

- Added a package-identical MCP registry with six input/output contracts, a CLI catalog, and project task/event JSON Schemas. `tests/test_contracts.py` validates live MCP results and real project records, including rejected invalid states. The HTTP surface remains absent.
- `tools/verify_public.py` now rejects a root `.agentos` receipt directory. Preserved the original public `docs/BROWSER_SURFACES.md` and reconciled packaged documentation copies.
- The canonical README, onboarding, install, release and compatibility docs describe source installation and the `0.5.0-beta.1` / `0.5.0b1` identity. The maintained site source was found at its own Git remote and its broken PyPI command was changed to a tagged source install; publishing and live website read-back belong to F05.
- Local Python 3.14.6 Darwin arm64: 153 tests passed, Ruff PASS, public-tree validator PASS, isolated source install/init/doctor PASS, wheel build PASS, and disposable offline install/update/rollback/overlay fixture PASS. The final F05 wheel SHA-256 and public source commit are recorded at release.
- Linux arm64 `python:3.12-bookworm`: fresh wheel install, `agentos --version`, `init`, `doctor`, resource listing and MCP initialize PASS. No actual Windows execution, Linux installer rollback, native Codex hook activation, private runtime parity or live website deployment is claimed.

Source remains the isolated public worktree based on `552ac9a3c812959e9d62883fd0a9052d6e44400f`; no candidate ZIP or private overlay is in the publish set. F05 must review the final diff and exact staged inventory, then publish and read back only what can be verified.
