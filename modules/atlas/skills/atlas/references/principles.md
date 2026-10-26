# Principles of controlled work

Use these principles as engineering decision rules. Do not present them as
universal physical laws or mathematical proofs. Assess their usefulness through
observable results, resilience of the work, and maintenance costs.

## Define relationships and conditions for the result first

Describe why the work is being done, the observable result needed, and the
conditions that make it possible. Link work to the state owner, inputs,
dependencies, contract, and acceptance criterion. Name the unknown that affects
the next step; do not replace it with similar names or general assumptions.

Before acting, answer: what will become functional or established afterward,
and which decision depends on it? Use this for useful reading, checking, and
implementation without a separate report for every tool step.

For example, changing a response field requires finding its consumers and the
agreement on default/null semantics. A matching endpoint name does not establish
behavioral compatibility. Explicit links direct the check to the relevant area.

## Match control to maintenance cost

Choose the smallest record sufficient for the next participant. Preserve sources
and material decisions; use a derived view to eliminate manual duplication of
the same statuses.

Strengthen controls for changes to a contract, state, responsibility, or an
irreversible consequence. Use a short cycle for a reversible local edit.
Independent review, a full suite, and a separate gate must address a specific
risk or requirement.

Fix repeatable actions as named procedures with parameters. Once configured,
use the prepared method sequence. Change it when conditions change; do not
spend each session reselecting the connection and identical order of actions.

Repeat a check when there is reason to expect a different material result.
With unchanged inputs/conditions, reuse existing evidence with its original
qualification. A new report date creates no knowledge. Stop maintenance when
the result and next step are clear.

## Assess resilience through consequences

Work is controlled when correct ownership and a clear record of remaining work
survive a failure, repeat delivery, change of actor, or lost response. Check
these properties with specific scenarios when they are relevant to the task.

Preserve stable IDs, one writer for a shared resource, and original events.
After UNKNOWN, reconcile the same operation and its consequences. Do not obtain
"success" by renaming an attempt, hiding uncertainty, or moving a result into a
stronger scope of acceptance.

For example, a lost response after a write means UNKNOWN for the caller, even
if the write may have persisted. A qualified readback of the same identity is
needed. A successful HTML build supports its own artifact; other consequences
require their own evidence.

## Change direction while preserving history

When a new fact arrives or the objective changes, review remaining work and
dependencies. Record the reason, changed scope, inapplicable assumptions, and
new outcome. Preserve previous decisions, every received matrix, and evidence
with its scope of validity.

Distinguish a decision error, a change of inputs, and an ordinary next stage:
they require different actions. Removing one blocker does not satisfy independent
criteria; an open blocker does not cancel useful authorized work in another area.

For example, an accepted source proposal may require a different runtime adapter
after the actual interface is checked. Preserve proposal acceptance as historical,
open a bounded work item, and link the contract change. Do not erase the previous
result or present it as evidence for the new composition.

Assess project completeness through exact inventory bindings and explicitly open
gaps. Preserve the distinction between the complete history of all matrices and
an available partial archive. Do not reconstruct an unavailable earlier version
as a document that actually existed.

## Apply the principles through Atlas

At a substantive checkpoint, check: **why this work; which conditions for the
result are established; what supports its consequences; what the next responsible
actor does**. Record the answers in the existing work record, links, and evidence.
Use the standard procedure for the repeatable part. Do not create separate
philosophical reports.
