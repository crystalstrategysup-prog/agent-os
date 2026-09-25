# Требования и проверяемая приёмка

FR-01: каждый новый/возобновлённый проектный запрос проходит intake; known context повторно
используется, material unknowns не выдумываются. Proof: new-turn/resume/missing-fields tests.
FR-02: разные типы/features выбирают применимые doc IDs с причинами; не весь каталог.
Proof: параметризованные type/feature tests, реальный package catalog и source planner.
FR-03: до READY исследование/документы разрешены, продуктовые tool writes блокируются на
действующем native adapter. Proof: local hook negative tests + отдельная actual client probe.
FR-04: отсутствие/устаревание документа блокирует readiness; stage связан с exact task.
FR-05: текущий результат проверяется actual process receipts, scope и semantic closeout;
новый source/revision, tampered log, late FAIL и missing check исключают false complete.
FR-06: data/settings вне core; install/update/rollback их не изменяет, import create-only.
FR-07: будущий агент получает instructions, skills, schemas, templates и mechanism через
версионный пакет; наличие hooks.json не считается активацией. Native trust не обходится.
FR-08: AgentOS описывает себя dossier/roadmap/architecture/contracts/data/quality/ops и
использует собственный цикл; начальный bootstrap раскрывается честно, не задним числом.

NFR-01: core без runtime dependencies; bounded local JSON/file traversal; no network needed
for project governance or offline wheel install. Optional legacy network features раскрыты отдельно.
NFR-02: same input types/features → same document set; explicit errors вместо silent overwrite.
NFR-03: owner/settings/history не входят public release; package inventory, source/wheel hashes.
NFR-04: restart-persistent state and locks; не distributed/multi-writer database и не OS sandbox.
NFR-05: доказательная отчётность отдельно различает built/tested, published, installed, native
hooks active и external integration parity. Модель/учётные данные/полномочия не меняются попутно.

Трассировка: tests/test_foundation.py; tools/demo_lifecycle.py; tools/install.py;
PROCESS/QUALITY/COMPATIBILITY. Конкретные результаты — в текущем task/evidence и handoff.
Цифровая подпись издателя, full sandbox, native UI questionnaire, Windows installer и полный
порт закрытых providers не заявлены завершёнными возможностями этой beta.
