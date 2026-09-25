# Совместимость и известные ограничения

|Область|Статус beta|Условие использования|
|---|---|---|
|Python CLI / project lifecycle|Реализовано; локальные тесты|Python>=3.11, bounded local tree|
|POSIX managed installer|Реализован; local Darwin arm64 install/update/rollback fixture PASS|Linux wheel smoke PASS; полный Linux installer fixture не выполнен; Windows installer не поддержан|
|Codex AGENTS / skills / hooks|Реализован адаптер|Фактическая поддержка, features, native trust, новая сессия|
|Иной агент + MCP|Discovery/planning|Нужен собственный lifecycle adapter для write enforcement|
|Config community v1–v4|Сохраняющая миграция в v5|Явный apply, backup, unknown keys retained|
|User overlay v1|Create-only import|Не содержит live secrets/state|
|Унаследованный public Session Hub|Dispatch fail-closed|Нужен exact bound intake, отдельный frontend onboarding ещё отсутствует|
|Private fleet/owner authority runtimes|Не являются public-core feature|Не перезаписывать; нужны extension contract/parity/target evidence|

Изменения относительно 0.4.0: user default ~/.agentos-user вместо ~/.agent-os,
legacy AGENT_OS_HOME понимается; одновременные различные env блокируются. Schema v5.
Кодексовские dispatch требуют fresh exact task contract и одноразовую receipt; это сознательное
ужесточение, не прозрачная совместимость старой Telegram кнопки. Содержимое приватных fork
не копируется в public wheel под видом настроек. Model IDs в унаследованном config — сохранённые
строки, их доступность клиент/аккаунт должен проверить. Никакого молчаливого fallback к другой модели.

Linux smoke выполнен в `python:3.12-bookworm` на arm64: чистый wheel install,
`init`, `doctor`, package resources и MCP initialize прошли. Это не проверка
нативных Codex hooks или installer rollback на Linux. Windows runtime не проверен.

Ограничения: не distributed DB; один active stage на проект; физические source limits;
semantics reviewer; evidence не внешне подписана; невозможно остановить любой сторонний
клиент из stdio MCP; install→integrate→trust не единая атомарная транзакция. Partial overlay
import не удаляет файлы и допускает retry, но не является all-or-nothing. Interrupted release
не автоудаляется. Native hooks API может развиваться; сверить фактическую версию прежде, чем
включать для реальной работы. Никакого claiming COMPLETE при несовместимом payload.
