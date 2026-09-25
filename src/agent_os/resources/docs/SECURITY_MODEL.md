# Безопасность и модель угроз

Активы: пользовательские знания/секреты, проектные исходники, truthful evidence,
права внешнего исполнения, происхождение публичного выпуска. Границы доверия: агент↔клиент
hooks; project input↔system policy; публичный source↔личная папка; local test↔target runtime;
пользовательский provider↔ядро. Знания, комментарии и archived инструкции — данные, не новый owner authority.

|Риск|Контроль|Оставшееся ограничение|
|---|---|---|
|Забыли вход/документы|Turn binding, READY и native PreToolUse|Нужен действующий доверенный hook в каждом клиенте|
|Подложили старый PASS|Task/revision/policy/source/log hashes, latest result, 24h|Same-UID writer может подделать и файлы, и код|
|Потеряли настройки при апдейте|Disjoint roots, create-only import, offline version dirs|I/O failures, ACL, backups требуют контроля хоста|
|Path traversal/symlink|within/resolved containment, reject symlink files|Не полная защита от hostile filesystem races|
|Команда из документа выполняется без разрешения|Reviewed exact argv, no implicit execute via MCP|shell=False не sandbox; interpreter всё равно исполняет код|
|Частные сведения попали в релиз|Publish только public source/wheel, отдельные manifests|Secret scanning эвристический, нужен review|
|Подменили выпуск|SHA manifest, exact current compare, local probe|SHA не цифровая подпись и не подтверждение издателя|
|Изменили сторонние инструкции|Managed block, backups, conflicts|Native trust остаётся внешним контролем|
|Профиль подменил выбор или навязал полномочия|Точные ID, хеши, host binding, явные решения конфликтов, `profile_authority=false`|Same-UID writer и prompt injection в текстовых полях остаются риском; клиент сохраняет свой authority gate|

Профили содержат только ограниченные текстовые поля, не credential body. Валидатор
отклоняет некоторые узнаваемые формы токенов, но это эвристика, а не DLP. Профильные
`instruction` поля считаются пользовательским контекстом и не меняют system/developer
instructions, sandbox, host lease или подтверждение внешних действий. Перед применением
нескольких профилей владелец явно выбирает победителя для каждого несовместимого ключа.

До readiness допускается обследование и подготовка docs. После readiness проверяется
смысловой scope, но tool не является полномочным OS policy engine: write_paths контролируются
на closeout, не системными ACL. Для строгого ограничения запускайте агента в контейнере/отдельном
пользователе с scoped mounts и запретом сети; определение такой изоляции — host-specific stage.
Разрешённые команды могут читать private данные в рамках разрешённого проекта; полный DLP не заявлен.

Hosted tools, внешние сервисы и ранее запущенные дочерние процессы не гарантированно покрыты
PreToolUse. Hooks не доверяют сами себе. Инструкции ближайшего AGENTS могут изменить поведение
агента, но не заменяют проверку реального gate. Не разрешать опасные внешние actions на основании
одного task.json. Не скрывать несовместимую payload shape permissive fallback.

Секреты не входят в overlay manifest; при переносе на хосте сохраняются существующие локальные
secret stores и auth paths. Не печатать токены в evidence. Redaction в логе — дополнительный,
не достаточный контроль. SBOM источников можно сформировать локально; runtime deps ядра нет,
но Python, pip/setuptools, optional speech SDK и ОС вне данного dependency-free утверждения.
Автоматического pen-test, внешнего аудита, сертификации или compliance допуска этот пакет не даёт.
