# Требования и проверяемая приёмка

FR-01: вопрос/поиск/read-only аудит/API discovery выполняется без project init/intake,
observe, активного профиля, answers-файла и closeout, включая unregistered cwd.
FR-02: новое/продолжающееся реальное изменение требует актуальных документов и архитектуры
до реализации. Catalog выбирает только применимые слои; draft/stale docs блокируют READY.
FR-03: known facts используются повторно; same-scope resume сохраняет ответы, но требует
текущий authority и сбрасывает readiness/evidence. Изменённый scope — полный новый entry.
FR-04: context/answers/review можно подать через bounded JSON object stdin (`-`), сохраняя
duplicate-key/size/path/symlink проверки. Bootstrap не зависит от callback.
FR-05: current source/task/revision/policy/log + latest check + semantic review определяют
closeout. Отдельная read-only verify-closeout выявляет устаревание после CLOSED.
FR-06: native hooks исключены: integrate не создаёт/не восстанавливает/не меняет их,
retired callbacks — no-op. Ошибка до entry не требует выдуманной задачи.
FR-07: production/external-send/runtime/DB/credentials/destructive/deploy имеют отдельные
операционные capability gates; route/READY/profile не выдают внешние полномочия.
FR-08: core и пользовательские данные физически разделены. Update/rollback сохраняют
overlay; частичные owner exports не применяются как полная замена настроек.
FR-09: старые незавязанные prompt receipts не блокируют entry; конфликтующая реальная
active task остаётся защищена. Optional audit receipts не перезаписывают task state.

NFR: runtime stdlib; локальные bounded reads/locks; явные errors, exact hashes; без daemon,
NLP intent engine или новой БД. Никаких секретов/личных настроек в public patch. Локальная
приёмка не заменяет свежую Mac/Codex проверку и independent integration review.

Трассировка: tests/test_workflow.py (A–F), test_foundation.py, test_contracts.py,
tools/demo_lifecycle.py, PROCESS/QUALITY/COMPATIBILITY. Точные результаты — test logs
конкретного кандидата. Full sandbox, private fleet parity, native hooks и Windows
managed installer не заявлены возможностями этой итерации.
