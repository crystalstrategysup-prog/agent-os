---
name: atlas
description: "Manage controlled development through parameterized standard procedures: connect the objective and specification, project-wide documentation, the matrix of all work, matrix history, actors, contracts, patches, and evidence of results. Use when starting or continuing project development, opening its Atlas contracts and roadmap, detecting or onboarding Atlas, coordinating agents, handing off engineering work, updating project records, or integrating Atlas into AgentOS. Do not create a full set of project reports for an ordinary question or brief consultation."
---

# Atlas

**Execution depth:** load [operating-modes.md](references/operating-modes.md)
to select MINIMAL or FULL project work; AGENTS only routes to Atlas.
Before any mutation, resolve and READ the owning project policy, writer and affected
source/contract context. For AgentOS public source read `docs/ATLAS_SOURCE_POLICY.md`
in the selected source root, or its exact installed resource; do not infer policy
loading from a path/hash or a missing private registry. A verified typed function is preferred to repeating
agent reasoning; its source remains canonical and its proof must be retained.


Continue a project from its objective and actual state. Leave the next agent a
short, verifiable path to the result: work → owner → change → acceptance.
Perform repeatable actions through standard procedures with explicit parameters.

Read [quickstart.md](references/quickstart.md) for daily work,
[modularity.md](references/modularity.md) for module/API/build/deployment boundaries,
and [operations.md](references/operations.md) for exact methods and parameters.
An existing WM-UI matrix uses [upstream-adapter.md](references/upstream-adapter.md):
one explicit binding and `refresh`, then a packet; the source keeps its writer.
Declare work/doc/module/contract/patch links in a pinned semantic catalog and
reuse earlier scoped results. Import alone does not require work checks again.

Registered projects use [workspace.md](references/workspace.md): `atlasctl start
PROJECT --work ID` loads context. The current writer records begin/dispatch and
progress through the typed `atlasctl work` method in the quickstart; it pins inputs
and publishes one checkpoint. Record research, document analysis and checks in
the assigned project task before a long operation or wait. Use `finish` for an
already saved source delta.
Use `atlasctl docs PROJECT --source-root PATH` per [document-sync.md](references/document-sync.md).
Signatures are in `scripts/WORKSPACE_OPERATIONS.json`; API cards use [catalogs.md](references/catalogs.md).
If absent from PATH, use the pinned command path without rediscovering transport. To open project contracts and the roadmap, handle `agentos atlas views PROJECT` in this session; do not self-forward. `ARTIFACTS_READY` means verified retained HTML/JSON, not `OPENED`. Confirm opening through the supported interface or deliver those files as downloads; a queued request is not opening evidence. See `workspace.md` for freshness and legacy routes.

## Detect Atlas before project development

A request to develop, resume or continue a project, including a plain-language
request such as "continue development of PROJECT", starts with an Atlas check.
Read the selected project's current instructions and exact registered binding;
check its local Atlas manifest or declared custom location. Use only the known
project root and registry. A missing CLI/registry is not proof that the project
has no Atlas, and an unreadable or inconsistent binding is UNKNOWN, not absent.

**Atlas exists:** read the binding and current writer, select the already assigned
work, and invoke its declared start/refresh-and-packet routine. For a registered
WM-UI project use `atlasctl start PROJECT --work ID`; for another native binding
use its documented `session-start` route. Record the actual beginning through the
current writer's work method, including research or checks before a code change.
If work is already underway, record present `progress` without backdating its
start. Continue the original task. Do not bootstrap a second matrix, reopen
unchanged accepted work or restart the session.

**Atlas is confirmed absent:** reuse an explicit prior choice for this project
and task scope. Otherwise offer exactly these three choices before Atlas writes:

1. **Create Atlas before development.** Establish the smallest truthful binding,
   initial inventory, writer and first work packet, then continue the task.
2. **Continue this task explicitly without Atlas.** Record that scoped choice in
   the existing task checkpoint; continue the authorized work and its applicable
   documentation/contract obligations. Do not initialize Atlas implicitly.
3. **Continue the task and start a separate temporary Atlas bootstrap session.**
   Keep the main task/writer. Assign one inventory/binding/history result with
   separate write scope and a return checkpoint. The main writer reviews and
   integrates it, then closes the temporary assignment. No permanent keeper,
   scheduler or parallel status owner is created.

Use the authorized native delegation/return route; the skill does not launch or
message sessions. Read-only questions need no onboarding. Detailed paths and
the temporary handoff are in [integration.md](references/integration.md).

## Select a standard procedure

