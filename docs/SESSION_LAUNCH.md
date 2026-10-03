# Session launch admission

## Scope and stage contract

This source change adds an explicit admission boundary to session creation. It
does not change host permissions or install a runtime. Ordinary questions,
metadata discovery and read-only work in the current session retain their direct
path. A newly created worker must still prove its execution environment before
receiving the original work.

The inherited `CodexRunner.create_session` dispatched the full task through
`codex exec` immediately after a documentation/intake claim. That claim proves
neither inherited sandbox/approval settings nor usable filesystem/network tools.
The `local`, `durable` and `cloud` labels are not permission evidence.

Implement this sequence, in order:

1. Bind the original goal, scope, semantic acceptance, accepted context and
   authority to an owner-selected existing executor and the capabilities needed
   for this task. Reuse known answers. There is no default elevation.
2. Read current provider configuration and the required execution catalog for
   the exact workspace and connection. Establish that the inherited model is a
   candidate in that catalog before creating a thread. Reject a known settings
   mismatch before creation. Missing, stale, copied, incomplete or ambiguous
   metadata is `UNKNOWN`; it is not evidence of a violation or PASS.
3. Create a thread with inherited settings only. Compare the provider's effective
   startup readback with the admitted settings. No policy/configuration setter is
   available through this adapter.
4. Run a bounded, harmless capability probe. Require actual successful tool
   items, matched to this thread and probe turn. Created-thread and agent ACK
   events do not prove command execution. Probe only explicitly needed tools;
   do not send the business task as a probe.
5. Recheck original authority, independent target gates and transfer conditions;
   then claim and dispatch the exact original task with its retained context.
   A started or completed turn is not semantic acceptance of the result.

## Public interfaces

`session_launch.launch(request, provider, target_guard, dispatch_claim)` is the
provider-neutral sequence. A request carries the original goal/context/authority,
not only a prompt hash. The provider returns current normalized observations;
the core never infers effective settings from a provider/executor label.
`target_guard` is an existing target-specific readback integration; launch
admission cannot manufacture target permission or a lease from narrative text.

`codex_launch` supplies a narrow Codex App Server stdio adapter for the existing
owner-selected local executable. It reads `config/read` and bounded `model/list`
pages on the same connection before creating with `thread/start` using only
`cwd`. It binds returned `approvalPolicy`/`sandbox`/`cwd` and actual startup
`model`/`modelProvider`, preserves the returned `reasoningEffort`, and sends text
turns through `turn/start`. It never expands the separate
`NativeRpc` allowlist. For a persistent GNU Screen executor, the guarded
[Screen adapter](SCREEN_LAUNCH.md) keeps that App Server connection inside a
dedicated provisional worker. It checks effective configuration before creating
the Codex thread and requires startup readback and probes before the business
task. A created Screen container alone is not a runnable task session.

`CodexRunner.create_session(prompt, workspace, launch_request=request,
target_guard=existing_guard)` is the default concrete creation path. Existing
callers can obtain the same request from `config.codex.launch_request`; absent
metadata returns `UNKNOWN:request_required` before any provider process. The
request must match the exact prompt and validated workspace. There is no fallback
to immediate `codex exec` dispatch. `CodexRunner.create_screen` uses the guarded
Screen route described in [SCREEN_LAUNCH.md](SCREEN_LAUNCH.md). Unsupported targets
remain explicit UNKNOWN/UNAVAILABLE outcomes. Existing TUI Screen continuation
keeps its durable user-event then non-user-event delivery check; that historical
`accepted` status does not establish command execution or semantic acceptance.

## Request and readback contract

The public request is `agentos.session-launch/v1`, bounded to 64,000 serialized
characters, with an original goal up to 20,000 characters. This example is a shape,
not authorization or a claim about an installed binary:

```json
{
  "schema": "agentos.session-launch/v1",
  "launch_id": "one-stable-task-attempt-key",
  "original_goal": "The exact already authorized objective",
  "scope": "The current bounded work and target surfaces",
  "authority": "Reference and scope of existing owner authority",
  "workspace": "/absolute/approved/workspace",
  "acceptance": ["The original semantic result criterion"],
  "context": {"accepted_answers": {}, "docs": [], "results": []},
  "autonomous_ordinary_work": true,
  "required_capabilities": ["filesystem_read", "filesystem_write"],
  "target_gates": [],
  "executor": {
    "id": "existing-owner-selected-executor",
    "provider": "codex-app-server-stdio",
    "owner_approved_ref": "existing-mode-selection-reference",
    "approved_version": "<read and approved installed version>",
    "approved_sandbox": "<existing approved sandbox mode>",
    "approved_approval_policy": "<existing approved approval policy>"
  }
}
```

