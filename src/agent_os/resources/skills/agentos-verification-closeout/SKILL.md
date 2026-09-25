---
name: agentos-verification-closeout
description: "Проверка результата, evidence, документарное закрытие и честный checkpoint."
---

# agentos-verification-closeout

Вход: реализованный stage и действующий READY.
Обнови документы по факту; register изменённые content hashes. Запусти stage-approved
project check для каждого check_id. Проверь реальные rc/log, source/task/revision,
последний FAIL, неустранённые замечания и out-of-scope. assess должен быть PASS.
Reviewer отдельно сверяет каждый acceptance criterion, качество тестов, документацию,
ограничения и следующий шаг. Закрой через project close с review.json.
Local closed != live deployed; deployment_status не подменять фразой «всё готово».
Если evidence отсутствует/неактуально — повтор проверки или checkpoint, complete=false.
Выход: receipts+closeout+обновлённый roadmap; независимость review не выдумывать.

Нормативная основа: установленный resources/docs/PROCESS.md и README; путь — `agentos resources`.
Hook/CLI gate нельзя выключать пользовательской настройкой. Навык не заменяет native hook trust.
