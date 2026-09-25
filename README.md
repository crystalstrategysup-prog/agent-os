# Crystal AgentOS Community Edition

**A local, documentation-first foundation for agents and the people who direct them.**

AgentOS gives a project a repeatable path from its current state to a verified change: project dossier → roadmap → documented stage → implementation → checks → updated documentation. A short intake selects only the relevant document layers. The CLI keeps the task, source, documents and check evidence bound to the same stage; ordinary read-only questions bypass intake entirely. Native hooks are excluded; explicit CLI checks do not intercept arbitrary tools.

This is the canonical public repository: [crystalstrategysup-prog/agent-os](https://github.com/crystalstrategysup-prog/agent-os). This local candidate source is `0.5.0-beta.6` (Python distribution version `0.5.0b6`). It is separate from any maintainer's private runtime, infrastructure and personal data.

Visit the [public project website](https://crystalstrategy.ru/agent-os/), read the [changelog](CHANGELOG.md), or open an [issue](https://github.com/crystalstrategysup-prog/agent-os/issues) with a bug or technical review. This candidate does not assert that a new tag, release asset or website deployment exists.

## Two physical layers

| Foundation, maintained here | User overlay, owned by the user |
| --- | --- |
| Python code, universal rules, schemas, templates, skills and docs | Configuration, knowledge references, optional 0 / 1 / N profiles, local state, secrets and extensions |
| Installed in a virtual environment or an immutable release directory | One separate folder, default `~/.agentos-user` |
| Updated or rolled back by selecting a verified release | Preserved on core update; imported and migrated only through explicit guarded commands |

See [Foundation ↔ Overlay](docs/FOUNDATION_OVERLAY.md) for versioning, conflicts and recovery. Project documents remain in their projects; the overlay indexes them without copying every project into the core.

Profiles are optional files under the user overlay. `agentos profiles inventory` reports their hashes and overlaps; `profiles select` activates none, one, or all in an explicit order. Conflicting values need an owner choice. `profiles interview` prefills observed device facts and asks about missing user fields. Editing or removing a profile leaves the installed foundation unchanged.

## Candidate verification, not installation authority

Python 3.11+ is required. Review the exact source and diff, run the local tests and compare
package resources before integration. `0.5.0-beta.6` is a local candidate, not an assertion
that its tag or distribution is published. See [Install and update](docs/INSTALL_UPDATE.md)
for the separately authorized offline flow, overlay preservation and no-hook rollback.
No global hooks, model/auth or client security changes are part of this candidate.

## Ordinary read-only requests

Answer questions, search, inspect code and discover authorized API capabilities directly.
No registration, answers file, profile interview, observe receipt or closeout is needed.
Optional `agentos workflow route --kind audit` explains the route without reading overlay
or changing files; calling it is not a prerequisite for answering a question.

## Instruction routing

Keep inherited project `AGENTS.md` short: define its scope, universal limits and
links to the project documents or skills that explain each topic. Read detailed
material only when the task requires it, and verify dated status against current
source or runtime evidence. A size target such as 4 KiB is editorial guidance,
not an entry or read-only gate. The public foundation stays host-neutral; owner
and host details belong in the separate user overlay. See
[architecture](docs/ARCHITECTURE.md) and [process](docs/PROCESS.md).

## Start a project task

```sh
agentos project questions --root /absolute/path/to/project
agentos project init --root /absolute/path/to/new-project --name Example \
  --type platform --feature public --context context.json
agentos project enter --root /absolute/path/to/project \
  --session ACTUAL_SESSION --turn ACTUAL_TURN --answers answers.json
```

`questions` shows verified project context and only missing supplied answers. Same-scope `--resume-task` reuses previous answers except current authority; `enter --reuse-answers` makes that reuse explicit. JSON inputs accept `-` for stdin. The required documents depend on project type and changed surfaces. A new project starts with a dossier and roadmap; every product stage has its own contract and acceptance checks before code changes. `ready` rejects draft or stale documents. `check`, `assess` and `close` require current source-bound evidence plus named semantic review. Optional audit recording uses `project observe`; ordinary investigation needs no receipt. `project verify-closeout` checks whether a CLOSED result still has current evidence. The [process](docs/PROCESS.md), [documentation catalog](docs/DOCUMENTATION_CATALOG.md) and [synthetic example](tools/demo_lifecycle.py) show the full flow.

## Interfaces and boundaries

- The stdio MCP server exposes six narrow planning/status tools. `tools/list` includes versioned input and output schemas; it does not expose arbitrary shell, SSH, file contents or credentials. See [MCP contract](schemas/mcp-tools-v1.json).
- The [CLI contract](schemas/cli-contract-v1.json), [data schemas](src/agent_os/resources/schemas/) and [contracts guide](docs/CONTRACTS.md) describe the machine-readable surfaces. No HTTP server is provided, so OpenAPI is not applicable to this release.
- Codex AGENTS and namespaced skills can be integrated while preserving other owners' content. **No native hooks are created or restored.** Read back effective instructions in a fresh client session; do not claim a universal tool sandbox.
- The optional Telegram Session Hub remains owner-allowlisted and disabled by default. This beta changes its dispatch boundary; read [compatibility](docs/COMPATIBILITY.md) before replacing any existing connector.
- Existing model routing, current-evidence result assessment, Full Inventory and update advisory remain available through the CLI. Their contracts and limits are in [architecture](docs/ARCHITECTURE.md), [result evidence](docs/RESULT_EVIDENCE.md), [Full Inventory](docs/FULL_INVENTORY.md) and [update checks](docs/UPDATE_CHECK.md).
- The Codex in-app Browser and Chrome remain separate documented surfaces; see [browser surfaces](docs/BROWSER_SURFACES.md). The optional [Telegram onboarding plan](docs/TELEGRAM_SESSION_HUB.md) does not require a website or transmit credentials to this repository.

## Develop and verify

```sh
python -m pip install -e '.[dev]'
python -m pytest -q
python tools/demo_lifecycle.py
python tools/verify_public.py
```

Start with the [project dossier](docs/agentos/DOSSIER.md), [roadmap](docs/agentos/ROADMAP.md), [current stage](docs/agentos/STAGE-F10.md), [architecture](docs/ARCHITECTURE.md) and [developer onboarding](docs/ONBOARDING.md). The [changelog](CHANGELOG.md) and [release policy](docs/RELEASE.md) state the beta status and limits. GitHub Actions are not used.

Crystal AgentOS is Apache-2.0 software. Contributions and skeptical technical reviews are welcome; see [Contributing](CONTRIBUTING.md), [Security](SECURITY.md), [Governance](GOVERNANCE.md) and the [AI Stewardship Charter](STEWARDSHIP.md). [Русская документация](docs/README.ru.md).
