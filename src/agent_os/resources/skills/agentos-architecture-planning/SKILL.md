---
name: agentos-architecture-planning
description: "Review the existing architecture, trust boundaries, contracts, and change plan."
---

# agentos-architecture-planning

Read-only architecture review may precede project entry. For a project audit or
substantial work with material unknowns, use temporary diagnostic level 0 under
**Project diagnostics** in `resources/docs/PROCESS.md`, or
`agentos workflow guidance --method project-diagnostics`. Preserve the 1–5 choice,
update the current dossier/plan within the owning writer's scope, and return after
findings and the next step are clear. Product changes still require their existing
entry and authority; diagnosis completion is not readiness or acceptance.

Before implementation, separate observations in code
and configuration from the desired state. Describe context, components, data,
interfaces, integrations, source/runtime boundaries, and owners. Choose the
smallest sufficient architecture; compare alternatives, compatibility, migration,
and rollback. Record the decision and its cost in an ADR.

New interfaces need schemas, versioning, and error semantics. Privileged actions
require target authority; a request to draw an architecture does not provide it.
Plan bounded stages with acceptance criteria, dependencies, and evidence. Leave
unresolved risks visible. Output: architecture, ADR, stage, and roadmap.

The installed `resources/docs/PROCESS.md` and README are normative; locate them with
`agentos resources`. Project gates apply to real changes. Reading requires no
intake or observation. Native hooks remain excluded and must not be enabled or
restored. Neither CLI output nor profile text grants external authority.
