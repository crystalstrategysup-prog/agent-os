# Work-continuity scenario

Use this guide when a person wants to preserve enough verified context to
resume work after changing devices, losing a workspace, or handing projects to
another agent. The output is a small **continuity passport**: an index and
current handoffs, not an archive of all project files. Start from the packaged
`resources/templates/work-continuity-passport.md` template. A filled passport
belongs in the user's external overlay or another user-controlled location;
never include it in a public AgentOS release.

## What to record

For each active project, record the owner's goal, canonical source and primary
documents, the last verified result with its date and evidence, unresolved
issues, and the next safe action. Distinguish the actual source of truth from a
working copy, old handoff, chat title, or inferred host. An unknown location or
status is written as **unknown**, with a concrete step to verify it. Do not
convert a dated observation into current state.

Keep a separate data map: where code, databases, media, account data and
credentials are held; which items exist only on this device; which systems
have an independently checked copy. Record references and recovery procedures,
not raw secrets, session strings, database contents or personal files. A
credential can be named by type and recovery owner without recording its value.

## Guided route

1. **Define the boundary.** Ask what continuity is needed: project intent,
   current handoff, data recovery, or all three. Identify the device or workspace
   at risk and the proposed destination for the passport. Reading and planning
   do not authorize deletion, account access or data transfer.
2. **Inventory selectively.** Use current project READMEs, stage/result records,
   repositories, relevant task summaries and verified host references. Keep the
   passport an index; link to detailed documents rather than copying whole
   histories. Note source, observation time and confidence for every claim.
3. **Write one current handoff per project.** State the goal, canonical source,
   accepted decisions, exact last checked result, open blocker, limits and next
   safe step. Identify concurrent work rather than silently treating a branch
   or chat as finished.
4. **Map data and exceptions.** Separate knowledge from working data. Mark
   unpushed commits, local-only files, databases and exports explicitly. A
   repository remote does not prove that ignored files, user settings, media or
   research data are preserved.
5. **Verify recovery.** Compare the passport copy by size and hash, open it
   from the intended destination, and where possible verify an independent
   remote or separate-device copy. For each irreplaceable data class, confirm a
   backup or live source and restore a sample. A file visible in a local sync
   directory alone does not prove server sync or restore.
6. **Close or mark gaps.** Record what was actually verified and what remains
   unknown. Do not call a device ready for clearance while required data lacks
   a tested recovery path. Device erasure is a separate, explicit operation.

## Keeping it current

Update the passport after a release, handoff, source move, host migration,
major owner decision, or recovery test. A scheduled check may detect missing
links, stale dates or mismatched hashes, but it cannot establish the meaning of
a project or prove a backup by itself. The owner or responsible project agent
reviews changed goals, authority and data locations. Keep older snapshots as
dated history outside the compact current index when useful.

The template's status vocabulary is `verified`, `documented`, `unknown` and
`stale`. Use `verified` only for a dated read-back of the exact source or data;
`documented` means a source claims it but no current read-back was made. This
guide has no executable provider and grants no rights over an external host.

For current handoff lookup, follow [HANDOFF_DISCOVERY](HANDOFF_DISCOVERY.md).
