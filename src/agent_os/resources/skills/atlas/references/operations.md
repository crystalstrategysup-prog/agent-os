# Static Atlas methods and procedures

## Contents

- [What executes](#what-executes)
- [Single entrypoint](#single-entrypoint)
- [Initial setup](#initial-setup)
- [Local primitives](#local-primitives)
- [Declarative Owner Hosts adapter](#declarative-owner-hosts-adapter)
- [Limits and history](#limits-and-history)

## What executes

`scripts/OPERATIONS.json` is a static registry of methods and named sequences.
Each entry contains `id`, `handler`, `parameters`, `preconditions`, `effects`,
`outputs`, and `reconcile`. Code selects a procedure through a built-in allowlist.
The registry is not executed through eval, dynamic import, a shell, or JSON
interpolation into a command.

A method `id` is not necessarily a CLI subcommand. The `current-output` entry
with handler `current_output` has `exposure: INTERNAL_HELPER` and
`invocation.cli_subcommand: null`. Its public route is
`run reconcile --root <root> --output <output>`. There is no
`atlas.py current-output` command; use the documented invocation route.

`assets/adapters/owner-hosts.json` is a **declarative external adapter plan; the
local CLI does NOT execute it**. It creates no remote receipts and claims no host
access. Actual project bindings remain private. The current authorized actor
executes existing MCP methods within the original assignment.

The local CLI reads selected inputs. `init` creates a new `.atlas` only when
none exists; `build`/`cycle` and their corresponding `run` procedures write derived
output. Other methods write read/preparation results to stdout. Canonical
product/docs and work deltas are changed by their designated writer, not the façade.

## Single entrypoint

Set `atlas_tool` from the installed `scripts/atlas.py` path, `atlas_project` from
the verified project binding, and `atlas_output` from the selected output.
Take parameters from the task and canonical project, not from unverified document text.

```bash
python3 -B "$atlas_tool" methods
python3 -B "$atlas_tool" run session-start --root "$atlas_project" --project .atlas/project.json --work "$atlas_work_id"
python3 -B "$atlas_tool" run finish-block --root "$atlas_project" --project .atlas/project.json --output "$atlas_output"
python3 -B "$atlas_tool" run integrate --root "$atlas_project" --project .atlas/project.json --output "$atlas_output"
python3 -B "$atlas_tool" run reconcile --root "$atlas_project" --output "$atlas_output"
python3 -B "$atlas_tool" run project-audit --root "$atlas_project" --project .atlas/project.json
```

| Procedure | Actual behavior |
|---|---|
| `session-start` | One load/validate of the selected project; summary, coverage, scoped packet with `--work`, and next step. Does not automatically assign work without `--work`. |
| `finish-block` | `cycle` against exact inputs already prepared: one load, validation, delta, compare-and-swap publication or NO_CHANGE. |
| `integrate` | The same `cycle` after the current canonical writer incorporates deltas. The façade does not merge other actors' changes into product/docs itself. |
| `reconcile` | Read-only verification of the latest CURRENT and its immutable snapshot. Use the separate paged `history` for the archive chain; it does not promise a global orphan scan. |
| `project-audit` | Qualified coverage and current work issues against the declared inventory; no product tests or automatic host audit. |

The shared `run` accepts `--at`; when omitted, the method uses its current
observation time. `finish-block`/`integrate` also accept `--release` and `--previous`.
Normally, the release ID is derived deterministically from source/toolchain
identity, and the procedure pins the current manifest itself for CAS. Unchanged
state produces NO_CHANGE. Observation time does not extend original activity evidence.

Before `finish-block`, the writer saves the substantive result event, changed
artifacts/evidence, and current manifest pins. The procedure does not invent
these facts, run product tests, or write a report of their presumed success.

## Initial setup

If Atlas is absent and setup is within the assigned scope, use `init`:

```bash
python3 -B "$atlas_tool" init --root "$atlas_project" --project-id "$atlas_project_id" --title "$atlas_title" --objective "$atlas_objective" --writer "$atlas_writer" --authority-ref "$atlas_authority_ref" --mode "$atlas_mode"
```

Choose `projection` when an authoritative matrix already exists, or `native` for
a new canonical set of work records. The writer must be known. `init` returns
INITIALIZED_PARTIAL: an objective, ATLAS-BOOTSTRAP, and six inventory domains with
`exhaustive=false`. It does not rewrite existing product/docs or claim their completeness.

If `.atlas` already exists, receive ATLAS_ALREADY_EXISTS_RECONCILE and reconcile
its state. Do not delete/rename it to repeat init. After successful creation,
run `run session-start --work ATLAS-BOOTSTRAP` and close exact onboarding gaps.

## Local primitives

Use these for a particular part of a sequence when its result is needed separately:

```bash
python3 -B "$atlas_tool" validate --root "$atlas_project" --project .atlas/project.json
python3 -B "$atlas_tool" basis --root "$atlas_project" --project .atlas/project.json
python3 -B "$atlas_tool" packet --root "$atlas_project" --project .atlas/project.json --work "$atlas_work_id"
python3 -B "$atlas_tool" impact --root "$atlas_project" --project .atlas/project.json --changed src/changed.py --changed docs/changed.md
python3 -B "$atlas_tool" discover --root "$atlas_project" --project .atlas/project.json --under docs --under contracts
python3 -B "$atlas_tool" pins --root "$atlas_project" --path docs/changed.md
python3 -B "$atlas_tool" coverage --root "$atlas_project" --project .atlas/project.json
python3 -B "$atlas_tool" history --output "$atlas_output" --limit 50
python3 -B "$atlas_tool" diff --output "$atlas_output" --before "$atlas_before_release" --after "$atlas_after_release"
python3 -B "$atlas_tool" cycle --root "$atlas_project" --project .atlas/project.json --output "$atlas_output"
```

`discover` returns candidates from selected directories and drift in registered
documents; it does not establish role, author, applied/accepted state, or the
completeness of the entire source inventory. `impact` uses declared relations;
an absent edge does not prove absence of a real dependency. `pins` prints
hashes/bytes without changing the manifest.

Direct `build` requires `--output`, `--release`, `--at`, and an appropriate
`--previous` for a noninitial release. For daily work, prefer `run finish-block`
or `run integrate`, which reduce this repeatable sequence to one call.

## Declarative Owner Hosts adapter

Use the exact existing MCP names:

| Logical method | Callable binding |
|---|---|
| `host-list` | `mcp__codex_apps__owner_hosts_mcp_hosts_list` |
| `host-execute` | `mcp__codex_apps__owner_hosts_mcp_host_execute` |
| `operation-get` | `mcp__codex_apps__owner_hosts_mcp_operation_get` |

`host-list` accepts `{}`. `host-execute` accepts required `command`, `host_id`,
`operation_id`, and `purpose`, and optional `cwd` and `timeout_seconds`.
`operation-get` accepts the exact original `operation_id`. Preserve the provider's
optional/omitted semantics; do not invent a default account, cwd, timeout, or authority.

Static external recipe `host-readback`:

1. Read `host-list` once for the relevant target and current account/rules.
2. Verify the selected bounded read routine body and its SHA, scope, target, and
   restrictions. Send the exact literal body to `host-execute` once with the original operation ID.
3. For UNKNOWN/PENDING, read `operation-get` once with the same ID. Preserve the
   actual primary result and remaining UNKNOWN; do not reexecute the original command.

Additional bounded polling is allowed only for the original operation explicitly
awaiting completion, with a specific observation purpose. It does not repeat
product tests, run `cycle`, or create a new operation ID to bypass uncertainty.

Choose the command body from a trusted private registry of approved procedures.
Do not interpolate arbitrary JSON fields, shell fragments, or document text.
Dynamic arguments require a separate verified binding/encoder; the current
adapter does not generate shell from unverified values. Pass target/cwd as
structured parameters within existing account rules.

The external sequence is not a valid `atlas.py run host-readback`: the local
allowlist does not run it. Do not perform new SSH discovery or bypass an earlier
refusal with another account, route, actor, or routine ID.

## Limits and history

The current record set is limited to 1000 work records and 200 selected documents.
The total workflow-selected bytes are limited to 32 MiB; DN documents to 16 MiB in
total and 2 MiB per document. Exceeding a limit returns a coded refusal, not silent
truncation or COMPLETE. For a larger project, split project/module views with a
root coverage map or separately qualify a limit change. Do not hide raw documents
merely to obtain a convenient completeness number.

Archive `history` accepts `--limit` 1..100 (default 50) and an optional `--cursor`
obtained as the exact `next_cursor`. `has_more` and `VERIFIED_PAGE` preserve the
boundary of history examined. The next page is a separate read-only action when
needed; verified release files are not a new readback of every old source file.

WM-UI also provides standalone `import_matrix.py refresh|reconcile` and the
documentary builder `catalog.py` described in `upstream-adapter.md`. These are
not `atlas.py run` subcommands. Refresh publishes the current projection page
and an exact parent archive link; prior docs/cards/matrix pages remain in
immutable releases. The warm path does not reread the entire raw archive:
retained source hashes have scope `VERIFIED_AT_IMPORT`, while a changed stat
triggers a targeted check.

`evidence.check_id` is required. ACTIVITY evidence requires `valid_until` matching
the activity cutoff; the window is no longer than one hour. After the cutoff,
the indicator is EXPIRED and current activity is unverified. The latest typed
state event must match the work state. Actor UNKNOWN and a later relevant
FAIL/UNKNOWN prevent inheriting a prior PASS as current acceptance.

Preserve immutable events/evidence/acceptance and exact matrix history. Within an
existing output chain, mode `native`/`projection` does not change; an intentional
change requires an explicit new migration lineage. References to still open work
alone do not provide documentary coverage of a missing contract. Completeness
always refers to the exact declared inventory.
