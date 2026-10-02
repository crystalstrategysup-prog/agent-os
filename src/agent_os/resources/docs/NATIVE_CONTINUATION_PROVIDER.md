# Optional native continuation provider

This local source successor implements a callable driver for an **existing**
native Codex thread. It is not installed or adopted by the actual root. The
accepted RC artifact remains immutable; no replacement wheel/tag is created.
Native v2 continuation transitions and legacy migration are unchanged. The module
does not schedule, create/resume a thread, choose a worker, change permissions,
read auth/session files, or publish.

## Exact supported contract

`codex_rpc.NativeRpc` connects to the selected existing native daemon through
`codex app-server proxy`. It uses documented Unix WebSocket Upgrade and
`initialize`/`initialized`, bounded JSON-RPC, masked client frames and no
approval replies. It verifies explicit binary version and read-only existing
daemon status/version before connecting. It never starts/restarts the daemon.
Owner selects the correct executable/environment and verifies socket origin.

This implementation pins native app-server0.159.3 v2 schema SHA256
`e77b7d1436a78f431a74b2cb263a862e92ae40d70411bc63835b47ab2168827c`.
It exposes only metadata `thread/read`, bounded `thread/items/list`, and narrow
`turn/start`; all auth, settings, create/resume and permission/model/workspace
overrides are refused. Server requests requiring owner action stop the client;
the adapter does not approve them. Closing terminates only its own proxy child.
Individual transport requests use a shared send/response deadline of at most
20 seconds. Proxy stdin uses nonblocking `os.write`, a readiness selector and
partial-write loop; frame masking is chunked and observes that same deadline.
Upgrade write/read shares a deadline as well. Timeout or broken pipe aborts
only this client's proxy (bounded terminate/kill cleanup), releases compliant
locks, and preserves uncertain delivery without resend. Cleanup adds at most
two 250ms process waits to the I/O deadline. Responses are bounded to4MiB;
unsupported fragmented frames refuse conservatively.

`continuation_provider.NativeProvider` requires an exact provider mapping,
selected target cwd/session and recorded **thread creation CLI version**, plus
an owner-supplied `verify_authority(phase, mapping)` function. That verifier must
validate the actual actor, operation, current target authority and existing
writer lease on read/dispatch/acknowledge. It must raise when scope/lease is
unavailable. Actor labels, transport identity and a local callback are not an
authentication system or new target grant. Do not supply an unconditional allow
callback for production. The thread's creation version may be older than the
verified current daemon's protocol version; they are separate pins.

## One admitted invocation and conservative recovery

Call `continuation_provider.run(home, item_id, actor, expected_revision,
provider)` for one explicitly selected v2 item. Exact revision/actor/schema and
pin checks precede action. v1 PENDING/CLAIMED/UNKNOWN/ACK refuse before provider
I/O; migration or resetting legacy state is not performed. A known ACK returns
without I/O or another receipt transition.

Before a new delivery, metadata read verifies exact target identity,
non-ephemeral history, direct-input capability and idle status. Busy/unloaded or
wrong target is not replaced or resumed. Local core then claims and commits
DELIVERY_UNKNOWN with stable operation key and fresh generation/nonce. The
driver persists an immutable per-generation invocation intent containing the
exact request text/digest, native namespace, actual selected mapping and client
correlation value **before** external I/O. Local driver lock serializes its
calls; the core continuation lock spans the final revision check and bounded
invoke, also serializing compliant core writers/installer final queue checks.
These local locks do not replace the real target lease or coordinate other user
homes/providers.

The only send is
`turn/start({threadId, clientUserMessageId, input:[{type:"text",text:envelope}]})`.
Envelope propagates immutable ledger ID/action, selected owners/workstream,
operation key, committed generation/nonce and delivery start. Client message ID
is a deterministic correlation digest; it is not a generated provider event
ID or a promise of native deduplication. Actual returned `turn.id` is recorded
when received; successful return alone cannot ACK.

If a response is lost, or a later invocation-intent update fails, repeated run
only queries the retained intent. No timeout takeover, resend or replacement
writer occurs. If process loss happened after core begin but before intent
creation, the item stays UNKNOWN/HOLD: absent intent is not safely reconstructed
into permission to send. If ACK committed but its response was lost, readback
returns the existing ACK without another call. A changed mapping/generation
cannot reuse the old intent.

## Durable query before CAS ACK

Read the same selected target via `thread/items/list`, descending pages of50,
maximum4pages. Retain only own intent and bounded evidence IDs/digests/times;
never persist thread transcripts, reasoning, tool payloads or command output.
The adapter requires exactly one matching `userMessage.clientId` and exact text
input, actual user event ID and turn ID, a producer `startedAtMs`, then a later
same-turn public `agentMessage` with a strictly later producer timestamp. A
returned turn ID, if known, must match that actual turn. Interleaved user input,
duplicate event IDs, content relabel, future/equal/reversed timestamps, another
turn, pagination cycle or missing optional fields cannot ACK. Exact origin,
persisted clientId echo and ordering still require real native acceptance; the
schema and fixture do not establish producer behavior for an actual target.

Only that validated query generates the core receipt. Current generation/nonce,
consumed evidence and revision are then checked by the unchanged CAS engine.
An item changed during read cannot be ACKed by stale evidence. Result delivery
ACK is not a completed review or project.

The native contract supplies no authoritative operation-specific non-delivery
query. Generic RPC error, `thread not loaded`, empty/failed read and missing
activity remain UNKNOWN. The driver never calls `not-sent`. An independently
verified non-delivery action elsewhere must preserve core history and generate
a new nonce/generation; old native events/intent cannot ACK that newer attempt.

## Actual root and rollout boundary

The selected Mac daemon does not load the cloud root/workstream. Cloud thread
tools are not callable from this implementation context. A root cloud provider
must implement its own exact tool contract/namespace; native events cannot be
relabeled as cloud evidence. The separate v3 option in `CLOUD_RECEIVED_ONLY.md`
uses exact persistent user input plus an explicit same-turn assistant nonce/
generation/digest ACK for receipt only. It requires verified cloud origin,
immutable complete records and actual authority/lease; it does not relax v2
timestamp rules or fabricate missing producer time/IDs. Live root wiring and
target proof remain pending.

Local synthetic tests exercise invocation/event/ledger control flow and real
pipe framing with a synthetic peer. Their ACKs are **not live/root acceptance**.
Actual0.5.5/current and admitted old workstreams stay unchanged. Independent
successor review, root provider integration and live fault/replay acceptance,
client adoption and agreed sequential host rollout remain gates. Privileged
remote reads are still blocked; publication remains last.
