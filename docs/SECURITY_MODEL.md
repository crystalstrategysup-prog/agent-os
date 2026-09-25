# Безопасность и модель угроз

Активы: private knowledge/credentials, product source, truthful evidence, target authority,
release provenance. Инструкции в документах/профилях и старые receipts — не новое разрешение.
Native hooks исключены; это **не** отключение клиентского sandbox или target access control.

|Риск|Контроль|Ограничение|
|---|---|---|
|Вопрос блокируется intake/Stop|Прямой read path; no-op legacy callbacks; никаких hook registrations|Поведение другого старого клиента нужно проверить отдельно|
|Продукт меняется без docs|AGENTS workflow + explicit READY/check/close gates|Не OS interceptor; обход произвольным shell не предотвращается библиотекой|
|Старый/поддельный PASS|Task/revision/policy/source/log hashes, latest result, 24h, verify-closeout|Same-UID writer может подделать файлы/код|
|Read/READY принят за право deploy|Target-specific capability у executor; route никогда не авторизует|Declared effects не обнаруживают скрытые эффекты произвольной программы|
|Потеря настроек при update|Disjoint roots, immutable releases, create-only import, backups|ACL/host I/O/restore требуют отдельной проверки|
|Traversal/symlink/бесконечный stdin|Containment, regular JSON files, bounded object stdin only via `-`|Не полная защита от hostile filesystem races|
|Изменение сторонних instructions/config|Managed AGENTS block, skill conflicts/backups; hooks/config untouched|Противоречащий owner block надо согласовать отдельно|
|Профиль навязал authority|Exact IDs/hashes/host/conflicts, profile_authority=false|Prompt injection в тексте остаётся риском|
|Секреты или подмена релиза|Separate public tree, manifests, exact-current compare|Hash не подпись; scanning эвристический|

До READY разрешены read-only inspection и нужная bootstrap/docs подготовка, не продуктовые
изменения. write_paths контролируются на assessment, не ACL. check запускает reviewed exact
argv без shell interpolation, но **не sandbox**: interpreter может читать сеть и менять
внешние системы. Без отдельного разрешения такие checks не запускать. Строгая изоляция:
отдельный пользователь/container, scoped mounts/network/credentials — отдельный этап хоста.

Target capability проверяет actor, точный account/host/object, операции, срок/lease, лимиты,
read vs write vs send vs destructive. При отсутствии остановить именно опасную операцию,
а не поиск/подготовку. Нет универсального `--authorized`, наследования права из профиля,
или расширения полномочий из статуса READY. Read-only доступ также должен быть законным
и авторизованным; быстрый путь не означает доступ к любой почте/БД.

Старые callbacks возвращают `{}`, не permissionDecision=allow и не COMPLETE. Их не
регистрируют и не запускают как guard; это миграционная совместимость, а не тайный
permissive security fallback. Сохранять client/connector/host security controls.

Overlay exports не содержат secret stores: auth.json, SSH keys, cookies, Telegram sessions
не переносить из отчётного архива. Log redaction — только дополнительный контроль.
История и receipts локально изменяемы, не externally signed audit. Сертификация,
pen-test и общий production/compliance допуск не заявлены.