Supply actual existing approved values; the adapter never writes these settings.
The concrete adapter opens its own local `codex app-server` stdio child. In the
Screen route, the persistent worker on the already selected host owns that child
and its pipes. The adapter does not select a remote host or claim that an
executor label grants permissions.
`codex --version` must exactly match the approved version; the observed native
`codex-cli VERSION` and input-established `codex VERSION` formats are accepted.
Policy and sandbox values come from the same live provider connection's
`config/read {includeLayers:false,cwd}`. Only the needed non-secret scalars are
retained; raw configuration, layers, credentials and transcript text are not
stored in launch receipts. The pre-create read resolves disk configuration;
effective `thread/start` response and subsequent tool results remain separate
checks because runtime requirements can change the inherited result.

### Inherited model admission and actual startup

A version match and usable inherited permissions do not establish model
compatibility. Two installed executables can expose different catalogs through
the same account. Select an already owner-approved executable and inherited
model combination whose current catalog can be checked; executable discovery or
a familiar name on `PATH` alone does not establish that combination. The adapter
never chooses another binary or model after a failed admission.

After `config/read`, the adapter reads `model/list` with `includeHidden:true`
and a page limit of 100 on the same live stdio connection. It follows opaque
cursors within one shared catalog deadline of at most 20 seconds, with at most
four pages and 256 model rows. Catalog responses must be complete and structurally
usable. A timeout, repeated cursor, exceeded bound or incomplete result stops
admission before `thread/start`; the adapter does not infer absence from a partial
first page. A null or omitted optional `nextCursor` is terminal under the
supported protocol. A non-null cursor must be followed within the same bounds;
invalid, empty or repeated cursors remain `UNKNOWN`.
No provider setter, authentication method or background catalog collector is
added to the RPC allowlist.

| Inherited input and read evidence | Admission meaning |
| --- | --- |
| Explicit `model` has an unambiguous exact canonical catalog `model` match | Provisional advertised candidate; actual startup and probes are still required |
| `model` is absent or null, with one default in a complete catalog | Resolve the unique `isDefault` candidate provisionally; do not write it into configuration |
| Missing/null `model_provider` | Supported absence of an explicit override; provisional until actual `thread/start.modelProvider` resolves the provider on this connection |
| Explicit `model_provider` | Preserve the exact configured value; actual startup must match it |
| Selected string matches only a catalog `id`, display name or inferred alias | `UNKNOWN`; no alias rewrite or fuzzy model match |
| No candidate, ambiguous required default, duplicate/ambiguous rows or malformed metadata | `UNKNOWN`; an unqualified catalog does not prove a provider-specific violation |

The checked catalog describes what this connection advertises. Its rows do not
contain a provider identity, so membership alone does not prove that every
provider/account combination can execute the model. Catalog defaults and
supported effort metadata are also not actual runtime observations. Preserve
these limitations rather than inventing a provider default, assigning another
family, or passing a model override to make a launch work.

The `thread/start` response must supply the actual startup model and provider on
the same inherited connection before a probe can start. The model must agree
with the admitted candidate. An explicit inherited provider must match the actual
provider; an unconfigured provider is resolved only from this response. Neither
an absent override nor catalog membership supplies an actual provider name. A
missing, null or invalid actual provider remains `UNKNOWN`, with the created
thread retained for reconciliation and no probe/work dispatch. No owner settings
change is required merely because the configured provider is null or absent.
Keep configured model/provider/effort, catalog candidate/default information and
actual startup fields distinguishable in the receipt, with their connection,
attempt and thread binding. A missing or null
actual reasoning effort remains `UNKNOWN`; never fill it from a configured or
catalog default. An explicit configured effort must be advertised and matched by
actual startup; when both configuration and startup leave effort null, report that
unknown field without inventing an actual default. Startup metadata is evidence
for that thread at creation, not proof of a later turn's actual model or semantic
behavior.

The `model_preflight` record identifies configured and catalog-derived values,
catalog completeness, page/row counts and a normalized catalog hash. It preserves
`configured_provider:null` plus `configured_provider_present` to distinguish an
omitted key from an explicit null, and reports `provider_source:unconfigured` or
`configured_exact`. The startup record carries the separate actual provider,
`model_metadata_source:thread_start_response` and a `model_binding` result with
`provider_resolution:startup_resolved` or `configured_match`; its
`provider_compatibility:NOT_PROVEN` is intentional. A reported startup
effort can differ from a catalog default when no effort was explicitly configured,
provided the actual value is advertised as supported. A configured effort cannot
be silently replaced in this way.

