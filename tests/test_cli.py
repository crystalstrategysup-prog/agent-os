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
