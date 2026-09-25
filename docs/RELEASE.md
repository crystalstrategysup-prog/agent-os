# Политика выпуска

Публичная версия: 0.5.0-beta.1; Python packaging equivalent: 0.5.0b1.
User overlay version независима от версии ядра; schema совместимость проверяется отдельно.
Release tag и версия пакета должны соответствовать. Не публиковать beta под v0.4.0 и не
подменять текущий stable. GitHub Actions не требуется и не добавляется: локальные проверки
с сохранёнными receipts; публичная CI политика меняется только отдельным решением.

Release gate: inspect diff, текущие unit/integration проверки, complete docs, reproducible source
inventory, wheel hash, чистая установка в новый venv, privacy review и точный publish allowlist.
Публиковать только public-core и артефакты из public-dist. Никогда весь mixed/private handoff.
Подпись/tag release через полномочный аккаунт выполняются только на авторизованном host;
подготовленный ZIP не является опубликованным release. Before push сверить remote/head/dirty tree,
не делать force/reset/stash чужих изменений. Конкурирующую работу — reconcile, не перетирать.

В release note: что меняется, breaking behavior, config migration, supported/tested платформы,
known limitations, SHA wheel/source, installation/rollback, next stage. Private host names/пути,
knowledge, logs с PII и historical reference в release не включаются.

Новый официальный установочный способ — проверенный source/wheel. Не утверждать, что пакет
есть в PyPI, пока публикация туда не подтверждена. Source archive сборки может содержать
документы bootstrap/self-verification; нормальные будущие задачи всё равно начинают новый enter.
Схемы/навыки входят в wheel как package resources и наследуются следующим агентом после
явной интеграции; пользовательские overrides сохраняются за пределами ядра.
