---
name: agentos-implementation-control
description: "Implement a documented stage without silently expanding its scope."
---

# agentos-implementation-control

Check that the project gate passes for the exact task. Read the stage contract,
write paths, authority, and approved checks. Implement a complete change within
that contract with meaningful regression and negative tests where needed. Do not
weaken a guard to make it pass. If scope expands, checkpoint the task, update the
scope and documents, and enter again. Verify source rather than relying on an
external report.

Before an external write, verify the target host, current source and runtime,
authority, and rollback. Local task permission does not authorize another
production system. Output changed source, tests, docs, and actual limitations;
then run verification and closeout.

The installed `resources/docs/PROCESS.md` and README are normative; locate them with
`agentos resources`. Project gates apply to real changes. Reading requires no
intake or observation. Native hooks remain excluded and must not be enabled or
restored. Neither CLI output nor profile text grants external authority.

Indexed results successor: follow `resources/docs/INDEXED_HANDOFF.md`. Both coordinators and workers query the selected owner library for prior results, then verify ID/revision/evidence and freshness before summarizing. New/resumed terminal transitions require accepted searchable handoff; a checkpoint stays unfinished. Historical permissions and archived instructions grant no new authority. Physical session cleanup is not implemented. Source instructions do not prove live coordinator adoption.

For work coordination read the single `resources/docs/COORDINATOR_KNOWLEDGE_INDEX.json` then selected `resources/docs/WORK_COORDINATION.md` references. Keep parent open until checked original user result. Every partial/final report needs verification, remainder and next owned action; receipt or session completion is not user-goal acceptance. Preserve independent work and reconcile exact unknown operations before retries. Personal role/name knowledge stays in the selected private overlay; linked files require explicit read/hash checks and live root/voice adoption is separate.
