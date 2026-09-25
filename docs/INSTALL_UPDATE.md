# Установка, обновление, откат и восстановление

## Установка из публичного исходника

После публикации проверенного tag `v0.5.0-beta.4` на macOS или Linux с Python 3.11+:

```sh
git clone --branch v0.5.0-beta.4 https://github.com/crystalstrategysup-prog/agent-os.git
cd agent-os
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
agentos init
agentos doctor
```

Это локальная установка из source в отдельное виртуальное окружение. `init` создаёт
пользовательскую папку по умолчанию `~/.agentos-user`; укажите `--home` или
`AGENTOS_USER_HOME`, если нужна иная папка. Для развития проекта используйте
`python -m pip install -e '.[dev]'` и тесты. Публичной загрузки с PyPI на момент
выпуска нет. Дальнейший управляемый offline installer принимает заранее
проверенный wheel и хранит выпуски ядра отдельно от пользовательских данных.

## Предварительные проверки

Проверить SHA переданного архива и wheel, происхождение source, Python 3.11+, свободное место,
права на две **непересекающиеся** папки. Управляемый installer POSIX-only. Не запускать с sudo.
Не использовать существующий current указатель другого/private AgentOS как новый core home.
Не запускать частную обезличенную копию как backup или готовую live installation.

```sh
python3 tools/install.py install \
 --wheel /absolute/crystal_agent_os-0.5.0b4-py3-none-any.whl \
 --sha256 ACTUAL_WHEEL_SHA256 --version 0.5.0-beta.4 \
 --core-home "$HOME/.local/share/agentos-foundation" --user-home "$HOME/.agentos-user"
```

Plan выводит expected_current (первый запуск `none`) и release_id. После проверки:
повторить **ту же команду** с `--apply --expected-current none` или exact observed release id.
Wheel копируется с повторной проверкой SHA, venv создаётся по окончательному пути, pip работает
--isolated --no-index --no-deps. Smoke проверяет реальную installed version/resources/MCP tools.
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

`integrate codex` сначала plan, затем --apply. Существующий AGENTS.override.md выбран, если
он есть; новый override не создаётся поверх owner instructions. Управляемый блок заменяется,
остальные инструкции сохраняются. Навыки имеют namespaced directories; чужие modifications
вызывают CONFLICT. Existing hooks иных владельцев сохраняются. Backup предыдущих файлов —
user/backups/integration. Config/auth/model/trust store не редактируются.

В actual клиенте проверить [features].hooks=true, доступность команд, /hooks, перечень
событий и доверие к точным определениям. Изменение команды/interpreter после апдейта требует
повторного review. Новый процесс/сессия: SessionStart → UserPromptSubmit → заведомый product
write до intake должен DENY → intake/docs/READY → только затем разрешённый write → check/close.
Повторить пропуск closeout (Stop блокирует), новый turn (старый gate больше не подходит).
Проверьте stdout/native event log, не только наличие hooks.json. При отсутствии механизма
статус ENFORCEMENT_NOT_PROVEN; правило в Markdown не заменяет эту проверку.
Для CLI-only режима без native hooks после checkpoint/close используйте
`agentos project next-turn` с точными session, previous turn, new turn и task,
затем отдельный `project enter`. Этот переход не подтверждает native enforcement.

## Обновление

Старый release immutable. Выполнить offline install нового wheel с observed expected_current.
Существующий user home остаётся неизменным; installer не мигрирует данные неявно.
После switch переподключить managed agent integration, затем новый native trust/probe.
Не делать автоматическую установку только потому, что update advisory нашёл tag.
Обновлять документацию, compatibility матрицу и health evidence того же source SHA.

## Откат

В core/PREVIOUS.json лежит previous id; `none` значит предыдущего managed release нет.
```sh
python3 tools/install.py rollback --release-id PREVIOUS_ID \
 --core-home CORE --user-home USER
# Затем то же с --apply --expected-current CURRENT_ID
```

Rollback проверяет manifest/wheel/probe/schema совместимость, атомарно меняет current и
не трогает user data. Затем повторный integrate из выбранного interpreter и native review.
Если несовместимо состояние пользователя, не делать downgrade; восстановить отдельный
backup в **новую** user папку и проверить там. Первый install не «откатывает» чужой runtime.

## Восстановление

INCOMPLETE release не активируется: сохраните логи, установите причину, не удаляйте marker
для обхода. Проверенный неактивный incomplete directory можно убрать только отдельным
решением после сверки current; повторить установку. Lock .install.lock или .agentos/write.lock
не удалять по таймеру: убедиться, что owner PID завершён, проверить журнал и целостность.
current foreign/unmanaged блокируется. Backup config восстанавливают после сравнения,
со snapshot действующего файла и readback. Ни installer, ни миграция не удаляют историю автоматически.
