# Процесс: чтение без барьеров, изменения через документацию

Норма кандидата `0.5.0-beta.6`. Native hooks исключены: не создавать, не включать,
не доверять заново и не восстанавливать при откате. Старые STAGE-F01…F08 — история,
а не действующее разрешение вернуть перехват запросов или Stop.

## 1. Сначала определить действие, не регистрировать каждый запрос

Обычный вопрос, поиск, read-only аудит кода/данных и discovery API выполняются сразу
в рамках уже имеющегося read-доступа. Не нужны `init`, `questions`, `enter`, `observe`,
answers.json, активный профиль или closeout. Незарегистрированный cwd допустим.
Унаследованный `AGENTS.md` держать кратким маршрутизатором: область применения,
несколько общих ограничений и ссылки на документы/навыки по типу задачи. Детальные
архитектура, операционные факты и датированная история лежат в адресных файлах,
которые читают по необходимости. Если файл длинный или клиент сообщает об обрезке,
сократить индекс и проверить его в новой сессии; это диагностическое замечание,
а не отказ в обычном вопросе, новый Stop hook или обязательная команда.
Создание файла отчёта, запрошенного пользователем, само по себе не изменение продукта;
но исправление исходников, настроек или runtime уже изменение, даже названное аудитом.

Необязательная команда `workflow route --kind audit` возвращает FAST_PATH и ничего
не читает/пишет. `--kind project-change` или `--effect local-project-write` возвращает
DOCUMENTATION_FIRST. `--effect deploy` (также external-send, production-write,
runtime-write, db-write, credentials, destructive) возвращает BLOCKED с точной
категорией требуемых полномочий. Это маршрутизация **объявленных** действий, не анализ
естественного языка и не проверка подлинности разрешения. Обычный вопрос не обязан
сначала запускать даже эту команду. Доступ к чужой почте/данным всё равно должен быть разрешён.

## 2. Подготовить реальное изменение

Сначала прочитать README, досье, roadmap, последний этап/результат, архитектуру и
контракты затронутых компонентов. Для неизвестного существующего проекта — read-only
обследование до scaffolding. Известные факты берутся из актуальных документов и
текущего поручения, не запрашиваются повторно. Уточняются лишь существенные неизвестные.
Профили загружаются только для релевантных фактов; NONE/STALE_SELECTION не блокирует
несвязанный вопрос. Нельзя применять устаревшие сведения о целевом хосте.

Если metadata нет, `project init --root P --name N --type TYPE --context context.json`
создаёт `.agentos/project.json` и черновики docs. Контекст содержит purpose, current_state, boundaries, constraints; точный список
полей — `project.CONTEXT_KEYS` и `examples/context.json`. Затем:

```sh
agentos project questions --root P --answers answers.json
agentos project enter --root P --session S --turn T --answers answers.json
```

Идентификаторы S/T — явно выбранные стабильные идентификаторы CLI workflow, не имитация
нативного события клиента. Использовать клиентские ID только когда они реально известны.
Подготовка context/answers/docs до READY разрешена; не использовать её для скрытой
продуктовой записи. Все JSON-входы context/answers/review поддерживают `-` как stdin:

```sh
cat answers.json | agentos project enter --root P --session S --turn T --answers -
```

Можно передать JSON из собственного процесса напрямую, не создавая answers.json.
Stdin ограничен 4 MiB, требует JSON object, запрещает дубликаты ключей. Обычные пути
остаются regular files без symlink: `/dev/stdin` не обход этой защиты.

## 3. Не спрашивать заново при продолжении

```sh
agentos project questions --root P --resume-task TASK
agentos project enter --root P --session S --turn T --resume-task TASK \
  --reuse-answers --answers current-authority.json
```

`current-authority.json` содержит текущий `authority`, остальные неизменные ответы
берутся из задачи. Authority не наследуется. Проверенные факты повторно используются
только при том же scope; изменение любого другого переданного поля требует полного
набора ответов без `--reuse-answers`. Новые задачи могут подавать заранее заполненные
ответы по актуальным документам; автоматического угадывания цели нет.
`--interactive` спрашивает лишь ещё отсутствующее. Возобновление сбрасывает READY
и evidence, повышает revision. CLOSED неизменяем: создаётся новая задача.

