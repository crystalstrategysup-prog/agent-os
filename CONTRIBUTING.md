# Contributing

Thank you for helping make personal agent infrastructure safer and easier to use.
Good first contributions include documentation, translations, operating-system
compatibility, tests and narrow connector adapters.

## Development

1. Fork the repository and create a focused branch.
2. Read the project [dossier](docs/agentos/DOSSIER.md), [roadmap](docs/agentos/ROADMAP.md), current [stage](docs/agentos/STAGE-F05.md) and [process](docs/PROCESS.md).
3. Install with `python -m pip install -e '.[dev]'`; run `python -m pytest -q`, `ruff check .`, `python tools/demo_lifecycle.py` and `python tools/verify_public.py`.
4. Define the stage and relevant contracts before changing product code. In the PR, explain the actual diff, checks, compatibility, limits and rollback.
5. Never include credentials, private overlays, hostnames, personal IDs or production logs. Do not add GitHub Actions.

Changes that expose arbitrary shell access, silently transmit credentials or
weaken owner approval will not be accepted. A named reviewer should distinguish
their independent review from the implementer's own checks.

An AI steward may triage and review contributions in its own voice under the
[AI Stewardship Charter](STEWARDSHIP.md). It must explain decisions with evidence,
protect contributor privacy and escalate legally ambiguous or irreversible actions.

By contributing, you agree that your contribution is licensed under Apache-2.0.
