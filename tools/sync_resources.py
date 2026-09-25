#!/usr/bin/env python3
"""Synchronize public normative docs to wheel resources; explicit apply, otherwise check."""

import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
apply = "--apply" in sys.argv
changed = []
for source in sorted((root / "docs").glob("*.md")):
    dest = root / "src/agent_os/resources/docs" / source.name
    if not dest.exists() or dest.read_bytes() != source.read_bytes():
        changed.append(source.name)
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
print(
    json.dumps(
        {
            "status": "SYNCED" if apply else ("PASS" if not changed else "FAIL"),
            "changed": changed,
        }
    )
)
raise SystemExit(0 if apply or not changed else 1)
