# Model selection and minimum sufficient reasoning

Contract: agentos.model-selection/v1. Stable source `0.7.1`; not installed or
published by this preparation, with no current runtime/model/settings changes. The policy is routed by
COORDINATOR_KNOWLEDGE_INDEX.json. This document contains generic rules, no private
presentation template, name, owner profile or session data.

The new index is knowledge1.2.0 for core0.7.1. Inherited coordinator documents
retain their historical1.0.0/rc2 contract labels and exact accepted bytes; they do
not claim new runtime adoption. Existing private indices remain pinned to their
accepted rc2 index; this source never refreshes them automatically.

## Verified official facts and scope

Checked2026-10-02: [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
supports low, medium, high, xhigh and max; its API default is medium. none/minimal
are unsupported. This is an API capability/default, not proof of another client's
catalog, selected setting, latency or actual executed model.

The [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)
describes low for efficient execution/tool work, medium for planning/judgement,
high for hard reasoning/debugging, and xhigh when evaluations justify additional
latency/cost. Supported values depend on the model. max is distinct from xhigh.
The guide describes tradeoffs; it does not command every agent to run deeply.

## Selection agreement and precedence

Default to the latest available **Sol** in the selected environment's current
catalog. Resolve the exact model version at entry; no permanent numeric alias.
An unavailable Sol is not permission to select Luna, Astra, Terra or another
family. A different family requires a separate exact model agreement with scope,
source/ref and reason. A saved legacy profile/model string is not that agreement.
An explicit available Sol version request may override the default latest choice.

System/developer and actual mandatory environment constraints keep priority.
Do not switch a current session, downgrade a mandatory setting, change grants,
bypass confirmations, launch another writer or alter config to make a proposal
work. Fixed model/effort constraints produce PRESERVE_CONSTRAINT with no proposal;
unknown mandatory fields block rather than being silently ignored. Actual metadata
remains independent even when a fixed setting is named in an instruction.

Catalog availability, family/version binding, capability source and observation
must come from the intended client/account/host. API documentation and another
host's catalog do not establish availability. A missing/provisional catalog or
missing environment effort support returns BLOCKED. No background discovery is
included. Authenticated adapters verify freshness and release ranks; ambiguous
latest ranks refuse. The pure validator cannot authenticate its supplied records.

## Effort and acceptance

| Report code | Full setting | Initial task basis |
|---|---|---|
| L | low | Bounded execution/read/build/edit with a clear plan, tools and measurable checks. |
| M | medium | Planning, judgement, independent review or unspecified/uncertain phase. |
| H | high | Complex diagnosis/debugging, deep dependencies or high complexity. |
| E | xhigh | Explicit escalation with verified comparative quality benefit and delay/cost tradeoff. |
| max | max | Separate full name; explicit deepest escalation with comparative evidence. Never label it E. |

These are owner-approved policy choices and implementation inferences, not
claims that OpenAI guarantees a task succeeds at a particular effort. Role names
alone do not prove complexity. A root/verifier with explicitly bounded low work
may use L. In the planner, worker execution is initially L, planning/unknown phase
M and high/critical complexity H; callers remain responsible for truthful task
classification, a clear plan and semantic quality. The planner chooses the least
supported setting at or above the task basis within model/environment bounds.
No silent downgrade or unrequested family fallback is allowed.

Before a proposal, record concrete quality criteria: required checks, reviewed
output/error tolerance, evidence/source identity and relevant user acceptance.
Every choice above L needs an explicit task-specific escalation reason. Record
why the lower effort is insufficient and how success will be checked. More tokens,
a longer analysis or a role label are not acceptance. Review outputs against the
same criteria after execution; reassess depth when phase/risk changes.

E and max additionally require referenced comparative evidence: lower baseline
full effort, higher quality score, both latency/cost observations and an explicit
accepted tradeoff. The validator checks complete finite metrics, positive quality
gain and a lower baseline. Its verified flag/evidence refs are **caller attestations**;
an authenticated adapter/reviewer must read their exact bound evidence and assess
the business benefit. This source adds no evaluator, benchmark runner, evidence
reader or automatic permission. Do not call those records remote proof. Prefer
one bounded comparison and downgrade future proposals when added depth no longer
helps. No universal quality score or latency/cost threshold is invented.

## Requested, assigned, proposed and actual

Keep separate: requested choice; assigned choice; PLANNED proposal; actual runtime
observation. Never fill actual from requested/assigned/config/default/catalog.
Missing/unbound metadata remains UNKNOWN. Runtime observations require source,
aware observation time and explicit session/turn IDs. These are trusted adapter
labels, not authentication; adapters bind and verify the intended actual turn.
Observed older/nonSol or unrecognised effort values remain faithfully reported.
Recognised actual max reports max; E reports only xhigh.

No module changes this current turn or model system instructions. Report the full
setting plus L/M/H/E where applicable, exact observed model/version and provenance;
if unavailable, explicitly UNKNOWN. A display family such as Sol is not a verified
exact model version. Reporting style itself belongs in private preferences.

## Implemented mechanism and compatibility boundary

model_routing.route_task is a pure, bounded proposal validator. It accepts current
catalog, environment constraints, requested/assigned/actual records, scoped model
agreement, escalation reason, quality criteria and comparative benefit. It returns
PLANNED, BLOCKED or PRESERVE_CONSTRAINT; no call/network/launch/persistence occurs.
Inputs are not mutated. Config defaults contain family selectors, not fixed version
IDs; config upgrade preserves owner values in memory and leaves stored bytes alone.
Legacy profile strings/delegate flags are inert for this planner and do not become
agreement, executed model or permission to delegate.

The unchanged CLI argument surface can emit BLOCKED when required context is
absent; complete proposals use the explicit Python API or a future supported
adapter. There is no CLI flag/MCP bridge that collects current quality/agreements,
no live catalog bridge into this proposal validator and no deployment enforcement.
No source/package test proves actual root/voice consumption. Review and
apply/adoption remain separate.

The separate [session launch adapter](SESSION_LAUNCH.md#inherited-model-admission-and-actual-startup)
performs bounded, same-connection `config/read` and `model/list` before creating
a thread with inherited settings. This narrow admission check does not implement
latest-family selection, choose an effort, collect routing agreements or apply a
proposal. A catalog candidate/default is provisional; actual startup metadata and
successful capability probes remain independent checks. A null/absent configured
provider is supported without an explicit override; preserve that input and its
presence separately from the required actual `thread/start.modelProvider`. The
same inherited connection must supply the actual identity before probes/work,
and any explicit configured provider must match it. Continuation retains that
actual identity. An omitted/null optional `nextCursor` is terminal; non-null
cursors are followed within the shared bounds. Missing actual provider binding,
incomplete pagination or unresolved aliases remain `UNKNOWN`. The adapter never
guesses a provider name, changes model/auth/policy settings or substitutes another
executable to pass.
