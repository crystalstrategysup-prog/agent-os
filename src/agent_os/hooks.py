"""Retired native hook entrypoints, retained only for migration compatibility.

Do not register or enable them. They intentionally return no permission decision,
no completion claim and no context. Target-system controls remain independent.
Explicit project receipts live in turns.py; governance lives in the CLI workflow.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def handle(payload: Any, home: Path | None = None) -> dict:
    """No lifecycle, I/O or validation dependency, even for a stale payload."""
    return {}


def main() -> int:
    # Do not read stdin: a retired callback must not wait for input or inspect state.
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
