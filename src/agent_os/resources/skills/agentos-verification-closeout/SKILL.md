---
name: agentos-verification-closeout
description: "Verify results and evidence, close documented work, or record an honest checkpoint."
---

# agentos-verification-closeout

Input: implemented stage and current READY. Update docs to match the result and
register changed content hashes. Run the stage-approved `project check` for each
check ID. Inspect actual return codes and logs, source/task/revision binding,
latest failures, unresolved findings, and out-of-scope changes. `assess` must pass.

The reviewer evaluates every acceptance criterion, test quality, documents,
limitations, and next step. Close through `project close` with a review JSON.
Local CLOSED is not live deployment. If a registered task lacks current evidence,
repeat the check or checkpoint with `complete=false`. Before task creation,
there is nothing to close; report the pre-entry failure directly. For CLOSED,
run read-only `project verify-closeout` without rewriting history. Report receipts,
closeout, and an updated roadmap; do not claim independent review when there was
only self-review.

The installed `resources/docs/PROCESS.md` and README are normative; locate them with
`agentos resources`. Project gates apply to real changes. Reading requires no
intake or observation. Native hooks remain excluded and must not be enabled or
restored. Neither CLI output nor profile text grants external authority.
