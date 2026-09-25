# F07 — standalone CLI turn transition

Status: LOCAL PASS, PUBLICATION READY. Baseline is published `v0.5.0-beta.2`; the independent review of beta.1 identified a third defect that its intermediate summary had not captured. This stage has its own immutable beta ordinal.

## Reproduction and scope

A fresh CLI-only `enter(session=S, turn=T1)` writes a turn receipt. After `checkpoint`, `enter(session=S, turn=T2, resume_task=TASK)` raises `turn_binding_mismatch_reenter_correct_turn` before resume processing. A synthetic local reproduction confirmed the refusal. The CLI path needs an explicit new-turn transition; a native hook must continue to supply its own real turn and must reject a fabricated stale turn.

## Contract

- Add `project next-turn --root P --session S --from-turn T1 --turn T2 --task TASK` for the standalone CLI path. It may advance only an exact local receipt with `hook_seen=false`, the same session and root, the named task, and a task status of CHECKPOINT or CLOSED. A native-hook receipt or wrong/old session, turn, root or task fails without changing the receipt.
- The transition writes only the user-home turn receipt as `INTAKE_REQUIRED` with `hook_seen=false`; then a separate `project enter` with the exact new turn resumes a checkpointed task or starts a new one after close. It does not grant product-write readiness, reactivate checks, or claim native hook enforcement.
- Preserve provenance in `bind_turn`: a standalone receipt stays `hook_seen=false`; a real `UserPromptSubmit` remains true. Do not weaken `_pending` or the existing native turn mismatch checks.
- Document this sequence in process, contract, onboarding, install guide and machine-readable CLI contract. Bump all release identity surfaces to human `0.5.0-beta.3` and Python `0.5.0b3`, leaving previous tags/assets unchanged.

## Acceptance

Regression covers CLI-only checkpoint → next-turn → resume, CLOSED → new task, native-hook refusal, wrong previous turn/root/task, and preserved source/readiness reset. Full tests, Ruff, public-tree validator, Darwin offline install/update/rollback, Linux network-disabled fresh install, source/tag/asset hash and site source read-back are required before publishing.

## Limits

The live Mac and website deployment gates from F05 remain separate. This work does not authorize bypassing them or claim Windows/native hook target proof.

## Local result before publication

- `164` pytest cases, Ruff, the public-tree validator and temporary lifecycle demo passed. Tests cover exact standalone transition after checkpoint and close, preserved `hook_seen=false`, native-hook refusal, mismatched prior turn/task/root, and reset of readiness on resume.
- Built wheel `crystal_agent_os-0.5.0b3-py3-none-any.whl` with SHA-256 `75ebdbee2a9545d06407cdf084a914adf0a9f64694102192b3ee014d7f4e49aa`.
- A disposable Darwin arm64 Python 3.14 fixture passed offline install, update, rollback, reactivation and user-tree preservation. Linux arm64 Python 3.12 installed the wheel without network and passed version, init, doctor and packaged CLI-contract read-back.
- These are local checks. Public tag/release/asset and site source remain publication steps; target host gates remain unresolved.
