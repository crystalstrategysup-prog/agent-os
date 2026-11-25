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
COMMON_METHOD = "solution-integrity"
METHODS = (DEFAULT_METHOD, "causal-debugging", COMMON_METHOD)
START = "<!-- agentos:project-development:start -->"
END = "<!-- agentos:project-development:end -->"
MAX_DOCUMENT_BYTES = 128 * 1024
MAX_SECTION_BYTES = 16 * 1024
MAX_CONTENT_BYTES = 2 * MAX_SECTION_BYTES + 2


def _section(text: str, method: str) -> tuple[str, tuple[int, int]]:
    start = f"<!-- agentos:{method}:start -->"
    end = f"<!-- agentos:{method}:end -->"
    if (text.count(start) != 1 or text.count(end) != 1
            or text.index(end) <= text.index(start)):
        raise GateError("engineering_guidance_section_invalid")
    first, last = text.index(start), text.index(end)
    content = text[first + len(start):last].strip()
    if not content or len(content.encode("utf-8")) > MAX_SECTION_BYTES:
        raise GateError("engineering_guidance_section_bound")
    return content, (first, last + len(end))


def load(method: str = DEFAULT_METHOD, *, development: dict | None = None) -> dict:
    """Read shared laws and the selected bounded method without side effects."""
    if method not in METHODS:
        raise GateError("engineering_guidance_unknown_method")
    selected = default() if development is None else normalize(development)
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
    methods = (COMMON_METHOD,) if method == COMMON_METHOD else (COMMON_METHOD, method)
    fragments, sections = [], []
    previous_end = -1
    for selected_method in methods:
        fragment, (first, last) = _section(text, selected_method)
        if first < previous_end:
            raise GateError("engineering_guidance_section_invalid")
        previous_end = last
        encoded_fragment = fragment.encode("utf-8")
        fragments.append(fragment)
        sections.append({
            "source": f"docs/PROCESS.md#{selected_method}",
            "content_sha256": sha(encoded_fragment),
            "content_bytes": len(encoded_fragment),
        })
    content = "\n\n".join(fragments)
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_CONTENT_BYTES:
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
        "sections": sections,
        "authority_granted": False,
        "native_hooks": "DISABLED",
        "behavior_compliance": "NOT_PROVEN",
        "writes": [],
    }
