# Tracked directory aliases in project source snapshots

Current public version: `0.7.1`. RC-labelled sections below are retained historical records, not current installation or publication claims.


The historical `0.6.0rc3` package candidate includes the exact tracked-directory-link fix
from a tested `0.6.0rc2` source predecessor. The original reviewed RC2 wheel
does not contain this change. Independent source/package reviews are pending;
this candidate is neither host acceptance nor permission to install a core.

`project snapshot` and lifecycle readiness/check/close snapshots can inventory
a tracked internal directory symlink as metadata. For example, a repository
may track `backend/app/contracts` with exact target `../contracts`, while the
real tracked files live under `backend/contracts`. The alias is recorded once;
it is never followed or used to read files. Real directory content is hashed
through its ordinary canonical paths. Existing no-link snapshots retain their
exact output shape and identity.

## Admission and identity

The project must be the actual Git working-tree root. Local Git index reads
must establish exactly one stage-0 entry with mode `120000`. The working link
target bytes must match the index blob OID (SHA-1 or SHA-256 object format).
The relative target is checked component by component through existing ordinary
directories. `..` is permitted only while remaining inside the project; each
intermediate component is checked even if a later `..` cancels it. Absolute,
escaping, broken, symlink-chain, untracked and excluded/private targets fail.
The final directory must have ordinary tracked file entries and no conflicted
index entries. File symlinks remain refused. A missing Git executable/repository,
dirty link target, index conflict, or unavailable metadata fails closed.

Snapshot `files[link_path]` contains a SHA-256 digest of the stable link metadata.
An optional `symlinks[link_path]` record includes `kind`, exact `target`, contained
`target_path`, `git_mode`, `git_blob_oid` and SHA-256 of the link text. No target
contents, device IDs or inode numbers appear in this record. The link counts
toward the existing inventory entry/byte bounds. Consumers must use the record
as link metadata, rather than assuming every `files` entry is a regular file.

During each inventory, local link/parent/referent identities and index entries
are checked before and after enumeration. Detected replacement or index drift
refuses the snapshot. Git output is capped at 4 MiB per query, with a five-second
termination timer; inherited Git repository/index overrides, global/system Git
configuration and fsmonitor commands are excluded, and optional index writes
are disabled. No network, hooks, filters or user scripts are needed.

This is ordinary substitution detection, not an atomic filesystem snapshot or
isolation against a hostile process with the same user ID. Normal source-file
hashing retains its existing concurrency limits. Generic `safeio.filemap`,
overlay imports, `within`, regular JSON reads and write destinations keep their
strict default symlink guards. There is no global allow-symlink switch.

## Verification and rollout

`tests/test_source_links.py` covers the tracked relative directory alias, exact
identity and no alias traversal, real target content drift, normal
READY/check/close/verify lifecycle, strict existing guards, unsafe/conflicted
links, intermediate path traversal, mid-inventory substitutions, Git output
bounds/environment/fsmonitor and both object formats. Existing foundation tests
cover the affected lifecycle and storage contracts. These are synthetic local
fixtures, not evidence of acceptance on a remote production contour.

Release as a separately reviewed, uniquely versioned fixed wheel; do not patch
an installed immutable RC2/older release in place or regenerate its manifest.
Target install/activation needs its own approval, fresh exact-current and
queue/caller compatibility, verified wheel/installer hashes and independent
rollback facts. No project link deletion, gate bypass, policy migration or
production promotion follows from preparing this source fix.

## Historical: Mandatory handoff capture in0.7.0rc1

When an approved write scope contains an admitted tracked directory alias, close and checkpoint save its exact snapshot metadata as regular JSON under `source-links/`, separate from canonical source paths. They never read bytes through the alias, never restore it as a file and never create a symlink. The original alias path is explicitly not restored; a required unknown dependency makes the recovery report PARTIAL even when all real files are captured. Capture retains admission rechecks through publication and validates the current source/docs against the capture snapshot. Link replacement (including identical target text), link index drift and target index drift refuse the terminal transition. This retains the documented ordinary substitution detection boundary; it does not claim atomic same-UID isolation.