The provider-neutral observation binds source, attempt, time (at most 60 seconds
old), executor/provider, connection, workspace, effective mode and advertised
capabilities. Configured capability availability is provisional until probed.
The adapter recognizes `never`, `on-request`, `untrusted` and narrowly interpretable
granular modes. `untrusted` is a known interactive mismatch for autonomous ordinary
work. `on-request` may run in-policy ordinary commands and is admitted only for
startup/probe; any actual approval request stops the route without a reply.
No mode guarantees that all future commands or external targets will work.

Supported concrete probes are:

| Capability | Harmless operation | Evidence required |
| --- | --- | --- |
| `filesystem_read` | Read directory entries in the task workspace; print only a nonce | Exact command, actual process cwd, provider item cwd, exit 0 and nonce |
| `filesystem_write` | Create/read/remove its own uniquely named temporary probe file | Same binding and successful result; no existing file is removed |
| `loopback_http` | Start/stop a temporary loopback-only HTTP server and send HEAD | Same binding and successful local round trip |
| `network_http` | HEAD to explicit task-authorized `probe_url` | HTTPS only, no credentials/query/fragment, no redirects, bounded timeout |

These probes establish workspace-local filesystem capabilities. Other filesystem
roots, browser tools and remote execution need an adapter that can advertise and
prove those exact needs; this narrow adapter returns UNKNOWN for unsupported
capabilities. Use a proportionate set of capabilities from the task contract.
A Windows stdio pipe implementation is not included; this adapter returns
`UNAVAILABLE:stdio_pipe_adapter_unavailable_on_windows` before starting a process.
A successful filesystem probe must not be reported as successful networking.
The Codex probe turn is bounded to 45 seconds. All generated Python snippets also
assert actual cwd, because a shell startup file can change directories after a
provider has recorded spawn cwd. Probe receipts keep item IDs and command/output
hashes; assistant claims alone do not produce a passing receipt. An App Server
`userMessage` item is allowed only when it contains the exact submitted probe
text. It contributes no tool proof; unrelated input still fails the probe.

The synchronous work turn is bounded by the configured turn timeout, capped at
1,800 seconds. Its final state is `turn_completed_unaccepted` or
`turn_failed_or_unknown`; it never returns semantic acceptance. The receipt has
`work_accepted:false`. Check actual task artifacts with the existing result gate.

Failed probe and work receipts retain a bounded, normalized cause when the
provider supplies one, including a recognized error category and HTTP status
where safely extractable. They never copy a raw provider message, nested error
text, URL, credential or transcript into the receipt. An unrecognized cause
remains unknown; a successful catalog check does not turn a failed model request
into a successful probe. No failure authorizes a model, policy or auth change.
The normalized `failure` fields are `category`, `http_status`, `codex_error_info`
and `turn_status`; completed turns carry no failure diagnostic. The launch core
preserves available normalized provider failure evidence when refusing the probe.

## Transfers and independent target gates

Retain original goal, accepted answers, documents/results references, semantic
acceptance, scope and authority. Before destination writes, obtain current
old-writer reconciliation and fencing from the existing coordinator, isolate the
source into a disjoint destination, and verify the target's existing lease for
this launch. An `inProgress` label alone proves neither a writer nor its absence.
Never stop, archive, delete or change another session as a launch side effect.

For transfer, add `transfer.source_session`, `source_workspace`,
`source_snapshot_sha256` and `target`. Source and destination paths are resolved
before the disjointness check, including symlink aliases and traversal. The
independent target guard must return current, attempt-bound `target_readback`
records for `before_create` and `before_dispatch`. It receives
`_launch_attempt_id` as a transport-only request key; remove that key before
computing `request_sha256` with `safeio.digest`. Each record includes `phase`,
`observed_at`, `source`, `attempt_id`, and a `gates` mapping whose required entries
contain `status:PASS` and a concrete `evidence_ref`.

Transfer records additionally bind the old session and source workspace,
`old_writer:stopped_and_reconciled|fenced_and_reconciled`, `fence_evidence_ref`,
the exact `isolated_workspace`, `isolated_snapshot_sha256` equal to the accepted
source snapshot and `isolation_evidence_ref`. Lease evidence binds
`lease_holder` to launch ID, `lease_target` to the requested target,
`lease_scope_sha256` to `digest([scope, authority])`, `lease_status:held` and
`lease_evidence_ref`. These are adapters to existing coordinator/target checks,
not new lease creation or permission mechanisms. The trusted caller inventories
gates for the current dispatch scope; unrelated future production steps do not
block ordinary preparation in the current session.

