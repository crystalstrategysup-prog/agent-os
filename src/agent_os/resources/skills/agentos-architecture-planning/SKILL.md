---
name: agentos-architecture-planning
description: "Разбор существующей архитектуры, границ доверия, контрактов и плана изменения."
---

# agentos-architecture-planning

Начинай после project entry; перед implementation.
Отдели наблюдения в коде/конфигах от desired state. Опиши контекст, компоненты, данные,
API, интеграции, source/runtime границы и владельцев. Рассмотри минимальную достаточную
архитектуру, альтернативы, совместимость, migration/rollback. ADR фиксирует решение и цену.
Новые интерфейсы должны иметь schema/error semantics/версии. Privileged actions имеют
target authority, а не выводятся из просьбы нарисовать архитектуру.
Построй широкие автономные этапы с критериями, зависимостями и evidence.
Выход: architecture/ADR/stage/roadmap; unresolved риск отмечен, не скрыт реализацией.

Нормативная основа: установленный resources/docs/PROCESS.md и README; путь — `agentos resources`.
Hook/CLI gate нельзя выключать пользовательской настройкой. Навык не заменяет native hook trust.
