# Crystal Microscope

## Purpose and place in AgentOS

Crystal Microscope connects a system's structure, the path of an actual result,
and the cost of producing it. Use it to understand an existing project, trace a
discrepancy, compare a mechanism, or explain a consequential research result.
**Lab** names the isolated experimental stand, not another development level.
The common Solution integrity laws and the bounded Crystal microscope section
of verified current PROCESS remain authoritative; load their actual body with
`agentos workflow guidance --method crystal-microscope`. This guide
explains their application; it does not replace project contracts or approval.

The method supports every project and saved development level. At level 1,
preserve a short map of the connected modular whole, useful debug and the error
journal, then zoom into the selected problem or risk. Level 3 adds the checks
needed for the connected increment; level 5 broadens immediate coverage where
the agreed task requires it. None requires cataloguing every library function
before building the first working whole. Diagnostic level 0 can use this map to
refresh a dossier, then returns to the retained 1–5 choice. Loading the method
does not enter level 0, change the saved level, or start instrumentation.

## 1. Fix the question and the snapshot

Restore the original objective, accepted partial results, current writer,
selected level/scope, target environment and authority. State the question as a
decision: which boundary loses the response, which resource explains the delay,
which transformation changes the quantity, or which alternative preserves the
contract at a justified cost. For new work, describe the intended useful chain;
an invented malfunction is unnecessary.

Identify the actual source revision and deployed build, relevant dependency
versions, configuration, inputs and scenario. A repository checkout is not proof
that its code is loaded. Tie runtime evidence to the executable/build identity,
process start and observation interval when available. A PID alone can be reused.
Record missing identities as UNKNOWN and narrow claims accordingly. Keep private
paths, credentials, captured payloads and project evidence in the owning project;
reusable public guidance contains only generic or synthetic examples.

Use existing records. One compact checkpoint records the question, baseline,
current evidence, candidate, accepted result, material remaining gap and next
step. A new microscope does not require a second plan, database of permissions,
full report or archive for every experiment.

## 2. Keep three connected views

| View | Contains | Does not establish by itself |
| --- | --- | --- |
| Structure | Modules, services, dependencies, interfaces, state and ownership | That a path ran or a particular binary implements the inspected source |
| Execution | Observed events, messages, tasks, spans, calls, transitions and results | That correlation proves a cause or that the unobserved paths work |
| Cost | Explicitly scoped time, resource and work measurements | That a local saving improves the user scenario or changes production |

A containment tree is a navigation aid. Keep a separate typed graph for calls,
messages, data flow, buffer ownership, queue/wait dependencies, state transitions,
recovery and correlation. Asynchronous work, fan-in, retries, callbacks, shared
buffers and cycles cannot be faithfully reduced to one parent-child call tree.
Distinguish a source-declared relation from an observed relation and a hypothesis.

Use stable local IDs and references. Every consequential assertion should lead
to its source or evidence, with revision, scenario and limits. Evidence links
must resolve within the declared package or explicitly identify an external
source. A path or hash is an identity check, not proof of the content's truth.

## 3. Zoom as far as the question requires

| Scale | Questions to resolve |
| --- | --- |
| User result | What action, expected content, timing, error or recovery matters? |
| Deployment and trust | Which client, service, process and permission boundary actually handles it? |
| Module contract | What enters, changes, leaves and persists; who owns the data and failure? |
| Runtime path | Which request/task/queue/lock/retry executes or waits, and in which order? |
| Code | Which file, function, method, call site and branch implements the boundary? |
| Dependency | Which loaded package/version/build and its implementation are involved? |
| OS and resources | Which syscall, scheduling interval, allocation, mapping or I/O is relevant? |
| Hardware | Which supported, attributable event explains the specific CPU or memory question? |

For a selected node, record inputs, output and units; transformations and
invariants; state transitions; data ownership and lifetime; errors, cancellation,
timeouts, retry/idempotency, concurrency and recovery where relevant. Describe
only applicable contracts, and name gaps instead of filling them with prose.
HTTP OpenAPI, message schemas, ABI, CLI, in-process signatures and file formats
are different interfaces. Do not invent an HTTP/Swagger requirement for a module
that has no HTTP API.

