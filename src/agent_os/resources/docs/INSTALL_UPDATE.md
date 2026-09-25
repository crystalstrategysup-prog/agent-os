# Установка, обновление, откат и восстановление

## Статус версии

`0.5.0` / `0.5.0` — версия исходников. Проверить, что tag,
PyPI пакет или release asset действительно опубликован. Проверить полученный source/patch/manifest,
провести independent tests и отдельно подтвердить целевой runtime. Python 3.11+,
отдельные core/user roots обязательны. Ниже описан порядок установки; факт её
выполнения устанавливается только по текущему указателю и read-back.

## Предварительные проверки

Проверить SHA переданного архива и wheel, происхождение source, Python 3.11+, свободное место,
права на две **непересекающиеся** папки. Управляемый installer POSIX-only. Не запускать с sudo.
Не использовать существующий current указатель другого/private AgentOS как новый core home.
Не запускать частную обезличенную копию как backup или готовую live installation.

```sh
python3 tools/install.py install \
 --wheel /absolute/crystal_agent_os-0.5.0-py3-none-any.whl \
 --sha256 ACTUAL_WHEEL_SHA256 --version 0.5.0 \
 --core-home "$HOME/.local/share/agentos-foundation" --user-home "$HOME/.agentos-user"
```

Plan выводит expected_current (первый запуск `none`) и release_id. После проверки:
повторить **ту же команду** с `--apply --expected-current none` или exact observed release id.
Wheel копируется с повторной проверкой SHA, venv создаётся по окончательному пути, pip работает
--isolated --no-index --no-deps. До запуска installed module сравниваются байты
`agent_os`, wheel metadata и entrypoint scripts с проверенным wheel; затем smoke
проверяет реальную installed version/resources/MCP tools.
Only after PASS меняется current symlink. Installer не изменяет пользовательскую папку,
но читает `overlay.json` и `config.json` для проверки совместимости схем перед планом и
перед переключением версии. Неизвестная схема, повреждённый JSON или symlink блокируют
установку и откат без изменения `current`; отсутствие файлов допустимо. Import — отдельная
команда. Установка не делает global PATH, service, auth changes.

## Пользовательская надстройка

Профили необязательны. Для их включения сохраните каждый `profile.json` под
`USER/profiles/ID/` по схеме `agentos.profile/v1`, затем выполните
`agentos --home USER profiles inventory` и изучите конфликты. `profiles select
--mode one --id ID --inventory-digest DIGEST` выбирает один профиль. `--mode all`
требует все точные ID в выбранном порядке; для разных значений одного ключа
передайте `--decisions` с JSON `{ "ключ": "профиль-победитель" }`. `--mode none`
отключает выбор. После изменения/удаления файлов проверьте `profiles context` и
выберите снова; ядро менять не нужно. `profiles interview` показывает текущие
факты устройства, выбранные поля и открытые вопросы, но не записывает ответы.

До init: `agentos --home USER overlay import --source OVERLAY` (план), затем `--apply`.
При CONFLICT ничего не перезаписывать: сохранить действующий файл, сравнить локально по ключам,
создать согласованную overlay-копию с новым manifest. Не регенерировать manifest ради скрытия
неизвестной порчи: происхождение и решение обязательны. Позднее `init` добавит служебные dirs,
не заменяя config. Не копировать auth.json, SSH keys, cookies, Telegram sessions из архива.

Для существующего community-config/v1..v4: `overlay migrate-config`, потом `--apply`.
Незнакомые ключи сохраняются; config backup остаётся в user/backups. Partial private configs
не интерпретируются как community-config автоматически: это отдельный on-host mapping.
Import создаёт файл только после полной записи и fsync во временный файл в том же каталоге;
при сбое записи целевой файл не появляется. Существующий файл никогда не заменяется.

## Подключение агента

`integrate codex` сначала plan, затем --apply. Цель выбирается явным
`--codex-home`, затем `CODEX_HOME`, затем обычным `~/.codex`. Override выбран,
только если он содержит непустые инструкции; пустой не заслоняет owner AGENTS.
Управляемый блок заменяется без изменения bytes вне него, включая CRLF.
Перепутанные маркеры блокируют запись. Навыки имеют namespaced directories;
чужие modifications вызывают CONFLICT. AGENTS, skills и receipt обновляются через
журнал с откатом или явным recovery; конкурентная правка не перезаписывается.
Existing hooks иных владельцев сохраняются. Backup предыдущих файлов —
user/backups/integration. Config/auth/model/trust store не редактируются.

Native hooks исключены: integrate не создаёт, не включает, не изменяет и не удаляет
hooks.json/config.toml. Он также не проверяет, не остались ли чужие/старые AgentOS callbacks.
Перед применением отдельно readback actual config/hooks: у владельца AgentOS hooks должны
оставаться отключены. Если они активны, остановить интеграцию и получить отдельное решение;
не «лечить» повторным доверием к ним. Не изменять auth, модель или sandbox.

Новая сессия клиента: проверить effective AGENTS/skills, прямой read-only ответ без служебных
файлов и registration; проектные изменения — docs/READY/check/close. Existing owner/global
project overrides сохраняются, поэтому противоречащие universal intake/observe инструкции
исправляются отдельным owner overlay change. Автоматически их удалять нельзя.

Для explicit workflow после checkpoint/close: `project next-turn` с точными session,
previous/new turn и task, затем enter. До регистрации задачи checkpoint/close не нужны.

## Обновление

Старый release immutable. Выполнить offline install нового wheel с observed expected_current.
Существующий user home остаётся неизменным; installer не мигрирует данные неявно.
После switch отдельно обновить managed AGENTS/skills из нового interpreter и проверить
их в новой сессии. Никаких native hooks/trust/probe с их включением.
Не делать автоматическую установку только потому, что update advisory нашёл tag.
Обновлять документацию, compatibility матрицу и health evidence того же source SHA.

## Откат

В core/PREVIOUS.json лежит previous id; `none` значит предыдущего managed release нет.
```sh
python3 tools/install.py rollback --release-id PREVIOUS_ID \
 --core-home CORE --user-home USER
# Затем то же с --apply --expected-current CURRENT_ID
```

Rollback проверяет manifest/wheel/installed payload/probe/schema совместимость,
атомарно меняет current и
не трогает user data. **Не запускать integrate старого ядра beta.4 или раньше:** он
может восстановить hooks. Сохранить no-hook AGENTS/skills или отдельно согласовать их
ручной откат без hook blocks. Не восстанавливать hooks из backups. Не выполнять old hook entrypoints.
Если несовместимо состояние пользователя, не делать downgrade; восстановить отдельный
backup в **новую** user папку и проверить там. Первый install не «откатывает» чужой runtime.

## Восстановление

INCOMPLETE release не активируется: сохраните логи, установите причину, не удаляйте marker
для обхода. Проверенный неактивный incomplete directory можно убрать только отдельным
решением после сверки current; повторить установку. Lock .install.lock или .agentos/write.lock
не удалять по таймеру: убедиться, что owner PID завершён, проверить журнал и целостность.
current foreign/unmanaged блокируется. Backup config восстанавливают после сравнения,
со snapshot действующего файла и readback. Ни installer, ни миграция не удаляют историю автоматически.
