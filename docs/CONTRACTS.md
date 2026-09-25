# Интерфейсы и совместимость

Машинные источники истины: `schemas/mcp-tools-v1.json` (точная копия в wheel:
`agent_os/resources/contracts/mcp-tools-v1.json`), `schemas/cli-contract-v1.json`,
`schemas/project-task-v1.schema.json`, `schemas/project-event-v1.schema.json` и
`agent_os/resources/schemas/*.schema.json`. Тесты сверяют опубликованные MCP
`inputSchema`/`outputSchema` с `tools/list` и фактическими `structuredContent`, а
task/event schemas — с записями реального локального lifecycle.

Версия выпуска для человека и MCP: `0.5.0-beta.6`; эквивалент Python packaging:
`0.5.0b6`. `agentos --version`, `agent_os.__version__` и `serverInfo.version`
совпадают буквально. Протокол stdio MCP остаётся `2025-06-18`. HTTP API нет, поэтому
OpenAPI/Swagger здесь не существует; события пишутся локально в JSONL и описаны
JSON Schema, а не AsyncAPI.

## CLI

Все команды выводят JSON, кроме справки/интерактивных вопросов. Ошибка foundation gate:
`{"status":"BLOCKED","error":"..."}`, exit 2. PASS/план/успешное выполнение: exit 0.
`project check` возвращает FAIL+exit2 для ненулевого процесса или изменения snapshot.
Оригинальные community-команды могут иметь прежние error shapes; callers не должны
обрабатывать их как новый project contract. `--home`/`--user-home` задаются перед командой.

|Группа|Команды|Контракт записи|
|---|---|---|
|project|init, questions, enter, next-turn, document, ready, check, assess, verify-closeout, status, close, checkpoint, gate, snapshot|Только явные действия в указанном проекте; вопросы/чтение без product writes|
|project observe|--root --answers --session --turn|Только user receipt, без .agentos в проекте|
|overlay|status, index, import, migrate-config|import/migrate план по умолчанию; apply явно|
|profiles|inventory, select, context, interview|Профили и выбор только в указанном user home; `select` — явная запись|
|integrate codex|--codex-home --skills-home --apply|AGENTS/skills, backup; hooks/config/trust не меняются|
|resources|--list|Путь к установленным схемам, шаблонам, навыкам, документации|
|hook|Retired compatibility entrypoint|Пустой JSON, exit0; stdin/home не читаются, записи нет|

`profiles inventory` показывает хеши, bindings и конфликты заявленных полей.
`profiles select --mode none|one|all` сохраняет выбор в `state/profile-selection.json`;
для `one`/`all` нужен актуальный `--inventory-digest`, для `all` — все ID в порядке,
заданном владельцем. Разные значения одного ключа требуют JSON `--decisions`
с выбором ID для каждого такого ключа. `profiles context` выдаёт только выбранные
поля или `STALE_SELECTION` при дрейфе; `profiles interview` добавляет живые факты
устройства и вопросы по неизвестным полям. Поля профиля не дают новых полномочий.

Session/turn предоставляются настоящим клиентом. При CLI-only испытании задаются явно;
это не доказывает hook_seen. После checkpoint/close `project next-turn` с точным
`--from-turn` обновляет только CLI receipt; native-hook receipt он не принимает. Совпадение
session/turn/root обязательно. Request для legacy
dispatch должен совпасть с objective и destination_session; receipt потребляется однократно,
даже если downstream запуск упал. Для повторной попытки требуется новый проверенный turn.

## MCP stdio

Protocol version сохранён 2025-06-18; serverInfo version = package __version__.
JSON-RPC initialize, tools/list, tools/call, ping. `tools/list` отдаёт входные и
выходные схемы для шести tools:
agentos_get_telegram_setup_plan; agentos_normalize_task; agentos_doctor;
agentos_get_project_entry_plan; agentos_select_documents; agentos_get_foundation_status.
Последние два получают types/features и metadata, без полного чтения знаний или secret bodies.
Unknown argument/tool возвращает tool error. HTTP/OpenAPI здесь не применимы: сервер stdio.
MCP не регистрирует автоматически AGENTS/hooks в любом клиенте.

## Retired native callbacks / explicit workflow

Native hooks исключены. `agentos hook` / `agentos-hook` — retired compatibility entrypoints:
stdout `{}`, exit 0, не читают stdin/home/config и ничего не пишут, не возвращают allow/deny
или COMPLETE. integrate не регистрирует их; hook input/output schema files сохранены лишь
для исторической совместимости, не обозначают активный hook protocol.

`workflow route --kind question|search|audit|discovery|project-change` необязателен и stateless.
Повторяемый --effect: local-project-write, external-send, production-write, runtime-write,
db-write, credentials, destructive, deploy. FAST_PATH/DOCUMENTATION_FIRST — exit0;
TARGET_AUTHORITY_REQUIRED — BLOCKED/exit2. external_authority_granted=false всегда.

Все --context/--answers/--review принимают JSON object stdin через `-` (4 MiB,
no duplicate keys), обычные пути — только regular files без symlink. questions --resume-task
предлагает known answers без authority; enter --resume-task --reuse-answers требует текущий
authority, допускает только прежний scope, сбрасывает readiness/check receipts. Новые поля
questionnaire suggested_answers/reused_from_task/reuse_scope — additive.

project verify-closeout — read-only current proof зарегистрированного CLOSED результата.
Local CLOSED не означает remote deployed. project observe — optional state/observations
receipt; не связывает и не перезаписывает task/turn. Abandoned unbound turn receipts
заменяются лишь explicit enter; conflicting bound tasks остаются заблокированы.

MCP entry plan сохраняет deprecated entry_required_every_task=false и добавляет
entry_required_for=project_changes, read_only_intake_required=false, native_hooks=DISABLED.
Точные JSON shape/version — schemas и проверяемые copies в wheel.

## Пользовательские расширения

`extensions/registry.json`: schema agentos.extension-registry/v1, entries с id,
provider_kind, enabled, source, core_api, data_schema, authority и verification_status.
В beta реестр описательный, код расширений **не исполняется автоматически**. Adapter должен
реализовать discovery/health/read-only capabilities, затем explicit task-bound execution;
написание такого adapter — самостоятельный stage с угрозами/контрактом/tests.
Подмена knowledge файлом исполняемой private ветки запрещена. Отсутствие переносимого provider
фиксируется как gap, старый runtime сохраняется, а не объявляется мигрированным.
