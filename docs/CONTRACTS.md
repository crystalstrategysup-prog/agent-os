# Interfaces and compatibility

Current source candidate: `0.8.0rc2` (not publication or host adoption). RC-labelled sections below are retained historical records, not current installation or publication claims.


## Historical: Indexed handoff successor0.7.0rc1

Library Python/CLI APIs and v1 manifest/root schemas are defined in INDEXED_HANDOFF.md. The six MCP tools remain unchanged; no library MCP bridge is claimed. See [indexed handoff](INDEXED_HANDOFF.md).

Machine-readable contracts are `schemas/mcp-tools-v1.json` (with an identical
wheel copy), `schemas/cli-contract-v1.json`, the project task and event schemas,
and the packaged schemas under `src/agent_os/resources/schemas/`. Tests compare
MCP `inputSchema` and `outputSchema` with `tools/list` and returned
`structuredContent`, and task/event schemas with actual local lifecycle records.

CLI, Python, and MCP report candidate version `0.8.0rc2`; the RC1 background in this
document is historical. The stdio MCP protocol version is `2025-06-18`. There is no HTTP API or OpenAPI specification. Project events are
local JSONL with JSON Schema, not AsyncAPI.

F15B adds `agentos setup probe ssh-vnc --host ALIAS [--vnc-port PORT]
[--ssh-only] [--apply]`. Without `--apply` it returns a network-free plan. With it, the
command returns `SSH_VERIFIED` or `TRANSPORT_VERIFIED` only for the requested
SSH and optional RFB transport layers, `FAIL` for a bounded probe failure, and
`BLOCKED` for invalid input or an unsupported environment. Output always leaves
`vnc_authenticated` and `desktop_frame_verified` false. The current diagnostic
implements no viewer path. This probe is an external read of the exact selected host, not
part of the stateless `setup list/show` commands. Its argv and result shape
are reviewed under STAGE-F15B before publication; the JSON result is defined by
`schemas/ssh-vnc-probe-v1.schema.json` and its packaged copy.

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


### Local candidate project inventory budget

`project inventory-budget --root P` is a readback; `--max-bytes N`, `--max-files F` or `--reset`
is an explicit project metadata write. The exact three-field optional record is
`{schema:"agentos.project-inventory-budget/v1", max_bytes:N, max_files:F}`.
Only integers 1..17179869184 are valid byte budgets; file budgets are integers 1..40000. Defaults remain 134217728 bytes and 20000 files.
Malformed/unknown records fail closed (`invalid_project_inventory_budget`).
Changing the record changes the policy digest and rejects old READY/check
receipts (`scope_changed_reenter_required`). No file hashes or retained evidence
are suppressed, and no runtime/production authority is implied.

Every effective setting change also increments project `inventory_budget_revision`
(integer 1..2147483647, fail closed on exhaustion). Reset retains this generation,
so returning to a previous byte budget cannot resurrect old READY/check receipts.
Policy/snapshot include the generation after first use; untouched projects retain
exact historical digests. A no-op neither increments nor invalidates.


### Optional lock-bound inventory setter predicates (rc2016)

Set/reset may supply BOTH `--expected-project-sha256 SHA256` and
`--expected-budget-revision N`. The digest is exactly 64 lowercase hexadecimal
characters over the current `.agentos/project.json` bytes; revision is an exact
integer 0..2147483647 (0 for an untouched legacy project, booleans rejected in the
typed API). Both current comparisons run inside the existing project write lock
before any project metadata write, including a no-op. One predicate, malformed
values, stale digest/revision or predicates on a read-only call fail closed.
The typed API names are `expected_project_sha256`, `expected_budget_revision`.
Omitting BOTH preserves legacy read/set/reset. Readback grants no authority.
Re-read and reconcile after mismatch; never automatically retry a changed target.

The finite maximum is 17179869184 bytes (16 GiB); default remains 134217728 bytes
and default max_files remains 20000; explicit max_files is bounded at 40000. This raises a reader ceiling without allocating disk.
All source files/content hashes and existing safety checks remain included. At
either ceiling STOP; no automatic expansion, guard skip or evidence exclusions.
Once a project stores a value above 4294967296, rc2015 cannot read that project.
Preserve a compatible forward reader; automatic downgrade or metadata reset is
forbidden. Isolated installer rollback does not prove project downgrade safety.


