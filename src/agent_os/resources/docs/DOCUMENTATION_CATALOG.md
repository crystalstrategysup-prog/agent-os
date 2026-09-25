# Каталог документарных слоёв

Это каталог возможных артефактов, не список пакетов, которые AgentOS устанавливает.
Выбирать по архитектуре и изменению; альтернативные форматы не дублировать без причины.
Базовый gate проверяет смысловые document IDs, reviewer выбирает реальный формат.
Один файл допустим для нескольких IDs, если его содержание действительно покрывает требования.

## 1. Продукт

Варианты: Vision, PRD, BRD, MRD, Roadmap, User Stories / Use Cases, Personas / JTBD, Acceptance Criteria, Glossary, FAQ.

Базовые IDs: dossier, requirements, roadmap, ux. Нужные дополнительные документы перечислить в контракте этапа и проверить отдельным check.

## 2. Аналитика

Варианты: SRS, FR, NFR, Business Rules, BPMN, Event Storming, Domain Model / Bounded Contexts, DFD.

Базовые IDs: requirements, architecture. Нужные дополнительные документы перечислить в контракте этапа и проверить отдельным check.

## 3. Архитектура

Варианты: C4, arc42, ADR, RFC / Design Doc / TDD, UML, Sequence / State / Activity, Structurizr DSL, Deployment / Integration diagrams, STRIDE / LINDDUN.

Базовые IDs: architecture, security. Нужные дополнительные документы перечислить в контракте этапа и проверить отдельным check.

## 4. API и контракты

Варианты: OpenAPI, AsyncAPI, GraphQL SDL, gRPC .proto / buf, RAML, API Blueprint, SOAP WSDL / WADL, JSON Schema, Avro / Protobuf, Postman / Insomnia, HAR, Webhooks, deprecation / style guides, Overlays / Spectral.

Базовые IDs: contracts, http-api, events. Нужные дополнительные документы перечислить в контракте этапа и проверить отдельным check.

## 5. Данные

Варианты: ERD, DBML, DDL comments, Dictionary / Catalog, Lineage, Master Data, migrations, dbt docs, retention / PII map.

Базовые IDs: data, privacy. Нужные дополнительные документы перечислить в контракте этапа и проверить отдельным check.

## 6. Код

Варианты: README, CONTRIBUTING, CODE_OF_CONDUCT, CHANGELOG, JSDoc / TSDoc, Javadoc, Doxygen, Sphinx, GoDoc, Rustdoc, XML-doc, docstrings, comments, fitness functions.

Базовые IDs: onboarding, quality. Нужные дополнительные документы перечислить в контракте этапа и проверить отдельным check.

## 7. Эксплуатация

Варианты: IaC, Helm values, CRD, Docker / compose, Runbook, SLO / SLI / error budget, on-call, postmortem, capacity, DR, backup / restore, topology, CI/CD, environments.

Базовые IDs: operations, incident, release. Нужные дополнительные документы перечислить в контракте этапа и проверить отдельным check.

## 8. Безопасность

Варианты: SECURITY, threat model, SBOM SPDX/CycloneDX, VEX, disclosure, privacy / DPIA, access matrix, audit spec, compliance mapping, pen-test, secrets policy.

Базовые IDs: security, privacy, safety. Нужные дополнительные документы перечислить в контракте этапа и проверить отдельным check.

## 9. Качество

Варианты: Test strategy/plan, cases/suites, BDD Gherkin, coverage, Pact contracts, performance/load, chaos, QA checklist, bug template.

Базовые IDs: quality. Нужные дополнительные документы перечислить в контракте этапа и проверить отдельным check.

## 10. Процесс

Варианты: SDLC, DoR/DoD, review, branching, release notes, SemVer, incident/RFC process, team charter/RACI, meetings/decision log.

Базовые IDs: stage, release, incident. Нужные дополнительные документы перечислить в контракте этапа и проверить отдельным check.

## 11. Знания

Варианты: Wiki, onboarding, handbook, glossary, Diátaxis tutorial/how-to/reference/explanation, cookbook, migration/troubleshooting/known issues/demo.

Базовые IDs: onboarding, operations. Нужные дополнительные документы перечислить в контракте этапа и проверить отдельным check.

## 12. Метадокументация

Варианты: Docs-as-code MkDocs/Docusaurus/Antora/Sphinx, navigation/style, versioning, CI/link checks, Mermaid/PlantUML/D2/Excalidraw, templates, ownership/CODEOWNERS.

Базовые IDs: quality, release, onboarding. Нужные дополнительные документы перечислить в контракте этапа и проверить отдельным check.

## Матрица выбора

Типы: general, backend, frontend, mobile, data-ml, platform, embedded, legacy. Допустимо несколько типов. Признаки: http-api, events, database, pii, public, deployment, ui, ml, external-send, safety-critical.

- `general`: dossier, quality, roadmap, stage.
- `backend`: architecture, contracts, dossier, quality, roadmap, security, stage.
- `frontend`: architecture, dossier, quality, requirements, roadmap, stage, ux.
- `mobile`: architecture, dossier, quality, release, requirements, roadmap, stage, ux.
- `data-ml`: data, dossier, model-card, quality, requirements, roadmap, stage.
- `platform`: architecture, contracts, dossier, onboarding, operations, quality, roadmap, security, stage.
- `embedded`: architecture, contracts, dossier, operations, quality, requirements, roadmap, stage.
- `legacy`: architecture, contracts, data, dossier, onboarding, operations, quality, requirements, roadmap, stage.

Для не-IT проекта general даёт минимальный досье/roadmap/stage/quality комплект.
Отсутствие feature database не повод создавать ERD, а отсутствие HTTP API — OpenAPI.
ML проект дополнительно раскрывает Model Card/Datasheet, данные/оценку/ограничения.
Правовые требования не выводятся по названию отрасли автоматически: фиксировать юрисдикцию,
фактическое основание и квалифицированную проверку. Пользовательская надстройка может хранить
дополнительные шаблоны, но не выключать обязательные базовые gate.
