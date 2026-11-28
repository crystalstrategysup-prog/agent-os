# Process: direct reading, documented changes

Read the selected source's `pyproject.toml` or installed package metadata for the
package version, and the selected release manifest for release identity. Version
metadata does not establish publication or host adoption. RC-labelled sections
below are retained historical records, not current installation or publication
claims.


## Historical indexed handoff successor0.7.0rc1

Every new/resumed mutable entry requires an accepted library handoff before CLOSED/CHECKPOINT. Checkpoints record unfinished work; legacy closed history is preserved. See [indexed handoff](INDEXED_HANDOFF.md).

This describes the candidate `0.8.0rc2` foundation. Native AgentOS hooks are excluded: do not
create, enable, trust again, or restore them during rollback. Older F01–F08
stages are historical evidence, not permission to reintroduce prompt interception
or a Stop hook.

## 1. Classify the action before registering a task

Answer ordinary questions, search, perform read-only audits, and discover
available APIs directly under existing read authority. These requests require no
`init`, `questions`, `enter`, `observe`, answers file, active profile, or closeout.
An unregistered working directory is acceptable.

An inherited `AGENTS.md` is a short router: scope, universal limits, and links to
relevant documents or skills. Read detailed architecture, operations, and dated
history on demand. If a file is truncated, report the risk and propose a separate
index change; a read-only request does not authorize rewriting instructions. A
file size target is editorial guidance, never a Stop gate or reason to refuse a
normal question. Creating a requested report file is not itself a product change;
changing source, configuration, or runtime is a product change even when called
an audit.

The optional `workflow route --kind audit` returns `FAST_PATH` without reading or
writing user data. `--kind project-change` or `--effect local-project-write`
returns `DOCUMENTATION_FIRST`. Effects such as `deploy`, `external-send`,
`production-write`, `runtime-write`, `db-write`, `credentials`, and `destructive`
return `BLOCKED` with the category of authority needed. This classifies the
declared effect. It neither interprets natural language nor proves authorization.
Even this optional routing command is not a prerequisite for a read-only answer.
Access to another person's data still needs its own authority.

## 2. Prepare a real change

Read the README, dossier, roadmap, latest stage and result, architecture, and
contracts for the affected components. Examine an unknown existing project
read-only before scaffolding. Reuse verified facts from current documents and
the owner's instruction; ask only about material unknowns. Load profiles only
when their verified owner or host context matters. A missing or stale selection
does not block unrelated reading, and dated host claims must not be used as live
facts without revalidation.

Prepare the complete plan for the current level and the declared next stage.
The project-level plan covers the route to the final result; module and
microprocess details are expanded when that level is selected. Start with a
connected working stand, then deepen its parts under **Project development**
below. Documentation and readiness describe the current level and stage; an
early stage may deliberately deliver a scaffold with explicit stubs.

When project metadata is absent, `project init --root P --name N --type TYPE
--context context.json` creates `.agentos/project.json` and draft docs. The
context supplies `purpose`, `current_state`, `boundaries`, and `constraints`.
Then use the explicit workflow session and turn:

```sh
agentos project questions --root P --answers answers.json
agentos project enter --root P --session S --turn T --answers answers.json
```

S and T are stable identifiers chosen for the CLI workflow, not simulated native
client events. Use client identifiers only when actually known. Context, answers,
and documents may be prepared before READY; that does not permit product writes.
JSON context, answers, and review inputs support `-` for stdin:

```sh
cat answers.json | agentos project enter --root P --session S --turn T --answers -
```

Stdin is limited to 4 MiB, must contain an object, and rejects duplicate keys.
Normal input paths must be regular non-symlink files; `/dev/stdin` does not bypass
that rule.

## 3. Continue without repeating known questions

```sh
agentos project questions --root P --resume-task TASK
agentos project enter --root P --session S --turn T --resume-task TASK \
  --reuse-answers --answers current-authority.json
```

`current-authority.json` supplies fresh `authority`; the other answers are reused
only for the same scope. Authority is never inherited. A changed scope requires
a complete new answer set without `--reuse-answers`. `--interactive` asks only
for missing answers. Resuming a task increments its revision and clears READY
and old check evidence. CLOSED is immutable; begin a new task.

Only one task may be active in a project. After CHECKPOINT or CLOSED in the same
workflow session, use `project next-turn --root P --session S --from-turn OLD
--turn NEW --task TASK`, then enter explicitly. An active binding to another
task blocks accidental entry. Unbound old observations do not block entry.

When a different task has since become active in the former project, run this
same `next-turn` command at the former root with the exact old terminal task,
session and previous turn. The old task must belong to that project and retain
that session/turn binding; the different active task must exist in the same
project. The existing exact receipt/root/task/status checks and project-then-turn
locks still apply. Only the old workflow receipt advances to INTAKE_REQUIRED;
both tasks, project active pointer/revision, READY and check evidence are left
unchanged. Then enter the intended isolated project explicitly. This does not
resume/accept the old task, enter the other active task, transfer its authority
or establish business completion. For this ordinary transition, missing, stale
or replayed bindings, nonterminal old tasks and pending recovery remain refusals.
Do not clear receipts manually
or invoke a lower-level helper as a consumer workaround; reconcile an unknown
atomic outcome before another transition.

If the exact former root is missing or has been moved, use the separate
`project recover-binding` procedure in [Binding recovery](BINDING_RECOVERY.md).
It requires the exact session, old turn/task/root, new turn and SHA-256 of the
current receipt, plus explicit owner permission to detach while the old task
state is unverifiable. It refuses existing roots, unsafe paths, mismatches and
conflicting registered executors. Under the user-turn lock, it archives the
original receipt and journals a compare-and-swap transition of this chat alone
to INTAKE_REQUIRED without a task binding. The old project, task and history
remain unchanged; no READY or authority is created. Then use ordinary `project
enter` at the intended project with the selected new turn and current authority.
An exact retry can finish a PREPARED transition from its unchanged original
receipt after repeating the preconditions, or confirm its exact replacement
receipt. A later entry cannot be cleared by replaying recovery.

Native provenance alone is neither authority nor evidence of native enforcement.

If an interrupted `enter` leaves `.agentos/entry-transaction.json`, dependent
lifecycle commands report `entry_recovery_required`. Questions and read-only
diagnostics continue. Check the exact stale lock, then repeat `enter` to recover
and re-establish the task binding.

## 4. Document before implementing

Select only applicable layers from the catalog: dossier, roadmap, and stage are
basic; API work needs a contract, personal data needs access and data rules,
and operations need runbook and rollback. Keep the overall objective and plan
visible, while detailing the selected project, module or microprocess level.
Define readiness and acceptance for the declared stage: a reviewed scaffold
stage can be ready without completing every module or release requirement.
A draft document never passes READY. The reviewer fills in facts, sources,
unknowns, write paths, architecture decision, stage acceptance, and rollback.
Reuse the existing documents instead of adding parallel plans. Register each
required document:

```sh
agentos project document --root P --id dossier --path docs/agentos/DOSSIER.md \
  --owner Reviewer --source 'current source and owner task' --summary 'Reviewed facts'
agentos project ready --root P --task TASK --reviewer Reviewer
```

A stage registration also needs `--task TASK`, and the document must name that
exact task. READY checks hashes, currency, and structural correspondence; it is
not an interception of arbitrary tool calls. The agent respects the boundary,
while the client, operating system, or target executor enforces any hard external
limit. Documentation does not grant production authority.

## 5. Implement with exact authority and checks

Write only within approved paths. `project check --root P --task TASK --check-id
NAME` runs the registered argument array with a timeout and a bounded,
source-bound receipt. Its runner stops its own process group on timeout, output
overflow, lingering child, or selector/pipe failure. A nonzero return code or a
source change during the check is FAIL. `shell=False` avoids shell interpolation
but is not a sandbox: the command may still reach a network or host. Verify its
real effects before running it. Local checks should use test data, temporary
directories, and no credentials or dangerous executors.

