# Module boundaries and project API workflow

AgentOS keeps execution evidence, project knowledge and domain implementation in
separate modules. Read only the module contract needed for the current change.
`agentos modules` reports the installed manifest and its selected file pins; it
does not start a provider or grant execution rights. Its pin set is not a claim
that every file in the installation was independently verified.

## Owners and interfaces

| Component | Owns | Entry point and contract | Boundary |
| --- | --- | --- | --- |
| Foundation | Local lifecycle, source inventories, explicit checks and receipts | `agentos project`; `src/agent_os/project.py`, `safeio.py`; [process](PROCESS.md), [interfaces](CONTRACTS.md) | Receipts describe their exact source and scope. The CLI does not intercept arbitrary tools. |
| Local accounting | Opt-in `source-only` / `offline-test` journal | `agentos project local record/status/sync`; `src/agent_os/project_lite.py` | Project `.agentos/lite` state; no legacy READY or new authority. Existing active writers and interrupted transactions must first be reconciled. |
| Atlas | Derived work/document views, API catalogs, retained source references | `agentos atlas`; canonical `modules/atlas/skills/atlas`; [Atlas source policy](ATLAS_SOURCE_POLICY.md) | One owning project source and writer. A projection does not create another plan or accept runtime behavior. |
| Function Extractor | The bundled FE 0.4.6 CLI and replay tools | `agentos fe`; packaged `skills/function-extractor` and `fe_tools` | Runs selected packaged tools in isolated Python (`-I`); target-project tools are not assumed installed. |
| Coordination | Optional synchronous assignment, evidence and recovery ledger | `src/agent_os/work_coordination.py`; [coordination](WORK_COORDINATION.md) | A ledger record does not launch a worker, install a scheduler or make an unknown external effect safe to retry. |
| Project | Domain modules, HTTP APIs, OpenAPI/Swagger source, data migrations and product tests | The project's repository and versioned contracts | AgentOS indexes selected declarations; the project owns implementation, compatibility and runtime acceptance. |
| User overlay | Private configuration, profiles, connections and knowledge references | [foundation/overlay contract](FOUNDATION_OVERLAY.md) | Stays outside public core and survives a core update. |
| Package tooling | Canonical copies, inventory parity, artifact provenance and installation plans | `tools/sync_resources.py`, `sync_atlas.py`, `verify_rebuild_contracts.py`; [installation](INSTALL_UPDATE.md) | A source commit, built wheel, installed package and loaded client are separate observed states. |

Module contracts use stable identifiers, explicit versions, bounded inputs and
declared errors. Add a domain rule to its owning project. Change a shared module
only when the rule belongs to its documented interface. A source import must
not infer state ownership from tags, permission from documentation, or runtime
success from a schema.

## Choose the smallest sufficient route

| Work | Route |
| --- | --- |
| Question, search, code/API inspection | Direct authorized read. No task journal or lifecycle receipt is required. |
| Local source change already covered by a project's workflow | Use that workflow; opt-in local accounting can record the result without global turn-lock bookkeeping. It cannot bypass an active legacy task. |
| Change requiring source-bound task acceptance | Existing `project enter/ready/check/assess/close` workflow, with relevant documents and named acceptance. |
| Product, host, database or external operation | Existing scope-specific authorization and executor contract. Local accounting, Atlas and module inventory do not grant it. |

Preserve the current task and relevant accepted evidence. Re-enter or rerun a
check when its inputs, scope or required freshness changed, or when a required
gate demands it. Do not create a second matrix merely to show the first one.
Keep missing facts and unresolved effects as `UNKNOWN` until a named readback
establishes them.

## Project API and contract workflow

1. **Locate the owner.** Select the project's canonical API specification and
   module contract. Record its exact revision or bytes, source document ID and
   responsible writer. Keep the full original source in the project.
2. **Select the declared format.** Atlas accepts OpenAPI **3.0.x and 3.1.x
   JSON**, an explicit record catalog, or an operation registry. Swagger
   **2.0**, YAML, OpenAPI 3.2 and recursive callback/webhook catalogs are outside
   this compiler's qualified scope. Convert unsupported input explicitly in
   the owning project with its own validation; do not relabel a version.
3. **Compile only the selected source.** The installed Atlas skill's
   `references/catalogs.md` defines `atlas.catalog-source/v1` and the bounded
   `scripts/catalog.py` invocation. `document_id` identifies a registered
   `UPSTREAM.documents` entry. Compilation reads data and returns
   `atlas.semantic-catalog/v1`; it performs no HTTP request or external `$ref`
   retrieval. Unresolved references remain explicit.
4. **Bind the derived view and selected work.** Add explicit `work_bindings`
   from existing work IDs to generated contract IDs when task packets need API
   context; the catalog guide gives the exact shape. Without these links a
   global catalog may be present while the selected work packet is empty.
   The owning writer pins the final catalog bytes by `path/bytes/sha256` in
   `UPSTREAM.semantic_catalog`, refreshes and checks the selected packet IDs.
   Declared dependencies pull in modules and source documents; unrelated
   documents need explicit links. Tags do not establish work or state ownership.
5. **Verify the changed contract in the project.** Check relevant request,
   response, authorization, compatibility and consumer behavior using the
   project's tests and authorized environment. A catalog declaration is
   `FACT` about source and `execution=NOT_RUN` about product execution. Read
   retained pinned OpenAPI files for schemas, successful response refs, server
   URLs and security-scheme definitions omitted from compact cards/packets.
6. **Return evidence once.** Report source revision, affected contracts,
   observed checks, remaining unknowns and next owner. Existing accepted work
   is not reopened merely because it was imported into Atlas.

For projects with non-HTTP interfaces, use their actual CLI, message or data
schemas. AgentOS exposes CLI, Python and stdio MCP interfaces; it does not
provide an HTTP server or invent an OpenAPI wrapper for those interfaces.

## Canonical source and package checks

Edit each maintained source once. Top-level `docs/*.md` have matching package
resources; Atlas skill files are maintained in `modules/atlas` and mirrored
into packaged skills. Refresh current byte/hash pins while retaining historical
`source_*` provenance. Check both inventories: a leftover packaged document is
an explicit error, never an automatic deletion.

Use the changed module's regressions, then integrated tests and package checks
appropriate to publication. A full source inventory still hashes every
selected file; [streaming hashing](INVENTORY_HASHING.md) bounds memory without
adding a metadata cache or relaxing evidence. Preserve overlays through the
installer's plan, expected-current, apply/readback and explicit rollback flow.
The FE audit/seccomp trace remains a bounded test instrument, not a production
security certification. Container qualification is separate.
