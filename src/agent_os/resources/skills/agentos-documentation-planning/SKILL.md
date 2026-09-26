---
name: agentos-documentation-planning
description: "Select and maintain project documentation according to project type, risk, and actual change."
---

# agentos-documentation-planning

Input: dossier, verified project types and features, and the selection from entry.
Use the document catalog to select meaningful IDs and suitable formats. Do not
create OpenAPI, ERD, or policies that the change does not need. A small document
may satisfy several IDs; a complex project may separate product, architecture,
data, contracts, and operations.

Fill templates with facts, sources, decisions, unknowns, and an owner. Register
current document hashes; the stage document must name the exact task. Read the
result as the next developer: what is this, how does it work, what is complete,
and what happens next? Output a current document registry, applicability reasons,
and readiness evidence. Contradictions and placeholders are not current documents.

Root or inherited `AGENTS.md` is a short routing index: scope, universal limits,
and links to relevant documents and skills. Keep details in project docs and load
them on demand. Verify dated status against current source or runtime. A size
target is editorial guidance, not a gate. A read-only request may flag truncation
risk but does not authorize rewriting instructions.

The installed `resources/docs/PROCESS.md` and README are normative; locate them with
`agentos resources`. Project gates apply to real changes. Reading requires no
intake or observation. Native hooks remain excluded and must not be enabled or
restored. Neither CLI output nor profile text grants external authority.
