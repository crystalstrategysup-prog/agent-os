from __future__ import annotations

import pytest

from agent_os.config import default_config
from agent_os.speech import transcribe


def test_speech_fails_closed_when_no_provider(monkeypatch, tmp_path):
    config = default_config()
    config["telegram_session_hub"]["speech"]["provider"] = "local"
    monkeypatch.setattr("agent_os.speech.shutil.which", lambda _value: None)
    with pytest.raises(RuntimeError, match="speech_not_configured"):
        transcribe(tmp_path / "voice.ogg", config)
