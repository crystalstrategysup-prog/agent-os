# Install, update, rollback, and recovery

## Version and proof

The source declares `0.5.5`. Verify the published tag or release asset
separately; a version string does not prove publication. Review the exact
source, patch, and manifest, run local checks, and read back the target runtime.
Python 3.11+ and disjoint core and user roots are required. The commands below
describe the procedure; only a current pointer and live readback prove it ran.

## Preflight and install

Verify the archive and wheel SHA-256, source provenance, Python version, free
space, and write access to two non-overlapping directories. The managed
installer is POSIX-only. Do not use sudo, replace another runtime, or use the
existing AgentOS installation as the new core home.

```sh
python3 tools/install.py install \
  --wheel /absolute/crystal_agent_os-0.5.5-py3-none-any.whl \
  --sha256 ACTUAL_WHEEL_SHA256 --version 0.5.5 \
  --core-home "$HOME/.local/share/agentos-foundation" \
  --user-home "$HOME/.agentos-user"
```

This first invocation is a plan. It reports the expected current release
(`none` on first install) and a release ID. After reviewing it, repeat the same
command with `--apply --expected-current none` or the exact observed release ID.
The installer copies and rechecks the wheel, builds the venv at its final path,
and runs pip offline with `--isolated --no-index --no-deps`. Before importing the
installed module, it compares installed `agent_os` bytes, wheel metadata, and
entrypoint scripts to the verified wheel. It then probes the installed version,
resources, and MCP tools. New releases use `agentos.install/v2` with SHA-256 for
all entrypoints. A legacy manifest v1 rollback accepts only its verified
canonical launcher. Unverified `__pycache__/*.pyc` derivatives inside installed
`agent_os` are cleared before the probe; a plan does not alter the cache.

Only after the probe passes does `current` switch. The installer leaves the user
folder unchanged, but reads `overlay.json` and `config.json` for schema
compatibility before planning and before switching. Unknown schemas, corrupt
JSON, and symlinks block install or rollback without moving `current`. Overlay
import is a separate command. Installation makes no global PATH, service,
authentication, model, or trust change.

## User overlay and profiles

Profiles are optional. Store each `profile.json` at `USER/profiles/ID/` under
`agentos.profile/v1`, then run `agentos --home USER profiles inventory` and
review conflicts. Select one with `profiles select --mode one --id ID
--inventory-digest DIGEST`. Select all only with exact ordered IDs and decisions
for conflicting keys; use JSON such as `{"field_key": "winning_profile_id"}`.
`--mode none` selects no profile. After a profile edit or deletion, inventory,
select again, and read back `profiles context`. `profiles interview` presents
verified current facts and unanswered questions; it does not write answers.

Before `init`, plan `agentos --home USER overlay import --source OVERLAY`, then
apply explicitly. A `CONFLICT` never overwrites: preserve the valid file,
compare keys, and prepare a reconciled overlay with a new manifest. Do not
regenerate a manifest just to conceal unexplained damage. `init` creates only
missing service directories and does not replace config. Do not copy auth files,
SSH keys, cookies, or Telegram sessions from an archive into public source.

For community config v1–v4, plan `overlay migrate-config`, then apply with a
backup and readback. Unknown keys are preserved. Partial private config is not
automatically treated as community config; it needs its own reviewed mapping.
Create-only import writes and fsyncs a temporary file in the same directory
before publication; a failed write leaves no target file. Existing files are
never replaced.

## Integrating with Codex

Plan `integrate codex`, then apply. Target Codex home comes from explicit
`--codex-home`, then `CODEX_HOME`, then `~/.codex`. An override file is chosen
only when it contains instructions; an empty file does not hide the owner's
AGENTS file. Integration edits only its managed block while preserving other
bytes, including CRLF. Conflicting markers block the write. Namespaced skills
are installed without overwriting another owner's modifications. A local log
supports rollback and interrupted-operation recovery; concurrent changes are
not overwritten. Backups live under `USER/backups/integration`. Client config,
auth, model, and trust stores are untouched.

Native hooks are excluded. Integration does not create, enable, change, or
restore AgentOS hooks, including in `hooks.json` or `config.toml`. It also does
not prove that an old callback elsewhere has been disabled. Read back the
actual client configuration separately; if an AgentOS hook is active, stop and
resolve that exact conflict without trusting it again. Preserve unrelated
client security controls.

In a fresh client session, check effective AGENTS and skills. Test direct
read-only answering without a project task, then project docs/READY/check/close
for an actual change. Existing owner and project overrides remain; conflicting
old intake rules require a separate owner-overlay change. After checkpoint or
close in an explicit CLI workflow, use `project next-turn` with exact session,
turns, and task, then enter. A pre-entry failure has no task to close.

## Update

Old releases remain immutable. Install a new verified wheel offline with the
observed expected current release. The installer does not migrate user data
implicitly. After switching, update only managed AGENTS and skills through the
new interpreter and test them in a fresh session. Do not enable hooks or install
simply because advisory metadata reports a tag. Record docs, compatibility, and
health evidence against the exact source SHA.

## Rollback

`core/previous.json` records the preceding release ID; `none` means there was
no previous managed release. Plan first, then apply against the observed current:

```sh
python3 tools/install.py rollback --release-id PREVIOUS_ID \
  --core-home CORE --user-home USER
# Repeat with --apply --expected-current CURRENT_ID after reviewing the plan.
```

Rollback verifies the manifest, wheel, installed payload, probe, and overlay
schema compatibility before switching `current`. It does not change user data.
Do not run beta.4-or-earlier integration generators or restore hook backups;
preserve no-hook AGENTS and skills or perform a separately reviewed manual
rollback. If user data is incompatible with an older core, stop rather than
guessing a downgrade. Restore a separate backup to a new user folder for
inspection. A first managed install cannot roll back another runtime.

## Recovery

An incomplete release is never activated. Preserve logs, diagnose the cause,
and do not delete a marker to bypass verification. Remove an inactive incomplete
release only after exact current-state review and a separate decision, then
repeat installation. Do not remove `.install.lock` or `.agentos/write.lock` by
age alone: verify the owning process has ended and inspect the log and integrity.
A foreign or unmanaged `current` blocks automatic changes. Restore config from
backup only after comparing it with the current file and reading back the result.
Neither installer nor migration automatically deletes history.