For a historically pinned native natural entry, use the explicit
[source relocation](references/source-relocation.md) contract:
`agentos atlas source-relocate plan|apply|status|reconcile` with exact root,
writer, current authority and expected pins. Preserve historical logical
identity and separate retained bytes. Never retarget a published document ID or
waive `HISTORICAL_MEMBER_REWRITE`; the method grants no target authority.

Find the project binding in the current task or active project instructions.
Use the selected root, project manifest, and operation registry. Do not reselect
SSH, the connection method, or the method sequence when these are already fixed.

| Procedure | Purpose |
|---|---|
| `session-start` | Restore the objective, selected work, writer, criteria, evidence, and next step. |
| `finish-block` | Reconcile the result, changed artifacts, evidence, event, and remaining work for one block. |
| `integrate` | Deliver prepared deltas to the current writer and update the project view. |
| `reconcile` | Check the current local output after UNKNOWN; read an external operation through its declared adapter using its original ID. |
| `project-audit` | Check the completeness of the registered project and identify missing links and work. |

Invoke procedures through the single local CLI described in [data-contract.md](references/data-contract.md).
Use declared methods, parameters, preconditions, and effect boundaries.
If a method binding is missing, identify the exact gap; do not invent a new route.
A declarative adapter neither grants authority nor launches a host/runtime automatically.

After the create/temporary-bootstrap choice or explicit Atlas integration,
follow [integration.md](references/integration.md) within that selected scope.
When `.atlas` is absent, a direct binding uses `init` with the actual objective,
writer, authority and `native`/`projection` mode. INITIALIZED_PARTIAL is not complete.
For WM-UI, create UPSTREAM and call `refresh`, without prior `init`. Refresh an
existing projection before its packet. Reuse given authorization and keep its scope.

## Restore the relevant context

1. Read the objective, authorized scope, current writer, and selected work item with its criteria.
2. Obtain the linked packet; distinguish canonical docs, the normalized matrix
   projection, proposals, immutable snapshots, and primary evidence.
3. Check coverage: documents, objectives, modules, contracts, work areas, all work,
   and the history of all authoritative matrices must have exact inventory bindings.
4. Preserve truthful coverage for partial/unmapped/UNKNOWN information. Do not
   claim the whole project is documented from a few documents or a subset of steps.
5. Select a substantive step that advances the result or closes a specific gap.
   Preserve the accepted task and current writer.

## Record work before waiting

- Record the outcome, criteria, dependencies, and a bounded set of changes.
- Record an assigned work item's actual beginning or delegation immediately,
  including research, diagnosis, document analysis and checks. Use the existing
  leaf work ID and responsible actor; state what is being investigated and the
  next observable result. `start` alone writes no source work event. For work
  already underway, record present `progress --status doing`, without backdating.
- If no existing leaf covers the actual task, the current writer registers a
  bounded research/check item through its established source method. Do not use
  an unrelated accepted item to make the matrix look active. Ordinary questions
  and standalone context lookups retain the read-only path without onboarding.
- Before waiting after new start/dispatch/progress/result/blocker facts, the main
  writer calls `work` with an operation ID, work, phase, executor, note, next action
  and any prepared document changes. It pins inputs, saves the delta and refreshes
  once; no extra `finish` is needed. Exact flags/profile/recovery are in `workspace.md`.
- Keep the map and relevant documents current while waiting by integrating real
  returned deltas and continuing independent authorized work. An unchanged wait
  creates no event; reuse its operation rather than polling the whole project.
- Prepare material document/contract changes alongside the work. The method can
  commit declared prepared bytes; it does not write their meaning on the agent's
  behalf. Refresh/finish only projects saved sources and does not invent acceptance.
- Leave one delta: result, artifacts, evidence, remaining work, and the next responsible actor.
- Send changes to a shared file to its current writer. When a matrix already
  exists, update its normalized projection through the owner; do not create a
  parallel status table.
- Preserve old events and every received matrix version. Accompany a material
  record change with an event; do not record a no-op as new work or a fresh release.
- If a required contract is missing, create an exact, bounded work item to recover
  or create it with known inputs and criteria. Do not replace UNKNOWN with a guess.

Use [workflow.md](references/workflow.md) for responsibilities and transitions.
Take exact fields, formats, and machine limits from the data contract.

## Preserve the meaning of statuses

- Distinguish assigned responsibility, historical status, and verified activity.
  Refreshing does not extend evidence validity; stale DOING does not prove
  inactivity or release the writer. Recorded DOING remains visible after activity
  expires and is reachable through the recorded-work selection; the active-only
  filter requires fresh actor/work evidence. Use the empty-view recovery action
  to inspect recorded or all work when a restrictive filter finds no rows.
- Native session actions are not collected by context loading or browser reload.
  The writer records real progress; saved observations retain their timestamp
  and source. Searching an observation does not establish CURRENT activity.
