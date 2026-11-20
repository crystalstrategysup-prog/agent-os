"""Materialize the existing public engineering method, without task or host effects.

PROCESS.md remains the sole normative source. Returning its actual selected text
proves which bytes were supplied, never that a client read or followed them.
"""

from __future__ import annotations

from pathlib import Path

from . import __version__
from .development_level import default, normalize
from .safeio import GateError, sha

PROCESS_PATH = Path(__file__).parent / "resources" / "docs" / "PROCESS.md"
DEFAULT_METHOD = "project-development"
METHODS = (DEFAULT_METHOD, "causal-debugging")
START = "<!-- agentos:project-development:start -->"
END = "<!-- agentos:project-development:end -->"
MAX_DOCUMENT_BYTES = 128 * 1024
MAX_SECTION_BYTES = 16 * 1024


def load(method: str = DEFAULT_METHOD, *, development: dict | None = None) -> dict:
    """Read one bounded packaged section; no overlay, network or execution."""
    if method not in METHODS:
        raise GateError("engineering_guidance_unknown_method")
    selected = default() if development is None else normalize(development)
    start = f"<!-- agentos:{method}:start -->"
    end = f"<!-- agentos:{method}:end -->"
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
    if (text.count(start) != 1 or text.count(end) != 1
            or text.index(end) <= text.index(start)):
        raise GateError("engineering_guidance_section_invalid")
    content = text.split(start, 1)[1].split(end, 1)[0].strip()
    encoded = content.encode("utf-8")
    if not encoded or len(encoded) > MAX_SECTION_BYTES:
        raise GateError("engineering_guidance_section_bound")
    return {
        "schema": "agentos.engineering-guidance/v1",
        "status": "MATERIALIZED",
        "version": __version__,
        "source": f"docs/PROCESS.md#{method}",
        "development": selected,
        "document_sha256": sha(raw),
        "content_sha256": sha(encoded),
        "content_bytes": len(encoded),
        "content": content,
        "authority_granted": False,
        "native_hooks": "DISABLED",
        "behavior_compliance": "NOT_PROVEN",
        "writes": [],
    }