Один активный task на проект. После CHECKPOINT/CLOSED для того же workflow-session:
`project next-turn --root P --session S --from-turn OLD --turn NEW --task TASK`, затем
явный enter. Активная чужая привязка блокирует ошибочный вход. Незавязанные старые
prompt/observation receipts не мешают явному входу; связанные записи сохраняются,
пока реальная задача не закрыта или не checkpoint. Нативная provenance не является
правом исполнения; explicit next-turn не доказывает native enforcement.

## 4. Документы до реализации

Каталог выбирает только применимые слои по типу/изменению: досье, roadmap, stage;
для API — контракт, для PII — доступ/данные, для эксплуатации — runbook/откат.
Черновик не проходит READY. Reviewer заполняет факты, источники, неизвестное,
write-set, архитектурное решение, измеримую приёмку и откат. Затем для каждого doc:

```sh
agentos project document --root P --id dossier --path docs/agentos/DOSSIER.md \
  --owner Reviewer --source 'current source and owner task' --summary 'Reviewed facts'
agentos project ready --root P --task TASK --reviewer Reviewer
```

Для stage дополнительно `--task TASK`, task ID есть в тексте. READY проверяет хеши,
актуальность, соответствие stage/task и заявленного контракта. Это явная проверка,
а **не перехват произвольных tool calls**. Агент соблюдает границу, внешнее жёсткое
ограничение обеспечивается клиентом/ОС/целевым executor. Документы не дают production authority.

## 5. Реализация, точечные полномочия и проверки

Только approved write_paths. `project check --root P --task TASK --check-id NAME`
исполняет exact argv, timeout, собирает ограниченный лог и source-bound receipt.
Ненулевой rc/timeout/изменение source во время check → FAIL. Shell-интерполяции нет,
но `shell=False` **не sandbox**: программа может обращаться к сети/хосту. До запуска
нужны проверенные полномочия на её реальные эффекты. В локальной приёмке — tmpdir,
тестовые данные, отсутствие credentials и опасных executors.

Для внешних отправок, prod/runtime/DB writes, credentials, destructive и deploy
отдельно проверяются субъект, операция, точный объект/host/account, срок/lease,
лимиты и разрешённые эффекты. Разрешение на чтение не разрешает отправку; локальный
READY не разрешает production. Нет capability — остановить только соответствующую
операцию и продолжить разрешённую подготовку. Не добавлять универсальный --authorized.

## 6. Завершение только существующей задачи

Актуализировать и повторно зарегистрировать изменённые docs; выполнить точные checks,
`assess`, затем `close --review review.json` или `--review -`. Reviewer принимает
каждый criterion и каждый required doc, scope, ограничения и следующий этап.
DoD: task/revision/policy/source/log совпадают; последний check PASS, возраст ≤24h;
нет out-of-scope; документы current; смысловая приёмка проведена. Разрешены лишь
not_requested/pending_target_verification как deployment_status локального закрытия.

`project verify-closeout --root P --task TASK` без записи проверяет актуальность
закрытого результата, включая changed source/docs/log, policy и срок evidence.
CLOSED — исторический факт; последующая устарелость не переписывает историю.
Невыполненная зарегистрированная задача — `checkpoint --reason ... --next-step ...`,
complete=false. Ошибка **до создания задачи** сообщается прямо; не выдумывать TASK
и не требовать closeout. Ответ на обычный вопрос просто заканчивается. Stop отсутствует.

## 7. Необязательная фиксация аудита

`project observe --root P --session S --turn T --answers audit.json` — только по
явной необходимости хранить выводы/хеши прочитанных локальных файлов. Пишет отдельный
`USER/state/observations/<digest>.json`, не создаёт project metadata и не меняет
активную task/turn receipt. Повтор того же S/T/root отклоняется вместо перезаписи.
Никакой обязательной квитанции для чтения API/почты нет. Такой receipt не доказывает
неизменность диска, достоверность внешнего API или полноту аудита.
