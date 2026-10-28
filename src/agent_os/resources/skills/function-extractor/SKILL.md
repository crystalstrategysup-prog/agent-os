---
name: function-extractor
description: Freeze and replay a selected Python callable with bounded static discovery, exact source pins, deterministic fault fixtures and explicit evidence boundaries. Synthetic replay grants no live authority.
---

# Function Extractor

Read [references/execution-protocol.md](references/execution-protocol.md) before execution. This skill guides an agent using maintained tooling; it is not a self-patching daemon, runtime permission or provider certification. Historical receipts belong in source documentation, not reusable instructions.

## Own the original outcome

Before changing code, preserve the original task and observable acceptance conditions, source ref, actual skill/protocol hashes, environment and writer boundary. Separate internal milestones from the parent goal. Preserve known answers and prior failures. Component PASS never closes an unmet original outcome.

Classify each gap as ACTIONABLE_IN_SCOPE, REQUIRES_AUTHORITY, EXTERNAL_UNVERIFIABLE or OUT_OF_SCOPE. Record the observed fact, missing proof, cause/coverage/outcome dimension and next safe action. Execute authorized feasible corrections and return to original acceptance. Repeated failure without new evidence calls for a different hypothesis, not blind retry. Never retry an ambiguous external effect.


Respect the owner's named responsibility split: the designated maintainer owns shared skill changes and installation; the maintainer and/or executor run tests; the executor applies the accepted skill to the original practical task. Do not turn executor feedback into permission to rewrite shared guidance. In this owner workflow consult `docs/developer/function-extractor/OWNER_EXECUTION_REGULATION.md`. Prioritize one complete fresh run on the original incident before new demonstration scenarios or module extraction.

## Establish a safe executor

Verify actual host/user, current workspace, source ownership, approved launcher where required, installed compatible interpreter and harmless command success in that same executor. A model ACK, PID or started session proves neither tool execution nor task completion. Preserve inherited permissions, credentials and network settings. Do not install dependencies, alter protections or borrow live services to manufacture a test environment.

In the integrated AgentOS installation use `agentos fe`; packaged skill scripts resolve the embedded engine and reuse their own installed release interpreter. Environment helpers accept `--source-root PATH`; in an integrated installation they default to the current project directory, while a separate verified source checkout retains its repository root. The standalone FE CLI remains `scripts/fe` or `python -B -m tools.function_extractor`. For new source, discover/extract/verify before replay. Static discovery, graph and bundle inspection are separate from execution: local syscall-guarded replay requires Linux and libseccomp. macOS must not report a local replay as executed without that guard; use an existing separately qualified Linux execution environment when explicitly selected. Use supported bounded subprocess diagnostics for offline work; qualify container execution separately with exact image/dependency pins and existing target authority. No production imports/settings, credentials, network effects or Docker mutation are implied by this skill. A public dependency environment is not application/runtime acceptance.

## Select the causal business boundary before freezing code

For a reported incident, first verify its **current** state with a bounded read-only snapshot: incident identity, source/tenant scope, timestamps, sampled object status and actual progress. A stale alert or a healthy process does not prove the business invariant either recovered or failed. Do not export private payloads, identifiers, credentials or exception text merely to build a diagnostic sample.

Build a small **symptom → state writer → prerequisite/dependency → decision/side effect** chain from real source and record relationships. Write the expected invariant, observed contradiction, earliest unproved transition, owning function and exact source provenance. Compare a status/classifier function with at least one upstream writer and downstream consumer. Pick the earliest actionable *business decision or state-transition* function as the primary FE entry; a classifier can be a secondary control, never a substitute merely because it passes. If a dependency already terminalized while a dependent operation still retries, inspect both the terminal handler and retry/creation guards, including effects and deduplication. Do not infer a root cause from attempt counters alone.

Record a causal-selection receipt with candidates considered and rejected, static/dynamic gaps, evidence boundaries and missing proof. A completed static graph is only static; thousands of unresolved/dynamic edges are not runtime coverage. If the root transition cannot be safely executed, report `CAUSAL_PATH_NOT_PROVEN` and preserve the original incident OPEN. A green isolated classifier is `SYMPTOM_CLASSIFIER_QUALIFIED`, **not** `ROOT_CAUSE_RESOLVED`.

