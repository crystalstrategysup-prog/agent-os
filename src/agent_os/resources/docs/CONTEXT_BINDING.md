# Bounded context binding

## Problem and scope

Installed files, selected profile hashes and an agent's acknowledgement describe
different facts. An installation receipt does not show the bytes available in a
particular turn. A profile entry containing a document path is not the document.
This change adds an explicit, bounded materialization step to the existing manual
integration. It is not a native hook, a sandbox, or proof of agent compliance.

## Contract

`agentos --home USER_HOME context build --request REQUEST.json` (or `-` for stdin)
reads only explicitly selected profile entries and indexed documents needed for
the declared purpose. The output contains their text and hashes, the original
goal, semantic acceptance, known answers and the session/turn binding. The caller
must consume that actual output in the current context before depending on it.
Goal fields are caller-supplied current task or handoff context; this command
preserves them verbatim but does not authenticate `source_ref` or prove that the
caller supplied the complete historical goal. Verify that provenance separately.
No recursive history scan, credentials, environment dump or automatic selection
is permitted. A reference path is resolved under the selected user home; each
index is pinned by its selected profile entry and each document by its index.

Request schema `agentos.context-request/v1`:

```json
{
  "schema": "agentos.context-request/v1",
  "session_id": "current-session",
  "turn_id": "current-turn",
  "purpose": "project-change",
  "profile_keys": ["owner.workflow"],
  "index_keys": [],
  "goal": {
    "original": "Preserve the agreed user outcome",
    "scope": "The existing approved local source scope",
    "acceptance": ["Verify the requested result against evidence"],
    "known_answers": {"comparison_unit": "the already agreed unit"},
    "authority_ref": "current owner instruction reference, not a new grant",
    "source_ref": "current task answers or accepted handoff reference"
  }
}
```

The caller chooses exact relevant profile keys. For an indexed rule, `index_keys`
contains the base profile key; `<key>_sha256` must also exist in the current
selection. The index uses `documents: [{path, sha256, required}]` and may constrain
`applies_to`. Document paths are relative to the index directory. Do not read a
rule whose scope is inapplicable. Missing, conflicting or changed dependencies
stop only the action that depends on them. Public defaults contain no private
presentation rules or personal identifiers.

Purposes are `project-change`, `continuation`, `project-report`,
`project-snapshot`, `question`, `search`, `audit` and `discovery`. The first two
require a goal. Reports may carry the current goal without opening an intake.
Ordinary reading with no requested profile dependency returns `FAST_PATH`
without touching a user home and needs no capsule command at all. Real changes
still follow PROCESS: documentation before product writes, target gates separate.

## Verification and continuation

`context verify --request REQUEST.json --receipt RECEIPT.json` re-materializes
the current dependencies and compares the capsule hash, session and turn with
a caller-supplied observed tool-result reference. Receipt fields are `session_id`,
`turn_id`, `capsule_sha256`, `event_kind: "tool_result"`, and `event_ref`.
An acknowledgement is insufficient. Success is named `CURRENT_BINDING_MATCH`:
it verifies the byte binding and the shape of the supplied reference, not the
authenticity of that event or whether the agent applied the rules. Collect the
actual provider event independently for live acceptance. A matching receipt has
`behavior_compliance: "NOT_PROVEN"` and grants no authority.

At a handoff, retain the original goal, scope, semantic criteria, known answers
and source references. Revalidate the current authority at the target; copying
`authority_ref` does not renew or widen it. Reconcile an old writer and enforce
the target lease under SESSION_LAUNCH before any target write. If an answer is
already known for unchanged scope, reuse it; ask only a material unresolved
question. A snapshot should name the verified result, the remainder and its next
owner using the existing coordination ledger, rather than close the parent goal
because a child stopped.

## Acceptance and limits

Targeted tests cover actual selected/index/document bytes, stale selection,
changed document/index, path escape/symlink, bounds, purpose mismatch, carried
goal/answers, cross-session receipt and ACK rejection, and independent fast reads.
The integration bootstrap routes through this command for dependent work.
Existing open chats require a fresh output read and observed behavior review.
No code here can prove a hidden prompt was loaded or that a human-readable
instruction was followed. No live installation or adoption is implied.
