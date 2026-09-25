# Вход человека и нового агента

Начать с короткого `AGENTS.md` текущего проекта/родительского рабочего каталога.
Он указывает на тематические документы и навыки; читать только те, что относятся
к запросу. Длинная история и актуальная архитектура принадлежат проектным docs,
а owner/host знания — отдельному overlay. При предупреждении клиента об обрезке
инструкций проверить, какие части реально загружены, и предложить отдельную
реорганизацию корневого файла. Обычный read-only запрос не разрешает его переписывать.
Размер — ориентир для сопровождения, не lifecycle gate.

Для вопроса, поиска, read-only аудита или discovery: использовать уже разрешённый доступ
и ответить. Не запускать intake/observe/profile interview и не создавать служебную задачу.

Для реального изменения прочитать dossier → roadmap → stage/last result → затронутые
architecture/contracts. Нет docs — сначала read-only обследование, затем заполнение
досье/roadmap/stage по фактам. Не scaffolding поверх неизвестной структуры. Запустить
project questions с уже известными ответами; enter с current authority. Лишь неизвестные
существенные решения требуют вопроса владельцу. Same-scope continuation:
questions --resume-task; enter --resume-task --reuse-answers, текущий authority подать
через JSON или stdin. Подробности и exact gates: PROCESS.md.

Register required docs → READY → approved product edits → exact checks → актуальные docs
→ assess/close или честный checkpoint. READY не даёт внешних прав. Проверка бессодержательным
`true` не считается смысловой приёмкой. tools/demo_lifecycle.py — tmpdir учебный пример,
не live evidence. После CLOSED verify-closeout проверяет текущую пригодность результата.

Профили optional и снаружи core. Читать только релевантные verified entries; missing/stale
не блокирует независимое чтение, но устаревшие host facts не применять. interview не нужна
для каждого вопроса. Full history/secrets не загружаются. Метаданные и документы проекта
остаются в его каталоге, runtime receipts не публикуются в public source.

Роли: owner задаёт результат/authority; coordinator — scope/этап; implementer — изменения;
reviewer — смысл и evidence; target operator — фактический live result. Самопроверка
допустима с раскрытием, но не называется независимым аудитом.

Интеграция — managed AGENTS + namespaced skills, **без native hooks**. Проверить точный
interpreter/resources и эффективные инструкции в новой сессии; global owner block и
project override могут противоречить новому правилу. Не редактировать их по частичному
экспорту целиком и не менять модель/auth/security config.

Ошибки: draft/stale → факты + register; scope changed → новый полный entry; stale checks →
повтор актуальных approved checks; out-of-scope → откат лишнего или согласованный этап;
bound turn mismatch → inspect реальной задачи и explicit checkpoint/next-turn;
pre-entry error → прямое сообщение без fake closeout. Не удалять lock вслепую.
