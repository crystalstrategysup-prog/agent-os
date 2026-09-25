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
После switch повтори integrate и native review изменённых hooks, затем genuine negative
пробы новой сессии. Сохрани previous release и выполни rollback rehearsal на тестовом контуре.
Выход: installed/probe evidence и separate target status; наличие файлов не доказывает hooks active.

Нормативная основа: установленный resources/docs/PROCESS.md и README; путь — `agentos resources`.
Hook/CLI gate нельзя выключать пользовательской настройкой. Навык не заменяет native hook trust.
