# AgentOS documentation

The public source declares `0.5.3`. Ordinary questions and read-only work need
no project intake; real project changes follow a documentation-first stage.
Native AgentOS hooks are excluded. Check publication and installation with
separate readback.

Start with [PROCESS](PROCESS.md), then read only the documents relevant to the
work: [ARCHITECTURE](ARCHITECTURE.md), [CONTRACTS](CONTRACTS.md),
[SECURITY_MODEL](SECURITY_MODEL.md), [INSTALL_UPDATE](INSTALL_UPDATE.md), or
[QUALITY](QUALITY.md). [FOUNDATION_OVERLAY](FOUNDATION_OVERLAY.md) explains
physical separation and [DOCUMENTATION_CATALOG](DOCUMENTATION_CATALOG.md)
explains document selection. The current source stage is
[STAGE-F15B](agentos/STAGE-F15B.md); earlier stages are historical. Stage records
are not shipped as runtime resources; the installed process contract is the
packaged `resources/docs/PROCESS.md`. See [COMPATIBILITY](COMPATIBILITY.md) for
platforms and unverified target behavior.

The [work-continuity scenario](WORK_CONTINUITY.md) gives a portable passport
template and a recovery proof route. The [connection scenarios](SETUP_SCENARIOS.md)
cover capability setup; filled user passports and connection settings stay
outside the public package.
