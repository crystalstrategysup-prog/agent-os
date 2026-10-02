# Exact delegation-ingress historical observation

This separately reviewed profile handles the actual cloud route's **tool**
codex_delegation ingress. It does not rewrite it as user input or broaden the
frozen user-only adapter. The implementation has bounded fixture and historical receipt-only canary
evidence, with actual result provenance relying on an authorized parent relay.
Each real owner still verifies route/source/admission/full-read attribution.
A canary proves no running scheduler, persistent connected bridge, work execution,
installation, publication or new grant.

## Frozen profile and hash definitions

Module `cloud_delegation_observed`, separate disposable
`state/cloud-delegation/<id>/` journal. Discriminators:
`ingress_kind=codex_delegation_tool/v1`,
`evidence_kind=single_read_delegation_ingress_observation`,
`acceptance_scope=observed_received_only`, receipt schema
`agentos.cloud-delegation-observed-receipt/v1`. Terminal OBSERVED_RECEIVED or
OBSERVED_RECEIVED_REFUSED means historical acknowledged input only. It proves
no successful work, authority grant, coordinator completion or project acceptance.
Coordinator/core/capability schemas and prior adapters remain unchanged.

Source S and target D are exact lower-case canonical UUID text in this supported
first profile. No trimming/normalization/uppercase conversion. Turn/item IDs are
genuine bounded opaque provider strings. The owner verifies actual source
context, target/workstream/lease and route-generated wrapper attribution;
source_thread_id text alone is not authentication.

`prepare(home, root, task_id, actor, pin, payload=...)` binds one verified CLOSED
stage and its owners; precommits generation1, fresh UUID4.hex nonce and exact
source/target/profile/payload before possible invocation. Canonical JSON is
exactly `json.dumps(value, ensure_ascii=False, sort_keys=True,
separators=(',', ':'), allow_nan=False).encode('utf-8')`, with no BOM/final LF or
Unicode normalization. request_sha256 is SHA256 of the **canonical challenge**,
distinct from exact original payload SHA256, entire P SHA256 and entire E SHA256.

Exact challenge keys: schema, acceptance_scope, ingress_kind,
serialization_profile, serialization_profile_sha256, ledger_id, operation_key,
delivery_generation, delivery_nonce, source_thread_id, target_thread_id,
workstream_id, mapping_digest, adapter_sha256, stage_identity_sha256,
journal_revision_at_admission, payload, payload_sha256. Generation1 and admission
revision2 are exact integers for the single-attempt adapter journal.

P is `AGENTOS_CLOUD_DELEGATION_REQUEST_V1` + one LF + canonical JSON with keys
schema/challenge/request_sha256/ack_instruction. The literal profile requires
no `<`, `>` or `&` anywhere in P. Expected E is exactly:

```text
<codex_delegation><source_thread_id>S</source_thread_id><input>P</input></codex_delegation>
```

S/P are substitutions. No whitespace/prefix/suffix, attributes, namespaces,
nesting, extra children, entity/CDATA substitution or unescape/re-encode. Root
must verify that the actual existing route emits this exact serialization.
Other escaping/profile is unsupported pending separate review. No wrapper hash
occurs inside P, avoiding circular hashing. Full E stays in selected evidence.

## ACK, admission and one original response

ACK prefix is exactly ASCII `AGENTOS_CLOUD_DELEGATION_ACK_V1` then **one LF
byte 0x0A**, followed by one full JSON object beginning `{` and ending `}`.
No CRLF, extra separator LF, surrounding whitespace/trailing LF, quote/fence or
prose. Internal JSON spacing/order is allowed. Duplicate keys and extra fields
refuse. Schema `agentos.cloud-delegation-observed-ack/v1`, scope
observed_received_only, status received/received_refused, exact ledger_id,
operation_key, integer delivery_generation, nonce, canonical request_sha256,
source_thread_id, target_thread_id and workstream_id; refusal adds refusal_reason.
No invented assistant turn echo or circular E hash. Request contains precise
ACK instructions; locally generated ACK vectors never count as actual evidence.

