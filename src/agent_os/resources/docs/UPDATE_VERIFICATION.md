# Dependency-scoped update verification

An update must establish the new artifact and current target state. It need not
reprove every unchanged component. Repeated discovery, complete regressions,
rollback rehearsals and unchanged integration rewrites are avoidable work when
their exact dependency evidence is already available.

## Cause and bounded correction

The former update skill required an isolated rollback rehearsal and a fresh
client without distinguishing changed dependencies or the claim being tested.
The existing `repeat_decision` helper was not connected to that procedure and
accepted an arbitrary repeat reason. This left broad retesting as the default.
Executor over-reading and verbose narration added avoidable context and latency;
network waits were a separate observable cost, not an inferred root cause.

Use `agent_os.investigation.verification_plan` before expensive work. Its module
entry calls the same implementation:

```sh
python -B -m agent_os.investigation --update-plan REQUEST.json
```

Use the selected installed release interpreter, or `PYTHONPATH=src` for source
qualification. The command reads one bounded JSON file or `-` for stdin, emits
one plan and writes nothing. It never runs checks, changes a target or authorizes
installation. No private profile, history scan, scheduler or second writer is
introduced. The existing installer remains the activation owner.

## Request and evidence contract

The request has exactly `checks` (1–64 records) and `evidence` (0–256 records).
Each check has exactly:

- `id`: unique nonempty string, at most 80 characters.
- `kind`: `artifact-integrity`, `compatibility`, `post-install-smoke`,
  `regression` or `installer-rehearsal`.
- `dependency_pins` and `environment_pins`: maps of at most 128 nonempty names
  (at most 256 characters) to lowercase SHA-256 strings. Pin the transitive code,
  tests, contracts, fixtures, guards and relevant interpreter/dependency profile.
- `coverage`: `COMPLETE`, `PARTIAL` or `UNKNOWN`.

The plan must contain all three fresh kinds. Each always returns `RUN`, even
with a matching PASS. This is a verification plan, not a list of install actions.
The installer's plan, current-pointer CAS, protected data/lock checks, actual
activation and handling of an ambiguous outcome are never cached or bypassed.

Each evidence record has exactly `check_id`, `input_key`, `outcome`
(`PASS`, `FAIL`, `UNKNOWN`, `BLOCKED`), `receipt_ref` (1–512 characters) and
`receipt_sha256`. Both digests are lowercase SHA-256 strings. Evidence is ordered
oldest first: the last record for a check supersedes an old PASS. `input_key`
comes from the previously returned check row and binds the complete check,
including its kind, coverage, dependencies and environment.

Before passing evidence, the caller verifies retained receipt bytes against its
hash and checks that its successful result proves this precise dependency scope.
The pure planner does not authenticate caller-supplied provenance or infer a
dependency closure. `COMPLETE` is a reviewed declaration, not a discovery result.
An absent/mismatching PASS, empty pins or partial/unknown coverage yields `RUN`.
Never relabel a subset COMPLETE to make reuse possible. Malformed/extra fields,
duplicate IDs, missing fresh kinds and unsupported effect kinds are refused.

Output schema is `agentos.update-verification-plan/v1`: `checks` contains each
`id`, `action` (`RUN`/`REUSE`), `reason` and `input_key`. Reused rows retain their
receipt reference/hash. `execution_authorized` is always false. This version
adds no persistent state or migration and does not change legacy repeat APIs.

## Execution and stopping

Read the current change list and affected fragments once. Batch independent
reads; avoid dumping manifests or historical documentation. Run the selected
checks through their owning approved runner once; do not run an identical suite
manually and then repeat it only to obtain a workflow receipt. Perform only the
authorized activation, then obtain current readback.
A fresh native client is needed for changed native integration or a native
adoption claim; a CLI-only update can be checked in new CLI processes.
Refresh managed instructions only when their source bytes changed. Preserve
existing conflict guards and unknown-effect reconciliation.

Record stage durations, changed inputs, decisions and actual results together.
If the remaining latency is a bounded network failure, report that observation;
do not restart unchanged qualification while waiting. Stop after acceptance
passes. Another full suite, repeated report or new investigation requires a new
relevant change, failure or explicitly bounded reproducibility question.

The regression fixture demonstrates a six-check update: three current-target
checks remain fresh, an affected regression runs, and two unchanged isolated
checks reuse their evidence. These are check counts, not a measured speedup or
proof of production behavior. Reverting the patch restores the former planner
and guidance; installed histories and published identifiers remain untouched.