- Accept work against its declared criteria and exact basis. A SOURCE criterion
  can complete a local SOURCE task. Establish installed/runtime/user acceptance
  within each respective scope.
- Show UNKNOWN explicitly. A hash, ACK, document heading, or test count does not
  prove unestablished behavior or establish the completeness of the project inventory.
- For a patch, identify its target, base SHA, and lifecycle. Keep ACCEPTED_UNAPPLIED
  unapplied; link APPLIED to the exact result and readback evidence.
- For unknown local output, call `run reconcile`. For an external effect, use exact
  operation readback through the declared adapter. A new ID, actor, or route does
  not by itself authorize repeating the effect.

## Limit maintenance costs

Refresh changed inputs and links after bootstrap. Repeat the inventory only for
a scope change or exact gap; a new session/view or unchanged blocker is not one.

Before repeating a check, identify a material changed input, condition, criterion,
new defect, applicable freshness requirement, or mandatory gate. Otherwise reuse
the earlier evidence with explicit applicability and its original date. Stop
checking when the specific risk is resolved.

Use [principles.md](references/principles.md) without presenting organizational rules as physical laws.

## Invoke one façade

Substitute the verified `atlas_tool` (this `scripts/atlas.py`), `atlas_project`,
`atlas_output`, and stable `atlas_work_id` from the current binding.

```bash
python3 -B "$atlas_tool" run session-start --root "$atlas_project" --project .atlas/project.json --work "$atlas_work_id"
python3 -B "$atlas_tool" run finish-block --root "$atlas_project" --project .atlas/project.json --output "$atlas_output"
python3 -B "$atlas_tool" run integrate --root "$atlas_project" --project .atlas/project.json --output "$atlas_output"
python3 -B "$atlas_tool" run reconcile --root "$atlas_project" --output "$atlas_output"
python3 -B "$atlas_tool" run project-audit --root "$atlas_project" --project .atlas/project.json
```

Before these core finish/integrate routines, the writer saves the source delta and
exact pins. The core performs one load/validation/CAS cycle of the selected output;
it does not change source/product/docs. Unless explicitly supplied, the release
ID is derived from content and the toolchain. NO_CHANGE creates no events/releases
and does not repeat product tests; a write flow may repair the verified current-view copy.

Use `methods` for the static registry, `history --output` for the entire retained
chain, and `diff --output --before --after` for two exact releases. Take exact
init, pins, impact, discover, coverage, and low-level commands from the operations
reference. `init` creates only a new control tree; `build`/`cycle` write the selected
output. Other core methods read data and write results to stdout. The declarative
Owner Hosts adapter is not executed by the core; the separate WM-UI importer
updates only its own projection.

On refusal, preserve the exact code and bounded scope; do not silently repair
existing pointers/history/locks. Preserve a refusal of an authorized browser
route; do not bypass it through another preview/server.

## Complete the handoff

Report the result, scope, exact artifacts, coverage, and next step. Do not claim
integration across all projects from one local PASS. Give the active session its
task, checkpoint, writer, and UNKNOWN items. Apply this cycle at the next begin,
dispatch or progress boundary, before waiting; do not defer it to final completion,
force a restart or repeat unchanged accepted checks.

## Копирование контекста работы

**Дополнение Copy/«Матрица работ» (18.10.2026).** В каждой строке две кнопки: «Копировать» записывает полный Markdown в буфер, а «↓ .md» сохраняет один полный Markdown companion с SHA256-манифестом для объёмных контекстов. При запрете Clipboard API открывается полный ручной fallback. Связи работ→контракты/модули выбираются только по точным ID и declared dependencies; общий нормативный документ не делает все его API контрактами этой работы. Недостающие связи остаются UNKNOWN с восстановлением у owning writer, а исходная приёмка сохраняет свой отдельный уровень доказательств. Верхние числовые эмодзи-счётчики — числа исходных шагов датированного снимка, не мониторинг live-активности и не новая приёмка.

В Atlas матрице кнопка «Копировать» для каждого шага формирует Markdown-пакет для пустой Codex/ChatGPT-сессии. Он включает сохранённое назначение, дерево, зависимости, статусы, реальных зарегистрированных участников, исходные существенные нормативные тексты и контракты, SHA, evidence, ограничения и процедуру продолжения. Срез не является live-проверкой или новым правом записи. Если кнопка показывает ручной диалог вместо «Скопировано», автоматическая запись в clipboard не удалась; скопируйте полное содержимое вручную. Перед изменением всегда заново проверить actual source, writer binding, lease и разрешённый scope; недостающие связи отмечены UNKNOWN.
