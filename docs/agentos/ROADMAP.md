# AgentOS foundation roadmap

Every product stage follows: dossier and roadmap read-back → current stage contract → implementation → checks and result record → dossier/roadmap/contract update. Intake chooses only relevant document layers; it does not replace these three project documents. A read-only R0 task keeps a short path.

| Stage | Dependency | Deliverable and acceptance | Current state |
| --- | --- | --- | --- |
| F01 — candidate reconciliation | Public `origin/main`, supplied handoff | Independent package audit, documented Foundation↔Overlay boundary, public/private file classification, exact changed-file plan | CLOSED; findings in STAGE-F01 |
| F02 — foundation and overlay | F01 accepted; joint F02/F03 contract | Clean install; one versioned user overlay; create-only import; backed-up migration; upgrade/rollback without lost user bytes | LOCAL_PASS on Darwin fixture; live target pending |
| F03 — documentation lifecycle | Joint F02/F03 contract | Mandatory project intake/entry, relevant doc selection, stage readiness, evidence-backed closeout and repeat-entry enforcement; R0 remains light | CLI/fixture PASS; native hook proof pending |
| F04 — interfaces and onboarding | F02–F03; STAGE-F04 | Machine-readable MCP input/output/version and affected CLI/config/data contracts; developer guide; package/site/release version and installation agree | LOCAL PASS; result in STAGE-F04; publication pending |
| F05 — verification and public release | F02–F04; STAGE-F05 | Mac install/upgrade/read-back, available Linux/Windows probes with honest limits, regression and security review, direct push/tag/release, published URL read-back | DOCUMENTED BEFORE PUBLICATION |

## Stage dependencies and stop rules

F01 may inspect and test the candidate but must not publish its mixed ZIP. F02/F03 start only after their stage documents name precise write sets, contracts, failure paths and checks. F05 cannot claim Windows, native hook enforcement, PyPI or website repair from a Linux fixture or a local build. Private runtime replacement and fleet rollout are separate work with their existing authority gates.

## Closeout record

At the end of each stage, record source identity, actual commands/results, changed scope, unresolved risks and rollback anchor in the stage document. Update this roadmap's status only from that evidence. The next stage starts from these current documents rather than the earlier conversation.
