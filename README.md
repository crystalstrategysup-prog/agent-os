# Crystal AgentOS

**A free, local-first control plane for personal AI agents.**

Crystal AgentOS helps you turn an AI client into a governed working environment:
local configuration, bounded task briefs, MCP tools, health checks and a clear
Telegram Business onboarding path.

The community edition is intentionally small. It contains no vendor account,
private host, production credential or hidden cloud dependency.

## Why AgentOS?

An AI model can reason, but a dependable agent also needs boundaries:

- where configuration and secrets live;
- which actions are allowed;
- how a task is classified before execution;
- how tools are exposed to ChatGPT and other MCP clients;
- how a personal Telegram account becomes an authorized business interface;
- how a result can be checked and rolled back.

AgentOS provides that control layer without taking ownership of your data.

## Install

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install .
agentos init
agentos doctor
```

For development:

```bash
pip install -e '.[dev]'
pytest
ruff check .
```

## Telegram Business onboarding

AgentOS uses a Telegram-first sequence:

1. Create an account in the official Telegram application if you do not have one.
2. Request approval from your AgentOS owner or administrator.
3. Authorize a `StringSession` using Telegram QR.
4. Store the explicitly approved `API_ID`, `API_HASH`, `STRING_SESSION` bundle locally.
5. Connect Telegram Business and its business bot.
6. Add AgentOS to an MCP-compatible client.
7. Run a harmless end-to-end verification task.

No website is required by this flow. Credentials must never be pasted into an
AI conversation, issue, log or repository.

Print the machine-readable plan:

```bash
agentos telegram-plan
```

## MCP

Generate a client configuration template:

```bash
agentos mcp-config
```

The included stdio server exposes three safe starter tools:

- `agentos_get_telegram_setup_plan`
- `agentos_normalize_task`
- `agentos_doctor`

It does not expose arbitrary shell, SSH, file reads or stored credentials.

## Telegram Session Hub

Version 0.2 adds an owner-only local Telegram control surface for Codex:

- discover recent persisted sessions from the platform default or configured folders;
- inspect GNU Screen sessions on Linux and macOS and show their mapped Codex UUID;
- select an existing session and send its next task;
- create a new persisted Codex session or a new GNU Screen attached to one;
- receive documents and media into a private local inbox;
- transcribe voice with local Whisper or an optional OpenAI transcription provider.

GNU Screen is not available on Windows; ordinary Codex session discovery and
creation remain supported there. The bot is disabled until an explicit owner ID
allowlist and a token environment variable are configured.

```bash
agentos sessions
agentos screens
agentos session-capabilities
agentos telegram-bot
```

See [Telegram Session Hub](docs/TELEGRAM_SESSION_HUB.md) for configuration and
the exact security/proof model.

## Status

`0.2.0` is an alpha community release. It is suitable for evaluation and local
development. Production connectors must add their own authentication, durable
receipts, least-privilege runtime and rollback policy.

## Community

AgentOS is free software under Apache License 2.0. Use it, study it, adapt it,
teach with it and contribute improvements. See [CONTRIBUTING.md](CONTRIBUTING.md)
and [GOVERNANCE.md](GOVERNANCE.md).

The project is operated day to day by an AI steward under the human owner's
authority. The mandate includes development, monitoring and respectful community
support, with explicit legal, privacy and truthfulness duties. See the
[AI Stewardship Charter](STEWARDSHIP.md).

Languages: [Русский](docs/README.ru.md) · English
