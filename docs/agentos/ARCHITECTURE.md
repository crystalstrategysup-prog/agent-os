# AgentOS engineering architecture

## Context
Repeated discovery currently crosses source checkout, installed package, project metadata, Atlas and private knowledge. The composition boundary must make their identity and freshness explicit without assuming that an old manifest or a successful process proves current work.

## Components
| Component | State owner | Narrow responsibility |
| --- | --- | --- |
| project / turns / safeio | Selected project and user workflow | Documented admission, locks, source-bound checks and terminal evidence |
| scoped_admission | Existing selected task | Finite recoverable source transactions with exact preimages |
| refusal_recovery / bridge | Existing workflow and supported observer | Preserve workflow/native identity and reconcile exact interrupted operations |
| project_lite | Selected local project | Opt-in append-only source accounting; never READY or external authority |
| project_diagnostics | No mutable state | Read bounded declared project references, classify freshness/gaps and return evidence metadata |
| investigation | Caller-owned evidence | Exact input keys, justified repetition and timed evidence classification |
| Atlas core and workspace adapter | Existing project writer | Native source records or normalized owning-matrix projection, views and history |
| managed installer and release tools | Selected immutable core installation | Verify package/source identity, compatible readers, expected current and rollback |
| user overlay | User | Private host/project bindings and owner knowledge; never copied into public core |

## Trust boundaries
Diagnostics never executes document text, follows an undeclared root, repairs a lock or claims authority. Registered paths must be contained regular files with bounded reads. A pending transaction is an owned reconciliation requirement. An active-task pointer to CLOSED or CHECKPOINT history is not evidence of a live writer. External source/runtime verification remains separately recorded.

## Decisions
Reuse existing Atlas, investigation, LITE, release and safe I/O primitives. Add one read-only project diagnostic command and expose native Atlas through the existing facade. Keep registry selection explicit. Integrate main recovery v3 with scoped admission under regression tests, then make only reproduced improvements. Do not broaden into unreviewed sibling branches. Each discovered general defect becomes a core regression; domain-only knowledge stays with its project.
