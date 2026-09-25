# Интерфейсы и совместимость

Машинные источники истины: `schemas/mcp-tools-v1.json` (точная копия в wheel:
`agent_os/resources/contracts/mcp-tools-v1.json`), `schemas/cli-contract-v1.json`,
`schemas/project-task-v1.schema.json`, `schemas/project-event-v1.schema.json` и
`agent_os/resources/schemas/*.schema.json`. Тесты сверяют опубликованные MCP
`inputSchema`/`outputSchema` с `tools/list` и фактическими `structuredContent`, а
task/event schemas — с записями реального локального lifecycle.

Версия выпуска для человека и MCP: `0.5.0-beta.3`; эквивалент Python packaging:
`0.5.0b3`. `agentos --version`, `agent_os.__version__` и `serverInfo.version`
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
|project|init, questions, enter, next-turn, document, ready, check, assess, status, close, checkpoint, gate, snapshot|Только явные действия в указанном проекте; вопросы/чтение без product writes|
|project observe|--root --answers --session --turn|Только user receipt, без .agentos в проекте|
|overlay|status, index, import, migrate-config|import/migrate план по умолчанию; apply явно|
|integrate codex|--codex-home --skills-home --apply|Управляемые блоки, backup; native trust не меняется|
|resources|--list|Путь к установленным схемам, шаблонам, навыкам, документации|
|hook|JSON stdin|UserPromptSubmit пишет turn; PreToolUse/Stop читают gate|

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

## Native hooks

Схемы в resources/schemas и код hooks.py. SessionStart даёт пути core/user;
UserPromptSubmit перезапускает обязательный вход; PreToolUse до READY допускает
консервативный набор чтения и документарную подготовку, остальные local tools deny;
Stop требует свежий CLOSED или честный CHECKPOINT/read-only receipt.

Неподдерживаемая payload shape, отсутствующий turn/cwd или ошибка — не повод пропустить
контроль. Сопоставить adapter с реально установленной версией клиента. Не внедрять shim,
который придумывает turn_id только для получения PASS. Native trust выполняется клиентом.
Владелец решает разрешение на изменение безопасности; внешний Codex не может сам доверить hook.

## Пользовательские расширения

`extensions/registry.json`: schema agentos.extension-registry/v1, entries с id,
provider_kind, enabled, source, core_api, data_schema, authority и verification_status.
В beta реестр описательный, код расширений **не исполняется автоматически**. Adapter должен
реализовать discovery/health/read-only capabilities, затем explicit task-bound execution;
написание такого adapter — самостоятельный stage с угрозами/контрактом/tests.
Подмена knowledge файлом исполняемой private ветки запрещена. Отсутствие переносимого provider
фиксируется как gap, старый runtime сохраняется, а не объявляется мигрированным.