Financial, authentication, destructive, database and production gates remain
independent and are checked again immediately before task dispatch. A suitable
sandbox and successful probe do not satisfy these gates. A timeout after a
mutating provider request is an unknown outcome: record the thread/request
identity, reconcile through supported reads, and do not blindly retry creation
or start a second writer.

The concrete route persists a one-shot launch journal before thread creation and
before task dispatch. Any prior provider-mutation attempt with the same launch ID
requires reconciliation; a fresh caller cannot silently reuse that ID. A
pre-create mismatch can be retried after its exact cause is corrected without
claiming that a task was started. Journal storage is not a security boundary
against a same-user process and does not replace live provider or target checks.

## Verification and activation criteria

Targeted offline tests cover compatible launch and exact call order; known
interactive mismatch before create; missing metadata; copied/stale observation;
missing capability; changed startup settings; ACK without tool evidence; failed
probe; transfer fencing/isolation/lease checks; and an independent target gate
denial after a successful probe. A synthetic JSONL peer covers the concrete
stdio transport without starting Codex, using credentials or contacting a host.
Affected model regressions cover advertised and absent selections, hidden models,
bounded pagination, unknown/default/alias/provider cases, startup binding and
sanitized failed-turn causes. The persistent route also checks model binding
when continuing the original connection.

Run the narrow regression group with a bounded runner:
`python -m pytest -q tests/test_session_launch.py tests/test_codex_launch.py
tests/test_session_hub.py`. The package's external verification directory records
actual stdout, timestamps, timeout and exit status. Synthetic peer tests execute
the generated filesystem probes in temporary directories; network failure and
approval events are injected fixtures. They are not a live Codex acceptance run.

No live Codex or GNU Screen binary is available in the preparation environment.
Before optional activation, the local reviewer must bind the chosen binary's
version and its exact App Server schema. Reuse an already generated schema when
its binary/version binding is verified; otherwise use the documented
`codex app-server generate-json-schema --out <isolated-schema-directory>`, and
verify the used request/response fields against that version. Then run one
authorized isolated worker using the existing approved mode and check its startup
receipt, same-connection catalog admission, harmless tool results and actual task
artifact. Verify the chosen binary's inherited model and permissions; preserve a
null/absent configured provider without guessing a name, and require its actual
provider from `thread/start` before probes/work. Missing retained model admission
still stops before thread creation, even when the provider is unconfigured. A
missing actual startup identity stops probes/work and requires reconciliation of
the created thread. For Screen, also verify
persistence after the creating client exits and a supported continuation in the
same thread. Effective `config/read` alone does not satisfy any of those runtime
criteria. Other executor surfaces
need their own current adapter/readback. If required evidence is absent, report
UNKNOWN; supported optional absence is not itself a failure. Do not create a
policy setter or relax a platform/target guard to pass this check.

Source rollback removes this patch and restores the reviewed baseline files;
pause new launches during rollback until a supported admission route is selected.
There are no permission/configuration, daemon, credential or native-hook changes
to undo. Already created live workers, if a later operator creates any, require
separate supported reconciliation; reversing source cannot cancel their work.

## Protocol evidence

The input source establishes the existing CLI route and the independent native
RPC version/allowlist. No installed `codex` executable was found in the isolated
preparation environment. The official App Server documentation was therefore
consulted for the replacement adapter:

- https://developers.openai.com/codex/app-server/ (read 2026-10-03; redirects to
  https://learn.chatgpt.com/docs/app-server): stdio JSONL transport, initialization,
  config/read, model/list, thread/start, turn/start, commandExecution items and approval
  request handling.
- https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/v2/config.rs
  and `thread.rs`: effective configuration and thread-start response fields.
- https://github.com/openai/codex/blob/main/codex-rs/cli/Cargo.toml and
  `cli/src/main.rs`: native CLI package/version output naming.

These are API-shape evidence, not a claim that the owner's exact binary has been
tested. Pin the approved binary/version and validate its generated schema before
live activation. The adapter must refuse unavailable required evidence and never
substitute copied `config.toml` contents for a live provider response.

The affected `ModelListParams`, `ModelListResponse`, `ConfigReadResponse` and
`ThreadStartResponse` shapes were also checked against supplied, locally generated
schemas for Codex 0.158.0 and 0.160.0. Both versions expose nullable configured
model/provider/effort, canonical model rows with pagination/default metadata, and
actual startup model/provider fields. Configured provider absence/null means no
explicit override; the required string `thread/start.modelProvider` supplies the
actual identity. Optional `nextCursor` absence/null is terminal; a non-null cursor
continues the bounded catalog read. Neither schema establishes a model alias rule
or a provider name to infer before startup. These finite schema checks do not make
either version a universal minimum or prove any target's current model access.
