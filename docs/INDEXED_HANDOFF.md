# Indexed results and verified terminal handoff

Current source candidate: `0.8.0rc1` (not publication or host adoption). RC-labelled sections below are retained historical records, not current installation or publication claims.


Stable source `0.7.1`. This POSIX local adapter implements the provider-neutral
format; live installation, coordinator adoption and external publication require
their own evidence. Private library objects and project receipts are not public
package inputs. No hooks, credentials or policy changes are required.

## Owner library and entry protocol

Explicit library root belongs to its owner. Separate confidential scopes use
separate physical roots. START.md is fixed protocol text; ROOT.json is the only
atomic current pointer (16 KiB limit); its digest-bound same-generation ROUTES
is at most128 KiB. Pages are at most64 KiB. Objects have logical IDs separately
from immutable SHA256/length/scoped-aos refs. Ordinary readers open only the
three entry files, selected pages, selected manifests and evidence. ROUTES named
copies use snapshots/<generation>/<routes-digest>/ROUTES.json so aborted staging
attempts cannot obstruct a later snapshot at the same expected generation.
ROOT embeds the small verified membership report as well as its audit ref;
ordinary readers need no fourth bootstrap file. No session/history scan.

## Build, acceptance and publication

Library.create/build_handoff/validate_handoff/publish_handoff/search/resolve/
read_evidence/restore/rebuild_indexes/publish_rebuild have a local CLI adapter:
agentos library --root OWNER_LIBRARY ACTION. Python callers must obtain a
principal from a trusted authenticated adapter; CLI derives the actual POSIX UID
and accepts no arbitrary claimed principal. This is no hostile-same-UID sandbox.
MCP remains its six existing planning/read tools; a library MCP bridge is not
implemented or implied by the format.

Manifest records scope, criteria/result/deliverable/evidence, current captured
provenance/selectors, decisions and reasons, historical permission boundaries,
checked-empty sections, open task refs, recovery/dependencies/privacy. Completed
parents require completed mandatory children; expanding a completed parent
requires a new scope revision. Checkpoint is unfinished, never successful closure.
Typed selectors supported here are UTF8 byte ranges, captured single-message ID,
unique Markdown section, and pinned commit-path line range. Unsupported source
adapters/selectors fail explicitly. Sources are not fetched or re-executed.

Content and clean restore checks precede publication. Batched identical captured
asset/recovery sets share a verified clean restore by exact hash; every candidate
still checks its own scope/provenance/hash/summary. Single validation exercises
candidate routes; batch publication verifies exact full index membership against
all accepted registry rows before ROOT commit. Eight checks are bound to receipts;
publication precommit validation becomes acceptance only at the successful CAS.
Files and directory links are fsynced under a kernel publisher lock, released
automatically on crash; expected generation prevents lost updates. Immutable
objects/report/registry/index pages precede the sole ROOT replacement. Idempotency
reconciliation reads the accepted operation tree after an unknown response;
an unreferenced staging object is never discoverable as accepted. Large operation
receipts page accepted refs and inline at most200 items.

## Search, authority, recovery and retirement

Exact ID/entity/project/stage/topic/related-entity/decision/task/type/state/time
and versioned NFC/casefold lexical indexes support current/history/as-of.
Controlled aliases use paged lookups and explicit ambiguity/redirects. IDs still
honor other filters. Pagination pins query, authenticated principal and snapshot;
current ROOT ACL is checked before any historical cursor, card, ref or count.
Exact declared predicates report complete; semantic natural-language requests
explicitly report partial. Empty results contain a safe query trace. Independent
external freshness is not inferred from a current snapshot; captured observations
always require revalidation for a claim about the current external source.

Restore verifies selected captured bytes, creates a fresh destination, refuses
overwrites and symlink/traversal refs, and runs no archived command or permission.
Missing objects/dependencies report exact partial recovery; corrupt bytes fail.
Repair walks only the committed accepted registry, never object-store discovery
or sessions. Mandatory facet loss/sequence/generation/normalizer mismatch refuse
ordinary reads; repair rebuilds from pinned accepted data and validates membership.
Unsupported normalizer migrations require an explicit successor adapter.

Retraction is supported logical retirement: a new immutable snapshot removes
current visibility and retains historical accepted bytes/reasons. Retirement
report returns reclaimed_bytes=0. Physical session cleanup/GC is NOT IMPLEMENTED;
coverage, backup and specific deletion approval are separate gates. Synthetic
test fixture disposal is a measured test-only operation, not a session-cleanup API.

## Project lifecycle and coordinators

Every new/resumed mutable project entry records mandatory handoff and its owner
home. Completion/checkpoint publishes and reads back a verified handoff before
persisting CLOSED/CHECKPOINT. Legacy closed records remain immutable. Terminal
retry journals bind reviewed payload and source/document hashes. Required source
write surfaces/current docs are captured, not unrelated directories or chat;
uncaptured baseline dependencies are explicitly external_required/partial.
verify-closeout additionally verifies accepted library binding and required bytes.

Coordinators and workers use the same route: selected owner root → exact entity,
project/topic or lexical query → manifest → selected evidence. A coordinator
summary of prior work must cite library ID, handoff ID and manifest revision,
and show partial/freshness limits. A live coordinator integration is accepted only after
its authenticated adapter actually executes this lookup and reads back results;
source instructions or a worker test do not prove live adoption. The bundled
CLI/Python path is usable without sessions; no private kernel/hook is needed.

## Verification and next bounded package

Synthetic tests cover fresh-process recovery, exact oracle intersections,
RU/EN aliases/ambiguity, visibility/idempotency/crashes/races, ACL revocation,
corruption/missing bytes, parent/task continuity, accepted-only repair and100,000
actual accepted packages with a3-entry/4-page exact-ID budget. Runtime metrics,
source-bound receipts and independent exact-source review determine acceptance.
Test counts and timings belong to external author evidence, not timeless policy.

Universal personality/style configuration is included in this successor through
the existing bounded profile adapter; see PERSONA.md. Private values and actual
connected coordinator adoption remain target-specific. The existing coordinator name is
preserved; no human biography or private kernel/hooks enter core. Explicit owner
publication/adoption authorization is handled only after exact-source review and
current canonical repository/host binding, not inferred from a library receipt.
Session deletion remains excluded.

## Historical: Independent P1 repair within0.7.0rc1

Every `embedded` dependency must name `asset_id` and exact scoped `ref` of an embedded deliverable or evidence asset. A caller can derive the ref with `library.store.reference(bytes, media_type)` before building; build writes and validates the actual asset. An embedded label alone, missing asset, unavailable preservation, wrong ref/scope/size or corrupt object refuses acceptance. Restore reports a dependency missing until its matching asset bytes have actually been verified and restored. Old unbound embedded labels remain readable as PARTIAL, never COMPLETE. The schema condition requires both binding fields only for embedded dependencies.

Approved tracked directory aliases are captured as typed JSON metadata at separate `source-links/` paths. No alias is followed or reconstructed. Exact original path/target/Git metadata is preserved; a required unknown `source-link:` dependency and `not_restored` entry make recovery PARTIAL/external_required. Capture and journal retries recheck the same admitted link/index identities, source snapshot and document hashes before publication. Generic path guards remain strict.