## Qualify the exact CLI route and counterfactuals

Before an expensive run, read the actual installed CLI help and qualify the source root, chosen entry, current commit, interpreter, dependency versions, sandbox and available runner. A `current` path that is a symlink may be refused: use only a verified immutable resolved root when that path is permitted, retain both paths and on-disk hashes, and never infer loaded runtime identity from Git objects. Use an exact `--source-ref` only when the frozen files match its Git objects; otherwise use separately declared file hashes. Preserve a source-rejection receipt instead of bypassing safety checks.

Pin the selected runner explicitly when its default is unsuitable. `container` requires an approved, qualified image; an unavailable image is a preflight blocker, not a defect in business code. For authorized offline work use the maintained guarded `subprocess` runner; the `offline`/`synthetic` mode label grants no permissions. Keep the recorder's actual event ceiling, selected module list and audit/seccomp guards. Verify the fixture schema and `--out` artifact shape (replay creates an evidence **directory** containing `trace.json`). `REFUSED`, invalid fixture, `TRACE_LIMIT` and missing observer evidence must never become PASS.

On a single frozen source, require at least one positive and one **independently derived counterfactual/negative** test at the selected causal boundary, plus relevant idempotency/no-retry and no-outbound checks. Prove the right object and tenant/source association, expected state transition, durable effects or deliberate fail-closed hold, and zero forbidden external actions. Two green classifier outputs alone do not demonstrate correct business recovery. Preserve the historic externally unknown outcome when receipts are absent.

## Maintainer handoff admission

After changing this skill, its protocol or maintained FE tooling, the designated maintainer **personally runs and reviews** a fresh source- and skill-pinned end-to-end qualification **before** installing or handing it to Codex. Record actual CLI argv, stdout/stderr and exit, exact suite/node membership, no undesired deselection, source stability, observer completeness, version/pickup hashes and relevant positive/negative cases. Use the same restrictions and test profile planned for the executor; an intentionally separate host-native fixture test is complementary evidence, not equivalent to a sandbox run. If any required native/sandbox test is blocked, mark the gate `NOT_READY` until an approved equivalent qualification exists; do not loosen a guard, change UID mappings or send an untested patch to Codex.

After passing, adopt exact reviewed bytes into a clean nonproduction commit, check both installed pickup paths and read back hashes, then perform one installed-route smoke test. The executor performs the owner's original practical task; the maintainer separately accepts that result. A source-only self-test or good Codex process exit never proves provider delivery, production recovery or an incident closure.

## Bind contracts to semantics

Read the actual request method, selectors, transformations, wrappers and side effects. Consult available pinned primary provider facts; distinguish a reviewed local machine adapter from an official schema and an observation from a normative contract. New provider coverage requires its own bounded normative review.

Map every mandatory prose requirement to an observable assertion before accepting a matrix. A coarse outcome such as RAISED does not prove an exact exception class. When the contract format cannot express a required property, add an independently derived assertion over complete execution evidence, or keep that property UNKNOWN. Distinguish JSON Schema numeric semantics from Python runtime types, including booleans, integral floats and subclasses; follow the selected contract rather than silently narrowing it to builtin types. State which values the fixture transport cannot represent.

A query's applicability must be proven before validation. For transformed input, validate the specified semantic value (for example decoded text after parsing), without rewriting the request or saving private transient values. Schema-only generation must not bypass applicability/projection. Unsupported syntax/selectors remain UNKNOWN rather than false PASS/FAIL; retain independent response checks.

Bind observations to exact source bytes AND the semantic AST operation: distinguish request serialization, request-body parsing and actual response decoding even when they share a callee. Requalify pins and runtime adapter/capture integration after source changes. A static pin or isolated helper test alone cannot prove an observation occurred.

Exercise real native wrappers and actual installed HTTP-stack behavior with deterministic synthetic boundaries. Preserve allowlisted typed cause evidence through wrappers, resource cleanup, attempt counts and receipt semantics. Do not parse private exception text or infer delivery/retry safety from a diagnostic family.

## Execute and preserve evidence

