# Find the current handoff

A request to show or resume a handoff is a read-only lookup. It needs no project
intake or task creation. Identify the requested project from current context or
the user's selected index before searching. Ask only if that identity is unknown.

## Lookup order

1. Read the selected project's concise AGENTS/README and its explicit current
   handoff or document index. Verify that the path exists and the record names
   the intended project, source, date, last result, open work and next step.
2. If no project is selected, read only the relevant entry in the user's
   declared cross-project index in the external overlay. This index supplies
   private pointers; public AgentOS does not create or discover a global
   handoff directory automatically.
3. If an indexed path moved or is absent, search within the one verified project
   root or the exact declared user location. Do not scan all backups, releases,
   transcripts or unrelated workspaces. Do not fall back to an older global
   directory just because it exists.
4. Before opening or presenting a folder as current, read its index or selected
   handoff and confirm scope/current status. If no current record is available,
   report that gap and the verified project location. An archive may be shown
   only with its date, project and historical status explicit.

## Distinguish the surfaces

| Surface | Purpose and evidence boundary |
| --- | --- |
| Installed core resources | Universal instructions/templates; find them using `agentos resources`. They contain no user's project handoffs. |
| Project current handoff | One maintained project record linked by its AGENTS/README or document index; recheck source and runtime when resuming. |
| Project lifecycle results | Local `.agentos` records and generated result reports describe individual tasks. CLOSED is not proof of current project/runtime state or a current handoff. |
| Private cross-project index | User-owned pointers outside public core; no credentials, automatic execution or implied access grant. |
| Legacy packets and backups | Dated history; existence, filename and newest timestamp alone do not establish current authority or status. |

There is no public runtime-wide `state/handoffs` convention. A private provider
may maintain its own packets; verify that provider and the requested project
before using them. Do not substitute a framework's development `docs` folder
for another project's current handoff.

## Record and maintain

Use `resources/templates/handoff.md` for a project record. Include source and
runtime separately, last verified checks and dates, unfinished work, authority
limits and next safe step. Link current primary documents rather than copying
history. A folder link alone is not a handoff.

Update the project pointer and any selected private index after a handoff,
release, source move or runtime switch. Keep the previous dated record as
history. A read-only lookup does not authorize writing a missing handoff or
rewriting instructions; do that only in an authorized change.

For installation freshness, read the managed pointer and installed version,
then check the official public release with a date. An installed version and a
source checkout are different facts; a previously correct answer can become
outdated after a release. Never silently substitute a source version for the
installed runtime. See [INSTALL_UPDATE](INSTALL_UPDATE.md) and
[WORK_CONTINUITY](WORK_CONTINUITY.md).
