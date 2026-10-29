# Guarded GNU Screen creation and continuation

## Scope and architecture

This source candidate restores a working Screen creation path. A persistent
Python worker runs inside a newly named GNU Screen window and owns one Codex App
Server stdio child. The initiating caller can return or exit while that worker
and connection remain available. The Screen window is a managed worker, with
continuation through `CodexRunner.continue_screen`; it is not a new Codex TUI.
Already existing Screen TUI sessions retain their discovery and keystroke path.

A provisional Screen transport is not a runnable business session. It can start
only the bounded provider initialization and current configuration/catalog reads.
The original work is dispatched after the provider-neutral admission sequence:
current `config/read`, complete bounded `model/list`, current target checks,
inherited `thread/start` readback, actual harmless tool probes, target recheck and
existing dispatch claim. All provider stages use the same Screen-owned connection
and actual task workspace. The configured model must be an admitted catalog
candidate before the worker creates a Codex thread.
An absent/null configured provider is provisional: the same connection's required
actual `thread/start.modelProvider` resolves it before any probe or work. Preserve
that actual value separately from configured null/presence; match an explicit
configured provider without changing settings or guessing a default name.
There is no immediate `codex exec` or TUI work fallback.

See [SESSION_LAUNCH](SESSION_LAUNCH.md) for the original goal/context/authority,
capabilities, transfer, target lease and independent approval contracts. This
adapter neither grants privileges nor changes Codex approval/sandbox settings.
The executor's label alone is not evidence of its effective mode.

## Supported public API

```python
result = CodexRunner(config).create_screen(
    name, original_goal, workspace,
    launch_request=request,
    target_guard=existing_target_readback,
)
```

The request is the existing `agentos.session-launch/v1` contract. Set
`executor.provider` to `codex-app-server-stdio`, and set `executor.transport` to
`gnu-screen` to identify the already owner-selected transport. The approved
Codex version, sandbox, approval policy and owner reference are required, exactly
as for the direct stdio route. No setting override is passed to Codex. The
original goal and validated workspace must match the call. A configured
`config.codex.launch_request` can supply the same explicit contract.

