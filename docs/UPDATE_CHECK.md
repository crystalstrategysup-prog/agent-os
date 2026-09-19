# Public update advisory

AgentOS Community Edition checks the fixed official GitHub tags endpoint on
AgentOS activity. A successful result is reused for 172800 seconds (48 hours).
An unavailable check retries after 21600 seconds (six hours).

```bash
agentos update-check
agentos update-check --force
```

The state is stored as `~/.agent-os/state/update-advisory.json` with private
permissions where supported. Normal commands remain quiet while current and
write a short stderr notice when a newer tag exists.

The check is deliberately advisory-only:

- it never downloads or installs a release;
- it never changes services, configuration or project files;
- public GitHub metadata does not authorize mutation;
- network failures are sanitized and do not expose provider diagnostics;
- idle installations do not wake themselves; the next AgentOS command performs
  an overdue check.

Disable it by setting `update_advisory.enabled` to `false` in `config.json`.
`automatic_install` must remain `false`.
