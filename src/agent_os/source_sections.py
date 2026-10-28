"""Read exact source ranges without silently clipping the rendered output.

This is ordinary caller-authorized file reading, not discovery or a sandbox.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from .safeio import GateError, within


class SourceReadError(ValueError):
    pass


def read_sections(root: Path, requests: list[dict], *, max_output_bytes: int = 6000) -> dict:
    """Return complete selected ranges or refuse the entire selection.

    Paths are relative to an explicit regular directory. No recursion, imports,
    persistent cache or authority inference. Hashes bind the bytes read, not a
    later filesystem state or protection against a malicious concurrent writer.
    """
    if type(max_output_bytes) is not int or not 256 <= max_output_bytes <= 16000:
        raise SourceReadError("invalid_output_budget")
    if not isinstance(requests, list) or not 1 <= len(requests) <= 16:
        raise SourceReadError("invalid_selection")
    root = Path(root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise SourceReadError("explicit_regular_root_required")
    root = root.resolve()
    cache = {}
    sections = []
    for request in requests:
        if not isinstance(request, dict) or set(request) != {"path", "start", "end"}:
            raise SourceReadError("invalid_range")
        rel, start, end = (request[k] for k in ("path", "start", "end"))
        if (not isinstance(rel, str) or not 0 < len(rel) <= 1024 or
                type(start) is not int or type(end) is not int or not 1 <= start <= end):
            raise SourceReadError("invalid_range")
        try:
            path = within(root, rel)
        except GateError:
            raise SourceReadError("unsafe_source_path") from None
        if rel not in cache:
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
                with os.fdopen(fd, "rb") as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode):
                        raise SourceReadError("regular_source_required")
                    data = stream.read(2097153)
            except OSError:
                raise SourceReadError("source_unavailable") from None
            if len(data) > 2097152:
                raise SourceReadError("source_input_limit")
            try:
                lines = data.decode("utf-8").splitlines(keepends=True)
            except UnicodeError:
                raise SourceReadError("source_utf8_required") from None
            cache[rel] = (lines, hashlib.sha256(data).hexdigest())
        lines, digest = cache[rel]
        if end > len(lines):
            raise SourceReadError("range_outside_source")
        sections.append({"path": rel, "start": start, "end": end,
                         "file_lines": len(lines), "source_sha256": digest,
                         "text": "".join(lines[start - 1:end])})
    result = {"schema": "agentos.source-sections/v1", "selection_complete": True,
              "coverage": "selected_ranges_only", "sections": sections}
    # Budget the actual JSON+newline, including escaping and metadata. Never
    # print individual sections before the whole result has passed this check.
    if len((json.dumps(result, ensure_ascii=False) + "\n").encode()) > max_output_bytes:
        raise SourceReadError("source_output_limit")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--request", default="-", help="JSON range list file, or - for stdin")
    parser.add_argument("--max-output-bytes", type=int, default=6000)
    args = parser.parse_args(argv)
    try:
        if args.request == "-":
            raw = sys.stdin.buffer.read(16385)
        else:
            path = Path(args.request)
            if path.is_symlink() or not path.is_file():
                raise SourceReadError("regular_request_required")
            with path.open("rb") as stream:
                raw = stream.read(16385)
        if len(raw) > 16384:
            raise SourceReadError("request_input_limit")
        requests = json.loads(raw)
        result = read_sections(args.root, requests, max_output_bytes=args.max_output_bytes)
    except (OSError, ValueError) as error:
        reason = str(error) if isinstance(error, SourceReadError) else "invalid_request"
        print(json.dumps({"status": "REFUSED", "reason": reason}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
