---
name: agentos-safe-update
description: "Установка/обновление фундамента с сохранением отдельной пользовательской папки."
---

# agentos-safe-update

Прочитай INSTALL_UPDATE и compatibility. Получи source/wheel SHA, current pointer,
core/user paths и backups; они disjoint. Сначала installer plan, потом apply с exact current.
Без sudo, сети, замены чужого runtime, global auth/model/trust edits.
Overlay import create-only: conflict означает reconcile, не overwrite. Config migrate только
с backup/readback; unknown future schema блокируется.
После switch обнови только managed AGENTS/skills, затем fresh-session read-only и project
пробы новой сессии. Сохрани previous release и выполни rollback rehearsal на тестовом контуре.
Выход: installed/probe evidence и separate target status; native hooks остаются отключены.
При откате не запускать old integrate beta.4 или раньше и не возвращать hook backups.

Нормативная основа: установленный resources/docs/PROCESS.md и README; путь — `agentos resources`.
Project gates относятся к реальным изменениям. Чтение не требует intake/observe. Native hooks исключены: не включать и не восстанавливать. CLI/профиль не дают внешних полномочий.
