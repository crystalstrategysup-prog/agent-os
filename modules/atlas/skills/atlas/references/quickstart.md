# Atlas every day

## Start or continue a project

Check the selected project's instructions, registry entry and Atlas binding before
continuing development. Missing tools or an unreadable binding are a gap, not proof
of absent Atlas. Do not search unrelated roots.

**Atlas exists:** read its writer and assigned work, then use the configured
start route. For a registered WM-UI project:

```bash
atlasctl start PROJECT --work WORK_ID
```

**Atlas is confirmed absent:** reuse an explicit prior choice for this same
scope; otherwise offer exactly three choices:

1. Create Atlas before development.
2. Continue this task explicitly without Atlas.
3. Continue the task and start a separate temporary Atlas bootstrap session.

Choice 3 preserves the main writer: review and integrate one bounded bootstrap
result, then close the temporary assignment. No permanent keeper is created.
See `integration.md` for onboarding; ordinary read-only questions need none.

## Record the work, then continue

`start` loads context; it does not mark work as begun. When actual project work
begins, including research, document analysis or checks, the main writer records
it before the long operation or wait. Use the existing leaf work ID and actor,
with the configured `.atlas/WRITER.json`:

```bash
atlasctl work PROJECT --operation OP_ID --work WORK_ID --phase start \
  --executor ACTOR --note "Investigating the assigned issue and its evidence" \
  --next-action "Record the cause or the exact remaining uncertainty"
```

If work is already underway, record its current progress without backdating:

```bash
atlasctl work PROJECT --operation PROGRESS_OP_ID --work WORK_ID --phase progress \
  --status doing --executor ACTOR --note "Checking the specific cause found" \
  --next-action "Save the check result and its effect on the next step"
```

Replace the notes with actual facts. If no leaf covers the assigned task, the
current writer registers a bounded research/check item through its established
source method; do not reopen an unrelated accepted item. A standalone question
or context lookup still needs no task intake or Atlas bootstrap.

`work` pins inputs and publishes once. Use `dispatch` for real delegation;
`progress`/`complete` require `--status`, and completion requires `--evidence REL`.
Add prepared changes with `--document-edit DEST PREPARED`; both file options repeat.
See `workspace.md` for exact statuses and the advanced record API.

**Publish before waiting after new facts**: dispatch, progress, result or blocker.
Workers return deltas to the matrix's writer. During waiting, integrate available
results and maintain affected documents; unchanged waiting creates no event.
Recorded DOING is separate from confirmed live activity.

The recorded-work selection shows source `doing` and native `DOING` even when
activity evidence is missing or expired. The current-activity filter is stricter;
if it is empty, use the offered recovery action to show recorded or all work.
Saved observations can be searched without making them current. The viewer and
`start` do not collect native session activity; recording is the writer's step.

For changes already saved through the existing project writer method, run
`atlasctl finish PROJECT` once. Neither method authors missing contract semantics
or proves acceptance. Reuse the same operation ID and arguments after interruption;
changed arguments are refused. Unchanged refresh/finish creates no release but may
repair the current-view copy. Read nested outcomes; reuse applicable evidence.

| Need | Registered project command |
|---|---|
| Get current contracts and roadmap views | `atlasctl views PROJECT` |
| Read retained work context | `atlasctl packet PROJECT --work WORK_ID` |
| Read history | `atlasctl history PROJECT --limit 50`; follow `next_cursor` only as needed |
| Review coverage or a concrete gap | `atlasctl audit PROJECT` |
| Read an unknown local result | `atlasctl reconcile PROJECT` |
| Read an unknown writer checkpoint | `atlasctl checkpoint-reconcile PROJECT --operation OP_ID` |
| Refresh selected document snapshots | `atlasctl docs PROJECT --source-root PATH` |

Handle opening in this session; do not self-forward. `views` compares only the
selected matrix and makes no writes. Reload its verified stable URL for the latest
publication; immutable URLs/downloads remain historical. Confirm release/section
through the supported interface, or deliver its verified HTML/JSON downloads with
the actual opening status. Queued is not opened; see `workspace.md` for fallback.

Use the pinned absolute command if absent from PATH. In AgentOS, `agentos atlas`
exposes the same command family. Use its explicit `--registry PATH` where needed.
Native bindings use their declared routes in `operations.md`. Bootstrap only in
the chosen scope: WM-UI uses UPSTREAM/refresh, new native projects use `init`.
Preserve existing bindings and all available matrices; name gaps instead of
inventing history or repeating bootstrap. INITIALIZED_PARTIAL is not full coverage.

For remote UNKNOWN, read the original operation through its declared MCP route.
Neither the local CLI nor this instruction sends messages or repeats host effects.

### Перенести одну работу в пустой чат

**Важно:** в русской вкладке «Матрица работ» рядом с «Копировать» есть «↓ .md» — полный UTF-8 companion со встроенным SHA256/bytes манифестом, который можно приложить целиком. Эмодзи-счётчики показывают сколько исходных работ выполнено/в работе/ожидает/заблокировано/частично выполнено, включая нулевые категории, и не подразумевают онлайн-статус. Недостаток точной привязки — UNKNOWN и next owner, а не скрытая автоматическая привязка к общему каталогу.

Откройте текущую опубликованную матрицу Atlas, найдите работу (в том числе родителя/заблокированную/завершённую), нажмите **«Копировать»** и вставьте текст в чистую сессию. Пакет содержит существенные тексты документов, версии/хеши, related contracts/modules, evidence и следующий проверяемый шаг. «Скопировано» появляется только после подтверждённой записи; при отказе буфера откроется весь Markdown для ручного выделения. Копирование ничего не меняет в project matrix и не переносит полномочия. Новая сессия должна отдельно сверить текущие источники и writer/lease.
