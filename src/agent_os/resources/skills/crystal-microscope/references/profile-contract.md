# Portable map and measurement contract

## Contents

- Commands and scope
- Document structure
- Evidence and measurement passport
- Offline viewer and exact export
- Limits and interpretation

## Commands and scope

`scripts/microscope.py` uses Python 3.11+ and the standard library. It reads an
explicit UTF-8 JSON document. It does **not** scan a repository, attach to a
process, collect profiles, execute source code, contact hosts, fetch evidence,
change settings or grant permissions. Supply observations through the ordinary
authorized project workflow; reuse its existing journal and artifacts.

```bash
python3 scripts/microscope.py validate references/example.json
python3 scripts/microscope.py render references/example.json --output microscope.html
python3 scripts/microscope.py extract microscope.html --output recovered.json
```

Output files must be new. Existing files and symlinks are refused without
replacement. The output directory must already exist. `extract` reads the
embedded data without executing HTML; it does not certify arbitrary HTML as
safe. The bundled example is synthetic explanatory data, not a measured run.

A successful command explicitly reports `claims_verified: false`. Structural
validation checks fields, references and the presence of declared provenance;
it cannot establish source authenticity, actual execution, metric accuracy,
causality, completeness, permissions or product acceptance.

## Document structure

The top-level `schema` is `crystal-microscope/v1`. Required arrays are `nodes`,
`edges`, `runs`, `evidence`, and `metrics`; use `[]` when the section has no
records. IDs are unique within each section. Additional fields at any level are
retained, including nested objects and zero values.

`metadata` requires nonempty `revision`, `environment`, `question`, and `scope`
strings, plus an `unknowns` array of nonempty strings. State the actual snapshot
and scenario scope; an empty unknowns list is not a completeness claim.

Each node requires:

| Field | Meaning |
|---|---|
| `id`, `kind`, `title` | Stable local identity, entity type and readable title |
| `parent` | Containing node ID or explicit `null`; multiple roots are allowed |
| `contract` | Object describing inputs, transformations, outputs, state, ownership, failure/retry/cancellation where relevant; record gaps explicitly |
| `source` | Source-anchor object or explicit `null`; useful fields include revision, binary build ID, package/version, path, symbol/signature and line/range |
| `status` | One classification from the table below |
| `evidence` | Array of evidence IDs, possibly empty for an unobserved claim |
| `unknown_reason` | Required when status is `unknown` |

Parent relations must be acyclic. Edges are separate from containment: each
requires `id`, `from`, `to`, `kind`, `status`, and `evidence`. Its kind is one of
`call`, `message`, `data`, `ownership`, `wait`, `state`, `recovery`, `correlation`.
An unknown edge needs `unknown_reason`. Graph cycles are allowed: a wait cycle
may be the very hypothesis being investigated. A graph edge does not prove a
runtime call, and correlation does not establish a mechanism.

## Evidence and measurement passport

Use classifications consistently for nodes, edges, evidence `kind`, and metric
`status`:

| Value | Declared meaning |
|---|---|
| `declared` | Intended or documented, not yet checked |
| `source` | Grounded in the identified source; not a runtime claim |
| `runtime` | Observed within an identified run |
| `experiment` | Supported by the described controlled experiment |
| `hypothesis` | Proposed interpretation or illustrative/estimated value |
| `unknown` | Unestablished, with a concrete reason |

These labels are supplied claims. The tool never upgrades them. Source nodes
need a source anchor. Runtime claims need runtime or experiment evidence;
experiment claims need experiment evidence. A source-only reference cannot
be relabelled as an observed run by changing the node status.

Each run requires `id`, `scenario`, `environment`, and `revision`. Record further
details as applicable: host/boot/process-start identity, configuration, input
version, timestamps, duration and collection settings. Do not add sensitive
process data merely to fill fields.

Each evidence record requires `id`, `kind`, `locator`, `summary`, `run` (ID or
explicit `null`), and `limits` (string array). Runtime/experiment evidence needs
a run. Unknown evidence needs `unknown_reason`. Locators are displayed as text;
the tool never follows them. Evidence is not validated just because its path or
hash exists in a record.

Each metric requires `id`, `node`, `name`, `unit`, `status`, and `value`.
**Unknown is `null` plus `unknown_reason`, never 0.** Numeric values require:

- `run`: an existing run ID;
- `scenario`: the measured or estimated scenario;
- `method`: what collected/derived the value;
- `evidence`: at least one evidence ID, also for an estimate;
- `sample`: either a positive integer `count` with `selection` and `aggregation`,
  or `na_reason` explaining why sampling does not apply; never both;
- `clock`: clock identity and scope, or why time does not apply;
- `time_basis`: `inclusive`, `exclusive`, `not_applicable`, or `unknown`;
- `overlap`: treatment of concurrent/nested intervals, or an explicit N/A reason;
- `overhead`: measured collection influence, or an explicit unmeasured reason;
- `limits`: applicable constraints, missing coverage and uncertainty.

Units are explicit strings. Preserve distinctions between wall/CPU/wait time;
heap/virtual/resident/physical memory; logical/payload/wire bytes; direct counts,
samples and derived estimates. For a percentile identify its population and
aggregation. Record loss, sampling, PMU multiplexing, symbol gaps, run exclusions
and clock uncertainty when applicable. A passport does not make a weak sample
conclusive, and the validator cannot infer these facts from prose.

For hardware or runtime measurements, require the capabilities and exact
versions that actually exist. Missing symbols, unsupported tracing, inaccessible
kernel activity or closed libraries stay explicit boundaries. Keep timing and
security context; do not fill a missing method with a plausible name.

## Offline viewer and exact export

The generated HTML is one local file with no external dependencies or network
requests. It provides node search, parent/child navigation, typed relations,
source/evidence details, per-node measurements, and snapshot/UNKNOWN views.
All supplied content is inserted through DOM `textContent`; source or evidence
strings are not executable HTML or links. A restrictive content-security policy
allows only the bundled static script and style.

The document is embedded as base64 of its **original bytes**, not reconstructed
from filtered UI objects. The Export button downloads those original bytes;
`extract` provides a command-line roundtrip check. Extensions, original numeric
tokens, formatting and zero values are therefore retained. Detail formatting
uses browser JSON numbers; metadata/extension numbers outside its exact numeric
range can be rounded in the view, while the exported JSON remains unchanged.
Known numeric metric integers outside ±9,007,199,254,740,991 are refused: select
a justified scaled unit instead of silently rounding a measurement.

## Limits and interpretation

The current implementation admits 8 MiB UTF-8 JSON, 64 JSON nesting levels,
5,000 nodes, 20,000 edges, 5,000 runs, 20,000 evidence records, 20,000 metrics,
128-character IDs, and 128 containment levels. HTML extraction admits 16 MiB.
These are packaging limits, not project-completeness claims. Search displays
200 matches initially with a Show more control. Split a larger project into
explicitly related scoped snapshots; do not silently discard overflow.

Duplicate JSON keys, NaN, Infinity and exponent-overflow values are rejected,
including in extension fields. Inputs and evidence remain untrusted data.
Changing a map or rendering it does not install a patch or demonstrate live
adoption. At level 1 retain the useful whole and deepen selected unknowns;
do not require this format for every helper edit or repeat unchanged checks.
