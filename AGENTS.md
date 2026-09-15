# Project contract

- This repository is the public, host-neutral Crystal AgentOS Community Edition.
- Never commit credentials, Telegram identifiers, private hostnames, Codex auth files, session contents, or production routes.
- Session discovery may read only bounded Codex metadata required to identify a session; ordinary output must never expose transcript contents.
- Telegram control is owner-allowlisted and disabled until explicitly configured.
- Commands are built as argument arrays from validated identifiers and configured paths. Do not expose an arbitrary shell surface.
- A queued Screen keystroke is not proof that Codex accepted a message; require a durable user event followed by a non-user event.
- Keep Windows behavior explicit: Codex session folders are supported, GNU Screen is not.
- Run local tests and review the diff before direct Git delivery. GitHub Actions are not used.