Before external messages, production/runtime/database writes, credential use,
destructive actions, or deployment, verify the exact actor, target, operation,
validity period or lease, allowed effects, and rollback at the target. Read
authority does not authorize a send. Local READY does not authorize production.
If a target capability is absent, stop only that action and continue other
authorized preparation. There is no universal `--authorized` override.
Choose protection by the actual effect and affected state under
[Proportionate protection](#proportionate-protection-of-data-and-runtime).
Rollback means a sufficient recovery route, not an automatic full copy.

<!-- agentos:solution-integrity:start -->

## Solution integrity

### Свод законов работы — редакция 1

**Решение сохраняет исходную задачу, имеет обоснованный путь получения и выдерживает существенную проверку. Желаемый ответ сам по себе этого не доказывает.**

Применяй законы к разработке, исследованиям, расчётам и диагностике. Они действуют на уровнях 1–5 и во временной диагностике 0. Уровень меняет глубину работы, но не достоверность. Для новой функции обосновывается ожидаемое поведение; выдумывать неисправность и её причину не нужно. Явная заглушка или временная мера может быть принятым промежуточным результатом.

**Агентам запрещено менять, сокращать, переопределять или ослаблять этот свод, его эталон и проверку ради своей задачи. Изменение возможно только по явному решению владельца именно об изменении свода. Предложение сохраняется отдельно; прежняя редакция остаётся в истории. Общее поручение улучшить проект таким разрешением не является.**

| № | Закон | Правильно | Неправильно |
|---|---|---|---|
| 1 | Сохраняй задачу, входы, условия и критерий успеха. Изменённые условия — отдельный опыт. | Учтены исходные расходы. | Расходы убраны ради прибыли. |
| 2 | Обоснуй ожидаемый результат: смысл, единицы, порядок, время и округление. Ожидание тоже может быть ошибочным. | 10 000 копеек = 100 рублей. | «Число кажется большим». |
| 3 | Проследи источник → вход → преобразование → выход на текущих версиях и настройках. | Проверен реально вызываемый код. | Исправлена неиспользуемая копия. |
| 4 | Найди последнее верное и первое неверное состояние. Углубляйся по наблюдаемому расхождению. | Проверено преобразование неверного поля. | Переписана вся система наугад. |
| 5 | Причина даёт проверяемое предсказание; сопоставляй существенные альтернативы. Противоречие требует пересмотра гипотезы. | Повтор события воспроизводит лишний эффект. | Причина выбрана по правдоподобию. |
| 6 | Проверяй существенный результат независимым эталоном, инвариантом или способом расчёта. | Малый пример рассчитан отдельно. | Ожидание вычислено проверяемой функцией. |
| 7 | Сохраняй исходную точку и различимость влияния изменений. Связанные изменения обосновывай вместе. | Сравнены одинаковые входы до и после. | Одновременно заменены данные и критерий. |
| 8 | Исправляй породивший ошибку механизм. Снятие симптома называй временной мерой. | Устранена повторная обработка. | Перезапуск объявлен исправлением причины. |
| 9 | Обосновывай решение только доступной тогда информацией. Поздние данные служат оценке. | Использована уже закрытая свеча. | Будущий минимум выбран задним числом. |
| 10 | Сохраняй состояние, историю и исходную идентичность неопределённой операции. Новый ID не обнуляет эффект. | Проверен исходный неизвестный запрос. | Тот же эффект отправлен под новым ID. |
| 11 | Ищи существенный случай, который опровергнет решение или покажет его вред. | Проверены настоящий повтор и другая операция. | Проверен только удобный пример. |
| 12 | Различай наблюдение, гипотезу, механизм, проверенную выборку и обобщение. Называй границы. | Кандидат установлен; живой сценарий открыт. | Сборка названа готовым продуктом. |
| 13 | Планируй целое, собирай связный модульный стенд, затем углубляй выбранную часть и подключай обратно. | Главный путь проходит через модули. | Готовые части не работают вместе. |
| 14 | Рано проверь предпосылку, способную обесценить выбранный путь, в нужной среде и контексте. | Проверены подпись и системный запуск. | Linux-тест выдан за проверку другой ОС. |
| 15 | Принимай пользовательскую цепочку в объявленном объёме, включая существенный следующий переход состояния. | Проверены вход, выход и повторный вход. | Сообщение бота принято за сессию приложения. |
| 16 | Если попытка не даёт новой информации, измени проверку или подход. Уточнение владельца сверяй с фактическим контекстом. | Сопоставлены удалённая и графическая сессии. | Повторяется уже опровергнутая просьба. |
| 17 | Сохраняй выбранный уровень. Проверяй соразмерно связи и риску; на уровне 1 нужны модульность, полезный debug и журнал ошибок. | Связный шаг проверен, работа продолжена. | Каждая вспомогательная функция тормозит платформу. |
| 18 | Фиксируй накопленный результат, проверку, остаток и следующий шаг кратко. Явный договор доставки сохраняй отдельно. | Принятое сохранено; доставка ещё открыта. | Новый этап обнулил прогресс; отчёт остановил работу. |
| 19 | Владей ресурсами. Перед большой записью проверь запас на реальном томе и параллельные записи; перед очисткой — потребителей, уникальные данные и восстановление. Измеряй эффект. | Известный временный ресурс освобождён и проверен. | Всё остановленное объявлено мусором. |
| 20 | Сохраняй права, Auth/ACL, данные, откат и границы синтетики, кандидата и production. Закон не создаёт полномочий. | Выполнена разрешённая часть, точный остаток назван. | Проверка или разрешение обойдены ради PASS. |

**Приёмка:** результат, нарушающий применимый закон, не принимается в заявленном объёме. Сохрани проверенные части, назови конкретное нарушение и исправь его; не обнуляй всё и не расширяй проверку без основания. Самооценка исполнителя, число тестов, ACK или хеш не заменяют проверку результата. Зависимые наблюдения не становятся независимыми от их количества.

**Короткий порядок:** восстанови цель и текущую основу → выбери связный шаг → выполни → проверь существенное → запиши результат и остаток → продолжай разрешённую работу. Для исправления объясни: где расхождение; какой механизм; почему правка влияет; что могло её опровергнуть и что показала проверка; что ещё неизвестно.

**Соразмерность:** используй существующие план, контракты и журнал. Новые формы, полный архив после каждого малого шага, произвольные лимиты времени и доказательство каждой функции не требуются. Явное поручение владельца о передаче или расписании сохраняется. Детали уровней, диагностики, причинной проверки и гигиены находятся в соответствующих разделах PROCESS. Чтение свода не доказывает его применение.

<!-- agentos:solution-integrity:end -->

<!-- agentos:workspace-hygiene:start -->

## Workspace hygiene

Own the space used by the authorized work through its useful lifetime. Apply
this method to development levels **1–5** and diagnostic **0** without changing
the saved level or scope. Before a material build, test, restore, package,
download or cleanup, establish the relevant resource and capacity facts. Reuse
unchanged facts and record one compact result at a substantive checkpoint,
close or handoff. The complete class, retention and qualification contract is
[WORKSPACE_HYGIENE.md](WORKSPACE_HYGIENE.md).

### What is implemented

`agentos project resource plan --input PATH|-` observes an explicit bounded
private descriptor and returns a metadata-only plan. It does not register a
resource, reserve capacity, release a lease, delete files or accept a stage.
Declared ownership, reproduction or closure is not independently proved by a
plan. Native reservation and cleanup apply/reconcile are proposed successors,
with separate destructive-profile qualification. Existing inventory and task
metadata budgets do not allocate filesystem capacity. A handoff retirement
retains history and does not reclaim space.

The obligations below already govern the agent's authorized work. Use an
existing qualified cleanup routine for its own private resources when disposal
is within the task's authority; do not ask again for each ordinary derived file.
A new observation plan grants no deletion or host authority and does not enable
mass cleanup of old directories.

### Before and during the run

Keep the existing task/run record of the resource's opaque ID, project/run and
creating operation, owner, private admitted root, class, reproduction/recovery
reference, consumers and release condition. One build tree or private test
database needs one root record: its known ordinary derivatives inherit the
class. Separate a different owner, durable evidence or recovery copy inside it.
Keep the path mapping private on the host; ordinary output uses opaque IDs and
safe reasons. Age, a `tmp` prefix, filename or common UID do not establish
provenance. An unclassified existing object stays HOLD.

Choose the actual filesystem and estimate its remaining peak of simultaneously
live new writes: archive/download, expansion, PGDATA/WAL, intermediates, package,
final copy, retained partial and any retry overlap. Do not count an existing
input read in place as a new copy. Use a comparable measured run or a justified
bound; distinguish estimates, configured limits, usage and measured peaks.
Bound unknown growth by chunks with fresh checks or a qualified exclusive window
with an enforceable limit. Do not prescribe one universal multiplier or margin.

Measure available bytes and inode capacity for the current identity, applicable
quota when known, relevant filesystem identity and other participating runs'
unconsumed reservations. Compare the remaining peak after subtracting those
promises and justified service headroom. Reserve room in the decision for the
final result and emergency journal. Physical allocation reduces an unconsumed
promise; counting both in full would count the same use twice. For a known
required quota without an observation, use a separately verified bounded area
or pause the dependent write. UNKNOWN is not unlimited. The read-only command
does not make a shared reservation or fence external writers.

Keep live ownership and consumer facts current. On normal exit and exception,
finish the owned routine in `finally`. After a crash or lost reply, reconcile
the original operation before a new attempt. Verify the exact stopped process
using the relevant host/boot/start identity, run, locks and data root. An absent
PID file or expired lease requires reconciliation; neither proves termination.

### Decide what can be released

- Release scratch, staging, build output or a private cache only within its
  proven ownership, after required output is retained/read back and reproduction
  inputs remain available. Shared caches belong to their manager and consumers.
- A disposable database additionally needs actual isolation, reproducible
  seed/migrations, stopped owner and consumers, and retained diagnostic evidence.
  Unique changes or uncertain process state stay HOLD.
- A temporary recovery copy needs a closed rollback window, no active
  backup/restore dependency and a verified usable replacement or exact recovery
  route. Check from the restoration location, including dependencies and access;
  replacing the only critical copy requires a restoration check.
- Retain authoritative results, receipts, journals, accepted checkpoints,
  durable backups and necessary PREPARED/UNKNOWN evidence under their own policy.
  A separate packaging copy can be removed after destination content is verified.
  No automatic age expiry or bulk historical cleanup follows from this method.

### Complete or hand over cleanup

Use the selected run's plan to see each resource ID, class/owner, estimate,
release or HOLD reason, and next action. Resolve the listed dependency through
its owner; close the owned consumer, preserve the useful result and record the
release condition. Then use only a qualified already-authorized routine with
durable intent/outcome outside the removable tree and fresh identity checks.
Keep a single cleaner in an exclusively controlled private scope. Do not follow
symlinks, cross unexpected mounts, infer mount identity from device number alone,
or treat another object at the same name as the former resource. A hardlink,
unexpected independent object, uncontrolled writer or unsupported adapter gives
HOLD in the initial profile. Repeated `lstat` alone cannot exclude substitution.

Read back the original object and any retained/transferred result. Lost output
requires the same operation ID and actual-state reconciliation, not another
delete against the current name. Record released, accepted transfer, or retention
with reason, responsible actor and next review date/event in the existing run
journal. A due date requests review rather than authorizing removal. A transfer
of HOLD retains responsibility and does not free bytes. Unrelated historical
material does not block the current stage. These are procedural obligations;
this release adds no native close gate or per-file report requirement.

Keep removed names, known allocated blocks and observed available-space delta
separate. Competing writes can make the volume delta zero or negative; an open
deleted file may keep its blocks. Retain timestamps and filesystem/quota scope.
Report uncertain reclaimed bytes as UNKNOWN, even after name removal is verified.

### Handle insufficient space without losing the result

On negative admission, ENOSPC or EDQUOT, stop new heavy writes to that filesystem.
Observe bytes, inode, quota and the selected owned temporary resources; check
open-deleted files when observable. Keep an unmeasured accumulation cause unknown.
Check a candidate alternate volume's capacity, quota, rights and lifetime, plus
memory headroom for memory-backed storage. Recheck both staging and the final
destination; their free space is separate.

Preserve the previous accepted result. Write its replacement through an exclusive
sibling partial, bounded writes, size/hash readback, file fsync, atomic replacement
on that filesystem and directory fsync under the publisher's qualified semantics.
Keep a failed write visibly partial and rebuild only reproducible outputs.
If the required durable journal cannot be written, pause new deletion until its
storage is reliable. Retain useful progress and an owned next action; do not
create another full archive or repeat unchanged work to finish a cleanup note.

<!-- agentos:workspace-hygiene:end -->

<!-- agentos:project-diagnostics:start -->

## Project diagnostics

**Diagnostic level 0** is a temporary, one-pass mode for understanding and
correcting the direction of an existing project. Its result is a current dossier,
an explicit inventory and gap assessment, and a justified next step. Ask: what
result are we pursuing, what actually exists, do the parts fit, does the work
serve that result, and what should happen next? Apply **Solution integrity**;
guidance prepends that same canonical body to this method.

Include resource ownership, capacity and retention gaps in the current dossier
where relevant; use [Workspace hygiene](#workspace-hygiene) for material audit
outputs and their disposition, without scanning unrelated historical roots.

### Enter, preserve and return

Keep the selected development level **1–5** and its scope; 0 does not replace it
or add a sixth persistent choice. Enter on the owner's request, or before
substantial work when material uncertainty about the current state, objective,
architecture or dependencies could lead to the wrong implementation. At a
significant architecture, integration, migration or delivery milestone, review
whether changed evidence warrants another diagnostic pass. This is an event-based
decision, not a calendar schedule or an audit after every patch.

Record the reason, scope, current basis and captured previous level in the
existing task/context. An active pass survives interruption and a new session:
resume its findings and next investigation instead of starting again. Native
registered tasks use `project diagnose start|status|finish|cancel`; take exact
arguments from the current CLI/contract. Standalone read-only work needs no
intake, project initialization or fabricated task. Retain equivalent state in its
existing plan/context and journal; do not create a parallel settings register.

On finish, retain the current dossier reference, findings, unresolved work and
next action, then return to the saved development mode. An explicit newer owner
choice of level/scope takes precedence over the captured previous choice; retain
both as history rather than restoring an obsolete setting. Cancellation records
the partial result and remainder and also returns the mode; it does not pretend
the audit completed. Neither transition closes the product task, accepts its
findings as repaired, grants READY/authority, nor clears a concrete blocker.

### Establish the current project, then its gaps

1. **Restore the intended outcome.** Read the original objective, current scope,
   main user scenarios, constraints and acceptance conditions. Separate the
   desired state from observations. Identify where current work no longer serves
   the goal; a convenient implementation is not a substitute for the requested
   result. Preserve the current writer, accepted results and their dated basis.
2. **Build the current inventory.** Cover the whole project at the selected
   architectural level: authoritative source/revisions, documents, components,
   services, dependencies, state owners, environments, interfaces and existing
   work. Name the inventory's boundary, exclusions and uninspected areas. Expand
   selected modules recursively when a dependency or discrepancy requires it;
   a top-level audit need not enumerate every internal helper. Stay within the
   known project roots and authorized sources, not unrelated accounts or hosts.
3. **Trace the useful chains.** Connect goal → user scenario → modules →
   interfaces/data → implementation → evidence → delivery/recovery. Establish
   responsibility, inputs/outputs, actual consumers, state/effect ownership and
   dependencies at each material boundary. A directory or service name alone
   does not establish modularity, independent builds or independent updates.
4. **Compare documents with actual state.** Check applicable contracts,
   architecture, dossier, roadmap and stage records against the relevant source
   and permitted runtime observations. Identify missing, stale, conflicting or
   incomplete content, including a documented interface with undocumented
   consumers or incompatible errors. A heading, file, hash or generated schema
   alone does not prove semantic correctness or complete coverage.
5. **Classify consequential gaps.** For each material finding keep its source,
   observation, effect on the goal, remaining uncertainty and next owner/action.
   Distinguish a demonstrated inconsistency from a hypothesis or missing evidence.
   Identify which gap blocks a particular next step and which belongs to a later
   stage. Do not stop independent authorized work for unrelated findings.
6. **Update the path forward.** Correct the affected authoritative documents
   through their existing writer and permitted change route; retain AS_IS and
   proposals separately. Reuse the current dossier, architecture, work matrix,
   roadmap and journal rather than creating another report suite. If a required
   source cannot be changed in this scope, return an exact proposed delta to its
   owner. Preserve history and prior partial acceptance. Leave an ordered plan
   with dependencies, a bounded next result and its meaningful check.

### Select applicable contracts and evidence

Use [the documentation catalog](DOCUMENTATION_CATALOG.md) and the existing module
contracts to select the required content and suitable formats. Inspect:

- **Interfaces:** provided and consumed HTTP, event, RPC and in-process methods;
  input/output/error semantics, versions, compatibility, Auth/ACL/tenant context,
  effects, idempotency and unknown-outcome reconciliation. Use OpenAPI for an
  applicable HTTP surface, or the project's appropriate schema/IDL/typed contract.
  No HTTP API means OpenAPI may be N/A with a reason, not a missing deliverable.
- **State and data:** actual owner, lifecycle, schema and migrations, lineage,
  privacy/access, transaction boundaries and partial/repeated operations. Do not
  manufacture an ERD when there is no database or omit real file-backed state.
- **Build and operations:** declared build/dependency inputs, artifacts,
  deployment units, versions/configuration, useful logs and error journal,
  readiness, continuity, recovery and rollback where the stage/effect needs them.
  Do not infer independent deployment from logical module boundaries.
- **Quality and progress:** what is accepted, partially accepted, running,
  blocked or not begun; exact proof scope and the concrete remainder. Separate
  source review, synthetic stand, candidate, installed state and observed
  production behavior. Preserve untested conditions and stale evidence.

Mark UNKNOWN when evidence cannot establish a fact, and N/A only with an
applicability reason. Missing required content is a named gap, not a placeholder
filled to pass a gate. Reuse current evidence with its original scope/date;
repeat only for changed inputs, a material discrepancy, applicable freshness or
a required gate. Existing Atlas `project-audit`/coverage is useful evidence about
its declared inventory; it does not automatically inspect the whole source or
execute the product. Read-only diagnosis grants no runtime mutation or access.

For migration from an existing production system to independent service modules,
map the current user journeys, identities/sessions, state and in-flight work to
the proposed owners and contracts. Identify compatibility during mixed versions,
migration ownership/order, observable continuity, cutover conditions, reconciliation
and recovery. Confirm which units can actually be built and updated separately.
A diagram, successful build or synthetic scenario does not establish a seamless
user transition; place the remaining real acceptance in the migration plan.

### Finish when the direction is sufficiently clear

The pass is sufficient when the inspected scope and sources are explicit, the
current/desired states and their material gaps are understandable, applicable
documentation and contracts are accounted for, and the next justified action,
owner, dependencies and check are clear. State remaining UNKNOWN and their impact.
Completing diagnosis does not require repairing every finding, proving every
internal detail or eliminating every unknown. Block only the next action whose
material precondition remains unestablished; give other gaps owned roadmap work.

Save one concise result in the existing records and return to the development
level. After a later significant change, inspect the affected delta against this
basis. Repeat the full inventory only when its scope or reliability materially
changed. Loading this method, ending the mode or receiving an ACK proves neither
that the audit was performed nor that the project works.

<!-- agentos:project-diagnostics:end -->

<!-- agentos:project-development:start -->

## Project development

Use this method to advance the whole project to the user's result through
understandable plans and working increments. It applies to ordinary development,
features and policy work. The canonical text is this marked section of
`docs/PROCESS.md`; read its current body through `agentos workflow guidance`,
or directly from the selected source or installed resource when the CLI is
unavailable. Apply the shared [Solution integrity](#solution-integrity) laws at
every level; guidance includes their current body before this method. When
reading the document directly, read both sections. Continue the existing project
and writer, using the current plan.

For material allocations and completion, use [Workspace hygiene](#workspace-hygiene).

At first engagement, read [WORK_ENVIRONMENT](WORK_ENVIRONMENT.md) once.
Reuse the current introduction and restore relevant parts after context loss;
the frozen laws remain the acceptance standard.

Before substantial work with material uncertainty about the project's state,
direction or dependencies, use **Project diagnostics** through
`agentos workflow guidance --method project-diagnostics`: temporary level 0
preserves the selected 1–5 level and returns to it after a current dossier,
findings and next action are recorded. Resume an active pass across sessions.
At significant milestones review changed evidence and diagnose the affected
scope when needed; do not launch a full audit after every increment or repeat
unchanged inventory. Explicit newer owner level choices prevail on return.
Diagnostics clarifies the next step; it does not require fixing every finding
before continuing, replace product acceptance or grant authority.

### Development level: 1–5, default 3

The level sets a development mode, not completion percentage. The user may change
it anytime for a project, stage or module. Inherit the enclosing level unless a
narrower choice exists; otherwise use **3**. Briefly state it at start/change and
record its scope in the current plan. Changes govern subsequent work; do not
rebuild completed work merely for a level change.

Carry the choice across sessions and handoffs. The existing task answers and
context goal can contain `development: {"level": 1, "scope": "project"}`;
`1D` is an input alias of level 1, not another level. Same-task resume retains
an omitted saved choice. For registered tasks, context callers bind the exact
current task and revision through `development_source` in [CONTEXT_BINDING](CONTEXT_BINDING.md);
the builder carries and checks its saved choice. Unregistered/portable callers
carry typed `goal.development`; a choice recorded only in prose is insufficient. Scope
names identify the existing plan's project/stage/module, not an authority grant
or an automatically inferred scope tree. Use the enclosing plan to resolve it.
When loading guidance, pass that same choice with `--development-level` and
`--development-scope`, including an explicit causal-debugging lookup. Omitted
arguments expose the stateless default; they do not replace a choice already
known from the plan. Without the CLI, retain the choice beside the actual method
text in that plan; no installation is required merely to read the method.

Only for a new project whose development has not begun, offer a native
single-choice control with the five options below, in the user's language;
if unavailable, present one compact five-option choice. Apply an explicit level
without repeating the choice. Patches, fixes, small changes and continuation
inherit the level, defaulting to **3**; show no selector. Create no forms,
standalone storage or imitation buttons.

| Level / short button label | Description |
|---|---|
| **1 — Fast assembly** | Connect the whole with simple implementations or explicit stubs; check the new connection and material risk sufficiently, retain useful debug and an accessible error journal, then continue assembly. |
| **2 — Main connections** | Assemble quickly with debug; check main module boundaries and connections, then deepen details. |
| **3 — Working stage** | Run a coherent stage with related functions/exports connected and exercised; use a light synthetic end-to-end scenario, then proceed. |
| **4 — Integration detail** | Detail selected module contracts and check main failure scenarios during integration. |
| **5 — Deep steps** | Detail and verify each step immediately within the overall plan. |

Instrument key paths and module boundaries. Use existing logging or a simple
accessible shared error journal: time, module/operation, error, known
cause/stack when available, and request/run identity linking the scenario.
Keep context bounded and free of secrets. Once a specific part works, remove or
disable temporary noisy debug and retain normal error logging; confirmation of
that part suffices without whole-project proof.

Every level preserves modularity, common working stand before recursive detail,
explicit stub status, access rights and essential checks for secrets, irreversible
effects and other protected operations.

At level 1, choose a connected increment as the unit of progress. A helper,
file edit or internal microstep need not become a separate acceptance cycle.
Keep module inputs/outputs and the short complete structure plan visible; defer
nonblocking internal detail to its named recursive stage. One relevant existing
check or a small scenario may suffice for the changed connection. Check affected
Auth/ACL and data/effect protections when needed at every level. Investigate a
concrete malfunction causally, then return to assembly once its scoped blocking
condition is resolved. No level imposes a fixed number of minutes or tests.

### Proportionate protection of data and runtime

Assess the actual action and affected state before choosing protection.
Distinguish a live service or operational database, unique non-production data,
and an isolated reproducible development stand. A new runtime is not production
merely because it runs a server or database. Names such as `lab` or `test` do not
establish isolation either; use the known target, connections, storage and
dependencies. Reuse unchanged facts instead of repeating discovery for every edit.

- For versioned source and reproducible development state, preserve changes
  through Git and retain the available inputs needed to rebuild or reseed the
  affected stand. Preserve relevant uncommitted or untracked work before an
  operation that could remove it. Do not routinely copy the whole runtime,
  dependencies, caches, synthetic database or earlier backups. A release package
  captures its declared source/artifacts; it does not require a running database
  copy. A full stand capture is warranted for a concrete transfer or recovery
  rehearsal that needs those bytes, not for ordinary development increments.
- Unique data, configuration or evidence can exist outside production. Preserve
  only the affected material that cannot be safely or acceptably recreated.
  Retain an expensive experiment's necessary result without copying unrelated
  runtime state. An isolated copy of real data remains confidential; keep private
  data and secrets out of public Git even when that copy can be recreated.
- For live services and operational data, assess concrete loss or corruption,
  interruption, disclosure and external effects. Choose the smallest sufficient
  protection: an existing applicable recovery point, transaction, targeted
  preimage/export, configuration rollback or retained release. A code-only change
  does not automatically require a database copy; code can still cause destructive
  writes without a schema migration. Read-only inspection requires no new backup.

A new backup needs a concrete reason: what state could be lost, by which action,
why it cannot be safely or acceptably recreated, and why an available recovery
route or a smaller copy is insufficient. A full backup is appropriate only when
the affected scope and recovery need justify it, or it is the requested
deliverable. Reuse an available, sufficiently current recovery point when it
covers the operation. Account for the copy's disk, time and service impact;
repeated copies are not evidence of safety.

Record material decisions briefly in the existing plan or operation record,
without a separate risk register, per-command form or repeated owner approval.
If the target or effect is uncertain, make the smallest relevant read-only check
and continue independent authorized work. Development level changes verification
depth, not the value of data or a default backup requirement. Existing target
authority, ownership, mandatory narrow transactional journals and UNKNOWN
reconciliation remain in force. This rule does not authorize deleting retained
backups, evidence or history.

For capacity, temporary-copy release conditions and owned cleanup, apply
[Workspace hygiene](#workspace-hygiene) and its single
[resource contract](WORKSPACE_HYGIENE.md); retain decisions in the existing run.

### Working cycle

1. **Define the result.** State the intended product, its main user scenarios,
   scope and constraints. Identify what completion means at the current level.
   Keep this outcome visible when choosing work, so implementation choices serve
   the project instead of accumulating unrelated features or process tasks.

2. **Plan the whole current level.** Before its main implementation, describe
   the path from beginning to result: necessary stages, their order,
   dependencies and concrete next steps. At project level, cover architecture,
   code structure, data, interfaces, integrations, infrastructure, launch and
   completion. Name unknowns and the stage that will resolve them. A complete
   project plan does not require every lowest-level detail upfront; expand a
   module or microprocess when choosing to work at that depth.

3. **Keep modularity mandatory.** Give each part a clear responsibility, inputs,
   outputs and interface to the rest of the project. Preserve these boundaries
   as work becomes more detailed. Prefer existing components and straightforward
   interfaces. A module boundary should make a part understandable and replaceable;
   it need not create a separate service or extra deployment machinery.

4. **Build the common working stand first.** Establish a runnable project with
   connected parts and one main end-to-end scenario before deeply polishing an
   individual component. This stand can use simple implementations and explicit
   stubs for unfinished parts. Its purpose is to make the overall structure work
   and expose the next useful increment. In an existing project, reuse the
   working stand and preserve its useful behavior instead of starting another.

5. **Use interim solutions deliberately.** Choose the simplest implementation
   sufficient for the declared stage. For a stub, say what it substitutes for,
   what behavior it currently provides, and which planned stage will replace it.
   Keep its boundary clear to callers and users who depend on that behavior.
   A scaffold, prototype or contract can be a completed stage result. Schedule
   robustness, optimization and broader coverage where the product needs them.

6. **Deepen recursively.** After the common stand works, select a module,
   function or detail and repeat the same cycle: complete plan for that level,
   understandable steps, working result, then further depth when useful.
   Apply it again to a selected microprocess if necessary. Reconnect each result
   to the common stand. Keep unresolved internals behind their declared interface
   or stub so one detail does not block independent platform work.

7. **Finish the declared stage.** Give each step a purpose, actions, expected
   output and a simple completion criterion. Judge that output against its own
   scope. Place whole-product integration and release acceptance in their planned
   stages. Record nonblocking improvements at an explicit later point in the
   same plan. Resolve a blocking dependency sufficiently to resume progress;
   parallelize independent work with clear ownership.

8. **Check enough, then stop.** Match verification to the selected development
   level, changed behavior and risk: inspection, a build, a relevant existing
   check or a focused user scenario may suffice. Sensitive data, access and
   critical operations require their applicable checks and recovery provisions. Once the stage criterion
   and required checks pass, with no concrete obstacle to continuation, stop
   checking and proceed. Extend verification for an observed defect, changed
   conditions, unresolved material risk or a planned acceptance gate. Reuse
   applicable results; do not repeat unchanged checks or add speculative test
   programs to a finished step.

9. **Record and continue.** Update the existing plan briefly with the result,
   remaining stubs or limits, and the next step. Save changes through the
   project's normal route, then perform that step. Adjust affected plans when
   new information changes dependencies or scope. When newer scoped guidance
   supersedes part of a mutable plan, mark the replaced section as historical
   and link to the current plan and its scope. Preserve accepted results and
   dated evidence. For immutable snapshots, update the existing current index
   instead. Repair affected links and conflicts without a separate documentation
   sweep. Make routine technical decisions within the assignment without
   repeatedly returning them to the owner. This method uses existing authority
   and does not change external permissions, protections or UNKNOWN reconciliation.

### Internal progress, handoff and coordination

For an internal step in the same retained working stand, keep a compact record:
changed connection, sufficient check/result, remaining stub or error, and next
authorized action. Continue within the current assignment. This is not a call
to `project close` or `project checkpoint`; those terminal operations retain
their existing accepted-handoff requirements. A long report and a rebuilt full
archive are not prerequisites for every internal step.

Reuse an accepted available base and retain changed/added/deleted files and
relevant new evidence as a delta. Pin the base and delta identities and their
relationship; preserve the dependencies required to reconstruct the result.
A delta without its accessible verified base is partial, not a self-contained
handoff. Produce a complete package when requested, when transfer/recovery needs
it, or when the destination cannot obtain the pinned base. Existing capture,
integrity, required result-delivery and restore checks still apply.

Preserve the result before a notification attempt. A failed optional owner
notification does not hold the saved result or an already authorized independent
next step; retain its exact delivery state for reconciliation. Required result
receipt/review and optional notification are separate. The coordinator still
reviews the declared result and owns the next assignment; do not infer permission
for an unassigned step or send a duplicate to a busy/unknown executor.

Delegate bounded independent parts when they can help. Record each returned
contribution and observed execution, dependent wait and integration time where
available; reuse existing timestamps at meaningful boundaries. Distinguish
implementation, checks, packaging/reporting, coordinator wait and lost access.
Unknown intervals stay UNKNOWN, overlaps are not summed twice, and gaps between
messages do not establish their cause. A launch count or an unmatched before/after
observation does not establish acceleration. This is lightweight task accounting,
not per-command instrumentation or another mandatory report.

A new method file, capsule hash or ACK proves neither active-session pickup nor
application. Deliver the exact current instruction through the authorized route
at a safe boundary, then inspect the next permitted action: retained level/scope,
connected increment, proportionate check, useful journal, compact progress and
continued ownership. Mark each observed behavior separately from unexercised or
unknown behavior. Do not restart work or replay a finished scenario to manufacture
adoption evidence.

<!-- agentos:project-development:end -->

<!-- agentos:causal-debugging:start -->

## Causal debugging

Select this method separately with
`agentos workflow guidance --method causal-debugging` for a specific malfunction
in UI, API, services, data, performance or operational constraints when causal
investigation is needed. Ordinary development follows **Project development**;
causal diagnosis is not a universal prerequisite. Define a sufficient correction
or mitigation criterion for the current problem, then return to the project plan
when it is met. Keep any unresolved cause explicit rather than extending the
investigation solely for completeness. This method uses the existing diagnosis,
implementation and acceptance cycle, without a second workflow, new task gate or
permission. On continuation restore the experiment and its evidence from the
existing work packet rather than restarting diagnosis.
The canonical text is this section of `docs/PROCESS.md`, mirrored byte-for-byte
in installed `resources/docs/PROCESS.md` (located with `agentos resources`).
Read the actual bounded section returned by the effect-free
`agentos workflow guidance --method causal-debugging`; if the CLI is unavailable,
read this exact section and shared [Solution integrity](#solution-integrity) from
the selected source or installed resource. Guidance includes the shared laws
before this method; their integrity requirements apply at every development level.
Entry/context output that already
materializes the same current body may be reused. A link, hash or receipt for
instruction delivery alone does not prove agent behavior. Ordinary feature work
without a malfunction does not require an invented failure or reversal cycle.

Use [Workspace hygiene](#workspace-hygiene) for diagnostic fixtures, capacity
observations and cleanup. A full filesystem can explain a write failure while
the accumulation cause remains unmeasured; preserve that distinction.

### Define and reproduce the failure

Record the user's action, expected result, actual result and an observable
success/failure criterion before choosing a cause. Reproduce with the exact
relevant environment, source/runtime version, data or fixture, configuration,
initial state and load. Record actual effective settings and actual execution,
including the first failing boundary, safe error/code and exit or response.
Keep source, installed version and already-loaded worker code distinct.

If reproduction fails or is unavailable, say so explicitly. Preserve the incident
as unresolved; a suspected cause remains a hypothesis. Select the next bounded
observation or safe reproduction that distinguishes the remaining explanations.
Do not invent a failure, infer recovery from a healthy process, or claim causality
from timing, a matching error label or one successful run.

The same HTTP 503 can originate at different boundaries. An `EXPORT_DEADLINE`
records the export's observed time boundary; it does not establish a database
`statement_timeout`. Retain the actual safe error, SQLSTATE if observed, and
diagnostic classification. A missing SQLSTATE or unobserved database boundary
remains unknown; never fill it with a guessed cause.

### Establish a working baseline

Obtain a configuration in which the same scenario meets its success criterion.
When artificial operational limits are suspected, use an authorized isolated
environment and sufficient **finite** values to establish that baseline. Record
which limits changed and their effective values; an explicit request is not
proof that a setting took effect. Keep data, scenario and required semantics
equivalent. Reuse a qualified baseline only while its relevant inputs match.

Before launch, check compatible finite limits along the whole relevant chain:
**producer/exporter → writer → reader → restore**. Compare effective units and
semantics, including output, chunk/page, stored, expanded and restore-input sizes;
raising the producer's ceiling does not establish downstream capacity. Account
for the files that can coexist on each filesystem: primary data/output, staging
and temporary copies, rollback/WAL and other journals, indexes and service data,
retained partials and required recovery copies. Compare their combined requirement
and justified headroom with available space. Preserve the previous configuration
and an applicable rollback route; do not discard a partial to make the budget fit.
Select recovery copies under [Proportionate protection](#proportionate-protection-of-data-and-runtime):
the action's actual risk determines their scope. A reproducible stand normally
uses retained source and rebuild inputs; this capacity check does not require a
full runtime or database backup. Reuse an applicable existing recovery point.

Keep **configured ceilings**, **estimated requirements**, **observed usage** and
**measured peaks** separate. A configured stage budget, end-of-run file size or
arithmetic sum is not a measured disk peak or process RSS. Record the measurement
method and scope, or leave the peak/RSS unknown. Missing sizing facts call for a
bounded measurement or explicit estimate, not an invented capacity guarantee.

Preserve authentication, authorization/access boundaries, isolation, data
integrity and every mandatory protection. An operational experiment must not
disable a security guard, expand private-data access, change credentials, enable
native hooks or bypass a target refusal. A limit serving a protective purpose
cannot be reclassified merely because it blocks progress. Use approved test
identities and synthetic or otherwise authorized data. If a safe experiment
cannot be made, state the exact boundary and leave the dependent cause unknown;
continue independent authorized work. This method grants no production mutation.

If the intended baseline also fails, localize its **first failure** and restore a
working baseline before testing the suspected restriction. Do not put restrictions
back over a broken baseline and interpret the resulting failures as their effect.
For a necessary limit adjustment on an actual target, retain its existing explicit
setter, ownership, authority, readback and rollback requirements.

Retain failed-baseline evidence and partial outputs. Use observed elapsed time,
completed/remaining work, bytes, phases and the first boundary to select the next
distinguishing experiment and justify its finite resource profile. State the
remaining uncertainty, expected new information, maximum duration/resources and
stop conditions before launch. Do not cycle through known-insufficient profiles
or repeat identical checks that add no knowledge. There is no automatic limit
escalation or permission to exceed an approved ceiling; a further profile needs
its existing scoped authority. A grouped profile change may establish a working
baseline, but does not identify one factor's cause. Restore restrictions one at a
time only after that baseline succeeds.

### Isolate the factor and demonstrate reversal

Choose each experiment to discriminate between named hypotheses or to verify a
specific correction. State the differing predicted outcomes before executing it.
Change one factor while holding data, scenario, initial state, versions, other
settings, observation method and load fixed. Reset mutable state equivalently
between runs and record any unavoidable difference. If many factors are involved,
a bounded binary search may locate a group; then isolate the individual factor.
If an effect requires a combination, test the combinations explicitly and name
the interaction. Group removal or changing several settings at once is not proof
of a single cause.

For two binary factors, observe all four states: neither enabled, each enabled
separately, and both enabled, with other factors and initial conditions fixed.
Do not infer an unmeasured reference state from assumed monotonicity or knowledge
of the implementation. If a state cannot be tested safely, identify the observed
states and keep the broader interaction claim partial.

Demonstrate a reversible sequence: **working configuration → failure → restoration
→ repeated failure**, with primary evidence for all four steps. For example,
with two actually overlapping requests and unchanged data/authentication, a finite
admission limit of 2 succeeds, 1 rejects the second request, 2 restores success,
and 1 repeats that rejection. Observe actual overlap and admission state; merely
requesting concurrency or reading a configured value does not establish either.
Connect the controlled factor to the first failing boundary and the user's
criterion. Temporal correlation and a single successful retry are insufficient.

Use only reversible, authorized effects. A failed or unknown external operation
is not permission to replay it for this sequence: reconcile its original operation
identity through the existing route first. When reversal cannot safely be tested,
retain partial observations, explain the limitation and keep the causal claim
unconfirmed. A synthetic reversal establishes only that experiment's scope;
claiming the historical or target incident's cause requires matching evidence.
An interrupted or stopped chat does not prove that an external process stopped.
Restore the original operation ID, inspect its durable result and actual effects,
and preserve UNKNOWN when evidence is insufficient. A new session, operation ID
or transport is not permission to repeat that effect.

### Keep a compact experiment journal

Keep the journal with the existing work/bug/incident record, linked by the current
writer. Do not create a competing status ledger or copy private payloads into
public reports. Retain the experiment ID, named hypotheses and differing forecasts
before launch. Record every discriminating run, including failed baselines:

| Step | Factor and actual value | Fixed conditions | Hypothesis and forecast | Actual result | Error and first failing location | Evidence reference | Conclusion and next step |
|---|---|---|---|---|---|---|---|
| Experiment/run ID | Effective setting or controlled input | Exact relevant pins, fixture, initial state and load | Named alternatives and their predictions, retained before the run | Observed criterion and response/exit | Safe code and boundary, or none | Primary retained receipt/artifact | What changed in knowledge; next discriminating action |

Label **hypothesis**, **observation**, **confirmed conclusion** and **unknown**
separately. A receipt proves only its actual scope. Retain failed observations
alongside later successes and record the reason for any repeated check. If a run
adds no information, revise the experiment instead of collecting the same symptoms
again. Identify bottlenecks in diagnosis itself: slow tools or remote calls,
unprepared data, redundant checks and unnecessary sequential execution. Prepare
stable inputs once and parallelize independent observations without changing a
controlled experiment or creating competing writers.

At existing checkpoints, assess the investigation's own bottleneck: elapsed work
and waits, slow remote access, unprepared local Linux environment/data, missing
declared dependencies, repeated checks or needless serialization. Remedy a
material bottleneck within current authority and verify the effect; otherwise
state the exact boundary and next owner/action. Do not leave a solvable setup
problem as a permanent blocker. Use subagents for useful independent work and
review, with one owner for each changed file and environment. This adds no fixed
checkpoint timer or authority to alter a protected environment.

### Correct, verify and continue

After establishing the cause, make the smallest correction that satisfies the
contract. Re-run the original user scenario, relevant boundaries and regressions,
and exercise rollback where applicable. A mitigation may be useful before proof;
identify it as a mitigation and keep the cause unresolved. Do not present an
isolated or synthetic success as a working-product fix.
For resource/admission changes, exercise the relevant capacity boundary, actual
resource release and the contracted refusal or queue behavior; a successful
request below the limit alone does not establish those properties.

Report these stages separately, with the exact source, artifact and evidence:

| Stage | Evidence needed for the stated scope |
|---|---|
| PREPARED | Reviewable correction and its exact basis exist. |
| LOCALLY_VERIFIED | The local scenario and relevant checks actually passed. |
| INSTALLED | The authorized target installation and readback are confirmed. |
| TARGET_VERIFIED | The original scenario actually passed in the target environment. |

Artifact status is a separate dimension. A checksum, retained partial or
`SEALED` label establishes only its verified artifact contract; it does not prove
source completeness, representativeness, successful restore or product acceptance.
An actual restore also establishes only the verified restored scope. Keep missing
required/optional work and the original user criterion visible.

For result handoff, follow the existing [coordination](WORK_COORDINATION.md),
[completion](COMPLETION.md) and [durable handoff](INDEXED_HANDOFF.md) contracts as
applicable. Keep prepared, send-uncertain, recipient-received and semantically
accepted results separate; use their existing states rather than a second ledger.
A visible sent message or sender enqueue is not durable preservation or confirmed
recipient receipt. Verify retained bytes/readback and the actual receiving-side
evidence before declaring delivery complete. A receiver ACK is not semantic
acceptance; a reviewed result may still be held or partial. Reconcile an uncertain
send by its original identity before another attempt.

These are reporting stages, not replacements for existing task/Atlas statuses.
On continuation, restore the user criterion, reproduction/baseline pins, journal,
current effective configuration, confirmed/unknown findings and next experiment.
Recheck changed dependencies; reuse unchanged applicable evidence. Installation,
document pickup and agent behavior remain distinct. For substantial changes to
diagnostic behavior, qualify the affected scenarios in proportion to risk, using
fresh-session behavior where needed. Select relevant cases such as one restriction,
a failing baseline, interacting factors, non-reproduction, a protected data/access
boundary or continuation with an existing journal and uncertain operation.
A default-method or routing change alone does not require the full fresh-session
diagnostic set. Requirements for claims of causality remain unchanged.
Evaluate the experiments actually chosen, preserved history, reconciliation
and conclusions, not just the presence
of this text. A fresh planning exercise can test interpretation of partial
evidence; it does not execute or establish the source incident's next result.

<!-- agentos:causal-debugging:end -->

<!-- agentos:crystal-microscope:start -->
## Crystal microscope

Use **Crystal Microscope** to connect system structure, the path of an actual
result and the cost of producing it. **Lab** is an isolated experimental stand,
not another development level. Apply the common Solution integrity laws. Read
[the full method](CRYSTAL_MICROSCOPE.md) on first use and restore relevant parts;
read [observability guidance](CRYSTAL_MICROSCOPE_OBSERVABILITY.md) before a new
collector. Reuse the existing project plan, dossier, journal and evidence.

1. Fix the original question, expected useful result, actual revision/deployed
   build, scenario, inputs, environment, current writer and authority. A source
   checkout is not proof that its implementation is loaded. Keep UNKNOWN explicit.
2. Keep three related views: structure, observed execution and measured cost.
   Separate containment from calls, asynchronous messages, data flow, ownership,
   waits, state/recovery and correlation. A call tree alone cannot describe them.
3. Zoom from the user result through components, contracts, tasks/queues, functions,
   actual library methods and supported runtime/OS/hardware evidence only as far
   as a material question requires. Record applicable inputs, outputs, units,
   invariants, errors, cancellation, concurrency, lifetime and recovery. Do not
   invent private/closed internals, missing symbols or an irrelevant HTTP API.
4. Distinguish declared, source-verified, runtime-observed, experiment-supported,
   hypothesis and UNKNOWN. Every numeric result or estimate needs its definition,
   units, run/scenario, method, primary evidence, sample/aggregation, clock and
   interval, inclusion/overlap, overhead and limits. UNKNOWN is not zero. Wall is
   not CPU time, cumulative allocations are not RSS, zero allocations do not mean
   no copying, and logical bytes are not physical RAM traffic. Source listings,
   samples and counters do not establish an exhaustive execution trace.
5. Locate the last correct and first incorrect state. Test a mechanism against an
   independent expectation and a case that can disprove it. Compare alternatives
   on the same useful work and contracts, including relevant error, ownership,
   cancellation and recovery behavior; verify the parent path and user effect.
   A faster wrong or incomplete response is not an optimization of the same task.
6. For research, trace source/data vintage, transformation/model and interpretation.
   Preserve what was available at the decision time; distinguish association,
   hypothesis, evaluated forecast and causation. Human-facing event/news markers
   must expose readable content or summary, source and meaningful timestamps;
   explain axes, units and uncertainty without making users decode internal IDs.
7. Keep one versioned canonical model and lossless views/exports. Preserve source
   references, contracts, experimental variants, unknown fields, zero and UNKNOWN.
   Detect and explicitly confirm a changed same-ID replacement; retain recovery.
   Check roundtrip and actual required human navigation. A reproducible viewer
   proves packaging, not the measurements or the user's product.
8. Keep behavior checked, cost measured, mechanism supported, alternative compared,
   user effect verified, prepared, installed and target-verified distinct. Preserve
   accepted partial results and concrete remaining work. Finish the investigation
   when it sufficiently supports the next authorized decision; continue that work.

Preserve the selected development level and scope. At level 1 keep the connected
modular whole, simple implementations or explicit stubs, useful debug and error
journal; zoom only into the selected risk. Levels 3 and 5 scale relevant immediate
coverage without changing truth or authority. A temporary diagnostic 0 may use
the map, then returns to the retained 1–5 choice. Loading this method changes
neither a level, active diagnostic run, task state nor readiness.

Reading existing evidence, starting instrumentation and fault experimentation
have different effects. Use existing rights, qualified host routes and owned
bounded resources. Preserve explicit bans on OS/kernel/CPU/memory/driver/security/
power changes. Do not weaken access controls, clear another tracer or consume an
unbounded recording to fill a map. An unsupported observation stays UNKNOWN.

The bundled `crystal-microscope` skill offers an optional offline JSON validator,
viewer and exact-byte export. It does not collect profiles, execute inspected
code, contact hosts, verify supplied claims or grant permissions. Existing richer
project viewers need no compulsory migration. Delegate independent useful parts;
the coordinator retains responsibility for integration and acceptance. Record
small steps in the existing journal, issue owner updates when meaningful, and
package a full archive for transfer, recovery or release rather than every edit.
<!-- agentos:crystal-microscope:end -->

## 6. Close only a registered task

Update documents to reflect the result and register their new hashes. Run the
exact approved checks, then `assess`, then `close --review review.json` (or
`--review -`). Review every acceptance criterion and required document, scope,
limitations, and next step. The task, revision, policy, source, and logs must
match; the latest relevant checks must pass and be no older than 24 hours. No
out-of-scope change may remain. Local closeout uses only `not_requested` or
`pending_target_verification` as deployment status.

`project verify-closeout --root P --task TASK` reads whether a CLOSED result still
has current source, documents, logs, policy, and evidence. CLOSED remains a
historical fact if later work makes that evidence stale. For unfinished
registered work, use a truthful checkpoint with `complete=false`. A failure
before entry has no task to close. A read-only answer ends normally; there is
no Stop requirement.

## 7. Optional audit record

Use `project observe --root P --session S --turn T --answers audit.json` only when
there is a reason to record bounded read evidence or hashes. It writes a
separate observation in the user home and does not create or change a project
task. Reusing the same session, turn, and root is rejected rather than silently
overwritten. API or mail reading requires no such record. An observation does
not prove external API completeness or that a disk never changed.

For provider selection and target-policy diagnosis, follow
[PROVIDER_INDEPENDENCE](PROVIDER_INDEPENDENCE.md). Public project work requires
no private kernel, fleet controller or notification service. Preserve actual
target controls; missing optional reporting does not block local completion.

## Historical: Main coordination successor0.7.0rc2

For continuing work, follow [WORK_COORDINATION](WORK_COORDINATION.md): child/session completion never closes the original parent goal. Record each verified result, remainder and owned next action; preserve independent work during checkpoints and reconcile unknown effects before retry. The optional synchronous ledger does not supply an always-running client.

## Explicit completion and recovery

Follow [the completion contract](COMPLETION.md) for bounded continuation, current target scope, confirmed handoff and safe recovery. Turn completion leaves the project open until independent current evidence satisfies the original goal. Source implementation and documentary checks do not establish host adoption or publication. The local validation chain includes `python3 tools/verify_completion.py`; GitHub Actions remain unused.


## Explicit per-project source inventory budget (local candidate)

The source inventory defaults remain 20,000 files and 128 MiB total bytes. Every
regular file still contributes its complete SHA-256; no evidence path is excluded
by this setting. Large evidence projects can explicitly opt in with:

```sh
agentos project inventory-budget --root P
agentos project inventory-budget --root P --max-bytes 536870912
agentos project inventory-budget --root P --max-files 40000
agentos project inventory-budget --root P --reset
```

The validated optional `inventory_budget` project field has schema
`agentos.project-inventory-budget/v1`, integer `max_files` in 1..40000 (default 20000), and integer
`max_bytes` in 1..17179869184 (booleans rejected). The setter uses the existing
project lock and atomic metadata writer; it does not alter tasks or evidence.
Readback reports the explicit/default choice and project revision. Identical
settings are a no-op. Reset removes the override and restores 128 MiB and 20000 files.

Explicit budgets are included in policy digests and source snapshots. A change
invalidates existing READY/check evidence until the normal re-entry and READY
workflow is completed; old receipts remain historical. Omitted settings preserve
previous policy digests. This setting grants no external authority and does not
change containment, symlink, directory-link attestation, file-limit enforcement, or hooks.
The snapshot still hashes ordinary files with the existing implementation; the
bounded total budget is not a hostile same-UID filesystem sandbox.

Every effective setting change also increments project `inventory_budget_revision`
(integer 1..2147483647, fail closed on exhaustion). Reset retains this generation,
so returning to a previous byte budget cannot resurrect old READY/check receipts.
Policy/snapshot include the generation after first use; untouched projects retain
exact historical digests. A no-op neither increments nor invalidates.


## Owner-local finite capacity successor 0.8.0rc2016

The supported maximum explicit per-project byte budget is 16 GiB. The default remains 128 MiB and the default file budget remains 20,000; an explicit per-project file budget is bounded at 40,000. Only an explicit supported project setter opts into a larger budget; every path and full content SHA remains in the inventory. No evidence exclusions, guard skips, symlink relaxation, secret scan exception or external authority is introduced. Re-entry and current READY are still required after a policy change. This owner-local version is not an upstream release. ATLAS_SOURCE retains historical source-base hashes; those are not current PROCESS pins. The selected coordinator PROCESS edge is updated; prior WORK_COORDINATION indexed mismatch is retained.


### Optional lock-bound inventory setter predicates (rc2016)

Set/reset may supply BOTH `--expected-project-sha256 SHA256` and
`--expected-budget-revision N`. The digest is exactly 64 lowercase hexadecimal
characters over the current `.agentos/project.json` bytes; revision is an exact
integer 0..2147483647 (0 for an untouched legacy project, booleans rejected in the
typed API). Both current comparisons run inside the existing project write lock
before any project metadata write, including a no-op. One predicate, malformed
values, stale digest/revision or predicates on a read-only call fail closed.
The typed API names are `expected_project_sha256`, `expected_budget_revision`.
Omitting BOTH preserves legacy read/set/reset. Readback grants no authority.
Re-read and reconcile after mismatch; never automatically retry a changed target.

The finite maximum is 17179869184 bytes (16 GiB); default remains 134217728 bytes
and default max_files remains 20000; explicit max_files is bounded at 40000. This raises a reader ceiling without allocating disk.
All source files/content hashes and existing safety checks remain included. At
either ceiling STOP; no automatic expansion, guard skip or evidence exclusions.
Once a project stores a value above 4294967296, rc2015 cannot read that project.
Preserve a compatible forward reader; automatic downgrade or metadata reset is
forbidden. Isolated installer rollback does not prove project downgrade safety.


### Optional finite per-project file budget (rc2017)

`--max-files F` / typed `max_files=F` accepts exact integer1..40000, rejecting
booleans/floats/overflow and malformed records. Global defaults remain20000 files
and128MiB; max_bytes ceiling remains16GiB. The exact budget record keeps its
three fields and schema version. Omitted max_files preserves EFFECTIVE current
file budget on byte-only update; omitted max_bytes preserves EFFECTIVE current
byte budget on count-only update. Both can be set together. Reset conflicts with
either setter input and restores BOTH defaults through the existing monotonic
generation; an untouched read keeps legacy default/digest bytes. Optional paired
CAS predicates remain strictly typed and checked under the existing write lock
before any project write/no-op; current Root mutation must supply BOTH.

Source policy/readiness invalidation and historical evidence retention are
unchanged. This does not change safeio walk/hash/alias/content checks or SKIP;
every accepted file is fully hashed. Further byte/file guard refusal means STOP
and qualification of the first boundary, never automatic expansion/exclusions.
Whether40000 suffices for any real corpus is UNKNOWN until separately authorized
Root source proof. Once a project stores max_files other than20000, rc2016 cannot
read it: retain a compatible forward reader; no automatic downgrade/reset.


### READY task metadata bound (rc2017)

A finite file inventory does not guarantee that its full READY task fits the
default4MiB task JSON reader; explicit rc2018 project task policy may select up to32MiB. READY serializes the complete future task with the
existing UTF-8 JSON formatting and checks its exact byte length before the atomic
task write or READY event. Above the effective task ceiling (4194304 by default) it fails with
`ready_task_metadata_limit`, preserving the prior task and history. Exactly the selected task ceiling
is accepted; the generic JSON reader stays4MiB. No source-map truncation, compression,
external storage, recovery route or global metadata-limit expansion is introduced.

Actual full corpus and task overhead must be qualified separately; synthetic
40000-path success/failure is not a real-project compatibility claim. Other
metadata writers and future receipt growth remain unchanged and retain their
existing reader limits. A refusal remains an explicit compatibility boundary.


## Explicit per-project TASK metadata budget (rc2018)

`project task-metadata-budget --root P` reads optional task_metadata_budget.
`--max-bytes N` or `--reset` explicitly changes project policy; optional PAIRED
expected-project-sha256/expected-budget-revision are compared under existing lock
before no-op/write. This command uses task_metadata_budget_revision, not inventory
budget revision. Exact record: schema agentos.project-task-metadata-budget/v1,
max_bytes integer4194304..33554432 (booleans/floats/extra fields rejected).
Default4MiB for untouched projects. Changes increment policy generation/project
revision and invalidate READY normally; reset retains generation. Byte-identical
legacy digests when both policy fields were never present. Lowering/reset is
refused when oversized tasks or unclassified retained preimages prevent bounded
compatibility proof; never delete/reset history to force it.

Only task.json and its typed lifecycle before/after/raw backup/readback rows use
this ceiling. Global safeio/project/turn/events/requests/provider/privacy limits
stay fixed. Full source map remains inline, no storage migration/compression or
truncation. Inventory16GiB/40000 unchanged. Entry/current READY/check/close/checkpoint
task writes are bounded before their task write, with exact readback. Existing
external checks/handoff side effects retain their authority and unknown handling.

Continuation embedded journal remains24MiB including base64 pre/postimages and
retarget history: an allowed32MiB task can fail journal eligibility. Refusal small
journal/request/permit caps and non-task row limits stay fixed; staged TASK raw
rows alone follow project policy. Handoff objects still16MiB/scanners unchanged.
No universal32MiB lifecycle guarantee. Ineligible route STOP, no auto cap increase,
new recovery route or replay. Legacy reader cannot read task>4MiB; preserve a
compatible forward reader/policy while such tasks/preimages exist. No auto downgrade.
