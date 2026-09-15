from __future__ import annotations

from agent_os.config import AgentOSPaths, default_config
from agent_os.telegram_bot import SessionBot


class FakeAPI:
    def __init__(self):
        self.calls = []

    def call(self, method, **params):
        self.calls.append((method, params))
        return True


def _bot(tmp_path):
    config = default_config()
    config["telegram_session_hub"]["owner_ids"] = [42]
    return SessionBot(AgentOSPaths.discover(tmp_path / "home"), config, FakeAPI())


def test_non_owner_is_rejected(tmp_path):
    bot = _bot(tmp_path)
    bot.handle({"message": {"chat": {"id": 7}, "from": {"id": 99}, "text": "/start"}})
    assert bot.api.calls[-1][1]["text"].startswith("Access denied")


def test_owner_start_gets_session_hub_menu(tmp_path):
    bot = _bot(tmp_path)
    bot.handle({"message": {"chat": {"id": 7}, "from": {"id": 42}, "text": "/start"}})
    method, params = bot.api.calls[-1]
    assert method == "sendMessage"
    assert "Session Hub" in params["text"]
    callbacks = [
        button["callback_data"]
        for row in params["reply_markup"]["inline_keyboard"]
        for button in row
    ]
    assert {"hub:sessions", "hub:screens", "hub:new", "hub:newscreen"} <= set(callbacks)
