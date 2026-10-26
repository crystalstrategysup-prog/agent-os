# Atlas — two depths, one workflow

This is a procedural reference, not permission for mutation. `AGENTS.md`
is only a router. A simple read-only question needs no Atlas intake.

## Profile selection
- MINIMAL: one bounded source change with known owner, effect and contract.
  Load the exact work item, a small set of affected source symbols, linked
  contract/docs and pertinent tests. Record one meaningful result/checkpoint.
  Do not create a full dossier, agent room, duplicate matrix or report suite.
- FULL: new project, architecture/data/contract changes, several dependent
  modules or actors, high-impact effects or an explicit owner request.
  Maintain the relevant objective/dossier, architecture and boundaries,
  roadmap, module/API/data contracts, work ownership/matrix/history, build,
  verification, rollout and rollback evidence. Existing authoritative docs
  are reused; FULL never means loading the whole repository in every turn.
- Escalate MINIMAL only for an observed dependency/risk/unknown. Mode changes
  documentation depth only; current scope and authorization remain unchanged.

## Shared lifecycle, not per-command micromanagement
1. Identify effect, exact root/binding, current task/writer, source revisions
   and applicable host/security policy. Existing explicit STOPs remain.
2. Query Atlas by task ID, event/API/symbol and owner. Read index metadata
   first: source/hash, contract, dependencies, version, proof and unknowns.
   Fetch only affected authoritative fragments; expand when completeness needs.
3. Work within existing writer and approvals. On actual start/dispatch record
   status once; maintain affected docs/contracts from real source changes.
4. Verify preconditions, tests and effects. Distinguish source, installed,
   runtime and owner acceptance; an answer or checksum is not runtime proof.
5. Publish one factual checkpoint, exact evidence and next owner/action.
   No false DOING, duplicate writes, extra finish after successful work,
   orphaned history or automatic external side effects.

## Durable function memory
When agent-assisted exploration has found a reproducible route, turn the
repeated procedure into a tested, typed function, not a long narrative skill.
Its Atlas card pins: stable ID, version/hash, trigger, inputs/outputs,
pre/postconditions, allowed effects, idempotency/retries, dependencies,
failure/rollback, owner, tests and observed evidence. Existing code/contract
is canonical; the catalog indexes it, not an alternate source of truth.
Known signals execute the verified function. New/UNKNOWN signals return to
agent reasoning and then can extend the function after verification.

## Retrieval and authority
- Prefer address/hash+bounded file fragments to complete transcripts/repos.
  Do not suppress meaningful dependencies or infer completeness from an index.
- On stale/conflicting/missing refs report UNKNOWN; reconcile before writes.
- For AgentOS public source mandatory policy is `docs/ATLAS_SOURCE_POLICY.md`.
  Honor one writer, protected credentials, private data, external effects,
  leases, disabled native hooks, owner pauses and existing acceptance rules.
- The installed skill and owner policy registry govern the owner's Mac;
  public docs never authorize host, production, DB or secret operations.


## Optional typed selection (not a new entry gate)

`agentos atlas profile --kind audit` returns READ_ONLY without a project registry,
profile, intake or writes. Calling it is optional for ordinary reading.
For a declared known bounded local change:

```
agentos atlas profile --kind project-change --effect local-project-write \
  --change source --bounded --context CURRENT --writer CURRENT
```

This selects MINIMAL. `--change architecture|contract|data|multi-module|multi-actor|
new-project|instruction-routing`, `--full`, unbounded scope, or a target effect
selects FULL. UNKNOWN/STALE/CONFLICT context or writer never yields a ready result.
Caller declarations of CURRENT are not freshness or writer proofs. A target
operation remains BLOCKED by the existing workflow route; selection grants none.

MINIMAL reuses required documents and registers current applicable evidence.
One concise document may cover several required document IDs. It does not lower
AgentOS native READY or skip source, receipt, secret, authority or lease
checks. FULL uses the existing applicability selector, not every available form.
Do not move or activate home policies merely because MINIMAL was selected.

The function is `scripts/work_profile.py:select_profile`, version1.0.0, indexed in
existing WORKSPACE_OPERATIONS.json. Its deterministic inputs, output, effect-free
boundary, tests and rollback are recorded there. No second catalog is created.
Function cards are declarations; executing arbitrary commands from catalog text
is forbidden. Promote a repeated route only after its canonical implementation,
contract and tests exist. UNKNOWN cases return to the owning agent.

## Policy migration and pickup

Public source policies remain verbatim in docs/ATLAS_SOURCE_POLICY.md and must be
read before mutation. Installed package resources carry the same policy.
Private policies remain in the external owner overlay. The supplied40-section
index is an unqualified proposal; do not install it or shorten home AGENTS while
any required policy has no current effect binding, verified body, pickup proof
and reversible rollback. Existing context build verifies selected profile/index/
document hashes and returns their bodies. A catalog, ACK or hash alone is not
policy pickup. Existing running chats require their own observed adoption.
Existing native/target restrictions and exact refusals remain in force.
