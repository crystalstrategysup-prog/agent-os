# Documentation layer catalog

This is a catalog of possible artifacts, not a list of packages that AgentOS installs. Choose by architecture and change; alternative formats do not duplicate without reason. The base gate checks the semantic document IDs, the reviewer selects the real format. A single file is acceptable for multiple IDs as long as its content does cover requirements.

## 1. Product

Options: Vision, PRD, BRD, MRD, Roadmap, User Stories / Use Cases, Personas / JTBD, Acceptance Criteria, Glossary, FAQ.

Basic IDs: dossier, requirements, roadmap, ux. The necessary additional documents are listed in the stage contract and checked by a separate check.

## 2. Analysis

Options: SRS, FR, NFR, Business Rules, BPMN, Event Storming, Domain Model/Bounded Contexts, DFD.

Basic IDs: requirements, architecture. The necessary additional documents are listed in the stage contract and checked by a separate check.

## 3. Architecture

Options: C4, arc42, ADR, RFC / Design Doc / TDD, UML, Sequence / State / Activity, Structurizr DSL, Deployment / Integration diagrams, STRIDE / LINDDUN.

Basic IDs: architecture, security. The necessary additional documents are listed in the stage contract and checked by a separate check.

## 4. APIs and contracts

Options: OpenAPI, AsyncAPI, GraphQL SDL, gRPC .proto / buf, RAML, API Blueprint, SOAP WSDL / WADL, JSON Schema, Avro / Protobuf, Postman / Insomnia, HAR, Webhooks, deprecation / style guides, Overlays / Spectral.

Basic IDs: contracts, http-api, events. The necessary additional documents are listed in the stage contract and checked by a separate check.

## 5. Data

Options: ERD, DBML, DDL comments, Dictionary / Catalog, Lineage, Master Data, migrations, dbt docs, retention / PII map.

Basic IDs: data, privacy. The necessary additional documents are listed in the stage contract and checked by a separate check.

## 6. Code documentation

Options: README, CONTRIBUTING, CODE OF CONDUCT, CHANGELOG, JSDoc / TSDoc, Javadoc, Doxygen, Sphinx, GoDoc, Rustdoc, XML-doc, docstrings, comments, fitness functions.

Basic IDs: onboarding, quality. The necessary additional documents are listed in the stage contract and checked by a separate check.

## 7. Operations

Options: IaC, Helm values, CRD, Docker / compose, Runbook, SLO / SLI / error budget, on-call, postmortem, capacity, DR, backup / restore, topology, CI / CD, environments.

Basic IDs: operations, incident, release. The necessary additional documents are listed in the stage contract and checked by a separate check.

## 8. Security

Options: SECURITY, threat model, SBOM SPDX/CycloneDX, VEX, disclosure, privacy/DPIA, access matrix, audit spec, compliance mapping, pen-test, secrets policy.

Basic IDs: security, privacy, safety. The necessary additional documents are listed in the stage contract and checked by a separate check.

## 9. Quality

Options: Test strategy/plan, cases/suites, BDD Gherkin, coverage, Pact contracts, performance/load, chaos, QA checklist, bug template.

Basic IDs: quality. The necessary additional documents are listed in the stage contract and checked by a separate check.

## 10. Process

Options: SDLC, DoR/DoD, review, branching, release notes, SemVer, incident/RFC process, team charter/RACI, meetings/decision log.

Basic IDs: stage, release, incident. The necessary additional documents are listed in the stage contract and checked by a separate check.

## 11. Knowledge

Options: Wiki, onboarding, handbook, glossary, Diátaxis tutorial/how-to/reference/explanation, cookbook, migration/troubleshooting/known issues/demo.

Basic IDs: onboarding, operations. The necessary additional documents are listed in the stage contract and checked by a separate check.

## 12. Documentation infrastructure

Options: Docs-as-code MkDocs/Docusaurus/Antora/Sphinx, navigation/style, versioning, CI/link checks, Mermaid/PlantUML/D2/Excalidraw, templates, ownership/CODEOWNERS.

Basic IDs: quality, release, onboarding. The necessary additional documents are listed in the stage contract and checked by a separate check.

## The selection matrix

Types: general, backend, frontend, mobile, data-ml, platform, embedded, legacy. Several types are allowed. Features: http-api, events, database, pii, public, deployment, ui, ml, external-send, safety-critical.

- `general`: dossier, quality, roadmap, stage.
- `backend`: architecture, contracts, dossier, quality, roadmap, security, stage.
- `frontend`: architecture, dossier, quality, requirements, roadmap, stage, ux.
- `mobile`: architecture, dossier, quality, release, requirements, roadmap, stage, ux.
- `data-ml`: data, dossier, model-card, quality, requirements, roadmap, stage.
- `platform`: architecture, contracts, dossier, onboarding, operations, quality, roadmap, security, stage.
- `embedded`: architecture, contracts, dossier, operations, quality, requirements, roadmap, stage.
- `legacy`: architecture, contracts, data, dossier, onboarding, operations, quality, requirements, roadmap, stage.

For a non-IT project, general provides a minimum dossier/roadmap/stage/quality set. Without a database, do not create an ERD merely to satisfy a checklist. Without an HTTP API, do not create OpenAPI merely to satisfy a checklist. An ML project may additionally need a model card or datasheet covering data, evaluation, and limitations. Legal requirements are not automatically derived by the name of the industry: fix jurisdiction, actual basis and qualified verification. A user overlay may store additional templates; it does not disable applicable base gates.
