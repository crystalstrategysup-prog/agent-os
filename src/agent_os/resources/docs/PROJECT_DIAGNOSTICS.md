# Project diagnostics

Use `agentos project diagnose` in the selected project directory, or
`agentos project diagnose --root /absolute/project` from elsewhere.

This optional command gives one bounded view of the facts already recorded in
that directory. It works before project initialization and without user overlay,
profile, task entry, READY, an Atlas registry, or an answers file. It creates
nothing and executes no project code or network request.

## Routine use

Read the selected project router and use diagnosis when the current binding or
document freshness is unclear. Reuse the existing project task and current
knowledge; collect only the additional facts needed for the intended change.
After a change, run the relevant existing check, update the owning document and
record its result in the existing workflow. Do not make diagnosis a prerequisite
for questions, reads, ordinary tasks, READY, or release acceptance.

A report provides one `next_action` for the most significant observed issue.
That action concerns the named surface. Continue independent authorized work
while resolving it. Diagnostics never creates a new hold or removes an existing
transaction, lock, writer, or authorization boundary.

## Observed surfaces

The command reads the selected root's `.agentos/project.json`, declared
document pins, and the task named by its active pointer. It checks known local
Atlas bindings at `.atlas/project.json` and `.atlas/UPSTREAM.json`, pinned
document/inventory references, and declared work-file presence. It also checks
local Markdown links in `AGENTS.md` and `README.md` and the presence of a finite
list of existing transaction/lock markers.

It returns metadata, relative paths, counts and SHA-256 hashes. It does not print
document or journal bodies, read credentials, walk source trees, discover other
projects, inspect processes, or repair pins. Markdown checking is a bounded
link check, not a complete Markdown renderer.

A terminal task pointer is recorded history; it does not prove that no process
is running. A nonterminal record does not prove current writer activity.
Missing default Atlas files do not prove that the project has no custom or
external binding. Select that existing binding before considering initialization.

## Result contract

The report schema is `agentos.project-diagnostics/v1`, with
`effect: READ_ONLY` and `advisory: true`.

| Status | Meaning |
| --- | --- |
| OBSERVED | The selected metadata was read; informational findings may exist. |
| FINDINGS | A missing, stale, or other selected local fact needs attention. |
| INCOMPLETE | A read, size, reference, or output limit prevented complete inspection of the selected surfaces. |
| NOT_QUALIFIED | The required safe file-reading primitives are unavailable on this platform. |

For a root opened successfully, all advisory result statuses exit 0. A root that
cannot be opened safely exits 2; invalid CLI arguments also exit 2. Consumers
must inspect the report to distinguish observations from incomplete coverage.
No result means whole-project acceptance or a permission grant.

Missing, unreadable, invalid, changed and stale references remain distinct.
Unknown or incomplete information is never presented as a verified absence.
Known pending markers are observations of the existing transaction owner.

## Bounds and portability

The limits are 4 MiB per JSON file, 512 KiB per document, 16 MiB of file reads,
256 declared references, 128 local Markdown links, 128 retained findings, and
32 KiB of UTF-8 stdout. Omitted rows are counted and output is marked incomplete.
A complete report means only the named, bounded metadata inspection.

Descriptor-relative reads reject path traversal, symbolic links, hard-linked
files and special files. The selected root must be a direct path on a qualified
POSIX filesystem. These checks are not a security boundary against a hostile
process running under the same OS identity.

## Atlas through the same CLI

The existing native Atlas interface is available as
`agentos atlas native --help`, for example:

```sh
agentos atlas native run project-audit --root /absolute/project --project .atlas/project.json
```

Native operations retain their own effect contracts. This route does not create
a registry or duplicate the project matrix. Registry-free native, profile and
help routes work with a global `--home` option. For registry-backed operations,
select the registry explicitly; `--home` never silently chooses one.

## Development checks

Run `python3 -B tools/verify_rebuild_contracts.py` for maintained version,
document, schema and catalog-pin consistency. Run the affected diagnostic,
Atlas, workflow and installer tests when changing those surfaces. These are
source-development checks, not new requirements for every user operation.
