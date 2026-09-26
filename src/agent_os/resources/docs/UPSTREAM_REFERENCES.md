# Upstream interfaces and their limits

Reviewed on 2026-09-25. Documentation does not prove the state of a particular
Mac or client session.

- [OpenAI AGENTS.md documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
  describes instruction precedence, including global `AGENTS.override.md` and
  project instructions along the directory chain. Read back effective
  instructions in a fresh session after a change.
- [OpenAI hooks documentation](https://learn.chatgpt.com/docs/hooks) describes
  Stop behavior. It explains an older failure mode; it does not authorize
  AgentOS hooks in this version.

The current AgentOS contract excludes native hooks and restoration from hook
backups. AGENTS and skills are not a technical sandbox. Client controls and
target executors retain their own security boundaries. Changing client
capabilities requires explicit, current verification.
