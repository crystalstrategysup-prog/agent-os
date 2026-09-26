# Interfaces and compatibility

Machine-readable contracts are `schemas/mcp-tools-v1.json` (with an identical
wheel copy), `schemas/cli-contract-v1.json`, the project task and event schemas,
and the packaged schemas under `src/agent_os/resources/schemas/`. Tests compare
MCP `inputSchema` and `outputSchema` with `tools/list` and returned
`structuredContent`, and task/event schemas with actual local lifecycle records.

CLI, Python, and MCP report version `0.5.1`; the stdio MCP protocol version is
`2025-06-18`. There is no HTTP API or OpenAPI specification. Project events are
local JSONL with JSON Schema, not AsyncAPI.

## CLI

Commands emit JSON except help and interactive questions. A foundation gate
error is `{"status":"BLOCKED","error":"..."}` with exit code 2. A successful
plan or execution exits 0. `project check` returns FAIL and exit 2 after a
nonzero process result, timeout, output limit, lingering child, or changed
source snapshot. The POSIX process group is complete before a PASS receipt.

`project enter` uses a recovery journal. After interruption, the next attempt
restores the prior state and returns `entry_recovered_retry`. A concurrent edit
returns `entry_recovery_conflict` without overwriting. Do not remove the journal
to bypass recovery. Older community commands may have different error shapes;
do not infer a new contract from them. Put global `--home`/`--user-home` before
the command group.

| Group | Operations | Boundary |
| --- | --- | --- |
| `project` | init, questions, enter, next-turn, document, ready, check, assess, verify-closeout, status, close, checkpoint, gate, snapshot | Explicit actions in the named project; questions and reads need no product write |
| `project observe` | root, answers, session, turn | Optional user-home receipt; does not create a project task |
| `overlay` | status, index, import, migrate-config | Import and migration plan by default; apply explicitly |
| `profiles` | inventory, select, context, interview | Exact profiles and selection in the named user home |
| `integrate codex` | target home, skills home, apply | Managed AGENTS and skills with backup; hooks/config/trust untouched |
| `resources` | list | Paths to packaged schemas, templates, skills, and docs |
| `setup` | list, show | Read-only discovery of published scenario cards |
| `hook` | retired compatibility entrypoint | Empty JSON, exit 0, no input or state access |

`profiles inventory` reports IDs, versions, hashes, host bindings, and conflicts.
`profiles select --mode none|one|all` stores explicit selection. One or all needs
the current inventory digest; all needs every exact ID in owner-chosen order.
Conflicting values need JSON decisions naming the winning profile for each key.
`profiles context` yields selected fields or `STALE_SELECTION` after drift;
`profiles interview` presents verified facts and unanswered questions. Profiles
grant no additional authority.

The client provides session and turn identifiers. In a CLI-only workflow they
are explicitly chosen; that does not prove a native hook event. After close or
checkpoint, `project next-turn` records an exact transition. Legacy dispatch
requires matching task objective and destination session; its one-time receipt
is consumed even when downstream launch fails.

## MCP stdio

JSON-RPC supports initialize, tools/list, tools/call, and ping. `tools/list`
provides versioned input/output schemas for six bounded tools: Telegram setup
plan, task normalization, doctor, project entry plan, document selection, and
foundation status. The planning tools accept project types, features, and
metadata without loading private knowledge bodies. Unknown tools and arguments
return tool errors. MCP does not register AGENTS or hooks in a client.

## Retired callbacks and explicit workflow

`agentos hook` and `agentos-hook` are retired no-op entrypoints: they output
`{}`, exit 0, do not read stdin, home, or config, do not write state, and do
not issue allow, deny, or COMPLETE. Historical hook schemas remain for
compatibility evidence, not as an active protocol. Integration registers no
AgentOS hooks.

Optional `workflow route --kind question|search|audit|discovery|project-change`
classifies declared effects. Local project writes route to documentation;
external send, production/runtime/database writes, credentials, destructive
operations, and deploy report target authority required. It never grants
external authority. JSON `--context`, `--answers`, and `--review` accept a
bounded object via `-` stdin or a regular non-symlink file and reject duplicate
keys. Same-scope resume reuses known answers without old authority and resets
readiness and checks. `project verify-closeout` reads current evidence for a
CLOSED result; it does not equate local closeout with deployment. Observations
are optional and do not bind tasks.

The MCP entry plan states that entry is required for project changes and that
read-only intake is unnecessary; native hooks are disabled. The exact JSON
shape and version are in the schemas and packaged copies.

## Optional extensions

`extensions/registry.json` describes `agentos.extension-registry/v1` entries:
provider kind, enabled flag, source, core API, data schema, authority, and
verification status. The registry is descriptive; it never auto-executes code.
A provider adapter needs bounded discovery and health, read-only capabilities,
then separately authorized task-bound execution. Building it is a separate
stage with threat review, contract, and tests. Knowledge cannot substitute for
an executable private provider. An absent portable provider is a recorded gap,
not a completed migration.

## Connection scenarios

The packaged `resources/setup-scenarios/index.json` lists published
`agentos.setup-scenario/v1` cards. `agentos setup list` returns the index;
`agentos setup show <id>` returns one card. These commands read neither the
overlay nor the network and run no provider. `guide_only` states that no general
runnable adapter is available, even if a private installation works. See
`docs/SETUP_SCENARIOS.md`.

## Public language contract

English is the language of human-facing public package text. Translation must
not alter JSON keys, schema names, command names, status and error codes, paths,
versions, or evidence semantics. Source docs under `docs/` must match their
packaged copies under `src/agent_os/resources/docs/`. See
`docs/LOCALIZATION.md`.

## Work-continuity guide

`docs/WORK_CONTINUITY.md` and the packaged template
`resources/templates/work-continuity-passport.md` are descriptive resources.
They do not add a CLI command, a new setup-scenario schema, an automatic backup
or an authority grant. A filled instance belongs outside public core. The
template requires dated evidence, canonical pointers, known data exceptions,
an independent-copy or restore check, and a next action. “Unknown” is a valid
state; the presence of a path is never treated as proof that data is preserved.
