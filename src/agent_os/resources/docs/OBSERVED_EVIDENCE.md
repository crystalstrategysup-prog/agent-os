# Bounded command evidence

For selected source reads, `agent_os.source_sections.read_sections` accepts an
explicit absolute root and up to16 relative file/range records. Its standalone
CLI takes `--root ROOT --request RANGES.json`, where the JSON list contains
`{"path":"module.py","start":10,"end":30}` records (1-based, inclusive).
It returns exact UTF-8 text, line bounds and full-file hashes. Default rendered
JSON budget is6000 bytes, configurable up to16000. Oversized output is refused
before any source body is printed; reduce the selected ranges instead of
clipping output. Files are bounded to2MiB, requests to16KiB; symlinks, path escape,
nonregular files and invalid ranges are refused. Use a verified resolved root
when an alias is a symlink. This POSIX helper reads no project state, imports no
application and needs no intake. Complete means only the selected ranges, not
the entire source or dependency coverage; caller authority remains separate.

`agent_os.observed_command.run_observed` observes a caller-authorized typed argv
on POSIX. It introduces no shell, permission, sandbox, scheduler or live write
authority. A caller can still explicitly invoke an interpreter or shell and is
responsible for its effects. Keep credentials, customer data and private routes
out of selected arguments, input, output and claim text. Use a private,
caller-owned single-writer output directory; do not share it with untrusted
writers. Filesystem failure can prevent ledger persistence and must be reported
as missing evidence, never success.

Standalone `-h` or `--help` displays usage without launching a command or writing
evidence. Execution requires a literal `--` between options and command arguments:

```sh
python -m agent_os.observed_command --purpose audit --claim 'selected check' \
  --cwd /selected/project --output-root /selected/evidence -- python3 check.py
```

Unquoted extra words before `--` are rejected before execution. Stdin defaults
to empty; supply a bounded regular file with `--stdin-file` or bytes through the
typed API. The CLI does not implicitly consume a potentially open stdin stream.
Python `-` requires explicit nonempty input. Supplied stdin is retained and
hashed; this proves offered bytes, not how much the program consumed.

The observer pins existing `.py` argument files and explicitly supplied
`--script-input` files. A script input is at most 1 MB; stdin at most 256 KiB.
Specify non-Python scripts explicitly. Imports, interpreter, executable,
environment, file dependencies, remote state and subprocess inputs are outside
these pins. A before/after hash cannot detect transient changes restored before
the second read. Select and review relevant dependencies independently.

Each accepted operation has a start and exactly one terminal record, including
failed launches (wrapper exit 127), timeout (124), output overflow (65), changed
script input (66) and observer/artifact failure (70). `target_started` means
Popen returned successfully, not a guarantee about transient OS child creation.
Errors expose categories rather than raw exception messages. Invalid requests
are refused before a start. A start without a terminal is incomplete evidence
after process interruption or storage failure; reconcile before replay.

Execution is bounded to 90 seconds and combined stdout/stderr to 24,000 bytes
(both limits may be lowered). Output is streamed into bounded buffers. Overflow
or timeout kills the POSIX process group and refuses output artifacts; retained
capture counts/hashes describe only the captured prefix, not all program output.
Descendants escaping that process group are outside this cleanup guarantee.
Qualified output artifacts retain exact bytes, never a silently clipped body.
No terminal evidence is printed as executable command text.

Choose bounded relevant file sections or a selected query before execution;
requesting an oversized body and then clipping it cannot establish completeness.
Reading an ordinary source dependency for the same authorized goal needs no new
permission gate. Protected effects retain their existing authority requirements.
After a refused observation, stop dependent business work and reconcile its
effects; finish mandatory cleanup of already owned resources without extending
that cleanup to unrelated resources.

The timeout applies to one observed command, not the aggregate task or executor
lifetime. When an authorized lifecycle spans several commands, compose bounded
steps under one owner and preserve required finally cleanup and terminal
accounting. Do not turn a per-command bound into a lifecycle blocker or weaken
it to fit the whole lifecycle. Escaped or unobservable effects still require
reconciliation before replay.

Before discarding raw diagnostics under the applicable data policy, retain a
safe failure category/code and actual exit status. Hash-only evidence can bind
a retained cause probe to a failure, but is not itself a diagnosis. A successful
expected-negative diagnostic probe does not make the original operation PASS.

The fingerprint covers argv, cwd, offered stdin hash and selected script pins.
Different stdin gives different identity. Matching fingerprints are duplicate
candidates, not proof that a repeat was redundant: mutable state may differ.

`agent_os.claim_evidence.primary_issues` accepts a canonical terminal record and
its output directory. It refuses context-only, nonterminal, failed, incomplete,
unbound or changed evidence and verifies retained artifact hashes. No defaults
turn absent exit codes into success. The caller must review required dependency
coverage, provenance and semantic relevance; a forged record can pass structural
checks. Structural admission is not semantic acceptance.

`aggregate_required` returns INCOMPLETE if any declared required criterion is
FAIL, INCOMPLETE, OPEN or PENDING_ACCEPTANCE, even alongside UNKNOWN. Only a
nonempty all-PASS set returns PASS; empty or unrecognized statuses stay UNKNOWN.
Do not label a criterion PASS merely because a command succeeded: it needs
admitted evidence and a semantic review against the original requirement.
All-PASS establishes the declared scope only, not universal correctness.
