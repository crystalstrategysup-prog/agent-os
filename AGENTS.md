# Project contract

- For every new or resumed product task, read `docs/agentos/DOSSIER.md`, `docs/agentos/ROADMAP.md` and the current stage document before product writes. Run `agentos project questions` and `project enter` for the actual session and turn, reusing verified existing facts. `docs/PROCESS.md` defines readiness, checks, closeout and checkpoint. A read-only observation uses its short path and does not require creating project metadata.
- The stage cycle is dossier → roadmap → stage contract → implementation → result evidence → documentation update. Relevant document layers are selected by project type and changed surfaces; all catalog layers are never mandatory by default. Draft, stale or unregistered required documents cannot establish READY. Do not edit `.agentos` task records to bypass the gate.
- Keep the public foundation and versioned user overlay physically separate as defined in `docs/FOUNDATION_OVERLAY.md`. Installed hooks require actual client trust and live probes before claiming enforcement. An AgentOS CLI or MCP plan does not itself grant external mutation authority.
- This repository is the canonical public, host-neutral Crystal AgentOS Community Edition: `https://github.com/crystalstrategysup-prog/agent-os`.
- The public project is owned and published through the Crystal Strategy GitHub account. Never substitute a similarly named personal or internal fleet repository when publishing, linking, reporting visibility, or preparing a community release.
- Never commit credentials, Telegram identifiers, private hostnames, Codex auth files, session contents, or production routes.
- Session discovery may read only bounded Codex metadata required to identify a session; ordinary output must never expose transcript contents.
- Telegram control is owner-allowlisted and disabled until explicitly configured.
- Commands are built as argument arrays from validated identifiers and configured paths. Do not expose an arbitrary shell surface.
- Public update metadata is advisory only: it may report an official tag but must never authorize download, installation or mutation.
- Full Inventory reads only explicitly registered canonical project roots, emits hashes and metadata instead of contents, and never auto-loads history.
- Browser routing follows `docs/BROWSER_SURFACES.md`: explicit user/workstream binding wins; otherwise select the in-app Browser or Chrome with the supported Playwright Extension by required capability.
- A queued Screen keystroke is not proof that Codex accepted a message; require a durable user event followed by a non-user event.
- Keep Windows behavior explicit: Codex session folders are supported, GNU Screen is not.
- Run local tests and review the diff before direct Git delivery. GitHub Actions are not used.
