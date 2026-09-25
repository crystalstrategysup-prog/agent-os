# Данные и документация

## Сущности

`.agentos/project.json`: identity, name, types/features, source-backed context, registry docs,
active_task, revision. `.agentos/tasks/<id>/task.json`: answers, selected docs, status,
revision, session/turn, ready baseline, receipt IDs, closeout/checkpoint. Текущие документы
в docs/agentos или другом зарегистрированном проектном пути; не в runtime package.
Каждый registry entry: path, owner, source, summary, sha256, reviewed_at, revision, task_id.

Evidence: JSON receipt + очищенный log; task_id/revision/policy/source before/after/argv,
return code, timestamps, executor module hash, log hash, foundation version. Последняя
проверка с данным check_id определяет результат; предыдущий PASS не перекрывает новый FAIL.

Статусы: INTAKE → READY → VERIFYING → CLOSED; промежуточный CHECKPOINT не завершение.
Resume увеличивает revision, сбрасывает READY и receipts. Старые evidence файлы сохраняются
как история, но не участвуют в новом результате. Source snapshot исключает .agentos,
docs/agentos, build caches, venv, node_modules; их checks независимы.
Все документы вне docs/agentos остаются частью source, даже зарегистрированные: регистрация code-файла не позволяет исключить его из доказательств. File count≤20000,
total bytes≤128MiB: большой проект надо осознанно дробить, не молча урезать снимок.

## Пользовательская папка

config.json — community-config/v5; overlay.json — agentos.user-overlay/v1;
knowledge/INDEX.json — индекс с provenance; preferences — персональные решения;
projects — ссылки; extensions — metadata вне ядра; state — explicit turn/dispatch/import receipts;
state/observations/<digest>.json — необязательные независимые read-only audit receipts;
backups — предыдущие конфигурации/интеграции; secrets — локальное хранилище не для архивов.
Новая папка приватна (0700), создаваемые config/state файлы 0600. Existing source docs
могут быть 0644 как публичные материалы. ACL/дисковое шифрование остаются обязанностью хоста.

Env: explicit --home > AGENTOS_USER_HOME > legacy AGENT_OS_HOME > ~/.agentos-user.
Если оба env расходятся без explicit --home — BLOCKED. Установочный root и user root
не могут совпадать или вкладываться. Симлинк конечного user root отвергается; resolved
containment обязателен и при переопределённом AGENTOS_CORE_HOME.

## Миграции и срок хранения

Import проверяет точный manifest, schema, SHA, allowlist путей; отсутствующие файлы создаёт,
совпадающие сохраняет, отличающиеся не перезаписывает. Полный preflight перед записью;
при I/O сбое возможен частичный create-only import, повтор идемпотентен. Это не транзакция
всей ФС. Config migrate делает backup с SHA имени и readback; unknown keys сохраняет.
Неподдерживаемая future schema блокируется, downgrade нет. Никогда не импортирует secrets/state.

Автоочистки evidence/backups/history нет. Пользователь задаёт сроки хранения по содержимому
и требованиям проекта; не выдумывать юридический retention. Перед удалением — отдельный
scope/authority, export проверенных метаданных и восстановительная проба. Чувствительные
логи не публиковать; встроенная redaction эвристическая и не гарантирует отсутствие секретов.

## Изменение поведения beta.5 без schema migration

turn/v1 остаётся форматом явной project-привязки, не создаётся на каждом prompt.
Unbound INTAKE_REQUIRED/OBSERVATION_RECORDED не блокирует новый explicit enter;
существующая bound task требует прежних корректных переходов. Старые receipts не удаляются.
Новые optional observation receipts keyed по session/turn/root и не перезаписывают task state.
Same-scope reuse не наследует authority. verify-closeout читает CLOSED, но не переписывает
его при устаревании evidence. Смена foundation_version/module SHA делает старые checks
неактуальными; история сохраняется, новая приёмка требует новых checks.