`run(home, id, actor, expected_revision, provider)` CAS-commits UNKNOWN before
one send of **P**. Service produces E; adapter does not send a fabricated tool
transcript. Retain genuine threadId/turnId/admissionOutcome. This profile requires
actual admitted nonempty T, actual target D and verified admission semantics.
Missing/lost/null/unverified T remains UNKNOWN without guessing from latestTurn
or ACK. No retry, replacement writer or NOT_SENT is supplied.

One original bounded read response for D must independently contain a unique
full tool record exactly E and full standalone assistant ACK, distinct actual
IDs with both actual turnId equal T. Preserve roles/texts. At most four responses
of50; no pair/cache join across pages or reads. A later response qualifies only
with the whole pair by itself. Truncated/summary/ambiguous/wrong-source/turn/
wrapper/profile/nonce/hash records refuse even with a correct-looking ACK.
No total-history absence, producer timestamp or eternal immutability is required.

`RawRead` is one original result serialization plus optional genuine reference;
adapter parses and hashes it itself. Never manufacture items, flatten multiple
results or infer roles. Actual full selected records and route/source attribution
must come from trusted existing tools/read semantics, not fixture flags.

## Owner bridge and durable evidence

`Provider` requires verify_authority, verify_complete, **verify_route** and
**verify_admission** callbacks. Route verification checks actual calling source,
serialization and route-generated attribution; admission verification checks
that existing send turn genuinely binds this operation. No new API fields are
required. Identity/profile/source hashes are local pins, not authentication.
Do not use unconditional fixture verifiers in production. Synchronous callbacks
must bound external calls; none is invoked while journal locks are held.

Exact pin keys: provider, adapter_sha256, parent_owner, target_owner,
source_thread_id, target_thread_id, workstream_id, ingress_kind,
serialization_profile, serialization_profile_sha256. Use actual module/profile
hash constants and genuine source/target/workstream/owner facts.

Append a create-only historical observation before own revision CAS: full
source/profile/attempt pins, challenge and digest, exact P and P/E hashes,
actual send projection, selected exact tool/assistant snapshot/roles/IDs/turn,
parsed ACK, pair/original-response hashes, genuine available read reference,
local checked_at and admitted journal revision. Persist no unrelated transcripts.
Snapshot/hash preserves observer capture, not authentication or an atomic
server snapshot. Keep original response preimage separately for bounded root
verification when permitted. Storage is not a hostile same-UID security boundary.

Evidence/CAS loss preserves UNKNOWN unless readback confirms the existing
terminal. Uncommitted old evidence cannot substitute for a fresh response.
Terminal repetition does no I/O. Optional explicit recheck appends positive
discrepancy hashes for later visible edits, preserving original receipt/journal;
omission is not deletion, and neither allows reopening/resend.

## Review boundary

Implementation follows before-code SPECIFICATION.md and independent
DELEGATION-INGRESS-DESIGN-REVIEW.md. Targeted tests exercise exact positive
profile, source/turn/wrapper/role substitution, ACK LF/canonical hash, truncation,
replay/page mixing and evidence/CAS faults. Frozen user-only adapter still
returns UNKNOWN for tool ingress. Real root bridge/source/admission/full-read
verification and one separately authorized canary remain later review gates.
Old uncertain requests without this new precommit cannot be retroactively
certified or retried. Installed0.5.5, core, credentials/grants and publication
remain outside this implementation step.

## Same-admitted-turn candidate accounting

Every assistant record beginning with the reserved ACK marker in the genuine retained admitted turn participates before ACK validation. Any malformed candidate or multiple valid candidates refuses observation; unrelated turns and ordinary/quoted/fenced noncandidate text remain permitted. Standard JSON Unicode escapes may protect an original tool-result serialization during owner relay: normal JSON parsing must restore exact E. Do not HTML-unescape, change roles, assemble pages or substitute locally generated vectors. Preserve the entire original structured value and outer transport provenance separately.
