---
name: agentos-project-handoff
description: "Передача проекта следующему агенту без восстановления замысла по старой переписке."
---

# agentos-project-handoff

Актуализируй dossier/roadmap/architecture/contracts/current stage/known issues.
Зафиксируй exact source и runtime отдельно, verified checks/limitations, permissions,
active task/checkpoint, команды начала и безопасный следующий шаг.
Создай комплект с manifest и publish boundary; user data отдельно. Не включай auth/secrets.
Получатель начинает новый project entry, читает документы, проверяет hashes, не принимает
предыдущий отчёт за независимое production доказательство.
Не скрывай пропущенные capabilities и concurrent work. Выход: self-contained packet + acceptance contract.

Нормативная основа: установленный resources/docs/PROCESS.md и README; путь — `agentos resources`.
Hook/CLI gate нельзя выключать пользовательской настройкой. Навык не заменяет native hook trust.
