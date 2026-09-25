# F02/F03 — integrate the public foundation and project lifecycle

Status: LOCAL_IMPLEMENTATION_VERIFIED on 2026-09-25. This is one bounded integration stage because the supplied candidate's overlay, task entry, document selection, hooks and package resources share the same CLI and storage contracts. F02 and F03 receive separate acceptance results below. No publication or live private runtime replacement is part of this stage.

## Inputs and exact write set

Source baseline is public `origin/main` at `552ac9a3c812959e9d62883fd0a9052d6e44400f`. Review candidates are the 143 `public-core/` files classified in F01; they derive from public 0.4.0 plus new code. Integrate only relevant `src/`, `schemas/`, `tools/`, `tests/`, `examples/` and public docs into the clean worktree. Preserve and reconcile current public `AGENTS.md`, `docs/BROWSER_SURFACES.md`, this dossier/roadmap/stage set and `docs/FOUNDATION_OVERLAY.md`. Exclude `.agentos/` runtime receipts, candidate self-verification result/stage receipts and all mixed-archive private top levels. No generated venv, cache, wheel or private material is committed.

## Foundation and overlay contract (F02)

The package is public read-only core. Default user home is a disjoint `~/.agentos-user` with `overlay.json` v1, config v5, state, secrets, knowledge, preferences, projects, extensions and backups. Explicit import first plans, then creates only missing hash-verified files; identical existing files remain unchanged, conflict blocks. Config migration v1–v4 retains unknown keys, writes a byte-exact backup before atomic replacement and verifies read-back. Managed release install/rollback is POSIX-only, uses a checked local wheel in an immutable release directory, switches `current` only after probe and never writes user home. The prior private AgentOS pointer is not a target.

Failure paths to test: overlapping roots, symlinked destinations, invalid manifest, changed source, conflicting existing file, interrupted partial import, unsupported future schema, stale expected current, failed wheel hash, incomplete release and rollback incompatibility. Windows package bootstrap is a separate probe; the managed installer must report unsupported there rather than claim success.

## Documentation lifecycle contract (F03)

Every new/resumed product task on the supported integrated path receives an entry record keyed to actual session and turn. The questionnaire reuses current project facts and asks only unresolved fields. Project types/features select dossier, roadmap, stage, quality plan and relevant contracts; no requirement to produce all catalog layers. Draft, changed or unregistered required docs block READY. Product write before READY is denied by an active native hook, when that hook is genuinely supported and trusted. Approved checks bind to source/task/revision; close requires current checks, semantic review of each criterion, current docs, scope and limitations. Checkpoint stays incomplete. R0 observation records a bounded user-home receipt without modifying an unrelated project.

The CLI remains an explicit path when native hooks are unavailable. Neither CLI output nor an untrusted/inactive hook file proves universal enforcement in arbitrary clients. Actual client activation is a later target check and must be labelled separately.

## Contracts and affected documentation

Stage F02/F03 supplies `overlay.json`/config and project/task/closeout JSON schemas, docs for data, process, architecture, security, installation and quality, plus package resources/templates and supported skills. `docs/FOUNDATION_OVERLAY.md` remains the authoritative boundary. HTTP OpenAPI and AsyncAPI are N/A because this stage adds no HTTP API or event transport. MCP input/output schemas, exact version mapping and a CLI command contract are finished in F04 before release.

## Acceptance and checks

- F02: clean temporary Mac install; overlay catalog; create-only import and idempotent retry; conflicting import blocks; config migration backup and unknown-key preservation; offline core update/rollback leaves a user-tree sentinel byte-identical. Source/wheel and executable versions are recorded.
- F03: project intake selects only relevant docs; missing/draft/stale docs block READY; current registered docs permit READY; old or tampered check evidence blocks close; current checks and named semantic review permit close; new turn re-enters; read-only observe does not create project metadata. Native hook tests are fixtures until actual client proof.
- Regression: full public test suite, schema validation, public-source heuristic and explicit diff/privacy review. The candidate's 146 tests are a baseline to reproduce after integration, not an acceptance substitute.

## Stage result record

- Integrated 137 manifest-listed public candidate files into the isolated branch, preserving current public `AGENTS.md` and `docs/BROWSER_SURFACES.md`. No `.agentos` receipt or mixed-archive private top-level file was copied. Added `.agentos/` to `.gitignore`.
- Reconciled `AGENTS.md` with the documentation-first cycle, preserved its public repository and security rules, and synced all top-level maintained docs into installed package resources. The candidate's duplicated docs initially omitted the newer browser contract; the integrated test detected this and it was corrected.
- On Darwin arm64 / Python 3.14.6, the integrated suite returned `146 passed in 2.64s`; the synthetic lifecycle returned early `BLOCKED`, check `PASS`, closeout `CLOSED`. These are fixture checks, not actual native Codex hook activation.
- Built `crystal_agent_os-0.5.0b1-py3-none-any.whl`, SHA-256 `262849a7f6f681e617df63fbf625c63c292f69e92ba231b4bea9e0de8dbe5566`. The offline Mac fixture checked initial install, update, rollback, reactivation, user-tree preservation and synthetic overlay import/init, all PASS. Its prior release was synthetic and its paths were temporary. No live Mac service or private runtime changed.
- The existing test suite includes negative cases for draft/stale docs, stale/tampered evidence, scope changes, symlink/path safety, import conflict, config backup, new turn and Stop behavior. The public-tree heuristic returned PASS but currently ignores `.agentos`; F04 must fail release staging if such runtime files are tracked.

F02 outcome: LOCAL_PASS with actual target installation and Windows/Linux portability still unverified. F03 outcome: CLI/fixture PASS; native hook enforcement remains NOT_VERIFIED. F04 must align distribution/version, machine-readable contracts, developer onboarding and release guidance before any public publication.
