# DN-01.4 finite document-record capacity

AgentOS source candidate0.8.0rc2032 supports at most1000selected document
records, including archived records. navigator.schema.json, navigator.MAX_DOCUMENTS
and OPERATIONS.limits agree.1001records fail closed. This versioned finite
engineering envelope adds no override flag or automatic/unbounded growth.

The native current index keeps every published ID, logical path, pin, version,
evidence and history entry. Appending a new version does not delete/rebind an
old document. Existing immutable release snapshots remain the exact linked
publication archive; this change adds no native pagination or external archive.
Archive lifecycle does not free a slot. Projection-only paging is not a native
mode-switch route.

Unchanged byte ceilings:2MiB/document,16MiBselected bodies total,8MiBinput
manifest,32MiBAtlas workflow-selected bytes,32MiBsnapshot,48MiBrendered HTML.
Whichever bound is reached first refuses. Metadata now records the already-
current16MiB aggregate; that runtime byte limit is not raised here. Complete
bodies, hashes, schema shape, append-only history, path/symlink, parent/lineage,
writer locks, CAS and orphan/rollback guards remain strict.

Install/adoption require separate exact review and target authority. The original
200-record project needs no identity/mode transformation: preserve its200records,
append the pinned201st under the same project/index, then run all remaining
semantic/pin/lineage checks before existing native CAS publication. Source
capacity proof does not accept the actual target candidate or activate a selector.
Predecessors can read unchanged historical outputs within their byte bounds;
they refuse rebuilding source above200records. Roll back software separately,
never remove/rewind history to force an older tool to publish. Growth beyond1000
or another byte bound requires its own reviewed finite successor. Savings and
actual target runtime remain UNKNOWN.

## Historical DN-01.3 aggregate-capacity note, retained verbatim

The following describes the predecessor, not the current1000record ceiling.

# DN-01.3 finite selected-document capacity

Owner-local AgentOS0.8.0rc2005 changes navigator.MAX_TOTAL from8MiB to16MiB
(16777216 bytes). The load API/schema, complete bodies and SHA256 verification
are unchanged. At16MiB exact the aggregate is accepted; one additional byte is
refused with TOTAL_LIMIT. This is a finite engineering resource bound, not a
waiver of a security/protected-data refusal. No approval flag, fallback reader,
deduplication/truncation, history exclusion or automatic limit increase exists.

Unchanged ceilings:2MiB per document,200 selected documents,8MiB input manifest,
32MiB Atlas-selected workflow bytes,32MiB snapshot and48MiB rendered HTML.
Highly escaped input may hit an output ceiling before16MiB; publication then
refuses without changing CURRENT. Path/symlink/schema/hash/UTF8 and append-only
history protections, publisher lock and manifest CAS remain active.

Use the same load/build/Atlas finish APIs after separately reviewed versioned
installation. No source or binding edit is needed to select the successor.
Old8MiB-valid inputs remain valid; all normative texts are retained. The
predecessor can read unchanged immutable output within its existing output
bounds but cannot rebuild inputs above8MiB. Rollback software separately from
project history; never rewind source, remove documents or change protected
acceptance criteria to make an older binary publish.

The source180 capacity observation8387666B/spare942B is dated task evidence,
not a constant in code. A future aggregate above16MiB needs a separate bounded
capacity assessment; this release promises finite result-publication headroom,
not unlimited growth or completion of the underlying project.
