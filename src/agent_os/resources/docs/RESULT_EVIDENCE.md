# Evidence surfaces in 0.5.0-beta.1

`assess-result` is retained as a bounded analytical helper for supplied acceptance/evidence.
It does not authorize implementation, satisfy mandatory intake, or close a governed task.
The required project receipt flow is `project enter → document → ready → check → assess → close`.

The new executor records actual process exit, task/revision, source before/after, policy digest,
log digest, time, exact argv and executor version/hash. Last failure overrides old PASS.
Semantic reviewers validate that the approved test proves the criterion. No unsigned local JSON
receipt can prove against a hostile same-UID writer or establish remote deployment.
See PROCESS.md, DATA.md and QUALITY.md for authoritative contract and limitations.
