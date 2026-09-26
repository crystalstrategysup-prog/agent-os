# Compatibility and known limits

The source declares `0.5.3`; publication and installation require separate
readback. A concise `AGENTS.md` is routing advice, not a new lifecycle gate.
F01–F08 results describe their own source and wheel, not this change.

The opt-in SSH/RFB probe requires a POSIX host with OpenSSH stdio forwarding.
It was exercised on the owner Mac against one macOS SSH route.
Windows probe execution, VNC authentication and desktop-frame capture are not
implemented by this command. Stateless scenario discovery remains portable.

| Surface | Source status | Limit |
| --- | --- | --- |
| Python CLI and lifecycle | Implemented and tested locally | Python 3.11+; see exact candidate evidence |
| Codex integration | Managed AGENTS and nine skills; no-hook fixtures | Read back effective instructions in a fresh Mac session |
| Native hooks | Old CLI entrypoints retired as no-ops | Never enable or restore; no runtime enforcement claim |
| Managed installer | POSIX implementation retained | This source change does not install or switch `current` |
| Windows | Managed installer not implemented or verified | Python import alone does not prove full support |
| MCP stdio | Six bounded planning/status tools | No arbitrary write tools or required intake for reading |
| Config v1–v4 and v5 | Existing explicit migration | Task lifecycle rules apply to project changes |
| User overlay and profiles | Existing v1 schemas | Owner edits and selection hash refresh are separate |
| Legacy Session Hub | Existing fail-closed dispatch boundary | Task capability does not prove private-provider parity |

The direct read path intentionally no longer runs project questions or observe
for every prompt. Retired callbacks neither create a turn nor block Stop.
After checkpoint or close, bound CLI tasks transition through explicit
`next-turn`; old unbound prompt receipts do not block entry. Optional
observations remain separate from project state, and old receipts are retained.

Checks bind foundation version and executor module hash. After a core change,
old PASS receipts are stale for new acceptance: resume an unfinished stage,
re-establish READY, and rerun checks. CLOSED remains historical; read-only
`verify-closeout` can report stale evidence without reopening it.

Legacy config and models do not silently change. There is no native runtime
hook, global sandbox, distributed database, externally signed receipt, private
provider parity proof, or atomic install-plus-integrate transaction. A partial
owner/Mac profile export does not prove an active profile or live runtime.
Rollback to an older core must not run its old integration generator or restore
hook backups.
