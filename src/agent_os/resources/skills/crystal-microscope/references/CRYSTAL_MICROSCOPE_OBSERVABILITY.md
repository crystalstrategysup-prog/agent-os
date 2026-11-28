# Crystal Microscope: observing code, runtime and resources

This is a selection guide for an explicit question, not a command to enable
every collector. Read the [method](CRYSTAL_MICROSCOPE.md) and the existing host's
rules. The skill itself performs no live collection, privilege change or tuning.
Tool behavior depends on the exact platform/version; verify current official
documentation before use. The references below were reviewed on 2026-11-28.

## Choose the least intrusive evidence that answers the question

| Question | Useful evidence | Principal limitation |
| --- | --- | --- |
| Where does a value change? | Identified input/output, source and existing structured logs | Logs can omit branches or reflect different builds |
| Which asynchronous work belongs together? | Request/span identity, parent and links, task/event transitions | Correlation is not proof of a causal mechanism |
| Why is elapsed time long? | End-to-end timestamps plus CPU/wait/queue and I/O evidence | Unsynchronized clocks and overlap can invalidate sums |
| Which code consumes CPU? | Supported statistical CPU profile with symbols | Sampling estimates frequency; it is not every call |
| What allocates or retains memory? | Allocation/heap profiles, ownership and lifetime evidence | Sampled and language-runtime allocation may omit native memory |
| Where are bytes copied? | Source/call path plus relevant observations or a bounded experiment | Zero allocation does not establish zero copying |
| Which system boundary blocks? | Supported syscall/scheduler/lock traces in the allowed scope | Tracing may change behavior, expose data or drop events |
| What runs in a binary? | Exact build IDs, symbols and disassembly | Static instructions do not show actual execution frequency |
| What hardware work explains a cost? | Supported process-scoped counters/trace with attribution | Event availability, privilege, multiplexing and export limits |

OpenTelemetry describes spans and links for causal relationships that do not fit
a simple parent tree, including asynchronous relationships. Preserve such links
and clock limitations; do not present distributed spans as a fully synchronized
instruction timeline. See the official
[traces documentation](https://opentelemetry.io/docs/concepts/signals/traces/).

## Observation is an effect category

Distinguish reading existing artifacts from starting a collector and from
fault injection or a product change. Attaching, enabling runtime profiles,
inserting probes, replaying workload, tracing a shared system or writing large
recordings can affect timing, resource use and other users. Authorization for
analysis alone does not grant these effects. Preserve explicit restrictions on
OS, kernel, processor, memory, drivers, protection, network and power settings.

Use current rights and supported tools. An access denial remains a limit;
do not disable protection, alter entitlements, change perf policy or attach as
another user to complete a diagram. If authorization already covers a bounded
collector, do not ask again unnecessarily. Explain a genuinely missing authority
only when it is needed for the selected next step.

Never overwrite or clear another operator's tracer, shared ring buffer or
in-progress recording. Linux ftrace documents that switching tracers can clear
buffers, `trace_pipe` consumes data, and disabling recording does not necessarily
remove all instrumentation overhead. Dynamic function tracing can patch running
code. Read the relevant controls before treating an operation as passive:
[ftrace](https://docs.kernel.org/trace/ftrace.html).

Linux performance monitoring can expose process addresses, registers or captured
memory; privilege and data-access restrictions are part of the tool's design.
Use [perf security](https://docs.kernel.org/admin-guide/perf-security.html) when
assessing scope. More granular hardware events do not justify collecting secrets
or unrelated workloads. Redact only a reviewed publication copy; preserve required
private recovery evidence in its authorized location.

## Resource and collection passport

Before a potentially large run, use the existing workspace-hygiene record for
owner, exact run root, actual volume, expected concurrent peak, available bytes,
inodes/quota, retained outputs and stop conditions. Include collector buffers,
exports, unpacked copies and final packaging in the capacity estimate. A new
directory on the same volume adds no capacity. Bound collection to the question
and available resource envelope, not an arbitrary universal time budget.

Record executable and symbol identities, process start and descendants included,
collection interval, filters, sampling frequency, successful observations,
unattributed/dropped records and export status. Keep attempted, started, stopped,
exported/readable and usable distinct. A recording file whose exporter cannot
read it is not an accepted profile. A control or idle trace is not evidence of
the target scenario. Record measured overhead or state it is unmeasured.

Stop and reconcile uncertain collectors before starting another. Preserve the
original operation identity after an unknown outcome. Clean only owned qualified
temporary data after its readers/writers are finished and required evidence is
retained. Do not delete another run, a recovery copy or a live trace to make space.
Update the existing journal with final disposition; no extra document bundle is
required for each probe.

## CPU and scheduling interpretation

Separate useful-work elapsed time from CPU execution, runnable delay, sleeping,
I/O and synchronization waits. Define the process/thread and descendants covered.
A waiting syscall duration may include network service, descheduling and wakeup;
its duration is not automatically CPU cost. Inclusive call times overlap nested
work; concurrent tasks overlap elapsed time. State the denominator of percentages.

Profiles require sufficient relevant samples for the intended conclusion, and
appropriate aggregation of repeated work. Low sample counts can locate a clue
without proving a precise share or tail latency. Hardware counters can be
multiplexed and scaled; preserve that qualification. A total process counter
does not identify a line without additional attribution. A machine listing can
support the explanation of a path but cannot substitute for execution evidence.

Apple's Processor Trace has specific hardware, OS and Instruments prerequisites;
symbolication and matching build information are needed for useful attribution.
Read [Analyzing CPU usage with Processor Trace](https://developer.apple.com/documentation/xcode/analyzing-cpu-usage-with-processor-trace)
for the actual target instead of assuming every Mac or running protected process
supports the same view. Unsupported or inaccessible detail stays UNKNOWN.

## Memory interpretation

Report quantities by their actual meaning: allocated bytes over the run, live
heap at a point, retained objects, virtual address space, resident mappings,
shared/private pages or physical footprint. These are different measurements.
An application's logical state limit is not a guarantee of its whole-process
RSS. A reduced allocation total can coexist with unchanged or larger peak memory.
Language-runtime profiles can omit foreign/native allocators and mappings.

Follow buffer allocation, ownership, reuse, aliases, copying and release as
separate edges. Before pooling or reusing data, establish that no consumer retains
the reference past the reuse boundary; include concurrent reads, cancellation
and foreign-function pointer lifetimes. A microbenchmark with reused memory may
report zero allocations while copying a full payload each iteration. Logical
bytes copied do not measure traffic across cache or RAM boundaries.

Physical cache/TLB/memory claims require relevant supported events in the actual
useful workload, with attribution and interpretation limits. Do not infer them
from an idle/control process, source code alone or an unreadable recording. Do
not change hardware or OS settings merely to turn UNKNOWN into a number.

## Evidence sufficient for the next decision

Use existing logs/source first, add one relevant collector when it can resolve a
material question, then compare the candidate at the same useful work and verify
the parent/user result. Preserve correctness and recovery throughout. End a
diagnostic pass when it supports a justified next action; it need not exhaust
every possible hardware event. Record a blocked deeper layer without hiding the
useful result already established at a higher layer.
