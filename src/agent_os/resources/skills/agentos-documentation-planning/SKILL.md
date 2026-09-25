---
name: agentos-documentation-planning
description: "Выбор и ведение документации проекта по типу, риску и реальному изменению."
---

# agentos-documentation-planning

Вход: dossier, факты о типах/features, selection от enter.
Сопоставь двенадцать слоёв catalog.json: выбери смысловые IDs и конкретные форматы.
Не создавай ненужные OpenAPI/ERD/политики. Одна небольшая записка может покрыть несколько IDs.
Для сложного проекта раздели product/architecture/data/contracts/operations.
Заполни шаблоны фактами, источниками, решениями/неизвестным; укажи owner.
Зарегистрируй document с sha; stage обязан ссылаться на exact task.
Прочитай документы как следующий разработчик: что это, как работает, что готово, что дальше?
Выход: current doc registry, объяснение применимости, DoR; не пустые файлы ради количества.
Нельзя принять contradiction/placeholder как current, даже если проверка длины проходит.

Нормативная основа: установленный resources/docs/PROCESS.md и README; путь — `agentos resources`.
Hook/CLI gate нельзя выключать пользовательской настройкой. Навык не заменяет native hook trust.
