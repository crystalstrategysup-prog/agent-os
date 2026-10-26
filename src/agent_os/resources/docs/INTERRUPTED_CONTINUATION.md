# Interrupted same-task continuation (candidate protocol)

This nonaccepting metadata transition is separate from SECRET refusal recovery.
Never replay a consumed refusal request, manufacture a new scanner witness,
change a bound task by hand, or restart an old product effect.

An existing VERIFYING/READY/INTAKE task whose exact previous provider turn is
interrupted may advance only through a fresh, owner-authorized same-session
request with exact project/task/revision/binding/events/source/goal preimages.
Old active/unknown turns, foreign actors, pending entry/refusal/handoff,
source drift and stale permits fail before effects. The task becomes
CONTINUATION_REQUIRED; the target turn becomes INTAKE_REQUIRED. No READY,
semantic acceptance, product completion or external authority results.

The existing supported app read_thread route is used through
SupportedReadThreadObserver. The embedding owner integration passes the actual
supported tool callable. It queries at most forty pages of one turn, retains
only exact old/current metadata, and requires matching thread/cwd, interrupted
old turn and active current turn. No new native RPC, includeTurns override,
credential, daemon, callback registry or arbitrary command is introduced.
A Python callable's tool origin is not authenticated by this core: the owning
integration must bind/verify the real tool origin and human decision separately.
Fixtures and saved reports are not live provider evidence. Standalone
`agentos project interrupted-continuation` fails closed without that selected
embedding; it does not accept a caller-supplied interrupted:true file.

Embedding API: command([advance|reconcile, --root ROOT, --request FILE,
--permit FILE], HOME, read_thread=ACTUAL_SUPPORTED_TOOL). For asynchronous tool
clients use an already selected synchronous bridge in the owner integration;
do not substitute recorded results or create a new writer. SOURCE bytes alone do not establish bridge adoption by a target; a separate
actual supported-tool trace and target readback are required.

The durable pending journal blocks lifecycle work. After interruption call
reconcile with the exact request/operation and fresh authority/real observer.
It verifies all pre/postimages before finishing only missing metadata writes;
foreign edits remain untouched. Preimages, original raw event prefix and consumed
recovery records remain preserved; repeated completed reconcile is read-only.
Ordinary advance after commit is rejected. After full enter consumes the ack,
old reconcile is rejected as consumed.

Then perform ordinary full-answer enter on the SAME task/session/current turn,
retaining the original objective, outcome and acceptance plus approved amendments.
Answer reuse is insufficient. Enter consumes the transition, increments revision,
clears old readiness/checks and follows existing document/check/READY procedure.
The original task remains OPEN. Existing CHECKPOINT/CLOSED next-turn behavior
is unchanged. Native hooks remain disabled.

## Distinct identities and one-shot supported-tool bridge

Workflow session_id and native_thread_id are separate; project root and native
cwd are separate. The request pins native_cwd plus the existing workflow
session/bound-turn/task+turn hashes. The actual supported native read must return
that SAME previous turn in the selected native thread and current permitted
turn. This joins existing metadata without inventing a native registry, rewriting
old bindings, or treating a historical report as current authority.

For the existing asynchronous MCP route use the reviewed one-shot
`python -m agent_os.interrupted_bridge advance|reconcile|observe-only --root ROOT
--home HOME --request REQUEST [--permit PERMIT]`. It emits a random nonce-bound
challenge naming only mcp__codex_app__read_thread, exact native thread, bounded
page arguments and request SHA. The existing owner's functions orchestration
calls THAT actual tool. At its trusted in-memory boundary it FIRST computes and
checks the FULL original canonical UTF-8 provider envelope size, THEN strips all
message bodies, previews, titles and turn items. Only strict thread id/cwd, turn
id/status and page cursor metadata plus original_response_bytes are returned
through metadata-only wire v2 with the exact nonce/tool/params/request hash. Timeout, foreign native ID, unexpected
method, response cap, wrong nonce/params/hash and unsolicited data fail closed.
No saved JSON evidence flag, daemon, RPC allowlist change or extra agent exists.
The bridge is an adaptation of the existing trusted caller, not authentication
of arbitrary stdin. Preserve only the sanitized challenge/call identity, bounded result metadata and
size-check receipt for independent review. Never persist or print the original
message bodies/credentials or forward them through command/write_stdin transcript.
Observe-only is provider evidence only, never task admission or authority.

Reconcile after the original continuation turn finishes uses the SAME immutable
request/operation plus fresh authority naming the permitted replacement turn.
The provider must show the original bound old turn interrupted, the previous
continuation turn completed/interrupted (not active or unknown), and the new
same-native-owner turn active. Before/after/prior-postimages are verified before
writes. Reconciliation retargets only that operation's pending nonaccepting task/
turn metadata; original request, preimages and each prior journal remain retained.
No second advance or product effect occurs. Eight retargets and the existing
finite journal cap bound recovery; a conflict stays pending for its exact owner.
Normal full-answer enter consumes the final ack; it is not READY.


