# Crystal AgentOS Community Edition — project dossier

Status: public `v0.5.0-beta.3` is published from `f6968c249f8bff1ce571cf92bbd960ba7cc2c1b2` with a verified wheel; live Mac installation and website deployment remain blocked by existing host gates.

F08 prepares a new public beta for optional external profiles. The published beta.3 remains the active release until the new source, wheel, tag and release are verified. The Mac owner profile is a separate draft and is not part of this public repository.

## Purpose and users

AgentOS gives a person and an agent a repeatable way to enter a project task, understand the current system, document the next bounded stage, execute it, prove the result and leave current knowledge for the next developer. The public edition must work without the maintainer's hosts, accounts, business rules or secrets. This repository is the first project expected to follow that cycle itself.

## Public baseline and verified worktree state

- At the public `0.4.0` baseline, the Python package requires Python 3.11+ and exposes a CLI and stdio MCP server. The code includes task normalization, result evidence, Full Inventory, local configuration and optional Telegram Session Hub.
- At that baseline, `agentos init` writes config, state and secrets under one user home, default `~/.agent-os`. Its config loader upgrades v1–v4 in memory; it does not provide a versioned user-data catalog, explicit persisted migration or core rollback. `mcp_server.py` returns `serverInfo.version=0.1.0` despite package `0.4.0`.
- The PyPI project URL for `crystal-agent-os` returned HTTP 404 on 2026-09-25. The actual public website route `https://crystalstrategy.ru/agent-os/` returned the maintained 0.4.0 HTML with a broken `pip install crystal-agent-os` recommendation. The different `/agent-os/community/` route redirects to authentication and is not the public site target.
- A separately supplied `0.5.0-beta.1` handoff ZIP contains a proposed public core, tests, docs, distribution and a private overlay. Its archive SHA-256 is `0bf055e6ebd6161795432210c261201415d97babb2da9ab819e94f3de0794637`. The internal manifest matches 537 listed files; this checks integrity of the received bytes, not authorship or correctness. No part of the mixed handoff is approved for wholesale publication.
- F01 independently reproduced 146 local tests and an offline Mac wheel install/update/rollback fixture. The candidate includes 13 runtime receipt files to exclude and omits a newer browser-surface document from public main. These findings govern integration.
- F02/F03 integration passed 146 tests and an offline Mac wheel install/update/rollback with a synthetic overlay and preserved user-tree hashes. F04 passed 153 tests and prepared the beta.1 source. F05 published beta.1. External review found three defects: missing user schema preflight, partial overlay import on I/O failure and a blocked next turn in standalone CLI mode. F06 published beta.2 with the first two fixes and a stricter `ready` baseline. F07 published beta.3 with an exact CLI-only `next-turn` transition. Current evidence: 164 tests, public-tree validator, Darwin arm64 install/update/rollback fixture, Linux arm64 wheel smoke and a fresh Mac source install from the published tag passed. MCP, CLI and project event/task contracts are packaged; human, CLI and MCP versions agree at `0.5.0-beta.3` while distribution metadata is `0.5.0b3`. Actual native hook activation and Windows execution remain unverified.

## Target state

The foundation is an independently updatable public package containing universal code, rules, contracts, templates and developer documentation. One obvious, versioned user overlay outside the package holds configuration, knowledge, project references, local state and user extensions. A core update preserves that overlay byte for byte unless an explicit, backed-up data migration is separately requested. New product tasks follow the documentation-first stage cycle. A short intake selects relevant document layers; closing checks current evidence and documentation against the implemented state.

F08 adds optional profile files under that external user home and an explicit selection of none, one or all. The adapter reports conflicts and stale selections without rewriting the public core. Owner and host facts enter an interview only through verified observations or selected profile entries; unknown facts remain questions.

## Scope and boundaries

This work may change only the canonical public repository, its public release artifacts and the intended public installation guidance after source and publication checks. The mixed handoff's `user-overlay`, `handoff`, `verification` and `provenance` trees remain private review material. Existing private runtime, host fleet, credentials, browser profiles and business projects are outside this public release. GitHub Actions are prohibited. A side-by-side Mac installation is a separate target proof; it cannot silently replace the installed private runtime.

## Current risks and unknowns

- The public source, release asset and tag have been read back. The external beta.1 review reproduced two defects and identified a third in the standalone CLI path; all three have local regression coverage in beta.3. A new independent beta.3 review and actual native hook trust proof remain valuable.
- Windows bootstrap and native Codex hook enforcement need actual supported runtime/client proof; unit fixtures alone do not establish either.
- The public website source is pushed to its separate Git remote, but the live `/agent-os/` route still serves 0.4.0. The existing website deployment gate has no applicable scope; source push alone is not deployment.
- Publishing to PyPI requires a real package account and upload receipt; until then GitHub source/wheel installation is the documented path.

## Sources and evidence

Public source: [repository](https://github.com/crystalstrategysup-prog/agent-os), `pyproject.toml`, `src/agent_os/config.py`, `src/agent_os/mcp_server.py`, `src/agent_os/tasks.py`, `src/agent_os/result_gate.py`, and tests at the commit above. External checks: [PyPI project URL](https://pypi.org/project/crystal-agent-os/) (404), [public releases](https://github.com/crystalstrategysup-prog/agent-os/releases). Owner requirements are recorded in the current task. Candidate archive and its manifest are private input, not public source authority.
