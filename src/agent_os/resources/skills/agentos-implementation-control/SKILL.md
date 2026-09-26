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
