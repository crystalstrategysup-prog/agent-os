# Contributing

Thank you for helping make personal agent infrastructure safer and easier to use.

Good first contributions include documentation, translations, operating-system
compatibility, tests and narrow connector adapters.

## Development

1. Fork the repository and create a focused branch.
2. Install with `pip install -e '.[dev]'`.
3. Run `pytest` and `ruff check .`.
4. Explain the user-visible behavior and security boundary in your change.
5. Never include real credentials, private hostnames, personal IDs or production logs.

Changes that expose arbitrary shell access, silently transmit credentials or
weaken owner approval will not be accepted.

By contributing, you agree that your contribution is licensed under Apache-2.0.
