# Стратегия качества

Проверяются четыре уровня: функции/отрицательные сценарии; целый lifecycle на временном
проекте; реальный wheel+offline venv installer/rollback с отдельной пользовательской папкой;
независимая target-проверка после передачи. Последний уровень нельзя заменить первыми тремя.

```sh
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
python3 tools/demo_lifecycle.py
python3 tools/verify_public.py
```

Regression baseline — 42 tests из community source, адаптированные только под новые version/schema,
число MCP tools и обязательную dispatch границу. Дополнительные tests: обязательные поля,
неприменимые документы, draft/stale doc, missing/failed/stale/tampered evidence, changed source,
out-of-scope, revision reset, stop/new turn, path traversal, overlapping roots, symlink import,
конфликты/идемпотентность, migration backup, сохранение сторонних AGENTS/hooks/skills,
неизменность read-only проекта, одноразовый dispatch. Точное число — в реальном test log,
не hard-coded promise в документации.

Gate не оценивает качество теста по его названию. Stage reviewer отвечает, что checks действительно
проверяют criterion, а не выполняют `true`. На демо используется маленькая проверяемая функция;
её происхождение как synthetic fixture обозначено явно. Интеграционный runner должен логировать
actual argv, environment class, source/wheel SHA, exit code, stdout и unsupported conditions.

Публичная privacy проверка сканирует только publishable tree по известным host/private маркерам
и проверяет наличие нормативных документов/ресурсов. Это не доказательство отсутствия любых
секретов. Review изменений обязателен. Схемы Draft2020-12 — reference contracts; production
validators stdlib выполняют критические проверки напрямую, не загружают удалённые $ref.
Проверка выпуска блокируется при наличии `.agentos/` runtime receipts в экспортируемом дереве.
`tests/test_contracts.py` сверяет версии, MCP input/output, task/event schemas и пакетные копии.

Локальный Linux PASS не подтверждает macOS launchd/Keychain/кодекс-хуки и чужие services.
Required target matrix: source SHA + runtime version; actual core/user paths disjoint;
existing config preserved; authentic native DENY/PASS/Stop/new-turn probes; existing integrations
read-only health before/after; rollback rehearsal and fresh readback. До этого target UNVERIFIED.
