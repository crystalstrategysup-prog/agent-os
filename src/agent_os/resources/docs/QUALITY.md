# Стратегия качества

Точные числа и среда — в evidence конкретного кандидата, не hard-coded обещание.
Проверяются функции, negative cases, whole lifecycle в tmpdir, package resources/contracts,
offline wheel build/smoke и затем отдельная actual Mac/Codex приёмка интегратором.

```sh
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3 tools/demo_lifecycle.py
PYTHONDONTWRITEBYTECODE=1 python3 tools/verify_public.py
python3 tools/sync_resources.py
```

A: direct/stateless read path без project/overlay; optional audit отдельно.
B: новая задача, stdin bootstrap, docs/READY до реального кода, exact checks/close.
C: существующий недокументированный проект не меняется до docs.
D: same-scope resume без повторных вопросов, без наследования authority; gates reset.
E: declared local effects идут в docs path, target effects BLOCKED; отрицательные
scope/check/MCP/dispatch tests. Это не испытание универсального network sandbox.
F: malformed/missing callbacks no-op, Stop не блокирует; integrate не создаёт hooks,
сохраняет config/owner blocks; active tasks защищены, stale unbound receipts не мешают;
нет fake closeout, verify-closeout выявляет tampering.

F10: managed AGENTS должен содержать короткий маршрут к тематическим docs/skills,
при этом не добавлять размерный gate, hook или обязательную загрузку всей истории.
Проверять сохранность owner text при integrate и читать effective instructions в
новой сессии; synthetic test не доказывает отсутствие обрезки на любом клиенте.

F11: S1–S8 проверяются отдельными отрицательными случаями для выбора CODEX_HOME,
пустого override, partial integration, CRLF/marker order, потомков check-процесса,
FIFO/socket inventory, повреждённой installed payload и console pytest.
Partial `project enter` проверяется отказом после создания черновика/turn receipt,
восстановлением после прерывания и отказом при конкурентной правке владельца.
Нужны оба способа запуска pytest, чистый Git export, wheel metadata/RECORD,
изолированные Mac и Linux fixture, затем отдельная приёмка реальной конфигурации.

Baseline native interception tests заменяются тестами retirement/no-install contract,
а не сохраняются как скрытое обещание enforcement. Остальные critical negative lifecycle,
path/symlink/duplicate JSON, evidence hash/age/version, profile/import/installer/MCP
контракты должны остаться. Проверять diff и объяснять удалённые obsolete tests.

Checks должны проверять acceptance criterion, не просто называться unit. Synthetic fixtures
помечаются явно. Отдельные logs хранят argv, environment, source/wheel hash, rc и ограничения.
Public-tree scanner — эвристика, не security certification. Нельзя публиковать `.agentos/`
receipts или owner settings вместе с core. Package docs/schemas совпадают с maintained source.

Linux tests/build не доказывают macOS/Keychain/launchd/Codex session behavior. На Mac нужны
source/runtime identity, disjoint roots, отсутствие AgentOS hooks, неизменность config/auth,
fresh effective AGENTS, A–F на локальных fixtures без внешних writes, rollback/readback.
До реального выполнения target acceptance NOT_RUN. Hooks не часть этих проверок и не включаются.