### Optional finite per-project file budget (rc2017)

`--max-files F` / typed `max_files=F` accepts exact integer1..40000, rejecting
booleans/floats/overflow and malformed records. Global defaults remain20000 files
and128MiB; max_bytes ceiling remains16GiB. The exact budget record keeps its
three fields and schema version. Omitted max_files preserves EFFECTIVE current
file budget on byte-only update; omitted max_bytes preserves EFFECTIVE current
byte budget on count-only update. Both can be set together. Reset conflicts with
either setter input and restores BOTH defaults through the existing monotonic
generation; an untouched read keeps legacy default/digest bytes. Optional paired
CAS predicates remain strictly typed and checked under the existing write lock
before any project write/no-op; current Root mutation must supply BOTH.

Source policy/readiness invalidation and historical evidence retention are
unchanged. This does not change safeio walk/hash/alias/content checks or SKIP;
every accepted file is fully hashed. Further byte/file guard refusal means STOP
and qualification of the first boundary, never automatic expansion/exclusions.
Whether40000 suffices for any real corpus is UNKNOWN until separately authorized
Root source proof. Once a project stores max_files other than20000, rc2016 cannot
read it: retain a compatible forward reader; no automatic downgrade/reset.


### READY task metadata bound (rc2017)

A finite file inventory does not guarantee that its full READY task fits the
default4MiB task JSON reader; explicit rc2018 project task policy may select up to32MiB. READY serializes the complete future task with the
existing UTF-8 JSON formatting and checks its exact byte length before the atomic
task write or READY event. Above the effective task ceiling (4194304 by default) it fails with
`ready_task_metadata_limit`, preserving the prior task and history. Exactly the selected task ceiling
is accepted; the generic JSON reader stays4MiB. No source-map truncation, compression,
external storage, recovery route or global metadata-limit expansion is introduced.

Actual full corpus and task overhead must be qualified separately; synthetic
40000-path success/failure is not a real-project compatibility claim. Other
metadata writers and future receipt growth remain unchanged and retain their
existing reader limits. A refusal remains an explicit compatibility boundary.


## Explicit per-project TASK metadata budget (rc2018)

`project task-metadata-budget --root P` reads optional task_metadata_budget.
`--max-bytes N` or `--reset` explicitly changes project policy; optional PAIRED
expected-project-sha256/expected-budget-revision are compared under existing lock
before no-op/write. This command uses task_metadata_budget_revision, not inventory
budget revision. Exact record: schema agentos.project-task-metadata-budget/v1,
max_bytes integer4194304..33554432 (booleans/floats/extra fields rejected).
Default4MiB for untouched projects. Changes increment policy generation/project
revision and invalidate READY normally; reset retains generation. Byte-identical
legacy digests when both policy fields were never present. Lowering/reset is
refused when oversized tasks or unclassified retained preimages prevent bounded
compatibility proof; never delete/reset history to force it.

Only task.json and its typed lifecycle before/after/raw backup/readback rows use
this ceiling. Global safeio/project/turn/events/requests/provider/privacy limits
stay fixed. Full source map remains inline, no storage migration/compression or
truncation. Inventory16GiB/40000 unchanged. Entry/current READY/check/close/checkpoint
task writes are bounded before their task write, with exact readback. Existing
external checks/handoff side effects retain their authority and unknown handling.

Continuation embedded journal remains24MiB including base64 pre/postimages and
retarget history: an allowed32MiB task can fail journal eligibility. Refusal small
journal/request/permit caps and non-task row limits stay fixed; staged TASK raw
rows alone follow project policy. Handoff objects still16MiB/scanners unchanged.
No universal32MiB lifecycle guarantee. Ineligible route STOP, no auto cap increase,
new recovery route or replay. Legacy reader cannot read task>4MiB; preserve a
compatible forward reader/policy while such tasks/preimages exist. No auto downgrade.
