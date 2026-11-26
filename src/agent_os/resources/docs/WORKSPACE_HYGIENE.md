# Workspace hygiene and temporary data

Keep enough usable capacity to finish the authorized work and retain its result.
The owner of a run also owns the disposition of its temporary resources: release
qualified reproducible data, complete an accepted transfer, or leave a justified
hold with a responsible actor and a review event. Apply this at development
levels 1–5 and diagnostic level 0. Use one record per private resource root in
the existing task/run journal; ordinary derived files inherit that root's class.

The operational method is the marked **Workspace hygiene** section of
[PROCESS](PROCESS.md#workspace-hygiene), available through
`agentos workflow guidance --method workspace-hygiene`. Read its actual body
before a material build, test, restore, package, download or cleanup operation.
Reuse it while its relevant facts remain current. The existing
[proportionate protection rule](PROCESS.md#proportionate-protection-of-data-and-runtime),
[data retention policy](DATA.md#migration-and-retention) and target authority
remain in force.

## Current capability and limits

| Capability | Current status | Consequence |
|---|---|---|
| Canonical work method and routed client instructions | Delivered guidance | The agent records and performs the applicable obligations; loading the text is not proof of application. |
| `agentos project resource plan --input PATH\|-` | Read-only observation and planning | Consume a bounded explicit private descriptor and emit metadata-only observations and a plan. No task registration, reservation, lease release, deletion or stage acceptance occurs. |
| Existing qualified cleanup owned by a run | Existing operation, within its own scope | The owner may finish an already authorized routine without asking for each derived temporary file. The new plan is not its permission or executor. |
| Native resource registry, cross-project reservations and close integration | Proposed successor | No such registry or capacity reservation is established by this release. Existing inventory/task-metadata budgets remain reader/metadata bounds. |
| Native cleanup `apply` and `reconcile` | Proposed successor | No new deletion API, scheduler, mass cleanup or automatic backup removal is enabled. |
| Destructive Linux, macOS and remote profiles | Separate qualification required | A plan or Linux observation does not qualify deletion, remote execution, APFS accounting or other platforms. |

The existing completion checkpoint space check remains applicable to its own
operation. Logical handoff retirement retains history and reports zero reclaimed
bytes; it remains distinct from physical resource release. Installation of this
method must not relabel old unclassified directories as disposable.

### Observation input and output

The implemented request is `agentos.resource-observation-request/v1`, distinct
from the proposed native lifecycle schema below. The exact machine contract is
[project-resource-observation-request-v1.schema.json](../schemas/project-resource-observation-request-v1.schema.json);
[project_resources.observe_plan](../src/agent_os/project_resources.py) is the
shared library entry used by the CLI. Use its current help/schema for field names,
enums and bounds instead of inventing a deletion or reservation command.
The installed copy is `resources/contracts/project-resource-observation-request-v1.schema.json`,
located with `agentos resources`.

Pass the bounded private descriptor as a JSON file or stdin. It names opaque
project/task/run/operation IDs, explicit admitted-root path mappings, selected
resource declarations and optional capacity observations. Supplying IDs registers
nothing and proves no host authority. Actual path mapping and relative resource
names stay in this private input; ordinary output uses opaque IDs. Keep the
input on its owning host, outside public issues, releases and shared journals.

The request permits 1–16 roots, up to 128 resources and 16 capacity records within
256 KiB; resource and capacity lists can be empty. Missing ownership, reproduction,
process, dependency, release or capacity facts use the schema's null/UNKNOWN
values. A declared STOPPED state, clear dependencies, reproducible input reference
or satisfied release condition remains a caller statement. A retention record
names the responsible actor and exactly one next-review time or release event;
expiry itself authorizes no removal. Quota/reservation declarations are identified
as supplied inputs, not measurements or promises made by the observer.

No recursive resource-content scan, resource-file-content read, hashing of an
arbitrary tree or discovery of other projects occurs. The output
`agentos.resource-observation-plan/v1` has status `OBSERVATION_ONLY` and contains
selected object/filesystem metadata, safe bounded reasons and next actions.
Resource classifications are `HOLD`, `RETAINED` or
`CANDIDATE_FOR_QUALIFICATION`. Candidate evaluation is limited to `build-output`
and `test-database` with the required declarations and Linux metadata checks.
A candidate has not established safe deletion, exclusive control, actual process
termination or a usable recovery route. Other classes retain their own policy.

Observed object identity includes type, device, inode, UID/GID, mode, link count,
mtime and ctime in nanoseconds. A regular file reports its logical length and
allocated bytes from `st_blocks * 512`. A directory's content size remains null
and `NOT_MEASURED`; its `st_size` is not the size of its tree. Linux mount evidence
includes namespace inode and mount ID. The volume ID is an opaque device-pool
identifier. Available bytes use `f_bavail * f_frsize` and available inodes use
`f_favail`; totals are included when available. Filesystem observations are not
an independently measured quota or a guarantee of future availability.

Capacity results group the observed same-device pool rather than add its free
capacity once per root. They report `FITS_REPORTED_VALUES`, `INSUFFICIENT` or
`UNKNOWN`, always with `admission_granted:false`. Device-pool accounting does not
establish permission to recurse across a bind mount. Positive arithmetic is
not a concurrent allocation guarantee.

The capability flags remain `effects:NONE`, `physical_cleanup_supported:false`,
`reservation_supported:false`, `apply_supported:false`, `authority_granted:false`
and `native_hooks:DISABLED`. Save a useful observation in the existing work
journal when relevant. The command itself writes no registry, journal or run
state and adds no daemon or scheduled cleanup.

## Before creation and heavy work

Choose the actual host, private root and filesystem before creating a resource.
Record its project/task/run, creating operation, owner, class, reproduction or
recovery reference, consumers and release condition. Keep actual path mapping
private on the host. Use opaque resource/root IDs in ordinary plans, exports
and shared journals: paths can contain names or credentials. A path prefix,
age, filename or matching UID alone does not establish ownership.

A private build tree or disposable database needs one root record. Its known
ordinary derivatives inherit provenance and class. Independently owned data,
a recovery copy, durable evidence or a handoff inside the tree needs its own
classification. Unexpected or unclassified contents remain HOLD until their
provenance and dependencies are established. Do not search unrelated roots to
find material to delete.

Estimate the largest simultaneously live **new writes** on every affected
filesystem: download/archive, expansion, database/WAL, intermediate output,
package, final placement, retained partials and an actual retry overlap. Reading
an existing input in place does not allocate it again. Use a comparable measured
run or a justified upper bound; no universal expansion multiplier or free-space
percentage is prescribed. If growth is unknown, use bounded chunks with renewed
checks, or a qualified exclusive window with an enforceable limit.

Measure bytes and inode availability to the current identity, applicable quotas
when known, relevant mount identity and the outstanding unconsumed promises of
other participating runs. Include a justified service margin and space for the
result and emergency journal. For a known required quota that cannot be measured,
use an independently verified bounded area or pause the dependent write; an
unknown quota is not unlimited. External writers can still change availability.

The intended admission arithmetic is available capacity, constrained by known
quota, minus other runs' **unconsumed** reservations and the service margin,
compared with the requesting run's remaining peak. Check bytes and inode budgets
separately. Decrease the unconsumed reservation as physical writes occur to avoid
counting the same allocation twice. For example, 220 units available minus 40
margin and 100 outstanding for another run leaves 80; a request for 90 waits.
This arithmetic describes a decision model, not a native reservation made by
the read-only observer.

## Classes and release conditions

| Class | Retain until | Qualified disposition |
|---|---|---|
| Scratch, intermediate calculation, unpacked/download staging | Inputs and reproduction route are available; required output is accepted or delivered and read back | Release the owned stopped resource. A private incomplete download may be recreated if its source and identity are known. |
| Build output | Source, toolchain and lock/input references can reproduce it; consumers have finished | Release the private output root after retaining the required result. |
| Dependency or computation cache | Its ownership and references are known | A private cache follows its owner's scope. A shared cache belongs to its cache manager and waits for all references. |
| Disposable test database | Isolation, repeatable seed/migrations and termination of the exact target process are established; diagnostic evidence is retained | Release the qualified private cluster. Unique changes, active consumers or uncertain termination give HOLD. |
| Temporary recovery copy | Its protection purpose, rollback window and dependencies are resolved; a usable replacement or exact restoration route is verified | Record closure of the window and release only the no-longer-needed copy. |
| Durable backup or accepted checkpoint | Its separate retention/recovery policy permits disposition | Exclude from temporary cleanup. No guessed age threshold or automatic expiry. |
| Final result, receipt or required journal | Project evidence and delivery policy permits disposition | Retain the authoritative result. A separate packaging copy may be released after destination content is verified. |

For a recovery copy, verify the replacement from the place where restoration
would run: availability, size/digest, dependencies, required access and reading
or restoration according to its class. Replacing the only copy of a critical
dataset requires a successful restoration check of the replacement. A hash alone
does not establish usability. Keep active backup/restore dependencies and the
recorded rollback window open until their actual conditions close.

Keep the original operation ID, intent, result, local database, keys and external
witnesses needed to reconcile PREPARED/UNKNOWN effects. A durable accepted transfer
can assume that responsibility only after readback verifies the mapping. These
records are not temporary merely because the producing process ended.

## During execution and at completion

Maintain resource ownership and the current consumer relationship. The normal
exit and exception path run the qualified cleanup in `finally`; an abrupt exit
requires reconciliation before a new attempt. Process termination must be tied
to the exact host/boot, process start identity, parent run, locks and data root
where applicable. An expired lease or absent PID file triggers reconciliation;
neither is proof that the resource is unused.

At a substantive checkpoint, close or handoff, record one disposition for each
registered resource of this run: released with evidence, transferred with
receiver acceptance/readback, or retained with reason, responsible actor and
next review date or release event. An overdue review calls for a fresh decision,
not deletion. Uncertain resource state remains held or is explicitly transferred
for reconciliation. Unrelated historical material outside this run does not
block the current stage.

These are current agent obligations in the existing work record. This release
does not add an automatic native close gate or alter accepted task/check history.
Keep the note proportional: resource IDs, outcome, material remainder and next
actor are sufficient. Do not create another report/archive for each helper or
ask the owner again for disposal already included in the authorized private run.
If disposal is outside that authority, preserve the resource and isolate that
decision while other permitted work continues.

## Convenient cleanup procedure

1. **Inspect the plan.** Start with the selected run's resource IDs, observed
   state and HOLD reasons. Choose a useful bounded set; preserve the private
   path mapping and identify the exact owner.
2. **Resolve its dependencies.** Let the owner close its own process/consumer
   and complete its normal `finally`. Confirm the output's durable destination,
   recovery conditions and absence of unresolved operation dependencies.
3. **Use a qualified existing routine.** Recheck identity, authority and the
   exclusive private scope immediately before effect. Record intent and result
   outside the removable tree. This observer never executes the routine.
4. **Read back the effect.** Check the original object and destination; retain
   uncertain outcomes under the original operation ID. Never retry an unknown
   delete against whatever now occupies the same name.
5. **Update the existing record.** Record the result, space measurements and
   attribution limit, or a transferable HOLD with the actor/event that can
   resolve it. Continue the next authorized step once this scope is sufficient.

The useful owner view is a compact list of resource ID, class, run/owner,
estimated size, release/HOLD reason and next action. A long list of filenames
without ownership or release conditions is not a cleanup plan. Observation can
make the next action clear while leaving a genuinely unknown condition explicit.

## ENOSPC, EDQUOT and partial writes

On negative capacity admission, ENOSPC or EDQUOT, stop admitting new heavy writes
to the affected filesystem. Capture bytes, inode and quota observations, the
known owned temporary resources and open-deleted-file evidence when observable.
Distinguish the immediate failed resource from an unmeasured accumulation cause.
Do not attribute an entire incident to backups or caches from a full-volume
snapshot alone.

Consider another volume only after checking its capacity/quota, inode behavior,
rights, lifetime and memory headroom if it is memory-backed. Separate temporary
test data from durable final results and controlling journals. Recheck the final
destination as well as staging; freeing one filesystem says nothing about another.

Preserve the previous accepted output. Publish a new critical result through an
exclusively created sibling partial, bounded writing, size/hash readback, file
fsync, atomic replacement within the filesystem and directory fsync as supported
by the qualified publisher. A failed write is a partial outcome, not a successful
empty result. Rebuild only reproducible outputs whose inputs are retained.

Budget durable intent and emergency outcome recording. If the required journal
cannot be written, pause new deletions until its reliable storage is restored.
Do not use an unrecorded destructive action to make a success receipt fit.

## Proposed native resource lifecycle

The proposed `agentos.run-resource/v1` is a successor design, **not** a schema
implemented or registered by the current observation command. It should bind
resource/project/task/run/operation/owner; host/volume/admitted root and private
relative mapping; type and object identity; class/state/revision/generation;
lease/process identity; inputs/dependencies/recovery/release condition;
capacity scope, reservation, attempt and evidence. Persist sensitive mapping
only on the owning host. One creating operation establishes the exclusive object;
ordinary unclassified existing files default to HOLD.

The intended transitions are REGISTERED → ACTIVE after exclusive creation and
identity binding; ACTIVE → CLOSED after owner/consumers stop; CLOSED → ELIGIBLE
when class conditions hold, or RETAINED while dependencies remain. A new fact
and recheck can make RETAINED eligible. HOLD preserves an ambiguous object until
a new observed basis and revision resolve it; age alone only schedules review.

The future executor records durable intent before ELIGIBLE → RELEASING. A verified
result completes RELEASED. Response loss produces UNKNOWN and reconciliation of
the original operation, not replay under a new ID. A repeated apply to RELEASED
returns its prior receipt; the same ID with different arguments conflicts. A new
object at the same name has a different resource identity. Absence proves that
the original name is absent, not how many bytes this operation reclaimed.

Future reservation issuance/recalculation must share a short host lock/CAS across
projects on the same volume and overlapping quotas. Multiple-volume admission
takes locks in a stable order and either grants the set or releases its partial
reservation. The registry accounts for participating actors and cannot guarantee
that unrelated writers leave capacity unchanged.

Future `register`, `reserve`, `release-lease`, `plan`, `apply`, `reconcile` and
`status` must share one service beneath the CLI/library. A mutation accepts
registered IDs, current revision, qualified profile and operation ID, never an
arbitrary absolute path. A pinned dry-run plan includes identity and reasons;
apply rechecks current conditions under the correct lock and fences. Drift
preserves the changed object. The journal lives outside every removable tree.

## Destructive profile qualification

One cleaner owns an admitted scope. Use operations relative to an open trusted
private directory descriptor, refuse symlinks and unexpected independent objects,
check component/type/object and mount identity, and never remove the admitted
root itself. A bind mount can share a device number: device equality alone is
insufficient. Leave multiple hardlinks on HOLD in the initial profile. Prevent
concurrent writers in the parent and target tree for the operation; repeating
`lstat` does not eliminate a substitution after the check.

Linux qualification binds mount identity in the active namespace. macOS requires
its own volume/mount and file-ID checks, including the attribution limits of
APFS snapshots/clones. A remote adapter needs exact operation reconciliation
and target capability/authority. If the platform cannot reliably fence the tree
or identify the object, preserve it on HOLD. A host write prohibition keeps the
read-only plan available and any apply unavailable.

Qualification is incremental:

| Stage | Scope and evidence needed | Claim permitted |
|---|---|---|
| Current observation stage | Explicit bounded descriptors, real read-only observations, privacy and refusal tests, useful plan with honest unknowns | Observation/planning and agent method only; no allocation or deletion acceptance |
| First native Linux profile | One disposable project, two runs/agents, private test PGDATA and build output; observed registration/admission/normal-exception-close/plan/apply/reconcile chain | Only the exercised local Linux classes and profile |
| Extended resource profiles | Download staging, caches, temporary recovery copies, verified rollback windows, several volumes and quota conflicts | Only each exercised class, volume and reservation behavior |
| macOS and remote profiles | Qualified identity/fencing, adapter uncertainty/reconciliation, APFS or remote accounting and shared-cache ownership | Explicit per-platform/per-adapter acceptance |

For the first destructive profile, require meaningful checks: success/exception
and idempotent cleanup with a foreign control file unchanged; crashes before and
after unlink with a same-name replacement preserved; two runs/cleaners and stale
plan/lease/identity/mount drift; live or reused PID, backup/restore and UNKNOWN
retention; separate block/inode/quota exhaustion and an open-deleted file; partial
publication and unavailable journal; and refusal for unsupported platform,
symlink, hardlink, nested bind mount or uncontrolled writer. Check actual effects
and durable receipts, not just function return labels.

Report removed names, known allocated blocks and available-volume delta as
different measurements. Concurrent writes can make the last delta zero or
negative. An open deleted file can keep blocks until its last descriptor closes.
Record timestamps, mount/quota scope and attribution quality; actual reclaimed
bytes may remain UNKNOWN even when release of the original name is confirmed.

Start a new native rollout in observation mode on one project. Enable apply only
after its qualified profile is accepted. Rollback disables new deletion while
retaining the resource registry, intent and receipts needed for reconciliation.
No stage authorizes broad cleanup of historical directories, accepted evidence
or the owner's other projects.
