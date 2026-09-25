---
name: agentos-implementation-control
description: "Реализация документированного этапа без скрытого расширения scope."
---

# agentos-implementation-control

Проверь project gate=PASS для exact task. Прочитай stage, write_paths, authority и checks.
Реализуй законченное изменение внутри контракта, вместе с regression/negative tests.
Не меняй guard ради его прохождения. При расширении задачи остановись в checkpoint,
обнови scope/документы и пройди новый entry. Не используй сторонние отчёты вместо source.
До внешней записи проверь target host, текущий source/runtime, разрешение и rollback.
Локальный sandbox здесь ограничен файлами текущей задачи; чужой production не трогать.
Выход: изменённые исходники/tests/docs и список фактических ограничений, затем verification-closeout.

Нормативная основа: установленный resources/docs/PROCESS.md и README; путь — `agentos resources`.
Hook/CLI gate нельзя выключать пользовательской настройкой. Навык не заменяет native hook trust.
