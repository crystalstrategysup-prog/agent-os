# Developer onboarding

Start with the current project's or parent directory's short `AGENTS.md`.
Follow only links relevant to the task. Detailed history and architecture
belong in project docs; owner and host knowledge belongs in the external
overlay. If client truncation is suspected, inspect effective instructions and
propose a separate index change. Length is editorial advice, never an intake
gate. A read-only request does not authorize rewriting instructions.

For a question, search, read-only audit, or API discovery, use existing read
authority and answer directly. Do not create a project task, observation, or
profile interview solely for that reading.

For a real change, read the dossier, roadmap, current stage and last result,
then affected architecture and contracts. Survey an undocumented project
read-only before creating docs; do not scaffold over unknown structure. Reuse
known answers, enter with current authority, and ask only material unknowns.
Same-scope continuation uses `questions --resume-task` and `enter --resume-task
--reuse-answers` with fresh authority. See `PROCESS.md` for exact gates.

Register required docs, reach READY, make approved writes, run exact checks,
update docs, then assess and close or checkpoint honestly. READY does not grant
external rights. A trivial always-true check is not semantic verification.
`tools/demo_lifecycle.py` is a temporary-directory example, not live proof.
After close, `verify-closeout` assesses whether evidence is still current.

Profiles are optional and outside core. Load only relevant verified entries;
missing or stale profiles do not block unrelated reads, but stale host facts
cannot support action. Do not preload full history or secrets. Project task
records stay in their project and are excluded from public exports.

The owner defines outcome and authority; a coordinator maintains scope and
stage; an implementer changes source; a reviewer judges meaning and evidence;
a target operator confirms live effects. Disclose self-review rather than
calling it independent acceptance.

Integration manages AGENTS and namespaced skills without native hooks. Verify
the exact interpreter and resources and read back effective instructions in a
fresh session. Conflicting owner or project instructions need separate review;
partial exports do not authorize broad rewrites of client auth, model, or
security configuration.

Common recovery: fill and register draft or stale docs; re-enter after changed
scope; rerun stale approved checks; revert unintended writes or agree a new
stage; inspect a bound-turn mismatch before explicit checkpoint/next-turn; and
report pre-entry failures directly without fake closeout. Never remove a lock
blindly.

For current handoff lookup, follow [HANDOFF_DISCOVERY](HANDOFF_DISCOVERY.md).
