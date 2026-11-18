"""Materialize the existing public engineering method, without task or host effects.

PROCESS.md remains the sole normative source. Returning its actual selected text
proves which bytes were supplied, never that a client read or followed them.
"""

from __future__ import annotations

from pathlib import Path

from . import __version__
from .safeio import GateError, sha

PROCESS_PATH = Path(__file__).parent / "resources" / "docs" / "PROCESS.md"
START = "<!-- agentos:causal-debugging:start -->"
END = "<!-- agentos:causal-debugging:end -->"
MAX_DOCUMENT_BYTES = 128 * 1024
MAX_SECTION_BYTES = 16 * 1024


def load() -> dict:
    """Read one bounded packaged section; no overlay, network or execution."""
    try:
        if PROCESS_PATH.is_symlink() or not PROCESS_PATH.is_file():
            raise GateError("engineering_guidance_document_required")
        with PROCESS_PATH.open("rb") as stream:
            raw = stream.read(MAX_DOCUMENT_BYTES + 1)
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise GateError("engineering_guidance_document_bound")
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise GateError("engineering_guidance_document_unavailable") from exc
    if (text.count(START) != 1 or text.count(END) != 1
            or text.index(END) <= text.index(START)):
        raise GateError("engineering_guidance_section_invalid")
    content = text.split(START, 1)[1].split(END, 1)[0].strip()
    encoded = content.encode("utf-8")
    if not encoded or len(encoded) > MAX_SECTION_BYTES:
        raise GateError("engineering_guidance_section_bound")
    return {
        "schema": "agentos.engineering-guidance/v1",
        "status": "MATERIALIZED",
        "version": __version__,
        "source": "docs/PROCESS.md#causal-debugging",
        "document_sha256": sha(raw),
        "content_sha256": sha(encoded),
        "content_bytes": len(encoded),
        "content": content,
        "authority_granted": False,
        "native_hooks": "DISABLED",
        "behavior_compliance": "NOT_PROVEN",
        "writes": [],
    }