Anchor source to a revision and symbol/signature plus a useful code range.
Follow the method actually imported or loaded, including wrappers, generated
code, foreign-function boundaries and runtime dispatch when they matter. Do not
substitute a similarly named library function. Record source/licensing and
symbol limitations. A closed dependency remains a bounded black box: inspect
its documented contract and allowed input/output observations; never invent its
internal functions or claim an unattainable complete trace.

Expand branches because an observation, material unknown or acceptance criterion
requires them. Keep the current path back to the user result visible. A thousand
nodes do not establish completeness; report coverage against a declared scenario
and component inventory, with unexplored boundaries and their consequence.

## 4. Classify evidence and time correctly

Use separate classifications for intended/documented, source-verified,
runtime-observed, experiment-supported, hypothesis and UNKNOWN. The portable
format uses `declared`, `source`, `runtime`, `experiment`, `hypothesis`, `unknown`.
The labels do not certify the claims. Do not upgrade source inspection to runtime
proof, a sample to all executions, or one successful case to general correctness.

Each numeric measurement or estimate needs a passport:

- Scenario, useful work, run, revision/build and environment.
- Definition, units, collector/derivation and primary evidence.
- Interval and clock domain; inclusive/exclusive scope and overlapping work.
- Population, sample selection, count and aggregation, or explicit N/A reason.
- Collection overhead, dropped/unattributed events, exclusions and uncertainty.
- Limits on the conclusion and the next material unknown.

UNKNOWN is null with a reason; zero is a value only when actually established.
Approximate, derived, sampled and directly counted values must be distinguishable.
Do not add inclusive parent and child times, sum concurrent intervals as elapsed
time, infer a latency percentile from an unspecified population, or compare
different work volumes without a justified denominator. Use monotonic clocks for
local durations; preserve synchronization uncertainty across machines.

Keep wall time, on-CPU time, runnable waiting, blocking, queues, network and disk
waiting separate. A long blocking read need not consume that much CPU. Keep
cumulative allocations, live heap, retained objects, virtual mappings, RSS,
shared/private pages and physical footprint separate. Zero allocations does not
mean zero copying; logical copies do not equal physical RAM traffic. Record the
collector's actual definitions rather than treating related metrics as synonyms.

A disassembly shows compiled instructions; a hardware counter counts events in
its declared scope; a sampled profile estimates where execution occurred. None
automatically provides an exhaustive ordered trace of every instruction. Use
[Observability](CRYSTAL_MICROSCOPE_OBSERVABILITY.md) before collecting new data.

## 5. Find and change the mechanism

Locate the last correct state and first incorrect state. Restore the fixed
conditions and independent expected result. Form a hypothesis with a prediction
that could fail: what should change if the proposed mechanism is absent or
altered? Explain why the candidate affects that mechanism. Follow dependencies
only as far as the observed discrepancy requires.

Keep a baseline A, an optional reference B, and candidate C under comparable
inputs, configuration and useful work. A reference implementation is evidence,
not an unquestioned oracle. Compare contracts before code or speed. Preserve
payload/result, ordering, error meaning, authentication, data protection,
ownership, cancellation, concurrency, backpressure, retry and recovery as relevant.
An implementation that returns sooner by dropping the reply is not faster at
the same task. A synthetic test is useful when its expected outcome is justified
independently of the function under test.

Change one hypothesis at a time when practical. A mechanism can require several
coupled edits; explain their relationship and retain the baseline. Use a relevant
negative/control case and inspect material regressions. A few noisy runs support
a limited observation, not a stable performance winner. Explain workload and
environment differences, warm/cold state, instrumentation overhead and sample
limits. Do not impose arbitrary run counts, minute budgets or a benchmark suite
unrelated to the remaining risk.

Verify the nearest meaningful parent path and then the agreed user criterion.
Lower allocations can be an accepted allocation improvement even if elapsed
time does not improve; name the benefit precisely. Quantify material tradeoffs.
Separate mitigation, cause correction and a proposed optimization. Creating a
custom library, algorithm or protocol is justified by a demonstrated contract
gap or useful tradeoff, not by a preference for rewriting.

## 6. Apply the same microscope to research and forecasting

Map source → observation → cleaning/alignment → feature/transformation → model
or decision rule → output → user interpretation. Record dataset vintage,
revisions, units, timezone, missing values, model/configuration and assumptions.
For time-dependent decisions preserve event occurrence, publication, ingestion
and decision-availability times separately. Later corrected data cannot silently
replace what was available at the decision. A retrospective annotation is not a
feature that an online forecast could have used.