Choose the exact already owner-approved executable whose inherited model and
provider can pass [model admission](SESSION_LAUNCH.md#inherited-model-admission-and-actual-startup).
Resolving a binary through `PATH` is executable discovery; it does not establish
model availability. The worker never switches binaries, writes model settings,
changes providers or grants permissions to recover from incompatibility.

Missing request/transport information is `UNKNOWN` before provider dispatch.
Unavailable binaries or Windows return `UNAVAILABLE`. Supported inherited modes
still require an actual probe; an approval request produces `BLOCKED` without a
synthetic approval response. Unsupported tools/targets remain `UNKNOWN`.

The new Screen uses the following argument array, with validated name and exact
existing executable paths; a shell does not interpret it:

```text
screen -D -m -S NAME -c /dev/null EXACT_PYTHON -m agent_os.screen_launch worker EXACT_WORKER_DIRECTORY
```

`-D -m` starts a detached, nonforking Screen process. Its PID and the child's
actual `STY` socket identity must agree with a fresh `screen -ls` observation
before a provider thread can be created. The worker asserts its actual cwd and
unchanged selected `CODEX_HOME` before opening App Server. Those checks detect a
Screen startup file that changes relevant process context.

For this new process only, both current `SYSTEM_SCREENRC` and historical
`SYSSCREENRC` point to `/dev/null`; `-c /dev/null` selects an empty user terminal
startup file. Existing Screen/Codex files are not edited. Some GNU builds disable
the global Screen startup override at compile time. Verify the chosen target's
supported override and absence of unexpected startup windows before activation;
the source candidate does not claim universal suppression of global startup
commands. No `screen -X quit`, `-wipe`, existing-session detach or kill is used.

## Persistent evidence and uncertainty

The worker directory is under `state/screen-workers/NAME` in the existing AgentOS
user home. It is created exclusively. Reusing a name or old directory is
`UNKNOWN:screen_name_exists_reconciliation_required`; the adapter never replaces
an old worker. The provider-neutral launch journal is reserved before starting
even a provisional Screen, so reusing an uncertain launch ID cannot start a
second Screen with a different name.

The bounded typed mailbox permits only `describe`, `describe_existing`,
`describe_adoption`, `resume`, `create`, `probe` and `dispatch`. Each request/response binds worker ID, exact retained request digest,
operation ID and connection ID. The bootstrap also binds the chosen executable,
work timeout and expected Codex home. A worker lock and caller control lock
serialize ownership; a worker cannot directly repeat thread creation or dispatch
without another successful probe. These are same-user consistency checks, not a
security boundary against a process with the same operating-system identity.

Records contain original authorized task data locally in mode-0600 files, and
normalized provider receipts with item IDs/hashes. They do not copy raw
configuration layers, auth files or transcript logs. Discovery reads one bounded
metadata record only. Existing target gates and leases retain their own sources.

A caller timeout leaves `pending.json` and the exact operation identity. Further
mutating mailbox calls refuse until separate supported reconciliation; the code
never retries a timed-out operation, recreates the Screen, closes a still-owned
worker because its caller returned, or converts a mailbox ACK into execution
proof. The public `ScreenLaunchProvider.status()` read returns failed/pending
worker metadata and observed Screen availability without clearing the block.
Response files retain the operation outcome if it arrives after caller timeout.
For a qualified completed dispatch with reviewed actual effects, the explicit
[pending reconciliation API](SCREEN_RECONCILIATION.md) can publish a separate
immutable receipt for guarded cold same-SID adoption. It never clears pending,
resets FAILED/UNKNOWN, unblocks the old mailbox or replays an operation.
A distinct [reviewed pre-resume disposition](SCREEN_PRE_RESUME.md) supports only
the exact proved metadata-only transfer-readback failure. It preserves the
failed SID/launch/provisional records and requires actual no-native/claim proof
and current ownership; false/null markers alone never unblock an attempt.
An operator must assess actual thread/tool/target effects before clearing or
replacing state; this candidate exposes no automatic uncertainty-reset command.

The worker waits for a bounded turn completion (at most 1,800 seconds) and
persists afterward. Actual provider approval/input requests are refused without
a reply. Startup/probe failure never sends the business prompt as a task.
Provisional workers can remain available for inspection after a failed admission;
they are not runnable or automatically substituted with another executor.
An incomplete catalog, unresolved model/default/alias, malformed explicit provider
or exceeded catalog read bound leaves admission `UNKNOWN` before thread creation.
Null or omitted optional `nextCursor` terminates the supported catalog response;
non-null cursors must be followed and remain subject to all limits. An
unconfigured provider is not a pre-create refusal. Missing/invalid actual startup
provider identity stops probes/work and retains the thread for reconciliation.
Failed turns retain only the normalized safe cause available from provider evidence;
raw provider error strings and credentials are not persisted as diagnostics.

## Existing and managed Screen continuation

Existing TUI sessions retain their original discovery and continuation behavior,
including names outside the new worker's narrower creation grammar. A queued
Screen keystroke is not delivery proof: the existing route requires a durable
matching user event followed by a non-user event. Its `accepted` status proves
delivery only, not successful execution or semantic acceptance of the task.

Managed workers continue through the same method, with optional current target
readback and explicit idempotency identity:

```python
result = runner.continue_screen(
    screen, next_action,
    target_guard=existing_target_readback,
    continuation_id=stable_continuation_id,
)
```

Continuation preserves the exact original stored goal, scope, context and
authority. It reads current configuration and the bounded model catalog on the
existing connection, compares the admitted model and any explicit configured
provider with the original effective startup, and checks retained effort metadata.
An unconfigured provider stays null in current configuration evidence while the
original actual provider identity remains bound to the same thread/connection;
the adapter neither replaces it from the catalog nor creates another thread.
It then re-runs the needed harmless probes and rechecks independent
target/transfer/lease gates before the next work turn.
The original startup receipt retains its original time; it is never relabelled
as a new startup observation. Changed connection/mode/workspace identity is
`UNKNOWN` and requires reconciliation. A known mismatch against retained startup
model/provider or an explicit effort is `MISMATCH`; missing model evidence is
`UNKNOWN`. The default continuation identity binds Screen and prompt; an
intentional repeat requires a new explicit identity.
Pending operations and failed/unknown initial work prevent further dispatch.
An older managed receipt without the required model binding is also `UNKNOWN`;
the adapter never fills actual fields from a new catalog or silently restarts a
thread. Existing TUI Screen delivery remains on its existing separate path.

New-worker delivery evidence requires a matching provider `userMessage` followed
by a non-user item on the exact thread and turn. Persisted normalized event IDs
and hashes identify those observations. A matching user event does not satisfy a
capability probe; successful exact `commandExecution` items are still required.
Managed continuation returns `accepted` only for proven delivery; its receipt
separately reports actual turn state and `semantic_acceptance:NOT_EVALUATED`.
Creation returns `turn_completed_unaccepted` or `turn_failed_or_unknown`.

## Verification, rollout and rollback

The offline tests use real local worker/stdio processes behind explicitly
synthetic GNU Screen and Codex peers. They execute filesystem probes, include
realistic provider user events, exit the initiating caller before continuation,
verify call order and refusal cases, and clean/reap only fixture-owned processes.
Run the narrow group with a bounded outer runner:

```text
python -m pytest -q tests/test_screen_launch.py tests/test_session_hub.py
```

Actual GNU Screen, Codex thread creation, host installation, a live business
task and existing host Screen behavior are `NOT_RUN` in this preparation
environment. Before deployment, under existing applicable authority, verify:

1. The exact installed Screen/Codex/Python versions, inherited model/provider and
   existing allowed mode, using an already owner-approved compatible executable.
2. Supported terminal startup override, one intended window, actual Screen
   socket/PID, task cwd and selected Codex home.
3. Same-connection effective config and complete model catalog before thread
   creation, bound actual startup model, supported null/absent configured provider
   resolved from the required actual startup provider, explicit configured-provider
   match, observed or explicitly unknown actual effort, and exact successful tool
   probes before any authorized task artifact is written.
4. Caller exit with worker/connection persistence, a managed continuation, and
   independent semantic checking of the actual authorized result.
5. Current target gates/transfer isolation/old writer/leases where applicable,
   plus unavailable or ambiguous model admission, changed startup model, blocked
   approval, safe failed-probe cause and unresolved-operation negatives.
6. A separately authorized observation/continuation of an existing TUI Screen,
   preserving its process/session and proving delivery and actual behavior.

No source test or read-only App Server initialization establishes those live
criteria. Source rollback restores reviewed files and pauses new launches until
a supported guarded path is selected. It does not cancel or reap any live
Screen; already created workers require separate supported reconciliation.

## Primary protocol references

- https://www.gnu.org/software/screen/manual/html_node/Invoking-Screen.html
  (`-D -m`, `-S`, `-c`, `-ls`, checked 2026-10-03).
- https://www.gnu.org/software/screen/manual/html_node/Startup-Files.html
  (current `SYSTEM_SCREENRC` and build-dependent global override).
- https://www.gnu.org/software/screen/manual/html_node/Environment.html
  (Screen process environment; historical versions use `SYSSCREENRC`).
- Codex App Server sources and exact local schema checks are linked in
  [SESSION_LAUNCH](SESSION_LAUNCH.md); schema availability alone is not a runtime
  thread/startup/probe or behavior result.


## Existing-thread settings readback (rc2045)

Creation still binds config/read plus the complete connection-local model catalog
to actual thread/start metadata. Managed continuation reads the exact retained
thread with thread/read {threadId, includeTurns:false} on its owning connection.
A loaded idle thread's current configured model/provider/effort/cwd must match
the retained startup. Global model/effort defaults are recorded separately and
do not select a model for the existing thread. The same bounded current catalog
must advertise its exact model and effort. Config policy and explicit provider
checks remain; no configuration writes, model overrides or thread/resume occur.

Missing/null model or effort, unsupported reads, notLoaded/systemError or stale
readback is UNKNOWN; active threads are BLOCKED before probes/work. thread/read
metadata is not per-turn execution telemetry. Historical startup is not relabelled
as a current read. A fresh read grants no business or target authority.

New workers advertise current-thread-readback/v1 in their status. A loaded older
worker without that capability returns UNKNOWN before a continuation journal,
mailbox write, probe or dispatch. Installing this source does not reload workers.
Any old failed/pending operation remains preserved; replacement/adoption needs
its separate exact terminal/effects/writer reconciliation and supported guards.


## Guarded same-SID cold transport adoption

`CodexRunner.adopt_screen(name, next_prompt, adoption, workspace,
launch_request=request, adoption_guard=held_guard, target_guard=current_targets)`
creates a new owning Screen transport for the **same existing native SID**. It
never stops, resets or reloads the old worker. A new unique registry/name is
required; old failed/pending/journal records remain immutable. Existing
`create_screen` and `continue_screen` retain their original roles.
For an exact successful predecessor followed by a distinct reconciled failed
dispatch, [reviewed successor adoption](SCREEN_SUCCESSOR.md) is an explicit
opt-in append-only chain. Existing failed/in-flight SID journals still refuse;
the original journal is never reset or overwritten.

The adoption input contains `session_id`, `old_name` and `old_pins` (raw SHA-256
of identity.json, bootstrap.json, startup.json, state.json and selected failed
receipts). New request context must contain `adopted_original_contract`, exactly
matching the old bootstrap's original_goal/scope/acceptance/context/authority.
This is historical data, never renewed authority; the new request binds today's
authorized next work. Same SID retains server conversation history; unknown
hidden instructions are not claimed byte-identical.

`adoption_guard(request, adoption)` must be a caller-owned context manager that
holds a real controller ownership exclusion until the whole call exits and
yields a live `check(query)` callable. A static receipt is insufficient. Query
binds phase, attempt_id, request_sha256, adoption_sha256 and actual new_worker.
The response repeats those identities with observed_at (maximum 60 seconds),
nonempty stable owner_exclusion_token, owner_exclusion_held:true, exact session_id,
terminal_effects_reconciled:true, old_owned_lineage_absent:true, terminal_turn_id
and evidence_ref. Before transport `source_writer_state` must be FREE; before
resume and before dispatch it must be NEW_WORKER_OWNED and new_worker_sha256 must
match the supplied actual worker. The owning implementation must prove that
writer lock belongs to the new exact lineage. Hold a separate controller lock,
**not** a source-writer flock that the unchanged Codex wrapper needs to acquire.
The old worker uses a `safeio.lock` directory lifecycle lock, removed on normal
exit. After exact PID absence, adoption requires the canonical `worker.lock`
path to be absent. Any existing file, directory or symlink remains UNKNOWN
and untouched; an unlocked descriptor cannot substitute for lifecycle cleanup.
Local PID absence, original file pins, no pending and absent old worker lock are
additional checks; none alone proves quiescence or effect reconciliation.
For a retained pending dispatch, `pending_reconciliation` may instead select the
exact reviewed receipt described in [SCREEN_RECONCILIATION.md](SCREEN_RECONCILIATION.md).
Pending remains present; current adoption guard responses also bind the receipt
hash and reviewed turn. Every other ownership, environment and once gate remains.

The initial supported permissions are deliberately limited to retained actual
`danger-full-access` plus `never`. Resume must return the exact singleton sandbox
`{"type":"dangerFullAccess"}` and approvalPolicy `never`. It has no restricting
workspaceWrite root/temp/network members. Other permission profiles remain
UNKNOWN until their complete provenance is supported. Current reviewer and
runtime-root digest are recorded separately; their historical values remain
UNKNOWN. The adapter never answers an approval request. Independent source,
authority, target/lease and storage boundaries still apply.

The new connection reads config policy and complete model catalog, selecting the
retained model/effort as a historical candidate independently of global defaults.
It sends only `thread/resume {threadId, excludeTurns:true}`: no setting, path,
history, policy or instruction overrides. Actual resume SID/model/provider/effort/
cwd/rights must match the retained startup, followed by fresh same-connection
loaded-idle thread/read. Exact harmless tool probes and independent targets pass
before a guarded destination claim and the new work. Missing/mismatched/unknown
readback stops dependent work and preserves the resumed identity.

An exclusive SID-keyed adoption journal is reserved before any transport effect.
Any existing record, including UNKNOWN, blocks another launch ID/name/operation
from replaying resume. There is no automatic reset or reconciliation override.
The held controller guard can exit after failure because the durable SID block
remains. Any later recovery needs separate exact effects reconciliation; this
API does not claim to implement a reset route. Installation alone never upgrades
an already loaded worker or accepts a business result.

## Request-bound probe deadline

`probe_budget_seconds` is optional, integer 1..240, default45. A newly created
worker binds the effective value into its bootstrap digest and publishes it with
`finite-probe-budget/v1`. Native probe observation uses that value; the parent
RPC waits that value plus five seconds (legacy defaults45/50). An explicit budget
requires matching request/bootstrap/current worker capability and budget readback;
an older loaded worker cannot silently accept it. Unknown timeout effects still
require reconciliation before any retry. This field neither extends startup/work
deadlines nor transfers an old transport's capability proof.
