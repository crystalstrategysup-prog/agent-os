import hashlib
import json
import os
from pathlib import Path

import pytest

from agent_os.source_sections import SourceReadError, main, read_sections

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX source reader")


def selection(path="source.py", start=1, end=2):
    return [{"path": path, "start": start, "end": end}]


def test_exact_ranges_and_hash_without_writes(tmp_path):
    raw = "first\nвторая\nlast".encode()
    (tmp_path / "source.py").write_bytes(raw)
    result = read_sections(tmp_path, selection())
    row = result["sections"][0]
    assert row["text"] == "first\nвторая\n"
    assert row["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert row["file_lines"] == 3
    assert result["coverage"] == "selected_ranges_only"
    assert list(tmp_path.iterdir()) == [tmp_path / "source.py"]


def test_cli_oversize_refuses_without_partial_source(tmp_path, capsys):
    marker = "SOURCE_MUST_NOT_LEAK"
    (tmp_path / "source.py").write_text((marker + "\n") * 300)
    request = tmp_path / "request.json"
    request.write_text(json.dumps(selection(end=300)))
    assert main(["--root", str(tmp_path), "--request", str(request)]) == 2
    output = capsys.readouterr().out
    assert marker not in output
    assert json.loads(output) == {"status": "REFUSED", "reason": "source_output_limit"}


def test_actual_serialized_budget_includes_escaping(tmp_path):
    (tmp_path / "source.py").write_text('"\\' * 1500)
    result = read_sections(tmp_path, selection(end=1), max_output_bytes=16000)
    size = len((json.dumps(result, ensure_ascii=False) + "\n").encode())
    assert read_sections(tmp_path, selection(end=1), max_output_bytes=size) == result
    with pytest.raises(SourceReadError, match="source_output_limit"):
        read_sections(tmp_path, selection(end=1), max_output_bytes=size - 1)


@pytest.mark.parametrize("path", ["../outside.py", "/etc/passwd", "missing.py"])
def test_unsafe_or_missing_source_refused(tmp_path, path):
    with pytest.raises(SourceReadError):
        read_sections(tmp_path, selection(path=path, end=1))


def test_symlinks_and_nonregular_source_refused(tmp_path):
    (tmp_path / "source.py").write_text("one\ntwo\n")
    (tmp_path / "alias.py").symlink_to(tmp_path / "source.py")
    with pytest.raises(SourceReadError):
        read_sections(tmp_path, selection(path="alias.py"))
    (tmp_path / "directory").mkdir()
    with pytest.raises(SourceReadError):
        read_sections(tmp_path, selection(path="directory"))
    alias = tmp_path / "root-alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(SourceReadError):
        read_sections(alias, selection())


@pytest.mark.parametrize("ranges", [[], [{"path": "source.py", "start": True, "end": 2}],
                                    selection(end=99), selection(start=0), selection(start=2, end=1)])
def test_invalid_range_refused(tmp_path, ranges):
    (tmp_path / "source.py").write_text("one\ntwo\n")
    with pytest.raises(SourceReadError):
        read_sections(tmp_path, ranges)


def test_oversized_and_non_utf8_source(tmp_path):
    path = tmp_path / "source.py"
    path.write_bytes(b"x" * 2097153)
    with pytest.raises(SourceReadError, match="source_input_limit"):
        read_sections(tmp_path, selection())
    path.write_bytes(b"\xff")
    with pytest.raises(SourceReadError, match="source_utf8_required"):
        read_sections(tmp_path, selection(end=1))


def test_cli_success_and_invalid_request(tmp_path, capsys):
    (tmp_path / "source.py").write_text("one\ntwo\n")
    request = tmp_path / "request.json"
    request.write_text(json.dumps(selection()))
    assert main(["--root", str(tmp_path), "--request", str(request)]) == 0
    assert json.loads(capsys.readouterr().out)["selection_complete"] is True
    request.write_bytes(b"[" * 16385)
    assert main(["--root", str(tmp_path), "--request", str(request)]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "request_input_limit"
