# Архитектура фундамента

## Контекст и границы

Обычное разрешённое чтение → непосредственный ответ, без AgentOS lifecycle.
Реальное изменение → inspect → docs/architecture → entry/READY → implementation →
checks → close/checkpoint. Внешний эффект → отдельный target authority gate у executor.
MCP — read-only discovery/planning, не shell. Native hooks исключены.
Project/workflow governance не требует сети; optional legacy Telegram/update/speech
не являются prerequisite и не исполняются маршрутизатором.

|Модуль|Ответственность|Не делает|
|---|---|---|
|workflow|Stateless optional route по declared kind/effects|Не NLP, не executor, не выдаёт capability|
|project / doc_catalog|Применимые docs, reuse, readiness, checks, current closeout|Не перехватывает все tools и не доказывает live deploy|
|turns|Явные project entry/terminal transitions|Не получает UserPromptSubmit и не сбрасывает task на вопросе|
|observation|Необязательные отдельные audit receipts|Не prerequisite для чтения и не меняет task binding|
|hooks|Retired no-op для старых callback entrypoints|Не читает stdin/config, не пишет state, не выдаёт deny/allow/complete|
|integration|Managed AGENTS + 9 namespaced skills, backup/conflict check|Не трогает hooks.json, config.toml, auth/model/trust|
|safeio|Containment, bounded regular JSON / explicit stdin, locks, atomic writes|Не защита от злонамеренного same-UID процесса|
|overlay / config / profile_adapter|Физически отдельные данные, 0/1/N verified profiles|Не создаёт полномочий и не подменяет runtime proof|
|dispatch_gate|Сохранённая одноразовая привязка legacy dispatch|Не общий сетевой sandbox|
|mcp_server|Шесть bounded planning/status tools|Нет произвольных write/shell tools|
|tools/install|Offline wheel→venv→probe→atomic current→rollback|Нет service/production изменений|
|setup scenarios|Версионированный публичный каталог целей, шагов и проверок подключения|Не запускает private provider, не читает секреты и не подтверждает live readiness|

## Решения

ADR-001: публичное ядро развивается отдельно от private runtime; сравнение source/wheel
не подтверждает публикацию или реальную установку.
ADR-002: core, user home и project docs физически разделены, config v5/overlay v1
версионируются независимо; вложенность/пересечение запрещены.
ADR-003: JSON+Markdown/stdlib, один active task, local locks; не distributed DB.
ADR-004: immutable release directories, venv сразу по конечному пути; current меняется
только после probe. Ни обновление, ни откат не меняют пользовательские данные неявно.
ADR-005: внешние профили optional, exact IDs/hashes/host/conflicts. Нет профиля — штатно;
STALE запрещает использовать устаревшее содержимое, не блокирует несвязанное чтение.
ADR-006: checks/schema/hash — traceability и структурный gate. Semantic reviewer и
target executor проверяют смысл/полномочия. Same-UID автор может подделать receipts.
ADR-007: private providers — отдельные контракты/разрешения/target parity; не копировать
их исполняемый код в public package под видом настроек.

ADR-008 (F09, заменяет прежнюю норму native-hook enforcement): отделить лёгкий read path
от обязательного documentation-first процесса **изменений**. Удалить глобальный callback
цикл, а не расширять shell/tool allowlist. Сохранить retired callback entrypoints как
пустой совместимый ответ без новых регистраций, чтобы старые ссылки не создавали ошибку.
Перенести нужные явному lifecycle turn helpers в turns.py; observation хранить отдельно.
Предоставить ограниченный stdin transport вместо ослабления symlink-защиты. Same-scope
reuse не наследует authority. Сохранить строгие project gates и отдельные target controls.

Компромисс: AgentOS больше не заявляет глобальный runtime-interceptor. Markdown/CLI не
заменяют client sandbox, ACL или scoped connector. Нельзя честно обещать запрет любого
произвольного shell действия, имея лишь библиотеку Python и AGENTS. Такая изоляция требует
отдельного host-specific этапа, а не возвращения исключённых хуков.

ADR-009 (F10): унаследованный корневой `AGENTS.md` — короткая карта области действия,
общих ограничений и ссылок на тематические документы/навыки. Он не хранит историю
инцидентов, объёмные runtime-снимки или правила несвязанных продуктов целиком.
Загрузить только подходящий задаче маршрут, затем проверить текущий source/runtime.
Публичное ядро задаёт этот способ работы; owner/host факты остаются в отдельном
overlay, а документация продукта — в его проекте. Ориентир малого размера —
подсказка при ревью, не новый blocking gate, hook или обещание полного контекста.

ADR-010 (F11): изменения нескольких управляемых файлов integration и project entry
пишутся под локальным lock с журналом ожидаемых хешей и отдельными исходными байтами.
При штатном отказе выполняется откат; после прерывания следующий вызов сначала
восстанавливает прежнее состояние и требует повторить вход. Если файл был изменён
после прерывания, восстановление останавливается без перезаписи чужих данных.
Проверки проекта запускаются в отдельной POSIX process group с ограниченным выводом;
PASS допустим только после завершения группы и снимка исходников после проверки.
Installer сравнивает реальные установленные файлы и entrypoints с проверенным wheel
до импорта и переключения `current`. Это локальная дисциплина целостности, не защита
от злонамеренного процесса того же пользователя.

ADR-011: «сценарий подключения» — типизированное знание публичного фундамента, а не
исполняемый модуль или инстанс пользовательской интеграции. Публичный индекс перечисляет
доступные сценарии и их честный статус; каждый сценарий содержит цель, варианты,
действия человека и агента, ожидаемые доказательства и ссылки на официальные источники.
CLI читает только упакованные ресурсы. GUI и разговорный мастер смогут использовать тот же
контракт. Личные параметры, session material, секреты и executable provider принадлежат
внешнему overlay/частному компоненту. Наличие карточки не означает доступного адаптера
или успешного подключения. Актуальность поддерживают проверки контрактов и
источников; изменение полномочий требует отдельного review. Протокол:
`docs/SETUP_SCENARIOS.md`.
