# Регламент проекта и задачи

## 1. Вход — обязателен, повторный допрос — нет

Триггеры: создать проект, изменить существующий, продолжить после паузы, новый запрос
в активной сессии, сменить проект/cwd или изменить scope. Hook UserPromptSubmit создаёт
новую запись INTAKE_REQUIRED. Прочитать README/AGENTS, досье, roadmap, текущий этап,
индекс пользовательских знаний. Отделить observed facts, owner requirements, assumptions,
unknowns. Известное не спрашивать повторно. Противоречия фиксировать со ссылками на источники.

`project questions --root P` выводит известный контекст и недостающие вопросы. До init
существующую систему сначала исследуют; создание метаданных не должно подменять понимание.
Для нового проекта init получает context.json: purpose, current_state, boundaries, constraints.
Можно указать несколько --type и --feature. Не притворяться, что project type определён автоматически:
агент выбирает его по фактам, script детерминированно объясняет выбранные документы.

## 2. Контракт входа

```sh
agentos project init --root /work/project --name Example --type backend --feature database --context context.json
agentos project questions --root /work/project --answers answers.json
agentos project enter --root /work/project --session SESSION --turn TURN --answers answers.json
```

В examples/ есть валидные context, task, review, observation формы. `--interactive`
задаёт только незаполненные строковые вопросы, сложные списки принимает JSON.
Операция enter обязательна даже при полностью известной анкете. Поля: цель, зачем,
результат, in/out scope, ограничения, устройство/способ работы, полномочия, kind,
разрешённые пути, критерии и mapping criteria→checks. Check — точный argv, timeout,
не свободный shell script. Интерпретатор в argv разрешён лишь как осознанно проверенная программа.

Один active task на проект. Для продолжения незакрытого — --resume-task с новой анкетой;
revision возрастает, READY и receipts сбрасываются. CLOSED не редактируется — новый task.
Если scope меняется в ходе этапа, сначала checkpoint, затем новый turn/entry или resume.
Изменение типов/признаков существующего проекта: пока нет отдельной revise-команды,
оформить архитектурный этап и контролируемо обновить project.json, затем **новый enter**;
check_ready блокирует старую policy. Не менять метаданные из-под READY.

## 3. Документация до реализации

Selection содержит обязательные doc IDs, причины и неприменимые IDs. Минимум:
досье, roadmap, контракт этапа, стратегия проверок. Для маленького проекта допустим
один содержательный Markdown с отдельными разделами, зарегистрированный для нескольких IDs.
Для API нужны контракты, для PII — карта данных/доступа, для эксплуатации — runbook и откат.
Все варианты форматов — в DOCUMENTATION_CATALOG.md; не создавать OpenAPI без HTTP API.

Скрипт создаёт **draft**, не доказательство. Reviewer заполняет фактами, обозначает источники,
неизвестное и измеримую приёмку. Документы регистрируют по одному:

```sh
agentos project document --root /work/project --id dossier --path docs/agentos/DOSSIER.md --owner Reviewer --source 'source inspection and owner task' --summary 'Verified purpose and boundary'
# Для stage дополнительно --task TASK; текст обязательно содержит этот TASK.
agentos project ready --root /work/project --task TASK --reviewer Reviewer
```

DoR: обязательные ответы, выбранные документы current и совпадают по SHA, stage привязан
к задаче, scope/authority/checks согласованы, reviewer назван. READY — не разрешение на
деплой или удаление внешних данных. Подготовка документов до READY разрешена специально.

## 4. Реализация и проверка

Работать только в approved paths. Не подменять результаты демо-данными. Сохранять
обратную совместимость либо явно документировать breaking change. Уточнение scope — новый вход.
`project check --check-id NAME` выполняет stage-approved программу с shell=False.
Timeout/ненулевой rc/изменившееся во время проверки source tree → FAIL. Лог ограничен
последними 200000 байтами; редактирование лога/кода после PASS делает evidence непригодным.
Проверки не sandbox: они могут менять внешнюю систему. Такие команды запрещены без отдельной
target authority; в fixture-контуре использовать tmpdir и изолированные тестовые данные.

## 5. Закрытие

Актуализировать docs по реально полученному результату. Повторно зарегистрировать изменённые
документы, затем assess и close. Reviewer обязан по отдельности принять все criteria,
перечислить все выбранные docs, подтвердить scope review и назвать ограничения/следующий этап.
Повторная регистрация docs сама по себе не делает их истинными; ответственность за смысл
остаётся за reviewer. Проверки относятся к текущему source hash; менять тесты после PASS нельзя.

DoD: текущие checks PASS, source/task/revision/policy/log совпадают, возраст ≤24ч,
нет out-of-scope, выполнена смысловая приёмка, текущая документация, truthful deployment status.
Локальный closeout разрешает только not_requested или pending_target_verification.
Существующий legacy assess-result — аналитическая подсказка, не заменяет этот closeout.

Если шаг заблокирован: checkpoint(reason,next_step), complete=false. Следующий исполнитель
сначала читает свежие документы и checkpoint. Stop hook не зацикливает пользователя:
повторный stop_hook_active сообщает NOT COMPLETE, но не выдаёт автоматический PASS.

## 6. Read-only

`project observe --root P --session S --turn T --answers observation.json` записывает
цель/зачем/полномочия/вывод/ограничения/следующий шаг и SHA реально прочитанных файлов только
в user home. Отдельный project init не нужен. Это не разрешает продуктовые tool writes.
Stop сверяет источники повторно. Такой режим не доказывает неизменность всего диска,
достоверность внешнего API или полноту проведённого аудита.
