# Начало работы следующего разработчика

## Чистая установка и исходники

Канонический исходник — `https://github.com/crystalstrategysup-prog/agent-os`.
Для beta используйте проверенный tag `v0.5.0-beta.3` после публикации. На macOS/Linux
нужен Python 3.11+: `python3 -m venv .venv`, затем `python -m pip install -e '.[dev]'`,
`agentos init`, `agentos doctor`, `python -m pytest -q`. Это установка из исходника,
не из PyPI: проект `crystal-agent-os` там пока даёт 404. Запуск `init` создаёт только
пользовательский home `~/.agentos-user`; он не меняет глобальный Codex и private runtime.
Изолированный offline wheel install/rollback описан в `INSTALL_UPDATE.md`.

## Состав и контракты

`src/agent_os/` — runtime, `src/agent_os/resources/` — файлы, реально попадающие в wheel,
`schemas/` — исходные машинные контракты, `docs/` — поддерживаемые объяснения,
`tests/` и `tools/demo_lifecycle.py` — проверка поведения. При изменении публичного
документа верхнего уровня `docs/*.md` обновите его пакетную копию в
`src/agent_os/resources/docs/`; тест проверяет побайтовое совпадение. Для нового CLI,
MCP, config, data или events поведения обновите соответствующий контракт и тест.

## Документация перед реализацией

Прочтите досье `agentos/DOSSIER.md`, roadmap `agentos/ROADMAP.md` и документ текущего
этапа. Для существующего проекта сначала исследуйте его read-only. Входной сценарий
использует известные факты и спрашивает лишь недостающее; из каталога выбираются только
релевантные слои. До `READY` допускается подготовка документов, но продуктовая запись
блокируется на поддерживаемом активном hook path. После реализации запустите точные
checks, обновите документацию по факту и выполните close либо checkpoint.

Порядок чтения: README → dossier → roadmap → последний этап/результат → architecture/contracts.
`agentos resources --list` показывает установленный нормативный комплект; пользовательский
`overlay index` указывает релевантные private docs, но не вываливает секреты и историю.
Перед задачей вызвать questions, использовать известные ответы, провести enter для session/turn.
В CLI-only сессии после checkpoint/close выполните `project next-turn` с точными
`--session S --from-turn OLD --turn NEW --task TASK`, затем новый `enter` с `--turn NEW`.
Для native hooks новый turn приходит только от UserPromptSubmit; CLI-переход его не подменяет.
Для незнакомого existing проекта начните read-only обследование, не scaffolding поверх неизвестного.

Практический пример полностью выполняется `python3 tools/demo_lifecycle.py` в tmpdir.
Он демонстрирует заблокированный ранний gate, реальные документы, реализацию маленькой функции,
source-bound check, смысловой closeout и Stop. Это учебный проект, не доказательство live installation.
В examples лежат JSON формы. Заменять поля фактами, а не выдавать fixture за работу владельца.

Основные роли: owner определяет результат/полномочия; coordinator управляет этапом/scope;
implementer меняет разрешённое; reviewer проверяет смысл и evidence; target operator подтверждает
live состояние. Один агент может совмещать роли с явным раскрытием, но самопроверка не независимый аудит.
Подключение нового агента: интеграция, native trust и отрицательная проба без intake; простой
прочитанный SKILL.md не означает enforced tool boundary.

Troubleshooting: draft/unregistered → заполнить и register; unreviewed_change → сверить и
register фактические изменения; scope_changed → новый entry; stale_check → повторить approved
check на текущем исходнике; out_of_scope → откат лишнего либо новый согласованный stage;
turn mismatch → точный session/turn клиента, не выдумывать; conflict import → согласовать private
данные локально; lock → проверить writer, не удалять вслепую; hook skipped → проверить native trust.
Если нет достоверного пути дальше — checkpoint с конкретным следующим действием.
