# Active source stage — F17

Public and installed owner-Mac stable are 0.5.4; see STAGE-F17 for
separate publication and activation evidence. F12 added the
connection-scenario catalog and protocol; F14 published this source at `v0.5.1`
and verified its managed Mac installation. See [STAGE-F14](STAGE-F14.md) for the
separate publication and runtime receipts.
F15 adds a standard SSH and VNC tunnel scenario; see [STAGE-F15](STAGE-F15.md)
for its bounded public scope and separate release/installation proof.
See [STAGE-F12](STAGE-F12.md) for scope and local acceptance. Earlier F11
release and activation history remains in [STAGE-F11](STAGE-F11.md).
F09 no-hook direct-read behavior remains invariant.

F13 translates all human-facing public text to English while preserving stable
machine contracts and the external user overlay boundary. See [STAGE-F13](STAGE-F13.md).
F14 adds reusable work-continuity guidance, a versioned public release and a
verified managed Mac update. See [STAGE-F14](STAGE-F14.md).

# AgentOS foundation roadmap

Every product stage follows: dossier and roadmap read-back → current stage contract → implementation → checks and result record → dossier/roadmap/contract update. Intake chooses only relevant document layers; it does not replace these three project documents. A read-only R0 task keeps a short path.

| Stage | Dependency | Deliverable and acceptance | Current state |
| --- | --- | --- | --- |
| F01 — candidate reconciliation | Public `origin/main`, supplied handoff | Independent package audit, documented Foundation↔Overlay boundary, public/private file classification, exact changed-file plan | CLOSED; findings in STAGE-F01 |
| F02 — foundation and overlay | F01 accepted; joint F02/F03 contract | Clean install; one versioned user overlay; create-only import; backed-up migration; upgrade/rollback without lost user bytes | LOCAL_PASS on Darwin fixture; live target pending |
| F03 — documentation lifecycle | Joint F02/F03 contract | Mandatory project intake/entry, relevant doc selection, stage readiness, evidence-backed closeout and repeat-entry enforcement; R0 remains light | CLI/fixture PASS; native hook proof pending |
| F04 — interfaces and onboarding | F02–F03; STAGE-F04 | Machine-readable MCP input/output/version and affected CLI/config/data contracts; developer guide; package/site/release version and installation agree | LOCAL PASS; result in STAGE-F04; publication pending |
| F05 — verification and public release | F02–F04; STAGE-F05 | Mac install/upgrade/read-back, available Linux/Windows probes with honest limits, regression and security review, direct push/tag/release, published URL read-back | PUBLIC RELEASE PASS; website and live Mac target BLOCKED by host gates; result in STAGE-F05 |
| F06 — beta hardening | External review; STAGE-F06 | Atomic create-only overlay import, user schema compatibility before activation, immutable readiness baseline; new beta release | PUBLIC RELEASE PASS; result in STAGE-F06; CLI follow-up in F07 |
| F07 — standalone CLI turn transition | Independent beta.1 review; STAGE-F07 | Exact CLI-only next-turn receipt after checkpoint/close, native-hook provenance preserved; next immutable beta | PUBLIC RELEASE PASS; result in STAGE-F07; target gates still pending |
| F08 — optional external profiles | Owner 0 / 1 / N decision; STAGE-F08 | Versioned profile adapter, explicit conflict decisions, interview, packaged schema and public beta.4 | PUBLIC RELEASE PASS; 179 tests, wheel read-back; live Mac gate blocked |
| F12 — connection scenarios | Stable 0.5.0 public source; STAGE-F12 | Versioned index and scenario cards, read-only discovery, authoring and maintenance protocol, local schema/CLI/package checks | INCLUDED IN v0.5.1; cards remain guide_only |
| F13 — English public edition | F12 source candidate; STAGE-F13 | English docs, CLI text, catalog, templates, skills and setup scenarios with source/package parity | INCLUDED IN v0.5.1 |
| F14 — continuity and public release | F12/F13 source candidates; STAGE-F14 | Generic continuity guide/template, versioned English release, verified managed Mac update | RELEASE AND MAC READ-BACK PASS; fresh Codex session not tested |
| F15 — remote-device tunnels | v0.5.1 public catalog; STAGE-F15 | Fast, generic SSH/VNC connection scenario with proof layers and maintenance triggers; reviewed versioned release and managed Mac update | RELEASE AND MAC READ-BACK PASS; live device and fresh Codex session not tested |
| F15B — one-host field validation | v0.5.2 public card; STAGE-F15B | Reproducible exact-alias SSH/RFB probe, tested commands, honest desktop proof boundary, public patch and Mac read-back | TRANSPORT CHECKS PASS; viewer requirement deferred by owner in F15C; no release/update |
| F15C — defer desktop viewer | Owner scope amendment; STAGE-F15C | Active SSH/RFB scenario without Screen Sharing or viewer-login requirement | SCOPED AMENDMENT IMPLEMENTED; documentation/catalog only; release/update pending |
| F15D — stable 0.5.3 release | Reviewed F15B/F15C; STAGE-F15D | Rebuilt public artifacts, local verification, canonical main/tag/release and asset read-back | PUBLIC RELEASE AND ASSET READ-BACK PASS; installed stable 0.5.2 |
| F16 — private scenarios | F15 public scenario contract | User-owned scenarios in the external overlay, isolated from public IDs and distribution, with explicit trust and maintenance rules | PLANNED; bounded design in STAGE-F15; separate entry required |

| F17 — handoff discovery | Owner repair request; STAGE-F17 | Current guide/bootstrap, exact Mac routing, versioned 0.5.4 and managed update | PUBLIC RELEASE AND MAC READ-BACK PASS; fresh installed process verified |

## Stage dependencies and stop rules

F01 may inspect and test the candidate but must not publish its mixed ZIP. F02/F03 start only after their stage documents name precise write sets, contracts, failure paths and checks. F05 cannot claim Windows, native hook enforcement, PyPI or website repair from a Linux fixture or a local build. Private runtime replacement and fleet rollout are separate work with their existing authority gates.

## Closeout record

At the end of each stage, record source identity, actual commands/results, changed scope, unresolved risks and rollback anchor in the stage document. Update this roadmap's status only from that evidence. The next stage starts from these current documents rather than the earlier conversation.
