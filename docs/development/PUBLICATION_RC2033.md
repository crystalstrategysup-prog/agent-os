# rc2033 source publication candidate

This branch makes the identified rc2033 public package source available in the canonical repository. It is a draft publication candidate, not an official release or a claim that the entire project has passed acceptance.

## Provenance and scope

- All 224 agent_os package files match the per-file hashes in .release/0.8.0rc2033-source.json.
- The identified distribution SHA-256 is 242fca71a7d08708ebc8dcb6fe6acfa8da0c3ba6cda0f5e27062f1657880bbff.
- Companion tools/tests came from the maintained public source tree and are not all proven to match the distribution revision. The source record describes this boundary.
- Contribution guidance and PR template are repository changes outside that frozen package. Existing installed packages and running clients do not automatically acquire this new guidance. Incorporating it into shipped resources requires a new version and its checks.

## Validation

- Public-tree validator: PASS; 224-file package identity: PASS. The complete staged whitespace check reports one existing blank line at EOF in frozen src/agent_os/interrupted_bridge.py:130. It is preserved to retain exact distribution bytes; no release qualification is inferred.
- Focused public validator, Atlas routing and foundation suites: 114 passed.
- Earlier bounded broad run stopped at five failures after 276 passes and ten passing subtests. Atlas routing and skill mirror findings from that run were corrected; the focused suite above verifies those changes.
- A later selected run before moving repository-only development documents produced 194 passes and two failures. The document mirror issue was corrected; the historical coordinator-index version expectation still differs.
- Remaining known qualification issues: two readable-view tests assert older stale-publication behavior; the coordinator index test expects rc2 although the frozen index identifies an older intermediate candidate; a fixture executable test was blocked with PermissionError by the local execution environment. No protection was bypassed.
- The complete suite has not passed for this assembled companion tree. Do not merge, tag or publish a release based only on the focused result.

## Review

Self-review covered the public-data boundary, exact package inventory, preserved root safety instructions, changed installer syntax, version checks and new contribution policy. No independent review is claimed. Release qualification is blocked pending matching companion tests and resolution of the named failures. Publishing a draft for review is the bounded delivery step; it does not certify new runtime behavior.
