# Compatibility notice for 0.5.0-beta.3

The inherited Session Hub code is retained, but mutating dispatch now fails closed without
AGENTOS_SESSION_ID/AGENTOS_TURN_ID and exact objective/destination bound to a READY task.
The prior Telegram UX does not yet provide a complete questionnaire/documentation frontend.
Do not use the instructions below as evidence of an immediately operational owner bot, and do
not replace an existing private bot with this community launcher. See COMPATIBILITY.md and
PROCESS.md. Secret setup and actual target health remain separate requirements.

## Historical community interface reference

# Telegram Session Hub

The Session Hub lets an allowlisted owner use a Telegram bot to discover and
continue local Codex sessions, inspect GNU Screen sessions, create a new Codex
session, or create a Screen attached to a newly persisted Codex session.

## Safety model

- The bot is disabled by default.
- `owner_ids` is mandatory. Messages from every other Telegram account are rejected.
- The bot token and optional transcription API key are read from environment variables.
- Session lists contain metadata only: UUID, update time, workspace and source path.
- Arbitrary shell commands, arbitrary executables and arbitrary workspaces are not exposed.
- A Screen message is successful only after AgentOS observes the matching durable
  Codex user event and a later non-user event. A visible composer is not success.

## Configuration

Run `agentos init`, then edit `~/.agent-os/config.json`:

```json
{
  "telegram_session_hub": {
    "enabled": true,
    "owner_ids": [123456789],
    "bot_token_env": "TELEGRAM_BOT_TOKEN"
  },
  "codex": {
    "executable": "codex",
    "home": "",
    "session_roots": [],
    "default_workspace": "~/Projects",
    "allowed_workspaces": ["~/Projects"]
  }
}
```

Empty `session_roots` means the platform default:

- Linux/macOS: `$CODEX_HOME/sessions` or `~/.codex/sessions`;
- Windows: `%CODEX_HOME%\sessions` or `%USERPROFILE%\.codex\sessions`.

Start the bot:

```bash
export TELEGRAM_BOT_TOKEN='stored-outside-the-repository'
agentos telegram-bot
```

## Voice and files

Telegram voice messages can be transcribed in two ways:

1. Local Whisper: install `whisper` and FFmpeg. No external transcription API is required.
2. OpenAI transcription: install `pip install 'crystal-agent-os[speech]'`, store
   the key in the environment variable configured by `openai_api_key_env`, and
   select `provider: openai` or `provider: auto`.

The current OpenAI model default is configurable and is never hard-wired into
session state. Keys must not be pasted into Telegram, prompts, issues or Git.

Documents, photos, audio and video are downloaded into the private AgentOS inbox.
Text and media paths can be passed to Codex after a target is selected. Audio and
video require a configured transcription provider before their speech becomes a prompt.

## Commands

- `/start` — main menu and current capabilities;
- `/sessions` — recent Codex sessions;
- `/screens` — GNU Screen sessions and mapped Codex UUIDs;
- `/new` — create a persisted Codex session in an allowed workspace;
- `/newscreen` — create a persisted session and attach it to a new Screen;
- `/capabilities` — session, Screen, file and speech readiness.

This community adapter controls the local host only. A multi-host deployment must
add an authenticated host broker rather than expose SSH or arbitrary routes to Telegram.
