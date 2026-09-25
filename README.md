# Crystal AgentOS Community Edition

**A local, documentation-first foundation for agents and the people who direct them.**

AgentOS gives a project a repeatable path from its current state to a verified change: project dossier → roadmap → documented stage → implementation → checks → updated documentation. A short intake selects only the relevant document layers. The CLI keeps the task, source, documents and check evidence bound to the same stage; an integrated native hook can enforce entry and closeout only after the client actually loads and trusts it.

This is the canonical public repository: [crystalstrategysup-prog/agent-os](https://github.com/crystalstrategysup-prog/agent-os). The current beta source is `0.5.0-beta.4` (Python distribution version `0.5.0b4`). It is separate from any maintainer's private runtime, infrastructure and personal data.

Visit the [public project website](https://crystalstrategy.ru/agent-os/), read the [changelog](CHANGELOG.md), or open an [issue](https://github.com/crystalstrategysup-prog/agent-os/issues) with a bug or technical review. The release tag is the installation authority while website deployment is pending.

## Two physical layers

| Foundation, maintained here | User overlay, owned by the user |
| --- | --- |
| Python code, universal rules, schemas, templates, skills and docs | Configuration, knowledge references, optional 0 / 1 / N profiles, local state, secrets and extensions |
| Installed in a virtual environment or an immutable release directory | One separate folder, default `~/.agentos-user` |
| Updated or rolled back by selecting a verified release | Preserved on core update; imported and migrated only through explicit guarded commands |

See [Foundation ↔ Overlay](docs/FOUNDATION_OVERLAY.md) for versioning, conflicts and recovery. Project documents remain in their projects; the overlay indexes them without copying every project into the core.

Profiles are optional files under the user overlay. `agentos profiles inventory` reports their hashes and overlaps; `profiles select` activates none, one, or all in an explicit order. Conflicting values need an owner choice. `profiles interview` prefills observed device facts and asks about missing user fields. Editing or removing a profile leaves the installed foundation unchanged.

## Install from the public source

Python 3.11+ is required. On macOS or Linux, after verifying the intended public tag and source:

```sh
git clone --branch v0.5.0-beta.4 https://github.com/crystalstrategysup-prog/agent-os.git
cd agent-os
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
agentos init
agentos doctor
agentos --version
```

The package is **not published on PyPI**: `pip install crystal-agent-os` is not an installation method. The managed offline wheel installer, explicit overlay import, update and rollback are documented in [Install and update](docs/INSTALL_UPDATE.md). Windows has no verified managed installer; do not infer full Windows support from a Python import or source inspection.

## Start a project task

```sh
agentos project questions --root /absolute/path/to/project
agentos project init --root /absolute/path/to/new-project --name Example \
  --type platform --feature public --context context.json
agentos project enter --root /absolute/path/to/project \
  --session ACTUAL_SESSION --turn ACTUAL_TURN --answers answers.json
```

`questions` reuses verified project facts and shows only missing answers. The required documents depend on project type and changed surfaces. A new project starts with a dossier and roadmap; every product stage has its own contract and acceptance checks before code changes. `ready` rejects draft or stale documents. `check`, `assess` and `close` require current source-bound evidence plus named semantic review. Read-only investigation uses `project observe` without writing project metadata. The [process](docs/PROCESS.md), [documentation catalog](docs/DOCUMENTATION_CATALOG.md) and [synthetic example](tools/demo_lifecycle.py) show the full flow.

## Interfaces and boundaries

- The stdio MCP server exposes six narrow planning/status tools. `tools/list` includes versioned input and output schemas; it does not expose arbitrary shell, SSH, file contents or credentials. See [MCP contract](schemas/mcp-tools-v1.json).
- The [CLI contract](schemas/cli-contract-v1.json), [data schemas](src/agent_os/resources/schemas/) and [contracts guide](docs/CONTRACTS.md) describe the machine-readable surfaces. No HTTP server is provided, so OpenAPI is not applicable to this release.
- Codex AGENTS, namespaced skills and hook definitions can be integrated without overwriting other owners' content. **Installed is not active:** native trust and a real new-session negative/positive probe are required before claiming enforcement.
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

Start with the [project dossier](docs/agentos/DOSSIER.md), [roadmap](docs/agentos/ROADMAP.md), [current stage](docs/agentos/STAGE-F08.md), [architecture](docs/ARCHITECTURE.md) and [developer onboarding](docs/ONBOARDING.md). The [changelog](CHANGELOG.md) and [release policy](docs/RELEASE.md) state the beta status and limits. GitHub Actions are not used.

Crystal AgentOS is Apache-2.0 software. Contributions and skeptical technical reviews are welcome; see [Contributing](CONTRIBUTING.md), [Security](SECURITY.md), [Governance](GOVERNANCE.md) and the [AI Stewardship Charter](STEWARDSHIP.md). [Русская документация](docs/README.ru.md).