Use deterministic positive, negative, boundary and unsupported fixtures with expectations derived independently of faulty output. Keep STATIC_POSSIBLE, REAL_CODE execution, SIMULATED boundaries, observed provider behavior and accepted contracts distinct. Preserve raw first failure; changed source/contract/fixture/runtime requires a newly qualified bundle and fresh normal-CLI evidence. Saved trace revalidation and cache hits are not fresh execution.

Run extract/verify/contracts resolve/scenarios generate/matrix/replay/validate as applicable through existing commands, not a replacement engine. Keep managed contracts/defaults in tracked source with provenance and hashes; ignored personal evidence must never be a clean-checkout dependency. Use separate output/registry directories for changed evidence identities. UNKNOWN cannot enter a positive cache.

Record UTC and monotonic timing, argv, exits, suite membership, PASS/FAIL/SKIP/DESELECT and exact skip causes. Run the complete FE suite and all relevant native/stack tests; do not deselect failures or loosen production guards. A test-environment adjustment must be explicit, confined to synthetic fixtures and separately reviewed.

Before attributing a regression, pin the actual interpreter, installed dependency versions, source revision, exact suite membership and collection outcome. Separate missing-library failures from adapter/fixture mismatches, assertions and tool/application defects; keep unproven causes UNKNOWN. Compare totals only for matching scopes. An available authorized library environment may resolve a missing-dependency gap without installation, but does not establish that other failures disappear or grant application/runtime authority.

Review trace completeness, actual request/response witnesses, result and side effects separately. Missing response, unsupported coverage and unknown historical outcome are different gaps. Successful handling of an intentionally malformed response can PASS while its schema verdict FAILs. A known simulated cause does not reconstruct a historical cause or external receipt.


A trace-cap failure is a coverage failure even when the target returned correctly. Inspect where recording ends and which mandatory observer/cleanup facts are absent. A dropped-event counter after recording has stopped is not necessarily the total missing execution; differences of truncated counters do not measure work saved. Preserve the original fixture, selected modules, cap and raw failure. Prefer removing demonstrably redundant fixture bookkeeping or validation, with identical business-call sequence and semantic assertions, over suppressing capture or weakening guards. Any recording-contract change requires explicit review and a distinct evidence identity.

Use one small failing case before a patch. Wait for process termination and durable receipt plus source hashes before changing a tested source. Run focused checks including cleanup and observer assertions, then one full qualification per frozen source/contract/environment identity. Do not run duplicate full suites concurrently. A justified subsequent source change requires new evidence, not an absolute permanent prohibition on reruns. Record stage wall time, actual suite time and repetitions separately; derive checkpoints and runtime safeguards from measured comparable stages, not an arbitrary universal duration.

## Generalize and close honestly

Use successor guidance on a new non-provider-specific callable with a bounded faulty/missing contract, deterministic positive/negative cases and an available CLI reproducer. Report author-aware exercise separately from an objectively blind experiment. For blind evidence, seal a neutral task and separate expected checks first, then give a new independent worker only the neutral task. Do not reveal the prepared root cause, expected solution or checker file in its prompt. An uninstalled proposal is not installed-skill adoption proof.

Review the final diff and test/source scope independently of prior green logs. Include tracked/new source manifests, provenance, clean-checkout portability limits, supported environment and remaining original conditions. Use `scripts/fe-goal-check` with the retained original task, actual skill and source pins; this checks structure/hashes, not semantic acceptance or reviewer identity.

Update reusable guidance only with proven general lessons; avoid fixture answers, copied historical success claims or inflated provider coverage. If the installed skill or git metadata is outside permitted writes, prepare full exact replacement/patch, before/expected-after hashes, semantic review and a precise coordinator adoption/commit request. Never chmod, bypass security or silently call a proposal installed.

Keep parent OPEN when any mandatory adoption, independent review or blind qualification remains. Report source/offline acceptance separately from installed/runtime/live acceptance. No live sends, unknown POST replays, deploys or external reports without current explicit target authority.

For CLI details and bounded contracts consult the selected repository's `docs/developer/function-extractor/RUNBOOK.md`, `API.md` and `CONTRACT_V3.md`; verify their current bytes and applicability. Existing historical snapshots remain evidence with their original scope.
