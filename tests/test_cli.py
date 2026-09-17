from __future__ import annotations

import json

from agent_os.cli import main


def test_cli_init_and_doctor(tmp_path, capsys):
    home = tmp_path / "home"
    assert main(["--home", str(home), "init"]) == 0
    capsys.readouterr()
    assert main(["--home", str(home), "doctor"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PASS"


def test_cli_routes_model_and_blocks_incomplete_result(tmp_path, capsys):
    home = tmp_path / "home"
    assert main(["--home", str(home), "init"]) == 0
    capsys.readouterr()
    assert main(["--home", str(home), "route-task", "--mode", "implementation"]) == 0
    route = json.loads(capsys.readouterr().out)
    assert route["model"] == "gpt-5.6-sol"
    payload = tmp_path / "result.json"
    payload.write_text(json.dumps({
        "acceptance": ["user-flow"],
        "evidence": [],
        "now": "2026-09-18T00:00:00Z",
    }), encoding="utf-8")
    assert main(["--home", str(home), "assess-result", "--file", str(payload)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BLOCKED"