Separate observed association, an explanatory hypothesis, an evaluated forecast
and a causal claim. A news item near a price movement does not establish the
cause. Check leakage, selection, overlapping/dependent examples, baselines and
evaluation boundaries proportionately to the actual conclusion. Do not quietly
change the period, costs, sample or success criterion to improve a result.

Name the actual forecast target, horizon, baseline and supplied features.
The presence of a publication is not an analysis of its contents or expectations.
Keep accuracy, probability calibration and realized return as distinct claims.
Preserve the unit of observation, temporal split, dependent/overlapping cases,
model-selection history and untouched evaluation boundary. Do not learn
preprocessing or choose the model on the declared final test data; see the
[scikit-learn leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).
Additional candidates and repeated significance decisions require an explicit
evaluation plan rather than reusing the same apparent confirmation indefinitely.

Make the result legible to its human reader. A chart marker should reveal a
plain-language title, event content or faithful short summary, source link,
publication time/timezone, actual event time when known, and why it is shown.
Differentiate original source, later interpretation and missing/unavailable text.
Expose the relevant quote only within permitted quotation limits; prefer a
summary and link to the full item. If a marker cannot be opened or understood,
record that as a user-interface gap even when its data pipeline is correct.
Use keyboard-accessible details and a list/table alternative where relevant.
When several events share a candle, interval or visual marker, retain every
event's stable identity and make all of them reachable. Show that grouping took
place; a last-write-wins map must not silently substitute one news item for another.
State whether marker placement uses publication, occurrence or system-observation
time. Explain an absent source without silently weakening URL safety checks.

Explain acronyms, axes, units, uncertainty and the meaning of visual encodings.
Do not force a person to decode internal IDs. Preserve technical provenance in
expandable details. Test at least one actual navigation from an observed result
to the item and source that support it; a screenshot of a dot does not prove that
the underlying information is accessible. Rendering a plausible story does not
validate the forecast.

## 7. Keep the instrument faithful and maintainable

Use a versioned canonical data model and generate views/exports from it. Retain
unknown extension fields, raw evidence references, contracts, explicit zeros,
UNKNOWN reasons and experimental variants. Validate references and identities.
Do not silently replace a richer profile with an older profile sharing its ID.
Show differences, require explicit replacement and retain a recoverable previous
state. Validate a batch before changing any of its members.

Verify canonical data → view → export → import with meaningful roundtrip checks.
An archive that reproduces its viewer establishes packaging, not the experiments.
Mark measurements stale for changed binaries, inputs or environments instead of
silently carrying their authority to new code. Reuse unchanged evidence by its
scope. Document the actual limits of the renderer and refuse overflow rather than
silently truncating the project.

The supplied portable `crystal-microscope` skill includes a standard-library
validator and offline viewer for `crystal-microscope/v1`. It accepts explicit
data, preserves original JSON bytes for export, and runs no profiler or source
code. Its validation result explicitly leaves `claims_verified: false`.
Its installed `references/profile-contract.md` defines structural checks and
limits. Existing project-specific viewers can keep
their richer interfaces; adoption need not force a disruptive format migration.

## 8. Finish the scoped work and continue

Stop the investigation when the question is answered sufficiently for the next
authorized decision: the boundary, mechanism, effect, relevant disproof check and
material remaining conditions are clear. A blocked observation can be a useful
diagnostic result if its limits and next action are explicit. Do not wait for
absolute knowledge before continuing an already sufficient connected increment.

Track distinct states: behavior checked, cost measured, mechanism supported,
alternative compared, user effect verified, change prepared, installed, and
observed in the target. These are independent facts, not a decorative progress
percentage. Preserve accepted subresults and concrete residuals. Product
completion needs agreed user outcomes, recovery and resource/quality targets
with explained tradeoffs; an unbounded claim of absolute optimality is not a
finite acceptance criterion.

Delegate independent bounded branches with shared baselines and separate write
ownership. The coordinator integrates evidence and checks the end-to-end result;
subagent count, ACK and hashes do not prove usefulness or adoption. Keep internal
steps in the current journal, send owner updates for meaningful results or real
decisions, and package the full evidence when transfer, recovery or release needs
it. Failed optional notification does not stop the next authorized step.
