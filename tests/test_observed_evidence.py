import json
import os
from pathlib import Path
import sys

import pytest

from agent_os import observed_command as observer
from agent_os.claim_evidence import aggregate_required, primary_issues


pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX observer")


def run(tmp_path, code=None, **kwargs):
    argv = kwargs.pop("argv", [sys.executable, "-c", code or "pass"])
    return observer.run_observed(argv, cwd=tmp_path, output_root=tmp_path / "evidence",
                                 purpose="regression", claim="selected check", **kwargs)


def terminal_pairs(tmp_path):
    rows = [json.loads(x) for x in (tmp_path / "evidence/operations.jsonl").read_text().splitlines()]
    for op in {x["op"] for x in rows}:
        pair = [x for x in rows if x["op"] == op]
        assert [x["event"] for x in pair] == ["started", "finished"]
    return rows


def test_cli_refuses_unquoted_claim_before_launch(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(observer.subprocess, "Popen", lambda *a, **k: calls.append(a))
    options = ["--purpose", "audit", "--claim", "late", "package", "exact",
               "--cwd", str(tmp_path), "--output-root", str(tmp_path / "evidence")]
    with pytest.raises(SystemExit) as error:
        observer.main(options + ["--", sys.executable, "-c", "pass"])
    assert error.value.code == 2
    with pytest.raises(SystemExit):
        observer.main(options[:4] + options[6:] + [sys.executable])
    assert not calls
    assert not (tmp_path / "evidence").exists()


def test_cli_quoted_claim_and_exact_output(tmp_path, capsys):
    assert observer.main(["--purpose", "audit", "--claim", "late package exact",
                          "--cwd", str(tmp_path), "--output-root", str(tmp_path / "evidence"),
                          "--", sys.executable, "-c", "print('proof')"]) == 0
    row = json.loads(capsys.readouterr().out)
    assert (tmp_path / "evidence" / row["stdout_ref"]).read_bytes() == b"proof\n"
    assert not primary_issues(row, output_root=tmp_path / "evidence")
    terminal_pairs(tmp_path)


def test_missing_executable_has_terminal_failure(tmp_path):
    row = run(tmp_path, argv=[str(tmp_path / "missing-executable")])
    assert row["wrapper_exit"] == 127
    assert row["status"] == "LAUNCH_FAILED" and row["target_started"] is False
    assert row["command_exit"] is None
    assert primary_issues(row, output_root=tmp_path / "evidence")
    terminal_pairs(tmp_path)


def test_stdin_identity_and_artifact_tampering(tmp_path):
    one = run(tmp_path, argv=[sys.executable, "-"], stdin=b"print(1)")
    two = run(tmp_path, argv=[sys.executable, "-"], stdin=b"print(2)")
    assert one["fingerprint"] != two["fingerprint"]
    assert not primary_issues(one, output_root=tmp_path / "evidence")
    (tmp_path / "evidence" / one["stdin_ref"]).write_bytes(b"changed")
    assert "stdin_artifact_missing_or_changed" in primary_issues(one, output_root=tmp_path / "evidence")
    terminal_pairs(tmp_path)


def test_changed_script_is_ineligible(tmp_path):
    script = tmp_path / "selfchange.py"
    script.write_text("from pathlib import Path\nPath(__file__).write_text('pass')\n")
    row = run(tmp_path, argv=[sys.executable, str(script)])
    assert row["wrapper_exit"] == 66 and row["script_inputs_stable"] is False
    assert not row["output_complete"]
    terminal_pairs(tmp_path)


def test_overflow_stops_unbounded_producer(tmp_path):
    row = run(tmp_path, "import os\nwhile True: os.write(1,b'x'*4096)", max_output_bytes=512)
    assert row["wrapper_exit"] == 65 and not row["output_complete"]
    assert row["stdout_captured_bytes"] <= 512
    assert "stdout_ref" not in row
    assert primary_issues(row, output_root=tmp_path / "evidence")
    terminal_pairs(tmp_path)


def test_timeout_kills_descendant_holding_pipe(tmp_path):
    row = run(tmp_path, "import subprocess,sys\nsubprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])",
              timeout=0.15)
    assert row["wrapper_exit"] == 124 and row["seconds"] < 3
    assert not row["output_complete"]
    terminal_pairs(tmp_path)


def test_failed_context_nonterminal_and_missing_fields_cannot_prove(tmp_path):
    failed = run(tmp_path, "raise SystemExit(3)")
    assert primary_issues(failed, output_root=tmp_path / "evidence")
    good = run(tmp_path)
    assert primary_issues(good, output_root=tmp_path / "evidence", role="context_only")
    assert primary_issues(dict(good, role="context_only"), output_root=tmp_path / "evidence")
    assert primary_issues(dict(good, event="started"), output_root=tmp_path / "evidence")
    assert primary_issues({}, output_root=tmp_path / "evidence")
    assert primary_issues(dict(good, input_binding="legacy"), output_root=tmp_path / "evidence")
    terminal_pairs(tmp_path)


@pytest.mark.parametrize("statuses,expected", [
    (["PASS", "PASS"], "PASS"), (["OPEN", "UNKNOWN"], "INCOMPLETE"),
    (["FAIL", "UNKNOWN"], "INCOMPLETE"), (["PENDING_ACCEPTANCE", "PASS"], "INCOMPLETE"),
    (["PASS", "UNKNOWN"], "UNKNOWN"), ([], "UNKNOWN"), (["unexpected"], "UNKNOWN")])
def test_aggregation(statuses, expected):
    assert aggregate_required(statuses) == expected