## Supported observer capacity v2 (SOURCE candidate)

Fixed turnLimit=1, includeOutputs=false, maxOutputCharsPerItem=80; up to40pages/40turns,4MiB per response and16MiB aggregate,45s per bridge call and120s aggregate. Follow only genuine cursors; a single oversized turn, missing required turn, provider isError, foreign identity, conflicting status or exhausted budget remains UNKNOWN and refuses dependent admission. No adaptive fallback or saved transcript proof. Observer-only performs no source snapshot or target metadata mutation. Actual supported-tool origin, exact completed previous turn and current inProgress remain required. The existing CONTINUATION_REQUIRED/INTAKE_REQUIRED then full entry sequence and CAS/authority/journal guards are unchanged. Source/synthetic proof is not target admission.

Deadline qualification: the public synchronous observer rejects late returned results; it cannot forcibly interrupt an arbitrary blocking callable. The owning integration must supply the supported bounded call protocol. The stdio bridge waits within the shorter per-call/aggregate deadline and checks again after final read/parse. No background worker or unsafe interruption is introduced. Full provider envelopes are budgeted before stripping at the selected trusted integration boundary. provider_encoded uses ensure_ascii=false, sorted keys, compact separators and trailing newline encoded as UTF-8. Errors consume the same original byte budget. Stdio transports at most64KiB of strict sanitized metadata, and charges its received original_response_bytes against4MiB/response and16MiB total. Direct in-process supported-tool returns are measured before extraction by the observer itself. Matching stdin shape does not authenticate real tool-call origin.


## Metadata-only bridge wire v2 and privacy boundary

This is an explicit wire contract change; old full-result wire v1 is rejected.
The bridge emits agentos.app-tool-metadata-challenge/v2 with exactly schema, tool,
params, nonce, request_sha256. The selected trusted tool integration holds the
ACTUAL supported-tool result in memory and uses one in-memory MetadataResponseAccounting for the SAME operation and
calls prepare_metadata_response(..., accounting=that_object) (or a reviewed equivalent) before any logging/stdio. That boundary measures the full
original canonical UTF-8 envelope FIRST, refuses >4MiB, and projects only metadata.
Never hand raw turns/messages to a subprocess, command argument, write_stdin, proof
file or debug log. Error bodies are stripped as well. No new RPC/channel is added.

Response agentos.app-tool-metadata-result/v2 has exactly schema, tool, params,
nonce, request_sha256, original_response_bytes (integer, not boolean), result.
For success result is exactly isError=false, thread={id,cwd},
turns=[{id,status}] (at most1), page={hasMore,nextCursor}. For a tool error result
is exactly {isError:true}; do not copy error body text. All other fields are
refused, including previews, items and message content. Wire length<=64KiB.
The bridge preserves45s/120s deadlines including final read/parse, exact typed
nonce/tool/params/request identity and the16MiB original-byte aggregate.

The original_response_bytes value is a trusted integration attestation, NOT a
cryptographic proof or authenticated provider receipt. Neither matching stdin
nor ProviderMetadataEnvelope proves a real tool call occurred or that the size
was measured honestly. Owning integration review and the actual sanitized
challenge->supported call->size check->metadata result trace remain mandatory.
A fixture/helper/caller-supplied size cannot grant completed-turn proof, READY
or target authority. SOURCE tests do not establish actual v2 integration adoption.
The existing task/turn CAS, states, refusal/handoff guards and authority semantics
are byte-identical; this wire change never reconciles a publication guard.

Both per-response4MiB AND aggregate16MiB original canonical-byte budgets are charged by the same operation accounting object BEFORE metadata projection. Error envelopes count. Reusing its nonce/foreign operation or exceeding40calls refuses before projection. The helper refuses an absent accounting object. Do not recreate accounting on each page. The bridge independently checks the attested original aggregate as a second fence; neither fence authenticates caller honesty.

## Opt-in accepted checkpoint history

Interrupted request v1 remains strict and rejects any handoff-prefixed journal.
A caller with accepted historical checkpoints may use
`agentos.interrupted-continuation-request/v2`: the exact v1 fields plus
`accepted_checkpoint_history_sha256` from the current read-only qualifier in
`ACCEPTED_CHECKPOINT_HISTORY.md`. The owning caller must regenerate current
preimages, current native-turn identity and a fresh request-bound authority; an
old refused v1 request or expired permit is never replayed as v2.

The existing bridge advance/reconcile methods handle v2 without a new transport.
The core independently requalifies the exact accepted/superseded Library history
before the supported observer and under the shared Library lock after observation,
through metadata commit/reconciliation. Current ACL/object/registry/retraction,
CAS/source/authority/goal and project/turn lock controls remain unchanged.
The old provider turn must still be interrupted, never completed or unknown; the
current turn must be inProgress. The receipt is
`agentos.interrupted-continuation-receipt/v2`, still FULL_ENTRY_REQUIRED only.
Fresh same-owner full entry and ordinary READY/checks remain mandatory.
