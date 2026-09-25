# Changelog

## 0.5.0-beta.2 — beta hardening, 2026-09-25

- Publish imported overlay files atomically with create-only semantics, so an interrupted write cannot leave a partial user file.
- Refuse managed install and rollback when the existing user overlay or config schema is incompatible, malformed or symlinked; legacy community config v1–v4 remains readable without implicit migration.
- Require a fresh task entry before `ready` can take a new source baseline. Repeating `ready` on an already ready task no longer clears receipts or hides an out-of-scope change.
- Keep the beta.1 tag immutable. This release is `v0.5.0-beta.2` (`0.5.0b2` in Python packaging). The existing target activation and platform verification limits remain documented.

## 0.5.0-beta.1 — community beta, 2026-09-25

- Add documentation-first project entry, relevant document selection, stage readiness, current checks, semantic closeout and a read-only observation path.
- Separate the public foundation from a versioned user overlay. Add create-only import, backed-up config v1–v4 migration, offline core install/update and rollback without modifying user data.
- Package eight namespaced skills, templates, reference schemas, CLI/MCP contracts and developer guidance. The MCP server reports the current package identity instead of `0.1.0`.
- Preserve the public browser-surface contract and existing security boundaries while integrating the beta candidate. No private handoff, host data or runtime receipts are part of the release.
- Distribution version is `0.5.0b1`; the human release/tag identity is `0.5.0-beta.1`. Install from the verified public GitHub tag or wheel. The PyPI project URL returns 404, so PyPI installation is not advertised.

Compatibility: the default user home changes from `~/.agent-os` to `~/.agentos-user`; legacy `AGENT_OS_HOME` remains recognized. New native hooks require actual client support and trust. The legacy Session Hub dispatch now fails closed without an exact intake. The managed installer is POSIX-only. Windows, native hook activation on a user's client and private runtime parity require separate target proof.

## 0.4.0 — 2026-09-19

- Add Full Inventory: a bounded, content-free map of registered project policy, roadmap, skill, problem, host and historical knowledge surfaces.
- Add an AgentOS-native public update advisory. On AgentOS activity it checks the official GitHub tags when the previous successful check is at least 48 hours old; failures retry after six hours.
- Keep update metadata strictly advisory: no automatic download, installation or mutation is permitted.

## 0.3.0 — 2026-09-18

- Add deterministic model-routing plans with exact reasoning effort and root-only critical escalation.
- Add a current-evidence result gate so missing, stale, failed or historical observations cannot be reported as complete.
- Upgrade community configuration to v3 while preserving nested v1/v2 values.

## 0.2.0 — 2026-09-17

- Add the owner-only Telegram Session Hub for persisted Codex sessions and GNU Screen bindings.
