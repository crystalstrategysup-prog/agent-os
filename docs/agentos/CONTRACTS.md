# AgentOS engineering interfaces and contracts

## Interfaces
The optional read-only interface is agentos project diagnose --root ROOT. It emits a versioned bounded report containing root identity, declared document hashes, task/Atlas state, findings and an actionable next step. It makes no file, process, network or target change. Existing project entry/READY/check/close and LITE routes retain their meanings.
The Atlas facade exposes the existing native implementation through an explicit native route, with the same arguments and effect boundaries. A global user-home option never silently selects an Atlas registry.

## Schemas
Project inspection uses agentos.project-diagnostics/v1. Findings have stable codes, severity, subject and remediation; missing, unreadable, stale, pending and verified states remain distinct. Output contains metadata and hashes, not document bodies or secrets. Exact limits and supported fields are documented with the implementation and tested with synthetic roots.
Existing project/task/turn, scoped-file-admission, refusal-recovery v1/v2/v3 and Atlas schemas remain compatible. New source/build provenance is additive and independently hash-bound; old install receipts remain readable under their existing verification rules.

## Compatibility
Preserve all installed scoped reader behavior while integrating main recovery v3. An update must not drop required installed state readers. Rollback preserves the external overlay and must not reset journals. A module inventory PASS states its actual coverage and never substitutes for whole-package or business acceptance.

## Errors
Unsafe or oversized input is not read; missing, stale and incomplete metadata produces advisory findings. An opened root exits 0 even when findings exist. Only inability to open the selected root safely, an unqualified platform or invalid arguments exits 2. Diagnosis is never an intake/READY prerequisite and does not block independent work. Reading an unregistered project is supported and reports missing bindings without initializing them. UNKNOWN side effects use the original operation readback; a new operation ID does not authorize a retry. A source patch or successful build never turns an unresolved production incident into fixed.
