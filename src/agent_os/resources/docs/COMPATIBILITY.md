# Совместимость и известные ограничения

`0.5.0` / `0.5.0` — версия исходников; публикацию и установку проверять отдельно.
Краткий AGENTS.md — рекомендация маршрутизации без нового lifecycle gate; read-only путь не меняется.
Исторические F01…F08 результаты относятся к своим source/wheel, не к этому патчу.

|Область|Статус кандидата|Граница|
|---|---|---|
|Python CLI / lifecycle|Реализация и локальные Linux tests|Python>=3.11; конкретные env/results в handoff|
|Codex integration|AGENTS/9 skills, no-hook fixture tests|Fresh-session Mac readback ещё обязателен|
|Native hooks|Исключены; legacy CLI entrypoints retired no-op|Не включать/восстанавливать; не заявлять runtime enforcement|
|Managed POSIX installer|Сохранённый исходный механизм|Этот review не устанавливает на Mac и не переключает current|
|Windows|Managed installer не реализован/не проверен|Импорт Python не доказывает полную поддержку|
|MCP stdio|Те же шесть planning/status tools|entry_required_every_task=false; нет arbitrary writes|
|Config community v1–v4 / v5|Прежняя сохраняющая миграция|intake/closeout invariants scoped к project changes|
|User overlay v1 / profile v1|Без schema migration|Owner instruction edits отдельно; selection hashes нужно обновить явно|
|Legacy Session Hub|Прежний fail-closed dispatch contract сохранён|Требуется task-bound capability; не full private parity|

Изменение поведения намеренно: project questions/observe больше не глобальная входная
процедура, hook callback не создаёт turn и не блокирует Stop. Сохранённые bound task receipts
можно перевести явным next-turn после реального checkpoint/close; unbound prompt receipts
не блокируют entry. Optional observations теперь state/observations, старые не удаляются.

Версия/core module SHA входят в check receipts. После смены ядра старый PASS не свежий:
для незакрытого этапа resume+READY+checks; CLOSED остаётся историческим и verify-closeout
может вернуть stale. Не переписывать старую evidence и не переоткрывать CLOSED.

Модели/auth в legacy config не меняются, их доступность проверяется клиентом. Нет скрытого
fallback. Нет runtime hooks, общего sandbox, distributed DB, externally signed receipts,
remote parity proof или атомарного install+integrate. Owner/Mac active profile по частичному
экспорту не доказывается; требуется живой readback. Откат old core не должен запускать его
старый integrate или восстанавливать hooks из backup.
